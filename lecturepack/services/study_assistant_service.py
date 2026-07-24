"""
lecturepack.services.study_assistant_service
=============================================

Backs the Study page's "Study assistant" panel (Chat / Quiz / Flashcards)
with the local Ollama endpoint already used for Context Repair.

Architecturally this mirrors ``ai_repair_service.AiRepairWorker``:
generation always runs on a QThread, every failure mode is caught at the
worker boundary and reported as a typed signal, and the deterministic
"opt-in local AI" gate (``config.get("ollama")``) is identical.

There is deliberately no offline/deterministic fallback here (unlike
Context Repair): a quiz or flashcard set generated from question/answer
pairs is inherently a generative task, not one with a sensible
extractive substitute, so when Ollama is unavailable the panel simply
reports that plainly instead of pretending to degrade gracefully.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from PySide6.QtCore import QObject, QThread, Signal

from lecturepack.infrastructure.ollama_client import OllamaClient, OllamaError

MAX_TRANSCRIPT_CHARS = 6000

CHAT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_index": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["question", "options", "correct_index", "explanation"],
            },
        }
    },
    "required": ["questions"],
}

FLASHCARDS_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "definition": {"type": "string"},
                    "tag": {"type": "string"},
                },
                "required": ["term", "definition"],
            },
        }
    },
    "required": ["cards"],
}

_SYSTEM_BASE = (
    "You are a study assistant embedded in a lecture note-taking app. "
    "Ground every answer strictly in the lecture transcript excerpt provided "
    "-- never invent facts, names, or figures the transcript doesn't support. "
    "If the transcript doesn't contain enough information to answer, say so "
    "plainly instead of guessing. Be concise."
)


def transcript_context(segments: list, max_chars: int = MAX_TRANSCRIPT_CHARS) -> str:
    """Join segment text into one bounded excerpt for prompt context.

    Truncates from the end rather than dropping segments outright, so a
    long lecture still contributes as much of its transcript as fits
    the model's context window instead of an arbitrary head-only slice
    silently losing later material -- callers needing the full picture
    for a specific timestamp should filter ``segments`` first."""
    text = " ".join(str(s.get("text") or "").strip() for s in segments).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def _chat_prompt(transcript_text: str, history: list, question: str):
    system = _SYSTEM_BASE + " Answer the student's question about the lecture."
    convo = "\n".join(f"{m.get('role', 'user')}: {m.get('text', '')}" for m in history[-6:])
    user = (f"Lecture transcript excerpt:\n{transcript_text}\n\n"
           f"{'Conversation so far:' + chr(10) + convo + chr(10) + chr(10) if convo else ''}"
           f"Student's question: {question}")
    return system, user, CHAT_SCHEMA


_QUIZ_DIFFICULTY_HINT = {
    "easy": "Target simple recall of facts, names, or figures stated outright.",
    "medium": "Target understanding and connections between ideas, not just recall.",
    "hard": "Target deeper reasoning, implications, and fine distinctions from the material.",
    "mixed": "Vary difficulty across the set, from recall to deeper reasoning.",
}


def _quiz_prompt(transcript_text: str, count: int,
                 difficulty: str = "Mixed", qtype: str = "Multiple choice"):
    tf = "true" in (qtype or "").lower()
    form = ('true/false questions (options MUST be exactly ["True","False"])' if tf
            else "multiple-choice questions with 3 or 4 options")
    diff = _QUIZ_DIFFICULTY_HINT.get((difficulty or "mixed").strip().lower(),
                                     _QUIZ_DIFFICULTY_HINT["mixed"])
    system = (
        "You are an expert exam writer. Using ONLY the lecture transcript excerpt "
        f"provided, write exactly {count} {form}. Requirements: "
        "(1) Each question tests a SPECIFIC fact, name, number, definition, cause, or "
        "claim actually stated in the transcript — never test outside knowledge or "
        "invent details. (2) Exactly one option is correct; wrong options must be "
        "plausible and on the SAME topic as the lecture (not silly or generic). "
        "(3) Never ask meta questions about 'the lecture', 'the speaker', 'this "
        "recording', the audio, or the transcript itself — ask about the subject "
        "matter. (4) No 'all/none of the above'; no duplicate questions. "
        "(5) Each question is one clear sentence; the explanation is one sentence that "
        "states the supporting fact from the transcript. " + diff +
        " Ground everything strictly in the transcript; if it is too thin, write fewer "
        "but valid questions rather than inventing content."
    )
    user = f"Lecture transcript excerpt:\n{transcript_text}\n\nGenerate the quiz now as JSON."
    return system, user, QUIZ_SCHEMA


def _flashcards_prompt(transcript_text: str, count: int,
                       difficulty: str = "Basic", qtype: str = ""):
    depth = {
        "basic": "Keep definitions short (one sentence).",
        "detailed": "Give a fuller 1-2 sentence definition with a concrete detail.",
        "exam-focused": "Phrase each card the way it would be tested on an exam.",
    }.get((difficulty or "basic").strip().lower(), "Keep definitions concise.")
    system = (
        f"You are a study assistant. Using ONLY the lecture transcript excerpt, write "
        f"exactly {count} flashcards for the most important terms/concepts ACTUALLY "
        "discussed. Each card: a short specific \"term\" (the front) and a concise "
        "\"definition\" (the back) grounded in what the transcript says about it. "
        "Never invent terms not in the transcript; skip filler/stopwords; no duplicates. "
        + depth
    )
    user = f"Lecture transcript excerpt:\n{transcript_text}\n\nGenerate the flashcards now as JSON."
    return system, user, FLASHCARDS_SCHEMA


class StudyAssistantWorker(QObject):
    """Runs one chat/quiz/flashcards generation in a QThread.

    Signals (all queued to the GUI thread):
        status(str)                 -- human-readable status line
        finished_ok(str, object)    -- (task, result) where result is
                                        {"answer": str} | {"questions": [...]} | {"cards": [...]}
        failed(str, str, str)       -- (kind, message, diagnostic_details)
    """
    status = Signal(str)
    finished_ok = Signal(str, object)
    failed = Signal(str, str, str)

    def __init__(self, task: str, transcript_text: str,
                 ollama_settings: Optional[dict] = None,
                 history: Optional[list] = None, question: str = "",
                 count: int = 5, difficulty: str = "Mixed", qtype: str = ""):
        super().__init__()
        assert task in ("chat", "quiz", "flashcards")
        self.task = task
        self.transcript_text = transcript_text
        self.ollama = dict(ollama_settings or {})
        self.history = list(history or [])
        self.question = question
        self.count = count
        self.difficulty = difficulty
        self.qtype = qtype
        self.cancel_event = threading.Event()
        self._thread: Optional[QThread] = None

    # ---- lifecycle ------------------------------------------------------ #
    def start(self):
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)
        self._thread.start()
        return self._thread

    def cancel(self):
        self.cancel_event.set()

    def detach_and_stop(self):
        self.cancel()
        thread = self._thread
        if thread is None or thread.isFinished():
            return
        thread.requestInterruption()
        thread.quit()

    # ---- worker body ------------------------------------------------------ #
    def _run(self):
        try:
            self._run_inner()
        except Exception as e:  # absolute boundary: never let anything escape
            import traceback
            self.failed.emit("internal", str(e), traceback.format_exc())
        finally:
            if self._thread is not None:
                self._thread.quit()

    def _run_inner(self):
        if not bool(self.ollama.get("enabled")) or not self.ollama.get("model"):
            self.failed.emit(
                "disabled",
                "Local AI assistance is off. Turn it on in Settings > Local AI endpoint "
                "to use the study assistant.", "")
            return

        client = OllamaClient(self.ollama.get("base_url") or None or "http://localhost:11434")
        probe = client.is_available()
        if not probe.get("available"):
            self.failed.emit(
                "unavailable",
                "Ollama is not reachable. Check that it's running and reachable at the "
                "configured URL in Settings.", str(probe.get("error", "")))
            return

        if self.task == "chat":
            system, user, schema = _chat_prompt(self.transcript_text, self.history, self.question)
        elif self.task == "quiz":
            system, user, schema = _quiz_prompt(self.transcript_text, self.count,
                                                self.difficulty, self.qtype)
        else:
            system, user, schema = _flashcards_prompt(self.transcript_text, self.count,
                                                      self.difficulty, self.qtype)

        self.status.emit(f"Asking {self.ollama.get('model')}…")
        try:
            result = client.chat_structured(
                self.ollama["model"], system, user, schema,
                keep_alive=self.ollama.get("keep_alive", "10m"),
                cancel_event=self.cancel_event)
        except OllamaError as e:
            self.failed.emit(e.kind, self._friendly(e), str(e))
            return

        import json
        try:
            payload = json.loads(result["content"])
        except (ValueError, TypeError, KeyError) as e:
            self.failed.emit("bad_response", "Ollama returned an invalid response.", str(e))
            return

        self.finished_ok.emit(self.task, payload)

    @staticmethod
    def _friendly(e: OllamaError) -> str:
        return {
            "unavailable": "Ollama is not reachable (is the service running?).",
            "timeout": "The Ollama request timed out.",
            "bad_response": "Ollama returned an invalid response.",
            "cancelled": "The request was cancelled.",
        }.get(e.kind, str(e))
