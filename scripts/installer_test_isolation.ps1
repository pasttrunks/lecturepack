[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Snapshot', 'Restore')][string]$Action,
    [Parameter(Mandatory)][string]$InstallDir,
    [Parameter(Mandatory)][string]$StatePath
)

# Native PowerShell/.NET only: this guard also ships in clean-machine kits.
$ErrorActionPreference = 'Stop'
$InstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$StatePath = [IO.Path]::GetFullPath($StatePath)
$registryParent = 'Software\Microsoft\Windows\CurrentVersion\Uninstall'
$leasePath = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'LecturePack-installer-acceptance.lock'
$shortcutPaths = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'LecturePack\LecturePack.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'LecturePack\Uninstall LecturePack.lnk'),
    (Join-Path ([Environment]::GetFolderPath('SendTo')) 'LecturePack.lnk'),
    (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'LecturePack.lnk')
)

function Get-KeyTree($Key) {
    $values = @()
    foreach ($name in @($Key.GetValueNames() | Sort-Object)) {
        $kind = $Key.GetValueKind($name).ToString()
        $data = $Key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        if ($kind -in @('Binary', 'None')) { $data = [Convert]::ToBase64String([byte[]]$data) }
        $values += [ordered]@{ name = $name; kind = $kind; data = $data }
    }
    $children = @()
    foreach ($name in @($Key.GetSubKeyNames() | Sort-Object)) {
        $child = $Key.OpenSubKey($name)
        try { $children += [ordered]@{ name = $name; tree = (Get-KeyTree $child) } }
        finally { $child.Dispose() }
    }
    return [ordered]@{ values = $values; children = $children }
}

function Set-KeyTree($Key, $Tree) {
    foreach ($value in $Tree.values) {
        $kind = [Microsoft.Win32.RegistryValueKind]::$($value.kind)
        $data = $value.data
        switch ($value.kind) {
            'Binary' { $data = [Convert]::FromBase64String($data) }
            'None' { $data = [Convert]::FromBase64String($data) }
            'DWord' { $data = [int]$data }
            'QWord' { $data = [long]$data }
            'MultiString' { $data = [string[]]$data }
        }
        $Key.SetValue([string]$value.name, $data, $kind)
    }
    foreach ($child in $Tree.children) {
        $keyChild = $Key.CreateSubKey([string]$child.name)
        try { Set-KeyTree $keyChild $child.tree } finally { $keyChild.Dispose() }
    }
}

function Get-LecturePackKeys($Parent) {
    if (-not $Parent) { return @() }
    return @($Parent.GetSubKeyNames() | Where-Object {
        $key = $Parent.OpenSubKey($_)
        try {
            # Enumerate actual names; Inno's escaped AppId is not a literal key.
            $_ -like '*LECTUREPACK*' -or [string]$key.GetValue('DisplayName', '') -like 'LecturePack*'
        } finally { $key.Dispose() }
    } | Sort-Object)
}

function Get-RegistrySnapshot {
    $records = @()
    foreach ($view in @('Registry64', 'Registry32')) {
        $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', [Microsoft.Win32.RegistryView]::$view)
        $parent = $base.OpenSubKey($registryParent)
        try {
            foreach ($name in (Get-LecturePackKeys $parent)) {
                $key = $parent.OpenSubKey($name)
                try { $records += [ordered]@{ view = $view; name = $name; tree = (Get-KeyTree $key) } }
                finally { $key.Dispose() }
            }
        } finally { if ($parent) { $parent.Dispose() }; $base.Dispose() }
    }
    return $records
}

function Assert-SameInstall($State) {
    if ($State.install_dir -ne $InstallDir) { throw 'Snapshot belongs to a different install directory' }
}

if ($Action -eq 'Snapshot') {
    if (Test-Path -LiteralPath $InstallDir) { throw "Refusing to replace an existing test install: $InstallDir" }
    if (Test-Path -LiteralPath $StatePath) { throw "Refusing to overwrite an isolation snapshot: $StatePath" }
    if ($InstallDir -eq [IO.Path]::GetPathRoot($InstallDir) -or $InstallDir -match '(^|\\)LecturePackData(\\|$)') {
        throw 'Refusing a root or normal lecture-data installation path'
    }
    # CreateNew serializes all of our installer runners. A leftover lease is a
    # recovery signal, never permission to discard the original snapshot.
    $lease = [IO.File]::Open($leasePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($StatePath)
        $lease.Write($bytes, 0, $bytes.Length)
    } finally { $lease.Dispose() }
    try {
        $shortcuts = @()
        foreach ($path in $shortcutPaths) {
            $exists = Test-Path -LiteralPath $path -PathType Leaf
            $shortcuts += [ordered]@{
                path = $path; existed = $exists
                parent_existed = (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName($path)))
                bytes = $(if ($exists) { [Convert]::ToBase64String([IO.File]::ReadAllBytes($path)) } else { '' })
            }
        }
        $state = [ordered]@{ install_dir = $InstallDir; registry = @(Get-RegistrySnapshot); shortcuts = $shortcuts }
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($StatePath)) | Out-Null
        [IO.File]::WriteAllText($StatePath, ($state | ConvertTo-Json -Depth 50), [Text.Encoding]::UTF8)
    } catch {
        [IO.File]::Delete($leasePath)
        throw
    }
} else {
    $state = [IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
    Assert-SameInstall $state
    if (-not (Test-Path -LiteralPath $leasePath) -or [IO.File]::ReadAllText($leasePath) -ne $StatePath) {
        throw 'Isolation lease does not match this snapshot; original state retained'
    }
    try {
        foreach ($view in @('Registry64', 'Registry32')) {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', [Microsoft.Win32.RegistryView]::$view)
            $parent = $base.CreateSubKey($registryParent)
            try {
                $saved = @($state.registry | Where-Object { $_.view -eq $view })
                foreach ($name in (Get-LecturePackKeys $parent)) {
                    $key = $parent.OpenSubKey($name)
                    try {
                        $location = [string]$key.GetValue('InstallLocation', '')
                        $tree = Get-KeyTree $key
                    } finally { $key.Dispose() }
                    $original = @($saved | Where-Object { $_.name -eq $name })
                    if ($original.Count -eq 1 -and ($tree | ConvertTo-Json -Depth 50 -Compress) -eq ($original[0].tree | ConvertTo-Json -Depth 50 -Compress)) {
                        continue
                    }
                    if ($location.TrimEnd('\') -ne $InstallDir) {
                        throw "Uninstall key changed outside this test: $name. Refusing to overwrite it."
                    }
                    # Only a key demonstrably owned by this disposable install is removed.
                    $parent.DeleteSubKeyTree($name)
                }
                foreach ($original in $saved) {
                    $key = $parent.CreateSubKey([string]$original.name)
                    try { Set-KeyTree $key $original.tree } finally { $key.Dispose() }
                }
            } finally { $parent.Dispose(); $base.Dispose() }
        }
    } finally {
        # A registry conflict must not leave restored launchers pointing at the test app.
        foreach ($shortcut in $state.shortcuts) {
            if ($shortcut.path -notin $shortcutPaths) { throw 'Unexpected shortcut path in snapshot' }
            if ($shortcut.existed) {
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($shortcut.path)) | Out-Null
                [IO.File]::WriteAllBytes($shortcut.path, [Convert]::FromBase64String($shortcut.bytes))
            } else {
                if (Test-Path -LiteralPath $shortcut.path) { Remove-Item -LiteralPath $shortcut.path }
                $directory = [IO.Path]::GetDirectoryName($shortcut.path)
                if (-not $shortcut.parent_existed -and (Test-Path -LiteralPath $directory) -and -not (Get-ChildItem -LiteralPath $directory -Force)) {
                    Remove-Item -LiteralPath $directory
                }
            }
        }
    }
    $actual = @(Get-RegistrySnapshot) | ConvertTo-Json -Depth 50 -Compress
    $expected = @($state.registry) | ConvertTo-Json -Depth 50 -Compress
    if ($actual -ne $expected) { throw 'Registry restoration verification failed; snapshot and lease retained' }
    foreach ($shortcut in $state.shortcuts) {
        $exists = Test-Path -LiteralPath $shortcut.path -PathType Leaf
        if ($exists -ne $shortcut.existed) { throw 'Shortcut membership restoration failed' }
        if ($exists -and [Convert]::ToBase64String([IO.File]::ReadAllBytes($shortcut.path)) -ne $shortcut.bytes) {
            throw 'Shortcut byte restoration failed'
        }
    }
    [IO.File]::WriteAllText($StatePath + '.restored.json', '{"registry_restored":true,"shortcuts_restored":true}', [Text.Encoding]::UTF8)
    [IO.File]::Delete($leasePath)
}
