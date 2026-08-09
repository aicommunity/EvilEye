#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap EvilEye on Windows via Docker Desktop.
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$EnableWatchdog,
    [switch]$SkipDockerCheck
)

$ErrorActionPreference = "Stop"

function Test-Docker {
    try {
        docker info 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

Write-Host "EvilEye Windows Docker installer"
Write-Host "Root: $Root"

if (-not $SkipDockerCheck) {
    if (-not (Test-Docker)) {
        Write-Host "Docker Desktop not running or not installed."
        Write-Host "Install: winget install Docker.DockerDesktop"
        Write-Host "Then start Docker Desktop and re-run this script."
        exit 1
    }
}

& (Join-Path $PSScriptRoot "Prepare-HostDirs.ps1") -Root $Root
& (Join-Path $PSScriptRoot "Start-EvilEye.ps1") -Root $Root

if ($EnableWatchdog) {
    & (Join-Path $PSScriptRoot "Install-Watchdog.ps1") -Root $Root
}

Write-Host ""
Write-Host "Done. Open http://127.0.0.1:8181"
Write-Host "Docs: docs/WINDOWS_DOCKER_DEPLOYMENT.md"
