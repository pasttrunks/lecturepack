"""
lecturepack.ui.widgets.study_assistant_panel
=============================================

The Study page's "Study assistant" card: Chat / Quiz / Flashcards tabs
backed by the local Ollama endpoint via
``services.study_assistant_service.StudyAssistantWorker``.

Generation always runs on a QThread (never the GUI thread), mirroring the
``ContextRepairPanel`` <-> ``AiRepairWorker`` relationship elsewhere in the
app: one worker in flight at a time, cooperative cancellation, and a plain
status message rather than a silent fallback when Ollama isn't reachable
(there is no deterministic substitute for "make up quiz questions").
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

from lecturepack.services import study_assistant_service as sas
from lecturepack.services import study_service
from lecturepack.ui import theme


class _ChatBubble(QFrame):
    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet("border: none; background: transparent;")
        lay.addWidget(lbl)
        is_user = role == "user"
        bg = theme.c("primary_soft") if is_user else theme.c("panel")
        border = theme.c("primary") if is_user else theme.c("line")
        self.setStyleSheet(
            f"_ChatBubble {{ background: {bg}; border: 1.5px solid {border}; border-radius: 11px; }}")
        self.setMaximumWidth(520)


class _FlashcardWidget(QFrame):
    """Click-to-flip term/definition card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(160)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(26, 26, 26, 26)
        lay.setSpacing(12)
        self.tag_lbl = QLabel("")
        self.tag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tag_lbl.setStyleSheet(
            f"font:500 10px '{theme.FONT_MONO}';letter-spacing:0.12em;"
            f"text-transform:uppercase;color:{theme.c('secondary_ink')};border:none;background:transparent;")
        lay.addWidget(self.tag_lbl)
        self.face_lbl = QLabel("")
        self.face_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.face_lbl.setWordWrap(True)
        self.face_lbl.setStyleSheet("font-weight: 700; font-size: 17px; border: none; background: transparent;")
        lay.addWidget(self.face_lbl)
        self.hint_lbl = QLabel("tap to flip")
        self.hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_lbl.setProperty("muted", True)
        self.hint_lbl.setStyleSheet(f"font:500 11px '{theme.FONT_MONO}';border:none;background:transparent;")
        lay.addWidget(self.hint_lbl)
        self._card = None
        self._flipped = False

    def set_card(self, card: dict):
        self._card = card
        self._flipped = False
        self._render()

    def mousePressEvent(self, event):
        if self._card is not None:
            self._flipped = not self._flipped
            self._render()
        super().mousePressEvent(event)

    def _render(self):
        if not self._card:
            self.tag_lbl.setText("")
            self.face_lbl.setText("No flashcards yet.")
            self.hint_lbl.setText("")
            return
        if self._flipped:
            self.tag_lbl.setText("Definition")
            self.face_lbl.setText(str(self._card.get("definition", "")))
        else:
            self.tag_lbl.setText(str(self._card.get("tag") or "Term"))
            self.face_lbl.setText(str(self._card.get("term", "")))
        self.hint_lbl.setText("tap to flip")


class StudyAssistantPanel(QWidget):
    """Chat / Quiz / Flashcards tabs. Call ``load_job`` whenever the Study
    page's job changes, and ``shutdown`` when the app is closing."""

    status_message = Signal(str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.job = None
        self._transcript_text = ""
        self._chat_history = []
        self._quiz_questions = []
        self._quiz_index = 0
        self._quiz_selected = None
        self._flashcards = []
        self._flashcard_index = 0
        self._worker = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(4, 4, 4, 8)
        icon = QLabel("✦")
        icon.setStyleSheet(f"color:{theme.c('primary')};font-size:16px;border:none;background:transparent;")
        header.addWidget(icon)
        title = QLabel("Study assistant")
        title.setStyleSheet("font-weight: 700; font-size: 15px;")
        header.addWidget(title)
        header.addStretch(1)
        self.status_badge = QLabel("")
        self.status_badge.setStyleSheet(
            f"font:600 10px '{theme.FONT_MONO}';text-transform:uppercase;border-radius:7px;"
            f"padding:4px 9px;border:none;")
        header.addWidget(self.status_badge)
        outer.addLayout(header)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_chat_tab(), "Chat")
        self.tabs.addTab(self._build_quiz_tab(), "Quiz")
        self.tabs.addTab(self._build_flashcards_tab(), "Flashcards")

        self._refresh_badge()

    def _build_chat_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(9)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_container = QWidget()
        self.chat_lay = QVBoxLayout(self.chat_container)
        self.chat_lay.setContentsMargins(4, 4, 4, 4)
        self.chat_lay.setSpacing(10)
        self.chat_lay.addStretch(1)
        self.chat_scroll.setWidget(self.chat_container)
        lay.addWidget(self.chat_scroll, 1)

        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask about this lecture…")
        self.chat_input.returnPressed.connect(self._send_chat)
        row.addWidget(self.chat_input, 1)
        self.chat_send_btn = QPushButton("Send")
        self.chat_send_btn.setProperty("primary", True)
        self.chat_send_btn.clicked.connect(self._send_chat)
        row.addWidget(self.chat_send_btn)
        lay.addLayout(row)
        return w

    def _build_quiz_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)

        self.quiz_progress_lbl = QLabel("")
        self.quiz_progress_lbl.setProperty("muted", True)
        self.quiz_progress_lbl.setStyleSheet(f"font:500 10px '{theme.FONT_MONO}';border:none;background:transparent;")
        lay.addWidget(self.quiz_progress_lbl)

        self.quiz_question_lbl = QLabel("Generate a quiz from this lecture's transcript.")
        self.quiz_question_lbl.setWordWrap(True)
        self.quiz_question_lbl.setStyleSheet("font-weight: 700; font-size: 16px; border:none; background:transparent;")
        lay.addWidget(self.quiz_question_lbl)

        self.quiz_options_lay = QVBoxLayout()
        self.quiz_options_lay.setSpacing(8)
        lay.addLayout(self.quiz_options_lay)
        self._quiz_option_btns = []

        self.quiz_answer_row = QFrame()
        self.quiz_answer_row.setProperty("card", True)
        ar_lay = QHBoxLayout(self.quiz_answer_row)
        self.quiz_answer_lbl = QLabel("")
        self.quiz_answer_lbl.setWordWrap(True)
        self.quiz_answer_lbl.setStyleSheet("border:none;background:transparent;font-weight:600;font-size:13px;")
        ar_lay.addWidget(self.quiz_answer_lbl, 1)
        self.quiz_next_btn = QPushButton("Next")
        self.quiz_next_btn.setProperty("primary", True)
        self.quiz_next_btn.clicked.connect(self._quiz_next)
        ar_lay.addWidget(self.quiz_next_btn)
        self.quiz_answer_row.setVisible(False)
        lay.addWidget(self.quiz_answer_row)

        lay.addStretch(1)

        self.quiz_generate_btn = QPushButton("Generate quiz")
        self.quiz_generate_btn.setProperty("primary", True)
        self.quiz_generate_btn.clicked.connect(lambda: self._generate("quiz"))
        lay.addWidget(self.quiz_generate_btn)
        return w

    def _build_flashcards_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)

        self.flashcard_widget = _FlashcardWidget()
        lay.addWidget(self.flashcard_widget, 1)

        nav = QHBoxLayout()
        self.flashcard_counter_lbl = QLabel("")
        self.flashcard_counter_lbl.setProperty("muted", True)
        self.flashcard_counter_lbl.setStyleSheet(f"font:500 12px '{theme.FONT_MONO}';border:none;background:transparent;")
        nav.addWidget(self.flashcard_counter_lbl)
        nav.addStretch(1)
        self.flashcard_next_btn = QPushButton("Next")
        self.flashcard_next_btn.setProperty("primary", True)
        self.flashcard_next_btn.clicked.connect(self._flashcard_next)
        nav.addWidget(self.flashcard_next_btn)
        lay.addLayout(nav)

        self.flashcard_generate_btn = QPushButton("Generate flashcards")
        self.flashcard_generate_btn.setProperty("primary", True)
        self.flashcard_generate_btn.clicked.connect(lambda: self._generate("flashcards"))
        lay.addWidget(self.flashcard_generate_btn)
        return w

    # ------------------------------------------------------------------ #
    # job lifecycle
    # ------------------------------------------------------------------ #
    def load_job(self, job, segments):
        self._teardown_worker()
        self.job = job
        self._transcript_text = sas.transcript_context(segments or [])
        if job is None:
            self._chat_history = []
            self._quiz_questions = []
            self._flashcards = []
        else:
            self._chat_history = study_service.load_chat_messages(job)
            quiz_data = study_service.load_quiz(job)
            self._quiz_questions = list(quiz_data.get("questions") or [])
            flashcard_data = study_service.load_flashcards(job)
            self._flashcards = list(flashcard_data.get("cards") or [])
        self._quiz_index = 0
        self._quiz_selected = None
        self._flashcard_index = 0
        self._rebuild_chat()
        self._render_quiz()
        self._render_flashcards()
        self._refresh_badge()

    def shutdown(self):
        self._teardown_worker()

    def _ollama_settings(self) -> dict:
        return dict(self.config_manager.get("ollama", {}) or {})

    def _refresh_badge(self):
        o = self._ollama_settings()
        if o.get("enabled") and o.get("model"):
            self.status_badge.setText(f"Local · {o['model']}")
            self.status_badge.setStyleSheet(
                self.status_badge.styleSheet()
                + f"background:{theme.c('green_soft')};color:{theme.c('green')};")
        else:
            self.status_badge.setText("AI assistance off")
            self.status_badge.setStyleSheet(
                self.status_badge.styleSheet()
                + f"background:{theme.c('sunk')};color:{theme.c('muted')};")

    # ------------------------------------------------------------------ #
    # worker plumbing
    # ------------------------------------------------------------------ #
    def _teardown_worker(self):
        if self._worker is not None:
            self._worker.detach_and_stop()
            self._worker = None

    def _generate(self, task: str, question: str = ""):
        if self._worker is not None or self.job is None:
            return
        self._worker = sas.StudyAssistantWorker(
            task, self._transcript_text, self._ollama_settings(),
            history=self._chat_history, question=question, count=5)
        self._worker.status.connect(self.status_message)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        if task == "chat":
            self.chat_send_btn.setEnabled(False)
            self.chat_input.setEnabled(False)
        elif task == "quiz":
            self.quiz_generate_btn.setEnabled(False)
            self.quiz_generate_btn.setText("Generating…")
        else:
            self.flashcard_generate_btn.setEnabled(False)
            self.flashcard_generate_btn.setText("Generating…")
        self._worker.start()

    def _on_finished(self, task, payload):
        self._teardown_worker()
        if task == "chat":
            self.chat_send_btn.setEnabled(True)
            self.chat_input.setEnabled(True)
            answer = str(payload.get("answer", "")).strip() or "(no answer)"
            self._chat_history.append({"role": "assistant", "text": answer})
            if self.job is not None:
                study_service.append_chat_message(self.job, "assistant", answer)
            self._rebuild_chat()
        elif task == "quiz":
            self.quiz_generate_btn.setEnabled(True)
            self.quiz_generate_btn.setText("Regenerate quiz")
            self._quiz_questions = list(payload.get("questions") or [])
            self._quiz_index = 0
            self._quiz_selected = None
            if self.job is not None:
                study_service.save_quiz(self.job, self._quiz_questions)
            self._render_quiz()
        else:
            self.flashcard_generate_btn.setEnabled(True)
            self.flashcard_generate_btn.setText("Regenerate flashcards")
            self._flashcards = list(payload.get("cards") or [])
            self._flashcard_index = 0
            if self.job is not None:
                study_service.save_flashcards(self.job, self._flashcards)
            self._render_flashcards()

    def _on_failed(self, kind, message, _details):
        self._teardown_worker()
        self.chat_send_btn.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.quiz_generate_btn.setEnabled(True)
        self.quiz_generate_btn.setText("Generate quiz")
        self.flashcard_generate_btn.setEnabled(True)
        self.flashcard_generate_btn.setText("Generate flashcards")
        self.status_message.emit(message)

    # ------------------------------------------------------------------ #
    # chat
    # ------------------------------------------------------------------ #
    def _rebuild_chat(self):
        while self.chat_lay.count() > 1:
            item = self.chat_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for msg in self._chat_history:
            bubble = _ChatBubble(msg.get("role", "user"), msg.get("text", ""))
            row = QHBoxLayout()
            if msg.get("role") == "user":
                row.addStretch(1)
                row.addWidget(bubble)
            else:
                row.addWidget(bubble)
                row.addStretch(1)
            row_w = QWidget()
            row_w.setLayout(row)
            self.chat_lay.insertWidget(self.chat_lay.count() - 1, row_w)

    def _send_chat(self):
        question = self.chat_input.text().strip()
        if not question or self._worker is not None:
            return
        self.chat_input.clear()
        self._chat_history.append({"role": "user", "text": question})
        if self.job is not None:
            study_service.append_chat_message(self.job, "user", question)
        self._rebuild_chat()
        self._generate("chat", question=question)

    # ------------------------------------------------------------------ #
    # quiz
    # ------------------------------------------------------------------ #
    def _render_quiz(self):
        for btn in self._quiz_option_btns:
            btn.setParent(None)
            btn.deleteLater()
        self._quiz_option_btns = []
        self.quiz_answer_row.setVisible(False)

        if not self._quiz_questions:
            self.quiz_progress_lbl.setText("")
            self.quiz_question_lbl.setText("Generate a quiz from this lecture's transcript.")
            return
        total = len(self._quiz_questions)
        self._quiz_index = max(0, min(self._quiz_index, total - 1))
        q = self._quiz_questions[self._quiz_index]
        self.quiz_progress_lbl.setText(f"Question {self._quiz_index + 1} of {total}")
        self.quiz_question_lbl.setText(str(q.get("question", "")))
        for i, option in enumerate(q.get("options") or []):
            btn = QPushButton(f"{chr(65 + i)}   {option}")
            btn.setProperty("softPanel", True)
            btn.clicked.connect(lambda checked=False, idx=i: self._quiz_pick(idx))
            self.quiz_options_lay.addWidget(btn)
            self._quiz_option_btns.append(btn)

    def _quiz_pick(self, index: int):
        self._quiz_selected = index
        q = self._quiz_questions[self._quiz_index]
        correct = int(q.get("correct_index", -1))
        for i, btn in enumerate(self._quiz_option_btns):
            btn.setEnabled(False)
            if i == correct:
                btn.setStyleSheet(f"background:{theme.c('green_soft')};border-color:{theme.c('green')};")
            elif i == index:
                btn.setStyleSheet(f"background:{theme.c('red_soft')};border-color:{theme.c('red')};")
        verdict = "Correct! " if index == correct else "Not quite. "
        self.quiz_answer_lbl.setText(verdict + str(q.get("explanation", "")))
        self.quiz_next_btn.setText(
            "Next" if self._quiz_index < len(self._quiz_questions) - 1 else "Restart")
        self.quiz_answer_row.setVisible(True)

    def _quiz_next(self):
        if self._quiz_index < len(self._quiz_questions) - 1:
            self._quiz_index += 1
        else:
            self._quiz_index = 0
        self._quiz_selected = None
        self._render_quiz()

    # ------------------------------------------------------------------ #
    # flashcards
    # ------------------------------------------------------------------ #
    def _render_flashcards(self):
        if not self._flashcards:
            self.flashcard_widget.set_card(None)
            self.flashcard_counter_lbl.setText("")
            return
        self._flashcard_index = max(0, min(self._flashcard_index, len(self._flashcards) - 1))
        self.flashcard_widget.set_card(self._flashcards[self._flashcard_index])
        self.flashcard_counter_lbl.setText(
            f"Card {self._flashcard_index + 1} / {len(self._flashcards)}")

    def _flashcard_next(self):
        if not self._flashcards:
            return
        self._flashcard_index = (self._flashcard_index + 1) % len(self._flashcards)
        self._render_flashcards()
