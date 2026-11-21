<#
.SYNOPSIS
  Cleanly stop headless SteamVR started by start-headless.ps1.
.PARAMETER Root
  The SteamVR folder (default: the parent folder of the folder this script lives in, i.e.
  C:\SteamVR when the repository is cloned to C:\SteamVR\SteamVR-OSC).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\SteamVR\SteamVR-OSC\stop-headless.ps1
  .\stop-headless.ps1 -Force      # kill leftovers if the clean shutdown times out
.NOTES
  Uses the built-in "vrstartup.exe -shutdown". Only processes whose executable
  lives under -Root are considered (unrelated programs such as vrchat are ignored).
#>
param(
    [string]$Root,
    [int]$TimeoutSec = 30,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }   # default: the folder the repository is cloned into
$rootPrefix = ([IO.Path]::GetFullPath($Root)).TrimEnd('\') + '\'

function Get-SteamVrProcs {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) }
}

if (-not (Get-SteamVrProcs)) { Write-Host "No SteamVR processes running under $Root."; exit 0 }

$exe = Join-Path $Root 'bin\win64\vrstartup.exe'
if (-not (Test-Path $exe)) { Write-Host "ERROR: $exe not found." -ForegroundColor Red; exit 1 }

Start-Process -FilePath $exe -ArgumentList '-shutdown' -WorkingDirectory (Split-Path $exe) -Wait | Out-Null

$deadline = (Get-Date).AddSeconds($TimeoutSec)
do {
    Start-Sleep -Milliseconds 500
    $left = @(Get-SteamVrProcs)
} until ($left.Count -eq 0 -or (Get-Date) -gt $deadline)

if ($left.Count -eq 0) { Write-Host "SteamVR stopped cleanly."; exit 0 }

$names = ($left | ForEach-Object { "$($_.Name)($($_.Id))" }) -join ', '
if ($Force) {
    $left | Stop-Process -Force
    Write-Host "Clean shutdown timed out; force-killed: $names" -ForegroundColor Yellow
    exit 0
}
Write-Host "ERROR: still running after $TimeoutSec s: $names. Re-run with -Force to kill." -ForegroundColor Red
exit 1
