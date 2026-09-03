Set-StrictMode -Version Latest

function Get-BapSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $Stream = [IO.File]::OpenRead($Path)
    try {
        $Hasher = [Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace("-", "").ToLowerInvariant()
        } finally {
            $Hasher.Dispose()
        }
    } finally {
        $Stream.Dispose()
    }
}

function Assert-BapChecksum {
    param(
        [Parameter(Mandatory = $true)][string]$ArtifactPath,
        [Parameter(Mandatory = $true)][string]$ChecksumPath
    )
    if (-not (Test-Path -LiteralPath $ArtifactPath -PathType Leaf)) { throw "Artifact not found: $ArtifactPath" }
    if (-not (Test-Path -LiteralPath $ChecksumPath -PathType Leaf)) { throw "Checksum not found: $ChecksumPath" }
    $Expected = ((Get-Content -LiteralPath $ChecksumPath -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
    if ($Expected -notmatch "^[0-9a-f]{64}$") { throw "Checksum file is invalid." }
    $Actual = Get-BapSha256 -Path $ArtifactPath
    if ($Actual -ne $Expected) { throw "Artifact checksum does not match." }
}

function Import-BapEnvironment {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Environment file not found: $Path" }
    foreach ($Line in Get-Content -LiteralPath $Path) {
        $Text = $Line.Trim()
        if (-not $Text -or $Text.StartsWith("#")) { continue }
        $Parts = $Text -split "=", 2
        if ($Parts.Count -ne 2 -or $Parts[0] -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
            throw "Environment file contains an invalid line."
        }
        [Environment]::SetEnvironmentVariable($Parts[0], $Parts[1], "Process")
    }
}

function Get-BapCurrentTarget {
    param([Parameter(Mandatory = $true)][string]$Root)
    $Current = Join-Path $Root "current"
    if (-not (Test-Path -LiteralPath $Current)) { return $null }
    $Item = Get-Item -LiteralPath $Current -Force
    if (-not ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Current path exists but is not a junction."
    }
    return $Item.Target
}

function Remove-BapCurrentJunction {
    param([Parameter(Mandatory = $true)][string]$Root)
    $Current = [IO.Path]::GetFullPath((Join-Path $Root "current"))
    if (-not (Test-Path -LiteralPath $Current)) { return }
    $Item = Get-Item -LiteralPath $Current -Force
    if (-not ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Current path exists but is not a junction."
    }
    $Target = [IO.Path]::GetFullPath([string]$Item.Target)
    $ReleasesPrefix = [IO.Path]::GetFullPath((Join-Path $Root "releases")).TrimEnd("\") + "\"
    if (-not $Target.StartsWith($ReleasesPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Current junction target is outside the releases directory."
    }
    # Windows PowerShell 5.1 may block in Remove-Item when the path is a
    # junction. Directory.Delete removes the junction itself, not its target.
    [IO.Directory]::Delete($Current)
}

function Stop-BapBackendTaskAndListener {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [string]$TaskName = "BAPBackend",
        [int]$Port = 12345
    )
    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($Task -and $Task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    }

    # Windows Task Scheduler can report Ready after stopping the PowerShell
    # action while the Python launcher and its uvicorn child remain alive.
    # Give a normal stop a short chance, then terminate only a listener whose
    # process tree and command line prove that it belongs to this BAP root.
    for ($Attempt = 0; $Attempt -lt 3; $Attempt++) {
        if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Seconds 1
    }

    $Listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $RootFull = [IO.Path]::GetFullPath($Root).TrimEnd("\").ToLowerInvariant()
    $CurrentPython = (Join-Path $RootFull "current\.venv\scripts\python.exe")
    $ReleasePrefix = (Join-Path $RootFull "releases\")
    foreach ($Listener in $Listeners) {
        $Owner = Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$Listener.OwningProcess)
        $Parent = if ($Owner) {
            Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$Owner.ParentProcessId)
        } else {
            $null
        }
        $OwnerCommand = if ($Owner -and $Owner.CommandLine) { [string]$Owner.CommandLine } else { "" }
        $ParentCommand = if ($Parent -and $Parent.CommandLine) { ([string]$Parent.CommandLine).ToLowerInvariant() } else { "" }
        $IsUvicorn = $OwnerCommand -match "(?i)(^|\s)-m\s+uvicorn(\s|$)"
        $IsBapApp = $OwnerCommand -match "(?i)bap_backend\.app\.main:app"
        $IsExpectedPort = $OwnerCommand -match ("(?i)--port\s+" + $Port + "(\s|$)")
        $IsCurrentPython = $ParentCommand.Contains($CurrentPython)
        $IsReleasePython = $ParentCommand.Contains($ReleasePrefix) -and $ParentCommand.Contains("\.venv\scripts\python.exe")
        if (-not ($Owner -and $Parent -and $IsUvicorn -and $IsBapApp -and $IsExpectedPort -and ($IsCurrentPython -or $IsReleasePython))) {
            throw "Backend port belongs to an unrecognized process; refusing to terminate it."
        }
        Stop-Process -Id ([int]$Owner.ProcessId) -Force -ErrorAction Stop
        Stop-Process -Id ([int]$Parent.ProcessId) -Force -ErrorAction SilentlyContinue
    }

    for ($Attempt = 0; $Attempt -lt 10; $Attempt++) {
        if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Seconds 1
    }
    throw "Backend port remained active after stopping the Scheduled Task."
}

function Assert-BapReleasePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ReleasePath
    )
    $Releases = [IO.Path]::GetFullPath((Join-Path $Root "releases"))
    $Candidate = [IO.Path]::GetFullPath($ReleasePath)
    $Prefix = $Releases.TrimEnd("\") + "\"
    if (-not $Candidate.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Release path is outside the releases directory."
    }
    return $Candidate
}

function Remove-BapTreeWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $SafeRoot = [IO.Path]::GetFullPath($Root).TrimEnd("\") + "\"
    $Candidate = [IO.Path]::GetFullPath($Path)
    if (-not $Candidate.StartsWith($SafeRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the intended root."
    }
    if (Test-Path -LiteralPath $Candidate) { Remove-Item -LiteralPath $Candidate -Recurse -Force }
}
