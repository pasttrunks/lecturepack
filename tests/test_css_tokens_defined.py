"""Every var(--token) in app.css must actually be defined in app.css.

The microinteraction polish styled the slide loupe with ``box-shadow: var(--shadow)``.
No such token exists -- the file defines ``--shadow-hard``, ``--shadow-hard-sm``,
``--shadow-soft``, ``--shadow-hi`` and ``--shadow-ink``. An undefined custom
property is not an error in CSS: the declaration is simply dropped, so the loupe
rendered with NO shadow and nothing anywhere reported a problem.

That is the whole failure mode worth guarding. A typo'd or invented token name
degrades silently, looks "nearly right" in review, and only a person comparing
against the design system would ever catch it.
"""

import os
import re

UI_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "ui"
)
CSS_RAW = open(os.path.join(UI_DIR, "app.css"), encoding="utf-8").read()
# Comments describe tokens too ("was var(--shadow), which ..."), and a prose
# mention is not a reference.
CSS = re.sub(r"/\*.*?\*/", "", CSS_RAW, flags=re.S)
JS = open(os.path.join(UI_DIR, "app.js"), encoding="utf-8").read()

# Tokens the stylesheet consumes but JavaScript owns (element.style.setProperty),
# discovered rather than hand-listed so a new one does not need a test edit.
EXTERNAL = set(re.findall(r"setProperty\(\s*['\"](--[A-Za-z0-9-]+)['\"]", JS))


def _defined() -> set[str]:
    # A definition is `--name:` appearing as a declaration, not inside var().
    return set(re.findall(r"(--[A-Za-z0-9-]+)\s*:", CSS))


def _referenced() -> set[str]:
    return set(re.findall(r"var\(\s*(--[A-Za-z0-9-]+)", CSS))


def test_every_referenced_custom_property_is_defined():
    defined = _defined()
    missing = sorted(name for name in _referenced() - defined if name not in EXTERNAL)
    assert not missing, (
        "app.css references custom properties it never defines: "
        + ", ".join(missing)
        + ". CSS drops the whole declaration silently, so the style just does not apply."
    )


def test_shadow_token_family_is_intact():
    """Pins the specific names, so a rename cannot quietly orphan a reference."""
    defined = _defined()
    for name in ("--shadow-hard", "--shadow-hard-sm", "--shadow-ink"):
        assert name in defined, f"{name} is missing from app.css"


def test_no_blurred_box_shadow_creeps_back_in():
    """The design language is neobrutalist: hard offsets, zero blur.

    A third length in a box-shadow is a blur radius. The polish arrived with a
    22px-blur drop-shadow on the carried drag card -- the only soft shadow in the
    file -- which read as a different application. Glows (`0 0 Npx`) on the
    deliberately-glowing demo card and scrollbar predate this and are exempt by
    selector, not by shape.
    """
    exempt = ("#glowing-demo-card", "::-webkit-scrollbar-thumb", "#dropzone.lp-demo-drop-hover")
    offenders = []
    for rule in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        selector, body = rule[0].strip(), rule[1]
        if any(token in selector for token in exempt):
            continue
        for decl in re.findall(r"(?:box-shadow|filter)\s*:[^;}]+", body):
            if re.search(r"\b\d+px\s+-?\d+px\s+[1-9]\d*px", decl):
                offenders.append(f"{selector[:40]} -> {decl.strip()[:70]}")
    assert not offenders, "blurred shadow in a neobrutalist system:\n" + "\n".join(offenders)
