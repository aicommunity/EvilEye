#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ComposeFile = ""
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "EvilEye-DockerCommon.ps1")
$ComposeFile = Get-EvilEyeComposeFile -Root $Root -ComposeFile $ComposeFile
Set-Location $Root

$composeDir = Split-Path -Parent $ComposeFile
$projectDir = if ((Split-Path -Leaf $composeDir) -ieq "docker") { $Root } else { $composeDir }

docker compose --project-directory $projectDir -f $ComposeFile down
Write-Host "EvilEye stack stopped."
