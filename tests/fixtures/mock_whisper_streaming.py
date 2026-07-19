"""Mock whisper-cli that streams segment lines on stdout like the real binary.

Used by test_live_transcript_streaming.py to drive the real WhisperWrapper
QProcess path end-to-end. Mimics whisper.cpp behavior: a couple of setup
lines, carriage-return progress rewrites interleaved with segment lines,
a non-ASCII segment (UTF-8 path), and a final segment line with no trailing
newline (exercises the wrapper's end-of-process flush). Also writes the
canonical raw.json/raw.srt/raw.txt outputs like mock_whisper.py.
"""
import json
import os
import sys


def _emit(text):
    """Write raw UTF-8 bytes like the real (C++) whisper-cli does."""
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def main():
    args = sys.argv[1:]

    output_prefix = ""
    i = 0
    while i < len(args):
        if args[i] == "-of" and i + 1 < len(args):
            output_prefix = args[i + 1]
            i += 2
        else:
            i += 1

    if not output_prefix:
        print("Error: Output file prefix (-of) not specified.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    _emit("whisper_init_from_file_with_params_no_state: loading model\n")
    # Progress rewrite terminated by \r, immediately followed by a segment
    # line -- the merged-channel pollution the parser must tolerate.
    _emit("whisper_print_progress: progress =  25%\r"
          "[00:00:00.000 --> 00:00:05.000]   Welcome to CS101 Lecture 3.\n")
    _emit("whisper_print_progress: progress =  60%\r"
          "[00:00:05.000 --> 00:00:15.000]   Today we cover café au lait economics.\n")
    # Final segment line deliberately left unterminated.
    _emit("[00:01:00.000 --> 00:01:05.000]   Thank you for attending.")

    json_data = {
        "systeminfo": "mock-whisper-cpp-streaming",
        "model": {"type": "mock-ggml"},
        "result": {
            "transcription": [
                {"offsets": {"from": 0, "to": 5000},
                 "text": " Welcome to CS101 Lecture 3."},
                {"offsets": {"from": 5000, "to": 15000},
                 "text": " Today we cover café au lait economics."},
                {"offsets": {"from": 60000, "to": 65000},
                 "text": " Thank you for attending."},
            ]
        },
    }
    with open(f"{output_prefix}.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4)
    with open(f"{output_prefix}.srt", "w", encoding="utf-8") as f:
        f.write("1\n00:00:00,000 --> 00:00:05,000\nWelcome to CS101 Lecture 3.\n")
    with open(f"{output_prefix}.txt", "w", encoding="utf-8") as f:
        f.write("[00:00:00.000 -> 00:00:05.000] Welcome to CS101 Lecture 3.\n")


if __name__ == "__main__":
    main()
