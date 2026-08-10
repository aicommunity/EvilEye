#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)
$ErrorActionPreference = "Stop"
$watch = Join-Path $PSScriptRoot "Watch-EvilEye.ps1"
$morning = Join-Path $PSScriptRoot "Morning-Report.ps1"

$watchCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$watch`" -Root `"$Root`""
$morningCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$morning`" -Root `"$Root`""

schtasks /Delete /TN EvilEyeDockerWatchdog /F 2>$null | Out-Null
schtasks /Delete /TN EvilEyeDockerMorningReport /F 2>$null | Out-Null

$c1 = schtasks /Create /TN EvilEyeDockerWatchdog /TR $watchCmd /SC MINUTE /MO 5 /RL HIGHEST /F
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create EvilEyeDockerWatchdog task. Run as Administrator. $c1"
}
schtasks /Create /TN EvilEyeDockerMorningReport /TR $morningCmd /SC DAILY /ST 09:00 /RL HIGHEST /F | Out-Null
Write-Host "Docker watchdog tasks installed (every 5 min + 09:00 report)."
