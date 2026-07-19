import os
import sys
import shutil
import subprocess
import numpy as np
import cv2

def create_synthetic_frames(output_avi, width=640, height=480, fps=25):
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    out = cv2.VideoWriter(output_avi, fourcc, fps, (width, height))
    
    total_duration = 65.0
    total_frames = int(total_duration * fps)

    # Pre-generate slide base frames
    # Slide 1: Title slide (blue background)
    slide1 = np.zeros((height, width, 3), dtype=np.uint8)
    slide1[:] = [150, 60, 30] # BGR Blueish
    cv2.putText(slide1, "CS101 Lecture 3", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
    cv2.putText(slide1, "Introduction to Algorithms", (50, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)

    # Slide 2: Bullets slide (white background)
    slide2 = np.ones((height, width, 3), dtype=np.uint8) * 255
    cv2.putText(slide2, "Today's Agenda", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 50), 2)
    cv2.putText(slide2, "- Topic A: Sorting Basics", (80, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2)
    cv2.putText(slide2, "- Topic B: Big-O Notation", (80, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2)

    # Slide 3: Progressive Build (Slide 2 + Topic C)
    slide3 = slide2.copy()
    cv2.putText(slide3, "- Topic C: Recursion Intro", (80, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 102, 204), 2)

    # Slide 4: Diagram (light gray background, shape diagram)
    slide4 = np.ones((height, width, 3), dtype=np.uint8) * 240
    cv2.putText(slide4, "System Components", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 50), 2)
    # Draw green circle
    cv2.circle(slide4, (200, 250), 60, (76, 175, 80), -1)
    # Draw yellow square
    cv2.rectangle(slide4, (380, 190), (500, 310), (0, 215, 255), -1)
    cv2.putText(slide4, "Client", (170, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(slide4, "Server", (410, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    # Slide 5: Code listing (dark background)
    slide5 = np.zeros((height, width, 3), dtype=np.uint8)
    slide5[:] = [30, 30, 30]
    cv2.putText(slide5, "Python Implementation", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    cv2.putText(slide5, "def main():", (80, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (76, 175, 80), 2)
    cv2.putText(slide5, "    print('Hello World')", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 215, 255), 2)

    # Slide 6: Whiteboard ink strokes (white background)
    slide6 = np.ones((height, width, 3), dtype=np.uint8) * 255
    cv2.putText(slide6, "Whiteboard Exercise", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 50), 2)

    # Slide 7: Final Slide (blue background)
    slide7 = np.zeros((height, width, 3), dtype=np.uint8)
    slide7[:] = [150, 60, 30]
    cv2.putText(slide7, "Thank You!", (180, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)

    for frame_num in range(total_frames):
        t = frame_num / fps
        frame = None

        if 0.0 <= t < 5.0:
            # 0:00 - 0:05 Title slide
            frame = slide1.copy()
        elif 5.0 <= t < 15.0:
            # 0:05 - 0:15 Slide 2 (bullets A, B)
            frame = slide2.copy()
        elif 15.0 <= t < 20.0:
            # 0:15 - 0:20 Slide 2 + mouse pointer moving
            frame = slide2.copy()
            # Draw mouse pointer (red circle) at moving coords
            px = int(300 + 15 * (t - 15.0))
            py = int(200 + 10 * (t - 15.0))
            cv2.circle(frame, (px, py), 8, (0, 0, 255), -1)
        elif 20.0 <= t < 25.0:
            # 0:20 - 0:25 Slide 3 (progressive build: bullets A, B, C)
            frame = slide3.copy()
        elif 25.0 <= t < 30.0:
            # 0:25 - 0:30 Slide 4 (diagram)
            frame = slide4.copy()
        elif 30.0 <= t < 33.0:
            # 0:30 - 0:33 Fade transition from Slide 4 to Slide 5
            alpha = (t - 30.0) / 3.0
            frame = cv2.addWeighted(slide4, 1.0 - alpha, slide5, alpha, 0)
        elif 33.0 <= t < 40.0:
            # 0:33 - 0:40 Slide 5 (code)
            frame = slide5.copy()
        elif 40.0 <= t < 45.0:
            # 0:40 - 0:45 Slide 5 + changing fake webcam noise in bottom-right (width=120, height=80)
            frame = slide5.copy()
            # Draw fake webcam noise
            noise = np.random.randint(0, 255, (80, 120, 3), dtype=np.uint8)
            frame[380:460, 500:620] = noise
        elif 45.0 <= t < 50.0:
            # 0:45 - 0:50 Slide 5 + changing captions in bottom 10%
            frame = slide5.copy()
            # Draw caption background
            cv2.rectangle(frame, (0, 430), (640, 480), (0, 0, 0), -1)
            # Display changing caption text
            cap_text = f"Live Captions: timestamp is {t:.1f}"
            cv2.putText(frame, cap_text, (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        elif 50.0 <= t < 55.0:
            # 0:50 - 0:55 Slide 6: Whiteboard progressive Ink stroke additions
            frame = slide6.copy()
            # Progressively draw line segments
            limit = int((t - 50.0) * 10) # draws more segments over time
            for i in range(limit):
                pt1 = (100 + i * 15, 200 + (i % 2) * 50)
                pt2 = (115 + i * 15, 200 + ((i + 1) % 2) * 50)
                cv2.line(frame, pt1, pt2, (0, 0, 0), 3)
        elif 55.0 <= t < 60.0:
            # 0:55 - 1:00 Slide 2 repeated
            frame = slide2.copy()
        else:
            # 1:00 - 1:05 Final slide
            frame = slide7.copy()

        out.write(frame)

    out.release()

def merge_audio(avi_path, out_mp4):
    """Integrates audio stream using FFmpeg if available."""
    # Find ffmpeg
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        # Check project root bin/
        proj_bin = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "bin", "ffmpeg.exe")
        if os.path.exists(proj_bin):
            ffmpeg_bin = proj_bin

    if not ffmpeg_bin:
        # If no ffmpeg, just rename avi to mp4 (though it won't have audio, allows fallback testing)
        print("Warning: ffmpeg not found. Mocking audio integration by copying video file.")
        shutil.copy(avi_path, out_mp4)
        return

    # Call ffmpeg to generate sine audio track and merge
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=65",
        "-i", avi_path,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        out_mp4
    ]
    
    subprocess.run(cmd, capture_output=True, check=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_test_video.py <output_path.mp4>")
        sys.exit(1)
        
    out_path = sys.argv[1]
    temp_avi = out_path + ".temp.avi"
    
    print("Generating frames...")
    create_synthetic_frames(temp_avi)
    print("Merging audio track...")
    merge_audio(temp_avi, out_path)
    
    if os.path.exists(temp_avi):
        os.remove(temp_avi)
    print(f"Generated synthetic lecture video: {out_path}")
