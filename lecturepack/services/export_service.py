import os
import base64
import json
import img2pdf
from PySide6.QtCore import QThread, Signal
from lecturepack.infrastructure.file_manager import FileManager
from lecturepack.infrastructure.cv_engine import datetime_from_seconds

class ExportService:
    def __init__(self, job, log_callback=None):
        self.job = job
        self.log_callback = log_callback

    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)

    def align_and_export(self):
        """Runs the alignment algorithm and generates all exports."""
        # 1. Load accepted slides
        self.log("Loading candidate decisions...")
        candidates_path = os.path.join(self.job.paths["root"], "candidates.json")
        candidates = FileManager.read_json_safe(candidates_path, [])
        accepted_slides = [c for c in candidates if c.get("decision") == "accepted"]

        if not accepted_slides:
            self.log("No accepted slides found. Using initial frame as fallback.")
            accepted_slides = [{
                "frame_number": 0,
                "timestamp_seconds": 0.0,
                "timestamp_formatted": "00:00:00.000",
                "decision": "accepted",
                "image_filename": ""
            }]

        # Sort chronologically
        accepted_slides.sort(key=lambda s: s["timestamp_seconds"])

        # Get video duration
        video_duration = self.job.source.get("duration", 65.0)

        # Calculate slide display intervals [start, end]
        slide_intervals = []
        for i, slide in enumerate(accepted_slides):
            start = slide["timestamp_seconds"]
            end = accepted_slides[i+1]["timestamp_seconds"] if i+1 < len(accepted_slides) else video_duration
            slide_intervals.append({
                "slide": slide,
                "start": start,
                "end": max(start, end)
            })

        # 2. Load transcript segments
        self.log("Parsing transcript segments...")
        transcript_json_path = os.path.join(self.job.paths["root"], "transcript", "raw.json")
        transcript_data = FileManager.read_json_safe(transcript_json_path, {})
        
        # Parse segments
        raw_segments = []
        if isinstance(transcript_data, dict):
            # whisper.cpp json format (check both nested and root level)
            transcription = transcript_data.get("result", {}).get("transcription", [])
            if not transcription and "transcription" in transcript_data:
                transcription = transcript_data["transcription"]
                
            for i, seg in enumerate(transcription):
                offsets = seg.get("offsets", {})
                start_sec = offsets.get("from", 0) / 1000.0
                end_sec = offsets.get("to", 0) / 1000.0
                text = seg.get("text", "").strip()
                raw_segments.append({
                    "id": i + 1,
                    "start": start_sec,
                    "end": end_sec,
                    "text": text
                })
        
        if not raw_segments:
            # Fallback to loading raw.txt if json is missing or empty
            raw_txt_path = os.path.join(self.job.paths["root"], "transcript", "raw.txt")
            if os.path.exists(raw_txt_path):
                with open(raw_txt_path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("[") and "->" in line:
                            try:
                                parts = line.split("]", 1)
                                ts_part = parts[0][1:]
                                text_part = parts[1].strip()
                                t1, t2 = ts_part.split("->")
                                def to_sec(s):
                                    s = s.strip()
                                    h, m, sec = s.split(":")
                                    return int(h)*3600 + int(m)*60 + float(sec)
                                start_sec = to_sec(t1)
                                end_sec = to_sec(t2)
                                raw_segments.append({
                                    "id": i + 1,
                                    "start": start_sec,
                                    "end": end_sec,
                                    "text": text_part
                                })
                            except Exception:
                                pass

        # Apply transcript corrections if edited.json exists
        edited_json_path = os.path.join(self.job.paths["transcript"], "edited.json")
        if os.path.exists(edited_json_path):
            edited_data = FileManager.read_json_safe(edited_json_path, {})
            for seg in raw_segments:
                seg_id_str = str(seg["id"])
                if seg_id_str in edited_data:
                    seg["text"] = edited_data[seg_id_str]

        # Sort segments
        raw_segments.sort(key=lambda s: s["start"])

        # 3. Alignment
        self.log(f"Aligning {len(raw_segments)} transcript segments to {len(slide_intervals)} slide intervals...")
        alignment = {i: [] for i in range(len(slide_intervals))}
        
        for seg in raw_segments:
            s_start, s_end = seg["start"], seg["end"]
            overlaps = []
            for interval in slide_intervals:
                overlap = max(0.0, min(s_end, interval["end"]) - max(s_start, interval["start"]))
                overlaps.append(overlap)
                
            max_val = max(overlaps)
            if max_val > 0:
                max_indices = [i for i, val in enumerate(overlaps) if val == max_val]
                assigned_idx = max_indices[0]
            else:
                midpoint = (s_start + s_end) / 2.0
                assigned_idx = 0
                for i, interval in enumerate(slide_intervals):
                    if interval["start"] <= midpoint <= interval["end"]:
                        assigned_idx = i
                        break
                else:
                    if midpoint < slide_intervals[0]["start"]:
                        assigned_idx = 0
                    else:
                        assigned_idx = len(slide_intervals) - 1
                        
            alignment[assigned_idx].append(seg)

        # Ensure every slide gets at least one segment
        for idx, interval in enumerate(slide_intervals):
            if not alignment[idx]:
                alignment[idx].append({
                    "id": -1,
                    "start": interval["start"],
                    "end": interval["end"],
                    "text": "[No dialogue spoken during this slide]"
                })

        aligned_data = []
        for idx, interval in enumerate(slide_intervals):
            aligned_data.append({
                "slide_index": idx + 1,
                "timestamp_seconds": interval["slide"]["timestamp_seconds"],
                "timestamp_formatted": interval["slide"]["timestamp_formatted"],
                "image_filename": interval["slide"]["image_filename"],
                "segments": alignment[idx]
            })

        aligned_json_path = os.path.join(self.job.paths["root"], "transcript", "aligned.json")
        FileManager.write_json_atomic(aligned_json_path, aligned_data)

        # 4. Generate Exports
        exports_dir = self.job.paths["exports"]
        os.makedirs(exports_dir, exist_ok=True)

        # 4.1 Slides PDF
        pdf_path = os.path.join(exports_dir, "slides.pdf")
        self.log(f"Compiling slide PDF to: {pdf_path}")
        image_paths = []
        for slide in accepted_slides:
            if slide["image_filename"]:
                img_p = os.path.join(self.job.paths["candidates"], slide["image_filename"])
                if os.path.exists(img_p):
                    image_paths.append(img_p)

        if image_paths:
            with open(pdf_path, "wb") as f:
                f.write(img2pdf.convert(image_paths))

        # 4.2 TXT
        self.log("Writing transcript TXT...")
        txt_path = os.path.join(exports_dir, "transcript.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            for seg in raw_segments:
                t1 = datetime_from_seconds(seg["start"])
                t2 = datetime_from_seconds(seg["end"])
                f.write(f"[{t1} -> {t2}] {seg['text']}\n")

        # 4.3 SRT
        self.log("Writing transcript SRT...")
        srt_path = os.path.join(exports_dir, "transcript.srt")
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(raw_segments):
                t1 = datetime_from_seconds(seg["start"]).replace(".", ",")
                t2 = datetime_from_seconds(seg["end"]).replace(".", ",")
                f.write(f"{i+1}\n{t1} --> {t2}\n{seg['text']}\n\n")

        # 4.4 JSON
        self.log("Writing transcript JSON...")
        json_path = os.path.join(exports_dir, "transcript.json")
        FileManager.write_json_atomic(json_path, raw_segments)

        # 4.5 HTML Study Pack
        html_path = os.path.join(exports_dir, "study-pack.html")
        self.log(f"Building self-contained HTML study pack: {html_path}")
        self._generate_html_study_pack(html_path, aligned_data)
        self.log("All exports completed successfully.")

    def _generate_html_study_pack(self, html_path, aligned_data):
        slides_html = []
        for entry in aligned_data:
            img_b64 = ""
            if entry["image_filename"]:
                img_p = os.path.join(self.job.paths["candidates"], entry["image_filename"])
                if os.path.exists(img_p):
                    with open(img_p, 'rb') as img_f:
                        img_b64 = base64.b64encode(img_f.read()).decode('utf-8')

            segments_html = []
            for seg in entry["segments"]:
                t_str = datetime_from_seconds(seg["start"])
                segments_html.append(f"""
                <div class="transcript-line">
                    <span class="timestamp" title="Timestamp">{t_str}</span>
                    <span class="text">{seg['text']}</span>
                </div>
                """)

            img_tag = f'<img src="data:image/png;base64,{img_b64}" alt="Slide {entry["slide_index"]}">' if img_b64 else '<div class="no-image">No Slide Image</div>'

            slides_html.append(f"""
            <div class="slide-block" id="slide-{entry['slide_index']}">
                <div class="slide-header">Slide {entry['slide_index']} - Time: {entry['timestamp_formatted']}</div>
                <div class="slide-content">
                    <div class="slide-image-wrapper">
                        {img_tag}
                    </div>
                    <div class="slide-transcript">
                        {"".join(segments_html)}
                    </div>
                </div>
            </div>
            """)

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Lecture Study Pack - {self.job.manifest.get('title', 'Lecture')}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f4f6f9;
            color: #333;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border-radius: 8px;
        }}
        h1 {{
            color: #1e3d59;
            border-bottom: 2px solid #ff6e40;
            padding-bottom: 10px;
        }}
        .video-note {{
            background: #eef1f6;
            padding: 10px;
            border-left: 4px solid #1e3d59;
            margin-bottom: 20px;
            font-size: 14px;
        }}
        .slide-block {{
            margin-bottom: 40px;
            border: 1px solid #ddd;
            border-radius: 6px;
            overflow: hidden;
            background: #fafafa;
        }}
        .slide-header {{
            background: #1e3d59;
            color: white;
            padding: 10px 15px;
            font-weight: bold;
            font-size: 16px;
        }}
        .slide-content {{
            display: flex;
            flex-direction: row;
        }}
        @media(max-width: 768px) {{
            .slide-content {{
                flex-direction: column;
            }}
        }}
        .slide-image-wrapper {{
            flex: 1.2;
            padding: 15px;
            background: #eaeaea;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .slide-image-wrapper img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ccc;
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        }}
        .slide-transcript {{
            flex: 1;
            padding: 15px;
            background: white;
            overflow-y: auto;
            max-height: 400px;
        }}
        .transcript-line {{
            margin-bottom: 12px;
            line-height: 1.5;
        }}
        .timestamp {{
            font-family: monospace;
            background: #ffe0b2;
            color: #e65100;
            padding: 2px 5px;
            border-radius: 3px;
            font-size: 13px;
            cursor: pointer;
            margin-right: 8px;
        }}
        .text {{
            font-size: 15px;
        }}
        .no-image {{
            color: #777;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Lecture Study Pack: {self.job.manifest.get('title', 'Lecture')}</h1>
        <div class="video-note">
            Original Video Path: <strong>{self.job.manifest.get('source', {}).get('original_path', '')}</strong><br>
            <em>Note: For offline compatibility, timestamp links display the slide interval. Open the video in your media player to seek to a specific time.</em>
        </div>
        <div class="slides-container">
            {"".join(slides_html)}
        </div>
    </div>
</body>
</html>
"""
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

class ExportWorker(QThread):
    progress = Signal(int)
    status_message = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self):
        try:
            service = ExportService(self.job, log_callback=self.status_message.emit)
            service.align_and_export()
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))
