[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$InnoSetupPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    [switch]$SkipInstaller,
    [string]$SignToolPath,
    [string]$CertificateThumbprint
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $PythonPath) {
    $PythonPath = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python was not found: $PythonPath"
}

Push-Location $RepoRoot
try {
    & $PythonPath -m PyInstaller --clean --noconfirm "packaging\windows\bap-desktop.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $AppExe = Join-Path $RepoRoot "dist\BAP\BAP.exe"
    if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) {
        throw "BAP.exe was not produced by the build."
    }

    if ($SignToolPath -and $CertificateThumbprint) {
        & $SignToolPath sign /sha1 $CertificateThumbprint /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 $AppExe
        if ($LASTEXITCODE -ne 0) { throw "Signing BAP.exe failed." }
    } else {
        Write-Warning "The Prototype artifact is unsigned. Provide SignToolPath and CertificateThumbprint before public release."
    }

    if (-not $SkipInstaller) {
        if (-not (Test-Path -LiteralPath $InnoSetupPath -PathType Leaf)) {
            throw "Inno Setup was not found: $InnoSetupPath"
        }
        & $InnoSetupPath (Join-Path $RepoRoot "packaging\windows\bap-installer.iss")
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }
    }
} finally {
    Pop-Location
}
