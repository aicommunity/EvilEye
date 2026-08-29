#Requires -Version 5.1
<#
.SYNOPSIS
  Start EvilEye Docker Compose stack (app + web + db).
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ComposeFile = ""
)

$ErrorActionPreference = "Stop"
if (-not $ComposeFile) {
    $ComposeFile = Join-Path $Root "docker\docker-compose.yml"
}
Set-Location $Root

docker compose -f $ComposeFile up -d --build
Write-Host "EvilEye stack starting. UI: http://127.0.0.1:8181"
