"""Evidence classification only; real network/UI acceptance is an opt-in script."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT))
try:
    spec = importlib.util.spec_from_file_location("batch_gate", SCRIPT / "electron_batch_link_acceptance.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
finally:
    sys.path.remove(str(SCRIPT))


@pytest.fixture
def batch(tmp_path):
    urls = ["https://example.test/a.mp4", "https://example.test/b.mp4"]
    downloads = []
    for n, url in enumerate(urls):
        path = tmp_path / "downloads" / str(n) / "recording.mp4"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"unit-test fixture")
        job = tmp_path / "jobs" / str(n)
        job.mkdir(parents=True)
        (job / "manifest.json").write_text(json.dumps({"job_id": str(n), "title": str(n), "source": {"original_path": str(path)}}))
        (job / "source.json").write_text(json.dumps({"duration": 5, "width": 640}))
        downloads.append({"url": url, "status": "complete", "path": str(path)})
    (tmp_path / "downloads-state.json").write_text(json.dumps({"downloads": downloads}))
    return tmp_path, urls, downloads


def test_batch_evidence_accepts_real_persisted_status_and_distinct_job_paths(batch):
    root, urls, _ = batch
    evidence = gate.validate_batch(root, urls)
    assert [item["url"] for item in evidence] == urls
    assert [item["job_id"] for item in evidence] == ["0", "1"]
    assert all(item["bytes"] > 0 and len(item["sha256"]) == 64 for item in evidence)


@pytest.mark.parametrize("defect", ["missing_job", "failed_download", "empty_file", "wrong_order", "uninspected"])
def test_batch_evidence_rejects_incomplete_or_mismatched_imports(batch, defect):
    root, urls, downloads = batch
    if defect == "missing_job":
        (root / "jobs" / "1" / "manifest.json").unlink()
    elif defect == "failed_download":
        downloads[1]["status"] = "failed"
    elif defect == "empty_file":
        Path(downloads[1]["path"]).write_bytes(b"")
    elif defect == "wrong_order":
        downloads.reverse()
    else:
        (root / "jobs" / "1" / "source.json").write_text('{"duration": 0, "width": 0}')
    (root / "downloads-state.json").write_text(json.dumps({"downloads": downloads}))
    with pytest.raises(ValueError):
        gate.validate_batch(root, urls)
