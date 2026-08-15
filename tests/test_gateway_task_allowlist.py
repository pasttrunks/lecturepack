"""Every Study task the app calls must be reachable end to end.

GatewayClient.request rejects any task missing from TASK_TYPES with a plain
ValueError. That is the right guard -- it stops an unreviewed task type
reaching the gateway -- but it makes forgetting an entry silent in the worst
possible way: the caller is a background pass wrapped in `except Exception:
continue`, so an unlisted task looks exactly like "the model had nothing to
add". The pack-expansion feature shipped that way. Every one of its requests
raised, every one was swallowed, and Study packs stayed at the generator's
schema minimum of two flashcards and three questions while the code that grows
them looked correct and the app reported no error at all.

So the allowlist is checked against the call sites rather than maintained by
hand, and against the gateway's own task list, which is the other half of the
same round trip.
"""

from __future__ import annotations

import re
from pathlib import Path

from lecturepack.services.ai_gateway import TASK_TYPES


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "lecturepack" / "services"
GATEWAY_TASKS = ROOT / "ai-gateway" / "src" / "tasks.js"


def called_tasks() -> set[str]:
    """Every task name the app actually asks the gateway for."""
    found: set[str] = set()
    for path in SERVICES.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r'_call\(\s*client\s*,\s*"([a-z_]+)"', text))
        # Both `client.request("x", ...)` and a locally bound `request("x", ...)`
        # -- group_study injects the callable so the reduce can be tested
        # without a live gateway, and the task name is still a literal there.
        found.update(re.findall(r'\brequest\(\s*"([a-z_]+)"', text))
    return found


def test_every_task_the_app_calls_is_on_the_allowlist():
    missing = called_tasks() - TASK_TYPES
    assert not missing, (
        f"these tasks are called but would raise ValueError: {sorted(missing)}. "
        "Callers swallow exceptions, so the feature would silently do nothing."
    )


def test_the_allowlist_has_no_task_nothing_calls():
    """A stale entry is a smaller problem than a missing one, but it still
    means the allowlist has stopped describing the app."""
    unused = TASK_TYPES - called_tasks()
    assert not unused, f"allowlist entries with no caller: {sorted(unused)}"


def test_the_expansion_task_specifically_is_reachable():
    """The one that shipped broken."""
    assert "expand_concept_material" in TASK_TYPES
    assert "expand_concept_material" in called_tasks()


def test_the_gateway_defines_every_task_the_client_may_send():
    """The other half of the round trip: an allowlisted task the Worker does
    not implement fails just as silently, only over the network."""
    if not GATEWAY_TASKS.is_file():
        import pytest
        pytest.skip("gateway source not present in this checkout")
    source = GATEWAY_TASKS.read_text(encoding="utf-8")
    for task in sorted(TASK_TYPES):
        assert re.search(rf"\b{re.escape(task)}\s*:", source), (
            f"{task} is allowlisted in the client but not defined in the gateway"
        )
