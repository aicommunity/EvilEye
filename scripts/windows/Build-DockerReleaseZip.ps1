#Requires -Version 5.1
<#
.SYNOPSIS
  Build a Windows Docker release zip (compose + ps1 + optional image tar).
  Run on a machine with Docker after building evileye/app:latest.
#>
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$OutDir = "",
    [string]$Version = "",
    [switch]$IncludeImage
)

$ErrorActionPreference = "Stop"

if (-not $Version) {
    $pyproject = Join-Path $RepoRoot "pyproject.toml"
    $raw = Get-Content -LiteralPath $pyproject -Raw -Encoding UTF8
    if ($raw -match '(?m)^version\s*=\s*"([^"]+)"') {
        $Version = $Matches[1]
    } else {
        throw "Could not read version from pyproject.toml"
    }
}

if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "dist" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$stage = Join-Path $OutDir "evileye-docker-windows-$Version"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }

# Layout matches repo: docker/docker-compose.yml + docker/windows/*.ps1
# so Start-EvilEye.ps1 default Root (..\..) resolves to stage root.
$dockerDir = Join-Path $stage "docker"
New-Item -ItemType Directory -Force -Path $dockerDir | Out-Null
Copy-Item (Join-Path $RepoRoot "docker\docker-compose.yml") (Join-Path $dockerDir "docker-compose.yml")
Copy-Item -Recurse (Join-Path $RepoRoot "docker\windows") (Join-Path $dockerDir "windows")
Copy-Item -Recurse (Join-Path $RepoRoot "docker\host-cli") (Join-Path $dockerDir "host-cli")

Copy-Item (Join-Path $RepoRoot "docs\WINDOWS_DOCKER_DEPLOYMENT.md") (Join-Path $stage "WINDOWS_DOCKER_DEPLOYMENT.md")
New-Item -ItemType Directory -Force -Path (Join-Path $stage "evileye") | Out-Null
Copy-Item (Join-Path $RepoRoot "evileye\credentials_proto.json") (Join-Path $stage "evileye\credentials_proto.json")
New-Item -ItemType Directory -Force -Path (Join-Path $stage "evileye\samples_configs") | Out-Null
Copy-Item (Join-Path $RepoRoot "evileye\samples_configs\*.json") (Join-Path $stage "evileye\samples_configs")

@"
# EvilEye Docker Windows bundle $Version

1. Install Docker Desktop (WSL2).
2. Copy this folder to a writable location (this folder is the site/repo root).
3. Optional: docker load -i evileye-app-$Version.tar
4. powershell -ExecutionPolicy Bypass -File .\docker\windows\Install-EvilEye.ps1 -EnableWatchdog
5. Open http://127.0.0.1:8181

See WINDOWS_DOCKER_DEPLOYMENT.md
"@ | Set-Content (Join-Path $stage "README.txt") -Encoding UTF8

if ($IncludeImage) {
    $tar = Join-Path $stage "evileye-app-$Version.tar"
    docker save -o $tar "evileye/app:latest"
}

$zip = Join-Path $OutDir "evileye-docker-windows-$Version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $stage -DestinationPath $zip
Write-Host "Created $zip"
