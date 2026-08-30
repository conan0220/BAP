[CmdletBinding()]
param(
    [string]$CommitSha = "HEAD",
    [string]$OutputDirectory,
    [string]$GitPath = "C:\Program Files\Git\cmd\git.exe",
    [string]$UvPath = "C:\Users\user\.local\bin\uv.exe",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $RepoRoot "dist" }
if (-not (Test-Path -LiteralPath $GitPath -PathType Leaf)) { throw "Git not found: $GitPath" }
if (-not (Test-Path -LiteralPath $UvPath -PathType Leaf)) { throw "uv not found: $UvPath" }

$FullSha = (& $GitPath -C $RepoRoot rev-parse "$CommitSha^{commit}").Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $FullSha -notmatch "^[0-9a-f]{40}$") { throw "Commit SHA is invalid." }
$TempRoot = Join-Path $env:TEMP ("bap-backend-build-" + [Guid]::NewGuid().ToString("N"))
$SnapshotZip = Join-Path $TempRoot "snapshot.zip"
$Snapshot = Join-Path $TempRoot "snapshot"
$Stage = Join-Path $TempRoot "artifact"

try {
    New-Item -ItemType Directory -Path $Snapshot, $Stage, $OutputDirectory -Force | Out-Null
    $Inputs = @(
        "bap_backend", "bap_common", "migrations", "tests/backend", "deployment/windows/backend",
        "alembic.ini", "pyproject.toml", "uv.lock", ".python-version"
    )
    & $GitPath -C $RepoRoot archive --format=zip --output=$SnapshotZip $FullSha -- $Inputs
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the clean Git snapshot." }
    Expand-Archive -LiteralPath $SnapshotZip -DestinationPath $Snapshot

    if (-not $SkipTests) {
        & $UvPath sync --directory $Snapshot --frozen --extra backend --group dev --no-extra desktop --no-extra packaging
        if ($LASTEXITCODE -ne 0) { throw "Unable to install locked Backend test dependencies." }
        $SnapshotPython = Join-Path $Snapshot ".venv\Scripts\python.exe"
        $BackendTests = Join-Path $Snapshot "tests\backend"
        $PytestTemp = Join-Path $TempRoot "pytest-temp"
        New-Item -ItemType Directory -Path $PytestTemp -Force | Out-Null
        $PreviousPluginAutoload = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
        $TestExitCode = 1
        Push-Location $Snapshot
        try {
            $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
            & $SnapshotPython -m pytest --confcutdir=$BackendTests --basetemp=$PytestTemp $BackendTests -q
            $TestExitCode = $LASTEXITCODE
        } finally {
            Pop-Location
            if ($null -eq $PreviousPluginAutoload) {
                Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD -ErrorAction SilentlyContinue
            } else {
                $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = $PreviousPluginAutoload
            }
        }
        if ($TestExitCode -ne 0) { throw "Backend tests failed in the clean Git snapshot." }
    }

    foreach ($Path in @("bap_backend", "bap_common", "migrations", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version")) {
        Copy-Item -LiteralPath (Join-Path $Snapshot $Path) -Destination (Join-Path $Stage $Path) -Recurse -Force
    }
    $Version = (Get-Content -LiteralPath (Join-Path $Stage "bap_backend\VERSION") -Raw).Trim()
    $ManifestPath = Join-Path $Stage "deployment-manifest.json"
    $ManifestPython = if (Test-Path (Join-Path $Snapshot ".venv\Scripts\python.exe")) {
        Join-Path $Snapshot ".venv\Scripts\python.exe"
    } else {
        Join-Path $RepoRoot ".venv\Scripts\python.exe"
    }
    & $ManifestPython -m bap_backend.tools.write_deployment_manifest `
        --output $ManifestPath --component backend --commit-sha $FullSha --version $Version `
        --entry-point "bap_backend.app.main:app" --alembic-revision "0001_initial" `
        --file "bap_backend" --file "bap_common" --file "migrations" --file "alembic.ini" `
        --file "pyproject.toml" --file "uv.lock" --file ".python-version"
    if ($LASTEXITCODE -ne 0) { throw "Unable to create deployment-manifest.json." }

    $Artifact = Join-Path $OutputDirectory ("bap-backend-" + $FullSha + ".zip")
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
