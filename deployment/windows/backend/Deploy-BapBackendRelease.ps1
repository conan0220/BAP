[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [Parameter(Mandatory = $true)][string]$ChecksumPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSourceTreeSha,
    [Parameter(Mandatory = $true)][string]$MasterCommitSha,
    [Parameter(Mandatory = $true)][string]$PromotionRecordPath,
    [string]$Root = "C:\BAP",
    [string]$UvPath = "C:\Users\user\.local\bin\uv.exe",
    [string]$TaskName = "BAPBackend",
    [switch]$SkipDependencyInstallForTesting,
    [switch]$PrepareOnlyForTesting,
    [switch]$SkipScheduledTaskForTesting,
    [switch]$SkipHealthCheckForTesting
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
foreach ($Sha in @($ExpectedSourceTreeSha, $MasterCommitSha)) {
    if ($Sha -notmatch "^[0-9a-f]{40}$") { throw "A required Git SHA is invalid." }
}
if ([IO.Path]::GetFileName($ArtifactPath) -ne ("bap-backend-tree-" + $ExpectedSourceTreeSha + ".zip")) {
    throw "Artifact filename does not match the expected Source Tree SHA."
}
Assert-BapChecksum -ArtifactPath $ArtifactPath -ChecksumPath $ChecksumPath
if (-not (Test-Path -LiteralPath $PromotionRecordPath -PathType Leaf)) { throw "Promotion record was not found." }
if (-not $SkipDependencyInstallForTesting -and -not (Test-Path -LiteralPath $UvPath -PathType Leaf)) { throw "uv was not found." }

$LockPath = Join-Path $Root "run\deployment.lock"
New-Item -ItemType Directory -Path (Split-Path $LockPath) -Force | Out-Null
try {
    $Lock = [IO.File]::Open($LockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
} catch {
    throw "Another Backend deployment is already running."
}

$Temp = Join-Path $Root ("incoming\extract-" + [Guid]::NewGuid().ToString("N"))
$Release = Assert-BapReleasePath -Root $Root -ReleasePath (Join-Path $Root ("releases\" + $MasterCommitSha))
$OldRelease = $null
$Backup = $null
try {
    if (Test-Path -LiteralPath $Release) {
        $Existing = Get-Content -LiteralPath (Join-Path $Release "deployment-manifest.json") -Raw | ConvertFrom-Json
        if ($Existing.source_tree_sha -ne $ExpectedSourceTreeSha) { throw "Immutable release exists with different content." }
    } else {
        New-Item -ItemType Directory -Path $Temp -Force | Out-Null
        Expand-Archive -LiteralPath $ArtifactPath -DestinationPath $Temp
        $Manifest = Get-Content -LiteralPath (Join-Path $Temp "deployment-manifest.json") -Raw | ConvertFrom-Json
        if ($Manifest.project -ne "BAP" -or $Manifest.component -ne "backend" -or $Manifest.source_tree_sha -ne $ExpectedSourceTreeSha) {
            throw "Artifact manifest does not match the requested Backend release."
        }
        $Allowed = @("bap_backend", "bap_common", "migrations", "deployment", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version", "deployment-manifest.json")
        foreach ($Item in Get-ChildItem -LiteralPath $Temp -Force) {
            if ($Allowed -notcontains $Item.Name) { throw "Artifact contains an unexpected top-level path." }
        }
        Move-Item -LiteralPath $Temp -Destination $Release
    }

    Copy-Item -LiteralPath $PromotionRecordPath -Destination (Join-Path $Release "promotion-record.json") -Force
    $Python = Join-Path $Release ".venv\Scripts\python.exe"
    if (-not $SkipDependencyInstallForTesting -and -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        & $UvPath sync --directory $Release --frozen --extra backend --no-dev --no-extra desktop --no-extra packaging
        if ($LASTEXITCODE -ne 0) { throw "Unable to install locked Backend production dependencies." }
        & $Python -c "from bap_backend.app.main import create_app; assert create_app"
        if ($LASTEXITCODE -ne 0) { throw "Backend release smoke test failed." }
    }
    if ($PrepareOnlyForTesting) {
        Write-Output ("BAP Backend release prepared: " + $MasterCommitSha)
        return
    }

    $OldRelease = Get-BapCurrentTarget -Root $Root
    if ($OldRelease) {
        Set-Content -LiteralPath (Join-Path $Root "run\previous-release.txt") -Value $OldRelease -Encoding Ascii
    }
    if (-not $SkipScheduledTaskForTesting) {
        Stop-BapBackendTaskAndListener -Root $Root -TaskName $TaskName
    }

    $Database = Join-Path $Root "data\bap.db"
    if (Test-Path -LiteralPath $Database -PathType Leaf) {
        $Backup = Join-Path $Root ("backups\bap-" + (Get-Date -Format "yyyyMMddHHmmss") + "-" + $MasterCommitSha + ".db")
        Copy-Item -LiteralPath $Database -Destination $Backup
    }
    Import-BapEnvironment -Path (Join-Path $Root "config\.env")
    Push-Location $Release
    try {
        & $Python -m alembic -c (Join-Path $Release "alembic.ini") upgrade head
    } finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }

    $Current = Join-Path $Root "current"
    Remove-BapCurrentJunction -Root $Root
    & "C:\WINDOWS\system32\cmd.exe" /d /c mklink /J $Current $Release | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to switch the current junction." }

    if (-not $SkipScheduledTaskForTesting) { Start-ScheduledTask -TaskName $TaskName }
    if (-not $SkipHealthCheckForTesting) {
        & (Join-Path $Release "deployment\runtime\Test-BapBackendHealth.ps1") -ExpectedCommitSha $MasterCommitSha
        if ($LASTEXITCODE -ne 0) { throw "Backend health check failed." }
    }
    $SucceededRecord = Get-Content -LiteralPath $PromotionRecordPath -Raw | ConvertFrom-Json
    $SucceededRecord.backend_result = "succeeded"
    $SucceededRecord | ConvertTo-Json | Set-Content -LiteralPath $PromotionRecordPath -Encoding UTF8
    Copy-Item -LiteralPath $PromotionRecordPath -Destination (Join-Path $Release "promotion-record.json") -Force
    Copy-Item -LiteralPath $PromotionRecordPath -Destination (Join-Path $Root "run\last-known-good.json") -Force
    Write-Output ("BAP Backend deployed: " + $MasterCommitSha)
} catch {
    $OriginalError = $_
    try {
        $FailedRecord = Get-Content -LiteralPath $PromotionRecordPath -Raw | ConvertFrom-Json
        $FailedRecord.backend_result = "failed"
        $FailedRecord | ConvertTo-Json | Set-Content -LiteralPath $PromotionRecordPath -Encoding UTF8
    } catch {}
    try {
        if ($OldRelease) {
            $Current = Join-Path $Root "current"
            Remove-BapCurrentJunction -Root $Root
            & "C:\WINDOWS\system32\cmd.exe" /d /c mklink /J $Current $OldRelease | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Unable to restore the previous current junction." }
            if ($Backup) { Copy-Item -LiteralPath $Backup -Destination (Join-Path $Root "data\bap.db") -Force }
            if (-not $SkipScheduledTaskForTesting) { Start-ScheduledTask -TaskName $TaskName }
            if (-not $SkipHealthCheckForTesting) {
                & (Join-Path $OldRelease "deployment\runtime\Test-BapBackendHealth.ps1")
            }
        }
    } catch {
        throw ("Deployment failed and rollback also failed. Deployment: " + $OriginalError.Exception.Message + "; rollback: " + $_.Exception.Message)
    }
    throw $OriginalError
} finally {
    if ($Lock) { $Lock.Dispose() }
    if (Test-Path -LiteralPath $LockPath) { Remove-Item -LiteralPath $LockPath -Force }
    Remove-BapTreeWithinRoot -Root (Join-Path $Root "incoming") -Path $Temp
}
