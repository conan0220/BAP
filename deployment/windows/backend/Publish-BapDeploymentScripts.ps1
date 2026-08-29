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
$Dirty = & $GitPath -C $RepoRoot status --porcelain -- "deployment/windows/backend" "bap_backend/deployment" "bap_backend/tools/write_deployment_manifest.py"
if ($Dirty) { throw "Deployment script inputs contain uncommitted or untracked files. Commit them first." }
$Sha = (& $GitPath -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
$Upstream = (& $GitPath -C $RepoRoot rev-parse "@{u}" 2>$null).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $Upstream -ne $Sha) { throw "HEAD is not pushed to the configured upstream branch." }
if (-not (Test-Path -LiteralPath $KnownHostsFile -PathType Leaf)) { throw "Known hosts file was not found." }
& "C:\WINDOWS\System32\OpenSSH\ssh-keygen.exe" -F $HostName -f $KnownHostsFile | Out-Null
if ($LASTEXITCODE -ne 0) { throw "SSH host fingerprint is not pinned in known_hosts." }

$Allowed = @(
    "Common-BapDeployment.ps1", "Deploy-BapBackendRelease.ps1", "Rollback-BapBackendRelease.ps1",
    "Start-BapBackend.ps1", "Stop-BapBackend.ps1", "Get-BapBackendStatus.ps1", "Test-BapBackendHealth.ps1"
)
$Temp = Join-Path $env:TEMP ("bap-script-build-" + [Guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Path $Temp -Force | Out-Null
    foreach ($Name in $Allowed) {
        $Content = & $GitPath -C $RepoRoot show ($Sha + ":deployment/windows/backend/" + $Name)
        if ($LASTEXITCODE -ne 0) { throw "Unable to read a deployment script from the Git snapshot." }
        Set-Content -LiteralPath (Join-Path $Temp $Name) -Value $Content -Encoding UTF8
    }
    $Version = (& $GitPath -C $RepoRoot show ($Sha + ":bap_backend/VERSION")).Trim()
    $Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $Manifest = Join-Path $Temp "deployment-manifest.json"
    $ManifestArgs = @("-m", "bap_backend.tools.write_deployment_manifest", "--output", $Manifest, "--component", "deployment-scripts", "--commit-sha", $Sha, "--version", $Version, "--entry-point", "none", "--alembic-revision", "none")
    foreach ($Name in $Allowed) { $ManifestArgs += @("--file", $Name) }
    & $Python @ManifestArgs
    if ($LASTEXITCODE -ne 0) { throw "Unable to create deployment script manifest." }
    $Dist = Join-Path $RepoRoot "dist"
    New-Item -ItemType Directory -Path $Dist -Force | Out-Null
    $Artifact = Join-Path $Dist ("bap-deployment-scripts-" + $Sha + ".zip")
    $Checksum = $Artifact + ".sha256"
    if (Test-Path -LiteralPath $Artifact) { Remove-Item -LiteralPath $Artifact -Force }
    Compress-Archive -Path (Join-Path $Temp "*") -DestinationPath $Artifact
    $Hash = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $Checksum -Value ($Hash + "  " + [IO.Path]::GetFileName($Artifact)) -Encoding Ascii

    $ScpOptions = @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", ("UserKnownHostsFile=" + $KnownHostsFile), "-P", $Port)
    $SshOptions = @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", ("UserKnownHostsFile=" + $KnownHostsFile), "-p", $Port)
    if ($IdentityFile) { $ScpOptions += @("-i", $IdentityFile); $SshOptions += @("-i", $IdentityFile) }
    $Remote = $UserName + "@" + $HostName
    & $ScpPath @ScpOptions $Artifact $Checksum ($Remote + ":C:/BAP/incoming/")
    if ($LASTEXITCODE -ne 0) { throw "Deployment script SCP upload failed." }
    $Name = [IO.Path]::GetFileName($Artifact)
    & $SshPath @SshOptions $Remote "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "C:\BAP\bootstrap\Update-BapDeploymentScripts.ps1" -ArtifactPath ("C:\BAP\incoming\" + $Name) -ChecksumPath ("C:\BAP\incoming\" + $Name + ".sha256") -ExpectedCommitSha $Sha
    if ($LASTEXITCODE -ne 0) { throw "Remote deployment script update failed." }
} finally {
    if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp -Recurse -Force }
}

