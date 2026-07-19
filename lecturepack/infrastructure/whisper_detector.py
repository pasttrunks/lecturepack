import os
import sys
from PySide6.QtCore import QObject, QProcess, Signal, QTimer

class WhisperCapabilityDetector(QObject):
    finished = Signal(str, dict)  # exe_path, result_dict

    _cache = {}  # static cache: (path, size, mtime) -> dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.exe_path = ""
        self.key = None
        self.timer = None
        self.output_buffer = ""

    def detect(self, exe_path):
        self.cancel()
        
        self.exe_path = exe_path
        if not exe_path or not os.path.exists(exe_path):
            self.finished.emit(exe_path, self._get_fallback_dict())
            return

        try:
            stat = os.stat(exe_path)
            self.key = (exe_path, stat.st_size, stat.st_mtime)
        except Exception:
            self.finished.emit(exe_path, self._get_fallback_dict())
            return

        if self.key in self._cache:
            self.finished.emit(exe_path, self._cache[self.key])
            return

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_ready_read)
        self.process.finished.connect(self._on_finished)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._on_timeout)

        if exe_path.lower().endswith(".py"):
            program = sys.executable
            args = [exe_path, "--help"]
        else:
            program = exe_path
            args = ["--help"]

        self.output_buffer = ""
        self.timer.start(3000)  # 3-second timeout
        self.process.start(program, args)

    def cancel(self):
        if self.timer:
            self.timer.stop()
            self.timer = None
        if self.process:
            try:
                self.process.readyReadStandardOutput.disconnect()
                self.process.finished.disconnect()
            except Exception:
                pass
            if self.process.state() == QProcess.ProcessState.Running:
                self.process.terminate()
                if not self.process.waitForFinished(500):
                    self.process.kill()
            self.process = None

    def _on_ready_read(self):
        if self.process:
            try:
                data = self.process.readAllStandardOutput().data()
                self.output_buffer += str(data, encoding="utf-8", errors="ignore")
            except Exception:
                pass

    def _on_finished(self, exit_code, exit_status):
        if self.timer:
            self.timer.stop()
            self.timer = None
        self._parse_output_and_finish()

    def _on_timeout(self):
        if self.process:
            try:
                self.process.readyReadStandardOutput.disconnect()
                self.process.finished.disconnect()
            except Exception:
                pass
            if self.process.state() == QProcess.ProcessState.Running:
                self.process.terminate()
                if not self.process.waitForFinished(500):
                    self.process.kill()
            self.process = None
        self._parse_output_and_finish()

    def _parse_output_and_finish(self):
        res = self._parse_help_text(self.output_buffer)
        if self.key:
            self._cache[self.key] = res
        self.finished.emit(self.exe_path, res)

    def _get_fallback_dict(self):
        return {
            "version": "Unknown",
            "backend": "CPU",
            "flags": {"-oj", "-osrt", "-otxt"}
        }

    def _parse_help_text(self, text):
        flags = set()
        for word in text.split():
            if word.startswith("-"):
                cleaned = word.strip("[],.:()")
                if "/" in cleaned:
                    flags.update(cleaned.split("/"))
                else:
                    flags.add(cleaned)
        
        for flag in ["--output-json-full", "-ojf", "--vad", "--vad-model", "-vm", "--vad-threshold", "-vt",
                     "--vad-min-speech-duration-ms", "-vspd", "--vad-min-silence-duration-ms", "-vsd",
                     "--prompt", "--carry-initial-prompt", "--threads", "-t"]:
            if flag in text:
                flags.add(flag)
                
        version = "Unknown"
        for line in text.splitlines():
            if "whisper.cpp version:" in line:
                version = line.split("whisper.cpp version:")[1].strip()
                break
        
        backend = "CPU"
        if "loaded CPU backend" in text:
            backend = "CPU"
        elif "loaded Vulkan backend" in text or "Vulkan" in text:
            backend = "Vulkan"
        elif "loaded CUDA backend" in text or "CUDA" in text:
            backend = "CUDA"

        if not flags:
            flags = self._get_fallback_dict()["flags"]

        return {
            "version": version,
            "backend": backend,
            "flags": flags
        }
