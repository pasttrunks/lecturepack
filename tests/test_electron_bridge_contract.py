"""Regression tests for the LecturePack Electron/Python bridge contract (Phase 8)."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "electron-spike" / "contracts" / "electron-bridge-contract.json"
UI_APP = ROOT / "app" / "ui" / "app.js"
SIDECAR = ROOT / "electron-spike" / "python-sidecar.py"
BRIDGE = ROOT / "electron-spike" / "electron-bridge.js"
MAIN = ROOT / "electron-spike" / "production-main.js"
VALID_STATUS = {"IMPLEMENTED", "PARTIAL", "MISSING", "DEFERRED"}
_EXTRA = {"start_demo_job", "end_demo_job", "ui_ready"}
_CALL = re.compile(r"lpBridge\.call\(\s*['\"]([A-Za-z0-9_]+)")
_ON = re.compile(r"lpBridge\.(?:on|emit)\(\s*['\"]([A-Za-z0-9_]+)")


def load():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def calls():
    found = set(_CALL.findall(UI_APP.read_text(encoding="utf-8")))
    found.update(_EXTRA)
    return found


def subs():
    return set(_ON.findall(UI_APP.read_text(encoding="utf-8")))


def cmds(p):
    t = p.read_text(encoding="utf-8")
    s = set(_CALL.findall(t))
    s |= set(re.findall(r"command\s*==\s*['\"]([A-Za-z0-9_]+)['\"]", t))
    s |= set(re.findall(r"command\s*===\s*['\"]([A-Za-z0-9_]+)['\"]", t))
    s |= set(re.findall(r"name\s*===\s*['\"]([A-Za-z0-9_]+)['\"]", t))
    s |= set(re.findall(r"command:\s*['\"]([A-Za-z0-9_]+)['\"]", t))
    return s


def evts(p):
    t = p.read_text(encoding="utf-8")
    s = set(re.findall(r"\"event\":\s*\"([A-Za-z0-9_]+)\"", t))
    s |= set(re.findall(r"event:\s*'([A-Za-z0-9_]+)'", t))
    s |= set(re.findall(r"event\s*===\s*'([A-Za-z0-9_]+)'", t))
    return s


def transport(op):
    names = {op["name"]}
    m = (op.get("mapped_to") or "").strip()
    if m and "+" not in m and "->" not in m:
        names.add(m)
    return names


def test_contract_valid_and_deterministic():
    data = load()
    assert data["contract"] == "lecturepack-electron-bridge"
    assert data["version"] == 1
    ops = data["operations"]
    assert ops
    for op in ops:
        assert op["status"] in VALID_STATUS, op["name"]
        assert op["direction"] in ("command", "event"), op["name"]
        assert isinstance(op["production_core"], bool), op["name"]
        assert isinstance(op["request_id_required"], bool), op["name"]
        assert isinstance(op["request_fields"], list), op["name"]
        assert isinstance(op["response_fields"], list), op["name"]
        assert isinstance(op["event_fields"], list), op["name"]
    assert json.loads(json.dumps(data, sort_keys=True)) == data


def test_operation_names_are_unique():
    ops = load()["operations"]
    names = [op["name"] for op in ops]
    assert len(names) == len(set(names)), "duplicate operation names"
    directions = {}
    for op in ops:
        assert directions.setdefault(op["name"], op["direction"]) == op["direction"]


def test_every_frontend_bridge_call_is_in_contract():
    contract = {op["name"]: op for op in load()["operations"]}
    missing = sorted(calls() - set(contract))
    assert not missing, "frontend bridge calls missing: %s" % missing
    for name in calls():
        assert contract[name]["direction"] == "command", name


def test_every_frontend_signal_is_in_contract():
    contract = {op["name"]: op for op in load()["operations"]}
    missing = sorted(subs() - set(contract))
    assert not missing, "frontend subscriptions missing: %s" % missing
    for name in subs():
        assert contract[name]["direction"] == "event", name


def test_implemented_core_commands_exist():
    known = cmds(SIDECAR) | cmds(MAIN) | cmds(BRIDGE)
    checked = [(op, transport(op)) for op in load()["operations"]
               if op["production_core"] and op["direction"] == "command"
               and op["status"] == "IMPLEMENTED"]
    assert checked
    for op, names in checked:
        assert names & known, "IMPLEMENTED core command %s -> %s missing" % (
            op["name"], names)


def test_implemented_core_events_exist():
    emitted = evts(SIDECAR) | evts(MAIN) | evts(BRIDGE)
    checked = [op for op in load()["operations"]
               if op["production_core"] and op["direction"] == "event"
               and op["status"] == "IMPLEMENTED"]
    assert checked
    for op in checked:
        assert op["name"] in emitted, "IMPLEMENTED core event %s missing" % op["name"]


def test_commands_requiring_responses_use_request_ids():
    sidecar_cmds = cmds(SIDECAR)
    sidecar_source = SIDECAR.read_text(encoding="utf-8")
    assert "request_id" in sidecar_source
    assert "response_to" in sidecar_source
    checked = [op for op in load()["operations"]
               if op["direction"] == "command" and op["request_id_required"]]
    assert checked
    for op in checked:
        assert transport(op) & sidecar_cmds, (
            "request_id_required command %s must be sidecar-handled" % op["name"])


def test_jobs_changed_uses_direct_job_summary_array():
    bridge_source = BRIDGE.read_text(encoding="utf-8")
    sidecar_source = SIDECAR.read_text(encoding="utf-8")
    app_source = UI_APP.read_text(encoding="utf-8")
    assert "jobs_changed" in bridge_source
    assert "Array.isArray" in bridge_source
    assert "event === 'jobs_changed'" in bridge_source
    assert re.search("jobs_changed[\\s\\S]{0,400}forEach", app_source)
    assert "jobs_changed" in sidecar_source and '"jobs"' in sidecar_source


def test_theme_settings_are_not_sent_to_sidecar():
    bridge_source = BRIDGE.read_text(encoding="utf-8")
    assert "isLocalThemeSetting" in bridge_source
    assert "'theme'" in bridge_source
    assert "localStorage" in bridge_source
    after_theme = bridge_source.split("isLocalThemeSetting(name, args))", 1)[1]
    assert "localStorage.setItem" in after_theme
    assert "api.request" in after_theme
    before_theme = bridge_source.split("isLocalThemeSetting(name, args))", 1)[0]
    assert "api.request" not in before_theme


def test_no_production_core_operation_is_silently_deferred():
    for op in load()["operations"]:
        if op["production_core"]:
            assert op["status"] != "DEFERRED"


def test_deferred_commands_do_not_cross_the_sidecar_boundary():
    bridge_source = BRIDGE.read_text(encoding="utf-8")
    for op in load()["operations"]:
        if op["direction"] == "command" and op["status"] == "DEFERRED":
            # A deferred command either stays in noopCalls (resolving to a
            # structured FEATURE_UNAVAILABLE response) or is handled by a
            # bridge-local special case that never calls api.request.
            assert (
                f'{op["name"]}: true' in bridge_source
                or f"name === '{op['name']}'" in bridge_source
            ), op["name"]

