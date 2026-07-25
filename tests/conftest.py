"""Shared pytest configuration.

**Qt must never open a real window during the test suite.**

Several tests construct real Qt widgets and call ``.show()``
(``test_ui_v11.py``, ``test_ui_phase2.py``, ``test_stability_phase.py``), and
``pytest-qt``'s ``qapp`` fixture builds a real ``QApplication``. With no
platform plugin pinned, Qt picks the native one — on Windows that means actual
windows pop up and vanish during a run. Reported by the user on 2026-07-25 as
"the app flashes away really quickly" while tests run.

That is not just cosmetic: a native window steals focus mid-run, it makes the
suite unusable while working, and it makes a headless CI run behave differently
from a local one. ``offscreen`` renders into a buffer instead, so widget
geometry, layout and painting still work — which is all these tests assert on.

This MUST be set before Qt is imported, so it lives at module import time in
conftest.py rather than in a fixture.
"""

import os

# setdefault, not assignment: an explicit QT_QPA_PLATFORM from the environment
# (e.g. someone debugging a widget visually, or a CI image pinning a plugin)
# still wins.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
