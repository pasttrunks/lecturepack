"""
lecturepack.ui.pages.settings_page
==================================

Settings (v1.1, Phases 1+5+7): binaries, transcription engines and model
profiles, AI (Ollama) configuration with live model discovery and a Test
Model action, appearance, and pipeline options.

All Ollama interactions run off the GUI thread.
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from lecturepack.infrastructure.transcription_engines import (
    EngineRegistry, ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN, ENGINE_LABELS,
    MODEL_PROFILES, model_search_dirs, resolve_profile_model,
)

# Order = preference. Benchmarked 2026-07-16 on the target PC (see
# docs/evidence/v1.1.0/ollama_model_benchmark.json): qwen3:1.7b matched the
# 9B model's repair recall (5/8) at 2.3x the speed of qwen3.5:4b; its rare
# extra proposals are safe because nothing is ever auto-accepted.
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
    def _card(self, title, layout):
        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 12)
        lbl = QLabel(title)
        lbl.setProperty("h2", True)
        cl.addWidget(lbl)
        cl.addLayout(layout)
        return card

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        title = QLabel("Settings")
        title.setProperty("h1", True)
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 8, 0)

        # ---- binaries ---------------------------------------------------- #
        bin_grid = QGridLayout()
        bin_grid.addWidget(QLabel("whisper-cli (CPU, verified):"), 0, 0)
        self.whisper_exe_edit = QLineEdit()
        bin_grid.addWidget(self.whisper_exe_edit, 0, 1)
        b1 = QPushButton("…")
        b1.setFixedWidth(28)
        b1.clicked.connect(lambda: self._pick_file(self.whisper_exe_edit, "Executables (*.exe *.bat *.py)"))
        bin_grid.addWidget(b1, 0, 2)
        bin_grid.addWidget(QLabel("Whisper model:"), 1, 0)
        self.whisper_model_edit = QLineEdit()
        bin_grid.addWidget(self.whisper_model_edit, 1, 1)
        b2 = QPushButton("…")
        b2.setFixedWidth(28)
        b2.clicked.connect(lambda: self._pick_file(self.whisper_model_edit, "Model files (*.bin)"))
        bin_grid.addWidget(b2, 1, 2)
        self.diag_lbl = QLabel("")
        self.diag_lbl.setWordWrap(True)
        self.diag_lbl.setProperty("muted", True)
        bin_grid.addWidget(self.diag_lbl, 2, 0, 1, 3)
        layout.addWidget(self._card("Binaries && models", bin_grid))

        # ---- engines ------------------------------------------------------ #
        eng_grid = QGridLayout()
        eng_grid.addWidget(QLabel("Default engine:"), 0, 0)
        self.engine_combo = QComboBox()
        for key in (ENGINE_AUTO, ENGINE_CPU, ENGINE_VULKAN):
            self.engine_combo.addItem(ENGINE_LABELS[key], key)
        eng_grid.addWidget(self.engine_combo, 0, 1)
        self.engines_status_lbl = QLabel("")
        self.engines_status_lbl.setWordWrap(True)
        eng_grid.addWidget(self.engines_status_lbl, 1, 0, 1, 2)
        self.vulkan_ok_chk = QCheckBox(
            "Vulkan benchmarked faster on this PC (allows Auto to pick Vulkan)")
        eng_grid.addWidget(self.vulkan_ok_chk, 2, 0, 1, 2)
        self.parallel_chk = QCheckBox("Run transcription and slide detection concurrently")
        self.parallel_chk.setChecked(True)
        eng_grid.addWidget(self.parallel_chk, 3, 0, 1, 2)
        self.profiles_lbl = QLabel("")
        self.profiles_lbl.setWordWrap(True)
        self.profiles_lbl.setProperty("muted", True)
        eng_grid.addWidget(self.profiles_lbl, 4, 0, 1, 2)
        layout.addWidget(self._card("Transcription engine && pipeline", eng_grid))

        # ---- Ollama -------------------------------------------------------- #
        ol = QGridLayout()
        self.ollama_enabled_chk = QCheckBox("Enable AI assistance (local Ollama)")
        ol.addWidget(self.ollama_enabled_chk, 0, 0, 1, 3)
        ol.addWidget(QLabel("Server:"), 1, 0)
        self.ollama_url_edit = QLineEdit("http://localhost:11434")
        ol.addWidget(self.ollama_url_edit, 1, 1, 1, 2)
        ol.addWidget(QLabel("Model:"), 2, 0)
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        ol.addWidget(self.ollama_model_combo, 2, 1)
        self.refresh_models_btn = QPushButton("Refresh")
        self.refresh_models_btn.clicked.connect(self.refresh_ollama_models)
        ol.addWidget(self.refresh_models_btn, 2, 2)
        ol.addWidget(QLabel("Keep model loaded:"), 3, 0)
        self.keep_alive_combo = QComboBox()
        self.keep_alive_combo.addItems(["5m", "10m", "30m", "0 (unload immediately)"])
        self.keep_alive_combo.setCurrentText("10m")
        ol.addWidget(self.keep_alive_combo, 3, 1)
        self.test_model_btn = QPushButton("Test model")
        self.test_model_btn.clicked.connect(self.test_ollama_model)
        ol.addWidget(self.test_model_btn, 3, 2)
        self.ollama_status_lbl = QLabel("Ollama status unknown — click Refresh.")
        self.ollama_status_lbl.setWordWrap(True)
        ol.addWidget(self.ollama_status_lbl, 4, 0, 1, 3)
        note = QLabel("AI proposes corrections and headings only; it never modifies the raw "
                      "transcript, never applies silently, and exports never wait for it.")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        ol.addWidget(note, 5, 0, 1, 3)
        layout.addWidget(self._card("AI (Ollama)", ol))

        # ---- appearance --------------------------------------------------- #
        ap = QGridLayout()
        ap.addWidget(QLabel("Theme:"), 0, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        ap.addWidget(self.theme_combo, 0, 1)
        ap.addWidget(QLabel("Data directory:"), 1, 0)
        self.data_dir_lbl = QLabel("")
        ap.addWidget(self.data_dir_lbl, 1, 1)
        layout.addWidget(self._card("Appearance && storage", ap))

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_btn = QPushButton("Save settings")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(self.save)
        save_row.addWidget(self.save_btn)
        layout.addLayout(save_row)
        layout.addStretch(1)

        scroll.setWidget(inner)
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

    # ------------------------------------------------------------------ #
    def refresh_engine_status(self):
        engines = self.engine_registry.detect_engines()
        lines = []
        for key in (ENGINE_CPU, ENGINE_VULKAN):
            e = engines[key]
            state = "available" if e.available else f"unavailable — {e.reason}"
            lines.append(f"• {e.label}: {state}")
        resolved = self.engine_registry.resolve(self.engine_combo.currentData() or ENGINE_AUTO)
        lines.append(f"→ Active choice: {resolved.label} ({resolved.reason or 'default'})")
        self.engines_status_lbl.setText("\n".join(lines))
        dirs = model_search_dirs(self.config_manager)
        plines = []
        for key, prof in MODEL_PROFILES.items():
            if key == "custom":
                continue
            found = resolve_profile_model(key, dirs)
            plines.append(f"{prof['label']}: {os.path.basename(found) if found else 'model not downloaded'}")
        self.profiles_lbl.setText("Model profiles — " + " · ".join(plines))

    def refresh_diagnostics(self):
        diag = self.config_manager.check_diagnostics()

        def fmt(key, label):
            e = diag[key]
            return f"{label}: {'OK' if e['valid'] else 'MISSING'} ({os.path.basename(e['path']) if e['path'] else '—'})"

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
        self.ollama_status_lbl.setText("Checking Ollama…")
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
                    label = (f"{m['name']}  —  {m['parameter_size'] or '?'} "
                             f"{m['quantization_level'] or ''}  ·  {size_gb:.1f} GB")
                    self.ollama_model_combo.addItem(label, m["name"])
                # plain names win for the editable text
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
                    f"Ollama v{version} — {len(models)} model(s) installed.{extra}")
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
        self.ollama_status_lbl.setText(f"Testing {model} (schema-constrained request)…")
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
                self.ollama_status_lbl.setText(f"Test failed — {result[1]}")

        self._run_bg(work, done)
