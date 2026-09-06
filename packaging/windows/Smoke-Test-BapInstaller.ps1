[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [string]$ApiBaseUrl,
    [string]$InstallDirectory,
    [string]$DataDirectory,
    [string]$PreviousInstallerPath,
    [switch]$RunRollbackTest,
    [switch]$RunHandoffTest
)

$ErrorActionPreference = "Stop"
$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
$InstallDir = if ($InstallDirectory) { $InstallDirectory } else { Join-Path $env:LOCALAPPDATA "Programs\BAP" }
$DataDir = if ($DataDirectory) { $DataDirectory } else { Join-Path $env:LOCALAPPDATA "BAP" }
$LauncherExe = Join-Path $InstallDir "BAPLauncher.exe"
$Uninstaller = Join-Path $InstallDir "unins000.exe"
$VersionProbe = Join-Path $env:TEMP ("bap-version-" + [Guid]::NewGuid().ToString("N") + ".txt")
$LaunchResult = Join-Path $env:TEMP ("bap-launch-" + [Guid]::NewGuid().ToString("N") + ".json")
$ApiE2EResult = Join-Path $env:TEMP ("bap-api-e2e-" + [Guid]::NewGuid().ToString("N") + ".json")
$InstallerName = [IO.Path]::GetFileName($InstallerPath)
$VersionMatch = [regex]::Match($InstallerName, '^BAP-Setup-(?<version>\d+\.\d+\.\d+(?:[+-][0-9A-Za-z.-]+)?)\.exe$')
if (-not $VersionMatch.Success) { throw "BAP installer filename does not contain a valid version." }
$ExpectedVersion = $VersionMatch.Groups["version"].Value
$PreviousVersion = $null
if ($PreviousInstallerPath) {
    $PreviousInstallerPath = (Resolve-Path -LiteralPath $PreviousInstallerPath).Path
    $PreviousMatch = [regex]::Match([IO.Path]::GetFileName($PreviousInstallerPath), '^BAP-Setup-(?<version>\d+\.\d+\.\d+(?:[+-][0-9A-Za-z.-]+)?)\.exe$')
    if (-not $PreviousMatch.Success) { throw "Previous BAP installer filename does not contain a valid version." }
    $PreviousVersion = $PreviousMatch.Groups["version"].Value
}

function Invoke-BapProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$TimeoutSeconds = 180
    )

    Write-Host "Starting $Label (timeout: $TimeoutSeconds seconds)."
    $Process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru
    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw "$Label timed out after $TimeoutSeconds seconds."
    }
    if ($Process.ExitCode -ne 0) {
        throw "$Label exited with $($Process.ExitCode)."
    }
    Write-Host "$Label completed."
}

function Invoke-BapAppCheck {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$TimeoutSeconds = 120,
        [string]$DiagnosticPath
    )

    Remove-Item -LiteralPath $LaunchResult -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ApiE2EResult -Force -ErrorAction SilentlyContinue
    $LauncherArguments = @("--program-root", $InstallDir, "--user-data-root", $DataDir, "--result-file", $LaunchResult, "--") + $Arguments
    Invoke-BapProcess -FilePath $LauncherExe -Arguments $LauncherArguments -Label "$Label Launcher" -TimeoutSeconds 30
    if (-not (Test-Path -LiteralPath $LaunchResult -PathType Leaf)) { throw "$Label did not produce a Launcher result." }
    $Started = Get-Content -LiteralPath $LaunchResult -Raw -Encoding UTF8 | ConvertFrom-Json
    $AppProcess = Get-Process -Id $Started.pid -ErrorAction SilentlyContinue
    if ($AppProcess) {
        if (-not $AppProcess.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $AppProcess.Id -Force -ErrorAction SilentlyContinue
            $Diagnostic = if ($DiagnosticPath -and (Test-Path -LiteralPath $DiagnosticPath -PathType Leaf)) {
                (Get-Content -LiteralPath $DiagnosticPath -Raw -Encoding UTF8).Trim()
            } else {
                "no diagnostic result"
            }
            throw "$Label timed out after $TimeoutSeconds seconds. Last result: $Diagnostic"
        }
        if ($AppProcess.ExitCode -ne 0) {
            $Diagnostic = if ($DiagnosticPath -and (Test-Path -LiteralPath $DiagnosticPath -PathType Leaf)) {
                (Get-Content -LiteralPath $DiagnosticPath -Raw -Encoding UTF8).Trim()
            } else {
                "no diagnostic result"
            }
            throw "$Label exited with $($AppProcess.ExitCode). Result: $Diagnostic"
        }
    }
}

try {
    if ($PreviousInstallerPath) {
        Invoke-BapProcess -FilePath $PreviousInstallerPath -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", ("/DIR=" + $InstallDir)) -Label "Previous BAP installer"
        $LegacyPreviousExe = Join-Path $InstallDir "BAP.exe"
        $VersionedPreviousExe = Join-Path $InstallDir ("releases\" + $PreviousVersion + "\BAP.exe")
        $PreviousStatePath = Join-Path $InstallDir "active-release.json"
        $PreviousLauncher = Join-Path $InstallDir "BAPLauncher.exe"
        $PreviousIsLegacy = Test-Path -LiteralPath $LegacyPreviousExe -PathType Leaf
        $PreviousIsVersioned =
            (Test-Path -LiteralPath $PreviousLauncher -PathType Leaf) -and
            (Test-Path -LiteralPath $PreviousStatePath -PathType Leaf) -and
            (Test-Path -LiteralPath $VersionedPreviousExe -PathType Leaf)

        if (-not $PreviousIsLegacy -and -not $PreviousIsVersioned) {
            throw "Previous public BAP Runtime was installed in neither the Legacy nor Versioned layout."
        }
        if ($PreviousIsVersioned) {
            $PreviousState = Get-Content -LiteralPath $PreviousStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($PreviousState.active_version -ne $PreviousVersion) {
                throw "Previous Versioned Install did not activate $PreviousVersion."
            }
            Write-Output "Previous public BAP Runtime $PreviousVersion uses the Versioned Install layout."
        } else {
            Write-Output "Previous public BAP Runtime $PreviousVersion uses the Legacy Install layout."
        }
    }
    $Sentinel = Join-Path $DataDir "sentinel\keep.txt"
    New-Item -ItemType Directory -Path (Split-Path $Sentinel) -Force | Out-Null
    Set-Content -LiteralPath $Sentinel -Value "user-data-must-survive" -Encoding UTF8

    $InstallArguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", ("/DIR=" + $InstallDir), ("/BAPDATADIR=" + $DataDir))
    $PreviousBapEnvironment = $env:BAP_ENV
    try {
        $env:BAP_ENV = "test"
        Invoke-BapProcess -FilePath $InstallerPath -Arguments $InstallArguments -Label "Candidate BAP installer"
    } finally {
        $env:BAP_ENV = $PreviousBapEnvironment
    }
    if (-not (Test-Path -LiteralPath $LauncherExe -PathType Leaf)) { throw "BAPLauncher.exe was not installed." }
    $StatePath = Join-Path $InstallDir "active-release.json"
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { throw "Active Release state was not created." }
    $State = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($State.active_version -ne $ExpectedVersion) { throw "Installer did not activate $ExpectedVersion." }
    if ($PreviousVersion -and $State.previous_version -ne $PreviousVersion) {
        throw "Legacy $PreviousVersion was not preserved as Previous Release."
    }
    $AppExe = Join-Path $InstallDir ("releases\" + $ExpectedVersion + "\BAP.exe")
    if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) { throw "Versioned BAP.exe was not installed." }

    Invoke-BapAppCheck -Arguments @("--write-version", $VersionProbe) -Label "BAP Runtime version check" -TimeoutSeconds 60
    if (-not (Test-Path -LiteralPath $VersionProbe -PathType Leaf)) { throw "BAP Runtime did not report its version." }
    $RuntimeVersion = (Get-Content -LiteralPath $VersionProbe -Raw -Encoding UTF8).Trim()
    if ($RuntimeVersion -ne $ExpectedVersion) {
        throw "BAP Runtime version $RuntimeVersion does not match Installer version $ExpectedVersion."
    }
    if ((Get-Content -LiteralPath $Sentinel -Raw -Encoding UTF8).Trim() -ne "user-data-must-survive") {
        throw "Sentinel User Data changed during installation or upgrade."
    }

    Invoke-BapAppCheck -Arguments @("--smoke-test") -Label "BAP launch smoke test" -TimeoutSeconds 60

    if ($ApiBaseUrl) {
        $PreviousApiBaseUrl = $env:BAP_API_BASE_URL
        try {
            $env:BAP_API_BASE_URL = $ApiBaseUrl
            Remove-Item -LiteralPath $ApiE2EResult -Force -ErrorAction SilentlyContinue
            Invoke-BapAppCheck `
                -Arguments @("--api-e2e-test", "--api-e2e-result-file", $ApiE2EResult) `
                -Label "Installed BAP API E2E" `
                -TimeoutSeconds 120 `
                -DiagnosticPath $ApiE2EResult
            if (-not (Test-Path -LiteralPath $ApiE2EResult -PathType Leaf)) {
                throw "Installed BAP API E2E did not produce a diagnostic result."
            }
            $ApiE2EOutcome = Get-Content -LiteralPath $ApiE2EResult -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($ApiE2EOutcome.status -ne "succeeded") {
                throw "Installed BAP API E2E failed at $($ApiE2EOutcome.stage): $($ApiE2EOutcome.message)"
            }
        } finally {
            $env:BAP_API_BASE_URL = $PreviousApiBaseUrl
        }
    }

    if ($RunHandoffTest) {
        $HandoffOperation = "handoff-smoke-" + [Guid]::NewGuid().ToString("N")
        $HandoffInstaller = Join-Path $DataDir ("updates\" + $InstallerName)
        New-Item -ItemType Directory -Path (Split-Path $HandoffInstaller) -Force | Out-Null
        Copy-Item -LiteralPath $InstallerPath -Destination $HandoffInstaller -Force
        $HandoffSha = (Get-FileHash -LiteralPath $HandoffInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
        $Updater = Join-Path $InstallDir "BAPUpdater.exe"
        $PreviousBapEnvironment = $env:BAP_ENV
        try {
            $env:BAP_ENV = "test"
            & $Updater handoff --installer $HandoffInstaller --version $ExpectedVersion --sha256 $HandoffSha --old-pid 0 --operation-id $HandoffOperation --program-root $InstallDir --user-data-root $DataDir
            if ($LASTEXITCODE -ne 0) { throw "Packaged Updater handoff was not accepted." }
            $JournalPath = Join-Path $DataDir "updates\$HandoffOperation\operation.json"
            $Deadline = [DateTime]::UtcNow.AddMinutes(3)
            $HandoffJournal = $null
            do {
                Start-Sleep -Milliseconds 250
                if (Test-Path -LiteralPath $JournalPath -PathType Leaf) {
                    try {
                        $HandoffJournal = Get-Content -LiteralPath $JournalPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    } catch {
                        $HandoffJournal = $null
                    }
                }
                if ($HandoffJournal -and $HandoffJournal.status -in @("succeeded", "install_failed", "health_failed", "rolled_back", "rollback_failed")) { break }
            } while ([DateTime]::UtcNow -lt $Deadline)
            if (-not $HandoffJournal -or $HandoffJournal.status -ne "succeeded") {
                $Status = if ($HandoffJournal) { $HandoffJournal.status } else { "timeout" }
                throw "Packaged Updater handoff did not succeed: $Status"
            }
            $HandoffLaunch = Join-Path $DataDir "updates\$HandoffOperation\candidate-launch.json"
            if (Test-Path -LiteralPath $HandoffLaunch -PathType Leaf) {
                $HandoffPid = (Get-Content -LiteralPath $HandoffLaunch -Raw -Encoding UTF8 | ConvertFrom-Json).pid
                Stop-Process -Id $HandoffPid -Force -ErrorAction SilentlyContinue
            }
        } finally {
            $env:BAP_ENV = $PreviousBapEnvironment
        }
        if ((Get-Content -LiteralPath $Sentinel -Raw -Encoding UTF8).Trim() -ne "user-data-must-survive") {
            throw "Packaged Updater handoff changed Sentinel Data."
        }
        Write-Output "BAP packaged Updater handoff E2E passed."
    }

    $TempDir = Join-Path $DataDir "temp\imu-diagnostics"
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    $Sentinel = Join-Path $TempDir "installer-smoke.csv"
    Set-Content -LiteralPath $Sentinel -Value "user-data-must-survive" -Encoding UTF8
} finally {
    Remove-Item -LiteralPath $VersionProbe -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $LaunchResult -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ApiE2EResult -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Uninstaller -PathType Leaf) {
        Invoke-BapProcess -FilePath $Uninstaller -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Label "BAP uninstaller"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $DataDir "temp\imu-diagnostics\installer-smoke.csv") -PathType Leaf)) {
    throw "Uninstall removed User Data Root content."
}
if ($RunRollbackTest) {
    if (-not $PreviousInstallerPath) { throw "Rollback E2E requires PreviousInstallerPath." }
    $RollbackProgram = $InstallDir + "-rollback"
    $RollbackData = $DataDir + "-rollback"
    $RollbackOperation = "rollback-test"
    $RollbackUninstaller = Join-Path $RollbackProgram "unins000.exe"
    try {
        Invoke-BapProcess -FilePath $PreviousInstallerPath -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", ("/DIR=" + $RollbackProgram)) -Label "Rollback E2E Previous Public Version installer"
        $RollbackSentinel = Join-Path $RollbackData "sentinel\keep.txt"
        New-Item -ItemType Directory -Path (Split-Path $RollbackSentinel) -Force | Out-Null
        Set-Content -LiteralPath $RollbackSentinel -Value "rollback-must-preserve" -Encoding UTF8
        Invoke-BapProcess -FilePath $InstallerPath -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/BAPMANAGED=1", ("/DIR=" + $RollbackProgram), ("/BAPDATADIR=" + $RollbackData)) -Label "Rollback E2E Candidate installer"

        $Updater = Join-Path $RollbackProgram "BAPUpdater.exe"
        $PreviousEnvironment = @($env:BAP_ENV, $env:BAP_TEST_SUPPRESS_READY_SIGNAL)
        try {
            $env:BAP_ENV = "test"
            $env:BAP_TEST_SUPPRESS_READY_SIGNAL = "1"
            & $Updater finalize --version $ExpectedVersion --operation-id $RollbackOperation --launch-and-wait --ready-timeout 2 --program-root $RollbackProgram --user-data-root $RollbackData
            $RollbackExit = $LASTEXITCODE
        } finally {
            $env:BAP_ENV = $PreviousEnvironment[0]
            $env:BAP_TEST_SUPPRESS_READY_SIGNAL = $PreviousEnvironment[1]
        }
        if ($RollbackExit -eq 0) { throw "Failure Injection unexpectedly accepted the Candidate." }
        $RollbackState = Get-Content -LiteralPath (Join-Path $RollbackProgram "active-release.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($RollbackState.active_version -ne $PreviousVersion) { throw "Rollback did not restore $PreviousVersion." }
        $RollbackJournal = Get-Content -LiteralPath (Join-Path $RollbackData "updates\$RollbackOperation\operation.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($RollbackJournal.status -ne "rolled_back") { throw "Rollback operation did not reach rolled_back." }
        if ((Get-Content -LiteralPath $RollbackSentinel -Raw -Encoding UTF8).Trim() -ne "rollback-must-preserve") { throw "Rollback changed Sentinel Data." }
        $RollbackLaunch = Join-Path $RollbackData "updates\$RollbackOperation\rollback-launch.json"
        if (Test-Path -LiteralPath $RollbackLaunch) {
            $RollbackPid = (Get-Content -LiteralPath $RollbackLaunch -Raw -Encoding UTF8 | ConvertFrom-Json).pid
            Stop-Process -Id $RollbackPid -Force -ErrorAction SilentlyContinue
        }
    } finally {
        if (Test-Path -LiteralPath $RollbackUninstaller -PathType Leaf) {
            Invoke-BapProcess -FilePath $RollbackUninstaller -Arguments @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Label "Rollback E2E uninstaller"
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RollbackData "sentinel\keep.txt") -PathType Leaf)) {
        throw "Rollback uninstall removed User Data Root."
    }
    Write-Output "BAP Failure Injection Rollback E2E passed."
}
if ($PreviousVersion) {
    Write-Output "BAP upgrade from $PreviousVersion to $ExpectedVersion passed; Sentinel Data survived."
} else {
    Write-Output "BAP fresh versioned installer smoke test passed; no Previous Public Version was supplied."
}

# Failure Injection intentionally makes the packaged Updater return a non-zero
# native exit code. Reaching this line means every rollback assertion passed,
# so do not let that expected native result become the GitHub Actions step result.
$global:LASTEXITCODE = 0
