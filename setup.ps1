<#
.SYNOPSIS
  Idempotent setup for SteamVR-OSC: checks the prerequisites, registers the SteamVR runtime,
  merges the headless settings and installs the Python packages of the bridge.
.DESCRIPTION
  Safe to run again at any time: every step first looks at the current state and only changes
  what differs. Use -DryRun to see what would be done without writing anything.

  Steps
    0. Prerequisites (read-only): SteamVR files under -Root (vrpathreg, vrstartup, vrserver,
       drivers\lighthouse, drivers\null), Python on PATH (3.15.x is the tested version), git on
       PATH, and the legacy DirectX DLL d3dx10_43.dll (System32 and SysWOW64). Without that DLL
       SteamVR's vrmonitor.exe shows an error popup ("d3dx10_43.dll was not found") at every start.
       Install the "DirectX End-User Runtimes (June 2010)" to get it. Missing items are reported
       together and setup stops (exit code 1) before it changes anything.
    1. Refuses to continue while any SteamVR process runs from -Root (exit code 2): SteamVR rewrites
       steamvr.vrsettings when it exits and would overwrite the change. Stop it with
       stop-headless.ps1.
    2. OpenVR registration with vrpathreg: runtime = <Root>, config = <Root>\config,
       log = <Root>\logs (%LOCALAPPDATA%\openvr\openvrpaths.vrpath). Creates the folders. Skipped
       when already set; shows the state before and after. (exit code 3 on failure)
    3. Merges the headless keys of config\steamvr.vrsettings (this repository) into
       <Root>\config\steamvr.vrsettings: steamvr.requireHmd=false, steamvr.forcedDriver="null",
       steamvr.activateMultipleDrivers=true, driver_null.enable=true. Creates the file if it is
       missing, keeps all other keys, backs the old file up as steamvr.vrsettings.bak-<time>
       before changing it, and writes valid JSON. (exit code 4 on failure)
    4. Installs the packages pinned in bridge\requirements.txt with pip (skipped when the pinned
       versions are already installed). (exit code 5 on failure)
    5. With -RunTests: runs tests\test_scenerotator.py. (exit code 6 on failure)
.PARAMETER Root
  The SteamVR folder (default: the parent folder of this repository, i.e. C:\SteamVR when the
  repository is cloned to C:\SteamVR\SteamVR-OSC).
.PARAMETER DryRun
  Report what would be done; write nothing (no folders, no vrpathreg calls, no files, no pip).
.PARAMETER RunTests
  Run the self-test at the end (needs no SteamVR and sends no network traffic).
.PARAMETER Only
  Run only some of the changing steps: register, settings, pip (default: all three), for
  example -Only settings or -Only register,pip.
.PARAMETER ConfigDir
  Test hook: merge the settings into <ConfigDir>\steamvr.vrsettings instead of <Root>\config.
  Does not change the registered config path.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\setup.ps1 -DryRun
  powershell -ExecutionPolicy Bypass -File .\setup.ps1 -RunTests
.NOTES
  Exit codes: 0 ok, 1 prerequisites missing, 2 SteamVR is running, 3 registration failed,
  4 settings failed, 5 pip failed, 6 self-test failed.
#>
[CmdletBinding()]
param(
    [string]$Root,
    [switch]$DryRun,
    [switch]$RunTests,
    [string[]]$Only = @('register', 'settings', 'pip'),
    [string]$ConfigDir
)

$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
# -Only accepts 'register,settings' as well (powershell -File passes a comma list as one string)
$Only = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
$badOnly = @($Only | Where-Object { @('register', 'settings', 'pip') -notcontains $_ })
if ($badOnly.Count -gt 0) { Write-Host "ERROR: -Only accepts register, settings, pip (got: $($badOnly -join ', '))." -ForegroundColor Red; exit 1 }
if (-not $Root) { $Root = Split-Path -Parent $repo }    # default: the folder the repository is cloned into
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
if (-not $ConfigDir) { $ConfigDir = Join-Path $Root 'config' }
$ConfigDir = [IO.Path]::GetFullPath($ConfigDir).TrimEnd('\')
$vrpathFile = Join-Path $env:LOCALAPPDATA 'openvr\openvrpaths.vrpath'
$todo = New-Object System.Collections.Generic.List[string]    # changes made, or that a dry run would make
$warnings = 0

function Norm($p) { ([IO.Path]::GetFullPath($p)).TrimEnd('\').ToLowerInvariant() }
function Section($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[ ok ]  $m" -ForegroundColor Green }
function Info($m) { Write-Host "[info]  $m" }
function Warn($m) { $script:warnings++; Write-Host "[warn]  $m" -ForegroundColor Yellow }
function Bad($m)  { Write-Host "[FAIL]  $m" -ForegroundColor Red }
function Todo($m) { $todo.Add($m); Write-Host "[todo]  would: $m" -ForegroundColor Yellow }
function Done($m) { $todo.Add($m); Write-Host "[done]  $m" -ForegroundColor Green }
function Stop-Setup($code, $msg) { Bad $msg; Write-Host ""; Write-Host "Setup stopped (exit code $code). Nothing after this point was done." -ForegroundColor Red; exit $code }

Write-Host "SteamVR-OSC setup$(if ($DryRun) { ' (DRY RUN: nothing will be written)' })"
Info "repository : $repo"
Info "SteamVR    : $Root"
if ((Norm $ConfigDir) -ne (Norm (Join-Path $Root 'config'))) { Info "settings go to the ConfigDir override: $ConfigDir" }

# ---------------------------------------------------------------- 0. prerequisites (read-only)
Section "0. Prerequisites"
$problems = New-Object System.Collections.Generic.List[string]

$need = @('bin\win64\vrpathreg.exe', 'bin\win64\vrstartup.exe', 'bin\win64\vrserver.exe')
$missing = @($need | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Root $_) -PathType Leaf) })
$missing += @(@('drivers\lighthouse', 'drivers\null') | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Root $_) -PathType Container) })
if ($missing.Count -eq 0) {
    Ok "SteamVR files found under $Root (vrpathreg, vrstartup, vrserver, drivers\lighthouse, drivers\null)"
} else {
    $problems.Add("SteamVR is missing or incomplete under ${Root}: $($missing -join ', '). Download SteamVR with DepotDownloader to this folder first.")
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
$pythonExe = $null
if (-not $pythonCmd) {
    $problems.Add("python was not found on PATH. Install Python 3.15 (tick 'Add python.exe to PATH').")
} else {
    $pythonExe = $pythonCmd.Source
    $pyVersion = (& $pythonExe --version) -join ' '
    $pyRan = ($LASTEXITCODE -eq 0) -and ($pyVersion -match 'Python (\d+)\.(\d+)\.(\d+)')
    if (-not $pyRan) {
        $problems.Add("'python' ($pythonExe) does not run (output: $pyVersion). If this is the Microsoft Store stub, install Python from python.org and put it first on PATH.")
    } elseif ($Matches[1] -eq '3' -and $Matches[2] -eq '15') {
        Ok "$pyVersion ($pythonExe)"
    } else {
        Ok "$pyVersion ($pythonExe)"
        Warn "the tested Python version is 3.15.x; $pyVersion may need other package versions than bridge\requirements.txt pins."
    }
}

$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    $problems.Add("git was not found on PATH. Install Git for Windows (it is needed to clone and update this repository).")
} else {
    Ok "$((& $gitCmd.Source --version) -join ' ') ($($gitCmd.Source))"
}

$dllWhy = "vrmonitor.exe shows an error popup ('d3dx10_43.dll was not found') every time SteamVR starts. Install the 'DirectX End-User Runtimes (June 2010)' (directx_Jun2010_redist.exe) from Microsoft and re-run setup."
$sys32 = Join-Path $env:windir 'System32\d3dx10_43.dll'
if (Test-Path -LiteralPath $sys32) {
    Ok "d3dx10_43.dll present in System32"
} else {
    $problems.Add("d3dx10_43.dll is missing from $env:windir\System32. $dllWhy")
}
$wow = Join-Path $env:windir 'SysWOW64'
if (Test-Path -LiteralPath $wow) {
    if (Test-Path -LiteralPath (Join-Path $wow 'd3dx10_43.dll')) {
        Ok "d3dx10_43.dll present in SysWOW64"
    } else {
        Warn "d3dx10_43.dll is missing from SysWOW64 (32-bit programs); the June 2010 DirectX runtime installs it too."
    }
}

if ($problems.Count -gt 0) {
    foreach ($p in $problems) { Bad $p }
    Write-Host ""
    Write-Host "Setup stopped (exit code 1): $($problems.Count) prerequisite problem(s) above. Nothing was changed." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------- 1. SteamVR must not be running
Section "1. SteamVR must not be running"
$rootPrefix = $Root + '\'
$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) })
if ($running.Count -eq 0) {
    Ok "no SteamVR process is running from $Root"
} else {
    $names = ($running | ForEach-Object { "$($_.Name)($($_.Id))" }) -join ', '
    if ($DryRun) {
        Warn "SteamVR is running ($names). A real run would stop here: stop it with stop-headless.ps1 first, because SteamVR rewrites steamvr.vrsettings on exit."
    } else {
        Stop-Setup 2 "SteamVR is running ($names). Stop it with stop-headless.ps1 first: SteamVR rewrites steamvr.vrsettings when it exits and would undo the settings change."
    }
}

# ---------------------------------------------------------------- 2. OpenVR registration
if ($Only -contains 'register') {
    Section "2. OpenVR registration (vrpathreg)"
    $vrpathreg = Join-Path $Root 'bin\win64\vrpathreg.exe'
    $want = [ordered]@{ runtime = $Root; config = (Join-Path $Root 'config'); log = (Join-Path $Root 'logs') }

    function Get-Registered {
        $r = [ordered]@{ runtime = $null; config = $null; log = $null }
        if (Test-Path -LiteralPath $vrpathFile) {
            try { $j = Get-Content -LiteralPath $vrpathFile -Raw | ConvertFrom-Json } catch { return $r }
            foreach ($k in @($r.Keys)) { $r[$k] = @($j.$k)[0] }
        }
        $r
    }
    function Show-Registered($label, $r) {
        Info "$label runtime = $($r.runtime)   config = $($r.config)   log = $($r.log)"
    }

    $before = Get-Registered
    if (Test-Path -LiteralPath $vrpathFile) { Show-Registered "before:" $before } else { Info "before: $vrpathFile does not exist yet" }

    foreach ($d in @($want.config, $want.log)) {
        if (Test-Path -LiteralPath $d -PathType Container) { Ok "folder exists: $d" }
        elseif ($DryRun) { Todo "create folder $d" }
        else { New-Item -ItemType Directory -Force -Path $d | Out-Null; Done "created folder $d" }
    }

    $verbs = [ordered]@{ runtime = 'setruntime'; config = 'setconfig'; log = 'setlog' }
    $differs = @($want.Keys | Where-Object { -not $before[$_] -or (Norm $before[$_]) -ne (Norm $want[$_]) })
    if ($differs.Count -eq 0) {
        Ok "already registered: runtime, config and log paths match"
    } else {
        foreach ($k in $differs) {
            if ($DryRun) { Todo "vrpathreg $($verbs[$k]) $($want[$k])   (now: $($before[$k]))"; continue }
            $out = & $vrpathreg $verbs[$k] $want[$k]
            if ($LASTEXITCODE -ne 0) { Stop-Setup 3 "vrpathreg $($verbs[$k]) $($want[$k]) failed with exit code $LASTEXITCODE. $($out -join ' ')" }
            Done "vrpathreg $($verbs[$k]) $($want[$k])"
        }
        if (-not $DryRun) {
            $after = Get-Registered
            Show-Registered "after: " $after
            $bad = @($want.Keys | Where-Object { -not $after[$_] -or (Norm $after[$_]) -ne (Norm $want[$_]) })
            if ($bad.Count -gt 0) { Stop-Setup 3 "registration did not take effect for: $($bad -join ', ') (see $vrpathFile)" }
            Ok "registration verified"
        }
    }
}

# ---------------------------------------------------------------- 3. headless settings
if ($Only -contains 'settings') {
    Section "3. Headless settings (steamvr.vrsettings)"
    $templateFile = Join-Path $repo 'config\steamvr.vrsettings'
    $target = Join-Path $ConfigDir 'steamvr.vrsettings'
    try { $template = Get-Content -LiteralPath $templateFile -Raw | ConvertFrom-Json }
    catch { Stop-Setup 4 "cannot read the template $templateFile : $_" }

    $isObject = { param($v) $v -is [System.Management.Automation.PSCustomObject] }
    function Same($a, $b) { $null -ne $a -and $null -ne $b -and $a.GetType() -eq $b.GetType() -and $a -ceq $b }
    function Show($v) { if ($v -is [string]) { '"' + $v + '"' } elseif ($v -is [bool]) { $v.ToString().ToLowerInvariant() } else { "$v" } }

    # merge the template into the target; every difference is added to $changes
    function Merge-Template($dst, $src, $path, $changes) {
        foreach ($p in $src.PSObject.Properties) {
            $name = $p.Name; $full = if ($path) { "$path.$name" } else { $name }
            $has = $dst.PSObject.Properties.Name -contains $name
            if (& $isObject $p.Value) {
                if (-not $has) {
                    $dst | Add-Member -NotePropertyName $name -NotePropertyValue ([pscustomobject]@{})
                    $changes.Add("add section $full")
                } elseif (-not (& $isObject $dst.$name)) {
                    $changes.Add("replace $full ($(Show $dst.$name)) by a section")
                    $dst.$name = [pscustomobject]@{}
                }
                Merge-Template $dst.$name $p.Value $full $changes
            } elseif (-not $has) {
                $dst | Add-Member -NotePropertyName $name -NotePropertyValue $p.Value
                $changes.Add("set $full = $(Show $p.Value)")
            } elseif (-not (Same $dst.$name $p.Value)) {
                $changes.Add("change $full from $(Show $dst.$name) to $(Show $p.Value)")
                $dst.$name = $p.Value
            }
        }
    }

    $existed = Test-Path -LiteralPath $target
    if ($existed) {
        try { $current = Get-Content -LiteralPath $target -Raw | ConvertFrom-Json }
        catch { Stop-Setup 4 "$target is not valid JSON ($_). Fix or move it away, then run setup again." }
        if (-not (& $isObject $current)) { Stop-Setup 4 "$target does not contain a JSON object." }
        Info "existing file: $target"
    } else {
        $current = [pscustomobject]@{}
        Info "no file yet: $target"
    }
    $changes = New-Object System.Collections.Generic.List[string]
    Merge-Template $current $template '' $changes

    if ($changes.Count -eq 0) {
        Ok "the headless settings are already in place; file left untouched"
    } else {
        foreach ($c in $changes) { Info "  $c" }
        if ($DryRun) {
            Todo "$(if ($existed) { 'back up and update' } else { 'create' }) $target ($($changes.Count) change(s))"
        } else {
            if (-not (Test-Path -LiteralPath $ConfigDir)) { New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null }
            if ($existed) {
                $backup = "$target.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
                Copy-Item -LiteralPath $target -Destination $backup
                Info "backup: $backup"
            }
            $json = $current | ConvertTo-Json -Depth 20
            [IO.File]::WriteAllText($target, $json + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
            # verify: parse it again and compare with the template
            $verify = New-Object System.Collections.Generic.List[string]
            try { Merge-Template (Get-Content -LiteralPath $target -Raw | ConvertFrom-Json) $template '' $verify }
            catch { Stop-Setup 4 "the written $target does not parse: $_" }
            if ($verify.Count -gt 0) { Stop-Setup 4 "the written $target does not contain the headless settings ($($verify -join '; '))" }
            Done "$(if ($existed) { 'updated' } else { 'created' }) $target ($($changes.Count) change(s))"
        }
    }
}

# ---------------------------------------------------------------- 4. python packages
if ($Only -contains 'pip') {
    Section "4. Python packages (bridge\requirements.txt)"
    $reqFile = Join-Path $repo 'bridge\requirements.txt'
    $pins = @(Get-Content -LiteralPath $reqFile | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
    function Get-PipState {
        $installed = @{}
        $list = (& $pythonExe -m pip list --format=json) -join "`n"
        foreach ($i in ($list | ConvertFrom-Json)) { $installed[($i.name -replace '[-_.]+', '-').ToLowerInvariant()] = $i.version }
        $state = @()
        foreach ($pin in $pins) {
            if ($pin -match '^([A-Za-z0-9._-]+)\s*==\s*(\S+)$') {
                $n = ($Matches[1] -replace '[-_.]+', '-').ToLowerInvariant(); $v = $Matches[2]
                $have = $installed[$n]
                $state += [pscustomobject]@{ Pin = $pin; Have = $have; Ok = ($have -eq $v) }
            } else {
                $state += [pscustomobject]@{ Pin = $pin; Have = '?'; Ok = $false }
            }
        }
        $state
    }
    $state = @(Get-PipState)
    foreach ($s in $state) {
        if ($s.Ok) { Ok "$($s.Pin) installed" }
        elseif ($s.Have) { Info "$($s.Pin) wanted, $($s.Have) installed" }
        else { Info "$($s.Pin) not installed" }
    }
    if (@($state | Where-Object { -not $_.Ok }).Count -eq 0) {
        Ok "all pinned packages are already installed; nothing to do"
    } elseif ($DryRun) {
        Todo "python -m pip install -r bridge\requirements.txt"
    } else {
        Info "running: python -m pip install -r bridge\requirements.txt"
        & $pythonExe -m pip install -r $reqFile
        if ($LASTEXITCODE -ne 0) { Stop-Setup 5 "pip install failed with exit code $LASTEXITCODE (see the output above)." }
        $stillBad = @(Get-PipState | Where-Object { -not $_.Ok })
        if ($stillBad.Count -gt 0) { Stop-Setup 5 "after pip, these pins are still not satisfied: $(($stillBad | ForEach-Object { $_.Pin }) -join ', ')" }
        Done "installed the packages of bridge\requirements.txt"
    }
}

# ---------------------------------------------------------------- 5. self-test
if ($RunTests) {
    Section "5. Self-test (tests\test_scenerotator.py)"
    $out = @(& $pythonExe -B -I (Join-Path $repo 'tests\test_scenerotator.py'))
    $code = $LASTEXITCODE
    $pass = @($out | Where-Object { $_ -like 'PASS *' }).Count
    $fail = @($out | Where-Object { $_ -like 'FAIL *' }).Count
    if ($code -eq 0 -and $fail -eq 0) {
        Ok "self-test passed ($pass checks)"
    } else {
        $out | Where-Object { $_ -like 'FAIL *' } | ForEach-Object { Bad $_ }
        Stop-Setup 6 "self-test failed (exit code $code, $fail failing check(s), $pass passing)."
    }
}

# ---------------------------------------------------------------- summary
Write-Host ""
if ($DryRun) {
    if ($todo.Count -eq 0) { Write-Host "DRY RUN: everything is already in place; a real run would change nothing." -ForegroundColor Green }
    else { Write-Host "DRY RUN: $($todo.Count) change(s) would be made (see [todo] lines); nothing was written." -ForegroundColor Yellow }
} elseif ($todo.Count -eq 0) {
    Write-Host "Setup finished: everything was already in place, nothing changed." -ForegroundColor Green
} else {
    Write-Host "Setup finished: $($todo.Count) change(s) made (see [done] lines)." -ForegroundColor Green
}
if ($warnings -gt 0) { Write-Host "$warnings warning(s) above." -ForegroundColor Yellow }
exit 0
