import os
import re
import sys
from PySide6.QtCore import QProcess, QObject, Signal
from lecturepack.infrastructure.process_tree import terminate_qprocess_tree

# whisper.cpp prints each decoded segment to stdout in real time:
#   [00:00:12.340 --> 00:00:18.720]   And so the theorem follows...
# These lines stream long before the final raw.json/srt/txt files exist, so
# they are the source for the live (ephemeral, display-only) transcript view.
_SEGMENT_LINE_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*\S)\s*$")


def _segment_timestamp_to_ms(timestamp):
    """Convert a whisper.cpp 'HH:MM:SS.mmm' timestamp to milliseconds."""
    hours, minutes, rest = timestamp.split(":")
    seconds, millis = rest.split(".")
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


class LiveSegmentParser:
    """Incremental parser for whisper.cpp stdout segment lines.

    Bytes are buffered across reads so multi-byte UTF-8 characters split
    between chunks decode correctly, and both '\\n' and '\\r' terminate a
    line because whisper's stderr progress updates (merged into the same
    channel) use carriage returns without newlines. Only complete whisper
    segment lines produce dicts; everything else (progress, VAD, timings)
    is ignored. Pure Python, no Qt, so it is unit-testable in isolation.
    """

    def __init__(self):
        self._buffer = b""
        self.seq = 0

    def reset(self):
        self._buffer = b""
        self.seq = 0

    def feed(self, data):
        """Consume raw stdout bytes; return any newly complete segments."""
        self._buffer += data
        # The text after the last line terminator may still grow; only parse
        # up to the last terminator seen.
        last = max(self._buffer.rfind(b"\n"), self._buffer.rfind(b"\r"))
        if last < 0:
            # Bound memory for pathological no-newline output.
            if len(self._buffer) > 65536:
                self._buffer = self._buffer[-4096:]
            return []
        complete = self._buffer[:last]
        self._buffer = self._buffer[last + 1:]
        segments = []
        for raw_line in complete.replace(b"\r", b"\n").split(b"\n"):
            segment = self._parse_line(raw_line)
            if segment is not None:
                segments.append(segment)
        return segments

    def flush(self):
        """Parse any trailing unterminated line at end of process output."""
        remainder = self._buffer
        self._buffer = b""
        segment = self._parse_line(remainder)
        return [segment] if segment is not None else []

    def _parse_line(self, raw_line):
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            return None
        match = _SEGMENT_LINE_RE.match(line)
        if not match:
            return None
        self.seq += 1
        return {
            "start_ms": _segment_timestamp_to_ms(match.group(1)),
            "end_ms": _segment_timestamp_to_ms(match.group(2)),
            "text": match.group(3).strip(),
            "seq": self.seq,
        }


class WhisperWrapper(QObject):
    # Signals for asynchronous transcription
    progress = Signal(str)
    finished = Signal(bool, str) # success, error_message
    backend_detected = Signal(str)  # actual loaded backend, e.g. "Vulkan (Vulkan0)" or "CPU"
    # Live segment dicts parsed from stdout: {"start_ms", "end_ms", "text", "seq"}.
    # Ephemeral display data only; canonical transcripts still come from raw.json.
    segment_ready = Signal(dict)

    def __init__(self, whisper_exe_path=""):
        super().__init__()
        self.whisper_exe_path = whisper_exe_path
        self.process = None
        self.detected_backend = ""
        self._backend_probe_buffer = ""
        self.last_cancel_report = None
        self._segment_parser = LiveSegmentParser()

    def get_supported_flags(self):
        """Supported CLI options for the CURRENT executable. Uses the async
        WhisperCapabilityDetector cache when warm; otherwise probes the binary
        synchronously (fast `--help` run) so alternate engines (e.g. the
        Vulkan build) still get full-JSON output, threads, VAD and prompt
        flags instead of the minimal fallback set."""
        from lecturepack.infrastructure.whisper_detector import WhisperCapabilityDetector
        fallback = {"-oj", "-osrt", "-otxt"}
        if not self.whisper_exe_path or not os.path.exists(self.whisper_exe_path):
            return fallback
        try:
            stat = os.stat(self.whisper_exe_path)
            key = (self.whisper_exe_path, stat.st_size, stat.st_mtime)
        except Exception:
            return fallback
        if key in WhisperCapabilityDetector._cache:
            return WhisperCapabilityDetector._cache[key]["flags"]
        if self.whisper_exe_path.lower().endswith(".py"):
            return fallback  # test mocks: keep the historical minimal set
        try:
            import subprocess
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            result = subprocess.run(
                [self.whisper_exe_path, "--help"], capture_output=True,
                timeout=5, creationflags=creationflags)
            text = (result.stdout + result.stderr).decode("utf-8", errors="ignore")
            detector = WhisperCapabilityDetector.__new__(WhisperCapabilityDetector)
            caps = detector._parse_help_text(text)
            WhisperCapabilityDetector._cache[key] = caps
            return caps["flags"]
        except Exception:
            return fallback

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
        self._segment_parser.reset()
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
        """Stop only the exact process tree started for transcription."""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.last_cancel_report = terminate_qprocess_tree(self.process)

    def _handle_ready_read(self):
        raw = bytes(self.process.readAllStandardOutput().data())
        for segment in self._segment_parser.feed(raw):
            self.segment_ready.emit(segment)
        data = raw.decode('utf-8', errors='ignore')
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
        if ("no GPU found" in buf
                or ("loaded CPU backend" in buf and "loaded Vulkan backend" not in buf)):
            self.detected_backend = "CPU"
            self.backend_detected.emit(self.detected_backend)
        # Keep the probe buffer bounded.
        if len(self._backend_probe_buffer) > 20000:
            self._backend_probe_buffer = self._backend_probe_buffer[-5000:]

    def _handle_finished(self, exit_code, exit_status):
        # Emit a trailing segment line that ended without a newline.
        for segment in self._segment_parser.flush():
            self.segment_ready.emit(segment)
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.finished.emit(True, "")
        else:
            self.finished.emit(False, f"whisper-cli exited with status {exit_status} and code {exit_code}")
