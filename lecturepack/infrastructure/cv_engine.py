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

    def __init__(self, video_path, crop_region, ignore_masks, preset_settings, job_paths):
        super().__init__()
        self.video_path = video_path
        self.crop_region = crop_region or {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
        self.ignore_masks = ignore_masks or []
        self.preset = preset_settings
        self.job_paths = job_paths
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

            t = 0.0
            while t < duration:
                if self._is_cancelled:
                    self.status_message.emit("Slide detection cancelled by user.")
                    self.finished.emit(False, "Cancelled", [])
                    return

                # Report progress
                percent = int((t / duration) * 100)
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
                # Safeguards
                cx = max(0, min(cx, w - 1))
                cy = max(0, min(cy, h - 1))
                cw = max(10, min(cw, w - cx))
                ch = max(10, min(ch, h - cy))
                
                cropped_frame = frame[cy:cy+ch, cx:cx+cw]

                # 2. Apply ignore masks (on the cropped frame coordinates)
                # Create mask of the same size as cropped frame
                mask = np.ones(cropped_frame.shape[:2], dtype=np.uint8) * 255
                for im in self.ignore_masks:
                    # ignore mask is in normalized coords of the full frame
                    # let's map them to the cropped frame coords
                    imx = int(im.get("x", 0.0) * w) - cx
                    imy = int(im.get("y", 0.0) * h) - cy
                    imw = int(im.get("width", 0.0) * w)
                    imh = int(im.get("height", 0.0) * h)
                    
                    # Intersect rectangle with cropped dimensions
                    ix1 = max(0, min(imx, cw))
                    iy1 = max(0, min(imy, ch))
                    ix2 = max(0, min(imx + imw, cw))
                    iy2 = max(0, min(imy + imh, ch))
                    
                    if ix2 > ix1 and iy2 > iy1:
                        mask[iy1:iy2, ix1:ix2] = 0

                # Clean frame by zeroing ignored regions
                masked_cropped = cropped_frame.copy()
                masked_cropped[mask == 0] = 0

                # 3. Downscale to 480px width (maintain aspect ratio)
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

                # Perform evaluation against last accepted frame
                is_accepted = False
                decision_reason = ""

                if last_accepted_frame is None:
                    # First frame is always accepted
                    is_accepted = True
                    decision_reason = "Initial frame"
                else:
                    # Compute dHash Hamming distance
                    curr_hash = compute_dhash(cleaned_frame)
                    dhash_dist = hamming_distance(curr_hash, last_accepted_hash)

                    dhash_reject = self.preset.get("dhash_reject", 3)
                    dhash_accept = self.preset.get("dhash_accept", 20)

                    if dhash_dist <= dhash_reject:
                        is_accepted = False
                        decision_reason = f"dHash reject (distance {dhash_dist} <= {dhash_reject})"
                    elif dhash_dist >= dhash_accept:
                        is_accepted = True
                        decision_reason = f"dHash accept (distance {dhash_dist} >= {dhash_accept})"
                    else:
                        # Stage 2: SSIM Confirmation
                        ssim_val = ssim(cleaned_frame, last_accepted_frame)
                        ssim_reject = self.preset.get("ssim_reject", 0.92)
                        ssim_accept = self.preset.get("ssim_accept", 0.75)

                        if ssim_val >= ssim_reject:
                            is_accepted = False
                            decision_reason = f"SSIM reject (val {ssim_val:.3f} >= {ssim_reject})"
                        elif ssim_val <= ssim_accept:
                            is_accepted = True
                            decision_reason = f"SSIM accept (val {ssim_val:.3f} <= {ssim_accept})"
                        else:
                            # Stage 3: Histogram + pixel diff tiebreaker
                            hist1 = cv2.calcHist([cleaned_frame], [0], None, [256], [0, 256])
                            hist2 = cv2.calcHist([last_accepted_frame], [0], None, [256], [0, 256])
                            cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
                            cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)
                            bhatt = cv2.compareHist(hist1, hist2, cv2.HISTCMP_BHATTACHARYYA)

                            diff = cv2.absdiff(cleaned_frame, last_accepted_frame)
                            pixel_diff_ratio = np.count_nonzero(diff > 30) / diff.size

                            hist_bhatt_accept = self.preset.get("hist_bhatt_accept", 0.25)
                            pixel_diff_accept = self.preset.get("pixel_diff_accept", 0.15)

                            if bhatt > hist_bhatt_accept or pixel_diff_ratio > pixel_diff_accept:
                                is_accepted = True
                                decision_reason = f"Stage 3 accept (Bhatt {bhatt:.3f} > {hist_bhatt_accept} or Diff {pixel_diff_ratio:.3f} > {pixel_diff_accept})"
                            else:
                                is_accepted = False
                                decision_reason = f"Stage 3 reject (Bhatt {bhatt:.3f}, Diff {pixel_diff_ratio:.3f})"

                if is_accepted:
                    # Trigger Stability Detection (Look ahead)
                    self.status_message.emit(f"Change detected at {t:.2f}s (Reason: {decision_reason}). Running stability check...")
                    
                    stability_window_sec = self.preset.get("stability_window_sec", 1.5)
                    stability_ssim_thresh = self.preset.get("stability_ssim", 0.97)
                    stability_max_wait_sec = self.preset.get("stability_max_wait_sec", 5.0)

                    stability_checks = int(stability_window_sec / 0.25)
                    max_checks = int(stability_max_wait_sec / 0.25)

                    stable_t = t
                    consecutive_stable = 0
                    
                    # Keep track of previous check frame
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
                            
                        # Preprocess check frame
                        check_cropped = check_frame[cy:cy+ch, cx:cx+cw]
                        check_masked = check_cropped.copy()
                        check_masked[mask == 0] = 0
                        check_resized = cv2.resize(check_masked, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                        check_gray = cv2.cvtColor(check_resized, cv2.COLOR_BGR2GRAY)
                        if blur_kernel > 0:
                            check_gray = cv2.GaussianBlur(check_gray, (blur_kernel, blur_kernel), 0)
                            
                        check_cleaned = check_gray
                        
                        # Compare check_cleaned vs prev_check_cleaned
                        chk_ssim = ssim(check_cleaned, prev_check_cleaned)
                        
                        if chk_ssim >= stability_ssim_thresh:
                            consecutive_stable += 1
                        else:
                            consecutive_stable = 0
                            
                        prev_check_cleaned = check_cleaned
                        stable_t = check_t
                        
                        if consecutive_stable >= stability_checks:
                            self.status_message.emit(f"Stabilized at {stable_t:.2f}s after {k * 0.25:.2f}s wait.")
                            break
                    
                    # Capture the stable frame
                    stable_frame_idx = int(stable_t * fps)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, stable_frame_idx)
                    stable_ret, stable_frame = cap.read()
                    if stable_ret and stable_frame is not None:
                        # Crop the final stable frame for save
                        final_cropped = stable_frame[cy:cy+ch, cx:cx+cw]
                        
                        # Reprocess for comparing against future slides
                        stable_masked = final_cropped.copy()
                        stable_masked[mask == 0] = 0
                        stable_resized = cv2.resize(stable_masked, (compare_w, compare_h), interpolation=cv2.INTER_AREA)
                        stable_gray = cv2.cvtColor(stable_resized, cv2.COLOR_BGR2GRAY)
                        if blur_kernel > 0:
                            stable_gray = cv2.GaussianBlur(stable_gray, (blur_kernel, blur_kernel), 0)
                        
                        cleaned_stable_frame = stable_gray
                        curr_hash = compute_dhash(cleaned_stable_frame)
                        
                        # Verify we didn't stabilize back to last_accepted_frame
                        if last_accepted_frame is not None:
                            verify_dist = hamming_distance(curr_hash, last_accepted_hash)
                            if verify_dist <= dhash_reject:
                                self.status_message.emit(f"Discarding change: stabilized back to previous state.")
                                t = stable_t + step_seconds
                                continue
                        
                        # Save candidate slide image
                        # Filename format: slide_<frame_number>_<timestamp_ms>.png
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
                            "image_filename": img_filename
                        }
                        candidates.append(candidate_info)
                        self.status_message.emit(f"Accepted candidate: {img_filename} at {candidate_info['timestamp_formatted']}")
                        
                        last_accepted_frame = cleaned_stable_frame
                        last_accepted_hash = curr_hash
                        t = stable_t  # Move time to stabilization point

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
