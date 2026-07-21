; Inno Setup script for LecturePack.
; Produces LecturePack-Setup-<version>.exe with Start Menu + optional desktop
; shortcut, an app icon, and an uninstaller. The build script passes the
; version in via /DAppVersion=x.y.z so this stays in sync with version.py.

#ifndef AppVersion
  #define AppVersion "0.9.0-beta.1"
#endif

#define AppName "LecturePack"
#define AppPublisher "LecturePack"
#define AppExeName "LecturePack.exe"
#define AppURL "https://github.com/pasttrunks/lecturepack"

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
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=LecturePack-Setup-{#AppVersion}
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
Source: "..\dist\LecturePack\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
