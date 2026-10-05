#Requires -Version 5.1
# EvilEye docker host-cli
# Shared launcher: run a command inside the EvilEye container.
$ErrorActionPreference = 'Stop'

$LauncherRoot = $PSScriptRoot
$CommandArgs = @($args)

$Image = if ($env:EVILEYE_DOCKER_IMAGE) { $env:EVILEYE_DOCKER_IMAGE } else { 'evileye/app:latest' }
$GpuMode = if ($env:EVILEYE_DOCKER_GPU_MODE) { $env:EVILEYE_DOCKER_GPU_MODE } else { 'gpus' }

function Test-EvilEyeCpuImage {
    param([string]$ImageName)
    $tag = ($ImageName -split '/')[-1]
    if ($tag -match ':') { $tag = ($tag -split ':', 2)[1] }
    return ($tag -eq 'cpu' -or $tag -like '*-cpu')
}

if (-not $env:EVILEYE_DOCKER_GPU_MODE -and (Test-EvilEyeCpuImage -ImageName $Image) -and $GpuMode -eq 'gpus') {
    $GpuMode = 'none'
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine('error: docker not found in PATH')
    exit 127
}

docker image inspect $Image 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("error: image '$Image' not found.")
    [Console]::Error.WriteLine('Build/pull it first:')
    [Console]::Error.WriteLine("  docker pull $Image")
    exit 1
}

if ($CommandArgs.Count -lt 1) {
    [Console]::Error.WriteLine("usage: $(Split-Path -Leaf $MyInvocation.MyCommand.Path) <command> [args...]")
    exit 2
}

function Resolve-SiteDir {
    param([string]$BinDir)
    if ($env:EVILEYE_DOCKER_SITE_DIR -and $env:EVILEYE_DOCKER_SITE_DIR.Trim()) {
        return [System.IO.Path]::GetFullPath($env:EVILEYE_DOCKER_SITE_DIR.Trim())
    }
    if ((Split-Path -Leaf $BinDir) -ieq 'bin') {
        $parent = Split-Path -Parent $BinDir
        $markers = @(
            (Join-Path $parent 'credentials.json'),
            (Join-Path $parent 'docker-compose.yml'),
            (Join-Path $parent 'configs')
        )
        foreach ($m in $markers) {
            if (Test-Path -LiteralPath $m) {
                return [System.IO.Path]::GetFullPath($parent)
            }
        }
    }
    return $null
}

$dockerArgs = @(
    '--rm',
    '--ipc=host',
    '-e', 'PYTHONUNBUFFERED=1'
)

if ($GpuMode -ne 'none') {
    $nvDevices = if ($env:NVIDIA_VISIBLE_DEVICES) { $env:NVIDIA_VISIBLE_DEVICES } else { 'all' }
    $nvCaps = if ($env:NVIDIA_DRIVER_CAPABILITIES) { $env:NVIDIA_DRIVER_CAPABILITIES } else { 'compute,utility,video' }
    $dockerArgs += @('-e', "NVIDIA_VISIBLE_DEVICES=$nvDevices")
    $dockerArgs += @('-e', "NVIDIA_DRIVER_CAPABILITIES=$nvCaps")
}

$site = Resolve-SiteDir -BinDir $LauncherRoot
if ($site) {
    $dataDir = if ($env:EVILEYE_DATA_DIR) { $env:EVILEYE_DATA_DIR } else { '/site/EvilEyeData' }
    $dockerArgs += @('-e', 'EVILEYE_SITE_DIR=/site')
    $dockerArgs += @('-e', "EVILEYE_DATA_DIR=$dataDir")
    $dockerArgs += @('-v', "${site}:/site")
    $dockerArgs += @('-w', '/site')
} else {
    $pwdPath = (Get-Location).Path
    $dockerArgs += @('-v', "${pwdPath}:${pwdPath}")
    $dockerArgs += @('-w', $pwdPath)
    if ($env:EVILEYE_DATA_DIR) {
        $dockerArgs += @('-e', "EVILEYE_DATA_DIR=$($env:EVILEYE_DATA_DIR)")
    } elseif (Test-Path -LiteralPath (Join-Path $pwdPath 'EvilEyeData')) {
        $dockerArgs += @('-e', "EVILEYE_DATA_DIR=$(Join-Path $pwdPath 'EvilEyeData')")
    }
}

# Always -i; add -t only for interactive console hosts
$dockerArgs += '-i'
$useTty = $false
try {
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        if ($Host.Name -eq 'ConsoleHost') {
            $useTty = $true
        }
    }
} catch {
    $useTty = $false
}
if ($useTty) {
    $dockerArgs += '-t'
}

switch ($GpuMode) {
    'gpus' { $dockerArgs += @('--gpus', 'all') }
    'cdi' { $dockerArgs += @('--device', 'nvidia.com/gpu=all') }
    'none' { }
    default {
        [Console]::Error.WriteLine("error: unknown EVILEYE_DOCKER_GPU_MODE='$GpuMode' (gpus|cdi|none)")
        exit 2
    }
}

if ($env:EVILEYE_DOCKER_EXTRA_ARGS -and $env:EVILEYE_DOCKER_EXTRA_ARGS.Trim()) {
    $extra = $env:EVILEYE_DOCKER_EXTRA_ARGS.Trim() -split '\s+'
    if ($extra.Count -gt 0) {
        $dockerArgs += $extra
    }
}

& docker run @dockerArgs $Image @CommandArgs
exit $LASTEXITCODE
