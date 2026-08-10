#Requires -Version 5.1
schtasks /Delete /TN EvilEyeDockerWatchdog /F 2>$null | Out-Null
schtasks /Delete /TN EvilEyeDockerMorningReport /F 2>$null | Out-Null
Write-Host "Docker watchdog tasks removed."
