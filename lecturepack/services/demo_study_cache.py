"""A pre-built Study pack for the bundled demo lecture.

The guided demo is a 10-second video whose only job is to show a student what
LecturePack produces. Building its Study pack for real means a full gateway
round trip -- lecture analysis, material generation, source validation --
measured at 15.6s on the bundled lecture, on top of local processing. That is
a long time to hold someone who has not yet decided to use the app. The pack
is therefore generated once, at build time, from a real run of that exact
video, and shipped alongside it.

This is a cache, not a fake. The shipped file is the genuine output of the
normal pipeline over the bundled lecture, so the demo shows a student exactly
what their own lectures will produce. Three things guard it:

* The demo video's SHA-256 is recorded in the cache. Swap the bundled lecture
  and the cache stops applying rather than describing the wrong video.
* Source citations are positional (segment IDs are transcript indices, slide
  IDs are indices or image filenames), so they stay correct only while the
  transcript and slide list have the shape they had at capture time. Both
  counts are recorded and checked.
* Regenerating from the Study screen bypasses the cache entirely, so a student
  who wants a real build can always have one.

Any mismatch means the demo simply builds its pack the normal way. A stale or
missing cache costs time, never correctness.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional


CACHE_FILENAME = "study-content-v2.json"

# The attested bundled lecture (app/assets/demo/PROVENANCE.md). The cache
# describes THIS video and no other.
DEMO_VIDEO_SHA256 = "24957e863c477cd7ad2ef9228f3bbe943f5038e5ccd18ef7ab92efefee13f55f"


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_cache(*roots: Any) -> str:
    """Return the shipped cache file, or "" when it is not present.

    package-win.mjs copies app/assets/demo into resources/assets/demo, so the
    packaged app finds it beside the guided-demo assets it already ships; a
    developer checkout finds the same file at its source location.
    """
    for root in roots:
        if not root:
            continue
        for parts in (("assets", "demo"), ("app", "assets", "demo")):
            candidate = os.path.join(str(root), *parts, CACHE_FILENAME)
            if os.path.isfile(candidate):
                return candidate
    return ""


def load_cache(path: str) -> Optional[dict[str, Any]]:
    """Read the cache file. A malformed cache is treated as absent."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("content"), dict):
        return None
    return data


def matches(cache: dict[str, Any], video_path: str, segment_count: int,
            slide_count: int) -> bool:
    """Is this cache describing the lecture that was actually processed?

    Deliberately strict. A cache that half-matches would attach real-looking
    citations to the wrong timestamps, which is worse than any wait.
    """
    if not isinstance(cache, dict):
        return False
    expects = cache.get("expects")
    if not isinstance(expects, dict):
        return False
    if int(expects.get("segment_count", -1)) != int(segment_count):
        return False
    if int(expects.get("slide_count", -1)) != int(slide_count):
        return False
    recorded = str(cache.get("demo_video_sha256") or "")
    if recorded != DEMO_VIDEO_SHA256:
        return False
    try:
        if sha256_of(video_path) != DEMO_VIDEO_SHA256:
            return False
    except OSError:
        return False
    return True


def content_for(cache: dict[str, Any]) -> dict[str, Any]:
    """The study-content-v2 document to persist, marked as what it is."""
    content = json.loads(json.dumps(cache.get("content") or {}))
    metadata = content.get("generation_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        content["generation_metadata"] = metadata
    metadata["stage"] = "Ready"
    metadata["progress_percent"] = 100
    metadata["last_error"] = ""
    # Recorded so the pack is never mistaken for a live build when reading a
    # support bundle, and so the UI could say so if it ever wants to.
    metadata["demo_cache"] = True
    metadata.pop("basic_reason", None)
    return content
