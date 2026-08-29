#Requires -Version 5.1
<#
.SYNOPSIS
  Install EvilEye Docker host-cli wrappers for PowerShell/cmd.
#>
param(
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA 'EvilEye\bin'),
    [string]$SiteDir = '',
    [string]$Image = '',
    [string]$SourceDir = '',
    [switch]$NoPathUpdate
)

$ErrorActionPreference = 'Stop'
$Marker = '# EvilEye docker host-cli'
$CmdMarker = 'rem EvilEye docker host-cli'

$Commands = @(
    'evileye',
    'evileye-launch',
    'evileye-process',
    'evileye-configure',
    'evileye-srv'
)

if (-not $Image) {
    if ($env:EVILEYE_DOCKER_IMAGE) { $Image = $env:EVILEYE_DOCKER_IMAGE }
    elseif ($env:EVILEYE_IMAGE) { $Image = $env:EVILEYE_IMAGE }
    else { $Image = 'evileye/app:latest' }
}

if (-not $SourceDir) {
    $SourceDir = Join-Path $PSScriptRoot '..\host-cli\windows'
}
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)
if (-not (Test-Path -LiteralPath $SourceDir)) {
    throw "Missing source directory: $SourceDir"
}

$launcherSrc = Join-Path $SourceDir 'EvilEye-DockerRun.ps1'
if (-not (Test-Path -LiteralPath $launcherSrc)) {
    throw "Missing launcher: $launcherSrc"
}

New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
Copy-Item -LiteralPath $launcherSrc -Destination (Join-Path $Prefix 'EvilEye-DockerRun.ps1') -Force

$cpuImage = $Image.EndsWith(':cpu')
$sitePin = ''
if ($SiteDir -and $SiteDir.Trim()) {
    $sitePin = [System.IO.Path]::GetFullPath($SiteDir.Trim())
    if (-not (Test-Path -LiteralPath $sitePin)) {
        throw "SiteDir does not exist: $sitePin"
    }
}

function Write-WrapperPs1 {
    param(
        [string]$Name,
        [string]$Cmd,
        [string]$DestDir,
        [string]$ImageName,
        [string]$PinnedSite,
        [bool]$ForceCpuGpuNone
    )
    $lines = @(
        '#Requires -Version 5.1',
        $Marker,
        '$ErrorActionPreference = ''Stop''',
        '$Root = $PSScriptRoot',
        "if (-not `$env:EVILEYE_DOCKER_IMAGE) { `$env:EVILEYE_DOCKER_IMAGE = '$ImageName' }"
    )
    if ($ForceCpuGpuNone) {
        $lines += "if (-not `$env:EVILEYE_DOCKER_GPU_MODE) { `$env:EVILEYE_DOCKER_GPU_MODE = 'none' }"
    }
    if ($PinnedSite) {
        $escaped = $PinnedSite.Replace("'", "''")
        $lines += "`$env:EVILEYE_DOCKER_SITE_DIR = '$escaped'"
    }
    $lines += @(
        '$Launcher = Join-Path $Root ''EvilEye-DockerRun.ps1''',
        "& `$Launcher '$Cmd' @args",
        'exit $LASTEXITCODE',
        ''
    )
    $path = Join-Path $DestDir "$Name.ps1"
    Set-Content -LiteralPath $path -Value ($lines -join "`r`n") -Encoding UTF8
}

function Write-WrapperCmd {
    param([string]$Name, [string]$DestDir)
    $content = @"
@echo off
$CmdMarker
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%$Name.ps1" %*
exit /b %ERRORLEVEL%
"@
    Set-Content -LiteralPath (Join-Path $DestDir "$Name.cmd") -Value $content -Encoding ASCII
}

foreach ($name in $Commands) {
    Write-WrapperPs1 -Name $name -Cmd $name -DestDir $Prefix -ImageName $Image -PinnedSite $sitePin -ForceCpuGpuNone:$cpuImage
    Write-WrapperCmd -Name $name -DestDir $Prefix
}

# Warn on conflicting evileye in PATH
$existing = Get-Command evileye -ErrorAction SilentlyContinue
if ($existing) {
    $existingPath = $existing.Source
    $isOurs = $false
    if (Test-Path -LiteralPath $existingPath) {
        $head = Get-Content -LiteralPath $existingPath -TotalCount 5 -ErrorAction SilentlyContinue
        if ($head -match [regex]::Escape($Marker) -or $head -match [regex]::Escape($CmdMarker)) {
            $isOurs = $true
        }
    }
    if (-not $isOurs) {
        Write-Host "warning: 'evileye' already exists at $existingPath (likely pip install)." -ForegroundColor Yellow
        Write-Host "         Docker host-cli and pip entry points should not share PATH." -ForegroundColor Yellow
    }
}

if (-not $NoPathUpdate) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $userPath) { $userPath = '' }
    $parts = $userPath -split ';' | Where-Object { $_ -and $_.Trim() }
    $normalizedPrefix = [System.IO.Path]::GetFullPath($Prefix)
    $found = $false
    foreach ($p in $parts) {
        try {
            if ([System.IO.Path]::GetFullPath($p) -ieq $normalizedPrefix) { $found = $true; break }
        } catch { }
    }
    if (-not $found) {
        $newPath = if ($userPath.TrimEnd(';')) { "$userPath;$Prefix" } else { $Prefix }
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
        Write-Host "Added to User PATH: $Prefix"
        Write-Host "Open a new terminal (or refresh PATH) for global 'evileye' discovery."
    }
    if ($env:Path -notlike "*$Prefix*") {
        $env:Path = "$Prefix;$env:Path"
    }
}

Write-Host "Installed EvilEye docker host-cli into $Prefix"
Write-Host "Image: $Image"
if ($sitePin) { Write-Host "SiteDir pin: $sitePin" }
Write-Host "Try: evileye --help"
