"""Optional live-provider smoke test; excluded from ordinary validation."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lecturepack.services.ai_gateway import GatewayClient  # noqa: E402


@pytest.mark.real_provider
def test_real_gateway_returns_grounded_canonical_analysis():
    if os.environ.get("LECTUREPACK_RUN_REAL_AI_TEST") != "1":
        pytest.skip("set LECTUREPACK_RUN_REAL_AI_TEST=1 for the explicit live smoke")
    data_dir = Path(r"C:\LecturePackScratch\data\ai-study\real-provider-smoke")
    client = GatewayClient(data_dir)
    response = client.request("lecture_analysis", {
        "lecture": {
            "title": "Synthetic polar-bear smoke fixture",
            "duration_ms": 9000,
            "transcript_segment_count": 2,
            "accepted_slide_count": 0,
        },
        "transcript": [
            {"segment_id": "0", "start_ms": 0, "end_ms": 5000,
             "text": "Polar-bear fur is transparent and the skin beneath it is black."},
            {"segment_id": "1", "start_ms": 5000, "end_ms": 9000,
             "text": "Polar bears are marine mammals adapted to Arctic sea ice."},
        ],
        "slides": [],
    })
    analysis = response["result"]
    assert analysis.get("lecture_summary")
    assert analysis.get("concepts")
    assert all(item.get("lecture_sources") for item in analysis["concepts"])
