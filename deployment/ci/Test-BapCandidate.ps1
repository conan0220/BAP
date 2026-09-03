[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackendArtifact,
    [Parameter(Mandatory = $true)][string]$BackendChecksum,
    [Parameter(Mandatory = $true)][string]$DesktopInstaller,
    [Parameter(Mandatory = $true)][string]$SourceTreeSha,
    [string]$UvPath = "C:\Users\runneradmin\.local\bin\uv.exe",
    [string]$WorkDirectory
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

    Push-Location $Release
    try {
        & $Python -m alembic -c (Join-Path $Release "alembic.ini") upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Candidate Alembic migration failed." }
        $InstallerHash = (Get-FileHash -LiteralPath $DesktopInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
        & $Python -m bap_backend.tools.publish_desktop_release --platform windows --version "0.0.0" --download-url "https://github.com/conan0220/BAP/releases/download/ci/BAP-Setup.exe" --sha256 $InstallerHash --source-tree-sha $SourceTreeSha
        if ($LASTEXITCODE -ne 0) { throw "Unable to seed the CI update-check record." }
        $BackendProcess = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "bap_backend.app.main:app", "--host", "127.0.0.1", "--port", "12345") -RedirectStandardOutput $BackendOut -RedirectStandardError $BackendErr -PassThru -WindowStyle Hidden
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

    & (Join-Path $RepoRoot "packaging\windows\Smoke-Test-BapInstaller.ps1") -InstallerPath $DesktopInstaller -ApiBaseUrl "http://127.0.0.1:12345/api/"
    if ($LASTEXITCODE -ne 0) { throw "Installed Desktop Candidate E2E failed." }
    Write-Output "BAP Candidate production-like E2E passed."
} finally {
    if ($BackendProcess -and -not $BackendProcess.HasExited) {
        Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue
        $BackendProcess.WaitForExit()
    }
    if (Test-Path -LiteralPath $Database -PathType Leaf) { Remove-Item -LiteralPath $Database -Force }
    if (Test-Path -LiteralPath $Release -PathType Container) {
        Remove-BapTreeWithinRoot -Root $WorkDirectory -Path $Release
    }
}
