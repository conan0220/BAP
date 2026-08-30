[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [Parameter(Mandatory = $true)][string]$ChecksumPath,
    [Parameter(Mandatory = $true)][string]$ExpectedCommitSha,
    [string]$Root = "C:\BAP",
    [string]$UvPath = "C:\Users\user\.local\bin\uv.exe",
    [switch]$SkipDependencyInstallForTesting,
    [switch]$PrepareOnlyForTesting,
    [switch]$SkipBackendStoppedCheckForTesting
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
$ExpectedCommitSha = $ExpectedCommitSha.ToLowerInvariant()
if ($ExpectedCommitSha -notmatch "^[0-9a-f]{40}$") { throw "Expected commit SHA is invalid." }
if ([IO.Path]::GetFileName($ArtifactPath) -ne ("bap-backend-" + $ExpectedCommitSha + ".zip")) {
    throw "Artifact filename does not match the expected commit SHA."
}
Assert-BapChecksum -ArtifactPath $ArtifactPath -ChecksumPath $ChecksumPath
if (-not $SkipDependencyInstallForTesting -and -not (Test-Path -LiteralPath $UvPath -PathType Leaf)) { throw "uv was not found." }

$Temp = Join-Path $Root ("incoming\extract-" + [Guid]::NewGuid().ToString("N"))
$Release = Assert-BapReleasePath -Root $Root -ReleasePath (Join-Path $Root ("releases\" + $ExpectedCommitSha))
if (Test-Path -LiteralPath $Release) { throw "Immutable release already exists: $Release" }
try {
    New-Item -ItemType Directory -Path $Temp -Force | Out-Null
    Expand-Archive -LiteralPath $ArtifactPath -DestinationPath $Temp
    $ManifestPath = Join-Path $Temp "deployment-manifest.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Artifact manifest is missing." }
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($Manifest.project -ne "BAP" -or $Manifest.component -ne "backend" -or $Manifest.commit_sha -ne $ExpectedCommitSha) {
        throw "Artifact manifest does not match the requested Backend release."
    }
    $Allowed = @("bap_backend", "bap_common", "migrations", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version", "deployment-manifest.json")
    foreach ($Item in Get-ChildItem -LiteralPath $Temp -Force) {
        if ($Allowed -notcontains $Item.Name) { throw "Artifact contains an unexpected top-level path." }
    }
    Move-Item -LiteralPath $Temp -Destination $Release
    $Python = Join-Path $Release ".venv\Scripts\python.exe"
    if (-not $SkipDependencyInstallForTesting) {
        & $UvPath sync --directory $Release --frozen --extra backend --no-dev --no-extra desktop --no-extra packaging
        if ($LASTEXITCODE -ne 0) { throw "Unable to install locked Backend production dependencies." }
        & $Python -c "from bap_backend.app.main import create_app; assert create_app"
        if ($LASTEXITCODE -ne 0) { throw "Backend release smoke test failed." }
    }
    if ($PrepareOnlyForTesting) { Write-Output ("BAP Backend release prepared: " + $ExpectedCommitSha); return }

    if (-not $SkipBackendStoppedCheckForTesting) {
        $Listener = Get-NetTCPConnection -LocalPort 12345 -State Listen -ErrorAction SilentlyContinue
        if ($Listener) {
            throw "Port 12345 is still in use. Stop the foreground BAP Backend with Ctrl+C before deploying."
        }
    }
    $OldRelease = Get-BapCurrentTarget -Root $Root
    if ($OldRelease) { Set-Content -LiteralPath (Join-Path $Root "run\previous-release.txt") -Value $OldRelease -Encoding Ascii }
    $Database = Join-Path $Root "data\bap.db"
    $Backup = $null
    if (Test-Path -LiteralPath $Database -PathType Leaf) {
        $Backup = Join-Path $Root ("backups\bap-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + $ExpectedCommitSha + ".db")
        Copy-Item -LiteralPath $Database -Destination $Backup
    }
    Import-BapEnvironment -Path (Join-Path $Root "config\.env")
    Push-Location $Release
    try { & $Python -m alembic -c (Join-Path $Release "alembic.ini") upgrade head } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) {
        if ($Backup) { Copy-Item -LiteralPath $Backup -Destination $Database -Force }
        throw "Alembic migration failed."
    }
    $Current = Join-Path $Root "current"
    if (Test-Path -LiteralPath $Current) { Remove-Item -LiteralPath $Current -Force }
    & "C:\WINDOWS\system32\cmd.exe" /d /c mklink /J $Current $Release | Out-Null
    if ($LASTEXITCODE -ne 0) {
        if ($OldRelease) {
            & "C:\WINDOWS\system32\cmd.exe" /d /c mklink /J $Current $OldRelease | Out-Null
        }
        if ($Backup) { Copy-Item -LiteralPath $Backup -Destination $Database -Force }
        throw "Unable to switch the current junction. The previous release was restored when available."
    }
    Write-Output ("BAP Backend release deployed: " + $ExpectedCommitSha)
    Write-Output "Start the Backend manually in a foreground Terminal, then run Test-BapBackendHealth.ps1."
} finally {
    Remove-BapTreeWithinRoot -Root (Join-Path $Root "incoming") -Path $Temp
}
