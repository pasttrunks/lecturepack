import os
import sys
import json

def main():
    # Simple manual argument parsing
    args = sys.argv[1:]
    
    model = ""
    audio = ""
    output_prefix = ""
    
    i = 0
    while i < len(args):
        if args[i] == "-m" and i + 1 < len(args):
            model = args[i+1]
            i += 2
        elif args[i] == "-f" and i + 1 < len(args):
            audio = args[i+1]
            i += 2
        elif args[i] == "-of" and i + 1 < len(args):
            output_prefix = args[i+1]
            i += 2
        else:
            i += 1

    if not output_prefix:
        print("Error: Output file prefix (-of) not specified.", file=sys.stderr)
        sys.exit(1)

    print(f"Mock Whisper started with model: {model}, audio: {audio}")
    print(f"Writing mock transcriptions to prefix: {output_prefix}")

    # Create directory if needed
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    # 1. Write JSON
    json_data = {
        "systeminfo": "mock-whisper-cpp",
        "model": { "type": "mock-ggml" },
        "result": {
            "transcription": [
                { "offsets": { "from": 0, "to": 5000 }, "text": " Welcome to CS101 Lecture 3." },
                { "offsets": { "from": 5000, "to": 15000 }, "text": " Today we will cover Topic A and Topic B." },
                { "offsets": { "from": 20000, "to": 25000 }, "text": " In addition, we will look at Topic C." },
                { "offsets": { "from": 25000, "to": 33000 }, "text": " Here is a diagram showing the system structure." },
                { "offsets": { "from": 33000, "to": 50000 }, "text": " Let's look at some Python code for the main function." },
                { "offsets": { "from": 50000, "to": 55000 }, "text": " We can draw annotations on the whiteboard." },
                { "offsets": { "from": 60000, "to": 65000 }, "text": " Thank you for attending this lecture." }
            ]
        }
    }
    
    with open(f"{output_prefix}.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4)

    # 2. Write SRT
    srt_content = """1
00:00:00,000 --> 00:00:05,000
Welcome to CS101 Lecture 3.

2
00:00:05,000 --> 00:00:15,000
Today we will cover Topic A and Topic B.

3
00:00:20,000 --> 00:00:25,000
In addition, we will look at Topic C.

4
00:00:25,000 --> 00:00:33,000
Here is a diagram showing the system structure.

5
00:00:33,000 --> 00:00:50,000
Let's look at some Python code for the main function.

6
00:00:50,000 --> 00:00:55,000
We can draw annotations on the whiteboard.

7
00:01:00,000 --> 00:01:05,000
Thank you for attending this lecture.
"""
    with open(f"{output_prefix}.srt", "w", encoding="utf-8") as f:
        f.write(srt_content)

    # 3. Write TXT
    txt_content = """[00:00:00.000 -> 00:00:05.000] Welcome to CS101 Lecture 3.
[00:00:05.000 -> 00:00:15.000] Today we will cover Topic A and Topic B.
[00:00:20.000 -> 00:00:25.000] In addition, we will look at Topic C.
[00:00:25.000 -> 00:00:33.000] Here is a diagram showing the system structure.
[00:00:33.000 -> 00:00:50.000] Let's look at some Python code for the main function.
[00:00:50.000 -> 00:00:55.000] We can draw annotations on the whiteboard.
[00:01:00.000 -> 00:01:05.000] Thank you for attending this lecture.
"""
    with open(f"{output_prefix}.txt", "w", encoding="utf-8") as f:
        f.write(txt_content)

    print("Mock transcription finished successfully.")

if __name__ == "__main__":
    main()
