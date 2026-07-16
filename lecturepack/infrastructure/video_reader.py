"""
lecturepack.infrastructure.video_reader
=======================================

Fast, sequential analysis-frame access for the slide detector (v1.1).

The v1.0 detector decoded a full-resolution frame with a cv2.VideoCapture
random seek for every 1 fps sample, every 0.25 s stability probe, and every
+1 s persistence probe. On H.264/HEVC sources each seek forces the decoder
back to a keyframe, so a 71-minute lecture cost thousands of expensive
seek+decode cycles (measured: 98.5 s of a 156 s pipeline on a 6-minute
excerpt).

This module replaces that with a two-pass strategy:

    Pass 1 (analysis)  one FFmpeg process decodes the video ONCE, applying
                       crop -> downscale -> grayscale in-process, and streams
                       raw analysis frames over a pipe at a fixed analysis
                       fps. ``FrameCursor`` buffers a sliding window so the
                       detector can look ahead (stability / persistence
                       probes) and step back (resume after acceptance)
                       without ever re-seeking.

    Pass 2 (capture)   full-resolution frames are decoded ONLY at the final
                       accepted candidate timestamps (tens of seeks instead
                       of thousands).

Falls back cleanly: when FFmpeg is unavailable the caller keeps using the
legacy cv2 path (see cv_engine).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np


def detect_ffmpeg_path(config_manager=None) -> str:
    """Locate ffmpeg.exe: configured path, bundled next to the app, or PATH."""
    if config_manager is not None:
        p = config_manager.get("ffmpeg_exe", "")
        if p and os.path.isfile(p):
            return p
    # Frozen bundle: bin/ next to the executable. Dev: project-root bin/.
    if getattr(sys, "frozen", False):
        roots = [os.path.dirname(sys.executable)]
    else:
        roots = [os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]
    for root in roots:
        for cand in (os.path.join(root, "bin", "ffmpeg.exe"),
                     os.path.join(root, "ffmpeg.exe")):
            if os.path.isfile(cand):
                return cand
    return shutil.which("ffmpeg") or ""


class AnalysisFrameStream:
    """Streams cropped, downscaled, grayscale frames from one FFmpeg process.

    Frames are produced at a constant ``analysis_fps``; frame ``n`` has
    timestamp ``start_time + n / analysis_fps``.
    """

    def __init__(self, ffmpeg_path: str, video_path: str,
                 src_width: int, src_height: int,
                 crop_region: Optional[dict] = None,
                 analysis_fps: float = 4.0,
                 out_width: int = 480,
                 start_time: float = 0.0,
                 end_time: Optional[float] = None):
        self.ffmpeg_path = ffmpeg_path
        self.video_path = video_path
        self.analysis_fps = float(analysis_fps)
        self.start_time = float(start_time)
        self.end_time = end_time
        self.proc: Optional[subprocess.Popen] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stderr_tail: deque = deque(maxlen=40)

        crop = crop_region or {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        cx = int(crop.get("x", 0.0) * src_width)
        cy = int(crop.get("y", 0.0) * src_height)
        cw = int(crop.get("width", 1.0) * src_width)
        ch = int(crop.get("height", 1.0) * src_height)
        cx = max(0, min(cx, src_width - 1))
        cy = max(0, min(cy, src_height - 1))
        cw = max(10, min(cw, src_width - cx))
        ch = max(10, min(ch, src_height - cy))
        # Mirror the legacy pixel geometry so detector thresholds are unchanged.
        self.crop_px = (cx, cy, cw, ch)
        self.width = out_width
        self.height = max(10, int((ch / cw) * out_width)) if cw > 0 else out_width

        self._frame_bytes = self.width * self.height
        self._next_index = 0

    def open(self):
        cx, cy, cw, ch = self.crop_px
        vf = (f"fps={self.analysis_fps},crop={cw}:{ch}:{cx}:{cy},"
              f"scale={self.width}:{self.height}:flags=area,format=gray")
        args = [self.ffmpeg_path, "-hide_banner", "-nostats", "-loglevel", "error"]
        if self.start_time > 0.0:
            args += ["-ss", f"{self.start_time:.3f}"]
        args += ["-i", self.video_path]
        if self.end_time is not None:
            args += ["-t", f"{max(0.0, self.end_time - self.start_time):.3f}"]
        args += ["-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, creationflags=creationflags,
            bufsize=self._frame_bytes * 8)

        def _drain_stderr(pipe, tail):
            try:
                for line in iter(pipe.readline, b""):
                    tail.append(line.decode("utf-8", errors="ignore").rstrip())
            except Exception:
                pass

        self._stderr_thread = threading.Thread(
            target=_drain_stderr, args=(self.proc.stderr, self._stderr_tail),
            daemon=True)
        self._stderr_thread.start()
        return self

    def read(self) -> Optional[Tuple[float, np.ndarray]]:
        """Return (timestamp_seconds, gray_frame) or None at end of stream."""
        if self.proc is None or self.proc.stdout is None:
            return None
        buf = self.proc.stdout.read(self._frame_bytes)
        if not buf or len(buf) < self._frame_bytes:
            return None
        frame = np.frombuffer(buf, dtype=np.uint8).reshape(self.height, self.width)
        t = self.start_time + self._next_index / self.analysis_fps
        self._next_index += 1
        return t, frame

    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_tail)

    def close(self):
        if self.proc is not None:
            try:
                if self.proc.stdout:
                    self.proc.stdout.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
                except Exception:
                    pass
            self.proc = None


class FrameCursor:
    """Sliding-window, timestamp-addressed access over an AnalysisFrameStream.

    The detector's access pattern is *almost* monotonic: it samples forward,
    probes up to ~6.5 s ahead (stability window + persistence look-ahead), and
    after accepting a candidate resumes from the acceptance point. The cursor
    keeps a bounded deque of decoded frames covering that window so every
    request is served from memory.
    """

    def __init__(self, stream: AnalysisFrameStream, keep_behind_sec: float = 8.0):
        self.stream = stream
        self.keep_behind = keep_behind_sec
        self.frames: deque = deque()  # (t, frame) in ascending t
        self.exhausted = False
        self._half_step = 0.5 / stream.analysis_fps

    def _pull_until(self, t: float) -> None:
        while not self.exhausted and (not self.frames or self.frames[-1][0] < t - 1e-9):
            item = self.stream.read()
            if item is None:
                self.exhausted = True
                break
            self.frames.append(item)

    def get(self, t: float) -> Optional[np.ndarray]:
        """Frame whose timestamp is nearest to ``t`` (within half a step)."""
        self._pull_until(t + self._half_step)
        best = None
        best_dt = None
        for ft, frame in self.frames:
            dt = abs(ft - t)
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best = frame
            elif ft > t + 2 * self._half_step:
                break
        if best is not None and best_dt is not None and best_dt <= 2 * self._half_step:
            return best
        return None

    def evict_before(self, t: float) -> None:
        cutoff = t - self.keep_behind
        while self.frames and self.frames[0][0] < cutoff:
            self.frames.popleft()

    def end_of_stream_after(self, t: float) -> bool:
        """True when the stream is exhausted and no frame at/after t exists."""
        self._pull_until(t + self._half_step)
        return self.exhausted and (not self.frames or self.frames[-1][0] < t - self._half_step)


def capture_native_frames(video_path: str, timestamps: List[float]) -> Dict[float, np.ndarray]:
    """Pass 2: decode full-resolution frames only at the given timestamps.

    Uses a single cv2.VideoCapture with sorted seeks -- tens of seeks for the
    final candidates instead of thousands for every analysis sample.
    """
    import cv2
    out: Dict[float, np.ndarray] = {}
    if not timestamps:
        return out
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return out
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps <= 0:
            fps = 25.0
        for t in sorted(set(timestamps)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, frame = cap.read()
            if ret and frame is not None:
                out[t] = frame
    finally:
        cap.release()
    return out
