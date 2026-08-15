"""Durable state for the current guided-tour offer.

The guided tour is an onboarding affordance, not a property of the lecture
library.  Keeping its version and status in the existing config file lets an
existing user receive a new tour without manufacturing an empty job list or a
second persistence system.
"""
from __future__ import annotations

from typing import Any


CURRENT_GUIDED_TOUR_VERSION = 2
CURRENT_GUIDED_TOUR_LABEL = "2.0.1"
GUIDED_TOUR_STATUSES = frozenset({"not_seen", "skipped", "completed"})


def _version(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _normalized(settings: dict[str, Any]) -> tuple[int, int, str]:
    current = max(
        CURRENT_GUIDED_TOUR_VERSION,
        _version(settings.get("guided_tour_version"), CURRENT_GUIDED_TOUR_VERSION),
    )
    seen = _version(settings.get("guided_tour_seen_version"), 0)
    status = str(settings.get("guided_tour_status") or "").strip().lower()
    if status not in GUIDED_TOUR_STATUSES:
        status = "completed" if seen >= current and seen > 0 else "not_seen"
    # A stale terminal marker must not suppress a newly introduced version.
    if seen < current and status in {"skipped", "completed"}:
        status = "not_seen"
    return current, seen, status


def guided_tour_state(settings: dict[str, Any]) -> dict[str, Any]:
    """Return the renderer-facing state without depending on library jobs."""
    current, seen, status = _normalized(settings)
    eligible = status == "not_seen" or seen < current
    return {
        "current_version": current,
        "seen_version": seen,
        "version": CURRENT_GUIDED_TOUR_LABEL,
        "status": status,
        "completed": status == "completed",
        "skipped": status == "skipped",
        "eligible": eligible,
        # Explicit key names make the JSON contract self-documenting and keep
        # the config names visible to diagnostics/support tooling.
        "guided_tour_version": current,
        "guided_tour_seen_version": seen,
        "guided_tour_status": status,
        "tour_eligible": eligible,
    }


def ensure_guided_tour_state(config: Any) -> dict[str, Any]:
    """Seed/migrate the three small config keys and return current state.

    Missing keys are treated as an unseen current tour.  No renderer
    localStorage value is consulted, so an old UI profile cannot hide the
    current tour from an existing user.
    """
    settings = config.settings
    current, seen, status = _normalized(settings)
    changed = (
        settings.get("guided_tour_version") != current
        or settings.get("guided_tour_seen_version") != seen
        or settings.get("guided_tour_status") != status
    )
    if changed:
        settings["guided_tour_version"] = current
        settings["guided_tour_seen_version"] = seen
        settings["guided_tour_status"] = status
        config.save()
    return guided_tour_state(settings)


def set_guided_tour_status(config: Any, status: Any) -> dict[str, Any]:
    """Persist one of the small, explicit tour lifecycle states."""
    normalized = str(status or "").strip().lower()
    if normalized not in GUIDED_TOUR_STATUSES:
        raise ValueError(f"unsupported guided tour status: {status!r}")
    state = ensure_guided_tour_state(config)
    current = int(state["current_version"])
    config.settings["guided_tour_status"] = normalized
    config.settings["guided_tour_seen_version"] = current if normalized != "not_seen" else 0
    config.save()
    return guided_tour_state(config.settings)


def clear_guided_tour_state(config: Any) -> None:
    """Remove tour keys during a full reset; the next launch seeds v2 again."""
    for key in (
        "guided_tour_version",
        "guided_tour_seen_version",
        "guided_tour_status",
    ):
        config.settings.pop(key, None)
    config.save()
