<#
.SYNOPSIS
  Start SteamVR headless (no HMD, no Steam) from a standalone runtime folder.
.DESCRIPTION
  After vrserver is up, SteamVR's vrmonitor launches the Room Setup wizard
  (tools\steamvr_room_setup\win64\steamvr_room_setup.exe) because there is no
  HMD and no chaperone calibration. It cannot be completed without a headset,
  so by default this script waits up to -RoomSetupWaitSec seconds for that
  process and closes it: first a graceful main-window close, then (if still
  alive after a short grace period) it terminates that one process. Only a
  process whose executable path is under <Root>\tools\steamvr_room_setup is
  touched. It does not loop: if vrmonitor launches the wizard again later, the
  script does not close it again.
  Pass -KeepRoomSetup to leave the wizard running.
.PARAMETER Root
  The SteamVR folder (default: the parent folder of the folder this script lives in, i.e.
  C:\SteamVR when the repository is cloned to C:\SteamVR\SteamVR-OSC).
.PARAMETER KeepRoomSetup
  Do not close the Room Setup wizard.
.PARAMETER RoomSetupWaitSec
  How long to wait for the wizard to appear (default 30).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\SteamVR\SteamVR-OSC\start-headless.ps1
  .\start-headless.ps1 -Root D:\SteamVR -TimeoutSec 90
  .\start-headless.ps1 -KeepRoomSetup
.NOTES
  Preconditions (checked, never fixed for you; setup.ps1 sets them up):
    - openvrpaths.vrpath runtime path equals -Root (set with vrpathreg.exe setruntime)
    - <config path>\steamvr.vrsettings has steamvr.requireHmd = false
  Stop with stop-headless.ps1.
#>
param(
    [string]$Root,
    [int]$TimeoutSec = 60,
    [switch]$KeepRoomSetup,
    [int]$RoomSetupWaitSec = 30
)

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }   # default: the folder the repository is cloned into
function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }
function Norm($p) { ([IO.Path]::GetFullPath($p)).TrimEnd('\').ToLowerInvariant() }

# 1. Runtime registration
$vrpath = Join-Path $env:LOCALAPPDATA 'openvr\openvrpaths.vrpath'
if (-not (Test-Path $vrpath)) { Fail "$vrpath not found. Register the runtime: vrpathreg.exe setruntime `"$Root`"" }
try { $paths = Get-Content $vrpath -Raw | ConvertFrom-Json } catch { Fail "Cannot parse ${vrpath}: $_" }
$runtime = @($paths.runtime)[0]
if (-not $runtime -or (Norm $runtime) -ne (Norm $Root)) {
    Fail "openvrpaths.vrpath runtime is '$runtime', expected '$Root'."
}
$configDir = @($paths.config)[0]
$logDir    = @($paths.log)[0]
if (-not $configDir) { Fail "openvrpaths.vrpath has no config path." }

# 2. Headless setting
$settingsFile = Join-Path $configDir 'steamvr.vrsettings'
if (-not (Test-Path $settingsFile)) { Fail "$settingsFile not found." }
try { $settings = Get-Content $settingsFile -Raw | ConvertFrom-Json } catch { Fail "Cannot parse ${settingsFile}: $_" }
if ($settings.steamvr.requireHmd -ne $false) {
    Fail "steamvr.requireHmd is not false in $settingsFile."
}

# 3. Launch
$exe = Join-Path $Root 'bin\win64\vrstartup.exe'
if (-not (Test-Path $exe)) { Fail "$exe not found." }
$running = Get-Process vrserver -ErrorAction SilentlyContinue
if ($running) { Fail "vrserver already running (PID $($running.Id -join ',')). Run stop-headless.ps1 first." }

Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) | Out-Null

# 4. Wait for vrserver
$deadline = (Get-Date).AddSeconds($TimeoutSec)
do {
    Start-Sleep -Milliseconds 500
    $srv = Get-Process vrserver -ErrorAction SilentlyContinue
} until ($srv -or (Get-Date) -gt $deadline)
if (-not $srv) { Fail "vrserver did not start within $TimeoutSec s. Check $(Join-Path $logDir 'vrstartup.txt')." }

Write-Host "vrserver running, PID $($srv.Id)"
Write-Host "Log: $(Join-Path $logDir 'vrserver.txt')"

# 5. Close the Room Setup wizard (it needs a headset), unless -KeepRoomSetup
if ($KeepRoomSetup) {
    Write-Host "Room Setup wizard: left alone (-KeepRoomSetup)."
    exit 0
}
$wizardDir = (Norm (Join-Path $Root 'tools\steamvr_room_setup')) + '\'
function Get-RoomSetupProcess {
    Get-Process -Name steamvr_room_setup -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and (Norm $_.Path).StartsWith($wizardDir) } catch { $false }
    }
}
$wizDeadline = (Get-Date).AddSeconds($RoomSetupWaitSec)
do {
    $wiz = @(Get-RoomSetupProcess)
    if ($wiz) { break }
    Start-Sleep -Milliseconds 500
} until ((Get-Date) -gt $wizDeadline)

if (-not $wiz) {
    Write-Host "Room Setup wizard: did not appear within $RoomSetupWaitSec s, nothing to close."
    exit 0
}
foreach ($w in $wiz) {
    Write-Host "Room Setup wizard detected (PID $($w.Id)), closing it."
    # Graceful: the window may not exist yet, so retry for up to ~8 s.
    $closeDeadline = (Get-Date).AddSeconds(8)
    $sent = $false
    while (-not $w.HasExited -and (Get-Date) -lt $closeDeadline) {
        try { $w.Refresh(); if ($w.MainWindowHandle -ne 0) { $sent = $w.CloseMainWindow() } } catch {}
        if ($w.WaitForExit(1000)) { break }
    }
    if ($w.HasExited) {
        Write-Host "Room Setup wizard closed gracefully (window close sent: $sent)."
    } else {
        Stop-Process -Id $w.Id -Force
        $null = $w.WaitForExit(5000)
        Write-Host "Room Setup wizard did not exit after a window close (sent: $sent); terminated PID $($w.Id)."
    }
}
exit 0
