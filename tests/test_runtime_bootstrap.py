"""Wave-0 runner contracts consumed by the later bootstrap policy plan."""

import sys
from pathlib import Path

from lecturepack.infrastructure.runtime_validation import RuntimeValidator


def test_runner_captures_success_evidence_with_argument_array(tmp_path):
    script = tmp_path / "echo.py"
    script.write_text("print('backend model WAV processing')", encoding="utf-8")
    evidence = RuntimeValidator(timeout_ms=1_000).run(sys.executable, [str(script)])
    assert evidence.ok is True
    assert evidence.argv == [sys.executable, str(script)]
    assert evidence.exit_code == 0
    assert "processing" in evidence.stdout
    assert evidence.reason == "success"


def test_runner_captures_nonzero_evidence(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; print('failed', file=sys.stderr); sys.exit(7)", encoding="utf-8")
    evidence = RuntimeValidator(timeout_ms=1_000).run(sys.executable, [str(script)])
    assert evidence.ok is False
    assert evidence.exit_code == 7
    assert "failed" in evidence.stderr
    assert evidence.reason == "nonzero exit"


def test_runner_times_out_the_exact_hang_fixture():
    fixture = Path(__file__).parent / "fixtures" / "mock_runtime_hang.py"
    evidence = RuntimeValidator(timeout_ms=100).run(sys.executable, [str(fixture)])
    assert evidence.ok is False
    assert evidence.timed_out is True
    assert evidence.reason == "timeout"
    assert evidence.duration_ms >= 100
