[CmdletBinding()]
param(
    [string]$HostName = "140.114.75.84",
    [string]$UserName = "user",
    [int]$Port = 22,
    [string]$IdentityFile,
    [string]$KnownHostsFile = (Join-Path $HOME ".ssh\known_hosts"),
    [string]$GitPath = "C:\Program Files\Git\cmd\git.exe",
    [string]$SshPath = "C:\WINDOWS\System32\OpenSSH\ssh.exe",
    [string]$ScpPath = "C:\WINDOWS\System32\OpenSSH\scp.exe"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Inputs = @("bap_backend", "bap_common", "migrations", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version", "deployment/windows/backend")
$DirtyInputs = & $GitPath -C $RepoRoot status --porcelain -- @Inputs
if ($DirtyInputs) { throw "Backend artifact inputs contain uncommitted or untracked files. Commit them first." }
$AllDirty = & $GitPath -C $RepoRoot status --porcelain
if ($AllDirty) { Write-Warning "Unrelated working-tree files are dirty; they will not enter the Backend artifact." }
$Sha = (& $GitPath -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
$Upstream = (& $GitPath -C $RepoRoot rev-parse "@{u}" 2>$null).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $Upstream -ne $Sha) { throw "HEAD is not pushed to the configured upstream branch." }
if (-not (Test-Path -LiteralPath $KnownHostsFile -PathType Leaf)) { throw "Known hosts file was not found." }
& "C:\WINDOWS\System32\OpenSSH\ssh-keygen.exe" -F $HostName -f $KnownHostsFile | Out-Null
if ($LASTEXITCODE -ne 0) { throw "SSH host fingerprint is not pinned in known_hosts." }

$BuildOutput = & (Join-Path $PSScriptRoot "Build-BapBackendArtifact.ps1") -CommitSha $Sha
if ($LASTEXITCODE -ne 0) { throw "Backend artifact build failed." }
$Artifact = $BuildOutput | Where-Object { $_ -like "*.zip" } | Select-Object -Last 1
$Checksum = $Artifact + ".sha256"
$Options = @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", ("UserKnownHostsFile=" + $KnownHostsFile), "-P", $Port)
$SshOptions = @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", ("UserKnownHostsFile=" + $KnownHostsFile), "-p", $Port)
if ($IdentityFile) { $Options += @("-i", $IdentityFile); $SshOptions += @("-i", $IdentityFile) }
$Remote = $UserName + "@" + $HostName
& $ScpPath @Options $Artifact $Checksum ($Remote + ":C:/BAP/incoming/")
if ($LASTEXITCODE -ne 0) { throw "SCP upload failed." }
$ArtifactName = [IO.Path]::GetFileName($Artifact)
& $SshPath @SshOptions $Remote "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "C:\BAP\scripts\Deploy-BapBackendRelease.ps1" -ArtifactPath ("C:\BAP\incoming\" + $ArtifactName) -ChecksumPath ("C:\BAP\incoming\" + $ArtifactName + ".sha256") -ExpectedCommitSha $Sha
if ($LASTEXITCODE -ne 0) { throw "Remote Backend deployment failed." }

