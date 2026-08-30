[CmdletBinding()]
param([string]$Root = "C:\BAP")

$ErrorActionPreference = "Stop"
Write-Output "BAP Backend runs in a foreground Terminal for this Prototype. Press Ctrl+C in that Terminal to stop it."
