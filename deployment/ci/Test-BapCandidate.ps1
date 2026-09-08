[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackendArtifact,
    [Parameter(Mandatory = $true)][string]$BackendChecksum,
    [Parameter(Mandatory = $true)][string]$DesktopInstaller,
    [Parameter(Mandatory = $true)][string]$SourceTreeSha,
    [string]$UvPath = "C:\Users\runneradmin\.local\bin\uv.exe",
    [string]$WorkDirectory,
    [string]$PreviousDesktopInstaller
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $RepoRoot "deployment\windows\backend\Common-BapDeployment.ps1")
if ($SourceTreeSha -notmatch "^[0-9a-f]{40}$") { throw "Source Tree SHA is invalid." }
if (-not $WorkDirectory) {
    $WorkDirectory = if ($env:RUNNER_TEMP) {
        Join-Path $env:RUNNER_TEMP "bap-candidate-e2e"
    } else {
        Join-Path $RepoRoot ".candidate-e2e"
    }
}
if (-not (Test-Path -LiteralPath $UvPath -PathType Leaf)) {
    $WindowsUvPath = $UvPath + ".exe"
    if (Test-Path -LiteralPath $WindowsUvPath -PathType Leaf) {
        $UvPath = $WindowsUvPath
    } else {
        throw "uv was not found: $UvPath"
    }
}
Assert-BapChecksum -ArtifactPath $BackendArtifact -ChecksumPath $BackendChecksum
if (-not (Test-Path -LiteralPath $DesktopInstaller -PathType Leaf)) { throw "Desktop Installer was not found." }

$Release = Join-Path $WorkDirectory "backend-release"
$Database = Join-Path $WorkDirectory "ci.db"
$Logs = Join-Path $WorkDirectory "logs"
$BackendOut = Join-Path $Logs "backend.stdout.log"
$BackendErr = Join-Path $Logs "backend.stderr.log"
$BackendProcess = $null
try {
    if (Test-Path -LiteralPath $WorkDirectory) {
        Remove-BapTreeWithinRoot -Root (Split-Path $WorkDirectory) -Path $WorkDirectory
    }
    New-Item -ItemType Directory -Path $Release, $Logs -Force | Out-Null
    Expand-Archive -LiteralPath $BackendArtifact -DestinationPath $Release
    $Manifest = Get-Content -LiteralPath (Join-Path $Release "deployment-manifest.json") -Raw | ConvertFrom-Json
    if ($Manifest.project -ne "BAP" -or $Manifest.component -ne "backend" -or $Manifest.source_tree_sha -ne $SourceTreeSha) {
        throw "Backend Artifact metadata does not match the Candidate."
    }

    & $UvPath sync --directory $Release --frozen --extra backend --no-dev --no-extra desktop --no-extra packaging
    if ($LASTEXITCODE -ne 0) { throw "Unable to install Backend Candidate dependencies." }
    $Python = Join-Path $Release ".venv\Scripts\python.exe"
    $env:BAP_ENV = "test"
    $env:BAP_BIND_HOST = "127.0.0.1"
    $env:BAP_BIND_PORT = "12345"
    $env:BAP_DATABASE_URL = "sqlite:///" + $Database.Replace("\", "/")
    $env:BAP_JWT_SIGNING_KEY = "ci-only-signing-key-not-for-production"
    $env:BAP_LOG_DIR = $Logs
    $env:BAP_COMMIT_SHA = $Manifest.commit_sha
    $env:BAP_CI_INSTALLER_HASH = (Get-FileHash -LiteralPath $DesktopInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:BAP_SOURCE_TREE_SHA = $SourceTreeSha

    Push-Location $Release
    try {
        & $Python -m alembic -c (Join-Path $Release "alembic.ini") upgrade 0002_app_release_source_tree_sha
        if ($LASTEXITCODE -ne 0) { throw "Unable to create the pre-change CI Database." }
        $SeedScript = Join-Path $WorkDirectory "ci_seed_existing_data.py"
        @'
import os
from datetime import datetime
from bap_backend.app.core.config import BackendSettings
from bap_backend.app.core.security import hash_password
from bap_backend.app.db.session import create_database_engine, create_session_factory
from bap_backend.app.models import AppRelease, User

settings = BackendSettings()
factory = create_session_factory(create_database_engine(settings.database_url))
with factory() as session:
    session.add(User(username="LegacyBoxer", password_hash=hash_password("boxing123")))
    session.add(AppRelease(
        platform="windows", version="0.0.0",
        download_url="https://github.com/conan0220/BAP/releases/download/ci/BAP-Setup.exe",
        sha256=os.environ["BAP_CI_INSTALLER_HASH"],
        source_tree_sha=os.environ["BAP_SOURCE_TREE_SHA"],
        published_at=datetime.utcnow(), is_active=True,
    ))
    session.commit()
'@ | Set-Content -LiteralPath $SeedScript -Encoding utf8
        & $Python $SeedScript
        if ($LASTEXITCODE -ne 0) { throw "Unable to seed existing account and update metadata." }
        & $Python -m alembic -c (Join-Path $Release "alembic.ini") upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Candidate Alembic migration failed." }
        & $Python -m alembic -c (Join-Path $Release "alembic.ini") downgrade 0002_app_release_source_tree_sha
        if ($LASTEXITCODE -ne 0) { throw "Candidate migration rollback rehearsal failed." }
        & $Python -m alembic -c (Join-Path $Release "alembic.ini") upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Candidate migration re-apply failed." }
        # 啟動 Artifact 內真正的 Backend application。不要在 Candidate E2E 注入固定結果，
        # 否則安裝後 Desktop 即使沒有成功呼叫 Production Executor，測試仍可能誤判為通過。
        $BackendProcess = Start-Process -FilePath $Python `
            -ArgumentList @("-m", "uvicorn", "bap_backend.app.main:app", "--host", "127.0.0.1", "--port", "12345") `
            -RedirectStandardOutput $BackendOut `
            -RedirectStandardError $BackendErr `
            -PassThru `
            -WindowStyle Hidden
    } finally {
        Pop-Location
    }

    $Ready = $false
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        if ($BackendProcess.HasExited) { break }
        try {
            $Response = Invoke-RestMethod -Uri "http://127.0.0.1:12345/health" -TimeoutSec 2
            if ($Response.status -eq "ok") { $Ready = $true; break }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $Ready) { throw "Backend Candidate did not become healthy." }

    $LoginBody = @{ username = "LegacyBoxer"; password = "boxing123" } | ConvertTo-Json
    $LegacyLogin = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:12345/api/v1/auth/login" -ContentType "application/json" -Body $LoginBody -TimeoutSec 10
    if (-not $LegacyLogin.access_token) { throw "Existing account did not survive migration rehearsal." }
    $ExistingRelease = Invoke-RestMethod -Uri "http://127.0.0.1:12345/api/v1/releases/latest?platform=windows" -TimeoutSec 10
    if ($ExistingRelease.source_tree_sha -ne $SourceTreeSha) { throw "Existing update metadata did not survive migration rehearsal." }

    $DesktopProgram = Join-Path $WorkDirectory "desktop-program"
    $DesktopData = Join-Path $WorkDirectory "desktop-data"
    & (Join-Path $RepoRoot "packaging\windows\Smoke-Test-BapInstaller.ps1") `
        -InstallerPath $DesktopInstaller `
        -ApiBaseUrl "http://127.0.0.1:12345/api/" `
        -InstallDirectory $DesktopProgram `
        -DataDirectory $DesktopData `
        -PreviousInstallerPath $PreviousDesktopInstaller `
        -RunRollbackTest:([bool]$PreviousDesktopInstaller) `
        -RunHandoffTest
    Write-Output "BAP Candidate production-like E2E passed."
} finally {
    if ($BackendProcess -and -not $BackendProcess.HasExited) {
        Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue
        if (-not $BackendProcess.WaitForExit(10000)) {
            throw "Backend Candidate process did not stop within 10 seconds."
        }
    }
    if ($BackendProcess) {
        $BackendProcess.Dispose()
    }
    if (Test-Path -LiteralPath $Database -PathType Leaf) {
        $DatabaseRemoved = $false
        for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
            try {
                Remove-Item -LiteralPath $Database -Force
                $DatabaseRemoved = $true
                break
            } catch [System.IO.IOException] {
                if ($Attempt -eq 20) { throw }
                Start-Sleep -Milliseconds 500
            }
        }
        if (-not $DatabaseRemoved) {
            throw "Unable to remove the Candidate E2E Database after waiting 10 seconds."
        }
    }
    if (Test-Path -LiteralPath $Release -PathType Container) {
        Remove-BapTreeWithinRoot -Root $WorkDirectory -Path $Release
    }
}
