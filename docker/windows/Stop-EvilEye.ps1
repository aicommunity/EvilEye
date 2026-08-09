#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ComposeFile = ""
)
$ErrorActionPreference = "Stop"
if (-not $ComposeFile) { $ComposeFile = Join-Path $Root "docker\docker-compose.yml" }
Set-Location $Root
docker compose -f $ComposeFile down
Write-Host "EvilEye stack stopped."
