import os
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from skimage.metrics import structural_similarity as ssim

def compute_dhash(img, hash_size=8):
    """Computes a difference hash (dHash) for an image."""
    resized = cv2.resize(img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    return diff

def hamming_distance(h1, h2):
    """Computes the Hamming distance between two binary hashes."""
    return np.count_nonzero(h1 != h2)

class SlideDetectorWorker(QThread):
    progress = Signal(int) # percent (0-100)
    status_message = Signal(str) # log messages
    finished = Signal(bool, str, list) # success, error, list of candidate dicts

    def __init__(self, video_path, crop_region, ignore_masks, preset_settings, job_paths, start_time=0.0, end_time=None):
        super().__init__()
        self.video_path = video_path
        self.crop_region = crop_region or {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        self.ignore_masks = ignore_masks or []
        self.preset = preset_settings
        self.job_paths = job_paths
        self.start_time = start_time
        self.end_time = end_time
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
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

            # Prepare folders
            candidates_dir = self.job_paths["candidates"]
            os.makedirs(candidates_dir, exist_ok=True)

            candidates = []
            last_accepted_frame = None
            last_accepted_hash = None
            last_accepted_time = -999.0
            
            # Rolling window for local motion baseline
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

                # Report progress
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

                # 1. Crop frame
                cx = int(self.crop_region.get("x", 0.0) * w)
                cy = int(self.crop_region.get("y", 0.0) * h)
                cw = int(self.crop_region.get("width", 1.0) * w)
                ch = int(self.crop_region.get("height", 1.0) * h)
                cx = max(0, min(cx, w - 1))
                cy = max(0, min(cy, h - 1))
                cw = max(10, min(cw, w - cx))
                ch = max(10, min(ch, h - cy))
                
                cropped_frame = frame[cy:cy+ch, cx:cx+cw]

                # 2. Apply ignore masks
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

                # 3. Downscale to 480px width
                compare_w = 480
                compare_h = int((ch / cw) * compare_w) if cw > 0 else 480
                compare_h = max(10, compare_h)
                resized_frame = cv2.resize(masked_cropped, (compare_w, compare_h), interpolation=cv2.INTER_AREA)

                # 4. Convert to grayscale & Gaussian blur
                gray_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2GRAY)
                blur_kernel = self.preset.get("gaussian_blur_kernel", 3)
                if blur_kernel > 0:
                    gray_frame = cv2.GaussianBlur(gray_frame, (blur_kernel, blur_kernel), 0)

                cleaned_frame = gray_frame

                # Calculate frame-to-frame change D_t for rolling baseline
                D_t = 0.0
                if prev_frame is not None:
                    f_diff = cv2.absdiff(cleaned_frame, prev_frame)
                    f_pixel_ratio = np.count_nonzero(f_diff > 30) / f_diff.size
                    f_ssim_dist = 1.0 - ssim(cleaned_frame, prev_frame)
                    D_t = 0.5 * f_ssim_dist + 0.5 * f_pixel_ratio

                # Calculate rolling baseline
                if len(self.recent_motion) >= 3:
                    baseline = max(0.01, np.median(self.recent_motion))
                else:
                    baseline = 0.02

                # Store motion difference in history
                if D_t > 0.0:
                    self.recent_motion.append(D_t)
                    if len(self.recent_motion) > 5:
                        self.recent_motion.pop(0)

                # Evaluate candidate decision path
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
                    # Combined change score against last accepted slide
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

                    # A. Major change path (exceeds major threshold, stands out above local baseline)
                    if C_t >= major_threshold and (D_t > baseline * 1.5 or D_t == 0.0):
                        is_accepted = True
                        detector_path = "major_change"
                        decision_reason = f"Major change (C_t={C_t:.3f} >= {major_threshold})"
                    
                    # B. Progressive build path (small localized change)
                    else:
                        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
                        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        
                        valid_contours = []
                        total_changed_area = 0.0
                        for c in contours:
                            x, y, w, h = cv2.boundingRect(c)
                            area = cv2.contourArea(c)
                            # Pointer size and transient filter (width > 10, height > 10, area > 80 pixels)
                            if w > 10 and h > 10 and area > 80:
                                # Not full transition
                                if area < 0.5 * diff.size:
                                    valid_contours.append(c)
                                    total_changed_area += area

                        if len(valid_contours) > 0 and C_t >= minor_threshold:
                            changed_area_ratio = total_changed_area / diff.size
                            if changed_area_ratio >= 0.005:  # small content additions
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
                            
                            # Discard if stabilized back to previous frame
                            if C_stable < minor_threshold:
                                self.status_message.emit(f"Discarding candidate at {stable_t:.2f}s: stabilized back to previous state.")
                                prev_frame = cleaned_stable_frame
                                t = stable_t + step_seconds
                                continue

                            changed_area_ratio = 0.0
                            if C_stable >= major_threshold:
                                detector_path = "major_change"
                                changed_area_ratio = float(s_pixel_diff_ratio)
                            else:
                                detector_path = "progressive_build"
                                # Check persistent contours in stable frame
                                _, s_thresh = cv2.threshold(s_diff, 30, 255, cv2.THRESH_BINARY)
                                s_contours, _ = cv2.findContours(s_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                                
                                s_valid_contours = []
                                s_total_changed_area = 0.0
                                for c in s_contours:
                                    x, y, w, h = cv2.boundingRect(c)
                                    area = cv2.contourArea(c)
                                    if w > 10 and h > 10 and area > 80 and area < 0.5 * s_diff.size:
                                        s_valid_contours.append(c)
                                        s_total_changed_area += area
                                        
                                if len(s_valid_contours) == 0:
                                    self.status_message.emit(f"Discarding candidate at {stable_t:.2f}s: no persistent progressive build regions.")
                                    prev_frame = cleaned_stable_frame
                                    t = stable_t + step_seconds
                                    continue
                                    
                                changed_area_ratio = float(s_total_changed_area / s_diff.size)

                            # Progressive build future look-ahead persistence check
                            if detector_path == "progressive_build":
                                future_t = stable_t + 1.0
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
                                        if f_ssim < 0.96:
                                            self.status_message.emit(f"Discarding progressive build at {stable_t:.2f}s: not persistent (future SSIM {f_ssim:.3f} < 0.96).")
                                            prev_frame = cleaned_stable_frame
                                            t = stable_t + step_seconds
                                            continue

                            # Min slide time check
                            time_diff = stable_t - last_accepted_time
                            if time_diff < min_time_between_slides:
                                self.status_message.emit(f"Discarding candidate: too close to previous slide ({time_diff:.2f}s < {min_time_between_slides}s)")
                                prev_frame = cleaned_stable_frame
                                t = stable_t + step_seconds
                                continue

                        # Save candidate slide image
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

            # Local deduplication: collapse adjacent visually identical candidates
            dedup_candidates = []
            dedup_phash_threshold = self.preset.get("dedup_phash_threshold", 8)
            
            self.status_message.emit("Running deduplication...")
            for i, cand in enumerate(candidates):
                if not dedup_candidates:
                    dedup_candidates.append(cand)
                    continue
                
                # Compare against the last kept candidate
                last_kept = dedup_candidates[-1]
                
                # Load images
                img_p1 = os.path.join(candidates_dir, last_kept["image_filename"])
                img_p2 = os.path.join(candidates_dir, cand["image_filename"])
                
                im1 = cv2.imread(img_p1, cv2.IMREAD_GRAYSCALE)
                im2 = cv2.imread(img_p2, cv2.IMREAD_GRAYSCALE)
                
                if im1 is not None and im2 is not None:
                    # Downscale
                    im1_r = cv2.resize(im1, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                    im2_r = cv2.resize(im2, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                    
                    h1 = compute_dhash(im1_r)
                    h2 = compute_dhash(im2_r)
                    dist = hamming_distance(h1, h2)
                    ssim_val = ssim(im1_r, im2_r)
                    time_diff = cand["timestamp_seconds"] - last_kept["timestamp_seconds"]
                    
                    # Collapse if very similar and close in time (within 10 seconds)
                    if dist < dedup_phash_threshold and ssim_val >= 0.95 and time_diff < 10.0:
                        self.status_message.emit(f"Collapsing adjacent duplicate: {cand['image_filename']} is similar to {last_kept['image_filename']} (dist: {dist}, ssim: {ssim_val:.3f})")
                        # Delete collapsed image file
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

def datetime_from_seconds(seconds):
    import datetime
    td = datetime.timedelta(seconds=seconds)
    # format HH:MM:SS.mmm
    hrs, remainder = divmod(td.seconds, 3600)
    mins, secs = divmod(remainder, 60)
    millis = int(td.microseconds / 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"
