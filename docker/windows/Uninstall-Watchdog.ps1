#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)
. (Join-Path $PSScriptRoot "EvilEye-DockerCommon.ps1")
$suffix = Get-EvilEyeWatchdogTaskSuffix -Root $Root
schtasks /Delete /TN "EvilEyeDockerWatchdog-$suffix" /F 2>$null | Out-Null
schtasks /Delete /TN "EvilEyeDockerMorningReport-$suffix" /F 2>$null | Out-Null
schtasks /Delete /TN EvilEyeDockerWatchdog /F 2>$null | Out-Null
schtasks /Delete /TN EvilEyeDockerMorningReport /F 2>$null | Out-Null
Write-Host "Docker watchdog tasks removed for Root=$Root (suffix=$suffix)."
