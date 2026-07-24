"""Unit tests for app/desktop/win_integration.py — keep-awake, taskbar state
mapping, and notification policy (focus-gating, dedup, routing). Pure: uses fake
seams and an injected clock, so no real OS/Qt calls occur."""

from app.desktop import win_integration as wi


class FakePower:
    """Faithful double: idempotent like the real PowerRequester (only records a
    call when the awake state actually changes)."""
    def __init__(self):
        self.calls = []
        self._active = False
    def set_awake(self, on):
        if on == self._active:
            return
        self.calls.append(on)
        self._active = on
    @property
    def active(self):
        return self._active


class FakeTaskbar:
    def __init__(self):
        self.states = []
        self.state = wi.TB_NONE
    def set_state(self, state, progress=0):
        self.state = state
        self.states.append((state, progress))


class FakeNotifier:
    def __init__(self, available=True):
        self._available = available
        self.shown = []
    def available(self):
        return self._available
    def show(self, note):
        if not self._available:
            return False
        self.shown.append(note)
        return True


class Clock:
    def __init__(self):
        self.t = 0.0
    def __call__(self):
        return self.t


def _wi(**kw):
    power = kw.pop("power", FakePower())
    taskbar = kw.pop("taskbar", FakeTaskbar())
    notifier = kw.pop("notifier", FakeNotifier())
    clock = kw.pop("clock", Clock())
    return wi.WindowsIntegration(power=power, taskbar=taskbar, notifier=notifier,
                                 clock=clock, **kw), power, taskbar, notifier, clock


# --- keep-awake ------------------------------------------------------------ #
def test_keep_awake_acquire_on_start_release_on_terminal():
    w, power, _, _, _ = _wi()
    w.on_job_started()
    assert power.active is True
    w.on_completed("j1", "Lec")
    assert power.active is False


def test_keep_awake_released_on_each_terminal_path():
    for hook in ("on_failed", "on_cancelled", "on_paused", "on_shutdown"):
        w, power, _, _, _ = _wi()
        w.on_job_started()
        assert power.active is True
        getattr(w, hook)("j1") if hook in ("on_failed",) else getattr(w, hook)()
        assert power.active is False, hook


def test_keep_awake_idempotent_no_duplicate_calls():
    w, power, _, _, _ = _wi()
    w.on_job_started()
    w.on_progress(50)  # must not re-acquire
    w.on_completed("j", "t")
    w.on_idle()        # already released; must not re-toggle
    assert power.calls == [True, False]


# --- taskbar mapping ------------------------------------------------------- #
def test_taskbar_state_mapping():
    w, _, tb, _, _ = _wi()
    w.on_job_started();           assert tb.state == wi.TB_NORMAL
    w.on_progress(42);            assert tb.states[-1] == (wi.TB_NORMAL, 42)
    w.on_pause_requested();       assert tb.state == wi.TB_PAUSED
    w.on_paused();                assert tb.state == wi.TB_PAUSED
    w.on_failed("j", "boom");     assert tb.state == wi.TB_ERROR
    w.on_completed("j", "t");     assert tb.state == wi.TB_NONE
    w.on_cancelled();             assert tb.state == wi.TB_NONE


def test_progress_clamped():
    w, _, tb, _, _ = _wi()
    w.on_progress(250)
    assert tb.states[-1] == (wi.TB_NORMAL, 100)
    w.on_progress(-5)
    assert tb.states[-1] == (wi.TB_NORMAL, 0)


# --- notification policy --------------------------------------------------- #
def test_notify_suppressed_when_focused_and_only_unfocused():
    w, _, _, notifier, _ = _wi()
    w.set_focused(True)  # default only_when_unfocused=True
    assert w.on_completed("j", "t") is False
    assert notifier.shown == []


def test_notify_fires_when_unfocused():
    w, _, _, notifier, _ = _wi()
    w.set_focused(False)
    assert w.on_completed("j1", "Lecture 1") is True
    assert len(notifier.shown) == 1
    assert notifier.shown[0].route == "job:j1"


def test_notify_respects_pref_off():
    w, _, _, notifier, _ = _wi(prefs={"notify_failed": False})
    w.set_focused(False)
    assert w.on_failed("j", "err") is False
    assert notifier.shown == []


def test_smart_study_off_by_default():
    w, _, _, notifier, _ = _wi()
    w.set_focused(False)
    assert w.on_smart_study_done("j") is False
    w.set_prefs({"notify_smart_study": True})
    assert w.on_smart_study_done("j") is True


def test_update_notification_ignores_focus():
    w, _, _, notifier, _ = _wi()
    w.set_focused(True)  # focused, but update should still fire
    assert w.on_update_available("0.9.0-beta.3") is True
    assert notifier.shown[-1].route == "update"


def test_duplicate_suppression_within_window():
    clock = Clock()
    w, _, _, notifier, _ = _wi(clock=clock, dedup_window=3.0)
    w.set_focused(False)
    assert w.on_completed("j", "t") is True
    clock.t = 1.0
    assert w.on_completed("j", "t") is False   # dup within 3s
    clock.t = 4.0
    assert w.on_completed("j", "t") is True     # window elapsed
    assert len(notifier.shown) == 2


def test_distinct_routes_not_deduped():
    w, _, _, notifier, _ = _wi()
    w.set_focused(False)
    assert w.on_completed("j1", "a") is True
    assert w.on_completed("j2", "b") is True
    assert len(notifier.shown) == 2


def test_click_routing_returns_last_route():
    w, _, _, _, _ = _wi()
    w.set_focused(False)
    w.on_completed("jX", "t")
    assert w.on_notification_clicked() == "job:jX"


def test_notifier_unavailable_degrades():
    w, _, _, _, _ = _wi(notifier=FakeNotifier(available=False))
    w.set_focused(False)
    assert w.on_completed("j", "t") is False
    assert w.shown_count == 0


def test_test_notification_bypasses_prefs_and_focus():
    w, _, _, notifier, _ = _wi(prefs={"notify_complete": False})
    w.set_focused(True)
    assert w.test_notification() is True
    assert len(notifier.shown) == 1
