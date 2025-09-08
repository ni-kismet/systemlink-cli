$ErrorActionPreference = 'Stop'

$packageName = 'slcli'
$toolsDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Version is inferred from nuspec; construct download URL
# Use the Chocolatey provided variable if available
if ($env:ChocolateyPackageVersion) { $version = $env:ChocolateyPackageVersion } else { $version = '$version$' }

$zipName = "slcli.zip"
$downloadUrl = "https://github.com/ni-kismet/systemlink-cli/releases/download/v$version/$zipName"
$tempZip = Join-Path $toolsDir $zipName

Write-Host "Downloading slcli $version from $downloadUrl"
Get-ChocolateyWebFile -PackageName $packageName -FileFullPath $tempZip -Url $downloadUrl -Checksum '$checksum$' -ChecksumType 'sha256'

Write-Host 'Extracting archive'
Get-ChocolateyUnzip -FileFullPath $tempZip -Destination $toolsDir

# Optional: remove zip after extraction
Remove-Item $tempZip -Force -ErrorAction SilentlyContinue

# Chocolatey will shim slcli.exe in the extracted folder (assumed root of zip)
Write-Host 'slcli installation complete.'
