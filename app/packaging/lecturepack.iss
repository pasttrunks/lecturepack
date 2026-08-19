; Inno Setup script for LecturePack.
; Produces LecturePack-Setup-<version>.exe with Start Menu + optional desktop
; shortcut, an app icon, and an uninstaller. The build script passes the
; version in via /DAppVersion=x.y.z so this stays in sync with version.py.

#ifndef AppVersion
  #define AppVersion "2.0.7"
#endif

; D-23: build.py passes /DSourceDir and /DOutputDir as already-normalized,
; absolute paths so ISCC never has to concatenate a "..\" segment onto its
; own script directory (app\packaging\) to find dist\LecturePack. That extra
; 13-character prefix pushed several bundled torch licence files past
; Windows' 260-char MAX_PATH and silently aborted the build with no
; Setup.exe produced. The relative defaults below only apply when ISCC is
; invoked manually without those defines.
#ifndef SourceDir
  #define SourceDir "..\dist\LecturePack"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

#define AppName "LecturePack"
#define AppPublisher "LecturePack"
#define AppExeName "LecturePack.exe"
#define AppURL "https://github.com/pasttrunks/lecturepack"
; D-20: must match APP_USER_MODEL_ID in app/desktop/main.py byte-for-byte,
; and stay free of any version component -- a version bump must never
; orphan a pinned taskbar or Start Menu icon. Defined once here and
; referenced by both non-uninstall [Icons] entries below so the two
; shortcut lines cannot drift from each other or from main.py's literal.
#define AppUserModelID "LecturePack.LecturePack"

[Setup]
AppId={{9F5D2E31-7C4A-4B8E-9E1D-LECTUREPACK01}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default → no admin prompt, and the silent auto-updater
; can replace files without elevation.
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=LecturePack-{#AppVersion}-Setup
SetupIconFile=lecturepack.ico
UninstallDisplayIcon={app}\{#AppExeName}
#if Defined(FastCompression)
Compression=lzma2/fast
SolidCompression=no
#else
Compression=lzma2/max
SolidCompression=yes
#endif
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Clear the previous build's payload BEFORE installing this one.
;
; [Files] copies over the top with `ignoreversion`, which updates and adds but
; never REMOVES. So any file an older version shipped and this one does not
; survived the upgrade forever. That is not cosmetic: upgrading 2.0.2 -> 2.0.3
; left 12 stale packages in the frozen sidecar (Cryptodome, certifi,
; cryptography, websockets, pywin32, yaml, brotli) and the leftovers broke
; `import yt_dlp`, so link import died on upgrade while a FRESH install of the
; same build was perfectly healthy. Caught by scripts/updater_ab_acceptance.py;
; a fresh-install test alone can never catch this class of bug.
;
; Only directories this installer fully re-ships are listed. User data lives in
; LecturePackData, never under {app}, so nothing here can touch it.
Type: filesandordirs; Name: "{app}\resources\LecturePackSidecar"
Type: filesandordirs; Name: "{app}\resources\ui"
Type: filesandordirs; Name: "{app}\resources\assets"
Type: filesandordirs; Name: "{app}\locales"

; NOTE: this section was silently lost once between 2.0.3 and 2.0.4 when an
; unrelated edit rewrote this file. tests/test_installer_iscc_path.py now
; asserts it is present -- do not delete it without reading DEF-019 in
; BUG_LIST.md first.

[Files]
; PyInstaller onedir output → everything under dist\LecturePack.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "{#AppUserModelID}"
; Explorer "Send to -> LecturePack". {usersendto} is the per-user SendTo folder
; so this needs no elevation and is removed with the rest of [Icons] on
; uninstall. Explorer passes the selected file paths as command-line
; arguments; LecturePack already forwards those to a running instance via
; its single-instance lock (see production-main.js 'second-instance'), so
; sending a lecture imports it instead of starting a second copy. The
; original file is only ever read.
Name: "{usersendto}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
