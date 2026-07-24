"""Adapter between the UI bridge and the LecturePack engine.

THIS IS THE INTEGRATION SEAM. The existing engine (transcription, slide
detection, alignment, exports, local AI) plugs in here — nothing else in
desktop/ or ui/ needs to change.

Three adapters live here:

- EngineAdapter — the interface, with docstrings describing exactly what each
  method must do and which Backend signals it must emit.
- DemoAdapter   — a self-contained simulation (same demo content as the design
  prototype) so the shell runs and every screen is exercisable before the real
  engine is wired. It doubles as living documentation of the signal payloads.
- LecturePackAdapter — drives the real `lecturepack` engine (JobController,
  transcript/study services, exports, local Ollama AI). Returned by
  make_adapter().
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QFileDialog

from .assets import asset_url, thumb_url
from .paths import data_dir
from .win_integration import WindowsIntegration


class EngineAdapter(QObject):
    """Interface the desktop shell expects. All signal emission goes through
    self.backend (a Backend instance); payloads are JSON strings."""

    def __init__(self, backend):
        super().__init__()
        self.backend = backend

    # -- lifecycle -----------------------------------------------------------
    def on_ui_ready(self):
        """Push initial state: jobs_changed, status_changed, slides_changed,
        transcript_changed, study_changed, settings_changed, ai_status."""
        raise NotImplementedError

    def on_setting_changed(self, key: str, value: str):
        """Persisted already by Backend; react if the engine cares (theme is
        UI-only, model paths and endpoints belong to the engine)."""

    # -- import / processing --------------------------------------------------
    def browse_video(self, parent) -> None:
        """Open a native file dialog; on selection call self.import_video(path)."""
        raise NotImplementedError

    def import_video(self, path: str) -> None:
        """Probe the file (resolution/duration/codec/size) and drive the UI's
        New-job overlay via status/log signals, then wait for start_processing."""
        raise NotImplementedError

    def open_job(self, job_id: str) -> None:
        """Open an existing job from the Home grid; push its review/study data."""

    def delete_job(self, job_id: str) -> None:
        """Delete a job (user-confirmed in the UI); refresh the jobs list."""

    def set_job_group(self, job_id: str, group: str) -> None:
        """Set a job's course/subject group; refresh the jobs list."""

    def notify_drag_over(self):
        """Optional: UI feedback while a file is dragged over the window."""

    def start_processing(self, mode: str) -> None:
        """Kick off the engine pipeline for the pending import. Emit
        pipeline_changed (stages/title/meta), log_line per engine log,
        status_changed for the footer, jobs_changed when the job list moves."""
        raise NotImplementedError

    def cancel_job(self) -> None:
        raise NotImplementedError

    # -- review ---------------------------------------------------------------
    def set_slide_state(self, index: int, state: str) -> None:
        """Persist accept/reject for a detected slide."""
        raise NotImplementedError

    def save_corrections(self, texts: list[str]) -> None:
        """Persist edited transcript segments for the current selection."""
        raise NotImplementedError

    def repair_selection(self) -> None:
        """Run the engine's context-repair on the selected segments."""
        raise NotImplementedError

    # -- study AI --------------------------------------------------------------
    def ask_ai(self, prompt: str) -> None:
        """Stream an answer: emit ai_token(accumulated_text) repeatedly, then
        ai_done(). Wire to the engine's local AI (Ollama endpoint) here."""
        raise NotImplementedError

    # -- exports ----------------------------------------------------------------
    def export_all(self, formats: list[str]) -> None:
        """Emit export_progress({pct,label}) during the run and
        export_done({files:[names], meta:'5 files · 42.6 MB · 3.2s'}) at the end."""
        raise NotImplementedError

    def export_one(self, kind: str) -> None:
        """kind is 'pdf' or 'html'."""
        raise NotImplementedError

    def export_folder(self) -> str | None:
        return None

    # -- misc -------------------------------------------------------------------
    def test_endpoint(self) -> None:
        """Ping the local AI endpoint; emit ai_status({label, model})."""

    def list_ollama_models(self) -> None:
        """List installed Ollama models; emit ollama_models({models, selected})."""

    def validate_vulkan(self) -> None:
        """Report compute-backend availability/selection; emit vulkan_status."""

    def validate_cuda(self) -> None:
        """Report CUDA (NVIDIA) backend availability/selection; emit cuda_status."""

    def cuda_pack_status(self) -> None:
        """Emit CUDA-pack install/availability state; emit cuda_pack."""

    def install_cuda_pack(self) -> None:
        """Download + install the optional CUDA acceleration pack into bin/cuda."""

    def cancel_cuda_pack(self) -> None:
        """Cancel an in-flight CUDA-pack download."""

    def smart_study_status(self) -> None:
        """Emit a Smart Study snapshot (presets, RAM recommendation, provider)."""

    def set_study_preset(self, preset: str) -> None:
        """Persist the chosen study model preset (Lightweight/Balanced/custom)."""

    def install_smart_study(self, preset: str) -> None:
        """Optional Smart Study setup: ensure/download + test a local model."""

    def cancel_smart_study(self) -> None:
        """Cancel an in-flight Smart Study setup."""

    def launch_ollama_installer(self) -> None:
        """Open the official Ollama installer/download page in the browser."""

    def is_processing(self) -> bool:
        """True while a lecture pipeline is running (updater install guard)."""
        return False

    def set_groq_key(self, key: str) -> None:
        """Store the Groq API key in the OS credential manager; emit groq_status."""

    def remove_groq_key(self) -> None:
        """Remove the stored Groq API key; emit groq_status."""

    def test_groq_key(self) -> None:
        """Verify the stored Groq key against the provider; emit groq_status."""

    def generate_quiz(self, opts) -> None:
        """Generate a quiz (AI or deterministic fallback); emit quiz_changed/quiz_status."""

    def cancel_quiz(self) -> None:
        """Cancel an in-flight quiz generation."""

    def save_quiz_session(self, session_json: str) -> None:
        """Persist quiz session state (answers/score/index) in study data."""

    def generate_flashcards(self, opts) -> None:
        """Generate flashcards (AI or fallback); emit flashcards_changed/status."""

    def cancel_flashcards(self) -> None:
        """Cancel an in-flight flashcard generation."""

    def save_flashcard_session(self, session_json: str) -> None:
        """Persist flashcard session state (known/unsure/index) in study data."""

    def save_notes(self, text: str) -> None:
        """Persist the user's free-text notes for the current job."""

    def browse_model(self, parent) -> None:
        """Pick a whisper model file; emit settings_changed({model_path})."""

    def save_project(self) -> None:
        """Persist current job state."""

    # -- beta.3: pause/resume/retry, queue, notifications, diagnostics -------
    def pause_job(self) -> None:
        """Cooperatively pause the active job; emit pause_state."""

    def resume_job(self, job_id: str = "") -> None:
        """Resume a paused/interrupted job from its checkpoint."""

    def retry_stage(self, job_id: str, stage: str) -> None:
        """Retry a single failed stage, preserving completed upstream work."""

    def restart_job(self, job_id: str) -> None:
        """Restart an interrupted job from the beginning."""

    def get_notification_prefs(self) -> None:
        """Emit notification_prefs with the persisted toggles."""

    def set_notification_prefs(self, prefs_json: str) -> None:
        """Persist notification toggles; apply to the notifier."""

    def test_notification(self) -> None:
        """Fire a one-off test notification."""

    def set_focused(self, focused: bool) -> None:
        """Track window focus for notification focus-gating."""

    def run_diagnostics(self, job_id: str) -> None:
        """Emit a redacted diagnostics bundle for a job (diagnostics signal)."""

    def open_job_folder(self, job_id: str) -> None:
        """Open a job's folder in the OS file browser."""

    def enqueue_job(self, job_id: str) -> None:
        """Add a job to the processing queue."""

    def reorder_queue(self, job_id: str, index: int) -> None:
        """Move a queued job to a new position."""

    def run_now(self, job_id: str) -> None:
        """Jump a queued job to the front."""

    def remove_from_queue(self, job_id: str) -> None:
        """Remove a job from the queue/schedule."""

    def schedule_job(self, job_id: str, when: str, tz: str, missed_policy: str) -> None:
        """Schedule a job to run at a local date/time."""

    def unschedule_job(self, job_id: str) -> None:
        """Remove a job's schedule."""

    def get_post_completion(self) -> None:
        """Emit the persisted post-completion behavior preference."""

    def attach_window(self, window, tray=None) -> None:
        """Give the adapter the main window + tray for OS integration."""

    def set_focused(self, focused) -> None:
        """Track window focus for notification focus-gating."""


class DemoAdapter(EngineAdapter):
    """Runs the UI with the design prototype's demo behavior. No engine needed."""

    def on_ui_ready(self):
        self.backend.settings_changed.emit(
            json.dumps({"export_dir": os.path.join("~", "LecturePackData", "…", "exports")})
        )

    def browse_video(self, parent):
        path, _ = QFileDialog.getOpenFileName(
            parent,
            "Choose a lecture video",
            os.path.expanduser("~"),
            "Video files (*.mp4 *.mkv *.mov *.m4v *.webm)",
        )
        if path:
            self.import_video(path)

    def import_video(self, path: str):
        size_mb = os.path.getsize(path) / 1e6 if os.path.exists(path) else 0
        self.backend.log_line.emit(
            json.dumps(
                {
                    "tag": "[import]",
                    "color": "var(--blue-ink)",
                    "text": f"{os.path.basename(path)} · {size_mb:.1f} MB",
                }
            )
        )

    def start_processing(self, mode: str):
        self.backend.status_changed.emit(
            json.dumps({"label": "Transcribing", "pct": 0, "detail": "0% · starting", "side": "Transcribing 0%"})
        )

    def cancel_job(self):
        self.backend.status_changed.emit(
            json.dumps({"label": "Cancelled", "pct": 0, "detail": "job cancelled"})
        )

    def set_slide_state(self, index: int, state: str):
        pass  # demo state lives in the UI

    def save_corrections(self, texts):
        self.backend.log_line.emit(
            json.dumps({"tag": "[save]", "color": "var(--green)", "text": f"{len(texts)} segments saved"})
        )

    def repair_selection(self):
        pass

    def ask_ai(self, prompt: str):
        full = (
            "Great question. Based on the transcript around 00:55, the base sits level "
            "to under two centimeters and the sides align to true north within 3/60 of "
            "a degree — remarkable precision for 2560 BC."
        )
        self._chunks = [full[:i] for i in range(2, len(full) + 2, 2)]
        self._timer = QTimer(self)
        self._timer.setInterval(22)

        def step():
            if self._chunks:
                self.backend.ai_token.emit(self._chunks.pop(0))
            else:
                self._timer.stop()
                self.backend.ai_done.emit()

        self._timer.timeout.connect(step)
        QTimer.singleShot(320, self._timer.start)

    def export_all(self, formats):
        files = ["slides.pdf", "study_pack.html"] + [f"transcript.{f.lower()}" for f in formats]
        steps = [(20, "1 of %d · rendering slides PDF"), (45, "2 of %d · building HTML pack"),
                 (70, "3 of %d · writing transcripts"), (90, "4 of %d · finishing up")]
        total = len(files)
        self._export_i = 0

        def tick():
            if self._export_i < len(steps):
                pct, label = steps[self._export_i]
                self.backend.export_progress.emit(json.dumps({"pct": pct, "label": label % total}))
                self._export_i += 1
                QTimer.singleShot(420, tick)
            else:
                self.backend.export_done.emit(
                    json.dumps({"files": files, "meta": f"{total} files · 42.6 MB · 3.2s"})
                )

        QTimer.singleShot(200, tick)

    def export_one(self, kind: str):
        self.export_all(["txt"] if kind == "pdf" else ["md"])

    def export_folder(self):
        return data_dir()


# ===========================================================================
#  Real engine adapter
# ===========================================================================

# Deferred engine imports (kept lazy so the shell can boot even if the engine
# package has an import-time problem — make_adapter() falls back to DemoAdapter).
import sys
import threading
import time

# The engine package (`lecturepack`) lives at the repository root, one level
# above app/. When run from source it is not on sys.path; add it. When frozen
# by PyInstaller the package is bundled and already importable, so this is a
# harmless no-op.
from .paths import app_root as _app_root
_repo_root = os.path.dirname(_app_root())
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from lecturepack import constants
from lecturepack.controllers.job_controller import JobController
from lecturepack.infrastructure.config_manager import ConfigManager
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.models.job import Job
from lecturepack.services import study_service, transcript_store
from lecturepack.services import study_assistant_service as sas
from lecturepack.services.export_service import ExportWorker

from . import smart_study
from . import cuda_pack


_MODE_MAP = {
    "study": constants.PRODUCT_MODE_STUDY_PACK,
    "transcript": constants.PRODUCT_MODE_TRANSCRIPT_ONLY,
    "slides": constants.PRODUCT_MODE_SLIDES_ONLY,
}

# Engine stage name -> (display label, active-bar color)
_STAGE_META = [
    (constants.STAGE_INSPECT, "Inspect", "orange"),
    (constants.STAGE_EXTRACT_AUDIO, "Extract audio", "green"),
    (constants.STAGE_TRANSCRIBE, "Transcribe", "orange"),
    (constants.STAGE_DETECT_SLIDES, "Detect slides", "blue"),
    (constants.STAGE_ALIGN, "Align", "orange"),
    (constants.STAGE_REVIEW_READY, "Review ready", "orange"),
]

_LOG_COLORS = {
    "inspect": "var(--muted)",
    "extract": "var(--green)",
    "audio": "var(--green)",
    "whisper": "var(--orange-ink)",
    "transcribe": "var(--orange-ink)",
    "t": "var(--ink)",
    "detect": "var(--blue-ink)",
    "slides": "var(--blue-ink)",
    "align": "var(--ink)",
    "export": "var(--ink)",
    "engine": "var(--blue-ink)",
    "error": "var(--red)",
}


def _fmt_hhmmss(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_mmss(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def _fmt_mmss_d(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:04.1f}"


def _human_size(num_bytes: float) -> str:
    num = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


def _esc(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _derive_group(title: str) -> str:
    """Best-effort course/subject label from a job title.

    Titles are commonly "CL100 - Day 3 - Mesopotamia" → "CL100"; otherwise the
    leading token (e.g. "PHYS101 lecture 2" → "PHYS101"). Falls back to
    "Ungrouped". Used only as the default when no explicit group is set.
    """
    t = (title or "").strip()
    if not t:
        return "Ungrouped"
    for sep in (" - ", " – ", ": ", " — "):
        if sep in t:
            head = t.split(sep, 1)[0].strip()
            if head:
                return head
    first = t.split()[0] if t.split() else ""
    return first or "Ungrouped"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# Common words filtered out of key-term-derived questions so the no-AI fallback
# doesn't build questions around filler like "one", "see", "know".
_STOPWORDS = frozenset("""
the a an and or but of to in on at for with from by as is are was were be been being
it its this that these those one two three we you they i he she him her his their our
your my me us so if then than which who what when where why how can could would should
will just also very more most some any all not no yes do does did done have has had
about into over under out up down off again more back only own same too can't don't
know way thing things lot kind sort stuff okay yeah really actually basically gonna
maybe guys right well like mean got get going want need world people time part
point today said say says lecture
""".split())


def _sentences(segments) -> list[str]:
    """Flatten transcript segments into clean sentence strings for grounding."""
    text = " ".join(str(s.get("text") or "").strip() for s in (segments or [])).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for p in parts:
        p = p.strip()
        if 25 <= len(p) <= 240:
            out.append(p)
    return out


def _clean_terms(terms) -> list[str]:
    """Drop stopwords/filler and dedupe key terms, preferring proper nouns and
    multi-word phrases (better quiz/flashcard material than bare stopwords)."""
    out, seen = [], set()
    for t in (terms or []):
        s = str(t).strip().strip("’'\"“”.,:;")
        low = s.lower()
        if not s or low in seen or low in _STOPWORDS:
            continue
        if "'" in s and len(s) < 6:            # "it's", "don't"
            continue
        if len(low) < 4 and not s[0].isupper():  # short & not a proper noun
            continue
        seen.add(low)
        out.append(s)
    return out


def _place_correct(correct, distractors, pos):
    """Interleave one correct answer among distractors at index ``pos``."""
    total = len(distractors) + 1
    pos = pos % total
    options, di = [], 0
    for p in range(total):
        if p == pos:
            options.append(correct)
        else:
            options.append(distractors[di])
            di += 1
    return options, pos


def _fallback_quiz_questions(terms, count: int, sentences=None) -> list[dict]:
    """Deterministic, no-AI quiz GROUNDED in the transcript.

    Builds cloze (fill-in-the-blank) questions from real lecture sentences: a
    sentence mentioning a key term has that term blanked out, and the options are
    the correct term plus other key terms that do NOT appear in that sentence (so
    the answer stays unambiguous). Far better than a generic "which is a key term"
    quiz. Deterministic — the correct option rotates position by index.
    """
    good = _clean_terms(terms)
    if not good:
        return []
    sentences = sentences or []
    n = max(1, int(count or 5))
    questions, used = [], set()
    pats = {t: re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in good}
    for term in good:
        if len(questions) >= n:
            break
        chosen = None
        for si, sent in enumerate(sentences):
            if si in used:
                continue
            if pats[term].search(sent):
                chosen = (si, sent)
                break
        if chosen is None:
            continue
        si, sent = chosen
        used.add(si)
        blanked = pats[term].sub("_____", sent, count=1)
        # distractors: other good terms NOT present in this sentence
        distractors = [t for t in good
                       if t.lower() != term.lower() and not pats[t].search(sent)][:3]
        if not distractors:
            continue
        options, pos = _place_correct(term, distractors, len(questions))
        questions.append({
            "question": "Fill in the blank: " + blanked,
            "options": options,
            "correct_index": pos,
            "explanation": f"From the lecture: “{sent}”",
        })
    return questions


def _normalize_quiz(questions, count: int) -> list[dict]:
    """Validate/repair LLM or fallback questions into a safe UI shape."""
    out = []
    for q in (questions or []):
        if not isinstance(q, dict):
            continue
        text = str(q.get("question") or "").strip()
        opts = [str(o) for o in (q.get("options") or []) if str(o).strip()]
        if not text or len(opts) < 2:
            continue
        try:
            ci = int(q.get("correct_index", 0))
        except (TypeError, ValueError):
            ci = 0
        ci = max(0, min(ci, len(opts) - 1))
        out.append({
            "question": text, "options": opts, "correct_index": ci,
            "explanation": str(q.get("explanation") or "").strip(),
        })
        if len(out) >= max(1, int(count or 5)):
            break
    return out


def _fallback_flashcards(terms, count: int, sentences=None) -> list[dict]:
    """Deterministic no-AI flashcards GROUNDED in the transcript: each term's
    back is the actual lecture sentence that introduces it, not a generic prompt.
    Terms with no supporting sentence are skipped."""
    good = _clean_terms(terms)
    if not good:
        return []
    sentences = sentences or []
    n = max(1, int(count or 10))
    cards = []
    for term in good:
        if len(cards) >= n:
            break
        pat = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        sent = next((s for s in sentences if pat.search(s)), "")
        if sent:
            cards.append({"term": term, "definition": f"“{sent}”"})
    return cards


def _normalize_flashcards(cards, count: int) -> list[dict]:
    out = []
    for c in (cards or []):
        if not isinstance(c, dict):
            continue
        term = str(c.get("term") or c.get("front") or c.get("q") or "").strip()
        definition = str(c.get("definition") or c.get("back") or c.get("a") or "").strip()
        if term and definition:
            out.append({"term": term, "definition": definition})
        if len(out) >= max(1, int(count or 10)):
            break
    return out


class LecturePackAdapter(EngineAdapter):
    """Drives the real LecturePack engine behind the web UI."""

    def __init__(self, backend):
        super().__init__(backend)
        self.config = ConfigManager()
        self.controller = JobController(self.config)
        # Per-launch session id: stamps ownership on active jobs so startup
        # reconciliation only reclaims dead-session jobs (see job_lifecycle).
        self._session_id = uuid.uuid4().hex
        # Windows OS integration (keep-awake / taskbar / notifications). Tray +
        # HWND are attached later by main.py via attach_window(); until then it
        # no-ops safely. Notification prefs are loaded from config.
        self.win = WindowsIntegration(prefs=self._load_notification_prefs())
        # Persistent queue / scheduler (one active job at a time).
        from lecturepack.services.job_queue import JobQueue
        self.queue = JobQueue(self.config.data_dir)
        self.current_job: Job | None = None
        self._pending_job: Job | None = None
        self._stages: list[dict] = []
        self._pipeline_start = 0.0
        self._stage_timings: dict = {}   # stage name -> {start, duration, cached}
        self._slide_frames: list[int] = []      # emit-order -> candidate frame_number
        self._review_ids: list[int] = []        # emit-order -> working segment id
        self._chat_history: list[dict] = []
        self._ai_worker = None
        self._repair_worker = None
        self._export_worker = None
        self._export_start = 0.0
        self._wire_controller()

    # ------------------------------------------------------------------ wiring
    def _wire_controller(self):
        c = self.controller
        c.stage_started.connect(self._on_stage_started)
        c.stage_progress.connect(self._on_stage_progress)
        c.stage_log.connect(self._on_stage_log)
        c.stage_finished.connect(self._on_stage_finished)
        c.stage_cached.connect(self._on_stage_cached)
        c.backend_info.connect(self._on_backend_info)
        c.transcript_segment.connect(self._on_transcript_segment)
        c.pipeline_completed.connect(self._on_pipeline_completed)
        c.pipeline_failed.connect(self._on_pipeline_failed)
        c.pause_state_changed.connect(self._on_pause_state)

    # ------------------------------------------------------------------ helpers
    def _ollama_settings(self) -> dict:
        return dict(self.config.get("ollama", {}) or {})

    def _emit(self, signal, payload):
        getattr(self.backend, signal).emit(
            payload if isinstance(payload, str) else json.dumps(payload))

    def _log(self, tag: str, text: str, key: str = ""):
        color = _LOG_COLORS.get(key or tag.strip("[]").lower(), "var(--ink)")
        for line in str(text).splitlines():
            line = line.strip()
            if line:
                self._emit("log_line", {"tag": tag, "color": color, "text": line})

    def _list_jobs(self) -> list[dict]:
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        rows = []
        if not os.path.isdir(jobs_dir):
            return rows
        entries = []
        for job_id in os.listdir(jobs_dir):
            manifest_p = os.path.join(jobs_dir, job_id, "manifest.json")
            man = FileManager.read_json_safe(manifest_p, None)
            if not isinstance(man, dict):
                continue
            state = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "state.json"), {}) or {}
            source = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "source.json"), {}) or {}
            entries.append((man.get("created_at", ""), job_id, man, state, source))
        entries.sort(reverse=True)
        from lecturepack.models import job_lifecycle as _lc
        for created_at, job_id, man, state, source in entries:
            title = man.get("title") or job_id[:8]
            filename = man.get("source", {}).get("filename", "")
            overall = state.get("overall_status", "pending")
            stages = state.get("stages", {})
            lifecycle = state.get("lifecycle") or _lc.backfill_from_overall_status(overall)
            running_stage = next(
                (name for name, sd in stages.items()
                 if sd.get("status") == "running"), None)
            group = man.get("group") or _derive_group(title)
            if lifecycle in (_lc.RUNNING, _lc.PAUSE_REQUESTED) and running_stage:
                rows.append({
                    "id": job_id, "group": group,
                    "name": title, "status": "running",
                    "stage": running_stage, "pct": 0, "eta": "",
                })
                continue
            dur = float(source.get("duration", 0.0) or 0.0)
            candidates = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "candidates.json"), []) or []
            n_slides = sum(1 for c in candidates if c.get("decision") == "accepted")
            bits = []
            if dur:
                bits.append(_fmt_mmss(dur))
            if candidates:
                bits.append(f"{n_slides} slides")
            date = (man.get("created_at", "") or "")[:10]
            if date:
                bits.append(date)
            done = (lifecycle == _lc.COMPLETED
                    or stages.get(constants.STAGE_REVIEW_READY, {}).get("status") == "completed"
                    or overall == "completed")
            # Authoritative lifecycle drives the badge; interrupted/failed jobs
            # leave the active view and surface under Needs Attention.
            status_map = {
                _lc.INTERRUPTED: "interrupted",
                _lc.FAILED: "failed",
                _lc.PAUSED: "paused",
                _lc.QUEUED: "queued",
                _lc.SCHEDULED: "scheduled",
                _lc.CANCELLED: "done",
            }
            status = status_map.get(lifecycle, "done" if done else "pending")
            rows.append({
                "id": job_id, "group": group,
                "name": title, "file": filename,
                "meta": "  ·  ".join(bits),
                "status": status,
            })
        return rows

    def _push_jobs(self):
        self._emit("jobs_changed", self._list_jobs())

    # ------------------------------------------------------------------ lifecycle
    def on_ui_ready(self):
        # Settings fields.
        self._emit("settings_changed", self._settings_payload())
        # Reconcile stale jobs from dead sessions BEFORE the first jobs push so
        # orphaned 'running' jobs surface as Interrupted, not falsely active.
        self._reconcile_jobs_on_startup()
        # Bring any due/missed schedules into the queue per their missed policy.
        try:
            self.queue.reconcile_schedules_on_launch()
        except Exception:
            pass
        self._push_jobs()
        self._probe_ollama_async()
        self.validate_vulkan()
        self.validate_cuda()
        self.cuda_pack_status()
        self._emit_groq_status()
        self.smart_study_status()
        # Show the most recent completed job's data so Review/Transcript/Study
        # aren't empty on launch.
        self._load_latest_completed_job()

    def _settings_payload(self) -> dict:
        """Current engine-config values the Settings screen reflects."""
        o = self._ollama_settings()
        return {
            "version": self._app_version(),
            "model_path": self.config.get("whisper_model", "") or "(not set)",
            "endpoint": o.get("base_url") or "http://localhost:11434",
            "engine": self.config.get("engine", "auto"),
            "ollama_model": o.get("model", ""),
            "transcription_backend": self.config.get("transcription_backend", "local-whispercpp"),
            "export_dir": self.config.data_dir,
        }

    def on_setting_changed(self, key: str, value: str):
        """Bridge UI setting changes into the engine's ConfigManager.

        The Backend persists every setting in QSettings (UI state), but the
        engine reads its own config.json — so without this bridge the compute
        engine, endpoint, model path and Ollama model chosen in Settings never
        reach processing/AI. ``theme`` is intentionally UI-only.
        """
        if key == "theme":
            return
        if key == "engine":
            engine = value if value in ("auto", "cpu", "vulkan", "cuda") else "auto"
            self.config.set("engine", engine)
            self._log("[engine]", f"compute engine set to {engine}", "engine")
            self.validate_vulkan()
            self.validate_cuda()
        elif key == "whisper_model":
            self.config.set("whisper_model", value)
        elif key == "ollama_base_url":
            o = dict(self.config.get("ollama", {}) or {})
            o["base_url"] = value
            self.config.set("ollama", o)
        elif key == "ollama_model":
            o = dict(self.config.get("ollama", {}) or {})
            o["model"] = value
            self.config.set("ollama", o)
            self._log("[ai]", f"study/repair model set to {value}", "ai")
        elif key == "transcription_backend":
            val = value if value in ("local-whispercpp", "groq-fast", "groq-accurate") \
                else "local-whispercpp"
            self.config.set("transcription_backend", val)
            self._log("[engine]", f"transcription backend set to {val}", "engine")
        # Re-emit so the UI reflects the persisted value.
        self._emit("settings_changed", self._settings_payload())

    def _app_version(self) -> str:
        try:
            from . import version
            return version.__version__
        except Exception:
            return "0.9.0-beta.1"

    def _load_latest_completed_job(self):
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        if not os.path.isdir(jobs_dir):
            return
        best = None
        for job_id in os.listdir(jobs_dir):
            state = FileManager.read_json_safe(
                os.path.join(jobs_dir, job_id, "state.json"), {}) or {}
            stages = state.get("stages", {})
            if stages.get(constants.STAGE_REVIEW_READY, {}).get("status") == "completed":
                man = FileManager.read_json_safe(
                    os.path.join(jobs_dir, job_id, "manifest.json"), {}) or {}
                key = man.get("created_at", "")
                if best is None or key > best[0]:
                    best = (key, job_id)
        if best:
            try:
                self.current_job = Job(self.config.data_dir, job_id=best[1])
                self._push_review_data()
                self._push_study_data()
            except Exception:
                self.current_job = None

    def open_job(self, job_id: str):
        """Open a completed job from the Home grid: load it and push its review /
        study data so Review/Transcript/Study reflect the selection."""
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        if not job_id or not os.path.isdir(os.path.join(jobs_dir, job_id)):
            self._log("[error]", f"job not found: {job_id}", "error")
            return
        try:
            self.current_job = Job(self.config.data_dir, job_id=job_id)
        except Exception as exc:
            self._log("[error]", f"failed to open job: {exc}", "error")
            return
        self._push_review_data()
        self._push_study_data()
        self._log("[review]", f"opened job {self.current_job.manifest.get('title', job_id)}", "detect")

    def _job_dir_guarded(self, job_id: str) -> str | None:
        """Return the absolute path of a real job dir directly under jobs/, or
        None. Rejects unsafe ids and anything resolving outside jobs/."""
        if not _SAFE_JOB_ID.match(job_id or ""):
            return None
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        job_dir = os.path.join(jobs_dir, job_id)
        if not os.path.isdir(job_dir):
            return None
        real = os.path.realpath(job_dir)
        if os.path.dirname(real) != os.path.realpath(jobs_dir):
            return None
        return real

    def _dir_size(self, path: str) -> int:
        total = 0
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total

    def delete_job(self, job_id: str) -> None:
        """Delete a job the user chose to remove (confirmed in the UI). Prefers
        the OS recycle bin (recoverable) and only hard-deletes as a fallback.
        Never called automatically — only from an explicit UI confirmation."""
        real = self._job_dir_guarded(job_id)
        if real is None:
            self._log("[error]", f"cannot delete: unknown job {job_id}", "error")
            self._emit("job_deleted", {"ok": False, "id": job_id})
            return
        freed = self._dir_size(real)
        was_current = (self.current_job is not None
                       and self.current_job.job_id == job_id)
        try:
            from send2trash import send2trash
            send2trash(real)
            method = "recycle bin"
        except Exception:
            shutil.rmtree(real, ignore_errors=False)
            method = "permanently"
        if was_current:
            self.current_job = None
        self._log("[home]", f"deleted job {job_id} → {method} "
                  f"({_human_size(freed)} freed)", "engine")
        self._emit("job_deleted", {"ok": True, "id": job_id,
                                   "freed": _human_size(freed), "method": method})
        self._push_jobs()
        if was_current:
            self._load_latest_completed_job()

    def set_job_group(self, job_id: str, group: str) -> None:
        """Set/clear a job's course/subject group (persisted in its manifest)."""
        real = self._job_dir_guarded(job_id)
        if real is None:
            self._log("[error]", f"cannot group: unknown job {job_id}", "error")
            return
        manifest_path = os.path.join(real, "manifest.json")
        man = FileManager.read_json_safe(manifest_path, None)
        if not isinstance(man, dict):
            self._log("[error]", f"cannot group: bad manifest {job_id}", "error")
            return
        group = (group or "").strip()
        if group:
            man["group"] = group
        else:
            man.pop("group", None)  # revert to derived default
        FileManager.write_json_atomic(manifest_path, man)
        if self.current_job is not None and self.current_job.job_id == job_id:
            self.current_job.manifest["group"] = group
        self._log("[home]", f"job {job_id} grouped as "
                  f"'{group or _derive_group(man.get('title', ''))}'", "engine")
        self._push_jobs()

    # ------------------------------------------------------------------ import
    def browse_video(self, parent):
        path, _ = QFileDialog.getOpenFileName(
            parent, "Choose a lecture video", os.path.expanduser("~"),
            "Video files (*.mp4 *.mkv *.mov *.m4v *.webm);;All files (*.*)")
        if path:
            self.import_video(path)

    def import_video(self, path: str):
        if not os.path.exists(path):
            return
        try:
            job = Job(self.config.data_dir, video_path=path)
            self.controller.set_job(job)
            self._pending_job = job
            self.current_job = job
            meta_str = f"{_human_size(os.path.getsize(path))}"
            try:
                self.controller.ffmpeg_wrapper.detect_binaries()
                meta = self.controller.ffmpeg_wrapper.inspect_video(path)
                job.source.update(meta)
                job.save()
                meta_str = (f"{meta['width']}×{meta['height']} · "
                            f"{_fmt_mmss(meta['duration'])} · {meta['video_codec']} · "
                            f"{_human_size(meta['size_bytes'])}")
            except Exception as exc:  # inspection is best-effort
                self._log("[inspect]", f"metadata unavailable: {exc}", "error")
            # Open the New-job overlay's "detected" step with real info.
            self._emit("onboarding", {
                "name": os.path.basename(path), "meta": meta_str})
        except Exception as exc:
            self._log("[import]", f"failed to open video: {exc}", "error")

    def start_processing(self, mode: str):
        job = self._pending_job or self.current_job
        if job is None:
            self._log("[error]", "No video selected.", "error")
            return
        # One active job: if a pipeline is already running a DIFFERENT job, queue
        # this one (FIFO) instead of starting a second. It runs when the active
        # job finishes (see _promote_next).
        if self.is_processing() and (self.current_job is None
                                     or self.current_job.job_id != job.job_id):
            from lecturepack.models import job_lifecycle as _lc
            try:
                if job.get_lifecycle() != _lc.QUEUED:
                    job.set_lifecycle(_lc.QUEUED)
            except _lc.IllegalTransition:
                pass
            job.settings["product_mode"] = _MODE_MAP.get(
                mode, constants.PRODUCT_MODE_STUDY_PACK)
            job.save()
            self.queue.enqueue(job.job_id)
            self._pending_job = None
            self._push_queue()
            self._push_jobs()
            self._log("[engine]", "Another job is running — queued behind it.", "engine")
            return
        product_mode = _MODE_MAP.get(mode, constants.PRODUCT_MODE_STUDY_PACK)
        job.settings["product_mode"] = product_mode
        w_model = self.config.get("whisper_model", "")
        if w_model:
            job.settings.setdefault("whisper", {})["model"] = w_model
        # Apply the compute-engine choice (cpu/vulkan/auto) so a Vulkan
        # selection in Settings actually reaches the transcription backend.
        job.settings.setdefault("whisper", {})["engine"] = \
            self.config.get("engine", "auto")
        # Apply the transcription backend (Private Local / Online Fast|Accurate).
        job.settings.setdefault("whisper", {})["transcription_backend"] = \
            self.config.get("transcription_backend", "local-whispercpp")
        job.save()
        self.current_job = job

        # Validate whisper availability for modes that need it.
        needs_whisper = product_mode != constants.PRODUCT_MODE_SLIDES_ONLY
        w_exe = self.config.get("whisper_exe", "")
        if needs_whisper and (not w_exe or not os.path.exists(w_exe)
                              or not w_model or not os.path.exists(w_model)):
            self._emit("status_changed", {
                "label": "Setup needed", "pct": 0,
                "detail": "configure Whisper in Settings"})
            self._log("[error]",
                      "Whisper executable/model not configured — set them in "
                      "Settings before processing (or choose Slides Only).", "error")
            return

        # Fresh pipeline model.
        skipped = constants.__dict__.get("STAGES_SKIPPED_BY_MODE", {})
        self._stages = []
        for name, label, color in _STAGE_META:
            self._stages.append({
                "name": name, "label": label, "color": color,
                "state": "pending", "pct": 0})
        self._pipeline_start = time.time()
        self._emit("status_changed", {"job": job.manifest.get("title", "Job")})
        self._render_pipeline(title="Starting…", meta="preparing")
        self._log("[engine]", f"Product mode: "
                  f"{constants.PRODUCT_MODE_LABELS.get(product_mode, product_mode)}",
                  "engine")
        # Claim the active slot + stamp session ownership; acquire keep-awake and
        # show taskbar progress for the duration of the run.
        from lecturepack.models import job_lifecycle as _lc
        try:
            if job.get_lifecycle() in (_lc.NEW, _lc.QUEUED, _lc.PAUSED,
                                       _lc.INTERRUPTED, _lc.FAILED):
                if job.get_lifecycle() != _lc.QUEUED:
                    # NEW/PAUSED/INTERRUPTED/FAILED -> QUEUED -> RUNNING
                    _to_queued = {_lc.NEW, _lc.PAUSED, _lc.FAILED, _lc.INTERRUPTED}
                    if job.get_lifecycle() in _to_queued:
                        job.set_lifecycle(_lc.QUEUED)
                owner = _lc.SessionOwner(session_id=self._session_id,
                                         process_id=os.getpid())
                job.set_lifecycle(_lc.RUNNING, owner=owner)
        except _lc.IllegalTransition:
            pass  # best-effort; overall_status still tracks progress
        self.win.on_job_started()
        self.controller.run_pipeline()

    def cancel_job(self):
        try:
            self.controller.cancel()
        finally:
            self.win.on_cancelled()
            self._promote_next()
            self._emit("status_changed", {
                "label": "Cancelled", "pct": 0, "detail": "job cancelled"})
            self._log("[engine]", "Pipeline cancelled by user.", "engine")

    # ------------------------------------------------------------------ pipeline render
    def _stage_by_name(self, name: str) -> dict | None:
        return next((s for s in self._stages if s["name"] == name), None)

    def _render_pipeline(self, title=None, meta=None):
        elapsed = time.time() - self._pipeline_start if self._pipeline_start else 0
        done = sum(1 for s in self._stages if s["state"] == "done")
        total = len(self._stages) or 1
        overall = int(done / total * 100)
        if title is None:
            active = next((s for s in self._stages if s["state"] == "active"), None)
            title = f"{active['label']}…" if active else "Processing…"
        if meta is None:
            meta = f"elapsed {_fmt_mmss(elapsed)} · {overall}%"
        stages = [{"label": s["label"], "state": s["state"],
                   **({"pct": s["pct"], "color": s["color"]}
                      if s["state"] == "active" else {})}
                  for s in self._stages]
        self._emit("pipeline_changed", {"title": title, "meta": meta, "stages": stages})

    def _on_stage_started(self, name: str):
        self._stage_timings[name] = {"start": time.time(), "cached": False}
        s = self._stage_by_name(name)
        if s:
            s["state"] = "active"
            s["pct"] = 0
        self._render_pipeline()
        self._emit("status_changed", {
            "label": s["label"] if s else name, "pct": 0,
            "detail": f"0% · {s['label'] if s else name}",
            "side": f"{s['label'] if s else name} 0%"})

    def _on_stage_progress(self, name: str, pct: int):
        s = self._stage_by_name(name)
        if s:
            s["state"] = "active"
            s["pct"] = int(pct)
        # Reflect overall pipeline progress on the taskbar button.
        done = sum(1 for st in self._stages if st["state"] == "done")
        total = len(self._stages) or 1
        self.win.on_progress(int((done + int(pct) / 100.0) / total * 100))
        self._render_pipeline()
        label = s["label"] if s else name
        self._emit("status_changed", {
            "label": label, "pct": int(pct),
            "detail": f"{int(pct)}% · {label}", "side": f"{label} {int(pct)}%"})

    def _on_stage_log(self, name: str, text: str):
        key = name.split()[0].lower()
        self._log(f"[{key}]", text, key)

    def _on_stage_finished(self, name: str, success: bool, error: str):
        t = self._stage_timings.get(name)
        if t and "start" in t:
            t["duration"] = round(time.time() - t["start"], 2)
        s = self._stage_by_name(name)
        if s:
            s["state"] = "done" if success else "pending"
            s["pct"] = 100 if success else s["pct"]
        self._render_pipeline()
        if not success and error:
            self._log("[error]", f"{name}: {error}", "error")

    def _on_stage_cached(self, name: str):
        self._stage_timings[name] = {"duration": 0.0, "cached": True}
        s = self._stage_by_name(name)
        if s:
            s["state"] = "done"
            s["pct"] = 100
        self._render_pipeline()
        self._log(f"[{name.split()[0].lower()}]", "cached — skipped", name.split()[0].lower())

    def _on_backend_info(self, text: str):
        self._log("[engine]", text, "engine")
        # Surface the ACTUAL loaded backend (not the requested one) in the UI.
        self._emit("settings_changed", {"actual_backend": text})

    def _on_transcript_segment(self, seg: dict):
        t0 = _fmt_hhmmss(seg.get("start_ms", 0) / 1000.0)
        t1 = _fmt_hhmmss(seg.get("end_ms", 0) / 1000.0)
        self._log("[t]", f"{t0} → {t1}  {seg.get('text', '').strip()}", "t")

    def _on_pipeline_completed(self):
        for s in self._stages:
            s["state"] = "done"
            s["pct"] = 100
        self._render_pipeline(title="Complete", meta="pipeline finished")
        self._emit("status_changed", {
            "label": "Done", "pct": 100, "detail": "processing complete", "side": "Done"})
        self._log("[engine]", "Pipeline complete.", "engine")
        self._write_performance_report()
        # Lifecycle -> completed; release keep-awake, clear taskbar, notify.
        job = self.current_job
        if job is not None:
            from lecturepack.models import job_lifecycle as _lc
            try:
                job.set_lifecycle(_lc.COMPLETED)
            except _lc.IllegalTransition:
                pass
            self.win.on_completed(job.job_id, job.manifest.get("title", ""))
            self._emit("job_completed", self._completion_payload(job))
        else:
            self.win.on_idle()
        self._push_jobs()
        self._push_review_data()
        self._push_study_data()
        self._promote_next()

    def _write_performance_report(self):
        """Persist a per-stage timing profile for the just-finished run so the
        pipeline is measurable (§4). Written to <job>/performance.json."""
        job = self.current_job
        if job is None:
            return
        total = round(time.time() - self._pipeline_start, 2) if self._pipeline_start else 0.0
        stages = []
        for st in self._stages:
            t = self._stage_timings.get(st["name"], {})
            stages.append({"stage": st["name"],
                           "duration_seconds": t.get("duration", 0.0),
                           "cached": bool(t.get("cached", False))})
        src = job.source or {}
        duration = float(src.get("duration", 0.0) or 0.0)
        report = {
            "job_id": job.job_id,
            "title": job.manifest.get("title", ""),
            "source_duration_seconds": duration,
            "source_resolution": (f"{src.get('width')}x{src.get('height')}"
                                  if src.get("width") else ""),
            "engine_requested": self.config.get("engine", "auto"),
            "parallel_pipeline": bool(self.config.get("parallel_pipeline", True)),
            "total_wall_seconds": total,
            "realtime_factor": (round(duration / total, 2) if total else None),
            "stages": stages,
            "generated_at": _now_iso(),
        }
        try:
            FileManager.write_json_atomic(
                os.path.join(job.paths["root"], "performance.json"), report)
            self._log("[engine]", f"profile: {total:.1f}s wall "
                      f"({report['realtime_factor']}x realtime) → performance.json", "engine")
        except OSError as exc:
            self._log("[engine]", f"could not write performance.json: {exc}", "error")

    def _on_pipeline_failed(self, msg: str):
        self._emit("status_changed", {
            "label": "Failed", "pct": 0, "detail": msg[:80]})
        self._log("[error]", f"Pipeline failed: {msg}", "error")
        job = self.current_job
        if job is not None:
            from lecturepack.models import job_lifecycle as _lc
            try:
                job.set_lifecycle(_lc.FAILED)
            except _lc.IllegalTransition:
                pass
            self.win.on_failed(job.job_id, msg[:200])
        else:
            self.win.on_idle()
        self._push_jobs()
        self._promote_next()

    def _on_pause_state(self, state: str):
        """Relay controller pause transitions to the UI and OS integration."""
        if state == "pause_requested":
            self.win.on_pause_requested()
        elif state == "paused":
            self.win.on_paused()
            job = self.current_job
            if job is not None:
                from lecturepack.models import job_lifecycle as _lc
                for edge in ((_lc.RUNNING, _lc.PAUSE_REQUESTED),
                             (_lc.PAUSE_REQUESTED, _lc.PAUSED)):
                    try:
                        if job.get_lifecycle() == edge[0]:
                            job.set_lifecycle(edge[1])
                    except _lc.IllegalTransition:
                        pass
            self._push_jobs()
        self._emit("pause_state", {"state": state})

    # ------------------------------------------------------------------ beta.3 job control
    def attach_window(self, window, tray=None):
        """Called by main.py once the QMainWindow + tray exist: give the OS
        integration its tray (notifications) and HWND (taskbar), and route
        notification clicks + focus changes."""
        try:
            hwnd = int(window.winId()) if window is not None else None
        except Exception:
            hwnd = None
        self.win.notifier._tray = tray
        self.win.taskbar._hwnd = hwnd

    def pause_job(self):
        if self.controller.request_pause():
            self._log("[engine]", "Pause requested — finishing current step.", "engine")

    def resume_job(self, job_id: str = ""):
        job = self.current_job
        if job_id:
            job = self._reload_job(job_id) or job
        if job is None:
            return
        self.current_job = job
        self.controller.set_job(job)
        from lecturepack.models import job_lifecycle as _lc
        try:
            if job.get_lifecycle() in (_lc.PAUSED, _lc.INTERRUPTED):
                job.set_lifecycle(_lc.QUEUED)
            job.set_lifecycle(_lc.RUNNING, owner=_lc.SessionOwner(
                session_id=self._session_id, process_id=os.getpid()))
        except _lc.IllegalTransition:
            pass
        self.win.on_job_started()
        self.controller.resume()

    def restart_job(self, job_id: str):
        job = self._reload_job(job_id)
        if job is None:
            return
        for stage in constants.STAGES:
            job.set_stage_status(stage, "pending")
        self.current_job = self._pending_job = job
        self.start_processing(self._mode_for_job(job))

    def retry_stage(self, job_id: str, stage: str):
        job = self.current_job
        if job_id and (not job or job.job_id != job_id):
            job = self._reload_job(job_id) or job
        if job is None:
            return
        self.current_job = job
        self.controller.set_job(job)
        self.win.on_job_started()
        self.controller.retry_stage(stage)

    # -- notifications -------------------------------------------------------
    def _load_notification_prefs(self) -> dict:
        raw = self.config.get("notifications", None)
        return dict(raw) if isinstance(raw, dict) else {}

    def get_notification_prefs(self):
        self._emit("notification_prefs", dict(self.win.prefs))

    def set_notification_prefs(self, prefs_json: str):
        try:
            prefs = json.loads(prefs_json) if isinstance(prefs_json, str) else dict(prefs_json)
        except (ValueError, TypeError):
            prefs = {}
        self.win.set_prefs(prefs)
        self.config.set("notifications", dict(self.win.prefs))
        self._emit("notification_prefs", dict(self.win.prefs))

    def test_notification(self):
        self.win.test_notification()

    def set_focused(self, focused):
        self.win.set_focused(bool(focused))

    # -- diagnostics / folders ----------------------------------------------
    def run_diagnostics(self, job_id: str):
        from lecturepack.services.job_ops import build_diagnostics
        job = self._reload_job(job_id) or self.current_job
        state = job.state if job is not None else {}
        stages = state.get("stages", {}) if isinstance(state, dict) else {}
        failed = next((n for n, sd in stages.items()
                       if sd.get("status") in ("failed", "interrupted")), "")
        err = stages.get(failed, {}).get("error", "") if failed else ""
        diag = build_diagnostics(
            app_version=self._app_version(),
            job_id=job_id,
            stage=failed,
            status=state.get("lifecycle", state.get("overall_status", "")) if isinstance(state, dict) else "",
            error=err,
            exit_code=None,
            timestamp=state.get("last_updated", "") if isinstance(state, dict) else "",
            runtime_paths={
                "whisper_exe": self.config.get("whisper_exe", ""),
                "ffmpeg": getattr(self.controller.ffmpeg_wrapper, "ffmpeg_path", ""),
                "data_dir": self.config.data_dir,
            })
        self._emit("diagnostics", diag)

    def open_job_folder(self, job_id: str):
        root = os.path.join(self.config.data_dir, "jobs", job_id)
        if not os.path.isdir(root):
            return
        if os.name == "nt":
            os.startfile(root)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", root])  # noqa: S603,S607

    # -- queue / scheduling --------------------------------------------------
    def enqueue_job(self, job_id: str):
        self.queue.enqueue(job_id)
        self._push_queue()

    def reorder_queue(self, job_id: str, index: int):
        self.queue.reorder(job_id, int(index))
        self._push_queue()

    def run_now(self, job_id: str):
        self.queue.run_now(job_id)
        self._push_queue()

    def remove_from_queue(self, job_id: str):
        self.queue.remove(job_id)
        self._push_queue()

    def schedule_job(self, job_id: str, when: str, tz: str, missed_policy: str):
        self.queue.schedule(job_id, when, tz or "local", missed_policy or "run_when_opened")
        self._push_queue()

    def unschedule_job(self, job_id: str):
        self.queue.unschedule(job_id)
        self._push_queue()

    def get_post_completion(self):
        from lecturepack.services.job_ops import POST_COMPLETION_DEFAULT
        self._emit("post_completion", {
            "value": self.config.get("post_completion_behavior", POST_COMPLETION_DEFAULT)})

    def _push_queue(self):
        rows = []
        for pos, jid in enumerate(self.queue.queued()):
            rows.append({"id": jid, "position": pos})
        self._emit("queue_changed", {
            "active": self.queue.active, "queue": rows,
            "schedules": self.queue.schedules()})

    def _promote_next(self):
        """Release the active slot when a job ends and launch the next queued job
        (FIFO), preserving the one-active-job invariant."""
        if self.current_job is not None:
            self.queue.finish_active(self.current_job.job_id)
        nxt = self.queue.promote_next()
        self._push_queue()
        if not nxt:
            return
        job = self._reload_job(nxt)
        if job is None:
            return
        # Defer so the just-finished pipeline fully unwinds before the next one
        # starts on the Qt event loop.
        def _go():
            self._pending_job = job
            self.current_job = job
            self.start_processing(self._mode_for_job(job))
        QTimer.singleShot(0, _go)

    def _completion_payload(self, job) -> dict:
        from lecturepack.services.job_ops import completion_metrics
        segments = FileManager.read_json_safe(
            os.path.join(job.paths.get("transcript", ""), "raw.json"), []) or []
        if isinstance(segments, dict):
            segments = segments.get("segments", []) or []
        candidates = FileManager.read_json_safe(
            os.path.join(job.paths.get("root", ""), "candidates.json"), []) or []
        n_slides = sum(1 for c in candidates if c.get("decision") == "accepted")
        m = completion_metrics(
            segments=segments, slides_detected=n_slides,
            started_iso=job.manifest.get("created_at", ""),
            finished_iso=job.state.get("last_updated", ""),
            study_state="ready" if job.get_stage_status(constants.STAGE_REVIEW_READY) == "completed" else "none",
            export_state="none")
        m["job_id"] = job.job_id
        m["title"] = job.manifest.get("title", "")
        return m

    def _reload_job(self, job_id: str):
        try:
            return Job(self.config.data_dir, job_id=job_id,
                       current_session_id=self._session_id)
        except Exception:
            return None

    def _reconcile_jobs_on_startup(self):
        """Sweep every persisted job through session-aware reconciliation so a
        job left 'running'/'pause_requested' by a dead session becomes
        'interrupted' (artifacts preserved) and stops showing as active. Loading
        each Job with the current session id triggers reconcile_on_load, which
        persists the corrected lifecycle. Never deletes or restarts anything."""
        jobs_dir = os.path.join(self.config.data_dir, "jobs")
        if not os.path.isdir(jobs_dir):
            return
        for job_id in os.listdir(jobs_dir):
            if not os.path.isfile(os.path.join(jobs_dir, job_id, "state.json")):
                continue
            self._reload_job(job_id)  # side effect: reconcile + persist

    def _mode_for_job(self, job) -> str:
        pm = job.settings.get("product_mode", constants.PRODUCT_MODE_STUDY_PACK)
        for ui_mode, mapped in _MODE_MAP.items():
            if mapped == pm:
                return ui_mode
        return "study"

    # ------------------------------------------------------------------ review data
    def _push_review_data(self):
        job = self.current_job
        if job is None:
            return
        duration = float(job.source.get("duration", 0.0) or 0.0)
        candidates = FileManager.read_json_safe(
            os.path.join(job.paths["root"], "candidates.json"), []) or []
        candidates = sorted(candidates, key=lambda c: float(c.get("timestamp_seconds", 0.0)))
        slides, self._slide_frames = [], []
        for c in candidates:
            ts = float(c.get("timestamp_seconds", 0.0))
            pct = (ts / duration * 100.0) if duration else 0.0
            img_name = c.get("image_filename") or ""
            slides.append({
                "pct": round(pct, 2),
                "time": _fmt_hhmmss(ts),
                "state": "accepted" if c.get("decision") == "accepted" else "rejected",
                "frame": c.get("frame_number"),
                # img = full-resolution (preview/export); thumb = cached downscale (list/grid)
                "img": asset_url(job.job_id, img_name) if img_name else "",
                "thumb": thumb_url(job.job_id, img_name) if img_name else "",
            })
            self._slide_frames.append(c.get("frame_number"))
        if slides:
            self._emit("slides_changed", {
                "slides": slides,
                "duration": _fmt_mmss(duration),
                "durationMid": _fmt_mmss(duration / 2.0)})

        # Transcript segments -> review rows + magazine blocks.
        segments = transcript_store.load_working(job.paths)
        self._review_ids = [s.get("id") for s in segments]
        review_segments = [{
            "t": _fmt_mmss_d(s.get("start", 0.0)),
            "text": s.get("text", ""),
        } for s in segments]
        corrections = sum(1 for s in segments if s.get("edited"))

        blocks, cur, cur_t, cur_len = [], [], None, 0
        for s in segments:
            if cur_t is None:
                cur_t = _fmt_mmss(s.get("start", 0.0))
            cur.append(_esc(s.get("text", "")))
            cur_len += len(s.get("text", ""))
            if cur_len >= 320:
                blocks.append({"t": cur_t, "html": " ".join(cur)})
                cur, cur_t, cur_len = [], None, 0
        if cur:
            blocks.append({"t": cur_t or "00:00", "html": " ".join(cur)})

        self._emit("transcript_changed", {
            "reviewSegments": review_segments or [{"t": "00:00.0", "text": "(no transcript)"}],
            "transcript": {
                "title": job.manifest.get("title", "Transcript"),
                "duration": _fmt_mmss(duration),
                "segments": len(segments),
                "corrections": corrections,
                "blocks": blocks or [{"t": "00:00", "html": "(no transcript yet)"}],
            }})

    def set_slide_state(self, index: int, state: str):
        job = self.current_job
        if job is None or index < 0 or index >= len(self._slide_frames):
            return
        frame = self._slide_frames[index]
        path = os.path.join(job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(path, []) or []
        for c in candidates:
            if c.get("frame_number") == frame:
                c["decision"] = "accepted" if state == "accepted" else "rejected"
                break
        FileManager.write_json_atomic(path, candidates)
        self._log("[review]", f"slide @ frame {frame} → {state}", "detect")

    def save_corrections(self, texts: list[str]):
        job = self.current_job
        if job is None:
            return
        segments = transcript_store.load_working(job.paths)
        by_id = {s.get("id"): s for s in segments}
        changed = 0
        for seg_id, text in zip(self._review_ids, texts):
            seg = by_id.get(seg_id)
            if seg is not None and seg.get("text", "") != text:
                seg["text"] = text
                seg["edited"] = True
                changed += 1
        transcript_store.save_working(job.paths, segments)
        self._log("[save]", f"{changed} segment(s) saved", "extract")
        self._push_review_data()

    def repair_selection(self):
        job = self.current_job
        if job is None:
            return
        o = self._ollama_settings()
        if not (o.get("enabled") and o.get("model")):
            self._log("[repair]", "Local AI is off — enable Ollama in Settings to "
                      "run context repair.", "error")
            return
        norm = FileManager.read_json_safe(
            os.path.join(job.paths["transcript"], "normalized.json"), None)
        if not norm:
            self._log("[repair]", "No normalized transcript to repair yet.", "error")
            return
        try:
            from lecturepack.services.ai_repair_service import AiRepairWorker
        except Exception as exc:
            self._log("[repair]", f"repair unavailable: {exc}", "error")
            return
        self._log("[repair]", "Running context repair…", "align")
        worker = AiRepairWorker(
            job.paths["transcript"], approved_names=[], norm_dict=norm,
            ollama_settings=o, course_title=job.manifest.get("title", ""))
        self._repair_worker = worker

        def ok(payload):
            n = len(payload.get("corrections", []) if isinstance(payload, dict) else [])
            self._log("[repair]", f"{n} correction proposal(s) generated.", "align")

        def fail(kind, message, details):
            self._log("[repair]", f"{message}", "error")

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()

    # ------------------------------------------------------------------ study
    def _push_study_data(self):
        job = self.current_job
        if job is None:
            return
        try:
            overview = study_service.build_overview(job)
        except Exception as exc:
            self._log("[study]", f"overview unavailable: {exc}", "error")
            return
        duration = float(overview.get("duration_seconds", 0.0) or 0.0)
        sections = overview.get("sections", []) or []

        topics, topic_blocks, topic_labels = [], [], []
        for i, sec in enumerate(sections):
            start = float(sec.get("start", 0.0) or 0.0)
            nxt = (float(sections[i + 1].get("start", duration) or duration)
                   if i + 1 < len(sections) else duration)
            heading = sec.get("heading", f"Section {i + 1}")
            topics.append({"t": _fmt_mmss(start), "title": heading, "active": i == 0})
            if duration:
                left = max(0.0, start / duration * 100.0)
                width = max(3.0, (nxt - start) / duration * 100.0)
                topic_blocks.append({"left": round(left, 1), "width": round(width, 1),
                                     "active": i == 0})
            short = heading.split(" ")
            topic_labels.append(" ".join(short[:2]))

        bookmarks = []
        for entry in (overview.get("bookmarked_slides", {}) or {}).values():
            if entry.get("bookmarked"):
                bookmarks.append({
                    "t": entry.get("timestamp_formatted", ""),
                    "text": entry.get("note") or "Bookmarked slide",
                    "color": "var(--orange)"})
        for entry in (overview.get("bookmarked_sections", {}) or {}).values():
            bookmarks.append({
                "t": _fmt_hhmmss(float(entry.get("start", 0.0) or 0.0)),
                "text": entry.get("heading") or "Bookmarked section",
                "color": "var(--blue)"})

        stats = [
            ["Slides", f"{overview.get('accepted_slide_count', 0)} kept"],
            ["Segments", str(overview.get("transcript_segment_count", 0))],
            ["Needs review", str(overview.get("needs_review_count", 0))],
        ]

        cards = []
        for card in (study_service.load_flashcards(job).get("cards") or []):
            term = card.get("term") or card.get("front") or card.get("q") or ""
            definition = card.get("definition") or card.get("back") or card.get("a") or ""
            if term or definition:
                cards.append({"q": term, "a": definition})
        if not cards:
            terms = overview.get("key_terms", []) or []
            if terms:
                cards = [{"q": "Key terms in this lecture",
                          "a": ", ".join(terms[:8])}]
            else:
                cards = [{"q": "No flashcards yet",
                          "a": "Open the AI assistant tab and generate flashcards "
                               "from this lecture."}]

        self._emit("study_changed", {
            "topics": topics or [{"t": "00:00", "title": "Lecture", "active": True}],
            "topicBlocks": topic_blocks or [{"left": 0.5, "width": 99, "active": True}],
            "topicLabels": topic_labels or ["Lecture"],
            "keyTerms": overview.get("key_terms", []) or [],
            "bookmarks": bookmarks,
            "stats": stats,
            "cards": cards,
            "notes": study_service.load_study_data(job).get("notes", "") or ""})

        # Restore a previously generated quiz / flashcards (+ session) for this job.
        self._emit_stored_quiz(job)
        self._emit_stored_flashcards(job)

    def save_notes(self, text: str):
        job = self.current_job
        if job is None:
            return
        data = study_service.load_study_data(job)
        data["notes"] = str(text or "")[:20000]
        study_service.save_study_data(job, data)

    def ask_ai(self, prompt: str):
        job = self.current_job
        o = self._ollama_settings()
        local_ready = bool(o.get("enabled") and o.get("model"))
        if job is None:
            self._emit("ai_token", "Open or process a lecture first, then ask away.")
            self.backend.ai_done.emit()
            return
        segments = transcript_store.load_working(job.paths) or []
        if not local_ready:
            # Built-in Study: with no local model, answer extractively from the
            # lecture transcript (source-linked recall) so Ask is never a dead
            # control (§8/§12 — lecture-only, cites timestamps).
            answer = self._builtin_answer(prompt, segments)
            self._chat_history.append({"role": "user", "text": prompt})
            self._chat_history.append({"role": "assistant", "text": answer})
            self._emit("ai_token", answer)
            self.backend.ai_done.emit()
            self._emit("ai_status", {"label": smart_study.PROVIDER_BUILTIN, "model": ""})
            try:
                study_service.append_chat_message(job, "user", prompt)
                study_service.append_chat_message(job, "assistant", answer)
            except Exception:
                pass
            return
        transcript_text = sas.transcript_context(segments)
        self._emit("ai_status", {"label": "Thinking…", "model": o.get("model")})
        worker = sas.StudyAssistantWorker(
            "chat", transcript_text, o,
            history=list(self._chat_history), question=prompt, count=5)
        self._ai_worker = worker
        self._chat_history.append({"role": "user", "text": prompt})

        def ok(task, result):
            answer = (result or {}).get("answer", "") if isinstance(result, dict) else ""
            answer = answer or "I couldn't find an answer in the transcript."
            self._chat_history.append({"role": "assistant", "text": answer})
            self._emit("ai_token", answer)
            self.backend.ai_done.emit()
            self._emit("ai_status", {"label": smart_study.PROVIDER_LOCAL, "model": o.get("model")})
            if job is not None:
                try:
                    study_service.append_chat_message(job, "user", prompt)
                    study_service.append_chat_message(job, "assistant", answer)
                except Exception:
                    pass

        def fail(kind, message, details):
            self._emit("ai_token", f"⚠ {message}")
            self.backend.ai_done.emit()
            self._emit("ai_status", {"label": "AI error", "model": o.get("model")})

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()

    _BUILTIN_STOPWORDS = frozenset(
        "the a an and or of to in on for with is are was were be been being this that "
        "these those it its as at by from what which who whom how why when where does do "
        "did can could should would will about into over under than then them they you "
        "your our his her their my me we he she i".split())

    def _builtin_answer(self, prompt: str, segments: list) -> str:
        """Extractive, lecture-only answer used when no local AI model is set.

        Scores transcript segments by keyword overlap with the question and
        returns the best-matching timestamped snippets (source-linked recall),
        clearly labelled as Built-in Study rather than posing as generated text.
        """
        terms = [w for w in re.findall(r"[a-z0-9]{3,}", (prompt or "").lower())
                 if w not in self._BUILTIN_STOPWORDS]
        scored = []
        for s in segments:
            text = str(s.get("text") or "").strip()
            if not text:
                continue
            low = text.lower()
            score = sum(low.count(t) for t in terms) if terms else 0
            if score > 0:
                scored.append((score, float(s.get("start", 0.0) or 0.0), text))
        scored.sort(key=lambda x: (-x[0], x[1]))
        top = scored[:3]
        if not top:
            return ("Built-in Study couldn't find that in this lecture's transcript. "
                    "Try different keywords, or set up Smart Study in Settings for "
                    "conversational answers.")
        lines = [f"• [{_fmt_mmss(start)}] {text}" for _score, start, text in top]
        return ("Built-in Study — from the lecture transcript:\n\n"
                + "\n\n".join(lines)
                + "\n\nSet up Smart Study in Settings for conversational, "
                  "AI-written answers.")

    # ------------------------------------------------------------------ quiz
    def _save_quiz(self, job, questions, meta, provider, model, reset_session=True):
        data = study_service.load_study_data(job)
        prev = data.get("quiz") if isinstance(data.get("quiz"), dict) else {}
        data["quiz"] = {
            "questions": questions,
            "meta": {**meta, "provider": provider, "model": model},
            "session": {} if reset_session else (prev.get("session") or {}),
            "updated_at": _now_iso(),
        }
        study_service.save_study_data(job, data)

    def _emit_stored_quiz(self, job):
        q = study_service.load_study_data(job).get("quiz") or {}
        if q.get("questions"):
            m = q.get("meta", {}) or {}
            self._emit("quiz_changed", {
                "questions": q["questions"], "provider": m.get("provider", ""),
                "model": m.get("model", ""), "meta": m,
                "session": q.get("session") or None})

    def generate_quiz(self, opts):
        job = self.current_job
        if job is None:
            self._emit("quiz_status", {"state": "error",
                       "message": "Open or process a lecture first."})
            return
        if isinstance(opts, str):
            try:
                opts = json.loads(opts or "{}")
            except ValueError:
                opts = {}
        count = max(1, min(int(opts.get("count") or 5), 50))
        meta = {"count": count, "difficulty": opts.get("difficulty", "Mixed"),
                "type": opts.get("type", "multiple choice"),
                "scope": opts.get("scope", "entire lecture"),
                "source": opts.get("source", "transcript")}
        o = self._ollama_settings()
        self._emit("quiz_status", {"state": "generating", "message": "Generating quiz…"})

        def deliver(questions, provider, model=""):
            questions = _normalize_quiz(questions, count)
            if not questions:
                self._emit("quiz_status", {"state": "error",
                           "message": "Couldn't build a quiz for this lecture."})
                return
            self._save_quiz(job, questions, meta, provider, model)
            self._emit("quiz_changed", {"questions": questions, "provider": provider,
                       "model": model, "meta": {**meta, "provider": provider, "model": model},
                       "session": None})
            self._emit("quiz_status", {"state": "ready",
                       "message": f"{len(questions)} questions · {provider}"})

        segments = transcript_store.load_working(job.paths) or []

        def do_fallback():
            try:
                terms = study_service.build_overview(job).get("key_terms", []) or []
            except Exception:
                terms = []
            deliver(_fallback_quiz_questions(terms, count, _sentences(segments)),
                    smart_study.PROVIDER_BUILTIN)

        if not (o.get("enabled") and o.get("model")):
            do_fallback()
            return

        transcript_text = sas.transcript_context(segments)
        worker = sas.StudyAssistantWorker("quiz", transcript_text, o, count=count,
                                          difficulty=meta["difficulty"], qtype=meta["type"])
        self._quiz_worker = worker

        def ok(task, result):
            qs = (result or {}).get("questions") if isinstance(result, dict) else None
            if qs:
                deliver(qs, smart_study.PROVIDER_LOCAL, o.get("model", ""))
            else:
                do_fallback()

        def fail(kind, message, details):
            self._log("[ai]", f"quiz gen failed ({kind}) — using built-in fallback", "ai")
            do_fallback()

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()

    def cancel_quiz(self):
        w = getattr(self, "_quiz_worker", None)
        if w is not None:
            try:
                w.detach_and_stop()
            except Exception:
                pass
        self._emit("quiz_status", {"state": "cancelled", "message": "Generation cancelled."})

    def save_quiz_session(self, session_json):
        job = self.current_job
        if job is None:
            return
        try:
            session = json.loads(session_json)
        except ValueError:
            return
        data = study_service.load_study_data(job)
        q = data.get("quiz") if isinstance(data.get("quiz"), dict) else {}
        q["session"] = session
        data["quiz"] = q
        study_service.save_study_data(job, data)

    # ------------------------------------------------------------------ flashcards
    def _save_flashcards(self, job, cards, meta, provider, model):
        data = study_service.load_study_data(job)
        data["flashcards"] = {
            "cards": cards,
            "meta": {**meta, "provider": provider, "model": model},
            "session": {},
            "updated_at": _now_iso(),
        }
        study_service.save_study_data(job, data)

    def _emit_stored_flashcards(self, job):
        f = study_service.load_study_data(job).get("flashcards") or {}
        cards = f.get("cards") or []
        if cards and all(isinstance(c, dict) and (c.get("term") or c.get("front")) for c in cards):
            m = f.get("meta", {}) or {}
            self._emit("flashcards_changed", {
                "cards": _normalize_flashcards(cards, len(cards)),
                "provider": m.get("provider", ""), "model": m.get("model", ""),
                "meta": m, "session": f.get("session") or None})

    def generate_flashcards(self, opts):
        job = self.current_job
        if job is None:
            self._emit("flashcards_status", {"state": "error",
                       "message": "Open or process a lecture first."})
            return
        if isinstance(opts, str):
            try:
                opts = json.loads(opts or "{}")
            except ValueError:
                opts = {}
        count = max(1, min(int(opts.get("count") or 10), 60))
        meta = {"count": count, "difficulty": opts.get("difficulty", "Basic"),
                "style": opts.get("style", "term → definition"),
                "scope": opts.get("scope", "entire lecture")}
        o = self._ollama_settings()
        self._emit("flashcards_status", {"state": "generating", "message": "Generating flashcards…"})

        def deliver(cards, provider, model=""):
            cards = _normalize_flashcards(cards, count)
            if not cards:
                self._emit("flashcards_status", {"state": "error",
                           "message": "Couldn't build flashcards for this lecture."})
                return
            self._save_flashcards(job, cards, meta, provider, model)
            self._emit("flashcards_changed", {"cards": cards, "provider": provider,
                       "model": model, "meta": {**meta, "provider": provider, "model": model},
                       "session": None})
            self._emit("flashcards_status", {"state": "ready",
                       "message": f"{len(cards)} cards · {provider}"})

        segments = transcript_store.load_working(job.paths) or []

        def do_fallback():
            try:
                terms = study_service.build_overview(job).get("key_terms", []) or []
            except Exception:
                terms = []
            deliver(_fallback_flashcards(terms, count, _sentences(segments)),
                    smart_study.PROVIDER_BUILTIN)

        if not (o.get("enabled") and o.get("model")):
            do_fallback()
            return

        transcript_text = sas.transcript_context(segments)
        worker = sas.StudyAssistantWorker("flashcards", transcript_text, o, count=count,
                                          difficulty=meta["difficulty"])
        self._flash_worker = worker

        def ok(task, result):
            cards = (result or {}).get("cards") if isinstance(result, dict) else None
            deliver(cards, smart_study.PROVIDER_LOCAL, o.get("model", "")) if cards else do_fallback()

        def fail(kind, message, details):
            self._log("[ai]", f"flashcard gen failed ({kind}) — using built-in fallback", "ai")
            do_fallback()

        worker.finished_ok.connect(ok)
        worker.failed.connect(fail)
        worker.start()

    def cancel_flashcards(self):
        w = getattr(self, "_flash_worker", None)
        if w is not None:
            try:
                w.detach_and_stop()
            except Exception:
                pass
        self._emit("flashcards_status", {"state": "cancelled", "message": "Generation cancelled."})

    def save_flashcard_session(self, session_json):
        job = self.current_job
        if job is None:
            return
        try:
            session = json.loads(session_json)
        except ValueError:
            return
        data = study_service.load_study_data(job)
        f = data.get("flashcards") if isinstance(data.get("flashcards"), dict) else {}
        f["session"] = session
        data["flashcards"] = f
        study_service.save_study_data(job, data)

    # ------------------------------------------------------------------ exports
    def export_all(self, formats: list[str]):
        self._run_export()

    def export_one(self, kind: str):
        self._run_export()

    def _run_export(self):
        job = self.current_job
        if job is None:
            self._emit("export_done", {"files": [], "meta": "no job loaded"})
            return
        self._export_start = time.time()
        self._emit("export_progress", {"pct": 5, "label": "starting export…"})
        worker = ExportWorker(job)
        self._export_worker = worker
        worker.progress.connect(
            lambda p: self._emit("export_progress",
                                 {"pct": int(p), "label": f"exporting… {int(p)}%"}))
        worker.status_message.connect(
            lambda m: self._emit("export_progress", {"pct": 50, "label": str(m)[:80]}))
        worker.finished.connect(lambda ok, err: self._on_export_finished(ok, err))
        worker.start()

    def _on_export_finished(self, success: bool, error: str):
        job = self.current_job
        if not success:
            self._emit("export_done", {"files": [], "meta": f"export failed: {error}"[:80]})
            return
        export_dir = job.paths["exports"]
        files, total_bytes = [], 0
        if os.path.isdir(export_dir):
            for name in sorted(os.listdir(export_dir)):
                fp = os.path.join(export_dir, name)
                if os.path.isfile(fp):
                    files.append(name)
                    total_bytes += os.path.getsize(fp)
        elapsed = time.time() - self._export_start
        self._emit("export_done", {
            "files": files,
            "meta": f"{len(files)} files · {_human_size(total_bytes)} · {elapsed:.1f}s"})

    def export_folder(self):
        if self.current_job is not None:
            return self.current_job.paths["exports"]
        return self.config.data_dir

    # ------------------------------------------------------------------ settings / misc
    def test_endpoint(self):
        self._probe_ollama_async(announce=True)

    def validate_vulkan(self):
        """Report the honest Vulkan/compute-backend state (never silently CPU).

        Uses the engine registry's real detection + selection so the UI can show
        available / selected / loaded / unavailable-with-reason, and which backend
        the current ``engine`` setting will actually resolve to.
        """
        try:
            from lecturepack.infrastructure.transcription_engines import (
                EngineRegistry, ENGINE_VULKAN)
            reg = EngineRegistry(self.config)
            vk = reg.detect_engines().get(ENGINE_VULKAN)
            requested = self.config.get("engine", "auto")
            resolved = reg.resolve(requested)
            avail = bool(vk and vk.available)
            selected = resolved.key == ENGINE_VULKAN
            if not avail:
                state = "unavailable"
                msg = f"Vulkan unavailable — {(vk.reason if vk else 'not detected')}"
            elif selected:
                state = "loaded"
                msg = f"Vulkan available and selected — will load {resolved.backend}"
            else:
                state = "available"
                msg = f"Vulkan available but not selected — currently using {resolved.backend}"
            self._emit("vulkan_status", {
                "state": state, "message": msg, "available": avail,
                "selected": selected, "reason": (vk.reason if vk else ""),
                "requested": requested, "resolved_backend": resolved.backend,
                "resolved_label": resolved.label,
                "benchmark_ok": bool(self.config.get("vulkan_benchmark_ok", False)),
                "exe": (vk.exe_path if vk else "")})
        except Exception as exc:  # pragma: no cover - defensive
            self._emit("vulkan_status", {"state": "error",
                       "message": f"Vulkan check failed: {exc}"})

    def validate_cuda(self):
        """Report the honest CUDA (NVIDIA GPU) backend state via the registry."""
        try:
            from lecturepack.infrastructure.transcription_engines import (
                EngineRegistry, ENGINE_CUDA)
            reg = EngineRegistry(self.config)
            cuda = reg.detect_engines().get(ENGINE_CUDA)
            requested = self.config.get("engine", "auto")
            resolved = reg.resolve(requested)
            avail = bool(cuda and cuda.available)
            selected = resolved.key == ENGINE_CUDA
            if not avail:
                state = "unavailable"
                msg = f"CUDA unavailable — {(cuda.reason if cuda else 'not detected')}"
            elif selected:
                state = "loaded"
                msg = f"CUDA available and selected — will load {resolved.backend}"
            else:
                state = "available"
                msg = f"CUDA available but not selected — currently using {resolved.backend}"
            self._emit("cuda_status", {
                "state": state, "message": msg, "available": avail,
                "selected": selected, "reason": (cuda.reason if cuda else ""),
                "requested": requested, "resolved_backend": resolved.backend,
                "resolved_label": resolved.label,
                "benchmark_ok": bool(self.config.get("cuda_benchmark_ok", False)),
                "exe": (cuda.exe_path if cuda else "")})
        except Exception as exc:  # pragma: no cover - defensive
            self._emit("cuda_status", {"state": "error",
                       "message": f"CUDA check failed: {exc}"})

    # -- Optional CUDA acceleration pack (verified download into bin/cuda) -----
    def _nvidia_present(self) -> bool:
        try:
            from lecturepack.infrastructure.transcription_engines import nvidia_cuda_present
            return bool(nvidia_cuda_present())
        except Exception:
            return False

    def cuda_pack_status(self):
        self._emit("cuda_pack", {
            "state": "installed" if cuda_pack.is_installed() else "idle",
            "gpu_present": self._nvidia_present(),
            "installed": cuda_pack.is_installed(),
            "size_label": cuda_pack.CUDA_PACK["size_label"]})

    def cancel_cuda_pack(self):
        ev = getattr(self, "_cuda_pack_cancel", None)
        if ev is not None:
            ev.set()

    def install_cuda_pack(self):
        """Download + verify + install the CUDA whisper.cpp binary into bin/cuda."""
        cancel = threading.Event()
        self._cuda_pack_cancel = cancel
        pack = cuda_pack.CUDA_PACK

        def emit(state, message="", pct=None, **extra):
            payload = {"state": state, "message": message, "percent": pct,
                       "gpu_present": self._nvidia_present(),
                       "installed": cuda_pack.is_installed(),
                       "size_label": pack["size_label"]}
            payload.update(extra)
            self._emit("cuda_pack", payload)

        def _rm(p):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

        def worker():
            if not self._nvidia_present():
                emit("error", "No NVIDIA CUDA GPU/driver detected on this computer.")
                return
            import tempfile
            base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            cache = os.path.join(base, "LecturePack", "Updates")
            os.makedirs(cache, exist_ok=True)
            partial = os.path.join(cache, pack["name"] + ".partial")
            final_zip = os.path.join(cache, pack["name"])
            _rm(partial)
            last = {"p": -5.0}

            def prog(pct, read, total):
                if cancel.is_set():
                    return
                if pct - last["p"] >= 1.0 or pct >= 100:
                    last["p"] = pct
                    emit("downloading", f"Downloading CUDA acceleration ({pack['size_label']})…",
                         round(pct, 1))

            emit("downloading", f"Downloading CUDA acceleration ({pack['size_label']})…", 0.0)
            try:
                cuda_pack.download(pack["url"], partial, on_progress=prog, cancel=cancel.is_set)
            except RuntimeError as exc:
                _rm(partial)
                emit("cancelled", "Download cancelled.") if str(exc) == "__cancelled__" \
                    else emit("error", f"Download failed: {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                _rm(partial)
                emit("error", f"Download failed: {exc}")
                return
            emit("verifying", "Verifying download…")
            if not cuda_pack.verify(partial):
                _rm(partial)
                emit("error", "Checksum mismatch — download rejected.")
                return
            os.replace(partial, final_zip)
            emit("installing", "Installing CUDA files…")
            try:
                n = cuda_pack.extract_pack(final_zip, cuda_pack.bin_cuda_dir())
            except Exception as exc:  # noqa: BLE001
                _rm(final_zip)
                emit("error", f"Install failed: {exc}")
                return
            _rm(final_zip)  # don't keep the ~650 MB archive
            if not cuda_pack.is_installed():
                emit("error", "Install completed but whisper-cli.exe is missing.")
                return
            self.validate_cuda()
            emit("ready", f"CUDA acceleration installed ({n} files). "
                          "Pick NVIDIA CUDA under Compute engine.")

        threading.Thread(target=worker, daemon=True).start()

    # -- Groq online transcription (reuses the existing backend + secret store) --
    def _groq_store(self):
        from lecturepack.infrastructure.secret_store import WindowsCredentialStore
        return WindowsCredentialStore()

    def _emit_groq_status(self, message="", testing=False):
        has = False
        try:
            has = self._groq_store().has_secret()
        except Exception:
            has = False
        self._emit("groq_status", {
            "has_key": bool(has), "testing": bool(testing),
            "backend": self.config.get("transcription_backend", "local-whispercpp"),
            "message": message or ("API key stored." if has else "No API key stored.")})

    def set_groq_key(self, key):
        try:
            self._groq_store().set(key)
            self._emit_groq_status("API key saved to Windows Credential Manager.")
        except Exception as exc:
            self._emit_groq_status(f"Could not save key: {exc}")

    def remove_groq_key(self):
        try:
            self._groq_store().remove()
            self._emit_groq_status("API key removed.")
        except Exception as exc:
            self._emit_groq_status(f"Could not remove key: {exc}")

    def test_groq_key(self):
        self._emit_groq_status("Testing Groq credentials…", testing=True)

        def work():
            try:
                from lecturepack.services.groq_transcription import GroqHttpClient
                key = self._groq_store().get()
                if not key:
                    self._emit_groq_status("No API key stored — set one first.")
                    return
                ok = GroqHttpClient().test_key(key)
                self._emit_groq_status(
                    "Groq credential test passed — account limits and billing still apply."
                    if ok else "Groq credential test failed — check the key.")
            except Exception as exc:
                self._emit_groq_status(f"Groq test failed: {exc}")

        threading.Thread(target=work, daemon=True).start()

    def list_ollama_models(self):
        """Fetch installed Ollama models (/api/tags) and emit them for the
        Settings model picker. Never hard-hardcodes a single model."""
        o = self._ollama_settings()
        base = o.get("base_url") or "http://localhost:11434"
        selected = o.get("model", "")

        def worker():
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                models = OllamaClient(base).list_models()
                self._emit("ollama_models", {
                    "models": models, "selected": selected, "available": True})
            except Exception as exc:
                self._emit("ollama_models", {
                    "models": [], "selected": selected,
                    "available": False, "error": str(exc)})

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------- Smart Study
    def _study_preset(self) -> str:
        stored = self.config.get("study_preset", "") or ""
        if stored in (smart_study.PRESET_LIGHTWEIGHT, smart_study.PRESET_BALANCED,
                      smart_study.PRESET_CUSTOM):
            return stored
        return smart_study.preset_for_model(self._ollama_settings().get("model", ""))

    def _smart_study_payload(self, state="idle", message="", pct=None,
                             ollama=None, installed=None, ram_gb=None):
        o = self._ollama_settings()
        model = o.get("model", "")
        ram = smart_study.usable_ram_gb() if ram_gb is None else ram_gb
        installed = installed or []
        ready = bool(o.get("enabled") and model and model in installed
                     and ollama and ollama.get("available"))
        return {
            "state": state,
            "message": message,
            "percent": pct,
            "ram_gb": ram,
            "recommendation": smart_study.recommend_preset(ram),
            "presets": smart_study.preset_list(),
            "preset": self._study_preset(),
            "model": model,
            "enabled": bool(o.get("enabled")),
            "ready": ready,
            "smart_study_ready": bool(self.config.get("smart_study_ready", False)),
            "ollama": ollama or {"available": False},
            "installed_models": installed,
            "provider": smart_study.PROVIDER_LOCAL if ready else smart_study.PROVIDER_BUILTIN,
        }

    def smart_study_status(self):
        """Probe Ollama + installed models and emit a full Smart Study snapshot."""
        base = self._ollama_settings().get("base_url") or "http://localhost:11434"

        def worker():
            ollama = {"available": False}
            installed = []
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                c = OllamaClient(base)
                ollama = c.is_available()
                if ollama.get("available"):
                    installed = [m["name"] for m in c.list_models()]
            except Exception as exc:
                ollama = {"available": False, "error": str(exc)}
            self._emit("smart_study",
                       self._smart_study_payload(ollama=ollama, installed=installed))

        threading.Thread(target=worker, daemon=True).start()

    def set_study_preset(self, preset: str):
        """Persist the chosen Smart Study preset + its model. No download here."""
        o = dict(self.config.get("ollama", {}) or {})
        if preset in (smart_study.PRESET_LIGHTWEIGHT, smart_study.PRESET_BALANCED):
            o["model"] = smart_study.model_for_preset(preset)
            o["enabled"] = True
            self.config.set("study_preset", preset)
        else:
            self.config.set("study_preset", smart_study.PRESET_CUSTOM)
        self.config.set("ollama", o)
        self._emit("settings_changed", self._settings_payload())
        self._probe_ollama_async()
        self.smart_study_status()

    def cancel_smart_study(self):
        ev = getattr(self, "_smart_study_cancel", None)
        if ev is not None:
            ev.set()

    def launch_ollama_installer(self):
        """Open the official Ollama download page in the browser.

        We deliberately do NOT download or execute the installer ourselves — the
        user runs the official installer, keeping LecturePack out of the business
        of fetching and running third-party binaries.
        """
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(smart_study.OLLAMA_DOWNLOAD_URL))
        except Exception:
            try:
                import webbrowser
                webbrowser.open(smart_study.OLLAMA_DOWNLOAD_URL)
            except Exception:
                pass
        self._emit("smart_study", self._smart_study_payload(
            state="need_engine",
            message=("Opened the official Ollama download page. Install Ollama, "
                     "then press Install Smart Study again.")))

    def install_smart_study(self, preset: str):
        """One-action Smart Study setup: ensure the preset's model is present,
        test it, and persist — all off the UI thread with progress + cancel."""
        if preset not in (smart_study.PRESET_LIGHTWEIGHT, smart_study.PRESET_BALANCED):
            preset = self._study_preset()
        if preset not in (smart_study.PRESET_LIGHTWEIGHT, smart_study.PRESET_BALANCED):
            preset = smart_study.recommend_preset(smart_study.usable_ram_gb())["recommended"]
        label = smart_study.STUDY_PRESETS[preset]["label"]
        model = smart_study.model_for_preset(preset)
        cancel = threading.Event()
        self._smart_study_cancel = cancel
        base = self._ollama_settings().get("base_url") or "http://localhost:11434"

        def emit(state, message="", pct=None, **extra):
            payload = self._smart_study_payload(state=state, message=message, pct=pct)
            payload.update(extra)
            payload["preset"] = preset
            self._emit("smart_study", payload)

        def worker():
            from lecturepack.infrastructure.ollama_client import (
                OllamaClient, OllamaError, OllamaCancelled)
            c = OllamaClient(base)
            if not c.is_available().get("available"):
                emit("need_engine",
                     "Local AI Engine (Ollama) isn't installed or running. "
                     "Install it to enable Smart Study.")
                return
            try:
                installed = [m["name"] for m in c.list_models()]
            except Exception:
                installed = []
            if model not in installed:
                emit("downloading", f"Downloading {label}…", 0.0)
                last = {"pct": -5.0}

                def on_prog(p):
                    if cancel.is_set():
                        return
                    pct = p.get("percent")
                    if pct is None or pct - last["pct"] >= 1.0 or pct >= 100:
                        last["pct"] = pct if pct is not None else last["pct"]
                        emit("downloading", f"Downloading {label}…",
                             round(pct, 1) if pct is not None else None,
                             status=p.get("status", ""))

                try:
                    c.pull_model(model, on_progress=on_prog, cancel_event=cancel)
                except OllamaCancelled:
                    emit("cancelled", "Smart Study setup cancelled.")
                    return
                except OllamaError as exc:
                    emit("error", f"Download failed: {exc}")
                    return
            emit("testing", f"Testing {label}…")
            try:
                res = c.chat_structured(
                    model, "Reply with compact JSON only.", 'Return {"ok": true}.',
                    {"type": "object", "properties": {"ok": {"type": "boolean"}},
                     "required": ["ok"]},
                    num_predict=32, keep_alive="5m", cancel_event=cancel, timeout=90.0)
                json.loads(res.get("content", "") or "{}")
            except OllamaCancelled:
                emit("cancelled", "Smart Study setup cancelled.")
                return
            except Exception as exc:
                emit("error", f"The model downloaded but the test request failed: {exc}")
                return
            o = dict(self.config.get("ollama", {}) or {})
            o["model"] = model
            o["enabled"] = True
            self.config.set("ollama", o)
            self.config.set("study_preset", preset)
            self.config.set("smart_study_ready", True)
            self._emit("settings_changed", self._settings_payload())
            self._probe_ollama_async()
            emit("ready", f"Smart Study ready — {label}.")
            # Refresh the full snapshot (installed list now includes the model).
            self.smart_study_status()

        threading.Thread(target=worker, daemon=True).start()

    def _probe_ollama_async(self, announce: bool = False):
        o = self._ollama_settings()
        base = o.get("base_url") or "http://localhost:11434"
        model = o.get("model", "")

        def worker():
            try:
                from lecturepack.infrastructure.ollama_client import OllamaClient
                probe = OllamaClient(base).is_available()
            except Exception as exc:
                probe = {"available": False, "error": str(exc)}
            if probe.get("available") and o.get("enabled") and model:
                self._emit("ai_status", {"label": smart_study.PROVIDER_LOCAL, "model": model})
                if announce:
                    self._emit("settings_changed", {"update_status": ""})
            else:
                # Built-in Study is always usable — never present the study
                # assistant as "off" or a dead control (§8).
                self._emit("ai_status", {
                    "label": smart_study.PROVIDER_BUILTIN, "model": model or ""})

        threading.Thread(target=worker, daemon=True).start()

    def browse_model(self, parent):
        path, _ = QFileDialog.getOpenFileName(
            parent, "Choose a Whisper model", os.path.expanduser("~"),
            "Whisper models (*.bin);;All files (*.*)")
        if path:
            self.config.set("whisper_model", path)
            self._emit("settings_changed", {"model_path": path})

    def save_project(self):
        if self.current_job is not None:
            self.current_job.save()
            self._log("[save]", "project saved", "extract")

    def is_processing(self) -> bool:
        try:
            return bool(getattr(self.controller, "_active_stages", None))
        except Exception:  # noqa: BLE001
            return False


def make_adapter(backend) -> EngineAdapter:
    """Return the real engine adapter, falling back to the demo on import error."""
    try:
        return LecturePackAdapter(backend)
    except Exception as exc:  # pragma: no cover - defensive boot guard
        import traceback
        traceback.print_exc()
        print(f"[engine_adapter] falling back to DemoAdapter: {exc}")
        return DemoAdapter(backend)
