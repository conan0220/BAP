Set-StrictMode -Version Latest

function Get-BapSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
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
