"""Pure (Qt-free, network-free) update logic for the in-app updater.

Everything here is deterministic and unit-testable: version comparison,
channel filtering over a GitHub releases *list* (so prereleases are
discoverable — /releases/latest hides them), strict asset selection, SHA256
verification, and building the update-overview payload. The Qt orchestration
(threads, download, installer handoff) lives in updater.py and calls into here.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Optional
from urllib.parse import urlparse

from packaging.version import InvalidVersion, Version

APP_NAME = "LecturePack"

# Hosts we accept release-asset downloads from without extra configuration.
# Production never widens this; tests may pass extra_hosts explicitly.
TRUSTED_ASSET_HOSTS = frozenset({
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})

# GitHub's auto-generated source archives — never an update artifact.
_SOURCE_ARCHIVE_NAMES = {"source code (zip)", "source code (tar.gz)"}

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


# --------------------------------------------------------------------------- #
# Versions (§5) — never compare tags as plain strings.
# --------------------------------------------------------------------------- #
def parse_version(tag: str) -> Optional[Version]:
    """Parse a tag like 'v0.9.0-beta.2' -> Version, or None if malformed."""
    if not tag:
        return None
    t = re.sub(r"^[vV]", "", str(tag).strip())
    try:
        return Version(t)
    except InvalidVersion:
        return None


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    if r is None or l is None:
        return False
    return r > l


def channel_of(value) -> str:
    """'beta' for a prerelease version, else 'stable'."""
    ver = value if isinstance(value, Version) else parse_version(value)
    if ver is None:
        return "stable"
    return "beta" if ver.is_prerelease else "stable"


def _release_version(rel: dict) -> Optional[Version]:
    return parse_version(rel.get("tag_name") or rel.get("name") or "")


def _release_tag(rel: dict) -> str:
    """Original release tag with a leading v/V stripped (e.g. '0.9.0-beta.2').

    Asset filenames and the user-facing version use this friendly tag form;
    comparison uses the parsed Version. The two differ ('0.9.0-beta.2' vs the
    normalized '0.9.0b2'), and asset names are built from the tag.
    """
    return re.sub(r"^[vV]", "", str(rel.get("tag_name") or rel.get("name") or "").strip())


# --------------------------------------------------------------------------- #
# Release-feed filtering (§4).
# --------------------------------------------------------------------------- #
def select_release(releases, current: str, channel: str = "beta",
                   skipped: Optional[str] = None) -> Optional[dict]:
    """Pick the newest compatible published release for the channel.

    Returns {"release", "version", "is_skipped"} or None. Draft releases and
    unparseable tags are ignored; a stable channel ignores prereleases; only
    versions strictly newer than ``current`` qualify. ``skipped`` only sets the
    ``is_skipped`` flag (the newest release is still chosen) so the caller can
    decide whether to auto-prompt.
    """
    cur = parse_version(current)
    best = None
    best_v: Optional[Version] = None
    for rel in releases or []:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        v = _release_version(rel)
        if v is None:
            continue
        if channel == "stable" and v.is_prerelease:
            continue
        if cur is not None and not (v > cur):
            continue
        if best_v is None or v > best_v:
            best, best_v = rel, v
    if best is None or best_v is None:
        return None
    skip_v = parse_version(skipped) if skipped else None
    return {"release": best, "version": _release_tag(best), "parsed": str(best_v),
            "is_skipped": skip_v is not None and skip_v == best_v}


# --------------------------------------------------------------------------- #
# Asset selection (§6).
# --------------------------------------------------------------------------- #
def expected_asset_names(version: str, portable: bool = False) -> tuple[str, str]:
    primary = (f"{APP_NAME}-{version}-Portable.zip" if portable
               else f"{APP_NAME}-{version}-Setup.exe")
    return primary, f"{APP_NAME}-{version}-SHA256SUMS.txt"


def _url_ok(url: str, extra_hosts=None) -> bool:
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    extra = {h.lower() for h in (extra_hosts or [])}
    if u.scheme == "https":
        return host in (TRUSTED_ASSET_HOSTS | extra)
    # Plain http is accepted ONLY for an explicitly configured host (test feed /
    # enterprise mirror). Production has no extra_hosts, so it stays https-only.
    if u.scheme == "http" and host in extra:
        return True
    return False


def _asset_url(asset: dict) -> str:
    return asset.get("browser_download_url") or asset.get("url") or ""


def select_asset(release: dict, version: str, portable: bool = False,
                 extra_hosts=None) -> dict:
    """Return {"installer": asset, "checksum": asset} or raise ValueError.

    Requires the exact expected filenames, rejects source archives, and
    validates state==uploaded, non-zero size, and https on a trusted host.
    """
    primary_name, sums_name = expected_asset_names(version, portable)
    by_name: dict[str, dict] = {}
    for a in release.get("assets", []) or []:
        name = (a.get("name") or "").strip()
        if not name or name.lower() in _SOURCE_ARCHIVE_NAMES:
            continue
        by_name[name] = a

    installer = by_name.get(primary_name)
    if installer is None:
        raise ValueError(f"release is missing expected asset {primary_name}")
    checksum = by_name.get(sums_name)
    if checksum is None:
        raise ValueError(f"release is missing checksum file {sums_name}")

    for asset, label in ((installer, primary_name), (checksum, sums_name)):
        state = asset.get("state")
        if state not in (None, "uploaded"):
            raise ValueError(f"asset {label} is not uploaded (state={state})")
        if int(asset.get("size", 0) or 0) <= 0:
            raise ValueError(f"asset {label} has a zero/unknown size")
        if not _url_ok(_asset_url(asset), extra_hosts):
            raise ValueError(f"asset {label} url is not https on a trusted host")
    return {"installer": installer, "checksum": checksum}


# --------------------------------------------------------------------------- #
# Hashing / verification (§6, §13).
# --------------------------------------------------------------------------- #
def digest_from_asset(asset: dict) -> Optional[str]:
    """GitHub asset 'digest' ('sha256:<hex>') -> lowercase hex, or None."""
    d = str((asset or {}).get("digest") or "")
    if d.lower().startswith("sha256:"):
        h = d.split(":", 1)[1].strip().lower()
        if _HEX64.match(h):
            return h
    return None


def parse_sha256sums(text: str, filename: str) -> Optional[str]:
    """Find the lowercase digest for ``filename`` in a SHA256SUMS.txt body."""
    want = os.path.basename(filename).strip().lower()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^([0-9a-fA-F]{64})[ \t]+[*]?(.+)$", line)
        if not m:
            continue
        digest, name = m.group(1).lower(), m.group(2).strip()
        if os.path.basename(name).lower() == want:
            return digest
    return None


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_file(path: str, expected_hex: Optional[str]) -> bool:
    if not expected_hex or not _HEX64.match(expected_hex):
        return False
    return sha256_file(path).lower() == expected_hex.lower()


def reconcile_digests(sums_hex: Optional[str], asset_hex: Optional[str]):
    """Return (expected_hex, ok). If both present they must agree; otherwise
    use whichever exists. (None, False) when neither is available."""
    if sums_hex and asset_hex:
        return (sums_hex, sums_hex.lower() == asset_hex.lower())
    chosen = sums_hex or asset_hex
    return (chosen, chosen is not None)


# --------------------------------------------------------------------------- #
# Overview payload (§3 View Update).
# --------------------------------------------------------------------------- #
def human_size(num) -> str:
    n = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


_SECTION_KEYS = (
    ("improvements", ("improv", "feature", "add", "new", "smart", "core")),
    ("fixes", ("fix", "bug", "patch")),
    ("limitations", ("limitation", "known", "caveat")),
)


def extract_notes(body: str) -> dict:
    """Split a markdown release body into plain-text bullet lists by section.

    Returns {improvements[], fixes[], limitations[], notes[]}. Only plain text
    is kept (the UI escapes it) — no HTML/script is ever produced or executed.
    """
    out = {"improvements": [], "fixes": [], "limitations": [], "notes": []}
    current = "notes"
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            current = "notes"
            for key, words in _SECTION_KEYS:
                if any(w in heading for w in words):
                    current = key
                    break
            continue
        if line.startswith(("- ", "* ", "+ ")):
            text = re.sub(r"\s+", " ", line[2:].strip())
            if text:
                out[current].append(text)
                out["notes"].append(text)
    if not out["notes"] and (body or "").strip():
        out["notes"] = [re.sub(r"\s+", " ", (body or "").strip())[:280]]
    for k in out:
        out[k] = out[k][:20]
    return out


def build_overview(release: dict, current: str, installer_asset: dict = None,
                   portable: bool = False) -> dict:
    """Assemble the polished Update Overview payload for the UI."""
    v = _release_version(release)
    version = _release_tag(release) or (str(v) if v is not None else "")
    notes = extract_notes(release.get("body", "") or "")
    size = human_size(installer_asset.get("size")) if installer_asset else ""
    return {
        "current": current,
        "available": version,
        "version": version,  # back-compat with the existing overlay
        "title": release.get("name") or f"{APP_NAME} {version}",
        "date": (release.get("published_at") or "")[:10],
        "size": size,
        "channel": "Beta" if channel_of(v) == "beta" else "Stable",
        "prerelease": bool(release.get("prerelease")) or channel_of(v) == "beta",
        "improvements": notes["improvements"],
        "fixes": notes["fixes"],
        "limitations": notes["limitations"],
        "notes": notes["notes"],
        "url": release.get("html_url") or "",
        "portable": bool(portable),
    }
