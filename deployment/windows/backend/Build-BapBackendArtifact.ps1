[CmdletBinding()]
param(
    [string]$CommitSha = "HEAD",
    [string]$SourceTreeSha,
    [string]$OutputDirectory,
    [string]$PythonPath,
    [string]$GitPath = "C:\Program Files\Git\cmd\git.exe"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = if ($env:RUNNER_TEMP) { Join-Path $env:RUNNER_TEMP "bap-candidate" } else { Join-Path $RepoRoot "dist" }
}
if (-not $PythonPath) { $PythonPath = Join-Path $RepoRoot ".venv\Scripts\python.exe" }
foreach ($Tool in @($GitPath, $PythonPath)) {
    if (-not (Test-Path -LiteralPath $Tool -PathType Leaf)) { throw "Required tool not found: $Tool" }
}

$CommitSha = (& $GitPath -C $RepoRoot rev-parse "$CommitSha^{commit}").Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $CommitSha -notmatch "^[0-9a-f]{40}$") { throw "Commit SHA is invalid." }
$ActualTree = (& $GitPath -C $RepoRoot rev-parse "$CommitSha^{tree}").Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $ActualTree -notmatch "^[0-9a-f]{40}$") { throw "Source Tree SHA is invalid." }
if ($SourceTreeSha -and $SourceTreeSha.ToLowerInvariant() -ne $ActualTree) {
    throw "Provided Source Tree SHA does not match the selected commit."
}
$SourceTreeSha = $ActualTree

$TempRoot = Join-Path $env:TEMP ("bap-backend-build-" + [Guid]::NewGuid().ToString("N"))
$SnapshotZip = Join-Path $TempRoot "snapshot.zip"
$Snapshot = Join-Path $TempRoot "snapshot"
$Stage = Join-Path $TempRoot "artifact"
$RuntimeScripts = @(
    "Common-BapDeployment.ps1",
    "Deploy-BapBackendRelease.ps1",
    "Run-BapBackendScheduledTask.ps1",
    "Rollback-BapBackendRelease.ps1",
    "Get-BapBackendStatus.ps1",
    "Test-BapBackendHealth.ps1"
)

try {
    New-Item -ItemType Directory -Path $Snapshot, $Stage, $OutputDirectory -Force | Out-Null
    $Inputs = @(
        "bap_backend", "bap_common", "migrations", "deployment/windows/backend",
        "alembic.ini", "pyproject.toml", "uv.lock", ".python-version"
    )
    & $GitPath -C $RepoRoot archive --format=zip --output=$SnapshotZip $CommitSha -- $Inputs
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the clean Git snapshot." }
    Expand-Archive -LiteralPath $SnapshotZip -DestinationPath $Snapshot

    foreach ($Path in @("bap_backend", "bap_common", "migrations", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version")) {
        Copy-Item -LiteralPath (Join-Path $Snapshot $Path) -Destination (Join-Path $Stage $Path) -Recurse -Force
    }
    $RuntimeDirectory = Join-Path $Stage "deployment\runtime"
    New-Item -ItemType Directory -Path $RuntimeDirectory -Force | Out-Null
    foreach ($Name in $RuntimeScripts) {
        $Source = Join-Path $Snapshot ("deployment\windows\backend\" + $Name)
        if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Runtime deployment script is missing: $Name" }
        Copy-Item -LiteralPath $Source -Destination (Join-Path $RuntimeDirectory $Name)
    }

    $Version = (Get-Content -LiteralPath (Join-Path $Stage "bap_backend\VERSION") -Raw).Trim()
    $ManifestPath = Join-Path $Stage "deployment-manifest.json"
    $ManifestArgs = @(
        "-m", "bap_backend.tools.write_deployment_manifest",
        "--output", $ManifestPath,
        "--component", "backend",
        "--commit-sha", $CommitSha,
        "--source-tree-sha", $SourceTreeSha,
        "--version", $Version,
        "--entry-point", "bap_backend.app.main:app",
        "--alembic-revision", "0002_app_release_source_tree_sha"
    )
    foreach ($Path in @("bap_backend", "bap_common", "migrations", "deployment", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version")) {
        $ManifestArgs += @("--file", $Path)
    }
    & $PythonPath @ManifestArgs
    if ($LASTEXITCODE -ne 0) { throw "Unable to create deployment-manifest.json." }

    $Artifact = Join-Path $OutputDirectory ("bap-backend-tree-" + $SourceTreeSha + ".zip")
    $Checksum = $Artifact + ".sha256"
    if (Test-Path -LiteralPath $Artifact) { Remove-Item -LiteralPath $Artifact -Force }
    Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Artifact -CompressionLevel Optimal
    $Hash = Get-BapSha256 -Path $Artifact
    Set-Content -LiteralPath $Checksum -Value ($Hash + "  " + [IO.Path]::GetFileName($Artifact)) -Encoding Ascii
    Write-Output $Artifact
    Write-Output $Checksum
} finally {
    if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force }
}
