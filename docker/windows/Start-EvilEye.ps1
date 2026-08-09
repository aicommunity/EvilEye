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

$env:EVILEYE_HOST_DATA = if ($env:EVILEYE_HOST_DATA) { $env:EVILEYE_HOST_DATA } else { Join-Path $Root "EvilEyeData" }
$env:EVILEYE_HOST_VIDEOS = if ($env:EVILEYE_HOST_VIDEOS) { $env:EVILEYE_HOST_VIDEOS } else { Join-Path $Root "videos" }
$env:EVILEYE_HOST_MODELS = if ($env:EVILEYE_HOST_MODELS) { $env:EVILEYE_HOST_MODELS } else { Join-Path $Root "models" }
$env:EVILEYE_HOST_CONFIGS = if ($env:EVILEYE_HOST_CONFIGS) { $env:EVILEYE_HOST_CONFIGS } else { Join-Path $Root "configs" }
$env:EVILEYE_HOST_LOGS = if ($env:EVILEYE_HOST_LOGS) { $env:EVILEYE_HOST_LOGS } else { Join-Path $Root "logs" }
$env:EVILEYE_HOST_CREDENTIALS = if ($env:EVILEYE_HOST_CREDENTIALS) { $env:EVILEYE_HOST_CREDENTIALS } else { Join-Path $Root "credentials.json" }

docker compose -f $ComposeFile up -d --build
Write-Host "EvilEye stack starting. UI: http://127.0.0.1:8181/ready"
