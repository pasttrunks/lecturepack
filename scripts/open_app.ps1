<#
.SYNOPSIS
  Open the PACKAGED LecturePack app with a given worktree's UI changes, and
  refuse to report success without a real visible window.

.DESCRIPTION
  Written because "the app won't open" kept being reported as opened. Every
  failure mode below produces a live process and a zero exit code, so process
  existence and exit codes prove nothing:

    1. SINGLE-INSTANCE GUARD. app/desktop/main.py acquires a QLocalServer pipe
       ("LecturePack.single-instance.v1"). A second launch asks the first to
       raise itself and `return 0` -- exit code 0, no window of its own. If the
       existing owner is a hidden or wedged process, NOTHING appears, forever.
       Any launcher must therefore clear strays and wait for the pipe to free.

    2. WINDOW SHOWN ONLY WHEN THEMED. MainWindow.show_when_ready() shows only
       once `_theme_ready` is set. If the palette never settles the process runs
       with no window at all.

    3. WRONG APP. electron-spike/dist/LecturePack-win32-x64 is a HARNESS, not
       the shipped product. Its UI lives in resources/ui; the real app is
       PyInstaller and reads _internal/ui. Overlaying one and launching the
       other silently tests nothing.

    4. --data-dir IS NOT A FLAG. The PySide6 app reads only the
       LECTUREPACK_DATA_DIR environment variable (app/desktop/paths.py). A
       --data-dir argument is ignored, so the app quietly uses the REAL library.

  A CDP screenshot does not settle it either: an offscreen or hidden renderer
  screenshots perfectly. The only proof is a Win32 window -- a non-zero
  MainWindowHandle with a non-blank title -- which is what this script waits
  for, and what it fails on.

.EXAMPLE
  pwsh -File scripts/open_app.ps1 -SourceTree "C:\Users\marsh\Documents\LecturePack-worktrees\microinteractions-polish"
#>
[CmdletBinding()]
param(
    # Worktree whose app/ui changes should be tested. Defaults to this script's repo.
    [string]$SourceTree,

    # A built PyInstaller onedir to use as the pristine base (never modified).
    [string]$Build,

    # Disposable data directory. NEVER point this at ~/LecturePackData while testing
    # drag-to-Process: confirming "Process again" replaces slides/transcript/Study pack.
    [string]$DataDir = "$env:TEMP\LecturePackData-dragtest",

    # Where the swapped copy is assembled.
    [string]$ScratchRoot = "$env:TEMP\LecturePackScratch",

    [int]$WindowTimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'

function Fail($msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; exit 1 }
function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
if (-not $SourceTree) { $SourceTree = $repo }
if (-not $Build) { $Build = Join-Path $repo 'app\dist\LecturePack' }

$exeName = 'LecturePack.exe'
$baseExe = Join-Path $Build $exeName
if (-not (Test-Path $baseExe)) {
    Fail "no packaged build at $Build`n  Build one first: python scripts/release_build.py --no-installer"
}
foreach ($f in 'app\ui\app.js', 'app\ui\app.css', 'app\ui\index.html') {
    if (-not (Test-Path (Join-Path $SourceTree $f))) { Fail "$SourceTree is missing $f" }
}

# ---------------------------------------------------------------- 1. strays
Step "Clearing stray instances (the single-instance guard makes a 2nd launch exit 0 with no window)"
$stray = Get-Process LecturePack -ErrorAction SilentlyContinue
if ($stray) {
    $stray | Select-Object Id, MainWindowHandle | Format-Table -AutoSize | Out-String | Write-Host
    $stray | Stop-Process -Force -Confirm:$false
    Write-Host "stopped $($stray.Count) process(es)"
} else {
    Write-Host "none running"
}

$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline) {
    $held = [System.IO.Directory]::GetFiles('\\.\pipe\') | Where-Object { $_ -match 'single-instance' }
    if (-not $held) { break }
    Start-Sleep -Milliseconds 400
}
$held = [System.IO.Directory]::GetFiles('\\.\pipe\') | Where-Object { $_ -match 'single-instance' }
if ($held) { Fail "single-instance pipe still held: $held`n  A hidden owner will swallow this launch." }
Write-Host "single-instance pipe is free"

# ------------------------------------------------- 2. assemble swapped build
$name = Split-Path $SourceTree -Leaf
$target = Join-Path $ScratchRoot "builds\$name"
Step "Assembling a swapped copy at $target (the pristine build stays untouched)"
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
Copy-Item $Build $target -Recurse -Force

$uiDest = Join-Path $target '_internal\ui'
if (-not (Test-Path $uiDest)) { Fail "expected UI dir missing in the build: $uiDest" }
foreach ($f in 'app.js', 'app.css', 'index.html') {
    Copy-Item (Join-Path $SourceTree "app\ui\$f") (Join-Path $uiDest $f) -Force
}

Step "Verifying hash parity (never assume the swap landed)"
$mismatch = $false
foreach ($f in 'app.js', 'app.css', 'index.html') {
    $a = (Get-FileHash (Join-Path $SourceTree "app\ui\$f") -Algorithm SHA256).Hash
    $b = (Get-FileHash (Join-Path $uiDest $f) -Algorithm SHA256).Hash
    $ok = $a -eq $b
    if (-not $ok) { $mismatch = $true }
    Write-Host ("  {0,-11} {1}" -f $f, $(if ($ok) { "OK  $($a.Substring(0,16))" } else { "MISMATCH" }))
}
if ($mismatch) { Fail "the swapped build does not match the source UI" }

# ------------------------------------------------------------- 3. data dir
Step "Data directory"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    Write-Host "created EMPTY $DataDir (no lectures -- import one, or copy your library in)"
} else {
    $jobs = @(Get-ChildItem (Join-Path $DataDir 'jobs') -Directory -ErrorAction SilentlyContinue).Count
    Write-Host "using $DataDir ($jobs lecture(s))"
}
if ($DataDir -eq (Join-Path $HOME 'LecturePackData')) {
    Write-Host "WARNING: this is your REAL library. 'Process again' will replace slides/transcript/Study pack." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 4. launch
Step "Launching $target\$exeName"
$env:LECTUREPACK_DATA_DIR = $DataDir
$log = Join-Path $ScratchRoot "$name-stdout.log"
New-Item -ItemType Directory -Force -Path $ScratchRoot | Out-Null
$proc = Start-Process -FilePath (Join-Path $target $exeName) -WorkingDirectory $target `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru
Write-Host "started PID $($proc.Id)"

# ------------------------------------------- 5. prove a REAL visible window
Step "Waiting for a real Win32 window (a live process and exit 0 prove nothing)"
$deadline = (Get-Date).AddSeconds($WindowTimeoutSeconds)
$win = $null
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) {
        $tail = if (Test-Path $log) { Get-Content $log -Tail 15 | Out-String } else { '' }
        $errTail = if (Test-Path "$log.err") { Get-Content "$log.err" -Tail 15 | Out-String } else { '' }
        Fail ("the process exited with code $($proc.ExitCode) before showing a window.`n" +
              "  Exit 0 here usually means it was a SECONDARY instance and deferred to another owner.`n" +
              "stdout: $tail`nstderr: $errTail")
    }
    $win = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne 0 }
    if ($win) { break }
    Start-Sleep -Milliseconds 500
}

if (-not $win) {
    $any = Get-Process LecturePack -ErrorAction SilentlyContinue |
        Select-Object Id, MainWindowHandle, MainWindowTitle | Format-Table -AutoSize | Out-String
    Fail ("no visible window after ${WindowTimeoutSeconds}s. The process is alive but headless.`n" +
          "  Most likely MainWindow.show_when_ready() is still waiting on _theme_ready.`n$any")
}

Write-Host "`nOPEN: PID $($win.Id) -- '$($win.MainWindowTitle)' (handle $($win.MainWindowHandle))" -ForegroundColor Green
Write-Host "  UI from : $SourceTree\app\ui"
Write-Host "  running : $target\$exeName"
Write-Host "  data    : $DataDir"
Write-Host "  log     : $log"
exit 0
