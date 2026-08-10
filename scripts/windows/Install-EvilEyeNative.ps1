#Requires -Version 5.1
<#
.SYNOPSIS
  Create venv, pip install evileye[win], deploy site (native Windows, no Docker).
#>
param(
    [string]$SiteDir = (Join-Path $env:USERPROFILE "EvilEye"),
    [string]$Python = "py",
    [string]$PythonVersion = "-3.11",
    [switch]$EnableService,
    [switch]$EnableWatchdog,
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $SiteDir | Out-Null
Set-Location $SiteDir

$venv = Join-Path $SiteDir ".venv"
if (-not (Test-Path $venv)) {
    & $Python $PythonVersion -m venv $venv
}
$pip = Join-Path $venv "Scripts\pip.exe"
$evileye = Join-Path $venv "Scripts\evileye.exe"

if ($RepoRoot -and (Test-Path (Join-Path $RepoRoot "pyproject.toml"))) {
    & $pip install -U pip
    & $pip install -e ((Join-Path $RepoRoot ".") + "[win]")
} else {
    & $pip install -U pip
    & $pip install "evileye[win]"
}

$env:EVILEYE_SITE_DIR = $SiteDir
& $evileye setup-web
& $evileye deploy

if ($EnableService) {
    & $evileye service-install
}
if ($EnableWatchdog) {
    & $evileye watchdog-install --config configs/system.json
}

Write-Host "Native site ready at $SiteDir"
Write-Host "Activate: $venv\Scripts\Activate.ps1"
Write-Host "UI: start with 'evileye server' or service-install; http://127.0.0.1:8181"
