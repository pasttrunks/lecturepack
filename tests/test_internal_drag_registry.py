"""LPDrag -- the one internal drag system.

Internal drag used to be a single hardcoded gesture (lecture card -> Process)
bound directly to elements. It read to users as "internal drag is broken" for
two reasons this suite pins down permanently:

  1. Releasing anywhere else did nothing AND SAID NOTHING, because the
     window-level dragover cancelled the event before checking whether the drag
     was internal -- so the whole window advertised a drop that only one element
     could act on.
  2. Handlers bound per element cannot survive a rerender, and both the queue
     and the library rebuild via innerHTML on every poll.

The rules encoded here are the ones that stop it regressing to either.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app" / "ui"


def read_ui(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


APP = read_ui("app.js")
CSS = read_ui("app.css")


def module_source() -> str:
    return APP.split("var LPDrag = (function () {", 1)[1].split(
        "\n  /* Dropping lectures on Process", 1
    )[0]


def function_source(name: str, source: str | None = None) -> str:
    src = source if source is not None else APP
    body = src.split("function %s(" % name, 1)[1]
    return body.split("\n    }", 1)[0]


# --------------------------------------------------- reorder maths, executed

def run_node(body: str) -> subprocess.CompletedProcess:
    """reorder_queue takes a FINAL absolute index, so a row moving forward has
    to account for its own removal shifting the destination down by one. That
    is an off-by-one waiting to happen, so it is executed rather than eyeballed.
    """
    program = "function reorderIndex(" + function_source("reorderIndex", module_source()) + "\n}\n" + body
    return subprocess.run(["node", "-e", program], capture_output=True, text=True)


def test_reorder_index_truth_table_executes_correctly() -> None:
    # (from, insert-before) -> expected final index
    cases = [
        # A row dropped immediately before or after itself must be a NO-OP,
        # i.e. resolve back to its own index. Both adjacent slots count.
        (0, 0, 0),
        (0, 1, 0),
        (3, 3, 3),
        (3, 4, 3),
        # Real moves.
        (0, 2, 1),   # A -> after B
        (0, 4, 3),   # A -> the end of a 4-row queue
        (3, 0, 0),   # D -> the front
        (2, 1, 1),   # C -> before B
    ]
    body = "\n".join(
        "if (reorderIndex(%d, %d) !== %d) { console.error('FAIL %d,%d got ' + reorderIndex(%d, %d)); process.exit(1); }"
        % (f, b, want, f, b, f, b)
        for f, b, want in cases
    )
    result = run_node(body + "\nconsole.log('OK');")
    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK" in result.stdout


def test_a_no_op_reorder_is_refused_with_a_reason_not_silently() -> None:
    """Releasing a row onto its own position used to look identical to a broken
    drag: nothing moves, nothing is said. It must state that it already sits
    there."""
    over = function_source("updateAt", module_source())
    assert "finalIndex === active.from" in over
    assert "is already in this position" in over
    assert "'bad'" in over
    # Caught live in a real browser when this was native: the branch armed the
    # drop and THEN bailed out, so the cursor said "droppable" over a position
    # that would do nothing -- accepted-and-ignored, the precise silent failure
    # this system exists to remove. The refusal must still come first, and now
    # also has to mark the carried card refused, since there is no OS cursor.
    reorder = over.split("if (desc.drop === 'queue-reorder') {", 1)[1]
    refusal = reorder.index("is already in this position")
    arming = reorder.index("armed = { desc: desc")
    assert refusal < arming, "a no-op reorder is armed before it is refused"
    assert "paintProxy('bad')" in reorder


def test_reorder_hysteresis_survives_a_refused_no_op() -> None:
    """The side (before/after) is remembered outside `armed`, because a no-op
    clears `armed` -- if the side lived there, hovering a dead zone right after
    a refusal would silently flip the insertion point."""
    module = module_source()
    assert "var lastAfter" in module
    over = function_source("updateAt", module)
    assert "lastAfter" in over
    assert "armed && armed.after" not in over


# ------------------------------------------------------- the ordering bug

def test_window_handlers_bail_out_before_cancelling_an_internal_drag() -> None:
    """THE bug. preventDefault() on window is what lets an external video be
    dropped on any screen -- but if it runs before the internal-drag check, an
    internal drag gets a window-wide "drop here" cursor that no handler will
    honour. The guard must come FIRST in both handlers."""
    for anchor in ("window.addEventListener('dragover'", "window.addEventListener('drop'"):
        # The last occurrence is the file-import pair; the earlier ones are the
        # capture-phase auto-scroll wiring.
        body = APP[APP.rindex(anchor):][:1400]
        guard = body.index("LPDrag.dragging()")
        cancel = body.index("e.preventDefault()")
        assert guard < cancel, "%s cancels the event before checking for an internal drag" % anchor


def test_the_dropzone_does_not_stop_internal_drags_from_reaching_the_registry() -> None:
    """The dropzone's guards used to stopPropagation(), which was aimed at the
    window handler but also stopped the event reaching LPDrag's delegated
    listeners on document -- so a lecture dragged across the dropzone went dark:
    no paint, no strip, no explanation."""
    for anchor in ("dz.addEventListener('dragover'", "dz.addEventListener('drop'"):
        body = APP[APP.index(anchor):][:520]
        assert "stopPropagation" not in body, "%s swallows internal drags" % anchor
        assert "LPDrag.dragging()" in body


# --------------------------------------------------------------- delegation

def test_every_drag_listener_is_delegated_from_document() -> None:
    """Per-element listeners cannot survive renderJobs()/renderQueue(), both of
    which rebuild their container with innerHTML."""
    wire = function_source("wire", module_source())
    # The lift is pointer-driven; only the native-drag SUPPRESSOR remains.
    assert "document.addEventListener('pointerdown'" in wire
    for event in ("pointermove", "pointerup", "pointercancel"):
        assert "window.addEventListener('%s'" % event in wire, event
    assert "document.addEventListener('dragstart'" in wire and "e.preventDefault()" in wire,         "native drag must be suppressed for internal sources"
    # Escape and a lost pointer must both be able to end a drag.
    assert "onPointerCancel" in wire and "keydown" in wire
    # No surface may re-grow its own internal-drag wiring.
    for dead in (
        "$('jobs-grid').addEventListener('dragstart'",
        "$('jobs-grid').addEventListener('dragend'",
        "processQueueTarget.addEventListener(",
    ):
        assert dead not in APP, "%s came back" % dead


def test_targets_are_declared_in_markup_not_wired_by_hand() -> None:
    # Sources
    assert 'data-lp-drag="lecture"' in APP
    assert 'data-lp-drag="queue"' in APP
    # Targets: Process, both subject surfaces, and queue reorder.
    assert "el.dataset.lpDrop = 'process'" in APP
    assert APP.count('data-lp-drop="group"') >= 2, "both the Library header and the Home subject card"
    assert 'data-lp-drop="queue-reorder"' in APP


def test_the_registry_names_a_refusal_reason_for_every_target() -> None:
    """A target that refuses a drag must be able to say why, in the user's
    words. A registry entry without a reason is how silent failure returns."""
    block = module_source().split("var TARGETS = [", 1)[1].split("\n    ];", 1)[0]
    entries = re.findall(r"\{ drop: '([a-z-]+)'", block)
    assert set(entries) == {"process", "group", "queue-reorder"}
    assert block.count("reason:") == len(entries)
    assert block.count("kinds:") == len(entries)


# -------------------------------------------------------- silent failure

def test_a_drag_that_lands_nowhere_explains_itself_and_returns_home() -> None:
    """The anti-silent-failure rule, now with a physical form: the reason stays
    on screen long enough to read AND the card visibly travels back to where it
    came from, so the gesture is seen not to have taken."""
    end = function_source("abandon", module_source())
    assert "was not moved" in end
    assert "hideStrip(1400)" in end, "the reason must stay on screen long enough to read"
    assert "snapProxy(sourceRect" in end, "the card must return to its origin"
    # every ending routes through the one teardown
    assert "finish();" in end


def test_hovering_a_wrong_kind_target_says_why_and_marks_the_carried_card() -> None:
    """With a custom drag layer there is no OS cursor to paint no-drop, so the
    refusal has to be visible on the card being carried -- not only in the strip
    at the bottom of the window, which the user may not be looking at."""
    over = function_source("updateAt", module_source())
    refusal = over.split("if (!desc.kinds[active.kind]) {", 1)[1].split("return;", 1)[0]
    assert "lp-drop-bad" in refusal
    assert "paintProxy('bad')" in refusal
    assert "desc.reason" in refusal
    # the proxy must have a refused look at all
    assert ".lp-drag-proxy.is-bad" in CSS


def test_the_status_strip_is_the_single_aria_live_channel() -> None:
    """The visual string and the screen-reader string must be the same object,
    or the two channels drift apart."""
    strip = function_source("strip", module_source())
    assert "role', 'status'" in strip
    assert "aria-live', 'polite'" in strip


# ------------------------------------------------------------- affordance

def test_the_grip_renders_only_on_a_card_that_can_actually_be_dragged() -> None:
    """Its absence is the honest signal. Every card used to advertise
    cursor:grab and then refuse to lift."""
    block = APP.split("var grip = draggable", 1)[1].split(";\n", 1)[0]
    assert "lp-drag-grip" in block
    assert "''" in block, "an ineligible card must get NO grip"


def test_multi_select_drags_lift_every_selected_card() -> None:
    start = function_source("beginDrag", module_source())
    # every id in the selection is lifted, not just the one under the pointer
    assert "active.ids.forEach" in start
    assert "lp-dragging" in start
    # and the carried object is a real deck with a count, not a lone card
    build = function_source("buildProxy", module_source())
    assert "lp-drag-proxy-back" in build and "lp-drag-proxy-count" in build
    assert "Math.min(count, 3)" in build


# ------------------------------------------------------------------- CSS

def test_drag_css_uses_theme_tokens_and_never_a_hardcoded_hex() -> None:
    """--orange is #EF5A1E in light but #FF6C36 in dark, and --orange-soft
    inverts outright, so a literal would fail one theme outright."""
    block = CSS.split("/* --- internal drag: ONE vocabulary", 1)[1].split(
        "@media (prefers-reduced-motion:reduce)", 1
    )[0]
    # Comments in this block quote the literals on purpose, to record WHY they
    # must not be used. Only the declarations are scanned.
    # The "/*" was consumed by the split above; restore it so the first comment
    # is a complete, strippable comment rather than dangling text.
    declarations = re.sub(r"/\*.*?\*/", "", "/*" + block, flags=re.S)
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", declarations), "hardcoded colour in the drag vocabulary"
    for token in ("var(--orange)", "var(--orange-soft)", "var(--red)", "var(--red-soft)"):
        assert token in block, token


def test_the_valid_target_ring_is_inset_so_targets_never_move() -> None:
    """An outset ring grows the target and nudges its neighbours mid-drag,
    which moves the thing the user is aiming at."""
    rule = CSS.split(".lp-drop-ok{", 1)[1].split("}", 1)[0]
    assert "inset 0 0 0 3px" in rule


def test_nothing_in_the_drag_system_transitions_geometry() -> None:
    """AD-20 kept normal animations but removed the geometry transitions that
    cost compositor work on weaker Windows machines. An indicator that eases
    between positions also lags the pointer and reads as unresponsive."""
    block = CSS.split("/* --- internal drag: ONE vocabulary", 1)[1].split(
        "/* --- the carried card", 1
    )[0]
    for rule in re.findall(r"transition:([^;}]+)", block):
        for prop in ("transform", "width", "height", "top", "left", "all"):
            assert prop not in rule, "geometry transition in the drag vocabulary: %s" % rule


def test_only_the_carried_card_animates_and_only_on_compositor_properties() -> None:
    """The proxy is the ONE deliberate exception: it is a single fixed element,
    it exists only while a drag is in flight, and it animates transform/opacity
    only -- both compositor properties, so the snap cannot trigger layout. The
    targets and the resting UI still animate no geometry at all."""
    rule = CSS.split(".lp-drag-proxy-settling{", 1)[1].split("}", 1)[0]
    assert "transform" in rule and "opacity" in rule
    for banned in ("width", "height", "top", "left", "margin", "all"):
        assert banned not in rule, banned
    # the tilt/scale live in JS so they can be dropped for reduced motion
    tf = function_source("proxyTransform", module_source())
    assert "rotate(3.5deg) scale(1.03)" in tf
    assert "reducedMotion()" in tf
    flat = re.sub(r"\s+", "", CSS)
    assert "prefers-reduced-motion:reduce" in flat
    assert ".lp-drag-proxy-settling{transition:none}" in flat, \
        "the snap must be instant when the user asks for reduced motion"


def test_reduced_motion_only_has_to_drop_colour_fades() -> None:
    # The stylesheet has several reduced-motion blocks; this asserts on the one
    # inside the drag vocabulary, not on whichever happens to be last.
    drag_block = CSS.split("/* --- internal drag: ONE vocabulary", 1)[1].split(
        "/* --- Home library", 1
    )[0]
    reduced = drag_block.split("@media (prefers-reduced-motion:reduce){", 1)[1]
    assert "lp-drop-ok" in reduced and "lp-drop-bad" in reduced
    assert "lp-drop-settle" in reduced


def test_the_insertion_bar_is_vertical_because_the_queue_wraps() -> None:
    """The queue is a wrapping grid in row-major order, not a vertical list. A
    horizontal full-width bar is meaningless across a wrapped row."""
    rule = CSS.split(".lp-drop-insert{", 1)[1].split("}", 1)[0]
    assert "width:3px" in rule
    assert "position:fixed" in rule, "measured from a rect, so it survives rerenders"


# ------------------------------------------------- accessible equivalents

def test_drag_never_becomes_the_only_route_to_a_capability() -> None:
    """Both new gestures are accelerators on top of controls that already
    shipped. If these disappear, the capability becomes pointer-only."""
    # Queue reorder: the buttons and the context-menu items.
    assert "qbtn('up'" in APP and "qbtn('down'" in APP
    assert "add('Move Up'" in APP and "add('Move Down'" in APP
    # Group assignment: the per-card action and the bulk dialog.
    assert "function bulkGroup()" in APP
    assert "set_jobs_group" in APP


def test_group_assignment_reuses_the_existing_bridge_call() -> None:
    """Drag must add a route to an existing capability, not a second way to
    persist one."""
    body = function_source("assignJobsToGroup", APP)
    assert "lpBridge.call('set_jobs_group'" in body
    assert "JSON.stringify(unique)" in body
    assert "Preview mode" in body, "no bridge means no silent no-op"
    assert "renderJobs()" in body


# ------------------------------------------------- discoverability (reported)

def test_every_valid_target_is_lit_when_the_drag_starts() -> None:
    """Reported as "where is it exactly droppable?". Only the target under the
    pointer used to react, so the answer was invisible until you had already
    guessed right. Every candidate now lights on lift."""
    module = module_source()
    assert "function markCandidates(kind)" in module
    start = function_source("beginDrag", module)
    assert "markCandidates(active.kind)" in start
    # ...and the count is reported, so the strip cannot claim places that are
    # not actually lit.
    assert "highlighted place" in start
    # Cleared in the single teardown path, never per-surface.
    finish = module.split("function finish() {", 1)[1].split("\n    }", 1)[0]
    assert "clearCandidates()" in finish


def test_candidate_marking_skips_reorder_and_offscreen_targets() -> None:
    """For a reorder every row is trivially a candidate, so outlining them all
    says nothing -- the insertion bar is the indicator there. And a target on a
    screen the user is not looking at must not be counted as an option."""
    mark = function_source("markCandidates", module_source())
    assert "kind !== 'lecture'" in mark
    assert "queue-reorder" in mark
    assert "offsetParent === null" in mark


def test_the_candidate_outline_cannot_reflow_the_page() -> None:
    """Lighting six targets at once must not move anything: outlines are painted
    outside the box and cost no layout, borders do not."""
    rule = CSS.split(".lp-drop-candidate{", 1)[1].split("}", 1)[0]
    assert "outline:2px dashed" in rule
    assert "border" not in rule
    # The armed target drops the dashes so it reads solid, not merely possible.
    armed = CSS.split(".lp-drop-ok{", 1)[1].split("}", 1)[0]
    assert "outline:none" in armed


def test_the_import_dropzone_accepts_an_existing_lecture() -> None:
    """It says "Drop a lecture video anywhere" and then refused the app's own
    lectures. Dropping one there can only mean "put this through the pipeline",
    so it shares the Process entry rather than growing a third semantic."""
    block = APP.split("Array.prototype.slice.call(document.querySelectorAll(", 1)[1].split("\n", 1)[0]
    assert "#dropzone" in block
    assert "lpDrop = 'process'" in APP


def test_the_carried_card_is_a_live_clone_not_a_snapshot() -> None:
    """The native path had to snapshot the card into an OS bitmap -- which is
    why it could not be tilted, scaled or eased, and why an undecoded poster
    captured a blank frame. The proxy is a real cloned element, so the poster is
    simply along for the ride and the whole thing is styleable."""
    build = function_source("buildProxy", module_source())
    assert "src.cloneNode(true)" in build
    # It must not inherit drag state from the card it was cloned from.
    for stale in ("lp-dragging", "lp-drop-ok", "lp-drop-bad", "lp-drop-candidate"):
        assert stale in build, stale
    assert "removeAttribute('draggable')" in build
    # And it must never intercept the hit-test that resolves the drop target.
    rule = CSS.split(".lp-drag-proxy{", 1)[1].split("}", 1)[0]
    assert "pointer-events:none" in rule
    resolve = function_source("updateAt", module_source())
    assert "document.elementFromPoint" in resolve


def test_no_internal_source_keeps_a_native_draggable_attribute() -> None:
    """Leaving draggable="true" on would let Chromium start its own unstyleable
    drag for the same gesture, so two input paths would race on one press."""
    assert 'draggable="true" data-existing-job-drag' not in APP
    assert '<div class="q-card" draggable="true"' not in APP
    card = APP.split("function _jobCardHtml(j) {", 1)[1].split("\n  }", 1)[0]
    # Comments here quote the attribute deliberately, to record why it is gone.
    code = re.sub(r"/\*.*?\*/", "", card, flags=re.S)
    assert 'data-lp-drag="lecture"' in code and 'draggable="true"' not in code


def test_drag_states_survive_forced_colours() -> None:
    """In high contrast every colour collapses to the system palette, so armed
    vs possible has to differ by STYLE (solid vs dashed), not hue."""
    block = CSS.split("@media (forced-colors:active){", 1)[1].split("\n}", 1)[0]
    assert "dashed Highlight" in block
    assert "solid Highlight" in block


# ------------------------------------------------- card density (reported)

def test_no_native_tooltip_competes_with_the_drag_affordance() -> None:
    """Reported as the card looking congested. Two unstyled OS tooltips -- one on
    the card, one on the grip -- stacked over the poster and covered the very
    thumbnail they described. The strip and the candidate outlines teach the
    gesture at the moment it matters, which no hover-only tooltip can."""
    card = APP.split("var grip = draggable", 1)[1].split("return '<div class=\"lp-card\"", 1)[0]
    assert "title=" not in card, "the grip regrew a native tooltip"
    decl = APP.split("return '<div class=\"lp-card\"", 1)[1].split("data-status=", 1)[0]
    assert "Drag to" not in decl, "the card regrew a native drag tooltip"


def test_the_grip_is_revealed_on_approach_not_painted_at_rest() -> None:
    """A lecture thumbnail already carries a poster, a status badge and a menu.
    A fourth permanent glyph was the difference between full and congested."""
    rule = CSS.split(".lp-drag-grip{", 1)[1].split("}", 1)[0]
    assert "opacity:0" in rule
    # up to and including the reveal group's own closing declaration
    reveal = CSS.split(".lp-drag-grip i{", 1)[1].split("opacity:1}", 1)[0]
    assert ":hover" in reveal and ":focus-within" in reveal
    # It must stay visible on the card being dragged, or the lifted card loses
    # its own affordance mid-gesture.
    assert "lp-dragging .lp-drag-grip" in reveal


def test_the_ghost_never_reserves_layout_space() -> None:
    """.lp-drag-ghost is position:fixed; the card variant re-declared relative,
    which silently overrode it. The ghost stayed off-screen only thanks to its
    left offset while still reserving a 172px block in flow for every drag."""
    rule = CSS.split(".lp-drag-ghost-card{", 1)[1].split("}", 1)[0]
    assert "position" not in rule
    base = CSS.split(".lp-drag-ghost{", 1)[1].split("}", 1)[0]
    assert "position:fixed" in base



# ------------------------------------------------------ card identity (reported)

def _q(value: str) -> str:
    import json
    return json.dumps(value)


def _display_name_source() -> str:
    body = APP.split("function _jobDisplayName(name, file) {", 1)[1].split("\n  }", 1)[0]
    return "function f(name, file) {" + body + "\n}\n"


def test_display_name_strips_the_downloader_id_but_never_a_real_bracket() -> None:
    """The card printed the yt-dlp video id twice -- in the heading and again in
    the filename line under it. Stripping is anchored on the id the SOURCE FILE
    carries rather than on a shape, and that is load-bearing: the importer
    rewrites "_" as " " when deriving the display name, so the stored name ends
    "[ OQbKAx9878]" WITH A SPACE, and any pattern loose enough to catch that also
    eats "[Lecture Notes]". The filename is unmangled, which is what makes it a
    safe anchor -- a real id has no space, a bracket the user chose does."""
    cases = [
        # the real shipped case
        ("Heinrich Schliemann The Boogeyman of Archaeology [ OQbKAx9878]",
         "Heinrich Schliemann_ The Boogeyman of Archaeology [_OQbKAx9878].mp4",
         "Heinrich Schliemann The Boogeyman of Archaeology"),
        ("Lecture 4 [_abc12345XYZ]", "Lecture 4 [_abc12345XYZ].mp4", "Lecture 4"),
        # brackets the USER chose survive, even at 8+ characters
        ("Thermo [Lecture Notes]", "Thermo [Lecture Notes].mp4", "Thermo [Lecture Notes]"),
        ("Bio 101 [2024]", "Bio 101 [2024].mp4", "Bio 101 [2024]"),
        # nothing to anchor on -> never strip
        ("Lecture 4 [ OQbKAx9878]", "", "Lecture 4 [ OQbKAx9878]"),
        ("Plain lecture", "Plain lecture.mp4", "Plain lecture"),
        # a name that is ONLY the id must not collapse to empty
        ("[ OQbKAx9878]", "[_OQbKAx9878].mp4", "[ OQbKAx9878]"),
    ]
    checks = "\n".join(
        "if (f(%s, %s) !== %s) { console.error('FAIL ' + JSON.stringify(f(%s, %s))); process.exit(1); }"
        % (_q(n), _q(fl), _q(exp), _q(n), _q(fl))
        for n, fl, exp in cases
    )
    program = _display_name_source() + checks + "\nconsole.log('OK');"
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK" in result.stdout


def test_the_name_itself_is_never_mutated() -> None:
    """Rename, search and the drag label all read j.name. Only the DISPLAYED
    string is trimmed, and the trimmed id stays recoverable on hover."""
    card = APP.split("function _jobCardHtml(j) {", 1)[1].split("\n  }", 1)[0]
    assert "var display = _jobDisplayName(j.name, j.file);" in card
    assert "j.name =" not in card
    assert "double-click to rename" in card


def test_the_subject_badge_left_the_poster() -> None:
    """A full subject name pinned top-left grew rightwards into the status badge
    pinned top-right -- measured at ~15px of overlap on a 247px card, and worse
    with longer subject names. Moving it into the body removes the collision by
    construction rather than by tuning offsets."""
    card = APP.split("function _jobCardHtml(j) {", 1)[1].split("\n  }", 1)[0]
    menu = card.split("var menu = j.id ?", 1)[1].split("';", 1)[0]
    assert "subjectBadge" not in menu, "the subject badge is back on the poster"
    assert "var kicker" in card and "subjectBadge" in card
    # Not reachable while the card's job is to be ticked.
    assert "(!selecting && j.id) ?" in card


def test_the_card_states_its_identity_once() -> None:
    """The body printed the heading, then the source filename -- the same words
    plus ".mp4" -- and only then the duration."""
    card = APP.split("function _jobCardHtml(j) {", 1)[1].split("\n  }", 1)[0]
    assert "esc(j.file || '') + '<br>'" not in card, "the duplicate filename line came back"
    assert "esc(j.meta || j.file || '')" in card, "meta line, with file kept only as a fallback"


def test_a_completed_drop_is_not_phrased_as_an_invitation() -> None:
    """Caught in the running app: after the drop the strip read "Release to ...
    moved to position 1" -- an instruction for something already finished."""
    module = module_source()
    say = function_source("say", module)
    assert "'done'" in say and "Done" in say
    drop = function_source("commit", module)
    assert "'ok'" not in drop.split("didDrop = true", 1)[1], "a confirmation still uses the armed tone"
    assert drop.count("'done'") == 3, "filed / queued / reordered must all confirm in past tense"
    assert 'data-tone="done"' in CSS


def test_dropping_on_ungrouped_clears_the_group_instead_of_naming_it() -> None:
    """"Ungrouped" is a synthetic bucket renderJobs invents for lectures with no
    group, not a subject you can belong to. Writing the literal string would
    create a real subject that looks identical in the list but permanently
    suppresses the inferred grouping for that lecture."""
    drop = function_source("commit", module_source())
    assert "if (group === 'Ungrouped') group = '';" in drop


def test_a_filing_that_cannot_change_the_visible_subject_is_refused() -> None:
    """Caught in the running app: dropping "CL100 - Day 9 ..." on the Ungrouped
    header DID clear j.group, and the strip confirmed "filed under Ungrouped" --
    but jobGroup() then re-infers CL100 from the name, so the card never moved.
    A confirmation for an invisible change is the same silent failure as the
    no-op reorder, and is refused the same way: before preventDefault."""
    module = module_source()
    assert "function bucketAfter(job, group)" in module
    over = function_source("updateAt", module)
    group_branch = over.split("if (desc.drop === 'group') {", 1)[1]
    refusal = group_branch.index("already filed under")
    arming = group_branch.index("armed = { desc: desc")
    assert refusal < arming, "a pointless filing is armed before it is refused"
    assert "bucketAfter(job, target) === jobGroup(job)" in group_branch
    assert "paintProxy('bad')" in group_branch


# ------------------------------------------------- group surface (reported)

def test_the_whole_group_box_takes_the_drop_not_just_its_header() -> None:
    """Reported with an annotated screenshot: the header strip was the target and
    the big box was not. Aiming a card at a ~30px bar is fussy when a 400px box
    means the same thing -- and because cards live inside the section, dropping
    onto any card in a subject now files the lecture into that subject."""
    jobs = APP.split("function renderJobs()", 1)[1]
    section = jobs.split("return '<section class=\"lib-group\"", 1)[1].split("+", 1)[0]
    assert 'data-lp-drop="group"' in section, "the section itself must be the target"
    head = jobs.split("'<div class=\"lib-group-head\"", 1)[1].split(">'", 1)[0]
    assert "data-lp-drop" not in head, "the header must no longer be its own target"


def test_the_library_group_header_can_rename_like_a_subject_card() -> None:
    """Renaming a subject from the library was only reachable through a single
    lecture's badge, so the two screens disagreed about where the action lives.
    Both surfaces must share ONE commit path or they will drift."""
    assert "function handleGroupRename(titleEl, oldGroup, fontCss)" in APP
    # the Subjects card is now a thin caller of the shared implementation
    card = APP.split("function handleSubjectCardRename(cardEl, oldGroup) {", 1)[1].split("\n  }", 1)[0]
    assert "handleGroupRename(" in card
    assert 'data-group-rename=' in APP
    # renaming from either surface has to refresh both, including on Escape
    shared = APP.split("function handleGroupRename(titleEl, oldGroup, fontCss) {", 1)[1].split("\n  }", 1)[0]
    assert "renderSubjects()" in shared and "renderJobs()" in shared
    escape_line = [l for l in shared.splitlines() if "Escape" in l][0]
    assert "renderJobs()" in escape_line, "Escape would leave a live input in the library header"


def test_select_mode_can_take_a_whole_subject_at_once() -> None:
    """The bulk actions already operate on a selection; the missing piece was a
    way to say "this whole subject"."""
    assert "function groupFullySelected(members)" in APP
    assert 'data-group-select=' in APP
    handler = APP.split("g.querySelectorAll('[data-group-select]')", 1)[1].split("\n    });", 1)[0]
    # it toggles rather than only ever adding
    assert "groupFullySelected(members)" in handler
    assert "delete LP.state.selected[id]" in handler
    assert "renderSelCount()" in handler
    # the control only exists while selecting
    assert "LP.state.selecting" in APP.split("data-group-select=", 1)[0][-400:]


def test_the_new_group_controls_stay_inside_the_home_library_motion_rule() -> None:
    """That block forbids easing outright -- it was the confirmed flicker hot
    spot on the affected laptop -- so these controls must not reintroduce any."""
    block = CSS.split("--- Home library:", 1)[1].split("\n.lp-slide-rail-head", 1)[0]
    # The "/*" was consumed by the split, so restore it -- otherwise the section
    # header comment is unstrippable text and its own prose trips the check.
    rules = re.sub(r"/\*.*?\*/", "", "/*" + block, flags=re.S)
    for prop in ("lib-group-rename", "lib-group-select"):
        assert prop in rules, prop
    for banned in ("transition", "animation", "will-change"):
        assert banned not in rules, banned
