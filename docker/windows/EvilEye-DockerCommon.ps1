#Requires -Version 5.1
<#
.SYNOPSIS
  Shared helpers for EvilEye Windows Docker scripts.
#>

function Get-EvilEyeComposeFile {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [string]$ComposeFile = ""
    )
    if ($ComposeFile -and $ComposeFile.Trim()) {
        return [System.IO.Path]::GetFullPath($ComposeFile.Trim())
    }
    $siteCompose = Join-Path $Root "docker-compose.yml"
    $repoCompose = Join-Path $Root "docker\docker-compose.yml"
    if (Test-Path -LiteralPath $siteCompose) {
        return [System.IO.Path]::GetFullPath($siteCompose)
    }
    if (Test-Path -LiteralPath $repoCompose) {
        return [System.IO.Path]::GetFullPath($repoCompose)
    }
    throw "No docker-compose.yml found under $Root (expected site-root or docker\docker-compose.yml)"
}

function Get-EvilEyeWatchdogTaskSuffix {
    param([Parameter(Mandatory = $true)][string]$Root)
    $full = [System.IO.Path]::GetFullPath($Root).ToLowerInvariant()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($full)
    $hash = [System.BitConverter]::ToString(
        [System.Security.Cryptography.SHA1]::Create().ComputeHash($bytes)
    ).Replace("-", "").Substring(0, 8)
    return $hash
}

function Test-EvilEyeComposeServiceRunning {
    param(
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [Parameter(Mandatory = $true)][string]$Service
    )
    $psOut = docker compose -f $ComposeFile ps --format json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $psOut) {
        $plain = docker compose -f $ComposeFile ps 2>$null | Out-String
        if (-not $plain) { return $false }
        # Match service column / container names: evileye_app, mysite-app-1, mysite_app_1
        $patterns = @(
            "(?i)\b${Service}\b",
            "(?i)[_-]${Service}[_-]?\d*",
            "(?i)evileye[_-]${Service}"
        )
        foreach ($line in ($plain -split "`n")) {
            if ($line -match "(?i)running|up\b") {
                foreach ($p in $patterns) {
                    if ($line -match $p) { return $true }
                }
            }
        }
        return $false
    }
    try {
        $rows = $psOut | ConvertFrom-Json
        if ($rows -isnot [System.Array]) { $rows = @($rows) }
        foreach ($row in $rows) {
            $svc = [string]$row.Service
            $name = [string]$row.Name
            $state = [string]$row.State
            if ($state -notmatch "(?i)running") { continue }
            if ($svc -ieq $Service) { return $true }
            if ($name -ieq "evileye_$Service") { return $true }
            if ($name -match "(?i)(^|[_-])$Service([_-]|$)") { return $true }
        }
    } catch {
        return $false
    }
    return $false
}
