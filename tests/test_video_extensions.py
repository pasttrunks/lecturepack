import os
from lecturepack.constants import SUPPORTED_VIDEO_EXTENSIONS


def test_m4v_in_supported_extensions():
    assert '.m4v' in SUPPORTED_VIDEO_EXTENSIONS


def test_m4v_path_accepted_by_drag_drop_filter():
    path = r"C:\Users\marsh\OneDrive\Desktop\UB\CL100\CL100 - Day 2 - Egypt and Archaeology.m4v"
    assert path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS)


def test_m4v_case_insensitive():
    path = "lecture.M4V"
    assert path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS)
    path = "lecture.M4v"
    assert path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS)


def test_qdialog_filter_includes_m4v():
    qt_filter = f"Video Files (*{' *'.join(SUPPORTED_VIDEO_EXTENSIONS)})"
    assert '*.m4v' in qt_filter
    for ext in SUPPORTED_VIDEO_EXTENSIONS:
        assert f'*{ext}' in qt_filter
