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

$VersionPath = Join-Path $RepoRoot "bap_desktop\VERSION"
$Version = (Get-Content -LiteralPath $VersionPath -Raw).Trim()
if ($Version -notmatch "^\d+\.\d+\.\d+([+-][0-9A-Za-z.-]+)?$") {
    throw "Desktop version could not be read from bap_desktop\VERSION."
}
$AppDist = Join-Path $WorkDirectory "app"
$BootstrapDist = Join-Path $WorkDirectory "bootstrap"
$PyInstallerWork = Join-Path $WorkDirectory "pyinstaller-app"
$GeneratedIss = Join-Path $WorkDirectory "bap-installer.generated.iss"
New-Item -ItemType Directory -Path $OutputDirectory, $WorkDirectory -Force | Out-Null

Push-Location $RepoRoot
try {
    & $PythonPath -m PyInstaller --clean --noconfirm --distpath $AppDist --workpath $PyInstallerWork "packaging\windows\bap-desktop.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
    & $PythonPath -m PyInstaller --clean --noconfirm --distpath $BootstrapDist --workpath (Join-Path $WorkDirectory "pyinstaller-launcher") "packaging\windows\bap-launcher.spec"
    if ($LASTEXITCODE -ne 0) { throw "BAPLauncher build failed." }
    & $PythonPath -m PyInstaller --clean --noconfirm --distpath $BootstrapDist --workpath (Join-Path $WorkDirectory "pyinstaller-updater") "packaging\windows\bap-updater.spec"
    if ($LASTEXITCODE -ne 0) { throw "BAPUpdater build failed." }

    $AppDirectory = Join-Path $AppDist "BAP"
    $AppExe = Join-Path $AppDirectory "BAP.exe"
    $LauncherDirectory = Join-Path $BootstrapDist "BAPLauncher"
    $UpdaterDirectory = Join-Path $BootstrapDist "BAPUpdater"
    $LauncherExe = Join-Path $LauncherDirectory "BAPLauncher.exe"
    $UpdaterExe = Join-Path $UpdaterDirectory "BAPUpdater.exe"
    if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) { throw "BAP.exe was not produced by the build." }
    if (-not (Test-Path -LiteralPath $LauncherExe -PathType Leaf)) { throw "BAPLauncher.exe was not produced by the build." }
    if (-not (Test-Path -LiteralPath $UpdaterExe -PathType Leaf)) { throw "BAPUpdater.exe was not produced by the build." }

    $ReleaseManifest = [ordered]@{
        schema_version = 1
        version = $Version
        source_tree_sha = $SourceTreeSha
        entry_point = "BAP.exe"
        created_at = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
        legacy = $false
    }
    $ReleaseManifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $AppDirectory "release-manifest.json") -Encoding UTF8

    if ($SignToolPath -and $CertificateThumbprint) {
        foreach ($Executable in @($AppExe, $LauncherExe, $UpdaterExe)) {
            & $SignToolPath sign /sha1 $CertificateThumbprint /fd SHA256 /tr "http://timestamp.digicert.com" /td SHA256 $Executable
            if ($LASTEXITCODE -ne 0) { throw "Signing $Executable failed." }
        }
    } else {
        Write-Warning "The Prototype artifact is unsigned."
    }

    if (-not $SkipInstaller) {
        if (-not (Test-Path -LiteralPath $InnoSetupPath -PathType Leaf)) { throw "Inno Setup was not found: $InnoSetupPath" }
        $Iss = Get-Content -LiteralPath (Join-Path $PSScriptRoot "bap-installer.iss") -Raw -Encoding UTF8
        $Iss = $Iss.Replace('#define MyAppVersion "__BAP_VERSION__"', ('#define MyAppVersion "' + $Version + '"'))
        $Iss = $Iss.Replace('OutputDir=..\..\dist', ('OutputDir=' + $OutputDirectory))
        $Iss = $Iss.Replace('Source: "..\..\dist\BAP\*"', ('Source: "' + $AppDirectory + '\*"'))
        $Iss = $Iss.Replace('Source: "..\..\dist\BAPLauncher.exe"', ('Source: "' + $LauncherExe + '"'))
        $Iss = $Iss.Replace('Source: "..\..\dist\BAPUpdater.exe"', ('Source: "' + $UpdaterExe + '"'))
        $Iss = $Iss.Replace('Source: "..\..\dist\launcher_runtime\*"', ('Source: "' + (Join-Path $LauncherDirectory 'launcher_runtime\*') + '"'))
        $Iss = $Iss.Replace('Source: "..\..\dist\updater_runtime\*"', ('Source: "' + (Join-Path $UpdaterDirectory 'updater_runtime\*') + '"'))
        Set-Content -LiteralPath $GeneratedIss -Value $Iss -Encoding UTF8
        & $InnoSetupPath $GeneratedIss
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }

        $Installer = Join-Path $OutputDirectory ("BAP-Setup-" + $Version + ".exe")
        if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) { throw "Desktop Installer was not produced." }
        $Hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
        $Checksum = $Installer + ".sha256"
        Set-Content -LiteralPath $Checksum -Value ($Hash + "  " + [IO.Path]::GetFileName($Installer)) -Encoding Ascii
        $Metadata = [ordered]@{
            schema_version = 1
            project = "BAP"
            component = "desktop"
            version = $Version
            platform = "windows"
            architecture = "x86_64"
            source_tree_sha = $SourceTreeSha
            installer_filename = [IO.Path]::GetFileName($Installer)
            installer_size_bytes = (Get-Item -LiteralPath $Installer).Length
            installer_sha256 = $Hash
            runtime_entries = [ordered]@{
                desktop = "releases/$Version/BAP.exe"
                launcher = "BAPLauncher.exe"
                updater = "BAPUpdater.exe"
            }
            candidate_run_id = if ($env:GITHUB_RUN_ID) { $env:GITHUB_RUN_ID } else { "local" }
            created_at = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
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
