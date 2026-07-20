"""
lecturepack.ui.pages.settings_page
=================================

Settings (v1.1, Phases 1+5+7): binaries, transcription engines and model
profiles, AI (Ollama) configuration with live model discovery and a Test
Model action, appearance, and pipeline options.

All Ollama interactions run off the GUI thread.  Studio visual layout.
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
    QInputDialog,
)

from lecturepack.infrastructure.transcription_engines import (
    EngineRegistry, ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN, ENGINE_LABELS,
    MODEL_PROFILES, model_search_dirs, resolve_profile_model,
)
from lecturepack.ui import theme

RECOMMENDED_MODELS = ["qwen3:1.7b", "qwen3.5:4b", "qwen3.5:9b", "qwen3:0.6b",
                      "gemma3:1b", "ministral-3:3b"]


class SettingsPage(QWidget):
    theme_changed = Signal(bool)           # dark?
    settings_changed = Signal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.engine_registry = EngineRegistry(config_manager)
        self._build_ui()
        self.reload()

    # ------------------------------------------------------------------ #
    def _card(self, title_text, inner_layout):
        card = QFrame()
        card.setProperty("card", True)
        theme.add_card_shadow(card)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 20, 22, 22)
        lbl = QLabel(title_text)
        lbl.setStyleSheet("font-weight: 700; font-size: 16px; margin-bottom: 13px;")
        cl.addWidget(lbl)
        cl.addLayout(inner_layout)
        return card

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(44, 34, 44, 52)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        wrapper = QWidget()
        wrapper.setMaximumWidth(800)
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(16)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 30px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 10px;")
        wl.addWidget(title)

        # ---- whisper model ---- #
        wm_grid = QHBoxLayout()
        wm_grid.setSpacing(10)
        wm_path = QLineEdit()
        wm_path.setReadOnly(True)
        wm_grid.addWidget(wm_path, 1)
        wm_browse = QPushButton("Browse")
        wm_browse.clicked.connect(lambda: self._pick_file(wm_path, "Model files (*.bin)"))
        wm_grid.addWidget(wm_browse)
        wm_layout = QVBoxLayout()
        wm_layout.addLayout(wm_grid)
        self.diag_lbl = QLabel("")
        wm_layout.addWidget(self.diag_lbl)
        self.diag_lbl.setWordWrap(True)
        self.diag_lbl.setStyleSheet(f"font-size: 12px; color: {theme.c('muted')}; border: none;")
        wl.addWidget(self._card("Whisper model", wm_layout))
        self.whisper_exe_edit = QLineEdit()
        self.whisper_model_edit = wm_path

        # ---- compute engine ---- #
        eng_layout = QVBoxLayout()
        eng_row = QHBoxLayout()
        eng_row.setSpacing(10)
        self.engine_combo = QComboBox()
        for key in (ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN):
            self.engine_combo.addItem(ENGINE_LABELS[key], key)
        eng_row.addWidget(self.engine_combo, 1)
        eng_layout.addLayout(eng_row)
        self.engines_status_lbl = QLabel("")
        self.engines_status_lbl.setWordWrap(True)
        self.engines_status_lbl.setStyleSheet(f"font-size: 12px; color: {theme.c('muted')}; border: none;")
        eng_layout.addWidget(self.engines_status_lbl)
        self.vulkan_ok_chk = QCheckBox("Vulkan benchmarked faster on this PC")
        eng_layout.addWidget(self.vulkan_ok_chk)
        self.parallel_chk = QCheckBox("Run transcription and slide detection concurrently")
        self.parallel_chk.setChecked(True)
        eng_layout.addWidget(self.parallel_chk)
        self.profiles_lbl = QLabel("")
        self.profiles_lbl.setWordWrap(True)
        self.profiles_lbl.setStyleSheet(f"font-size: 12px; color: {theme.c('muted')}; border: none;")
        eng_layout.addWidget(self.profiles_lbl)
        wl.addWidget(self._card("Compute engine", eng_layout))

        # ---- local AI endpoint ---- #
        ai_layout = QVBoxLayout()
        ai_header = QHBoxLayout()
        ai_header.addStretch(1)
        self.ollama_status_lbl = QLabel("")
        self.ollama_status_lbl.setWordWrap(True)
        ai_header.addWidget(self.ollama_status_lbl)
        ai_layout.addLayout(ai_header)
        ai_url_row = QHBoxLayout()
        ai_url_row.setSpacing(10)
        self.ollama_url_edit = QLineEdit("http://localhost:11434")
        ai_url_row.addWidget(self.ollama_url_edit, 1)
        self.test_model_btn = QPushButton("Test")
        self.test_model_btn.clicked.connect(self.test_ollama_model)
        ai_url_row.addWidget(self.test_model_btn)
        ai_layout.addLayout(ai_url_row)
        ai_model_row = QHBoxLayout()
        ai_model_row.setSpacing(10)
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        ai_model_row.addWidget(self.ollama_model_combo, 1)
        self.refresh_models_btn = QPushButton("Refresh")
        self.refresh_models_btn.clicked.connect(self.refresh_ollama_models)
        ai_model_row.addWidget(self.refresh_models_btn)
        ai_layout.addLayout(ai_model_row)
        self.ollama_enabled_chk = QCheckBox("Enable AI assistance (local Ollama)")
        ai_layout.addWidget(self.ollama_enabled_chk)
        ai_keep_row = QHBoxLayout()
        ai_keep_row.setSpacing(10)
        ai_keep_row.addWidget(QLabel("Keep model loaded:"))
        self.keep_alive_combo = QComboBox()
        self.keep_alive_combo.addItems(["5m", "10m", "30m", "0 (unload immediately)"])
        self.keep_alive_combo.setCurrentText("10m")
        ai_keep_row.addWidget(self.keep_alive_combo)
        ai_keep_row.addStretch(1)
        ai_layout.addLayout(ai_keep_row)
        note = QLabel("AI proposes corrections and headings only; it never modifies the raw "
                      "transcript, never applies silently, and exports never wait for it.")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        ai_layout.addWidget(note)
        wl.addWidget(self._card("Local AI endpoint", ai_layout))

        # ---- Groq ---- #
        groq_layout = QVBoxLayout()
        self.groq_status_lbl = QLabel("")
        self.groq_status_lbl.setWordWrap(True)
        groq_layout.addWidget(self.groq_status_lbl)
        groq_btns = QHBoxLayout()
        self.groq_set_btn = QPushButton("Set API key")
        self.groq_set_btn.clicked.connect(self.set_groq_key)
        groq_btns.addWidget(self.groq_set_btn)
        self.groq_test_btn = QPushButton("Test key")
        self.groq_test_btn.clicked.connect(self.test_groq_key)
        groq_btns.addWidget(self.groq_test_btn)
        self.groq_remove_btn = QPushButton("Remove key")
        self.groq_remove_btn.clicked.connect(self.remove_groq_key)
        groq_btns.addWidget(self.groq_remove_btn)
        groq_layout.addLayout(groq_btns)
        groq_note = QLabel(
            "Online transcription is opt-in. Only audio chunks are uploaded.")
        groq_note.setWordWrap(True)
        groq_note.setStyleSheet(f"font-size: 12px; color: {theme.c('muted')}; border: none;")
        groq_layout.addWidget(groq_note)
        wl.addWidget(self._card("Groq online transcription", groq_layout))

        # ---- appearance ---- #
        ap_layout = QVBoxLayout()
        ap_row = QHBoxLayout()
        ap_row.setSpacing(10)
        ap_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        ap_row.addWidget(self.theme_combo)
        ap_row.addStretch(1)
        ap_layout.addLayout(ap_row)
        ap_dir_row = QHBoxLayout()
        ap_dir_row.setSpacing(10)
        ap_dir_row.addWidget(QLabel("Data directory:"))
        self.data_dir_lbl = QLabel("")
        self.data_dir_lbl.setStyleSheet("border: none;")
        ap_dir_row.addWidget(self.data_dir_lbl, 1)
        ap_layout.addLayout(ap_dir_row)
        wl.addWidget(self._card("Appearance", ap_layout))

        # ---- privacy ---- #
        privacy_layout = QHBoxLayout()
        privacy_layout.setSpacing(12)
        priv_lbl = QLabel("\u2713")
        priv_lbl.setStyleSheet(
            f"font-size: 22px; color: {theme.c('secondary_ink')}; border: none;")
        privacy_layout.addWidget(priv_lbl)
        priv_text = QLabel(
            "<b>100% local.</b> No telemetry, no uploads, no account. "
            "Job data stays in <span style='font: 500 12px monospace'>~/LecturePackData</span>.")
        priv_text.setTextFormat(Qt.TextFormat.RichText)
        priv_text.setWordWrap(True)
        priv_text.setStyleSheet("font-size: 13px; line-height: 1.5; border: none;")
        privacy_layout.addWidget(priv_text, 1)
        privacy_card = QFrame()
        privacy_card.setStyleSheet(
            f"background: {theme.c('secondary_soft')}; border: 1.5px solid {theme.c('secondary')}; "
            f"border-radius: 13px; padding: 16px 20px;")
        privacy_card.setLayout(privacy_layout)
        wl.addWidget(privacy_card)

        wl.addSpacing(10)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_btn = QPushButton("Save settings")
        self.save_btn.setStyleSheet(
            f"font: 700 14px sans-serif; background: {theme.c('primary')}; color: #fff; "
            f"border: 1.5px solid {theme.c('primary_hover')}; border-radius: 9px; "
            f"padding: 10px 22px;")
        self.save_btn.clicked.connect(self.save)
        save_row.addWidget(self.save_btn)
        wl.addLayout(save_row)
        wl.addStretch(1)

        layout.addWidget(wrapper)
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _pick_file(self, edit, filt):
        p, _ = QFileDialog.getOpenFileName(self, "Select file", "", filt)
        if p:
            edit.setText(p)

    # ------------------------------------------------------------------ #
    def reload(self):
        cm = self.config_manager
        self.whisper_exe_edit.setText(cm.get("whisper_exe", ""))
        self.whisper_model_edit.setText(cm.get("whisper_model", ""))
        idx = self.engine_combo.findData(cm.get("engine", ENGINE_AUTO))
        self.engine_combo.setCurrentIndex(max(0, idx))
        self.vulkan_ok_chk.setChecked(bool(cm.get("vulkan_benchmark_ok", False)))
        self.parallel_chk.setChecked(bool(cm.get("parallel_pipeline", True)))
        o = cm.get("ollama", {}) or {}
        self.ollama_enabled_chk.setChecked(bool(o.get("enabled", False)))
        self.ollama_url_edit.setText(o.get("base_url", "http://localhost:11434"))
        if o.get("model"):
            self.ollama_model_combo.setEditText(o["model"])
        ka = str(o.get("keep_alive", "10m"))
        self.keep_alive_combo.setCurrentText("0 (unload immediately)" if ka == "0" else ka)
        self.theme_combo.setCurrentIndex(1 if cm.get("dark_theme", False) else 0)
        self.data_dir_lbl.setText(cm.data_dir)
        self.refresh_engine_status()
        self.refresh_diagnostics()
        self.refresh_groq_status()

    def _load_settings(self):
        self.reload()

    def save(self):
        cm = self.config_manager
        cm.set("whisper_exe", self.whisper_exe_edit.text().strip())
        cm.set("whisper_model", self.whisper_model_edit.text().strip())
        cm.set("engine", self.engine_combo.currentData())
        cm.set("vulkan_benchmark_ok", self.vulkan_ok_chk.isChecked())
        cm.set("parallel_pipeline", self.parallel_chk.isChecked())
        ka = self.keep_alive_combo.currentText()
        cm.set("ollama", {
            "enabled": self.ollama_enabled_chk.isChecked(),
            "base_url": self.ollama_url_edit.text().strip() or "http://localhost:11434",
            "model": self.ollama_model_combo.currentText().strip(),
            "keep_alive": 0 if ka.startswith("0") else ka,
        })
        dark = self.theme_combo.currentIndex() == 1
        cm.set("dark_theme", dark)
        self.theme_changed.emit(dark)
        self.refresh_engine_status()
        self.refresh_diagnostics()
        self.settings_changed.emit()
        self.ollama_status_lbl.setText("Settings saved.")

    def refresh_groq_status(self):
        from lecturepack.infrastructure.secret_store import (
            SecretStoreError, WindowsCredentialStore,
        )
        try:
            present = WindowsCredentialStore().has_secret()
            self.groq_status_lbl.setText(
                "API key stored securely in Windows Credential Manager."
                if present else "No Groq API key stored. Private Local remains the default.")
            self.groq_test_btn.setEnabled(present)
            self.groq_remove_btn.setEnabled(present)
        except SecretStoreError as exc:
            self.groq_status_lbl.setText(str(exc))
            self.groq_test_btn.setEnabled(False)
            self.groq_remove_btn.setEnabled(False)

    def set_groq_key(self):
        from lecturepack.infrastructure.secret_store import (
            SecretStoreError, WindowsCredentialStore,
        )
        key, ok = QInputDialog.getText(
            self, "Groq API key", "API key:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            WindowsCredentialStore().set(key)
        except SecretStoreError as exc:
            self.groq_status_lbl.setText(str(exc))
            return
        self.refresh_groq_status()

    def remove_groq_key(self):
        from lecturepack.infrastructure.secret_store import (
            SecretStoreError, WindowsCredentialStore,
        )
        try:
            WindowsCredentialStore().remove()
        except SecretStoreError as exc:
            self.groq_status_lbl.setText(str(exc))
            return
        self.refresh_groq_status()

    def test_groq_key(self):
        from lecturepack.infrastructure.secret_store import WindowsCredentialStore
        from lecturepack.services.groq_transcription import GroqHttpClient
        self.groq_test_btn.setEnabled(False)
        self.groq_status_lbl.setText("Testing Groq credentials...")

        def work():
            key = WindowsCredentialStore().get()
            if not key:
                return ("error", "No API key stored.")
            return ("ok", GroqHttpClient().test_key(key))

        def done(result):
            self.groq_test_btn.setEnabled(True)
            if result and result[0] == "ok" and result[1]:
                self.groq_status_lbl.setText(
                    "Groq credential test passed. Account limits and billing still apply.")
            else:
                self.groq_status_lbl.setText(
                    "Groq credential test failed: " +
                    (str(result[1]) if result else "unknown"))

        self._run_bg(work, done)

    # ------------------------------------------------------------------ #
    def refresh_engine_status(self):
        engines = self.engine_registry.detect_engines()
        lines = []
        for key in (ENGINE_CPU, ENGINE_VULKAN):
            e = engines[key]
            state = "available" if e.available else f"unavailable \u2014 {e.reason}"
            lines.append(f"\u2022 {e.label}: {state}")
        resolved = self.engine_registry.resolve(self.engine_combo.currentData() or ENGINE_AUTO)
        lines.append(f"\u2192 Active choice: {resolved.label} ({resolved.reason or 'default'})")
        self.engines_status_lbl.setText("\n".join(lines))
        dirs = model_search_dirs(self.config_manager)
        plines = []
        for key, prof in MODEL_PROFILES.items():
            if key == "custom":
                continue
            found = resolve_profile_model(key, dirs)
            plines.append(f"{prof['label']}: {os.path.basename(found) if found else 'model not downloaded'}")
        self.profiles_lbl.setText("Model profiles \u2014 " + " \u00b7 ".join(plines))

    def refresh_diagnostics(self):
        diag = self.config_manager.check_diagnostics()

        def fmt(key, label):
            e = diag[key]
            return f"{label}: {'OK' if e['valid'] else 'MISSING'} ({os.path.basename(e['path']) if e['path'] else '\u2014'})"

        self.diag_lbl.setText("   ".join([
            fmt("ffmpeg", "FFmpeg"), fmt("ffprobe", "FFprobe"),
            fmt("whisper_cli", "whisper-cli"), fmt("whisper_model", "Model"),
            fmt("data_dir", "Data dir")]))

    # ------------------------------------------------------------------ #
    # Ollama actions (always off the GUI thread)
    # ------------------------------------------------------------------ #
    def _run_bg(self, fn, done):
        holder = {}

        def runner():
            try:
                holder["r"] = fn()
            except Exception as e:
                holder["r"] = ("error", str(e))

        th = threading.Thread(target=runner, daemon=True)
        th.start()

        def poll():
            if th.is_alive():
                QTimer.singleShot(150, poll)
            else:
                done(holder.get("r"))

        QTimer.singleShot(150, poll)

    def refresh_ollama_models(self):
        from lecturepack.infrastructure.ollama_client import OllamaClient, OllamaError
        base = self.ollama_url_edit.text().strip() or "http://localhost:11434"
        self.ollama_status_lbl.setText("Checking Ollama\u2026")
        self.refresh_models_btn.setEnabled(False)

        def work():
            client = OllamaClient(base)
            probe = client.is_available()
            if not probe.get("available"):
                return ("offline", probe.get("error", ""))
            try:
                return ("ok", probe.get("version", "?"), client.list_models())
            except OllamaError as e:
                return ("error", str(e))

        def done(result):
            self.refresh_models_btn.setEnabled(True)
            if not result:
                return
            if result[0] == "ok":
                _tag, version, models = result
                current = self.ollama_model_combo.currentText().strip()
                self.ollama_model_combo.clear()
                for m in models:
                    size_gb = m["size_bytes"] / (1024 ** 3)
                    label = (f"{m['name']}  \u2014  {m['parameter_size'] or '?'} "
                             f"{m['quantization_level'] or ''}  \u00b7  {size_gb:.1f} GB")
                    self.ollama_model_combo.addItem(label, m["name"])
                for i in range(self.ollama_model_combo.count()):
                    self.ollama_model_combo.setItemText(
                        i, self.ollama_model_combo.itemText(i))
                if current:
                    ix = self.ollama_model_combo.findData(current)
                    if ix >= 0:
                        self.ollama_model_combo.setCurrentIndex(ix)
                    else:
                        self.ollama_model_combo.setEditText(current)
                names = [m["name"] for m in models]
                rec = next((r for r in RECOMMENDED_MODELS if r in names), None)
                extra = f" Recommended installed model: {rec}." if rec else \
                    " Consider `ollama pull qwen3:1.7b` for a light default."
                self.ollama_status_lbl.setText(
                    f"Ollama v{version} \u2014 {len(models)} model(s) installed.{extra}")
            elif result[0] == "offline":
                self.ollama_status_lbl.setText(
                    f"Ollama not reachable at {base}. AI features stay disabled; "
                    f"everything else works offline. ({result[1]})")
            else:
                self.ollama_status_lbl.setText(f"Ollama error: {result[1]}")

        self._run_bg(work, done)

    def test_ollama_model(self):
        from lecturepack.infrastructure.ollama_client import OllamaClient, OllamaError
        base = self.ollama_url_edit.text().strip() or "http://localhost:11434"
        model = (self.ollama_model_combo.currentData()
                 or self.ollama_model_combo.currentText().strip())
        if not model:
            self.ollama_status_lbl.setText("Pick a model first.")
            return
        self.ollama_status_lbl.setText(f"Testing {model} (schema-constrained request)\u2026")
        self.test_model_btn.setEnabled(False)

        schema = {"type": "object",
                  "properties": {"ok": {"type": "boolean"}, "echo": {"type": "string"}},
                  "required": ["ok", "echo"]}

        def work():
            client = OllamaClient(base)
            try:
                res = client.chat_structured(
                    model, "Return JSON only.",
                    'Respond with {"ok": true, "echo": "lecturepack"}.',
                    schema, num_predict=60, timeout=90.0)
                import json as _json
                obj = _json.loads(res["content"])
                speed = res["eval_count"] / res["eval_duration_s"] if res["eval_duration_s"] else 0
                return ("ok", obj.get("ok") is True and obj.get("echo") == "lecturepack",
                        speed, res["load_duration_s"])
            except OllamaError as e:
                return ("error", f"{e.kind}: {e}")

        def done(result):
            self.test_model_btn.setEnabled(True)
            if not result:
                return
            if result[0] == "ok":
                _t, valid, speed, load_s = result
                verdict = "passed" if valid else "responded but JSON content unexpected"
                self.ollama_status_lbl.setText(
                    f"Test {verdict}: {speed:.1f} tok/s (load {load_s:.1f}s). "
                    f"Structured output {'OK' if valid else 'check the model'}.")
            else:
                self.ollama_status_lbl.setText(f"Test failed \u2014 {result[1]}")

        self._run_bg(work, done)
