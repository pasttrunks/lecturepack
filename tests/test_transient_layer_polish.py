"""The 2.0.9 polish pass: the transient layer, shortcut discoverability, and
the Space double-advance fix.

These are static-source assertions in the same style as the other renderer
tests: the shipped UI has no build step, so app.js/app.css/index.html ARE the
artifact, and asserting against them is asserting against what ships.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"
HTML = (UI / "index.html").read_text(encoding="utf-8")
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "app.css").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The toast becomes a control surface
# --------------------------------------------------------------------------- #

def test_toast_is_dismissible_and_an_action_buys_more_time() -> None:
    """A message is read; an action must be read, decided on, and aimed at."""
    assert "TOAST_LIFE_PLAIN = 5000" in JS
    assert "TOAST_LIFE_ACTION = 8000" in JS
    assert "_toastLife = action ? TOAST_LIFE_ACTION : TOAST_LIFE_PLAIN" in JS
    assert "t.addEventListener('click', function () { dismissToast(); })" in JS
    # The timer stops while the pill is hovered, so an Undo cannot expire out
    # from under the hand reaching for it.
    assert "t.addEventListener('mouseenter'" in JS
    assert "t.addEventListener('mouseleave'" in JS
    assert "t.setAttribute('role', 'status')" in JS


def test_toast_action_swallows_its_own_click() -> None:
    """The one real bug this control can have: an Undo that only dismisses.

    The action sits inside a pill whose own click handler dismisses. Undo that
    ALSO dismisses is fine; Undo that fires dismiss INSTEAD is not.
    """
    block = JS.split("btn.className = 'lp-toast-action'", 1)[1].split("t.appendChild(rule)", 1)[0]
    assert "e.stopPropagation()" in block
    assert "action.run()" in block


# --------------------------------------------------------------------------- #
# Undo for a mis-stamped slide
# --------------------------------------------------------------------------- #

def test_stamping_a_slide_is_undoable_and_a_run_coalesces() -> None:
    assert "function recordStamp(" in JS
    assert "function undoStampRun(" in JS
    # Both stamp buttons must record BEFORE they mutate, or undo restores the
    # state the stamp itself just wrote.
    for button in ("btn-keep", "btn-reject"):
        block = JS.split("$('%s').addEventListener('click'" % button, 1)[1].split("renderSlides();", 1)[0]
        assert "recordStamp(" in block, button
        assert block.index("recordStamp(") < block.index("s.state = "), (
            "%s records its undo state after mutating it" % button)
    # A fast sweep must not offer to undo one slide at a time: the toast is a
    # singleton, so each stamp would replace the last one's offer.
    # A change of kind CLOSES the current run onto the history stack and
    # opens a new one -- coalescing still holds, and F-11 added the stack
    # so an earlier run stays reachable.
    assert "if (stampRun.kind !== kind) {" in JS
    assert "closeStampRun();" in JS
    assert "'Undo all'" in JS
    # Ctrl+Z is the real undo and works with no toast on screen.
    assert "LP.hasStampToUndo && LP.hasStampToUndo()" in JS


def test_undo_restores_in_reverse_and_returns_the_cursor() -> None:
    """A run can stamp one slide twice; only its oldest entry holds the truth."""
    block = JS.split("function undoStampRun()", 1)[1].split("renderSlides();", 1)[0]
    assert "for (var i = run.entries.length - 1; i >= 0; i--)" in block
    # Back to where the mistake happened, not where the sweep has travelled to.
    assert "LP.state.viewingSlide = first" in block


def test_undo_reaches_past_the_most_recent_run() -> None:
    """F-11: undo was one run deep.

    Once a Ctrl+Z consumed the current run, the next answered "Nothing to undo
    yet." while a wrong reject from thirty seconds earlier stayed applied --
    and "yet" promised a later success that never came. Completed runs go on a
    stack and unwind newest-first, which is also the only SAFE order: a later
    run can re-stamp a slide an earlier one touched, so LIFO is what makes
    each run's remembered previous state the right one to restore.
    """
    assert "var stampHistory = []" in JS
    assert "stampHistory.push(stampRun)" in JS
    # The current run first, then the newest completed one.
    undo = JS.split("function undoStampRun()", 1)[1].split("renderSlides();", 1)[0]
    assert "stampRun.entries.length ? stampRun : stampHistory.pop()" in undo
    # hasStampToUndo must see the stack, or Ctrl+Z refuses work it can do.
    has = JS.split("LP.hasStampToUndo = function ()", 1)[1].split("};", 1)[0]
    assert "stampHistory.length" in has
    # The dead-end wording is gone from the message the student actually sees
    # (the phrase survives in the comment explaining why it was wrong).
    assert "toast('Nothing to undo yet.')" not in JS
    assert "toast('Nothing left to undo.')" in JS


def test_space_advances_once_not_twice() -> None:
    """DEF-043: btn-keep grew its own advance, so Space then moved two slides.

    A Space sweep kept every other slide and skipped the rest without ever
    displaying them. Invisible to any test that only checks the stamped state,
    so assert the extra click is gone from the handler itself.
    """
    block = JS.split("if (rk === ' ' || e.code === 'Space')", 1)[1].split("return;", 1)[0]
    assert "btnKeep2.click()" in block
    assert "flashViewport('keep')" in block
    assert "btn-next-slide" not in block, "Space advances twice again"


# --------------------------------------------------------------------------- #
# Shortcut discoverability
# --------------------------------------------------------------------------- #

def test_palette_rows_carry_their_shortcut_quietly() -> None:
    assert "hint: 'Ctrl+O'" in JS and "hint: 'Ctrl+E'" in JS
    assert "lp-palette-hint" in JS
    assert "data-palette-selected" in JS
    hint = CSS.split(".lp-palette-hint{", 1)[1].split("}", 1)[0]
    assert "margin-left:auto" in hint
    assert "color:var(--muted)" in hint
    # Plain mono metadata, not a key cap: caps belong to the cheat sheet, and
    # forty of them in a scrolling list out-shout every label.
    assert "border" not in hint
    # The selected row must not paint the hint blue -- its blue border already
    # carries the selection signal, and a second blue competes with it.
    selected = CSS.split("[data-palette-selected] .lp-palette-hint{", 1)[1].split("}", 1)[0]
    assert "var(--ink)" in selected
    assert "--blue" not in selected


def test_shortcut_sheet_documents_every_binding_the_app_implements() -> None:
    assert 'id="shortcuts-overlay"' in HTML
    assert 'id="shortcuts-body"' in HTML
    groups = JS.split("var SHORTCUT_GROUPS = [", 1)[1].split("\n  ];", 1)[0]
    for key in ("'Ctrl', 'K'", "'Ctrl', 'O'", "'Ctrl', 'E'", "'Ctrl', 'Z'",
                "'Space'", "'J'", "'K'", "'F'", "'?'", "'Esc'"):
        assert key in groups, "cheat sheet omits %s" % key
    # It joins the modal machinery, or Tab escapes to controls behind it.
    assert "'palette-overlay', 'shortcuts-overlay'" in JS
    assert "if (shortcutsOpen()) { closeShortcuts(); return; }" in JS


def test_shortcut_sheet_is_not_palette_chrome() -> None:
    """Palette shape would imply you can type into it -- the first thing tried."""
    panel = HTML.split('id="shortcuts-panel"', 1)[1].split("</div>", 1)[0]
    assert "<input" not in panel
    overlay = HTML.split('id="shortcuts-overlay"', 1)[1].split(">", 1)[0]
    # A real backdrop element, never a spread-shadow scrim (AD-20).
    assert "background:rgba(" in overlay
    assert "100vmax" not in overlay and "9999px" not in overlay


def test_question_mark_does_not_hijack_typing() -> None:
    block = JS.split('String(e.key || \'\') === \'?\'', 1)[1].split("}\n", 1)[0]
    assert "isContentEditable" in block
    assert "if (!askEditing)" in block


# --------------------------------------------------------------------------- #
# Copying an AI answer
# --------------------------------------------------------------------------- #

def test_study_answers_can_be_copied_and_confirm_in_place() -> None:
    assert "function copyTextQuiet(" in JS
    assert "copyControlHtml('ask')" in JS
    assert "copyControlHtml('teach')" in JS
    handler = JS.split("closest('[data-lp-copy]')", 1)[1].split("\n    });", 1)[0]
    # In-place confirmation. A bottom-centre toast for a click in the upper feed
    # sends the eye travelling to confirm what it already knows.
    assert "btn.textContent = 'Copied'" in handler
    assert "is-copied" in handler
    assert "toast('Copied'" not in handler
    # The control lives inside the bubble it copies, so its own label must not
    # be copied along with the answer.
    assert "actions.remove()" in JS


def test_copy_control_is_persistent_not_hover_revealed() -> None:
    """Hover-reveal fails touch and keyboard, and hides it in a scrolling feed."""
    css = CSS.split(".lp-copy-inline{", 1)[1].split("}", 1)[0]
    assert "opacity:0" not in css
    assert ".study-answer-actions:hover" not in CSS


def test_copy_only_appears_once_the_answer_is_final() -> None:
    """A Copy button beside a half-streamed answer copies half an answer."""
    block = JS.split("function appendStudyAskText(text, done)", 1)[1].split("\n  }", 1)[0]
    assert "if (done) {" in block
    guarded = block.split("if (done) {", 1)[1]
    assert "copyControlHtml('ask')" in guarded
    assert "studyV2.askAnswer &&" in guarded


# --------------------------------------------------------------------------- #
# One app: Study borrows Review's stamp gesture
# --------------------------------------------------------------------------- #

def test_study_grading_reuses_reviews_stamp_gesture_at_a_narrower_box() -> None:
    assert "function flashStamp(" in JS
    assert "flashStamp($('study-flashcards-root')" in JS
    assert "flashStamp($('study-quiz-root')" in JS
    # Review's colours, unchanged: a second green/red pair for correctness is a
    # distinction nobody would perceive as intentional.
    assert ".lp-stamp-flash-keep{animation:lpEdgeFlashGreen" in CSS
    assert ".lp-stamp-flash-reject{animation:lpEdgeFlashRed" in CSS
    # Scoped, not the full-viewport flash: Study's screen also holds the scope
    # bar, progress and concept list, and flashing all of it would claim the
    # whole screen was graded.
    assert "flashViewport($('study" not in JS


def test_flashcard_flash_runs_after_the_render_that_replaces_the_card() -> None:
    block = JS.split("function recordFlashReview(correct)", 1)[1].split("\n  }", 1)[0]
    assert block.index("renderStudyFlashcards();") < block.index("flashStamp("), (
        "the flash targets a container the render has already replaced")


# --------------------------------------------------------------------------- #
# Standing constraints
# --------------------------------------------------------------------------- #

def test_new_motion_has_a_reduced_motion_branch_that_keeps_the_information() -> None:
    """Colour feedback is information; movement is decoration. Keep the first.

    Same trap as .lp-viewport-flash: the ring lives in the keyframes, so
    `animation:none` alone would leave a graded answer with no feedback at all.
    """
    reduced = CSS.split("@media (prefers-reduced-motion: reduce)")[-1]
    assert ".lp-stamp-flash-keep{animation:none;box-shadow:inset 0 0 0 4px var(--green)}" in reduced
    assert ".lp-stamp-flash-reject{animation:none;box-shadow:inset 0 0 0 4px var(--red)}" in reduced
    assert ".lp-copy-inline{transition:none}" in reduced


def test_new_css_obeys_the_ad20_ban() -> None:
    """AD-20: no spread scrims, no geometry transitions, no will-change.

    Removed on purpose after beta.10 flickered on a clean-install machine. It
    will not reproduce on a dev box, so the ban is enforced by test.
    """
    section = CSS.split("3.9  Transient layer", 1)[1]
    for banned in ("100vmax", "9999px", "will-change", "drop-shadow"):
        assert banned not in section, "AD-20 violation: %s" % banned
    for geometry in ("transition:left", "transition:top", "transition:width", "transition:height"):
        assert geometry not in section


def test_the_cheat_sheet_is_reachable_without_knowing_the_shortcut() -> None:
    """A shortcut that only announces itself via a shortcut announces itself
    to nobody. There must be a surface a mouse can find.
    """
    # A persistent header control, always visible, with the key in its tooltip
    # so the button also teaches the shortcut.
    assert 'id="btn-shortcuts"' in HTML
    header_btn = HTML.split('id="btn-shortcuts"', 1)[1].split(">", 1)[0]
    assert 'title="Keyboard shortcuts (?)"' in header_btn
    assert 'aria-label="Keyboard shortcuts"' in header_btn
    assert "$('btn-shortcuts')" in JS
    # And a palette row, for the person who reaches for Ctrl+K to hunt features.
    assert "{ label: 'Keyboard shortcuts', hint: '?'" in JS


def test_the_stamp_flash_leaves_no_layout_behind_it() -> None:
    """A 140ms tint must not permanently change its container.

    flashStamp only removes the TONE class, so anything else it adds outlives
    the flash. A `position` on a Study root would silently become the
    containing block for every absolutely positioned descendant after the
    student's first graded card.
    """
    assert ".lp-stamp-flash{position:relative}" not in CSS
    block = JS.split("function flashStamp(el, tone)", 1)[1].split("\n  }", 1)[0]
    assert "el.classList.add('lp-stamp-flash-' + tone)" in block
    assert "'lp-stamp-flash'," not in block, "adds a class the timer never removes"
