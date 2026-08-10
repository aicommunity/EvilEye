#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare host directories and credentials.json for EvilEye Docker Compose on Windows.
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $Root

$dirs = @(
    "EvilEyeData\images",
    "videos",
    "models",
    "configs",
    "logs",
    "monitor\incidents",
    "monitor\reports"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null
}

$creds = Join-Path $Root "credentials.json"
$proto = Join-Path $Root "evileye\credentials_proto.json"
if (-not (Test-Path $creds)) {
    if (-not (Test-Path $proto)) {
        throw "Missing $proto"
    }
    Copy-Item $proto $creds
    Write-Host "Created credentials.json from credentials_proto.json"
}

# Force compose DB hostname
$raw = Get-Content $creds -Raw -Encoding UTF8
if ($raw -match '"host_name"\s*:\s*"localhost"') {
    $raw = $raw -replace '"host_name"\s*:\s*"localhost"', '"host_name": "db"'
    Set-Content -Path $creds -Value $raw -Encoding UTF8
    Write-Host "Set database.host_name to `"db`" for Compose"
}

$sampleSrc = Join-Path $Root "evileye\samples_configs\single_video.json"
$sampleDst = Join-Path $Root "configs\single_video.json"
if ((Test-Path $sampleSrc) -and -not (Test-Path $sampleDst)) {
    Copy-Item $sampleSrc $sampleDst
    Write-Host "Copied sample configs\single_video.json"
}

Write-Host "Host dirs ready under: $Root"
Write-Host "Next: docker compose -f docker/docker-compose.yml up --build -d"
