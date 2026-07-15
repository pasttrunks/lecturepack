import os
import sys
from PySide6.QtCore import QProcess, QObject, Signal

class WhisperWrapper(QObject):
    # Signals for asynchronous transcription
    progress = Signal(str)
    finished = Signal(bool, str) # success, error_message

    def __init__(self, whisper_exe_path=""):
        super().__init__()
        self.whisper_exe_path = whisper_exe_path
        self.process = None

    def start_transcription(self, audio_path, model_path, output_prefix, glossary=None):
        """Asynchronously runs the transcription using QProcess."""
        if not self.whisper_exe_path:
            self.finished.emit(False, "Whisper executable path is not set.")
            return

        self.process = QProcess()
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        # Build argument list
        # Standard whisper.cpp arguments:
        # whisper-cli -m model -f wav -oj -osrt -otxt -of output_prefix
        whisper_args = [
            "-m", model_path,
            "-f", audio_path,
            "-oj",
            "-osrt",
            "-otxt",
            "-of", output_prefix
        ]
        
        # Add glossary prompt if present
        if glossary:
            whisper_args.extend(["--prompt", glossary])

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
        self.progress.emit(data)

    def _handle_finished(self, exit_code, exit_status):
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.finished.emit(True, "")
        else:
            self.finished.emit(False, f"whisper-cli exited with status {exit_status} and code {exit_code}")
