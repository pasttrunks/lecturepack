"""D-23: ISCC must receive already-collapsed absolute paths, never a
`packaging\\..\\` segment.

Root cause: `lecturepack.iss`'s `[Files] Source: "..\\dist\\LecturePack\\*"`
used to be resolved by ISCC relative to the .iss file's own directory
(`app/packaging/`), producing `...\\app\\packaging\\..\\dist\\LecturePack\\...`
internally -- 13 characters longer than the normalized
`...\\app\\dist\\LecturePack\\...`. Several bundled `torch` third-party
licence files sit at 247-250 characters on disk; that extra prefix pushed
them past Windows' 260-char MAX_PATH and ISCC aborted with "The system
cannot find the path specified", silently producing no Setup.exe.

These tests assert the *path construction* build.py hands to ISCC contains
no ".." segment. They deliberately do not invoke ISCC or PyInstaller --
launching a real Inno Setup compile is a multi-minute, environment-dependent
operation unsuitable for the fast unit-test suite. The real end-to-end proof
(Setup.exe actually produced) is captured once, by hand, in
`.planning/phases/01-clean-device-footprint-first-launch/01-EVIDENCE.md`.
"""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD_PY = REPO / "app" / "packaging" / "build.py"
ISS_PATH = REPO / "app" / "packaging" / "lecturepack.iss"

_spec = importlib.util.spec_from_file_location("_lp_build_iscc", BUILD_PY)
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def test_iscc_argv_contains_no_dotdot_segment():
    argv = build.build_iscc_argv("ISCC.exe", "0.9.0-beta.7")
    for arg in argv:
        assert ".." not in Path(arg.split("=", 1)[-1] if "=" in arg else arg).parts, (
            f"un-normalized path segment reached ISCC argv: {arg!r}"
        )


def test_iscc_argv_source_and_output_dirs_are_absolute():
    argv = build.build_iscc_argv("ISCC.exe", "0.9.0-beta.7")
    defines = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in argv if a.startswith("/D") and "=" in a}
    source_dir = Path(defines["/DSourceDir"])
    output_dir = Path(defines["/DOutputDir"])
    assert source_dir.is_absolute()
    assert output_dir.is_absolute()
    assert source_dir == (build.APP_DIR / "dist" / "LecturePack")
    assert output_dir == (build.APP_DIR / "dist" / "installer")


def test_iscc_argv_last_element_is_the_iss_script():
    argv = build.build_iscc_argv("ISCC.exe", "0.9.0-beta.7")
    assert argv[-1] == str(build.PKG_DIR / "lecturepack.iss")


def test_iscc_argv_carries_app_version_define():
    argv = build.build_iscc_argv("ISCC.exe", "0.9.0-beta.7")
    assert "/DAppVersion=0.9.0-beta.7" in argv


def test_iss_script_uses_sourcedir_and_outputdir_macros_not_hardcoded_dotdot():
    text = ISS_PATH.read_text(encoding="utf-8")
    assert 'Source: "{#SourceDir}\\*"' in text
    assert "OutputDir={#OutputDir}" in text
    # The only remaining literal ".." in the file must be inside the
    # #ifndef fallback defaults (for manual, defineless ISCC invocations),
    # not in the [Files]/[Setup] directives ISCC actually resolves paths from.
    files_section = text.split("[Files]", 1)[1]
    assert ".." not in files_section


def test_installer_removes_the_previous_payload_before_installing():
    """DEF-019 guard. [Files] uses `ignoreversion`, which adds and overwrites but
    NEVER removes, so without [InstallDelete] every upgrade accumulates whatever
    older versions shipped. That is how 2.0.3-over-2.0.2 left 12 stale packages
    in the frozen sidecar and killed `import yt_dlp` on upgrade while a FRESH
    install of the identical build was healthy.

    This section shipped in v2.0.3 and was then silently deleted by an unrelated
    edit to this file, which 1772 green tests did not notice. Hence this test.
    """
    text = ISS_PATH.read_text(encoding="utf-8")
    assert "[InstallDelete]" in text, (
        "[InstallDelete] is gone; upgrades will accumulate stale files again (DEF-019)"
    )
    section = text[text.index("[InstallDelete]"):]
    section = section[: section.index("\n[Files]")]
    for target in (
        r"{app}\resources\LecturePackSidecar",   # the frozen Python payload
        r"{app}\resources\ui",
        r"{app}\resources\assets",
        r"{app}\locales",
    ):
        assert target in section, f"{target} is no longer cleared before install"
    # Never clear anything outside {app}: user data lives in LecturePackData.
    for line in section.splitlines():
        if line.startswith("Type:"):
            assert r'Name: "{app}' in line, f"refuses to delete outside the app dir: {line}"
