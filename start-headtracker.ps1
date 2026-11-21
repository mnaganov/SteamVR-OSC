<#
.SYNOPSIS
  One command for the head tracker: start SteamVR headless, run the OpenVR-OSC SceneRotator
  bridge in this console, stop SteamVR again when the bridge ends.
.DESCRIPTION
  1. Starts SteamVR with start-headless.ps1 from this folder (or uses it if vrserver is already
     running).
  2. Runs "python openvr-osc.py --scenerotator <extra arguments>" from the bridge directory in
     the foreground of this console, so the keys (r / space = recenter, q = quit) and the status
     line work.
  3. When the bridge exits for any reason (q, Ctrl+C, crash), stops SteamVR with
     stop-headless.ps1 from this folder - but only if this script started it. A SteamVR that was
     already running is left running.
  The exit code is the bridge's exit code (0 after q or Ctrl+C), or non-zero if the launcher itself
  failed (missing files, SteamVR did not start, SteamVR could not be stopped).
.PARAMETER Root
  The SteamVR folder (default: the parent folder of the folder this script lives in, i.e.
  C:\SteamVR when the repository is cloned to C:\SteamVR\SteamVR-OSC).
.PARAMETER BridgeDir
  Folder with openvr-osc.py (default: the bridge folder next to this script).
.PARAMETER Python
  Python executable (default python).
.PARAMETER BridgeArgs
  Everything else is passed to the bridge, e.g. --front=+y --port 9000 --rate 50 (see README).
.EXAMPLE
  .\start-headtracker.ps1
  .\start-headtracker.ps1 --front=+y --port 9001
  start-headtracker.cmd            (double-click wrapper)
#>
param(
    [string]$Root,
    [string]$BridgeDir,
    [string]$Python = 'python',
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$BridgeArgs
)

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }   # default: the folder the repository is cloned into
if (-not $BridgeDir) { $BridgeDir = Join-Path $PSScriptRoot 'bridge' }

function Say($msg) { Write-Host "[headtracker] $msg" }
function Fail($msg, $code = 2) { Write-Host "[headtracker] ERROR: $msg" -ForegroundColor Red; exit $code }

# 0. Check everything before touching SteamVR
$startScript = Join-Path $PSScriptRoot 'start-headless.ps1'
$stopScript  = Join-Path $PSScriptRoot 'stop-headless.ps1'
$bridge      = Join-Path $BridgeDir 'openvr-osc.py'
if (-not (Test-Path -LiteralPath (Join-Path $Root 'bin\win64\vrstartup.exe'))) { Fail "No SteamVR found at '$Root' (bin\win64\vrstartup.exe is missing; check -Root)." }
if (-not (Test-Path -LiteralPath $startScript)) { Fail "$startScript not found." }
if (-not (Test-Path -LiteralPath $stopScript))  { Fail "$stopScript not found." }
if (-not (Test-Path -LiteralPath $bridge))      { Fail "$bridge not found (check -BridgeDir)." }
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) { Fail "Python '$Python' not found (check -Python or PATH)." }

# 1. SteamVR
$alreadyRunning = [bool](Get-Process vrserver -ErrorAction SilentlyContinue)
$startedSteamVR = $false
if ($alreadyRunning) {
    Say "SteamVR is already running: using it, and it will be left running when the bridge exits."
} else {
    Say "Starting SteamVR ..."
    $startError = $null
    try {
        & $startScript -Root $Root
        if ($LASTEXITCODE -ne 0) { $startError = "start-headless.ps1 exited with code $LASTEXITCODE" }
    } catch {
        $startError = "start-headless.ps1 failed: $_"
    }
    if ($startError) {
        Write-Host "[headtracker] ERROR: $startError" -ForegroundColor Red
        # clean up a half-started SteamVR (we started it), then give up without running the bridge
        if (Get-Process vrserver, vrstartup, vrmonitor -ErrorAction SilentlyContinue) {
            Say "Stopping the partly started SteamVR ..."
            & $stopScript -Root $Root -Force
        }
        exit 3
    }
    $startedSteamVR = $true
}

# 2. Bridge in the foreground of this console, 3. cleanup however it ends
$bridgeExit = 1
$ended = 'was interrupted (Ctrl+C)'
try {
    Say "Running the bridge: $Python openvr-osc.py --scenerotator $($BridgeArgs -join ' ')"
    Say "Keys: r = recenter, q = quit (Ctrl+C also works; start-headtracker.cmd then asks 'Terminate batch job', answer Y)."
    Push-Location -LiteralPath $BridgeDir
    try {
        & $Python 'openvr-osc.py' '--scenerotator' @BridgeArgs
        $bridgeExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $ended = if ($bridgeExit -eq 0) { 'ended normally (q, or --duration reached)' } else { "ended with an error (exit code $bridgeExit)" }
} finally {
    Write-Host ""
    Say "The bridge $ended."
    $stopFailed = $false
    if ($startedSteamVR) {
        Say "Stopping SteamVR (this launcher started it) ..."
        & $stopScript -Root $Root
        if ($LASTEXITCODE -ne 0) {
            $stopFailed = $true
            Write-Host "[headtracker] ERROR: stop-headless.ps1 exited with code $LASTEXITCODE" -ForegroundColor Red
        }
    } else {
        Say "SteamVR was already running before the launcher started, so it is left running."
    }
    # ending here (also after Ctrl+C) gives the launcher a defined exit code
    if ($stopFailed) { exit 4 }
    if ($ended -like 'was interrupted*') { exit 0 }
    exit $bridgeExit
}
