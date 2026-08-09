[CmdletBinding()]
param(
    [ValidateSet('Acceptance', 'Negative')]
    [string]$Mode = 'Acceptance',
    [string]$KitRoot = $PSScriptRoot,
    [string]$ResultsDir = (Join-Path $PSScriptRoot 'results'),
    [int]$JobTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$KitRoot = [IO.Path]::GetFullPath($KitRoot)
$ResultsDir = [IO.Path]::GetFullPath($ResultsDir)
$script:SidecarProcess = $null
$script:SidecarMessages = New-Object System.Collections.ArrayList
$script:RequestNumber = 0

function Quote-NativeArgument([string]$Value) {
    if ($Value.Contains('"')) { throw "A validation path contains an unsupported quote: $Value" }
    return '"' + $Value + '"'
}

function Get-CommandPresence([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-AdminStatus {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-SystemEvidence {
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
    $defender = Get-MpComputerStatus -ErrorAction SilentlyContinue
    $vcKeys = @(
        'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
    )
    $vcInstalled = $false
    foreach ($key in $vcKeys) {
        if (Test-Path $key) {
            $value = Get-ItemProperty $key -ErrorAction SilentlyContinue
            if ($value -and $value.Installed -eq 1) { $vcInstalled = $true }
        }
    }
    return [ordered]@{
        windows_edition = $os.Caption
        windows_version = $os.Version
        windows_build = $os.BuildNumber
        architecture = $os.OSArchitecture
        username = [Environment]::UserName
        is_admin = Get-AdminStatus
        cpu = $cpu.Name
        logical_processors = $cpu.NumberOfLogicalProcessors
        memory_bytes = [int64]$os.TotalVisibleMemorySize * 1024
        gpu = $gpu.Name
        python_present = Get-CommandPresence 'python.exe'
        node_present = Get-CommandPresence 'node.exe'
        rust_present = Get-CommandPresence 'rustc.exe'
        vc_runtime_registered = $vcInstalled
        defender_enabled = if ($defender) { [bool]$defender.AntivirusEnabled } else { $null }
        defender_realtime = if ($defender) { [bool]$defender.RealTimeProtectionEnabled } else { $null }
        defender_signature = if ($defender) { $defender.AntivirusSignatureVersion } else { '' }
    }
}

function Find-CandidateRoot([string]$Root) {
    $direct = Join-Path $Root 'LecturePack.exe'
    if (Test-Path -LiteralPath $direct -PathType Leaf) { return (Resolve-Path $Root).Path }
    $match = Get-ChildItem -LiteralPath $Root -Recurse -Filter 'LecturePack.exe' -File |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.DirectoryName 'resources\LecturePackSidecar\LecturePackSidecar.exe') } |
        Select-Object -First 1
    if (-not $match) { throw "LecturePack.exe was not found under $Root" }
    return $match.DirectoryName
}

function Invoke-PackagedSelfTest([string]$Candidate, [string]$DataPath, [string]$Fault = '') {
    $sidecarRoot = Join-Path $Candidate 'resources\LecturePackSidecar'
    $sidecar = Join-Path $sidecarRoot 'LecturePackSidecar.exe'
    $arguments = @('--resources-root', $sidecarRoot, '--data-dir', $DataPath, '--self-test')
    if ($Fault) { $arguments += @('--self-test-fault', $Fault) }
    $started = Get-Date
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = & $sidecar @arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    $record = $null
    foreach ($line in $lines) {
        try {
            $value = $line.ToString() | ConvertFrom-Json
            if ($value.event -eq 'self_test') { $record = $value }
        } catch { }
    }
    return [ordered]@{
        exit_code = $exitCode
        elapsed_ms = [int](((Get-Date) - $started).TotalMilliseconds)
        result = $record
    }
}

function Start-SidecarSession([string]$Candidate, [string]$DataPath, [string]$MediaPath) {
    $sidecarRoot = Join-Path $Candidate 'resources\LecturePackSidecar'
    $sidecar = Join-Path $sidecarRoot 'LecturePackSidecar.exe'
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $sidecar
    $info.WorkingDirectory = $sidecarRoot
    $info.Arguments = (@(
        '--resources-root', (Quote-NativeArgument $sidecarRoot),
        '--data-dir', (Quote-NativeArgument $DataPath),
        '--demo-video', (Quote-NativeArgument $MediaPath)
    ) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $script:SidecarProcess = New-Object System.Diagnostics.Process
    $script:SidecarProcess.StartInfo = $info
    if (-not $script:SidecarProcess.Start()) { throw 'Packaged sidecar did not start' }
    $script:SidecarMessages.Clear()
    $script:RequestNumber = 0
}

function Read-SidecarMessage([datetime]$Deadline) {
    $remaining = [int][Math]::Max(1, ($Deadline - (Get-Date)).TotalMilliseconds)
    $task = $script:SidecarProcess.StandardOutput.ReadLineAsync()
    if (-not $task.Wait($remaining)) { throw 'Timed out waiting for packaged sidecar output' }
    $line = $task.Result
    if ($null -eq $line) {
        $stderr = $script:SidecarProcess.StandardError.ReadToEnd()
        throw "Packaged sidecar closed its output early. $stderr"
    }
    try { return ($line | ConvertFrom-Json) } catch { return $null }
}

function Wait-SidecarEvent([string]$Event, [int]$TimeoutSeconds) {
    foreach ($saved in $script:SidecarMessages) {
        if ($saved.event -eq $Event) { return $saved }
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $message = Read-SidecarMessage $deadline
        if ($null -eq $message) { continue }
        [void]$script:SidecarMessages.Add($message)
        if ($message.event -eq $Event) { return $message }
    }
    throw "Timed out waiting for sidecar event $Event"
}

function Invoke-SidecarRequest([string]$Command, [hashtable]$Payload = @{}, [int]$TimeoutSeconds = 60) {
    $script:RequestNumber += 1
    $requestId = 'clean-' + $script:RequestNumber
    $request = [ordered]@{ request_id = $requestId; command = $Command; payload = $Payload }
    $script:SidecarProcess.StandardInput.WriteLine(($request | ConvertTo-Json -Compress -Depth 10))
    $script:SidecarProcess.StandardInput.Flush()
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $message = Read-SidecarMessage $deadline
        if ($null -eq $message) { continue }
        [void]$script:SidecarMessages.Add($message)
        if ($message.response_to -eq $requestId) {
            if ($message.ok -eq $false) { throw "Sidecar command $Command failed: $($message.error)" }
            return $message
        }
    }
    throw "Timed out waiting for sidecar command $Command"
}

function Get-ProcessSnapshot {
    return @(Get-CimInstance Win32_Process | Select-Object ProcessId, Name)
}

function Get-NewLecturePackProcesses($Before) {
    $known = @{}
    foreach ($item in $Before) { $known[[int]$item.ProcessId] = $true }
    $tokens = @('lecturepack', 'sidecar', 'ffmpeg', 'ffprobe', 'whisper', 'python', 'electron')
    $orphans = @()
    foreach ($item in (Get-ProcessSnapshot)) {
        if ($known.ContainsKey([int]$item.ProcessId)) { continue }
        $lower = $item.Name.ToLowerInvariant()
        if ($tokens | Where-Object { $lower.Contains($_) }) {
            $orphans += [ordered]@{ pid = $item.ProcessId; name = $item.Name }
        }
    }
    return $orphans
}

function Wait-HostEvidence([string]$LogDir, [string]$Event, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        foreach ($file in (Get-ChildItem -LiteralPath $LogDir -Filter 'production-*.jsonl' -ErrorAction SilentlyContinue)) {
            if ((Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue).Contains('"event":"' + $Event + '"')) {
                return $true
            }
        }
        Start-Sleep -Milliseconds 100
    }
    return $false
}

function Invoke-HostLaunch([string]$Candidate, [string]$DataPath, [string]$LogDir) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $exe = Join-Path $Candidate 'LecturePack.exe'
    $started = Get-Date
    $process = Start-Process -FilePath $exe -ArgumentList @(
        '--results', (Quote-NativeArgument $LogDir),
        '--data-dir', (Quote-NativeArgument $DataPath)
    ) -PassThru
    $complete = Wait-HostEvidence $LogDir 'startup_complete' 30
    $failed = Wait-HostEvidence $LogDir 'startup_terminal_failure' 1
    $restored = Wait-HostEvidence $LogDir 'job_restored' 2
    try {
        $process.Refresh()
        if (-not $process.CloseMainWindow()) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
        $process.WaitForExit(10000) | Out-Null
    } catch { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    return [ordered]@{
        startup_complete = $complete
        startup_failure = $failed
        restore_passed = $restored
        elapsed_ms = [int](((Get-Date) - $started).TotalMilliseconds)
    }
}

function Get-HealthCheck($SelfTest, [string]$Id) {
    if (-not $SelfTest -or -not $SelfTest.result) { return $null }
    return @($SelfTest.result.checks | Where-Object { $_.id -eq $Id })[0]
}

function Write-ValidationResult([System.Collections.IDictionary]$Result, [string]$BaseName) {
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
    $jsonPath = Join-Path $ResultsDir ($BaseName + '.json')
    $textPath = Join-Path $ResultsDir ($BaseName + '.txt')
    $Result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('LecturePack clean-machine validation')
    $lines.Add(('Mode: ' + $Mode))
    $lines.Add(('Passed: ' + $Result.passed))
    foreach ($key in $Result.Keys) {
        if ($key -in @('passed', 'system')) { continue }
        $lines.Add(($key + ': ' + (($Result[$key] | ConvertTo-Json -Compress -Depth 8))))
    }
    $lines | Set-Content -LiteralPath $textPath -Encoding UTF8
    Write-Host "Wrote $jsonPath"
    Write-Host "Wrote $textPath"
}

function Invoke-Acceptance {
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
    $installer = Get-ChildItem -LiteralPath $KitRoot -Filter 'LecturePack-*-Setup.exe' -File | Select-Object -First 1
    $media = Join-Path $KitRoot 'test-media\demo-lecture.mp4'
    if (-not $installer) { throw 'Final Setup executable is missing from the kit' }
    if (-not (Test-Path -LiteralPath $media -PathType Leaf)) { throw 'Deterministic test media is missing from the kit' }
    $installDir = Join-Path $ResultsDir 'Installed LecturePack'
    $dataDir = Join-Path $ResultsDir 'User Data With Spaces Ω'
    $installerLog = Join-Path $ResultsDir 'installer.log'
    if (Test-Path -LiteralPath $installDir) { throw "Refusing to overwrite prior install test: $installDir" }
    $installStarted = Get-Date
    $installProcess = Start-Process -FilePath $installer.FullName -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', '/NOICONS',
        ('/DIR="' + $installDir + '"'), ('/LOG="' + $installerLog + '"')
    ) -Wait -PassThru
    $installMs = [int](((Get-Date) - $installStarted).TotalMilliseconds)
    if ($installProcess.ExitCode -ne 0) { throw "Installer exited $($installProcess.ExitCode)" }
    $candidate = Find-CandidateRoot $installDir
    $installedMedia = Join-Path $candidate 'resources\assets\demo-lecture.mp4'
    if (-not (Test-Path -LiteralPath $installedMedia -PathType Leaf)) { throw 'Installed deterministic demo media is missing' }
    $lecturePackVersion = (Get-Item (Join-Path $candidate 'LecturePack.exe')).VersionInfo.ProductVersion
    $systemEvidence = Get-SystemEvidence
    $appLocalMsvcp = Join-Path $candidate 'resources\LecturePackSidecar\_internal\msvcp140.dll'
    $appLocalMsvcpPresent = Test-Path -LiteralPath $appLocalMsvcp
    $before = Get-ProcessSnapshot
    $selfTest = Invoke-PackagedSelfTest $candidate $dataDir
    if (-not $selfTest.result -or -not $selfTest.result.passed) { throw 'Installed packaged self-test failed' }

    Start-SidecarSession $candidate $dataDir $installedMedia
    [void](Wait-SidecarEvent 'ready' 60)
    $health = Invoke-SidecarRequest 'health_check'
    $imported = Invoke-SidecarRequest 'import_video' @{ path = $installedMedia; bundled_demo = $true }
    $jobId = [string]$imported.job_id
    [void](Invoke-SidecarRequest 'start_job' @{ job_id = $jobId; mode = 'study'; auto_export = $true })
    [void](Wait-SidecarEvent 'job_completed' $JobTimeoutSeconds)
    $slides = Invoke-SidecarRequest 'get_slides' @{ job_id = $jobId }
    $transcript = Invoke-SidecarRequest 'get_transcript' @{ job_id = $jobId }
    for ($index = $script:SidecarMessages.Count - 1; $index -ge 0; $index--) {
        if ($script:SidecarMessages[$index].event -eq 'export_done') {
            $script:SidecarMessages.RemoveAt($index)
        }
    }
    [void](Invoke-SidecarRequest 'export' @{ job_id = $jobId })
    [void](Wait-SidecarEvent 'export_done' 60)
    $exportDir = Join-Path $dataDir ('jobs\' + $jobId + '\exports')
    $exportFiles = @(Get-ChildItem -LiteralPath $exportDir -Recurse -File -ErrorAction SilentlyContinue)
    [void](Invoke-SidecarRequest 'shutdown')
    $script:SidecarProcess.WaitForExit(15000) | Out-Null
    $sidecarExit = $script:SidecarProcess.ExitCode

    $hostEvidence = Invoke-HostLaunch $candidate $dataDir (Join-Path $ResultsDir 'host-logs')
    Start-Sleep -Seconds 1
    $orphans = @(Get-NewLecturePackProcesses $before)
    $studyData = Join-Path $exportDir 'study-data.json'
    $uninstaller = Join-Path $installDir 'unins000.exe'
    $uninstallResult = $null
    if (Test-Path -LiteralPath $uninstaller) {
        $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru
        $uninstallResult = $uninstallProcess.ExitCode
    }
    $result = [ordered]@{
        system = $systemEvidence
        lecturepack_version = $lecturePackVersion
        username_path_test = [ordered]@{ path = $dataDir; contains_spaces = $dataDir.Contains(' '); contains_unicode = $dataDir.Contains('Ω') }
        installer_result = [ordered]@{ exit_code = $installProcess.ExitCode; elapsed_ms = $installMs; per_user = $true; uninstall_exit_code = $uninstallResult }
        vc_runtime_result = [ordered]@{ machine_registered = $systemEvidence.vc_runtime_registered; app_local_msvcp140 = $appLocalMsvcpPresent }
        startup_health_result = $selfTest.result
        ffmpeg_result = Get-HealthCheck $selfTest 'ffmpeg'
        ffprobe_result = Get-HealthCheck $selfTest 'ffprobe'
        whisper_smoke_result = Get-HealthCheck $selfTest 'whisper_smoke'
        model_result = Get-HealthCheck $selfTest 'bundled_model'
        rust_study_core_result = Get-HealthCheck $selfTest 'study_core'
        yt_dlp_result = Get-HealthCheck $selfTest 'yt_dlp'
        real_job_result = [ordered]@{ job_id = $jobId; completed = $true; slides = @($slides.slides).Count; transcript_segments = @($transcript.transcript.blocks).Count }
        study_result = [ordered]@{ study_data_exists = (Test-Path -LiteralPath $studyData); rust_core = (Get-HealthCheck $selfTest 'study_core').ok }
        export_result = [ordered]@{ directory = $exportDir; file_count = $exportFiles.Count; files = @($exportFiles | ForEach-Object { $_.Name }) }
        shutdown_result = [ordered]@{ sidecar_exit_code = $sidecarExit; host = $hostEvidence }
        orphan_process_result = $orphans
        passed = [bool]($selfTest.result.passed -and $health.startup_ok -and $hostEvidence.startup_complete -and $hostEvidence.restore_passed -and $sidecarExit -eq 0 -and (Test-Path -LiteralPath $studyData) -and $exportFiles.Count -eq 13 -and $orphans.Count -eq 0)
    }
    Write-ValidationResult $result 'clean-machine-result'
    if (-not $result.passed) { exit 1 }
}

function Invoke-Negative {
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
    $portable = Get-ChildItem -LiteralPath $KitRoot -Filter 'LecturePack-*-Portable.zip' -File | Select-Object -First 1
    if (-not $portable) { throw 'Portable ZIP is missing from the kit' }
    $expanded = Join-Path $ResultsDir 'negative-disposable-copy'
    if (Test-Path -LiteralPath $expanded) { throw "Refusing to overwrite prior negative copy: $expanded" }
    Expand-Archive -LiteralPath $portable.FullName -DestinationPath $expanded
    $candidate = Find-CandidateRoot $expanded
    $sidecar = Join-Path $candidate 'resources\LecturePackSidecar\LecturePackSidecar.exe'
    $scenarios = New-Object System.Collections.Specialized.OrderedDictionary
    foreach ($entry in @(
        @('ffmpeg_missing', 'resources\LecturePackSidecar\_internal\bin\ffmpeg.exe'),
        @('model_missing', 'resources\LecturePackSidecar\_internal\models\ggml-base.en.bin'),
        @('whisper_missing', 'resources\LecturePackSidecar\_internal\bin\Release\whisper-cli.exe'),
        @('rust_missing', 'resources\LecturePackSidecar\_internal\lecturepack_study_core\lecturepack_study_core.cp312-win_amd64.pyd')
    )) {
        $name = $entry[0]
        $file = Join-Path $candidate $entry[1]
        $held = $file + '.negative-held'
        Move-Item -LiteralPath $file -Destination $held
        try { $scenarios[$name] = Invoke-PackagedSelfTest $candidate (Join-Path $ResultsDir ('data-' + $name)) }
        finally { Move-Item -LiteralPath $held -Destination $file }
    }
    $scenarios['yt_dlp_unavailable'] = Invoke-PackagedSelfTest $candidate (Join-Path $ResultsDir 'data-yt-dlp') 'yt_dlp'
    $blocker = Join-Path $ResultsDir 'data-unwritable-file'
    New-Item -ItemType File -Path $blocker | Out-Null
    $scenarios['data_unwritable'] = Invoke-PackagedSelfTest $candidate $blocker

    $hostLog = Join-Path $ResultsDir 'sidecar-missing-host'
    $heldSidecar = $sidecar + '.negative-held'
    Move-Item -LiteralPath $sidecar -Destination $heldSidecar
    try { $scenarios['sidecar_missing'] = Invoke-HostLaunch $candidate (Join-Path $ResultsDir 'data-sidecar-missing') $hostLog }
    finally { Move-Item -LiteralPath $heldSidecar -Destination $sidecar }

    $where = Join-Path $env:SystemRoot 'System32\where.exe'
    $goodSidecar = $sidecar + '.negative-good'
    $stubSidecar = $sidecar + '.negative-stub'
    Move-Item -LiteralPath $sidecar -Destination $goodSidecar
    Copy-Item -LiteralPath $where -Destination $sidecar
    try { $scenarios['sidecar_exits'] = Invoke-HostLaunch $candidate (Join-Path $ResultsDir 'data-sidecar-exits') (Join-Path $ResultsDir 'sidecar-exits-host') }
    finally {
        Move-Item -LiteralPath $sidecar -Destination $stubSidecar
        Move-Item -LiteralPath $goodSidecar -Destination $sidecar
    }
    $passed = $true
    foreach ($key in $scenarios.Keys) {
        $value = $scenarios[$key]
        if ($key -in @('rust_missing', 'yt_dlp_unavailable')) {
            if (-not $value.result -or $value.result.startup_ok -ne $true -or $value.result.passed -ne $false) { $passed = $false }
        } elseif ($key -in @('sidecar_missing', 'sidecar_exits')) {
            if ($value.startup_failure -ne $true -or $value.elapsed_ms -gt 30000) { $passed = $false }
        } else {
            if (-not $value.result -or $value.result.startup_ok -ne $false) { $passed = $false }
        }
    }
    $result = [ordered]@{ system = Get-SystemEvidence; scenarios = $scenarios; passed = $passed }
    Write-ValidationResult $result 'negative-test-result'
    if (-not $passed) { exit 1 }
}

if ($Mode -eq 'Negative') { Invoke-Negative } else { Invoke-Acceptance }
