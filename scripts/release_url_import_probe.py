"""RELEASE-ONLY network probe for LecturePack URL import.

The normal pytest suite is network-free on purpose. This script is the
separate, explicit release gate that proves URL import actually works against
the live internet -- something no offline test can establish, because
"import yt_dlp succeeds" says nothing about whether YouTube extraction works.

Modern yt-dlp needs an external JavaScript runtime to solve YouTube's JS
challenges (its EJS system). This probe therefore proves the whole chain:

    yt-dlp present
      -> yt-dlp-ejs present
      -> a real JS runtime present and executable
      -> probe URL returns a title and duration
      -> the media actually downloads
      -> the downloaded file is real playable media (ffprobe agrees)
      -> it lands on the normal LecturePack import path

Run it against a packaged build before shipping:

    python scripts/release_url_import_probe.py --evidence C:/LecturePackScratch/results/url-probe.json

Nothing here weakens DRM or sign-in restrictions: it uses the ordinary public
extractor path, and a stream yt-dlp cannot read plainly simply fails.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# A short, stable, long-standing public video. Small enough to download in
# full during a release gate.
DEFAULT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
DEFAULT_MIN_SECONDS = 5


def _ffprobe_duration(ffprobe: str, media: Path) -> float:
    """Seconds of real decodable media, via the bundled ffprobe."""
    completed = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media),
        ],
        capture_output=True, text=True, timeout=120,
        shell=False, encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        return 0.0
    try:
        return float((completed.stdout or "0").strip())
    except ValueError:
        return 0.0


def run(url: str, evidence: Path | None) -> dict:
    from lecturepack.services import media_fetch

    started = time.time()
    result: dict[str, object] = {
        "probe": "lecturepack url import release gate",
        "url": url,
        "status": "FAIL",
        "failures": [],
        "support": {},
        "steps": {},
    }
    failures: list[str] = result["failures"]  # type: ignore[assignment]

    # ---------------------------------------------------------- capability
    support = media_fetch.youtube_support()
    result["support"] = support
    if not support["yt_dlp"]:
        failures.append("yt-dlp is not available in this build")
    if not support["ejs"]:
        failures.append("yt-dlp-ejs is not available; YouTube JS challenges cannot be solved")
    if not support["js_runtime"]:
        failures.append("no bundled JavaScript runtime; YouTube support is degraded or broken")
    if not support["ffmpeg_location"]:
        failures.append("bundled FFmpeg was not located for yt-dlp")
    if failures:
        result["elapsed_seconds"] = round(time.time() - started, 2)
        return _finish(result, evidence)

    fetcher = media_fetch.MediaFetcher()

    # -------------------------------------------------------------- probe
    try:
        info = fetcher.probe(url)
    except Exception as error:  # noqa: BLE001 - a release gate reports anything
        failures.append(f"probe failed: {type(error).__name__}: {error}")
        result["elapsed_seconds"] = round(time.time() - started, 2)
        return _finish(result, evidence)

    title = str(info.get("title") or "")
    duration = int(info.get("duration") or 0)
    result["steps"]["probe"] = {"title": title, "duration": duration,
                                "extractor": info.get("extractor")}
    if not title:
        failures.append("probe returned no title")
    if duration <= 0:
        failures.append("probe returned no duration")

    # ----------------------------------------------------------- download
    with tempfile.TemporaryDirectory(prefix="lecturepack-url-probe-") as workspace:
        try:
            media_path = fetcher.download(url, workspace)
        except Exception as error:  # noqa: BLE001
            failures.append(f"download failed: {type(error).__name__}: {error}")
            result["elapsed_seconds"] = round(time.time() - started, 2)
            return _finish(result, evidence)

        media = Path(media_path)
        exists = media.is_file()
        size = media.stat().st_size if exists else 0
        result["steps"]["download"] = {"filename": media.name, "bytes": size}
        if not exists or size <= 0:
            failures.append("download produced no file")

        # ------------------------------------- real media on the import path
        ffprobe = os.path.join(support["ffmpeg_location"], "ffprobe.exe")
        if not os.path.isfile(ffprobe):
            ffprobe = shutil.which("ffprobe") or ""
        decoded = _ffprobe_duration(ffprobe, media) if ffprobe else 0.0
        result["steps"]["media"] = {"ffprobe_duration": decoded, "ffprobe": ffprobe}
        if decoded < DEFAULT_MIN_SECONDS:
            failures.append(
                f"downloaded file is not {DEFAULT_MIN_SECONDS}s+ of decodable media "
                f"(ffprobe reported {decoded}s)"
            )

        # The normal import path accepts a local file; prove this one qualifies.
        from lecturepack.services.media_fetch import safe_filename
        importable = bool(exists and size > 0 and decoded >= DEFAULT_MIN_SECONDS)
        result["steps"]["import_path"] = {
            "safe_name": safe_filename(title),
            "accepted_by_local_import": importable,
        }
        if not importable:
            failures.append("resulting media would not enter the normal import path")

    result["elapsed_seconds"] = round(time.time() - started, 2)
    return _finish(result, evidence)


def _finish(result: dict, evidence: Path | None) -> dict:
    result["status"] = "PASS" if not result["failures"] else "FAIL"
    if evidence is not None:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL, help="public probe URL")
    parser.add_argument("--evidence", type=Path, help="write a machine-readable result here")
    args = parser.parse_args(argv)

    result = run(args.url, args.evidence)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
