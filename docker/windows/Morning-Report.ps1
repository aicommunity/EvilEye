#Requires -Version 5.1
param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)
$ErrorActionPreference = "Stop"
$monitor = Join-Path $Root "monitor"
$reports = Join-Path $monitor "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$day = Get-Date -Format "yyyy-MM-dd"
$journal = Join-Path $monitor "journal.jsonl"
$out = Join-Path $reports "$day.md"
$lines = @("# EvilEye Docker watchdog report $day", "")
$incidents = 0
if (Test-Path $journal) {
    Get-Content $journal -Encoding UTF8 | ForEach-Object {
        if ($_ -match $day) {
            $lines += "- $_"
            if ($_ -match '"status"\s*:\s*"incident"') { $incidents++ }
        }
    }
}
$lines = @("# EvilEye Docker watchdog report $day", "", "Incidents today: **$incidents**", "") + ($lines | Select-Object -Skip 2)
Set-Content -Path $out -Value ($lines -join "`n") -Encoding UTF8
Write-Host "Report: $out"
