; Inno Setup script for LecturePack.
; Produces LecturePack-Setup-<version>.exe with Start Menu + optional desktop
; shortcut, an app icon, and an uninstaller. The build script passes the
; version in via /DAppVersion=x.y.z so this stays in sync with version.py.

#ifndef AppVersion
  #define AppVersion "0.9.0-beta.5"
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
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller onedir output → everything under dist\LecturePack.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "{#AppUserModelID}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
