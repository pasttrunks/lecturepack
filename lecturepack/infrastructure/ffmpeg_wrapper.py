import os
import sys
import json
import shutil
import subprocess
from PySide6.QtCore import QProcess, QObject, Signal

class FFmpegWrapper(QObject):
    # Signals for asynchronous audio extraction
    progress = Signal(str)
    finished = Signal(bool, str) # success, error_message

    def __init__(self, config_manager=None):
        super().__init__()
        self.config_manager = config_manager
        self.ffmpeg_path = ""
        self.ffprobe_path = ""
        self.process = None
        self.detect_binaries()

    def detect_binaries(self):
        """Attempts to locate ffmpeg and ffprobe executables."""
        # 1. Check user-configured path
        if self.config_manager:
            ffmpeg_dir = self.config_manager.get("ffmpeg_dir")
            if ffmpeg_dir and os.path.isdir(ffmpeg_dir):
                ff = os.path.join(ffmpeg_dir, "ffmpeg.exe")
                fp = os.path.join(ffmpeg_dir, "ffprobe.exe")
                if os.path.exists(ff) and os.path.exists(fp):
                    self.ffmpeg_path = ff
                    self.ffprobe_path = fp
                    return

        # 2. Check project root bin/
        project_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "bin")
        ff = os.path.join(project_bin, "ffmpeg.exe")
        fp = os.path.join(project_bin, "ffprobe.exe")
        if os.path.exists(ff) and os.path.exists(fp):
            self.ffmpeg_path = ff
            self.ffprobe_path = fp
            return

        # 3. Check system PATH
        ff_sys = shutil.which("ffmpeg")
        fp_sys = shutil.which("ffprobe")
        if ff_sys and fp_sys:
            self.ffmpeg_path = ff_sys
            self.ffprobe_path = fp_sys

    def is_available(self):
        return bool(self.ffmpeg_path and self.ffprobe_path)

    def inspect_video(self, video_path):
        """Inspects the video file using ffprobe. Returns metadata dict or raises Exception."""
        if not self.ffprobe_path:
            raise FileNotFoundError("ffprobe.exe not found. Please install it or configure its path in settings.")

        # Run ffprobe synchronously as it is extremely fast
        args = [
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-print_format", "json",
            video_path
        ]

        if self.ffprobe_path.lower().endswith(".py"):
            cmd = [sys.executable, self.ffprobe_path] + args
        else:
            cmd = [self.ffprobe_path] + args

        # Use subprocess safely without shell=True
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed with error: {result.stderr}")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise ValueError(f"ffprobe output could not be parsed: {result.stdout}")

        # Extract relevant fields
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        format_info = data.get("format", {})

        metadata = {
            "duration": float(format_info.get("duration", 0)),
            "size_bytes": int(format_info.get("size", 0)),
            "width": int(video_stream.get("width", 0)) if video_stream else 0,
            "height": int(video_stream.get("height", 0)) if video_stream else 0,
            "fps": self._parse_fps(video_stream.get("avg_frame_rate", "0/1")),
            "video_codec": video_stream.get("codec_name", "unknown"),
            "audio_codec": audio_stream.get("codec_name", "none"),
        }
        return metadata

    def _parse_fps(self, fps_str):
        try:
            if "/" in fps_str:
                num, denom = map(float, fps_str.split("/"))
                return num / denom if denom != 0 else 0
            return float(fps_str)
        except Exception:
            return 0.0

    def start_audio_extraction(self, video_path, output_wav_path):
        """Asynchronously extracts 16 kHz mono WAV audio using QProcess."""
        if not self.ffmpeg_path:
            self.finished.emit(False, "ffmpeg.exe not found.")
            return

        os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)

        self.process = QProcess()
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        # ffmpeg -y -i <video> -acodec pcm_s16le -ac 1 -ar 16000 <output>
        ffmpeg_args = [
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            output_wav_path
        ]

        if self.ffmpeg_path.lower().endswith(".py"):
            program = sys.executable
            args = [self.ffmpeg_path] + ffmpeg_args
        else:
            program = self.ffmpeg_path
            args = ffmpeg_args

        self.process.readyReadStandardOutput.connect(self._handle_ready_read)
        self.process.finished.connect(self._handle_finished)

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
            self.finished.emit(False, f"ffmpeg exited with status {exit_status} and code {exit_code}")
