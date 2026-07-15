import sys
import json

def main():
    metadata = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 640,
                "height": 480,
                "avg_frame_rate": "25/1"
            },
            {
                "codec_type": "audio",
                "codec_name": "aac"
            }
        ],
        "format": {
            "duration": "65.0",
            "size": "1000000"
        }
    }
    print(json.dumps(metadata))

if __name__ == "__main__":
    main()
