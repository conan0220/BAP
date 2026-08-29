[CmdletBinding()]
param(
    [string]$Root = "C:\BAP",
    [string]$ExpectedUser = "user",
    [string]$PythonPath = "C:\Python312\python.exe",
    [string]$UvPath = "C:\Users\user\.local\bin\uv.exe",
    [switch]$SkipHostChecks
)

$ErrorActionPreference = "Stop"
if (-not $SkipHostChecks) {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python 3.12 was not found." }
    $PythonVersion = (& $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($PythonVersion -ne "3.12") { throw "Python 3.12 is required." }
    if (-not (Test-Path -LiteralPath $UvPath -PathType Leaf)) { throw "uv was not found." }
    & $UvPath --version | Out-Null
    if (-not (Get-LocalUser -Name $ExpectedUser -ErrorAction SilentlyContinue)) { throw "Expected Windows user does not exist." }
    $SshService = Get-Service -Name "sshd" -ErrorAction SilentlyContinue
    if (-not $SshService -or $SshService.Status -ne "Running") { throw "OpenSSH Server is not running." }
    $AuthorizedKeys = "C:\ProgramData\ssh\administrators_authorized_keys"
    if (-not (Test-Path -LiteralPath $AuthorizedKeys -PathType Leaf) -or (Get-Item $AuthorizedKeys).Length -eq 0) {
        throw "administrators_authorized_keys is missing or empty."
    }
    $PublicKeyLines = @(Get-Content -LiteralPath $AuthorizedKeys | Where-Object {
        $Line = $_.Trim()
        $Line -and -not $Line.StartsWith("#")
    })
    $SupportedPublicKey = @($PublicKeyLines | Where-Object {
        $_ -match "^(ssh-(rsa|ed25519)|ecdsa-sha2-nistp(256|384|521))\s+[A-Za-z0-9+/=]+(?:\s+.*)?$"
    })
    if ($SupportedPublicKey.Count -eq 0) {
        throw "administrators_authorized_keys does not contain a supported OpenSSH public key."
    }

    # Windows OpenSSH ignores this file when unrelated accounts can read or
    # change it. Validate the existing ACL, but do not rewrite host security
    # settings from this bootstrap script.
    $AllowedAclSids = @("S-1-5-18", "S-1-5-32-544") # SYSTEM, Administrators
    $AuthorizedKeysAcl = Get-Acl -LiteralPath $AuthorizedKeys
    $ObservedAllowSids = @()
    foreach ($Rule in $AuthorizedKeysAcl.Access) {
        try {
            $Sid = $Rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        }
        catch {
            throw "Unable to validate administrators_authorized_keys ACL identity."
        }
        if ($Rule.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow) {
            $ObservedAllowSids += $Sid
            if ($AllowedAclSids -notcontains $Sid) {
                throw "administrators_authorized_keys ACL grants access to an unexpected account."
            }
        }
    }
    foreach ($RequiredSid in $AllowedAclSids) {
        if ($ObservedAllowSids -notcontains $RequiredSid) {
            throw "administrators_authorized_keys ACL must grant access to SYSTEM and Administrators only."
        }
    }
}

$Directories = @(
    "releases", "incoming", "config", "data", "logs", "backups", "scripts",
    "scripts-releases", "bootstrap", "run"
)
New-Item -ItemType Directory -Path $Root -Force | Out-Null
foreach ($Directory in $Directories) {
    New-Item -ItemType Directory -Path (Join-Path $Root $Directory) -Force | Out-Null
}
Write-Output "BAP Backend host directories are ready. Existing persistent data was preserved."
