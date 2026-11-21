#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare host directories and credentials.json for EvilEye Docker Compose on Windows.
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$PostgresPassword = ""
)

$ErrorActionPreference = "Stop"
Set-Location $Root

if (-not $PostgresPassword) {
    if ($env:POSTGRES_PASSWORD) { $PostgresPassword = $env:POSTGRES_PASSWORD }
    else { $PostgresPassword = "postgres" }
}

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

# Force compose DB defaults (empty string is treated as missing)
$json = Get-Content $creds -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $json.database) {
    $json | Add-Member -MemberType NoteProperty -Name database -Value ([pscustomobject]@{})
}
$json.database.host_name = "db"
if (-not $json.database.user_name) { $json.database.user_name = "postgres" }
if (-not $json.database.password) { $json.database.password = $PostgresPassword }
if (-not $json.database.database_name) { $json.database.database_name = "evil_eye_db" }
if (-not $json.database.port) { $json.database.port = 5432 }
if (-not $json.database.admin_user_name) { $json.database.admin_user_name = $json.database.user_name }
if (-not $json.database.admin_password) { $json.database.admin_password = $json.database.password }
($json | ConvertTo-Json -Depth 10) | Set-Content -Path $creds -Encoding UTF8
Write-Host "Set database.host_name to 'db' for Compose"

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    @(
        "EVILEYE_IMAGE=evileye/app:latest"
        "EVILEYE_HOST_PORT=8181"
        "EVILEYE_PG_PORT=5432"
        "POSTGRES_PASSWORD=$PostgresPassword"
    ) | Set-Content -Path $envFile -Encoding UTF8
    Write-Host "Created .env with POSTGRES_PASSWORD"
} else {
    $envText = Get-Content $envFile -Raw -Encoding UTF8
    if ($envText -notmatch '(?m)^POSTGRES_PASSWORD=') {
        Add-Content -Path $envFile -Value "POSTGRES_PASSWORD=$PostgresPassword" -Encoding UTF8
        Write-Host "Appended POSTGRES_PASSWORD to .env"
    }
}

$sampleSrc = Join-Path $Root "evileye\samples_configs\single_video.json"
$sampleDst = Join-Path $Root "configs\single_video.json"
if ((Test-Path $sampleSrc) -and -not (Test-Path $sampleDst)) {
    Copy-Item $sampleSrc $sampleDst
    Write-Host "Copied sample configs\single_video.json"
}

Write-Host "Host dirs ready under: $Root"
Write-Host "Next: .\docker\windows\Start-EvilEye.ps1"
Write-Host "  # or: docker compose --project-directory . -f docker/docker-compose.yml up -d --build"
