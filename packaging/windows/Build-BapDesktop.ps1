[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$OutputDirectory,
    [string]$WorkDirectory,
    [string]$SourceTreeSha,
    [string]$GitPath = "C:\Program Files\Git\cmd\git.exe",
    [string]$InnoSetupPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    [switch]$SkipInstaller,
    [string]$SignToolPath,
    [string]$CertificateThumbprint
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $PythonPath) { $PythonPath = Join-Path $RepoRoot ".venv\Scripts\python.exe" }
if (-not $OutputDirectory) {
    $OutputDirectory = if ($env:RUNNER_TEMP) { Join-Path $env:RUNNER_TEMP "bap-candidate" } else { Join-Path $RepoRoot "dist" }
}
if (-not $WorkDirectory) {
    $WorkDirectory = if ($env:RUNNER_TEMP) { Join-Path $env:RUNNER_TEMP "bap-desktop-build" } else { Join-Path $RepoRoot "build" }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python was not found: $PythonPath" }
if (-not $SourceTreeSha) {
    if (-not (Test-Path -LiteralPath $GitPath -PathType Leaf)) { throw "Git was not found: $GitPath" }
    $SourceTreeSha = (& $GitPath -C $RepoRoot rev-parse "HEAD^{tree}").Trim().ToLowerInvariant()
}
if ($SourceTreeSha -notmatch "^[0-9a-f]{40}$") { throw "Source Tree SHA is invalid." }

$Version = (Get-Content -LiteralPath (Join-Path $RepoRoot "bap_desktop\VERSION") -Raw).Trim()
$AppDist = Join-Path $WorkDirectory "app"
$PyInstallerWork = Join-Path $WorkDirectory "pyinstaller"
$GeneratedIss = Join-Path $WorkDirectory "bap-installer.generated.iss"
New-Item -ItemType Directory -Path $OutputDirectory, $WorkDirectory -Force | Out-Null

Push-Location $RepoRoot
try {
    & $PythonPath -m PyInstaller --clean --noconfirm --distpath $AppDist --workpath $PyInstallerWork "packaging\windows\bap-desktop.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $AppDirectory = Join-Path $AppDist "BAP"
    $AppExe = Join-Path $AppDirectory "BAP.exe"
    if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) { throw "BAP.exe was not produced by the build." }

    if ($SignToolPath -and $CertificateThumbprint) {
        & $SignToolPath sign /sha1 $CertificateThumbprint /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 $AppExe
        if ($LASTEXITCODE -ne 0) { throw "Signing BAP.exe failed." }
    } else {
        Write-Warning "The Prototype artifact is unsigned."
    }

    if (-not $SkipInstaller) {
        if (-not (Test-Path -LiteralPath $InnoSetupPath -PathType Leaf)) { throw "Inno Setup was not found: $InnoSetupPath" }
        $Iss = Get-Content -LiteralPath (Join-Path $PSScriptRoot "bap-installer.iss") -Raw
        $Iss = $Iss.Replace('#define MyAppVersion "0.1.0"', ('#define MyAppVersion "' + $Version + '"'))
        $Iss = $Iss.Replace('OutputDir=..\..\dist', ('OutputDir=' + $OutputDirectory))
        $Iss = $Iss.Replace('Source: "..\..\dist\BAP\*"', ('Source: "' + $AppDirectory + '\*"'))
        Set-Content -LiteralPath $GeneratedIss -Value $Iss -Encoding UTF8
        & $InnoSetupPath $GeneratedIss
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }

        $Installer = Join-Path $OutputDirectory ("BAP-Setup-" + $Version + ".exe")
        if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) { throw "Desktop Installer was not produced." }
        $Hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
        $Checksum = $Installer + ".sha256"
        Set-Content -LiteralPath $Checksum -Value ($Hash + "  " + [IO.Path]::GetFileName($Installer)) -Encoding Ascii
        $Metadata = [ordered]@{
            project = "BAP"
            component = "desktop"
            version = $Version
            source_tree_sha = $SourceTreeSha
            filename = [IO.Path]::GetFileName($Installer)
            sha256 = $Hash
        }
        $MetadataPath = Join-Path $OutputDirectory ("BAP-Setup-" + $Version + ".metadata.json")
        $Metadata | ConvertTo-Json | Set-Content -LiteralPath $MetadataPath -Encoding UTF8
        Write-Output $Installer
        Write-Output $Checksum
        Write-Output $MetadataPath
    }
} finally {
    Pop-Location
}
