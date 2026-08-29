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
    "postgres_data",
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

# Force compose DB defaults
$json = Get-Content $creds -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $json.database) {
    $json | Add-Member -MemberType NoteProperty -Name database -Value ([pscustomobject]@{})
}
$json.database.host_name = "db"
if (-not $json.database.user_name) { $json.database.user_name = "postgres" }
if (-not $json.database.password) { $json.database.password = "postgres" }
if (-not $json.database.database_name) { $json.database.database_name = "evil_eye_db" }
if (-not $json.database.port) { $json.database.port = 5432 }
if (-not $json.database.admin_user_name) { $json.database.admin_user_name = $json.database.user_name }
if (-not $json.database.admin_password) { $json.database.admin_password = $json.database.password }
($json | ConvertTo-Json -Depth 10) | Set-Content -Path $creds -Encoding UTF8
Write-Host "Set database.host_name to 'db' for Compose"

$sampleSrc = Join-Path $Root "evileye\samples_configs\single_video.json"
$sampleDst = Join-Path $Root "configs\single_video.json"
if ((Test-Path $sampleSrc) -and -not (Test-Path $sampleDst)) {
    Copy-Item $sampleSrc $sampleDst
    Write-Host "Copied sample configs\single_video.json"
}

Write-Host "Host dirs ready under: $Root"
Write-Host "Next: docker compose -f docker/docker-compose.yml up -d --build"
