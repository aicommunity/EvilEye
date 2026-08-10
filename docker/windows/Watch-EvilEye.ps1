#Requires -Version 5.1
<#
.SYNOPSIS
  Docker-oriented health check for EvilEye on Windows.
#>
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ComposeFile = "",
    [string]$ReadyUrl = "http://127.0.0.1:8181/ready",
    [int]$LogStaleSec = 600,
    [switch]$NoRestart
)

$ErrorActionPreference = "Continue"
if (-not $ComposeFile) { $ComposeFile = Join-Path $Root "docker\docker-compose.yml" }

$monitor = Join-Path $Root "monitor"
New-Item -ItemType Directory -Force -Path (Join-Path $monitor "incidents") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $monitor "reports") | Out-Null

$journal = Join-Path $monitor "journal.jsonl"
$watchLog = Join-Path $monitor "watchdog.log"
$ts = (Get-Date).ToString("o")
$reasons = @()

function Write-Watch([string]$msg) {
    Add-Content -Path $watchLog -Value "$ts $msg" -Encoding UTF8
}

# Container checks
$psOut = docker compose -f $ComposeFile ps --format json 2>$null
$appOk = $false
$webOk = $false
if ($LASTEXITCODE -eq 0 -and $psOut) {
    try {
        $rows = $psOut | ConvertFrom-Json
        if ($rows -isnot [System.Array]) { $rows = @($rows) }
        foreach ($row in $rows) {
            $name = [string]$row.Name
            $state = [string]$row.State
            if ($name -eq "evileye_app" -and $state -match "running") { $appOk = $true }
            if ($name -eq "evileye_web" -and $state -match "running") { $webOk = $true }
        }
    } catch {
        # older compose may not support --format json
        $plain = docker compose -f $ComposeFile ps 2>$null | Out-String
        if ($plain -match "evileye_app" -and $plain -match "running") { $appOk = $true }
        if ($plain -match "evileye_web" -and $plain -match "running") { $webOk = $true }
    }
}
if (-not $appOk) { $reasons += "container_missing_app" }
if (-not $webOk) { $reasons += "container_missing_web" }

# HTTP /ready
$uiOk = $false
try {
    $resp = Invoke-WebRequest -Uri $ReadyUrl -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) { $uiOk = $true }
} catch {
    $uiOk = $false
}
if (-not $uiOk) { $reasons += "ui_unreachable" }

# Log age
$logAge = $null
$logFile = $null
$logsDir = Join-Path $Root "logs"
if (Test-Path $logsDir) {
    $latest = Get-ChildItem -Path $logsDir -Filter "*_evileye_main.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) {
        $logFile = $latest.FullName
        $logAge = [int]((Get-Date) - $latest.LastWriteTime).TotalSeconds
        if ($logAge -gt $LogStaleSec -and $appOk) {
            $reasons += "log_stale_${logAge}s"
        }
    }
}

if ($reasons.Count -eq 0) {
    $status = "ok"
    $reason = "healthy"
} else {
    $status = "incident"
    $reason = ($reasons -join ";")
}

$entry = @{
    timestamp = $ts
    status = $status
    reason = $reason
    cli_pid = $null
    child_pid = $null
    log_file = $logFile
    log_age_sec = $logAge
} | ConvertTo-Json -Compress
Add-Content -Path $journal -Value $entry -Encoding UTF8
Write-Watch "health status=$status reason=$reason"

if ($status -eq "incident" -and -not $NoRestart) {
    $incId = Get-Date -Format "yyyyMMdd_HHmmss"
    $incDir = Join-Path $monitor "incidents\$incId"
    New-Item -ItemType Directory -Force -Path $incDir | Out-Null
    Set-Content -Path (Join-Path $incDir "summary.txt") -Value $reason -Encoding UTF8
    docker compose -f $ComposeFile ps > (Join-Path $incDir "compose_ps.txt") 2>&1
    & (Join-Path $PSScriptRoot "Restart-EvilEye.ps1") -Root $Root -ComposeFile $ComposeFile
}

Write-Host "status=$status reason=$reason"
