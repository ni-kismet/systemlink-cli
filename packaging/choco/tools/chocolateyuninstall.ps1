$ErrorActionPreference = 'Stop'

$packageName = 'slcli'
$toolsDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host 'Removing slcli files'
# Rely on Chocolatey shim removal; optionally cleanup extracted directory
# Keep minimal to avoid removing user data unexpectedly
Write-Host 'Uninstall complete.'
