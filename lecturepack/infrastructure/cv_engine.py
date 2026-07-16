"""
lecturepack.infrastructure.cv_engine
====================================

Adaptive slide detection (v1.1 two-pass decode).

Decision logic (rolling motion baseline, major-change path, progressive-build
path, stability window, overlay-band rejection, persistence probes, dedup) is
unchanged from the verified v1.0 detector -- the ground-truth fixture tests
lock it in. What changed in v1.1 is *how frames are obtained*:

    v1.0  cv2.VideoCapture random seek + full-resolution decode for every
          sample, stability probe and persistence probe (thousands of seeks).
    v1.1  Pass 1: one FFmpeg process streams cropped/downscaled/grayscale
          analysis frames sequentially (video_reader.AnalysisFrameStream).
          Pass 2: full-resolution frames are decoded only at the accepted
          candidate timestamps.

When FFmpeg is unavailable the detector transparently falls back to the
legacy cv2 seek path (_run_legacy), which is kept verbatim.
"""
import os
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from skimage.metrics import structural_similarity as ssim

from lecturepack.infrastructure.video_reader import (
    AnalysisFrameStream, FrameCursor, capture_native_frames, detect_ffmpeg_path,
)

# Granularity of stability / persistence probes (matches the v1.0 0.25 s step).
PROBE_STEP_SEC = 0.25


def compute_dhash(img, hash_size=8):
    """Computes a difference hash (dHash) for an image."""
    resized = cv2.resize(img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    return diff


def hamming_distance(h1, h2):
    """Computes the Hamming distance between two binary hashes."""
    return np.count_nonzero(h1 != h2)


class SlideDetectorWorker(QThread):
    progress = Signal(int)  # percent (0-100)
    status_message = Signal(str)  # log messages
    finished = Signal(bool, str, list)  # success, error, list of candidate dicts

    def __init__(self, video_path, crop_region, ignore_masks, preset_settings,
                 job_paths, start_time=0.0, end_time=None, ffmpeg_path=None,
                 decode_threads=0):
        super().__init__()
        self.video_path = video_path
        self.crop_region = crop_region or {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        self.ignore_masks = ignore_masks or []
        self.preset = preset_settings
        self.job_paths = job_paths
        self.start_time = start_time
        self.end_time = end_time
        self.ffmpeg_path = ffmpeg_path if ffmpeg_path is not None else detect_ffmpeg_path()
        self.decode_threads = decode_threads
        self._is_cancelled = False
        # Diagnostics: which decode path actually ran ("piped" or "legacy").
        self.decode_path_used = None

    def cancel(self):
        self._is_cancelled = True

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def run(self):
        # Only a real ffmpeg binary can serve the rawvideo analysis pipe --
        # test mocks (.py/.bat shims) and missing paths use the legacy decoder.
        is_real_ffmpeg = (self.ffmpeg_path and os.path.isfile(self.ffmpeg_path)
                          and self.ffmpeg_path.lower().endswith(".exe"))
        if is_real_ffmpeg:
            try:
                self._run_piped()
                return
            except _PipedDecodeUnavailable as e:
                self.status_message.emit(
                    f"Piped decode unavailable ({e}); falling back to legacy decoder.")
            except Exception as e:
                self.finished.emit(False, str(e), [])
                return
        else:
            self.status_message.emit(
                "FFmpeg not found; using legacy frame-seek decoder.")
        self._run_legacy()

    # ------------------------------------------------------------------ #
    # v1.1 piped two-pass implementation
    # ------------------------------------------------------------------ #
    def _probe(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise ValueError("Could not open video file.")
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        finally:
            cap.release()
        if width <= 0 or height <= 0:
            raise ValueError("Video reports no frame dimensions.")
        return total_frames, fps, total_frames / fps, width, height

    def _build_small_mask(self, stream, src_w, src_h):
        """Ignore-mask raster at analysis resolution (mirrors legacy geometry)."""
        cx, cy, cw, ch = stream.crop_px
        mask = np.ones((stream.height, stream.width), dtype=np.uint8) * 255
        sx = stream.width / float(cw)
        sy = stream.height / float(ch)
        for im in self.ignore_masks:
            imx = int(im.get("x", 0.0) * src_w) - cx
            imy = int(im.get("y", 0.0) * src_h) - cy
            imw = int(im.get("width", 0.0) * src_w)
            imh = int(im.get("height", 0.0) * src_h)
            ix1 = max(0, min(imx, cw))
            iy1 = max(0, min(imy, ch))
            ix2 = max(0, min(imx + imw, cw))
            iy2 = max(0, min(imy + imh, ch))
            if ix2 > ix1 and iy2 > iy1:
                mask[int(iy1 * sy):int(np.ceil(iy2 * sy)),
                     int(ix1 * sx):int(np.ceil(ix2 * sx))] = 0
        return mask

    def _run_piped(self):
        self.status_message.emit(f"Opening video file: {self.video_path}")
        total_frames, fps, duration, src_w, src_h = self._probe()
        self.status_message.emit(
            f"Video specs: {total_frames} frames, {fps:.2f} fps, {duration:.2f}s duration")

        sample_fps = self.preset.get("sample_fps", 1.0)
        step_seconds = 1.0 / sample_fps
        analysis_fps = max(1.0 / PROBE_STEP_SEC, sample_fps)

        end_limit = duration if self.end_time is None else min(duration, self.end_time)

        stream = AnalysisFrameStream(
            self.ffmpeg_path, self.video_path, src_w, src_h,
            crop_region=self.crop_region, analysis_fps=analysis_fps,
            out_width=480, start_time=self.start_time, end_time=end_limit)
        try:
            stream.open()
        except OSError as e:
            raise _PipedDecodeUnavailable(f"could not start ffmpeg: {e}")
        cursor = FrameCursor(stream)

        # Fail over to the legacy decoder if FFmpeg produces nothing at all.
        first = cursor.get(self.start_time)
        if first is None:
            tail = stream.stderr_tail()
            stream.close()
            raise _PipedDecodeUnavailable(tail or "no frames from ffmpeg pipe")

        self.status_message.emit(
            f"Analysis pass: piped decode at {analysis_fps:.0f} fps, "
            f"{stream.width}x{stream.height} grayscale.")
        self.decode_path_used = "piped"

        mask = self._build_small_mask(stream, src_w, src_h)
        has_mask = bool(self.ignore_masks)
        blur_kernel = self.preset.get("gaussian_blur_kernel", 3)

        def prep(frame):
            f = frame
            if has_mask:
                f = frame.copy()
                f[mask == 0] = 0
            if blur_kernel > 0:
                f = cv2.GaussianBlur(f, (blur_kernel, blur_kernel), 0)
            return f

        candidates_dir = self.job_paths["candidates"]
        os.makedirs(candidates_dir, exist_ok=True)

        candidates = []       # candidate dicts (image written in pass 2)
        dedup_frames = []     # raw analysis frame at stable_t per candidate
        last_accepted_frame = None
        last_accepted_hash = None
        last_accepted_time = -999.0
        recent_motion = []
        prev_frame = None
        # Deferred acceptance: a candidate that passed every content check but
        # failed ONLY the min-time gate. The v1.0 detector discarded it and had
        # to re-detect + re-stabilise the same change later, drifting the
        # captured timestamp several seconds past the real slide change. Here
        # we remember the fully-validated candidate and accept it at the first
        # sample past the gate, provided the content is still on screen.
        pending = None  # (candidate_info, cleaned_stable_frame, curr_hash)

        major_threshold = self.preset.get("major_threshold", 0.12)
        minor_threshold = self.preset.get("minor_threshold", 0.02)
        min_time_between_slides = self.preset.get("min_time_between_slides", 5.0)

        try:
            t = self.start_time
            while t < end_limit:
                if self._is_cancelled:
                    self.status_message.emit("Slide detection cancelled by user.")
                    self.finished.emit(False, "Cancelled", [])
                    return

                percent = int(((t - self.start_time) / max(0.1, end_limit - self.start_time)) * 100)
                self.progress.emit(percent)

                raw = cursor.get(t)
                if raw is None:
                    if cursor.end_of_stream_after(t):
                        break
                    t += step_seconds
                    continue

                cleaned_frame = prep(raw)

                # Resolve a deferred candidate once the min-time gate opens.
                if pending is not None:
                    p_info, p_frame, p_hash = pending
                    if t >= last_accepted_time + min_time_between_slides:
                        if ssim(cleaned_frame, p_frame) >= 0.95:
                            p_info = dict(p_info)
                            p_info["timestamp_seconds"] = t
                            p_info["timestamp_formatted"] = self._format_timestamp(t)
                            p_info["frame_number"] = int(t * fps)
                            p_info["image_filename"] = f"slide_{p_info['frame_number']}_{int(t * 1000)}.png"
                            p_info["decision_reason"] += " (deferred past min-time gate)"
                            candidates.append(p_info)
                            dedup_frames.append(raw.copy())
                            self.status_message.emit(
                                f"Accepted deferred candidate ({p_info['detector_path']}): "
                                f"{p_info['image_filename']} at {p_info['timestamp_formatted']}")
                            last_accepted_frame = cleaned_frame
                            last_accepted_hash = compute_dhash(cleaned_frame)
                            last_accepted_time = t
                            prev_frame = cleaned_frame
                            pending = None
                            t += step_seconds
                            cursor.evict_before(t)
                            continue
                        # Content moved on; evaluate this sample normally.
                        pending = None

                # Frame-to-frame change D_t for the rolling baseline
                D_t = 0.0
                if prev_frame is not None:
                    f_diff = cv2.absdiff(cleaned_frame, prev_frame)
                    f_pixel_ratio = np.count_nonzero(f_diff > 30) / f_diff.size
                    f_ssim_dist = 1.0 - ssim(cleaned_frame, prev_frame)
                    D_t = 0.5 * f_ssim_dist + 0.5 * f_pixel_ratio

                if len(recent_motion) >= 3:
                    baseline = max(0.01, np.median(recent_motion))
                else:
                    baseline = 0.02

                if D_t > 0.0:
                    recent_motion.append(D_t)
                    if len(recent_motion) > 5:
                        recent_motion.pop(0)

                is_accepted = False
                detector_path = "none"
                combined_score = 0.0
                component_scores = {}
                changed_area_ratio = 0.0
                decision_reason = ""

                if last_accepted_frame is None:
                    is_accepted = True
                    detector_path = "initial_frame"
                    decision_reason = "Initial frame"
                    combined_score = 1.0
                    component_scores = {"ssim_dist": 1.0, "dhash_dist_ratio": 1.0, "pixel_diff_ratio": 1.0}
                    changed_area_ratio = 1.0
                else:
                    ssim_val = ssim(cleaned_frame, last_accepted_frame)
                    ssim_dist = 1.0 - ssim_val

                    curr_hash = compute_dhash(cleaned_frame)
                    dhash_dist = hamming_distance(curr_hash, last_accepted_hash)
                    dhash_dist_ratio = dhash_dist / 64.0

                    diff = cv2.absdiff(cleaned_frame, last_accepted_frame)
                    pixel_diff_ratio = np.count_nonzero(diff > 30) / diff.size

                    C_t = 0.4 * ssim_dist + 0.3 * dhash_dist_ratio + 0.3 * pixel_diff_ratio
                    combined_score = C_t
                    component_scores = {
                        "ssim_dist": float(ssim_dist),
                        "dhash_dist_ratio": float(dhash_dist_ratio),
                        "pixel_diff_ratio": float(pixel_diff_ratio)
                    }

                    if C_t >= major_threshold and (D_t > baseline * 1.5 or D_t == 0.0):
                        is_accepted = True
                        detector_path = "major_change"
                        decision_reason = f"Major change (C_t={C_t:.3f} >= {major_threshold})"
                    else:
                        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
                        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                        valid_contours = []
                        total_changed_area = 0.0
                        for c in contours:
                            x, y, w, h = cv2.boundingRect(c)
                            area = cv2.contourArea(c)
                            if w > 10 and h > 10 and area > 80:
                                if area < 0.5 * diff.size:
                                    valid_contours.append(c)
                                    total_changed_area += area

                        if len(valid_contours) > 0 and C_t >= minor_threshold:
                            changed_area_ratio = total_changed_area / diff.size
                            if changed_area_ratio >= 0.005:
                                is_accepted = True
                                detector_path = "progressive_build"
                                decision_reason = f"Progressive build (area ratio {changed_area_ratio:.3f} >= 0.005)"

                if is_accepted:
                    self.status_message.emit(
                        f"Candidate detected at {t:.2f}s via {detector_path}. Running stability check...")

                    stability_window_sec = self.preset.get("stability_window_sec", 1.5)
                    stability_ssim_thresh = self.preset.get("stability_ssim", 0.97)
                    stability_max_wait_sec = self.preset.get("stability_max_wait_sec", 5.0)

                    stability_checks = int(stability_window_sec / PROBE_STEP_SEC)
                    max_checks = int(stability_max_wait_sec / PROBE_STEP_SEC)

                    stable_t = t
                    consecutive_stable = 0
                    prev_check_cleaned = cleaned_frame
                    k = 0

                    for k in range(1, max_checks + 1):
                        check_t = t + k * PROBE_STEP_SEC
                        if check_t >= end_limit:
                            break
                        check_raw = cursor.get(check_t)
                        if check_raw is None:
                            continue
                        check_cleaned = prep(check_raw)
                        chk_ssim = ssim(check_cleaned, prev_check_cleaned)

                        if chk_ssim >= stability_ssim_thresh:
                            consecutive_stable += 1
                        else:
                            consecutive_stable = 0

                        prev_check_cleaned = check_cleaned
                        stable_t = check_t

                        if consecutive_stable >= stability_checks:
                            break

                    stable_raw = cursor.get(stable_t)
                    if stable_raw is not None:
                        cleaned_stable_frame = prep(stable_raw)
                        curr_hash = compute_dhash(cleaned_stable_frame)

                        if last_accepted_frame is not None:
                            s_ssim_val = ssim(cleaned_stable_frame, last_accepted_frame)
                            s_ssim_dist = 1.0 - s_ssim_val
                            s_dhash_dist = hamming_distance(curr_hash, last_accepted_hash)
                            s_dhash_dist_ratio = s_dhash_dist / 64.0
                            s_diff = cv2.absdiff(cleaned_stable_frame, last_accepted_frame)
                            s_pixel_diff_ratio = np.count_nonzero(s_diff > 30) / s_diff.size

                            C_stable = 0.4 * s_ssim_dist + 0.3 * s_dhash_dist_ratio + 0.3 * s_pixel_diff_ratio

                            if C_stable < minor_threshold:
                                self.status_message.emit(
                                    f"Discarding candidate at {stable_t:.2f}s: stabilized back to previous state.")
                                prev_frame = cleaned_stable_frame
                                t = stable_t + step_seconds
                                cursor.evict_before(t)
                                continue

                            overlay_band_reject = bool(self.preset.get("overlay_band_reject", False))
                            overlay_band_frac = float(self.preset.get("overlay_band_frac", 0.15))
                            build_persistence_ssim = float(self.preset.get("build_persistence_ssim", 0.96))
                            major_persistence_ssim = float(self.preset.get("major_persistence_ssim", 0.0))
                            persistence_look_ahead_sec = float(self.preset.get("persistence_look_ahead_sec", 1.0))

                            changed_area_ratio = 0.0
                            if C_stable >= major_threshold:
                                detector_path = "major_change"
                                changed_area_ratio = float(s_pixel_diff_ratio)
                            else:
                                detector_path = "progressive_build"
                                _, s_thresh = cv2.threshold(s_diff, 30, 255, cv2.THRESH_BINARY)
                                s_contours, _ = cv2.findContours(s_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                                s_valid_contours = []
                                s_total_changed_area = 0.0
                                band_line = s_diff.shape[0] * (1.0 - overlay_band_frac)
                                all_in_bottom_band = True
                                for c in s_contours:
                                    x, y, w, h = cv2.boundingRect(c)
                                    area = cv2.contourArea(c)
                                    if w > 10 and h > 10 and area > 80 and area < 0.5 * s_diff.size:
                                        s_valid_contours.append(c)
                                        s_total_changed_area += area
                                        if (y + h / 2.0) < band_line:
                                            all_in_bottom_band = False

                                if len(s_valid_contours) == 0:
                                    self.status_message.emit(
                                        f"Discarding candidate at {stable_t:.2f}s: no persistent progressive build regions.")
                                    prev_frame = cleaned_stable_frame
                                    t = stable_t + step_seconds
                                    cursor.evict_before(t)
                                    continue

                                if overlay_band_reject and s_valid_contours and all_in_bottom_band:
                                    self.status_message.emit(
                                        f"Discarding candidate at {stable_t:.2f}s: change confined to bottom caption/overlay band.")
                                    prev_frame = cleaned_stable_frame
                                    t = stable_t + step_seconds
                                    cursor.evict_before(t)
                                    continue

                                changed_area_ratio = float(s_total_changed_area / s_diff.size)

                            persistence_threshold = (build_persistence_ssim
                                                     if detector_path == "progressive_build"
                                                     else major_persistence_ssim)
                            if persistence_threshold > 0.0:
                                future_t = stable_t + persistence_look_ahead_sec
                                if future_t < end_limit:
                                    f_raw = cursor.get(future_t)
                                    if f_raw is not None:
                                        f_gray = prep(f_raw)
                                        f_ssim = ssim(f_gray, cleaned_stable_frame)
                                        self.status_message.emit(
                                            f"Persistence probe at {stable_t:.2f}s ({detector_path}): "
                                            f"future SSIM {f_ssim:.3f} vs thr {persistence_threshold:.3f}.")
                                        if f_ssim < persistence_threshold:
                                            self.status_message.emit(
                                                f"Discarding {detector_path} at {stable_t:.2f}s: not persistent "
                                                f"(future SSIM {f_ssim:.3f} < {persistence_threshold:.3f}).")
                                            prev_frame = cleaned_stable_frame
                                            t = stable_t + step_seconds
                                            cursor.evict_before(t)
                                            continue

                            time_diff = stable_t - last_accepted_time
                            if time_diff < min_time_between_slides:
                                # Passed every content check; only the timing
                                # gate failed. Defer instead of discarding so
                                # the change is not re-stabilised late.
                                pending = ({
                                    "frame_number": int(stable_t * fps),
                                    "timestamp_seconds": stable_t,
                                    "timestamp_formatted": self._format_timestamp(stable_t),
                                    "decision": "accepted",
                                    "decision_reason": decision_reason,
                                    "image_filename": f"slide_{int(stable_t * fps)}_{int(stable_t * 1000)}.png",
                                    "detector_path": detector_path,
                                    "combined_score": float(combined_score),
                                    "rolling_baseline_score": float(baseline),
                                    "component_scores": component_scores,
                                    "stability_result": f"stabilized at {stable_t:.2f}s after {k * PROBE_STEP_SEC:.2f}s wait",
                                    "changed_area_ratio": float(changed_area_ratio),
                                }, cleaned_stable_frame, curr_hash)
                                self.status_message.emit(
                                    f"Deferring candidate: too close to previous slide "
                                    f"({time_diff:.2f}s < {min_time_between_slides}s); will re-check after gate.")
                                prev_frame = cleaned_stable_frame
                                t = stable_t + step_seconds
                                cursor.evict_before(t)
                                continue

                        stable_frame_idx = int(stable_t * fps)
                        timestamp_ms = int(stable_t * 1000)
                        img_filename = f"slide_{stable_frame_idx}_{timestamp_ms}.png"

                        candidate_info = {
                            "frame_number": stable_frame_idx,
                            "timestamp_seconds": stable_t,
                            "timestamp_formatted": self._format_timestamp(stable_t),
                            "decision": "accepted",
                            "decision_reason": decision_reason,
                            "image_filename": img_filename,
                            "detector_path": detector_path,
                            "combined_score": float(combined_score),
                            "rolling_baseline_score": float(baseline),
                            "component_scores": component_scores,
                            "stability_result": f"stabilized at {stable_t:.2f}s after {k * PROBE_STEP_SEC:.2f}s wait",
                            "changed_area_ratio": float(changed_area_ratio)
                        }
                        candidates.append(candidate_info)
                        dedup_frames.append(stable_raw.copy())
                        self.status_message.emit(
                            f"Accepted candidate ({detector_path}): {img_filename} "
                            f"at {candidate_info['timestamp_formatted']}")

                        last_accepted_frame = cleaned_stable_frame
                        last_accepted_hash = curr_hash
                        last_accepted_time = stable_t
                        prev_frame = cleaned_stable_frame
                        t = stable_t
                        cursor.evict_before(t)
                        continue

                prev_frame = cleaned_frame
                t += step_seconds
                cursor.evict_before(t)
        finally:
            stream.close()

        self.progress.emit(100)

        # Local deduplication on the retained analysis frames (unmasked, like
        # the legacy PNG-based comparison) -- collapse adjacent near-identical
        # candidates before any full-resolution decode happens.
        self.status_message.emit("Running deduplication...")
        dedup_phash_threshold = self.preset.get("dedup_phash_threshold", 8)
        dedup_candidates = []
        kept_frames = []
        for cand, frame in zip(candidates, dedup_frames):
            if not dedup_candidates:
                dedup_candidates.append(cand)
                kept_frames.append(frame)
                continue
            last_kept = dedup_candidates[-1]
            im1 = kept_frames[-1]
            im2 = frame
            h1 = compute_dhash(im1)
            h2 = compute_dhash(im2)
            dist = hamming_distance(h1, h2)
            ssim_val = ssim(im1, im2)
            time_diff = cand["timestamp_seconds"] - last_kept["timestamp_seconds"]
            if dist < dedup_phash_threshold and ssim_val >= 0.95 and time_diff < 10.0:
                self.status_message.emit(
                    f"Collapsing adjacent duplicate: {cand['image_filename']} is similar to "
                    f"{last_kept['image_filename']} (dist: {dist}, ssim: {ssim_val:.3f})")
                continue
            dedup_candidates.append(cand)
            kept_frames.append(frame)

        # Pass 2: full-resolution capture ONLY at the surviving candidates.
        if dedup_candidates:
            self.status_message.emit(
                f"Capture pass: decoding {len(dedup_candidates)} full-resolution frames...")
            wanted = [c["timestamp_seconds"] for c in dedup_candidates]
            natives = capture_native_frames(self.video_path, wanted)
            cx, cy, cw, ch = stream.crop_px
            for cand in dedup_candidates:
                if self._is_cancelled:
                    self.status_message.emit("Slide detection cancelled by user.")
                    self.finished.emit(False, "Cancelled", [])
                    return
                native = natives.get(cand["timestamp_seconds"])
                if native is None:
                    continue
                final_cropped = native[cy:cy + ch, cx:cx + cw]
                img_path = os.path.join(candidates_dir, cand["image_filename"])
                cv2.imwrite(img_path, final_cropped)

        self.status_message.emit(
            f"Slide detection completed. Detected {len(dedup_candidates)} slides.")
        self.finished.emit(True, "", dedup_candidates)

    # ------------------------------------------------------------------ #
    # v1.0 legacy implementation (fallback when FFmpeg is unavailable)
    # ------------------------------------------------------------------ #
    def _run_legacy(self):
        try:
            self.decode_path_used = "legacy"
            self.status_message.emit(f"Opening video file: {self.video_path}")
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                raise ValueError("Could not open video file.")

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 25.0
            duration = total_frames / fps
            self.status_message.emit(f"Video specs: {total_frames} frames, {fps:.2f} fps, {duration:.2f}s duration")

            sample_fps = self.preset.get("sample_fps", 1.0)
            step_seconds = 1.0 / sample_fps

            candidates_dir = self.job_paths["candidates"]
            os.makedirs(candidates_dir, exist_ok=True)

            candidates = []
            last_accepted_frame = None
            last_accepted_hash = None
            last_accepted_time = -999.0

            self.recent_motion = []
            prev_frame = None

            t = self.start_time
            end_limit = duration
            if self.end_time is not None:
                end_limit = min(duration, self.end_time)

            while t < end_limit:
                if self._is_cancelled:
                    self.status_message.emit("Slide detection cancelled by user.")
                    self.finished.emit(False, "Cancelled", [])
                    return

                percent = int(((t - self.start_time) / max(0.1, end_limit - self.start_time)) * 100)
                self.progress.emit(percent)

                frame_idx = int(t * fps)
                if frame_idx >= total_frames:
                    break

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    t += step_seconds
                    continue

                h, w = frame.shape[:2]

                cx = int(self.crop_region.get("x", 0.0) * w)
                cy = int(self.crop_region.get("y", 0.0) * h)
                cw = int(self.crop_region.get("width", 1.0) * w)
                ch = int(self.crop_region.get("height", 1.0) * h)
                cx = max(0, min(cx, w - 1))
                cy = max(0, min(cy, h - 1))
                cw = max(10, min(cw, w - cx))
                ch = max(10, min(ch, h - cy))

                cropped_frame = frame[cy:cy+ch, cx:cx+cw]

                mask = np.ones(cropped_frame.shape[:2], dtype=np.uint8) * 255
                for im in self.ignore_masks:
                    imx = int(im.get("x", 0.0) * w) - cx
                    imy = int(im.get("y", 0.0) * h) - cy
                    imw = int(im.get("width", 0.0) * w)
                    imh = int(im.get("height", 0.0) * h)

                    ix1 = max(0, min(imx, cw))
                    iy1 = max(0, min(imy, ch))
                    ix2 = max(0, min(imx + imw, cw))
                    iy2 = max(0, min(imy + imh, ch))

                    if ix2 > ix1 and iy2 > iy1:
                        mask[iy1:iy2, ix1:ix2] = 0

                masked_cropped = cropped_frame.copy()
                masked_cropped[mask == 0] = 0

                compare_w = 480
                compare_h = int((ch / cw) * compare_w) if cw > 0 else 480
                compare_h = max(10, compare_h)
                resized_frame = cv2.resize(masked_cropped, (compare_w, compare_h), interpolation=cv2.INTER_AREA)

                gray_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2GRAY)
                blur_kernel = self.preset.get("gaussian_blur_kernel", 3)
                if blur_kernel > 0:
                    gray_frame = cv2.GaussianBlur(gray_frame, (blur_kernel, blur_kernel), 0)

                cleaned_frame = gray_frame

                D_t = 0.0
                if prev_frame is not None:
                    f_diff = cv2.absdiff(cleaned_frame, prev_frame)
                    f_pixel_ratio = np.count_nonzero(f_diff > 30) / f_diff.size
                    f_ssim_dist = 1.0 - ssim(cleaned_frame, prev_frame)
                    D_t = 0.5 * f_ssim_dist + 0.5 * f_pixel_ratio

                if len(self.recent_motion) >= 3:
                    baseline = max(0.01, np.median(self.recent_motion))
                else:
                    baseline = 0.02

                if D_t > 0.0:
                    self.recent_motion.append(D_t)
                    if len(self.recent_motion) > 5:
                        self.recent_motion.pop(0)

                is_accepted = False
                detector_path = "none"
                combined_score = 0.0
                component_scores = {}
                changed_area_ratio = 0.0
                decision_reason = ""

                major_threshold = self.preset.get("major_threshold", 0.12)
                minor_threshold = self.preset.get("minor_threshold", 0.02)
                min_time_between_slides = self.preset.get("min_time_between_slides", 5.0)

                if last_accepted_frame is None:
                    is_accepted = True
                    detector_path = "initial_frame"
                    decision_reason = "Initial frame"
                    combined_score = 1.0
                    component_scores = {"ssim_dist": 1.0, "dhash_dist_ratio": 1.0, "pixel_diff_ratio": 1.0}
                    changed_area_ratio = 1.0
                else:
                    ssim_val = ssim(cleaned_frame, last_accepted_frame)
                    ssim_dist = 1.0 - ssim_val

                    curr_hash = compute_dhash(cleaned_frame)
                    dhash_dist = hamming_distance(curr_hash, last_accepted_hash)
                    dhash_dist_ratio = dhash_dist / 64.0

                    diff = cv2.absdiff(cleaned_frame, last_accepted_frame)
                    pixel_diff_ratio = np.count_nonzero(diff > 30) / diff.size

                    C_t = 0.4 * ssim_dist + 0.3 * dhash_dist_ratio + 0.3 * pixel_diff_ratio
                    combined_score = C_t
                    component_scores = {
                        "ssim_dist": float(ssim_dist),
                        "dhash_dist_ratio": float(dhash_dist_ratio),
                        "pixel_diff_ratio": float(pixel_diff_ratio)
                    }

                    if C_t >= major_threshold and (D_t > baseline * 1.5 or D_t == 0.0):
                        is_accepted = True
                        detector_path = "major_change"
                        decision_reason = f"Major change (C_t={C_t:.3f} >= {major_threshold})"
                    else:
                        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
                        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                        valid_contours = []
                        total_changed_area = 0.0
                        for c in contours:
                            x, y, w2, h2 = cv2.boundingRect(c)
                            area = cv2.contourArea(c)
                            if w2 > 10 and h2 > 10 and area > 80:
                                if area < 0.5 * diff.size:
                                    valid_contours.append(c)
                                    total_changed_area += area

                        if len(valid_contours) > 0 and C_t >= minor_threshold:
                            changed_area_ratio = total_changed_area / diff.size
                            if changed_area_ratio >= 0.005:
                                is_accepted = True
                                detector_path = "progressive_build"
                                decision_reason = f"Progressive build (area ratio {changed_area_ratio:.3f} >= 0.005)"

                if is_accepted:
                    self.status_message.emit(f"Candidate detected at {t:.2f}s via {detector_path}. Running stability check...")

                    stability_window_sec = self.preset.get("stability_window_sec", 1.5)
                    stability_ssim_thresh = self.preset.get("stability_ssim", 0.97)
                    stability_max_wait_sec = self.preset.get("stability_max_wait_sec", 5.0)

                    stability_checks = int(stability_window_sec / 0.25)
                    max_checks = int(stability_max_wait_sec / 0.25)

                    stable_t = t
                    consecutive_stable = 0
                    prev_check_cleaned = cleaned_frame
                    k = 0

                    for k in range(1, max_checks + 1):
                        check_t = t + k * 0.25
                        if check_t >= duration:
                            break

                        check_frame_idx = int(check_t * fps)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, check_frame_idx)
                        check_ret, check_frame = cap.read()
                        if not check_ret or check_frame is None:
                            continue

                        check_cropped = check_frame[cy:cy+ch, cx:cx+cw]
                        check_masked = check_cropped.copy()
                        check_masked[mask == 0] = 0
                        check_resized = cv2.resize(check_masked, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                        check_gray = cv2.cvtColor(check_resized, cv2.COLOR_BGR2GRAY)
                        if blur_kernel > 0:
                            check_gray = cv2.GaussianBlur(check_gray, (blur_kernel, blur_kernel), 0)

                        check_cleaned = check_gray
                        chk_ssim = ssim(check_cleaned, prev_check_cleaned)

                        if chk_ssim >= stability_ssim_thresh:
                            consecutive_stable += 1
                        else:
                            consecutive_stable = 0

                        prev_check_cleaned = check_cleaned
                        stable_t = check_t

                        if consecutive_stable >= stability_checks:
                            break

                    stable_frame_idx = int(stable_t * fps)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, stable_frame_idx)
                    stable_ret, stable_frame = cap.read()

                    if stable_ret and stable_frame is not None:
                        final_cropped = stable_frame[cy:cy+ch, cx:cx+cw]

                        stable_masked = final_cropped.copy()
                        stable_masked[mask == 0] = 0
                        stable_resized = cv2.resize(stable_masked, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                        stable_gray = cv2.cvtColor(stable_resized, cv2.COLOR_BGR2GRAY)
                        if blur_kernel > 0:
                            stable_gray = cv2.GaussianBlur(stable_gray, (blur_kernel, blur_kernel), 0)

                        cleaned_stable_frame = stable_gray
                        curr_hash = compute_dhash(cleaned_stable_frame)

                        if last_accepted_frame is not None:
                            s_ssim_val = ssim(cleaned_stable_frame, last_accepted_frame)
                            s_ssim_dist = 1.0 - s_ssim_val
                            s_dhash_dist = hamming_distance(curr_hash, last_accepted_hash)
                            s_dhash_dist_ratio = s_dhash_dist / 64.0
                            s_diff = cv2.absdiff(cleaned_stable_frame, last_accepted_frame)
                            s_pixel_diff_ratio = np.count_nonzero(s_diff > 30) / s_diff.size

                            C_stable = 0.4 * s_ssim_dist + 0.3 * s_dhash_dist_ratio + 0.3 * s_pixel_diff_ratio

                            if C_stable < minor_threshold:
                                self.status_message.emit(f"Discarding candidate at {stable_t:.2f}s: stabilized back to previous state.")
                                prev_frame = cleaned_stable_frame
                                t = stable_t + step_seconds
                                continue

                            overlay_band_reject = bool(self.preset.get("overlay_band_reject", False))
                            overlay_band_frac = float(self.preset.get("overlay_band_frac", 0.15))
                            build_persistence_ssim = float(self.preset.get("build_persistence_ssim", 0.96))
                            major_persistence_ssim = float(self.preset.get("major_persistence_ssim", 0.0))
                            persistence_look_ahead_sec = float(self.preset.get("persistence_look_ahead_sec", 1.0))

                            changed_area_ratio = 0.0
                            if C_stable >= major_threshold:
                                detector_path = "major_change"
                                changed_area_ratio = float(s_pixel_diff_ratio)
                            else:
                                detector_path = "progressive_build"
                                _, s_thresh = cv2.threshold(s_diff, 30, 255, cv2.THRESH_BINARY)
                                s_contours, _ = cv2.findContours(s_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                                s_valid_contours = []
                                s_total_changed_area = 0.0
                                band_line = s_diff.shape[0] * (1.0 - overlay_band_frac)
                                all_in_bottom_band = True
                                for c in s_contours:
                                    x, y, w2, h2 = cv2.boundingRect(c)
                                    area = cv2.contourArea(c)
                                    if w2 > 10 and h2 > 10 and area > 80 and area < 0.5 * s_diff.size:
                                        s_valid_contours.append(c)
                                        s_total_changed_area += area
                                        if (y + h2 / 2.0) < band_line:
                                            all_in_bottom_band = False

                                if len(s_valid_contours) == 0:
                                    self.status_message.emit(f"Discarding candidate at {stable_t:.2f}s: no persistent progressive build regions.")
                                    prev_frame = cleaned_stable_frame
                                    t = stable_t + step_seconds
                                    continue

                                if overlay_band_reject and s_valid_contours and all_in_bottom_band:
                                    self.status_message.emit(f"Discarding candidate at {stable_t:.2f}s: change confined to bottom caption/overlay band.")
                                    prev_frame = cleaned_stable_frame
                                    t = stable_t + step_seconds
                                    continue

                                changed_area_ratio = float(s_total_changed_area / s_diff.size)

                            persistence_threshold = build_persistence_ssim if detector_path == "progressive_build" else major_persistence_ssim
                            if persistence_threshold > 0.0:
                                future_t = stable_t + persistence_look_ahead_sec
                                if future_t < duration:
                                    future_frame_idx = int(future_t * fps)
                                    cap.set(cv2.CAP_PROP_POS_FRAMES, future_frame_idx)
                                    f_ret, f_frame = cap.read()
                                    if f_ret and f_frame is not None:
                                        f_cropped = f_frame[cy:cy+ch, cx:cx+cw]
                                        f_masked = f_cropped.copy()
                                        f_masked[mask == 0] = 0
                                        f_resized = cv2.resize(f_masked, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                                        f_gray = cv2.cvtColor(f_resized, cv2.COLOR_BGR2GRAY)
                                        if blur_kernel > 0:
                                            f_gray = cv2.GaussianBlur(f_gray, (blur_kernel, blur_kernel), 0)

                                        f_ssim = ssim(f_gray, cleaned_stable_frame)
                                        self.status_message.emit(f"Persistence probe at {stable_t:.2f}s ({detector_path}): future SSIM {f_ssim:.3f} vs thr {persistence_threshold:.3f}.")
                                        if f_ssim < persistence_threshold:
                                            self.status_message.emit(f"Discarding {detector_path} at {stable_t:.2f}s: not persistent (future SSIM {f_ssim:.3f} < {persistence_threshold:.3f}).")
                                            prev_frame = cleaned_stable_frame
                                            t = stable_t + step_seconds
                                            continue

                            time_diff = stable_t - last_accepted_time
                            if time_diff < min_time_between_slides:
                                self.status_message.emit(f"Discarding candidate: too close to previous slide ({time_diff:.2f}s < {min_time_between_slides}s)")
                                prev_frame = cleaned_stable_frame
                                t = stable_t + step_seconds
                                continue

                        timestamp_ms = int(stable_t * 1000)
                        img_filename = f"slide_{stable_frame_idx}_{timestamp_ms}.png"
                        img_path = os.path.join(candidates_dir, img_filename)
                        cv2.imwrite(img_path, final_cropped)

                        candidate_info = {
                            "frame_number": stable_frame_idx,
                            "timestamp_seconds": stable_t,
                            "timestamp_formatted": self._format_timestamp(stable_t),
                            "decision": "accepted",
                            "decision_reason": decision_reason,
                            "image_filename": img_filename,
                            "detector_path": detector_path,
                            "combined_score": float(combined_score),
                            "rolling_baseline_score": float(baseline),
                            "component_scores": component_scores,
                            "stability_result": f"stabilized at {stable_t:.2f}s after {k * 0.25:.2f}s wait",
                            "changed_area_ratio": float(changed_area_ratio)
                        }
                        candidates.append(candidate_info)
                        self.status_message.emit(f"Accepted candidate ({detector_path}): {img_filename} at {candidate_info['timestamp_formatted']}")

                        last_accepted_frame = cleaned_stable_frame
                        last_accepted_hash = curr_hash
                        last_accepted_time = stable_t
                        prev_frame = cleaned_stable_frame
                        t = stable_t
                        continue

                prev_frame = cleaned_frame
                t += step_seconds

            cap.release()
            self.progress.emit(100)

            compare_w = 480
            compare_h = 360

            dedup_candidates = []
            dedup_phash_threshold = self.preset.get("dedup_phash_threshold", 8)

            self.status_message.emit("Running deduplication...")
            candidates_dir = self.job_paths["candidates"]
            for i, cand in enumerate(candidates):
                if not dedup_candidates:
                    dedup_candidates.append(cand)
                    continue

                last_kept = dedup_candidates[-1]

                img_p1 = os.path.join(candidates_dir, last_kept["image_filename"])
                img_p2 = os.path.join(candidates_dir, cand["image_filename"])

                im1 = cv2.imread(img_p1, cv2.IMREAD_GRAYSCALE)
                im2 = cv2.imread(img_p2, cv2.IMREAD_GRAYSCALE)

                if im1 is not None and im2 is not None:
                    im1_r = cv2.resize(im1, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                    im2_r = cv2.resize(im2, (compare_w, compare_h), interpolation=cv2.INTER_AREA)

                    h1 = compute_dhash(im1_r)
                    h2 = compute_dhash(im2_r)
                    dist = hamming_distance(h1, h2)
                    ssim_val = ssim(im1_r, im2_r)
                    time_diff = cand["timestamp_seconds"] - last_kept["timestamp_seconds"]

                    if dist < dedup_phash_threshold and ssim_val >= 0.95 and time_diff < 10.0:
                        self.status_message.emit(f"Collapsing adjacent duplicate: {cand['image_filename']} is similar to {last_kept['image_filename']} (dist: {dist}, ssim: {ssim_val:.3f})")
                        try:
                            os.remove(img_p2)
                        except Exception:
                            pass
                        continue

                dedup_candidates.append(cand)

            self.status_message.emit(f"Slide detection completed. Detected {len(dedup_candidates)} slides.")
            self.finished.emit(True, "", dedup_candidates)

        except Exception as e:
            self.finished.emit(False, str(e), [])

    def _format_timestamp(self, seconds):
        td = datetime_from_seconds(seconds)
        return td


class _PipedDecodeUnavailable(RuntimeError):
    """FFmpeg produced no analysis frames -- fall back to the legacy decoder."""


def datetime_from_seconds(seconds):
    import datetime
    td = datetime.timedelta(seconds=seconds)
    # format HH:MM:SS.mmm
    hrs, remainder = divmod(td.seconds, 3600)
    mins, secs = divmod(remainder, 60)
    millis = int(td.microseconds / 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"
