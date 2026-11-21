#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "EvilEye-DockerCommon.ps1")

$suffix = Get-EvilEyeWatchdogTaskSuffix -Root $Root
$watchTn = "EvilEyeDockerWatchdog-$suffix"
$morningTn = "EvilEyeDockerMorningReport-$suffix"

$watch = Join-Path $PSScriptRoot "Watch-EvilEye.ps1"
$morning = Join-Path $PSScriptRoot "Morning-Report.ps1"

$watchCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$watch`" -Root `"$Root`""
$morningCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$morning`" -Root `"$Root`""

schtasks /Delete /TN $watchTn /F 2>$null | Out-Null
schtasks /Delete /TN $morningTn /F 2>$null | Out-Null
# Also clean legacy global names from older installs on this Root
schtasks /Delete /TN EvilEyeDockerWatchdog /F 2>$null | Out-Null
schtasks /Delete /TN EvilEyeDockerMorningReport /F 2>$null | Out-Null

$c1 = schtasks /Create /TN $watchTn /TR $watchCmd /SC MINUTE /MO 5 /RL HIGHEST /F
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create $watchTn task. Run as Administrator. $c1"
}
schtasks /Create /TN $morningTn /TR $morningCmd /SC DAILY /ST 09:00 /RL HIGHEST /F | Out-Null
Write-Host "Docker watchdog tasks installed: $watchTn (every 5 min) + $morningTn (09:00)."
