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
. (Join-Path $PSScriptRoot "EvilEye-DockerCommon.ps1")
$ComposeFile = Get-EvilEyeComposeFile -Root $Root -ComposeFile $ComposeFile
Set-Location $Root

$env:EVILEYE_SITE_DIR = $Root
if (-not $env:EVILEYE_PG_DATA) {
    $env:EVILEYE_PG_DATA = Join-Path $Root "postgres_data"
}

$composeDir = Split-Path -Parent $ComposeFile
$projectDir = if ((Split-Path -Leaf $composeDir) -ieq "docker") { $Root } else { $composeDir }

docker compose --project-directory $projectDir -f $ComposeFile up -d --build
Write-Host "EvilEye stack starting. UI: http://127.0.0.1:8181"
Write-Host "Compose: $ComposeFile"
