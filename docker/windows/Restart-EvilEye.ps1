#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ComposeFile = ""
)
$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "EvilEye-DockerCommon.ps1")
$ComposeFile = Get-EvilEyeComposeFile -Root $Root -ComposeFile $ComposeFile
Set-Location $Root

$monitor = Join-Path $Root "monitor"
New-Item -ItemType Directory -Force -Path $monitor | Out-Null
Add-Content -Path (Join-Path $monitor "watchdog.log") -Value "$((Get-Date).ToString('o')) restart compose up -d" -Encoding UTF8

$env:EVILEYE_SITE_DIR = $Root
if (-not $env:EVILEYE_PG_DATA) {
    $env:EVILEYE_PG_DATA = Join-Path $Root "postgres_data"
}

$composeDir = Split-Path -Parent $ComposeFile
$projectDir = if ((Split-Path -Leaf $composeDir) -ieq "docker") { $Root } else { $composeDir }

docker compose --project-directory $projectDir -f $ComposeFile up -d
