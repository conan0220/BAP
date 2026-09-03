[CmdletBinding()]
param(
    [string]$Root = "C:\BAP",
    [string]$ExpectedUser = "user",
    [string]$UvPath = "C:\Users\user\.local\bin\uv.exe",
    [string]$TaskName = "BAPBackend",
    [switch]$SkipHostChecks
)

$ErrorActionPreference = "Stop"
if (-not $SkipHostChecks) {
    if (-not (Test-Path -LiteralPath $UvPath -PathType Leaf)) { throw "uv was not found." }
    & $UvPath --version | Out-Null
    if (-not (Get-LocalUser -Name $ExpectedUser -ErrorAction SilentlyContinue)) { throw "Expected Windows user does not exist." }
    $SshService = Get-Service -Name "sshd" -ErrorAction SilentlyContinue
    if (-not $SshService -or $SshService.Status -ne "Running") { throw "OpenSSH Server is not running." }
    $AuthorizedKeys = "C:\ProgramData\ssh\administrators_authorized_keys"
    if (-not (Test-Path -LiteralPath $AuthorizedKeys -PathType Leaf) -or (Get-Item $AuthorizedKeys).Length -eq 0) {
        throw "administrators_authorized_keys is missing or empty."
    }
    $AllowedAclSids = @("S-1-5-18", "S-1-5-32-544")
    $ObservedAllowSids = @()
    foreach ($Rule in (Get-Acl -LiteralPath $AuthorizedKeys).Access) {
        $Sid = $Rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($Rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow) {
            $ObservedAllowSids += $Sid
            if ($AllowedAclSids -notcontains $Sid) { throw "administrators_authorized_keys ACL grants access to an unexpected account." }
        }
    }
    foreach ($RequiredSid in $AllowedAclSids) {
        if ($ObservedAllowSids -notcontains $RequiredSid) { throw "administrators_authorized_keys ACL must grant access to SYSTEM and Administrators only." }
    }
}

$Directories = @("releases", "incoming", "config", "data", "logs", "backups", "bootstrap", "run")
New-Item -ItemType Directory -Path $Root -Force | Out-Null
foreach ($Directory in $Directories) { New-Item -ItemType Directory -Path (Join-Path $Root $Directory) -Force | Out-Null }

$BootstrapSource = Join-Path $PSScriptRoot "Bootstrap-BapBackendCandidate.ps1"
if (Test-Path -LiteralPath $BootstrapSource -PathType Leaf) {
    Copy-Item -LiteralPath $BootstrapSource -Destination (Join-Path $Root "bootstrap\Bootstrap-BapBackendCandidate.ps1") -Force
}
if (-not $SkipHostChecks) {
    $PowerShell = "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"
    $RunScript = Join-Path $Root "current\deployment\runtime\Run-BapBackendScheduledTask.ps1"
    $Action = New-ScheduledTaskAction -Execute $PowerShell -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $RunScript + '" -Root "' + $Root + '"') -WorkingDirectory $Root
    $Trigger = New-ScheduledTaskTrigger -AtStartup
    $Settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)
    $Principal = New-ScheduledTaskPrincipal -UserId $ExpectedUser -LogonType S4U -RunLevel Highest
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
}
Write-Output "BAP Backend host and Scheduled Task configuration are ready. Existing persistent data was preserved."
