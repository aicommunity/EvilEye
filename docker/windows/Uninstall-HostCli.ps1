#Requires -Version 5.1
<#
.SYNOPSIS
  Remove EvilEye Docker host-cli wrappers previously installed by Install-HostCli.ps1.
#>
param(
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA 'EvilEye\bin')
)

$ErrorActionPreference = 'Continue'
$Marker = '# EvilEye docker host-cli'
$CmdMarker = 'rem EvilEye docker host-cli'

$Names = @(
    'EvilEye-DockerRun.ps1',
    'evileye.ps1', 'evileye.cmd',
    'evileye-launch.ps1', 'evileye-launch.cmd',
    'evileye-process.ps1', 'evileye-process.cmd',
    'evileye-configure.ps1', 'evileye-configure.cmd',
    'evileye-srv.ps1', 'evileye-srv.cmd'
)

$removed = 0
foreach ($name in $Names) {
    $target = Join-Path $Prefix $name
    if (-not (Test-Path -LiteralPath $target)) { continue }
    $content = Get-Content -LiteralPath $target -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) { continue }
    $ours = ($content -match [regex]::Escape($Marker)) -or ($content -match [regex]::Escape($CmdMarker))
    if ($ours) {
        Remove-Item -LiteralPath $target -Force
        Write-Host "removed $target"
        $removed++
    } else {
        Write-Host "skip $target (not an EvilEye docker host-cli script)"
    }
}

# Remove Prefix from User PATH only if directory is empty (or missing)
$empty = $true
if (Test-Path -LiteralPath $Prefix) {
    $left = Get-ChildItem -LiteralPath $Prefix -Force -ErrorAction SilentlyContinue
    if ($left -and $left.Count -gt 0) { $empty = $false }
    else {
        Remove-Item -LiteralPath $Prefix -Force -ErrorAction SilentlyContinue
    }
}

if ($empty) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($userPath) {
        $normalizedPrefix = $null
        try { $normalizedPrefix = [System.IO.Path]::GetFullPath($Prefix) } catch { }
        $parts = @()
        foreach ($p in ($userPath -split ';')) {
            if (-not $p -or -not $p.Trim()) { continue }
            try {
                if ($normalizedPrefix -and ([System.IO.Path]::GetFullPath($p) -ieq $normalizedPrefix)) { continue }
            } catch { }
            $parts += $p
        }
        [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
        Write-Host "Removed empty Prefix from User PATH: $Prefix"
    }
}

Write-Host "Uninstalled $removed host-cli file(s) from $Prefix"
