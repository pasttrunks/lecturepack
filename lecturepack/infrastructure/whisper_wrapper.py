import os
import sys
from PySide6.QtCore import QProcess, QObject, Signal

class WhisperWrapper(QObject):
    # Signals for asynchronous transcription
    progress = Signal(str)
    finished = Signal(bool, str) # success, error_message
    backend_detected = Signal(str)  # actual loaded backend, e.g. "Vulkan (Vulkan0)" or "CPU"

    def __init__(self, whisper_exe_path=""):
        super().__init__()
        self.whisper_exe_path = whisper_exe_path
        self.process = None
        self.detected_backend = ""
        self._backend_probe_buffer = ""

    def get_supported_flags(self):
        """Retrieves supported options from WhisperCapabilityDetector cache or fallback."""
        from lecturepack.infrastructure.whisper_detector import WhisperCapabilityDetector
        if not self.whisper_exe_path or not os.path.exists(self.whisper_exe_path):
            return {"-oj", "-osrt", "-otxt"}
        try:
            stat = os.stat(self.whisper_exe_path)
            key = (self.whisper_exe_path, stat.st_size, stat.st_mtime)
            if key in WhisperCapabilityDetector._cache:
                return WhisperCapabilityDetector._cache[key]["flags"]
        except Exception:
            pass
        return {"-oj", "-osrt", "-otxt"}

    def start_transcription(self, audio_path, model_path, output_prefix, glossary=None,
                            threads=8, vad_settings=None, engine_exe=None, extra_args=None):
        """Asynchronously runs the transcription using QProcess.

        ``engine_exe`` overrides the configured whisper executable for this run
        (transcription-engine abstraction); ``extra_args`` are appended verbatim
        (e.g. ``["-ng"]`` to force CPU on a Vulkan-capable binary)."""
        if engine_exe:
            self.whisper_exe_path = engine_exe
        self.detected_backend = ""
        self._backend_probe_buffer = ""
        if not self.whisper_exe_path:
            self.finished.emit(False, "Whisper executable path is not set.")
            return

        self.process = QProcess()
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        # Detect supported flags
        supported_flags = self.get_supported_flags()

        # Build argument list
        whisper_args = [
            "-m", model_path,
            "-f", audio_path,
            "-of", output_prefix
        ]

        # Use full JSON output if supported, otherwise standard JSON
        if "--output-json-full" in supported_flags:
            whisper_args.append("--output-json-full")
        elif "-ojf" in supported_flags:
            whisper_args.append("-ojf")
        else:
            whisper_args.append("-oj")

        # Standard subtitle outputs
        whisper_args.extend(["-osrt", "-otxt"])

        # Thread count
        if threads:
            if "--threads" in supported_flags:
                whisper_args.extend(["--threads", str(threads)])
            elif "-t" in supported_flags:
                whisper_args.extend(["-t", str(threads)])

        # VAD Settings
        if vad_settings and vad_settings.get("enabled"):
            v_model = vad_settings.get("model_path", "")
            if v_model and os.path.exists(v_model):
                if "--vad" in supported_flags:
                    whisper_args.append("--vad")
                if "--vad-model" in supported_flags:
                    whisper_args.extend(["--vad-model", v_model])
                elif "-vm" in supported_flags:
                    whisper_args.extend(["-vm", v_model])
                
                # Advanced VAD options if supported
                v_threshold = vad_settings.get("threshold", 0.50)
                if "--vad-threshold" in supported_flags:
                    whisper_args.extend(["--vad-threshold", f"{v_threshold:.2f}"])
                elif "-vt" in supported_flags:
                    whisper_args.extend(["-vt", f"{v_threshold:.2f}"])

                v_spd = vad_settings.get("min_speech_duration_ms", 250)
                if "--vad-min-speech-duration-ms" in supported_flags:
                    whisper_args.extend(["--vad-min-speech-duration-ms", str(v_spd)])
                elif "-vspd" in supported_flags:
                    whisper_args.extend(["-vspd", str(v_spd)])

                v_sd = vad_settings.get("min_silence_duration_ms", 100)
                if "--vad-min-silence-duration-ms" in supported_flags:
                    whisper_args.extend(["--vad-min-silence-duration-ms", str(v_sd)])
                elif "-vsd" in supported_flags:
                    whisper_args.extend(["-vsd", str(v_sd)])

        # Glossary Prompt
        if glossary:
            sanitized = "".join(c for c in glossary if c.isalnum() or c in " ,.-_")
            words = sanitized.split()
            if len(words) > 150:
                words = words[:150]
            glossary_clean = " ".join(words)
            
            if glossary_clean:
                if "--prompt" in supported_flags:
                    whisper_args.extend(["--prompt", glossary_clean])
                if "--carry-initial-prompt" in supported_flags:
                    whisper_args.append("--carry-initial-prompt")

        if extra_args:
            whisper_args.extend(extra_args)

        # If the path is a python script, run sys.executable with script + args
        if self.whisper_exe_path.lower().endswith(".py"):
            program = sys.executable
            args = [self.whisper_exe_path] + whisper_args
        else:
            program = self.whisper_exe_path
            args = whisper_args

        self.process.readyReadStandardOutput.connect(self._handle_ready_read)
        self.process.finished.connect(self._handle_finished)

        # Log command representation
        cmd_repr = f"Executing: {program} " + " ".join([f'"{a}"' if ' ' in a else a for a in args])
        self.progress.emit(f"{cmd_repr}\n")

        self.process.start(program, args)

    def cancel(self):
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()

    def _handle_ready_read(self):
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        self._probe_backend(data)
        self.progress.emit(data)

    def _probe_backend(self, data):
        """Detect the ACTUAL loaded compute backend from whisper.cpp output.
        Reliable v1.9.x lines: 'whisper_backend_init_gpu: using Vulkan0 backend'
        and 'whisper_backend_init_gpu: no GPU found'."""
        if self.detected_backend:
            return
        self._backend_probe_buffer += data
        buf = self._backend_probe_buffer
        if "using Vulkan" in buf:
            for line in buf.splitlines():
                if "using Vulkan" in line and "backend" in line:
                    name = line.split("using", 1)[1].replace("backend", "").strip()
                    self.detected_backend = f"Vulkan ({name})"
                    self.backend_detected.emit(self.detected_backend)
                    return
        if "no GPU found" in buf or "loaded CPU backend" in buf and "loaded Vulkan backend" not in buf:
            if "no GPU found" in buf:
                self.detected_backend = "CPU"
                self.backend_detected.emit(self.detected_backend)
        # Keep the probe buffer bounded.
        if len(self._backend_probe_buffer) > 20000:
            self._backend_probe_buffer = self._backend_probe_buffer[-5000:]

    def _handle_finished(self, exit_code, exit_status):
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.finished.emit(True, "")
        else:
            self.finished.emit(False, f"whisper-cli exited with status {exit_status} and code {exit_code}")

