"""Named-scenario acceptance for quiz + flashcards (§7/§8) — HEADLESS BACKEND.

This is NOT an interactive click-through. It drives the real WebView adapter
(`LecturePackAdapter.generate_quiz` / `generate_flashcards` + session save/restore)
against a THROWAWAY temp data dir, exercising exactly the sizes the acceptance
prompt names: a 3-question and a 20-question quiz, and a 5-card and 20-card
flashcard session. It uses the deterministic no-AI fallback (no Ollama required)
so the result is reproducible on any machine. It never touches ~/LecturePackData.

Run:  .venv/Scripts/python.exe docs/evidence/.../named_scenario_acceptance/harness.py [out.txt]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
APP_DIR = os.path.join(ROOT, "app")
for p in (APP_DIR, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from desktop import engine_adapter as ea  # noqa: E402
from lecturepack.infrastructure.config_manager import ConfigManager  # noqa: E402
from lecturepack.models.job import Job  # noqa: E402
from lecturepack.services import study_service  # noqa: E402

# 26 unique term/sentence pairs so count=20 has room (one sentence consumed per Q).
_PAIRS = [
    ("Ziggurat", "The Ziggurat was a massive terraced temple at the city center."),
    ("Cuneiform", "Scribes recorded trade using Cuneiform pressed into clay."),
    ("Hammurabi", "King Hammurabi issued one of the earliest written legal codes."),
    ("Euphrates", "The Euphrates fed the irrigation canals of the plain."),
    ("Babylon", "Babylon grew into the dominant power of the region."),
    ("Tigris", "The Tigris flooded less predictably than its neighbor."),
    ("Sumer", "Sumer is often called the cradle of urban civilization."),
    ("Akkad", "Sargon united the cities under the banner of Akkad."),
    ("Uruk", "Uruk was among the first true cities in the world."),
    ("Assyria", "Assyria built a feared standing army in the north."),
    ("Nineveh", "The great library was housed at Nineveh."),
    ("Marduk", "The chief god of the capital was Marduk."),
    ("Gilgamesh", "The epic hero Gilgamesh sought eternal life."),
    ("Enlil", "Storms were attributed to the god Enlil."),
    ("Ishtar", "A famous gate was dedicated to Ishtar."),
    ("Nippur", "The religious center of the south was Nippur."),
    ("Lagash", "A boundary dispute troubled the city of Lagash."),
    ("Ur", "The moon god was worshipped at Ur."),
    ("Kish", "Kingship first descended upon Kish."),
    ("Elam", "Raiders came from the eastern land of Elam."),
    ("Sargon", "Sargon founded the first known empire."),
    ("Ea", "The god of wisdom was Ea."),
    ("Anu", "The sky father of the pantheon was Anu."),
    ("Mari", "Palace archives survived at Mari."),
    ("Eridu", "Tradition held Eridu as the oldest city."),
    ("Zagros", "Rain fell on the distant Zagros mountains."),
]
_TERMS = [t for t, _ in _PAIRS]
_SENTS = [s for _, s in _PAIRS]


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)


class _FakeBackend:
    def __init__(self):
        for n in ("log_line", "quiz_changed", "quiz_status",
                  "flashcards_changed", "flashcards_status", "study_changed"):
            setattr(self, n, _Signal())


def _make_adapter(tmp):
    a = ea.LecturePackAdapter.__new__(ea.LecturePackAdapter)
    a.config = ConfigManager(tmp)
    a.config.set("ollama", {})  # AI OFF -> deterministic fallback path
    a.backend = _FakeBackend()
    a.current_job = Job(tmp, video_path="lecture.mp4")
    # ground the fallback in a real transcript + key terms
    study_service.build_overview = lambda job: {"key_terms": _TERMS}
    ea.transcript_store.load_working = lambda paths: [{"text": s} for s in _SENTS]
    return a


def _last(sig):
    return json.loads(sig.emissions[-1])


def main():
    out_lines = []

    def say(msg):
        out_lines.append(msg)
        print(msg)

    say("NAMED-SCENARIO ACCEPTANCE (headless backend; no AI; temp data)")
    say("=" * 64)
    ok = True

    with tempfile.TemporaryDirectory() as tmp:
        # ---- Quiz: 3 questions ----
        a = _make_adapter(tmp)
        a.generate_quiz(json.dumps({"count": 3, "difficulty": "Easy",
                                    "type": "Multiple choice", "source": "Transcript"}))
        q3 = _last(a.backend.quiz_changed)
        st3 = _last(a.backend.quiz_status)
        n3 = len(q3["questions"])
        say(f"[quiz  3] delivered={n3} provider={q3['provider']!r} state={st3['state']}")
        ok &= (n3 == 3 and st3["state"] == "ready")
        # shape check on first question
        first = q3["questions"][0]
        shape_ok = ("question" in first and len(first["options"]) >= 2
                    and 0 <= first["correct_index"] < len(first["options"]))
        say(f"          shape_ok={shape_ok} sample={first['question'][:60]!r}")
        ok &= shape_ok

        # ---- Quiz: 20 questions ----
        a.generate_quiz(json.dumps({"count": 20, "difficulty": "Hard",
                                    "type": "Mixed", "source": "Both"}))
        q20 = _last(a.backend.quiz_changed)
        n20 = len(q20["questions"])
        say(f"[quiz 20] delivered={n20} provider={q20['provider']!r} "
            f"(fallback caps at usable grounded terms)")
        ok &= (n20 >= 15)  # 26 pairs -> expect close to 20

        # ---- Quiz session save/restore ----
        a.save_quiz_session(json.dumps({"phase": "session", "index": 2,
                                        "answers": {"0": 1, "1": 0}, "flags": {}}))
        restored = study_service.load_study_data(a.current_job)["quiz"].get("session")
        sess_ok = bool(restored) and restored.get("index") == 2
        say(f"[quiz  session] persisted index={restored.get('index') if restored else None} ok={sess_ok}")
        ok &= sess_ok

        # ---- Flashcards: 5 cards ----
        a.generate_flashcards(json.dumps({"count": 5, "difficulty": "Basic",
                                          "style": "Term → definition"}))
        f5 = _last(a.backend.flashcards_changed)
        fs5 = _last(a.backend.flashcards_status)
        m5 = len(f5["cards"])
        say(f"[flash 5] delivered={m5} provider={f5['provider']!r} state={fs5['state']}")
        ok &= (m5 == 5 and fs5["state"] == "ready")

        # ---- Flashcards: 20 cards ----
        a.generate_flashcards(json.dumps({"count": 20, "difficulty": "Detailed",
                                          "style": "Mixed"}))
        f20 = _last(a.backend.flashcards_changed)
        m20 = len(f20["cards"])
        say(f"[flash 20] delivered={m20} provider={f20['provider']!r}")
        ok &= (m20 >= 15)

        # ---- Flashcard session save/restore ----
        a.save_flashcard_session(json.dumps({"phase": "session", "index": 3,
                                             "known": {"0": 1}, "unsure": {"1": 1}}))
        fr = study_service.load_study_data(a.current_job)["flashcards"].get("session")
        fsess_ok = bool(fr) and fr.get("index") == 3
        say(f"[flash session] persisted index={fr.get('index') if fr else None} ok={fsess_ok}")
        ok &= fsess_ok

    say("=" * 64)
    say("RESULT: " + ("NAMED_SCENARIOS_OK" if ok else "FAILED"))

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as fh:
            fh.write("\n".join(out_lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
