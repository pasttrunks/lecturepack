"""Build the disposable media fixtures the packaged acceptance gate needs.

scripts/stable_release_acceptance.py takes four media arguments. Three of them
are satisfied by the bundled Polar Bears demo, but `--long` is not: the gate
waits for a live ETA label, and the renderer only shows one once a job has been
running for 20+ seconds with 20+ seconds still remaining
(see etaLabel/processingEta in app/ui/app.js). The 10-second demo transcribes
faster than that threshold, so the ETA never appears and the gate times out
with "timed out waiting for live progress and ETA on long workload".

This builds a long fixture by concatenating the SAME Polar Bears demo with the
bundled FFmpeg. No other video is introduced: the fixture is the shipped demo
repeated, it lives under C:\\LecturePackScratch, and it is never packaged. The
release contains exactly one video -- the 10-second demo.

Usage:
    python scripts/make_acceptance_fixtures.py --out C:/LecturePackScratch/data/fixtures

Then:
    python scripts/stable_release_acceptance.py \\
        --exe <candidate>/LecturePack.exe \\
        --demo electron-spike/assets/demo-lecture.mp4 \\
        --packaged-demo <candidate>/resources/assets/demo-lecture.mp4 \\
        --secondary electron-spike/assets/demo-lecture.mp4 \\
        --long <out>/polar-bears-long.mp4 \\
        --evidence <results>
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "electron-spike" / "assets" / "demo-lecture.mp4"
# 126 x ~10s of source runs ~21 minutes, which reliably clears the ETA
# threshold with plenty of margin on a slow machine.
DEFAULT_REPEATS = 126


def build(out_dir: Path, repeats: int, ffmpeg: Path) -> Path:
    if not DEMO.is_file():
        raise SystemExit(f"bundled demo is missing: {DEMO}")
    out_dir.mkdir(parents=True, exist_ok=True)
    listing = out_dir / "polar-bears-concat.txt"
    target = out_dir / "polar-bears-long.mp4"
    source = str(DEMO).replace("\\", "/")
    listing.write_text("".join(f"file '{source}'\n" for _ in range(repeats)), encoding="utf-8")
    if target.exists():
        target.unlink()
    subprocess.run(
        [str(ffmpeg), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(target)],
        check=True, shell=False, timeout=1800,
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="disposable fixture directory")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--ffmpeg", type=Path, default=ROOT / "bin" / "ffmpeg.exe")
    args = parser.parse_args(argv)

    if "LecturePackData" in str(args.out.resolve()):
        raise SystemExit("refusing to write fixtures into a real LecturePackData directory")

    target = build(args.out.resolve(), args.repeats, args.ffmpeg)
    print(f"built {target} from {args.repeats} copies of the bundled Polar Bears demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
