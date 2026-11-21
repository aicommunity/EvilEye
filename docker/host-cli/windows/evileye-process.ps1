#Requires -Version 5.1
# EvilEye docker host-cli
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
if (-not $env:EVILEYE_DOCKER_IMAGE) { $env:EVILEYE_DOCKER_IMAGE = 'evileye/app:latest' }
$Launcher = Join-Path $Root 'EvilEye-DockerRun.ps1'
& $Launcher 'evileye-process' @args
exit $LASTEXITCODE
