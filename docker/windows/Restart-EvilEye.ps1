#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ComposeFile = ""
)
$ErrorActionPreference = "Continue"
if (-not $ComposeFile) { $ComposeFile = Join-Path $Root "docker\docker-compose.yml" }
Set-Location $Root
$monitor = Join-Path $Root "monitor"
New-Item -ItemType Directory -Force -Path $monitor | Out-Null
Add-Content -Path (Join-Path $monitor "watchdog.log") -Value "$((Get-Date).ToString('o')) restart compose up -d" -Encoding UTF8
docker compose -f $ComposeFile up -d
