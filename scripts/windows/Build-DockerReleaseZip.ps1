#Requires -Version 5.1
<#
.SYNOPSIS
  Build a Windows Docker release zip (compose + ps1 + optional image tar).
  Run on a machine with Docker after building evileye/app:latest.
#>
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$OutDir = "",
    [string]$Version = "0.0.11",
    [switch]$IncludeImage
)

$ErrorActionPreference = "Stop"
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$stage = Join-Path $OutDir "evileye-docker-windows-$Version"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Copy-Item (Join-Path $RepoRoot "docker\docker-compose.yml") (Join-Path $stage "docker-compose.yml")
Copy-Item -Recurse (Join-Path $RepoRoot "docker\windows") (Join-Path $stage "windows")
Copy-Item (Join-Path $RepoRoot "docs\WINDOWS_DOCKER_DEPLOYMENT.md") (Join-Path $stage "WINDOWS_DOCKER_DEPLOYMENT.md")
Copy-Item (Join-Path $RepoRoot "evileye\credentials_proto.json") (Join-Path $stage "credentials_proto.json")
New-Item -ItemType Directory -Force -Path (Join-Path $stage "samples_configs") | Out-Null
Copy-Item (Join-Path $RepoRoot "evileye\samples_configs\*.json") (Join-Path $stage "samples_configs")

@"
# EvilEye Docker Windows bundle $Version

1. Install Docker Desktop (WSL2).
2. Copy this folder to a writable location.
3. powershell -ExecutionPolicy Bypass -File .\windows\Prepare-HostDirs.ps1 -Root (Get-Location)
   (If credentials_proto is here, copy it to credentials.json manually or point Root at a full checkout.)
4. Prefer a full git checkout + .\docker\windows\Install-EvilEye.ps1 for first builds.
5. Optional: docker load -i evileye-app-$Version.tar

See WINDOWS_DOCKER_DEPLOYMENT.md
"@ | Set-Content (Join-Path $stage "README.txt") -Encoding UTF8

if ($IncludeImage) {
    $tar = Join-Path $stage "evileye-app-$Version.tar"
    docker save -o $tar evileye/app:latest
}

$zip = Join-Path $OutDir "evileye-docker-windows-$Version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $stage -DestinationPath $zip
Write-Host "Created $zip"
