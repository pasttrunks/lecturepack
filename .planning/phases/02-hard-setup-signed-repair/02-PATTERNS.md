# Phase 02: Hard Setup & Signed Repair - Pattern Map

**Mapped:** 2026-07-28  
**Files analyzed:** 15 planned source/test files  
**Analogs found:** 14 / 15

## File Classification

| New/Modified File | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|
| `lecturepack/infrastructure/release_trust.py` | infrastructure/service utility | request-response, transform | `app/desktop/update_service.py` | partial (pure validation only) |
| `lecturepack/infrastructure/runtime_generation.py` | infrastructure | file-I/O, transactional | `app/desktop/updater.py` | partial (staging only) |
| `lecturepack/services/runtime_repair.py` | service | event-driven, file-I/O | `lecturepack/services/runtime_bootstrap.py` | role-match |
| `app/desktop/repair_worker.py` | worker | event-driven, streaming | `app/desktop/updater.py` | role-match |
| `app/desktop/bridge.py` | bridge/controller | request-response, event-driven | itself (Phase 1 admission boundary) | exact |
| `app/ui/bridge.js` | browser bridge | pub-sub, request-response | itself | exact |
| `app/ui/app.js` | component/controller | event-driven reducer | overlay/focus code in itself | role-match |
| `app/ui/index.html` | UI component/template | event-driven | existing onboarding/What's New overlays | role-match |
| `app/requirements.txt` | config | batch | existing pin file | exact |
| `requirements.txt` | config | batch | `app/requirements.txt` | role-match |
| `LecturePack.spec` / packaging hook used by frozen test | config | batch | `app/packaging/build.py` inventory contract | partial |
| `tests/test_release_trust.py` | test | transform | `tests/test_update_service.py` | role-match |
| `tests/test_runtime_generation.py` | test | file-I/O/fault injection | `tests/test_cuda_pack.py` | partial |
| `tests/test_runtime_repair.py` | test | event-driven/file-I/O | `tests/test_runtime_bootstrap.py` | role-match |
| `tests/test_setup_gate_repair.py` | integration/UI test | request-response/event-driven | `tests/test_adapter_startup.py` | exact |

## Pattern Assignments

### `lecturepack/infrastructure/release_trust.py` (infrastructure utility, transform)

**Analog:** `app/desktop/update_service.py` (lines 1-15, 117-160).

Keep trust policy Qt-free and deterministic, following the updater's split between pure policy and QThread/network orchestration:

```python
# app/desktop/update_service.py:1-7
"""Pure (Qt-free, network-free) update logic..."""

# app/desktop/update_service.py:123-133
def _url_ok(url: str, extra_hosts=None) -> bool:
    u = urlparse(url or "")
    ...
```

Use the same module boundary, but **do not reuse** `TRUSTED_ASSET_HOSTS`, `extra_hosts`, release-feed selection, or installer/checksum asset flexibility. Production repair must construct the AD-19 exact-version fixed GitHub release paths, verify the 64-byte detached Ed25519 signature against original manifest bytes before parsing, then apply duplicate-key/canonical-schema/inventory checks. Test transports are constructor-injected, never environment-enabled production overrides.

### `lecturepack/infrastructure/runtime_generation.py` (infrastructure, transactional file-I/O)

**Analog:** `_DownloadWorker.run` in `app/desktop/updater.py` (lines 130-168).

```python
partial = os.path.join(updates, self._dest_name + ".partial")
...
if not us.verify_file(partial, expected):
    raise ValueError("checksum mismatch — download rejected")
os.replace(partial, final)
```

Copy only the transaction shape: private staging name, verify before publish, `os.replace` for same-directory atomic publication, and cleanup of incomplete private output. For repair, publication is an atomic `active.json` pointer/journal replacement after a *complete* generation is extracted and fully admitted. Do not reuse updater cache semantics, direct executable handoff, or any writable bundle target.

Use `lecturepack/infrastructure/runtime_inventory.py:34-56` as the canonical inventory/containment seam:

```python
def resolve_inventory(root: Path, entries: Iterable[str] | None = None) -> dict[str, Path]:
    ...
    resolved = candidate.resolve()
    resolved.relative_to(base)
```

Extend through one active-generation resolver so bootstrap, diagnostics, packaged tests, and repair all resolve the same root. ZIP extraction must pre-inspect an exact forward-slash allow-list; never use `extractall` or `cuda_pack.extract_pack` (the latter intentionally flattens names).

### `lecturepack/services/runtime_repair.py` (service, event-driven transactional file-I/O)

**Analog:** `lecturepack/services/runtime_bootstrap.py` and `RuntimeBootstrapService.assess()` as consumed at `app/desktop/bridge.py:109-124`.

```python
self.runtime_health_result = RuntimeBootstrapService(self._runtime_config).assess()
...
if self.runtime_health_result.state == "HEALTHY":
    self._adapter = make_adapter(...)
    self._updater = Updater(self)
```

Model repair as a pure, injected coordinator: acquire → authenticate → stage → hash/inventory validate → activate safe boundary → `assess(trigger="repair")` → admitted/rollback. It returns structured progress/error/evidence; it must not import Qt or touch widgets. Cancellation is checked between units, but pointer activation is indivisible. The complete bootstrap assessment is the success proof, not presence/size inspection.

### `app/desktop/repair_worker.py` (worker, event-driven streaming)

**Analog:** `app/desktop/updater.py:95-168`.

```python
class _DownloadWorker(QThread):
    progress = Signal(float, int, int)
    done = Signal(str)
    failed = Signal(str)
    ...
    def cancel(self):
        self._cancel = True
```

Use a named `QThread` worker with explicit signals and a cancellation flag/event. Emit small JSON-safe repair events (`operation_id`, `started/progress/retrying/cancel_requested/cancelled/failed/activated/admitted`), and ensure one terminal event. Do not inherit updater's `__cancelled__` string sentinel as the repair protocol or its direct-to-live installation behavior.

### `app/desktop/bridge.py` (bridge/controller, request-response + event-driven)

**Analog:** existing Phase 1 admission guard at lines 29-180.

```python
def __getattribute__(self, name):
    guarded = object.__getattribute__(self, "_ADMISSION_GUARDED_OPERATIONS")
    if name in guarded:
        state = object.__getattribute__(self, "__dict__").get("runtime_health_result")
        if state is not None and state.state != "HEALTHY":
            return lambda *args, **kwargs: self._guard_admitted_operation(name)
    return super().__getattribute__(name)

@Slot(result=str)
def get_bootstrap(self) -> str:
    snapshot = self._runtime_diagnostics.runtime_health_snapshot()
    return json.dumps({"runtime_health_state": snapshot["admission_state"],
                       "setup_required": snapshot if snapshot["admission_state"] == "SETUP_REQUIRED" else None})
```

Add only narrow repair slots/signals that are usable while `SETUP_REQUIRED`; keep every normal bridge operation guarded. On matching post-repair `admitted`, rerun the canonical assessment and construct adapter/updater only then. Preserve JSON strings across QWebChannel, as `_setup_required_payload()` already does.

### `app/ui/bridge.js` (browser bridge, pub-sub)

**Analog:** `app/ui/bridge.js:17-49`.

```javascript
var SIGNALS = [ /* backend signal names */ ];
SIGNALS.forEach(function (name) {
  if (backend[name] && backend[name].connect) {
    backend[name].connect(function () { fire.apply(null, [name].concat(Array.prototype.slice.call(arguments))); });
  }
});
```

Append the dedicated repair signal to this synchronized list; invoke narrow slots through `lpBridge.call`. Do not tunnel repair through generic diagnostics/status signals.

### `app/ui/app.js` (client controller, event-driven reducer)

**Analogs:** bootstrap at lines 3122-3136 and modal focus helpers at lines 1793-1832.

```javascript
lpBridge.call('get_bootstrap').then(function (json) {
  var b = JSON.parse(json);
  if (b.theme) setTheme(b.theme);
  if (b.version) { LP.data.version = b.version; $('app-version').textContent = b.version; }
});

function topOverlay() { /* ranks open overlays by z-index */ }
function focusFirst(scope) { /* focuses first visible FOCUSABLE */ }
function trapFocus(scope, e) { /* Tab/Shift+Tab containment */ }
```

Consume `runtime_health_state` / `setup_required` before normal bootstrap activity. Add one reducer state (`gate | diagnostics | confirm | repairing | offline | failed | ready`) plus active operation id; reject stale/duplicate terminal events. Put the gate first/highest in `topOverlay()`. Its keyboard handler must ignore Escape and suppress all background shortcuts/scroll while gate is active, unlike the normal overlay escape branch at `app/ui/app.js:2714-2725`.

For backend strings, reuse the existing escaping convention (`esc(...)` used in `app/ui/app.js:3114-3118`) or text nodes; never interpolate diagnostics/URLs/reasons unescaped with `innerHTML`.

### `app/ui/index.html` (UI template, event-driven)

**Analog:** `#whatsnew-overlay` at lines 592-628, with structural tokens from `#onb-overlay` lines 550-589.

```html
<div ... class="lp-scrim" style="position:fixed;inset:0;z-index:55;...padding:32px">
  <div class="lp-pop" style="width:560px;max-width:100%;background:var(--panel);
       border:2px solid var(--border);border-radius:18px;box-shadow:var(--shadow-hi);overflow:hidden">
```

Use a higher z-index, no scrim dismissal/X button, `.lp-hit` plus `.lp-press`/`.lp-press-sm` on every action, and existing dark scrim/panel/border/radius/shadow. Progress uses the compositor pattern already present in `index.html:461`:

```html
<div class="lp-fill" style="width:100%;height:100%;background:var(--orange);transform:scaleX(0)"></div>
```

Do not copy `#whatsnew-progress-bar`'s animated `width` (line 617) or the updater's dismissible actions. Gate needs its own semantic progressbar/live regions, technical-details disclosure, and inert normal-app management.

### Tests (unit, filesystem transaction, bridge/UI integration)

**Admission/bridge analog:** `tests/test_adapter_startup.py:186-258`. It monkeypatches `RuntimeBootstrapService`, creates a real `Backend`, invokes every guarded slot, and asserts canonical setup JSON. Follow this to prove repair commands are the only setup-available surface and collaborators appear only after `HEALTHY`.

**Pure-policy analog:** `tests/test_update_service.py` and `app/desktop/update_service.py:1-7`. Keep release-trust tests Qt/network-free and use immutable byte fixtures: known-good signature/vector; one-byte alteration; malformed key/signature; duplicate/unknown JSON fields; wrong schema/version; inventory/hash failures.

**Fault-injection analog:** `tests/test_cuda_pack.py:1-33, 98-156` uses `tmp_path`, local ZIP fixtures, monkeypatches the downloader/target, and asserts no path escape. For repair, strengthen it: fake injected transport/filesystem points at `tmp_path`; parameterize download, write, extract, hash, admission, and pointer-replace failures; assert prior `active.json` and generation bytes are unchanged after every failure/cancel.

**QThread/network analog:** `tests/test_update_integration.py` creates a local `ThreadingHTTPServer`, temp `LOCALAPPDATA`, signal-capturing backend, and `qtbot.waitSignal`. Reuse the lifecycle/signal observation shape, but do not use its environment feed/host override as production repair behavior.

**Frozen evidence analog:** `tests/test_runtime_packaged_smoke.py:66-101` requires a clean onedir fixture, copies it into a space/non-ASCII path, runs `RuntimeBootstrapService(..., runtime_root=copied).assess()`, and validates smoke evidence fields. Extend this through the active-generation resolver and compiled trust verifier; keep fixture absence an explicit failure.

## Shared Patterns

### Canonical admission and diagnostics

**Sources:** `app/desktop/bridge.py:109-180`, `lecturepack/services/runtime_bootstrap.py`, `lecturepack/services/runtime_diagnostics.py`.

The bridge owns construction ordering. Reuse canonical component identities, admission snapshot, and sanitized diagnostics; do not create a parallel repair health model.

### Worker lifecycle and cancellation

**Source:** `app/desktop/updater.py:95-168, 309-348`.

Use explicit worker ownership, signals connected before `start()`, cancellation requested by method/event, and cleanup before terminal failure. Repair adds safe activation boundaries and operation IDs.

### UI motion, focus, and progress

**Sources:** `app/ui/app.js:188-255, 1793-1832, 2710-2726`; `app/ui/index.html:550-628`.

Reuse `LP.motion`, `LP.motion.close`, `.lp-scrim`, `.lp-pop`, `FOCUSABLE`, `focusFirst`, `trapFocus`, `topOverlay`, `.lp-hit`, `.lp-press`, and `.lp-fill`. Gate-specific keyboard behavior overrides dismissal/shortcuts while visible; reduced motion uses `LP.motion.reduced()`.

### Packaging inventory

**Source:** `tests/test_runtime_packaged_smoke.py:13-101` and `app/packaging/build.py`.

The frozen self-test must derive membership from the canonical runtime inventory and test a real onedir payload. The repair release layout must be checked against that same inventory before activation.

## No Analog Found

| File/capability | Reason / planner direction |
|---|---|
| Exact-byte Ed25519 manifest verifier | No signed release verifier exists; implement from AD-19/RESEARCH with pure injected seams. |
| Complete generation pointer+journal rollback | No existing generation transaction; updater only demonstrates partial-file verification and `os.replace`. |
| Setup-gate reducer / stale operation suppression | Existing overlays have focus/motion patterns, but no non-dismissible repair state machine. |

## Metadata

**Analog search scope:** `app/desktop`, `app/ui`, `lecturepack/services`, `lecturepack/infrastructure`, `app/packaging`, `tests`  
**Files scanned:** 18 primary analogs/tests plus Phase 2 context, research, and UI contract  
**Pattern extraction date:** 2026-07-28
