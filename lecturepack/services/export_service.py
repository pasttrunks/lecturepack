import os
import base64
import json
import html
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
        """Runs the alignment algorithm and generates the exports appropriate to
        the job's product mode:

            study_pack       slides.pdf + transcript.* + study-pack.html
            transcript_only  transcript.* (no slide deck / study pack)
            slides_only      slides.pdf (no transcript)
        """
        from lecturepack.constants import (
            PRODUCT_MODE_STUDY_PACK, PRODUCT_MODE_TRANSCRIPT_ONLY,
            PRODUCT_MODE_SLIDES_ONLY,
        )
        mode = self.job.get_product_mode() if hasattr(self.job, "get_product_mode") else PRODUCT_MODE_STUDY_PACK
        want_slides = mode in (PRODUCT_MODE_STUDY_PACK, PRODUCT_MODE_SLIDES_ONLY)
        want_transcript = mode in (PRODUCT_MODE_STUDY_PACK, PRODUCT_MODE_TRANSCRIPT_ONLY)
        want_study_pack = mode == PRODUCT_MODE_STUDY_PACK
        self.log(f"Product mode: {mode} (slides={want_slides}, transcript={want_transcript}, study_pack={want_study_pack})")

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

        # 2. Load transcript segments through the v1.1 working layer, which
        # already applies user text edits and structural split/merge edits on
        # top of the immutable raw output. Old jobs without a working.json
        # load raw + legacy edited.json identically to v1.0.
        self.log("Parsing transcript segments...")
        from lecturepack.services import transcript_store
        raw_segments = [
            {"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"]}
            for s in transcript_store.load_working(self.job.paths)
        ]
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
        if want_slides:
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

        if want_transcript:
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

            # 4.4b Additional machine/readable formats (Markdown, JSONL, CSV, VTT),
            # all from the same corrected raw_segments and one serializer module.
            from lecturepack.services import transcript_formats as tf
            for fmt, fname in [("markdown", "transcript.md"), ("jsonl", "transcript.jsonl"),
                               ("csv", "transcript.csv"), ("vtt", "transcript.vtt")]:
                try:
                    content = tf.serialize(fmt, raw_segments, include_timestamps=True)
                    with open(os.path.join(exports_dir, fname), "w", encoding="utf-8") as f:
                        f.write(content)
                except Exception as e:
                    self.log(f"{fmt} export skipped: {e}")

            # 4.4c Section-structured markdown (topic headings + slides).
            try:
                sections = tf.build_sections(aligned_data)
                title = self.job.manifest.get("title", "Lecture")
                with open(os.path.join(exports_dir, "transcript.sections.md"), "w", encoding="utf-8") as f:
                    f.write(tf.sections_to_markdown(sections, include_timestamps=True, title=title))
            except Exception as e:
                self.log(f"sections export skipped: {e}")

            # 4.4d Normalized transcript (Layer 2) as a readable paragraph export,
            # sourced from the deterministic normalized.json produced in the pipeline.
            self._write_normalized_export(exports_dir)

        # 4.5 HTML Study Pack
        if want_study_pack:
            from lecturepack.services import study_service
            FileManager.write_json_atomic(
                os.path.join(exports_dir, "study-data.json"),
                study_service.export_payload(self.job))
            html_path = os.path.join(exports_dir, "study-pack.html")
            self.log(f"Building self-contained HTML study pack: {html_path}")
            self._generate_html_study_pack(html_path, aligned_data)
            study_pdf_path = os.path.join(exports_dir, "study-pack.pdf")
            self.log(f"Building PDF study pack: {study_pdf_path}")
            self._generate_pdf_study_pack(study_pdf_path, aligned_data)
        self.log("All exports completed successfully.")

    def _write_normalized_export(self, exports_dir):
        """Write transcript.normalized.txt from the Layer-2 normalized.json when
        present. Paragraph-grouped, deterministic; proves the layered transcript
        model reaches the exported artifacts. Best-effort and never fatal."""
        try:
            normalized_path = os.path.join(self.job.paths["transcript"], "normalized.json")
            if not os.path.exists(normalized_path):
                return
            data = FileManager.read_json_safe(normalized_path, {})
            segs = {int(s["id"]): s for s in data.get("segments", [])}
            paragraphs = data.get("paragraphs", [])
            out_path = os.path.join(exports_dir, "transcript.normalized.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                if paragraphs:
                    for para in paragraphs:
                        text = " ".join(segs[i]["text"] for i in para if i in segs).strip()
                        if text:
                            f.write(text + "\n\n")
                else:
                    for s in data.get("segments", []):
                        f.write(s.get("text", "") + "\n")
            self.log(f"Wrote normalized transcript: {out_path}")
        except Exception as e:
            self.log(f"Normalized export skipped: {e}")

    def _generate_html_study_pack(self, html_path, aligned_data):
        from lecturepack.services import study_service
        study = study_service.load_study_data(self.job)
        slide_study = study["bookmarked_slides"]
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
                    <span class="text">{html.escape(str(seg['text']))}</span>
                </div>
                """)

            img_tag = f'<img src="data:image/png;base64,{img_b64}" alt="Slide {entry["slide_index"]}">' if img_b64 else '<div class="no-image">No Slide Image</div>'
            key = study_service.slide_key(entry)
            annotation = slide_study.get(key, {})
            annotation_html = ""
            if annotation.get("bookmarked") or annotation.get("note"):
                bookmark = "★ Bookmarked" if annotation.get("bookmarked") else "Note"
                note = html.escape(str(annotation.get("note") or ""))
                annotation_html = (
                    '<div class="user-note"><strong>User-authored: '
                    f'{bookmark}</strong>{("<br>" + note) if note else ""}</div>')

            slides_html.append(f"""
            <div class="slide-block" id="slide-{entry['slide_index']}">
                <div class="slide-header">Slide {entry['slide_index']} - Time: {entry['timestamp_formatted']}</div>
                <div class="slide-content">
                    <div class="slide-image-wrapper">
                        {img_tag}
                    </div>
                    <div class="slide-transcript">
                        {"".join(segments_html)}
                        {annotation_html}
                    </div>
                </div>
            </div>
            """)

        title = html.escape(str(self.job.manifest.get('title', 'Lecture')))
        source_path = html.escape(str(
            self.job.manifest.get('source', {}).get('original_path', '')))
        section_bookmarks = sorted(
            study["bookmarked_sections"].values(),
            key=lambda entry: float(entry.get("start", 0.0)))
        section_items = "".join(
            f"<li>★ {datetime_from_seconds(float(entry.get('start', 0.0)))} — "
            f"{html.escape(str(entry.get('heading', 'Untitled section')))}</li>"
            for entry in section_bookmarks)
        study_summary = (
            '<section class="study-data"><h2>Your study bookmarks and notes</h2>'
            + (f"<ul>{section_items}</ul>" if section_items else
               "<p>No section bookmarks.</p>") + "</section>")
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Lecture Study Pack - {title}</title>
    <style>
        body {{
            font-family: 'Space Grotesk', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
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
        .study-data, .user-note {{
            background: #eff6ff;
            border-left: 4px solid #2563eb;
            padding: 12px;
            margin: 14px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Lecture Study Pack: {title}</h1>
        <div class="video-note">
            Original Video Path: <strong>{source_path}</strong><br>
            <em>Note: For offline compatibility, timestamp links display the slide interval. Open the video in your media player to seek to a specific time.</em>
        </div>
        {study_summary}
        <div class="slides-container">
            {"".join(slides_html)}
        </div>
    </div>
</body>
</html>
"""
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def _generate_pdf_study_pack(self, pdf_path, aligned_data):
        """Create a printable study pack with transcript and user annotations."""
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage,
            PageBreak,
        )
        from lecturepack.services import study_service

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "StudyTitle", parent=styles["Title"], alignment=TA_CENTER,
            textColor="#1e3d59")
        note_style = ParagraphStyle(
            "UserNote", parent=styles["BodyText"], backColor="#eff6ff",
            borderColor="#2563eb", borderWidth=1, borderPadding=8,
            spaceBefore=8, spaceAfter=8)
        story = [
            Paragraph(
                f"Lecture Study Pack: {html.escape(str(self.job.manifest.get('title', 'Lecture')))}",
                title_style),
            Paragraph("Transcript and slide content are source-derived. Bookmarks and notes are user-authored.",
                      styles["Italic"]),
            Spacer(1, 0.2 * inch),
        ]
        study = study_service.load_study_data(self.job)
        section_bookmarks = sorted(
            study["bookmarked_sections"].values(),
            key=lambda entry: float(entry.get("start", 0.0)))
        if section_bookmarks:
            story.append(Paragraph("User-authored section bookmarks", styles["Heading2"]))
            for entry in section_bookmarks:
                story.append(Paragraph(
                    f"Bookmarked {html.escape(datetime_from_seconds(float(entry.get('start', 0.0))))} — "
                    f"{html.escape(str(entry.get('heading', 'Untitled section')))}",
                    note_style))
            story.append(Spacer(1, 0.15 * inch))
        for entry in aligned_data:
            story.append(Paragraph(
                f"Slide {entry['slide_index']} — {html.escape(str(entry['timestamp_formatted']))}",
                styles["Heading2"]))
            image_name = entry.get("image_filename") or ""
            image_path = os.path.join(self.job.paths["candidates"], image_name)
            if image_name and os.path.exists(image_path):
                image = ReportLabImage(image_path)
                image._restrictSize(6.8 * inch, 4.6 * inch)
                story.extend([image, Spacer(1, 0.12 * inch)])
            annotation = study["bookmarked_slides"].get(
                study_service.slide_key(entry), {})
            if annotation.get("bookmarked") or annotation.get("note"):
                label = "★ Bookmarked" if annotation.get("bookmarked") else "Note"
                note = html.escape(str(annotation.get("note") or ""))
                story.append(Paragraph(
                    f"<b>User-authored: {label}</b>{('<br/>' + note) if note else ''}",
                    note_style))
            for segment in entry.get("segments", []):
                timestamp = datetime_from_seconds(float(segment.get("start", 0.0)))
                story.append(Paragraph(
                    f"<b>{html.escape(timestamp)}</b>  "
                    f"{html.escape(str(segment.get('text') or ''))}",
                    styles["BodyText"]))
            story.append(PageBreak())
        SimpleDocTemplate(
            pdf_path, pagesize=letter, rightMargin=0.6 * inch,
            leftMargin=0.6 * inch, topMargin=0.55 * inch,
            bottomMargin=0.55 * inch, title=str(self.job.manifest.get("title", "Lecture")),
        ).build(story)

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
