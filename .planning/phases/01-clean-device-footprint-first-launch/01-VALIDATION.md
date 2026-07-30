---
phase: 1
slug: clean-device-footprint-first-launch
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-30
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded by `/gsd-plan-phase 1` from `01-RESEARCH.md` § Validation Architecture.
> The Per-Task Verification Map is filled by the planner / `/gsd-validate-phase`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` (repo root); `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` for headless Qt (BUG-10) |
| **Quick run command** | `pytest tests/test_beta3_packaging.py tests/test_runtime_packaged_smoke.py -x` |
| **Full suite command** | `pytest` (confirm invocation directory during planning) |
| **Estimated runtime** | quick subset ~seconds; full suite baseline ~677–684 tests per BUG_LIST.md — re-confirm current count |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_beta3_packaging.py tests/test_runtime_packaged_smoke.py -x`, plus the focused test file for the task just completed
- **After every plan wave:** Run `pytest` (full suite must be green)
- **Before `/gsd-verify-work`:** Full suite green **AND** all four physical/manual evidence artifacts captured (measured size table, measured cold + warm launch, two-process single-instance proof, packaged clean-profile launch showing the icon *and* rendered WebEngine content)
- **Max feedback latency:** quick subset must stay under 60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| *(filled by planner)* | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Requirement IDs:** no `REQUIREMENTS.md` IDs are mapped to this phase. The ROADMAP Success Criteria act as the effective requirement IDs (SC-1 … SC-6).

| Req | Behavior | Test type | Coverage today |
|---|---|---|---|
| SC-1 size measured | Fresh `Setup.exe` produced; size + expansion measured; contributors listed | scripted measurement, not a pytest assertion | ❌ nothing in `tests/` measures artifact size |
| SC-2 tree assertions | One `ggml-base.en.bin`; `translations/`, `qml/`, Quick/Quick3D DLLs, `Qt6Pdf.dll` absent; packaged smoke still passes | unit + integration | 🟡 `check_clean_state` (`build.py:316-360`) + `test_runtime_packaged_smoke.py` exist; new assertions needed |
| SC-2 render proof | Packaged GUI still paints after the Qt cuts | manual / CDP-driven | ❌ **Wave 0 gap** — no existing test launches the real window |
| SC-3 launch timing | Window visible in seconds; itemized honest progress | manual timing + driven-app assertion on progress text | ❌ Wave 0 gap |
| SC-4 single instance | Second launch raises the first window, no second process | two-process integration | ❌ Wave 0 gap |
| SC-5 first-run checklist | Ready / Needs Attention renders before the demo offer; acknowledgement persists | JS reducer unit tests + `ConfigManager` persistence test | 🟡 `RuntimeSetupGateModel` is already test-friendly; new states + new persistence field untested |
| SC-6 icon | Icon in title bar and Windows taskbar for the installed build | manual / physical | ❌ inherently physical |

---

## Wave 0 Requirements

- [ ] Size-measurement step — build `Setup.exe`, extract to scratch, measure both, diff top contributors (nothing in `tests/` does this)
- [ ] Extended `check_clean_state` / `tests/test_beta3_packaging.py` assertions — absent `translations/`, `qml/`, `Qt6Qml.dll`, `Qt6Quick.dll`, `Qt6Quick3DRuntimeRender.dll`, `Qt6Pdf.dll`; exactly one `ggml-base.en.bin` in the whole tree
- [ ] **Packaged-GUI-launch verification (highest-value gap)** — screenshot or CDP-driven proof that WebEngine still renders after the Qt cuts. No existing test launches the real window, so the offline-processing smoke passing does **not** prove the UI survives
- [ ] `RuntimeSetupGateModel` reducer tests for the new first-run-checklist state/transition
- [ ] `ConfigManager` test for the "setup acknowledged" field living alongside `runtime_health` (D-16)
- [ ] Two-process single-instance integration test, or a documented manual procedure if CI cannot spawn real GUI processes
- [ ] Test proving `_bundled_demo_model_path()`'s fallback reaches the canonical copy once the `_internal/models/` duplicate is removed (D-05: the resolution logic is the deliverable)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Measured installer + installed size | SC-1 | Requires a full local `packaging/build.py` run and disk measurement of one artifact | Build once; record `Setup.exe` bytes, extracted-tree bytes, and top contributors from the *same* artifact. Do not average, do not reuse the stale 1.9 GB figure |
| Cold and warm launch times on a clean profile | SC-3 | Cold path only exists on a fresh profile; timing needs a real clock on real hardware | Fresh profile → time to first visible feedback and to ready. Then relaunch and time the warm path. Record both separately (D-07) |
| Second launch raises the existing window | SC-4 | Needs two real GUI processes and Windows focus behavior | Launch installed build, then launch again. Assert one process, existing window raised and focused |
| Packaged clean-profile launch: icon visible + WebEngine renders | SC-2, SC-6 | Windows shell icon association and Chromium renderer startup cannot be asserted headlessly | Install on a clean profile, launch, screenshot title bar + taskbar, confirm the UI paints real content |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s for the quick subset
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
