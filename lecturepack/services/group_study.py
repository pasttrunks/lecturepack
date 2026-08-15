"""Study a whole group of lectures as one subject.

A student who has processed five lectures on one topic wants to revise the
topic, not five separate lectures in turn. This builds the cross-lecture map
that makes that possible: which concepts are the same idea taught more than
once, which build on an earlier treatment, what runs through the whole subject,
and where the lectures leave a hole.

The important property is that this is a REDUCE over work already done. Every
lecture stores its own ``lecture_analysis`` when it is processed, so a group of
ten costs ONE request over ten small summaries -- not ten transcripts read
again. On the bundled demo a stored analysis is about 1KB; ten real lectures
land comfortably inside a single prompt. Flashcards, quiz and Teach Me are then
generated from this map by the existing per-concept tasks, which is what keeps
any single request well clear of the route budget that broke Study once before.

The map is cached against the exact set of lectures it was built from. Add a
lecture to the group and the fingerprint changes, so the next session rebuilds;
study the same group again and it is free.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable, Optional

from lecturepack.services import study_v2


GROUP_DIRNAME = "groups"
GROUP_FILENAME = "group-analysis-v1.json"
SCHEMA_VERSION = 1

# A group is a revision unit, not an archive. Past this many lectures the
# reduce stops being one cheap request and the map stops being something a
# student can hold in their head; the UI should ask them to split the subject
# rather than silently truncate it.
MAX_GROUP_LECTURES = 12

# Guard against a single enormous analysis crowding out the others. Ten
# lectures of this size still leave room for the instruction and the schema.
MAX_ANALYSIS_CHARS = 24000


def group_dir(data_dir: str) -> str:
    return os.path.join(str(data_dir), GROUP_DIRNAME)


def _slug(name: str) -> str:
    digest = hashlib.sha256(str(name or "").strip().casefold().encode("utf-8"))
    return digest.hexdigest()[:16]


def analysis_path(data_dir: str, group: str) -> str:
    return os.path.join(group_dir(data_dir), _slug(group), GROUP_FILENAME)


def fingerprint(members: list[dict[str, Any]]) -> str:
    """Identify the exact lectures a map was built from.

    Keyed on job id AND the generation timestamp of each lecture's own pack, so
    re-processing one lecture invalidates the group map that quoted it. Order
    is normalised: reordering the library is not a content change.
    """
    parts = sorted(
        f"{str(member.get('job_id') or '')}:{str(member.get('generated_at') or '')}"
        for member in members)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def collect_members(jobs: list[Any]) -> list[dict[str, Any]]:
    """Gather the stored analysis of every lecture that has one.

    A lecture still processing, or one whose Study pack failed, simply is not
    here. That is what lets a group be studied while one of its lectures is
    still being processed -- the map covers what is ready, and rebuilds when
    the rest arrives.
    """
    members = []
    for job in jobs:
        try:
            content = study_v2.load_content(job)
        except Exception:  # noqa: BLE001 - a broken pack must not sink the group
            continue
        if content.get("study_status") not in {study_v2.STUDY_READY, study_v2.STUDY_BASIC}:
            continue
        analysis = content.get("lecture_analysis")
        if not isinstance(analysis, dict) or not analysis.get("concepts"):
            continue
        members.append({
            "job_id": str(getattr(job, "job_id", "")),
            "title": str((getattr(job, "manifest", {}) or {}).get("title") or ""),
            "generated_at": str(content.get("generated_at") or ""),
            "analysis": analysis,
            "concepts": content.get("concepts") or [],
        })
    return members


def build_evidence(members: list[dict[str, Any]]) -> dict[str, Any]:
    """The request body: every lecture's map, tagged with where it came from."""
    lectures = []
    for member in members[:MAX_GROUP_LECTURES]:
        analysis = json.dumps(member["analysis"], ensure_ascii=False)
        if len(analysis) > MAX_ANALYSIS_CHARS:
            # Keep the concept list, which is what the reduce actually merges,
            # rather than truncating mid-JSON into something unparseable.
            trimmed = {
                "lecture_summary": member["analysis"].get("lecture_summary", ""),
                "concepts": (member["analysis"].get("concepts") or [])[:24],
            }
            analysis = json.dumps(trimmed, ensure_ascii=False)
        lectures.append({
            "job_id": member["job_id"],
            "title": member["title"],
            "analysis": json.loads(analysis),
        })
    return {"lectures": lectures}


def load_cached(data_dir: str, group: str, expected: str) -> Optional[dict[str, Any]]:
    """Return the stored map only when it matches the group as it is now."""
    path = analysis_path(data_dir, group)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(stored, dict):
        return None
    if int(stored.get("schema_version", 0)) != SCHEMA_VERSION:
        return None
    if str(stored.get("fingerprint") or "") != expected:
        return None
    analysis = stored.get("analysis")
    return analysis if isinstance(analysis, dict) else None


def save(data_dir: str, group: str, fingerprint_value: str,
         analysis: dict[str, Any], members: list[dict[str, Any]]) -> str:
    path = analysis_path(data_dir, group)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    document = {
        "schema_version": SCHEMA_VERSION,
        "group": str(group),
        "fingerprint": fingerprint_value,
        "job_ids": [member["job_id"] for member in members],
        "analysis": analysis,
    }
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False)
    os.replace(temporary, path)
    return path


def unwrap_result(raw: Any) -> Any:
    """Take the analysis out of the gateway's envelope.

    ``GatewayClient.request`` answers ``{"result": ..., "diagnostics": ...}``;
    the map is under ``result``. Handing the envelope straight to ``normalize``
    finds no ``concepts`` at the top level and silently yields an empty map, so
    a perfectly good answer reads as ``empty_analysis`` -- which is exactly how
    group study shipped broken past a suite of mocks that returned the
    unwrapped shape. Both shapes are accepted because ``prepare`` also takes an
    injected ``call``, which may hand back a bare analysis.
    """
    if isinstance(raw, dict) and "concepts" not in raw:
        inner = raw.get("result")
        if isinstance(inner, dict):
            return inner
    return raw


def normalize(analysis: Any, members: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep only what the supplied lectures can actually support.

    Same discipline as single-lecture grounding: a concept attributed to a job
    that is not in this group would send a student to a citation that does not
    exist, so it is dropped rather than shown.
    """
    known = {member["job_id"] for member in members}
    if not isinstance(analysis, dict):
        return {}
    concepts = []
    for item in analysis.get("concepts") or []:
        if not isinstance(item, dict):
            continue
        job_ids = [str(j) for j in (item.get("job_ids") or []) if str(j) in known]
        if not job_ids:
            continue
        concepts.append({**item, "job_ids": job_ids})
    concept_ids = {str(c.get("id") or "") for c in concepts}
    relationships = [
        item for item in analysis.get("relationships") or []
        if isinstance(item, dict)
        and str(item.get("from_concept_id") or "") in concept_ids
        and str(item.get("to_concept_id") or "") in concept_ids
    ]
    def _scoped(key: str) -> list[dict[str, Any]]:
        rows = []
        for item in analysis.get(key) or []:
            if not isinstance(item, dict):
                continue
            ids = [str(c) for c in (item.get("concept_ids") or []) if str(c) in concept_ids]
            rows.append({**item, "concept_ids": ids})
        return rows
    return {
        "group_summary": str(analysis.get("group_summary") or ""),
        "concepts": concepts,
        "relationships": relationships,
        "through_lines": _scoped("through_lines"),
        "gaps": _scoped("gaps"),
    }


def prepare(data_dir: str, group: str, jobs: list[Any], client: Any, *,
            force: bool = False,
            call: Optional[Callable[..., Any]] = None) -> dict[str, Any]:
    """Return the group's cross-lecture map, building it only when needed."""
    members = collect_members(jobs)
    if not members:
        return {"ok": False, "reason": "no_ready_lectures", "members": []}
    mark = fingerprint(members)
    if not force:
        cached = load_cached(data_dir, group, mark)
        if cached is not None:
            return {"ok": True, "cached": True, "analysis": cached, "members": members}
    request = call or (lambda task, payload: client.request(task, payload))
    raw = request("group_analysis", build_evidence(members))
    analysis = normalize(unwrap_result(raw), members)
    if not analysis.get("concepts"):
        return {"ok": False, "reason": "empty_analysis", "members": members}
    save(data_dir, group, mark, analysis, members)
    return {"ok": True, "cached": False, "analysis": analysis, "members": members}
