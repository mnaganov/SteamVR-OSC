# INSTRUCTIONS.md - guide for the AI agent that sets up this PC

You are an AI agent on a Windows PC. You know nothing about the session in which this repository was
built. This file tells you everything you need. Follow it in order, report evidence after every phase,
and ask the user whenever a phase needs hardware or a decision. Statements marked **[inferred]** were
worked out from files and logs but not confirmed by documentation; statements marked **[unverified]**
were reported by the user or by an earlier session and could not be checked again.

## 1. Goal and end state

Bring this PC to the state of the laptop this repository was made on:

- SteamVR runs **headless, without the Steam client**: no headset, the `null` driver provides a fake HMD,
  and `steamvr.vrsettings` carries exactly the four settings of `config\steamvr.vrsettings`
  (`steamvr.requireHmd=false`, `steamvr.forcedDriver="null"`, `steamvr.activateMultipleDrivers=true`,
  `driver_null.enable=true`).
- OpenVR is registered for this SteamVR (`runtime = Root`, `config = Root\config`, `log = Root\logs`).
- The SteamVR "Room Setup" wizard, which SteamVR opens at every start because there is no headset, is
  closed automatically by the launcher.
- One **VIVE Tracker 3.0** is tracked by two lighthouse base stations (first connected by USB cable, then
  wireless through its USB dongle).
- The bridge (`bridge\openvr-osc.py`, mode `--scenerotator`) sends the head rotation of that tracker as
  `/SceneRotator/ypr` to `127.0.0.1:9000`, where the **IEM SceneRotator** plug-in in **Reaper** compensates
  head movements (binaural monitoring of Ambisonics).
- Daily use is one command: `start-headtracker.cmd` (starts SteamVR, runs the bridge, stops SteamVR again).

## 2. Assumptions (the user has done these before you start)

- SteamVR (the laptop used 2.18.4; app id 250820 is shown in vrmonitor's log) was downloaded with
  DepotDownloader into `C:\SteamVR`. Do not download it yourself. If it is elsewhere, that is fine:
  **Root = the parent folder of this repository** (this repository must be a direct subfolder of it).
- Python (tested: 3.15.2), Git and the DirectX June 2010 runtime (`d3dx10_43.dll`) are installed.
- This repository is cloned to `<Root>\SteamVR-OSC` (normally `C:\SteamVR\SteamVR-OSC`). Below, `$Repo` means
  that folder and `$Root` its parent.
- **There is no Steam client and none must be installed.**
- The user has a VIVE Tracker 3.0, its dongle, two lighthouse base stations (powered on, in view of the
  tracker) and Reaper with the IEM Plug-in Suite.

Use PowerShell. If your shell is Git Bash or cmd, call scripts as
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File <script> <arguments>`. Define the variables once:

```powershell
$Repo = 'C:\SteamVR\SteamVR-OSC'
$Root = Split-Path -Parent $Repo      # C:\SteamVR
```

## 3. Rules

1. **Never install Steam**, and never create fake Steam registry keys or files. (`vrstartup.exe` works without it.)
2. **Never edit SteamVR's own files** under `resources\`, `drivers\`, `tools\`, `bin\` (and do not rename or
   delete them). Everything this setup needs is in `config\` and in this repository.
3. **SteamVR rewrites `steamvr.vrsettings` when it exits.** Change settings only while SteamVR is stopped
   (`setup.ps1` enforces this).
4. **Ask the user before any hardware action**: connecting or disconnecting the tracker or dongle, pairing,
   power-cycling base stations, changing a base station channel, and especially firmware updates (never
   update firmware unless the user explicitly approves it).
5. **Do not push, commit or edit this repository** unless the user asks you to. Do not change the scripts.
6. **`logs\vrserver.txt` (and the other logs) are appended across runs**, so a search can match lines of
   old runs. Always limit a search to the current run: it starts at the last line containing
   `startup with PID=`:
   ```powershell
   $lines = Get-Content "$Root\logs\vrserver.txt"
   $start = @($lines | Select-String 'startup with PID=')[-1].LineNumber
   $run   = $lines[($start - 1)..($lines.Count - 1)]
   $run | Select-String 'Active HMD set|Loaded server driver|Connected to receiver|BOOTSTRAPPED|CALIBRATED|universe'
   ```
   (SteamVR also rotates logs to `*.previous.txt`; the current run is always in the file without `previous`.)
7. After every phase, **report evidence to the user**: the commands you ran, the exit codes and the pasted
   key output or log lines. Say plainly when something failed or was skipped.
8. Do not bind UDP port 9000 yourself for tests: Reaper may be listening there. To test without Reaper use
   another port (`--port 9100`) and your own listener.

## 4. Procedure

### Phase 1 - prerequisite check (changes nothing)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$Repo\setup.ps1" -DryRun
```
Expected: `[ ok ]` lines for the SteamVR files, Python (a warning if it is not 3.15.x), git, and
`d3dx10_43.dll` in System32 and SysWOW64; then the plan for each step (`[todo] would: ...` on a fresh PC);
the last line starts with `DRY RUN:` and the exit code is 0.
If a `[FAIL]` line appears (exit code 1 or 2), fix it with the user and repeat. See pitfalls P1 (missing DLL),
P2 (missing SteamVR files), P12 (Python version) and P13 (SteamVR still running).

### Phase 2 - setup

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$Repo\setup.ps1" -RunTests
```
`setup.ps1` is idempotent and safe to re-run. It (1) registers OpenVR with `vrpathreg`
(runtime = `$Root`, config = `$Root\config`, log = `$Root\logs`), (2) merges the four settings into
`$Root\config\steamvr.vrsettings` (creates it, keeps other keys, writes `steamvr.vrsettings.bak-<time>` before
changing an existing file), (3) installs `bridge\requirements.txt` with pip, (4) runs the self-test.
Expected: `[done]` lines for what it changed, `[ ok ]  self-test passed (66 checks)` and exit code 0.
Verify:

```powershell
& "$Root\bin\win64\vrpathreg.exe" show        # Runtime path = C:\SteamVR, Config path = ...\config, Log path = ...\logs
Get-Content "$Root\config\steamvr.vrsettings"
powershell -NoProfile -ExecutionPolicy Bypass -File "$Repo\setup.ps1" -DryRun     # now: everything already in place
```
Exit codes of `setup.ps1`: 0 ok, 1 prerequisites, 2 SteamVR running, 3 registration, 4 settings, 5 pip, 6 self-test.
Options: `-Root <folder>`, `-DryRun`, `-RunTests`, `-Only register,settings,pip` (a subset of the changing
steps), `-ConfigDir <folder>` (test hook for the settings merge only).

### Phase 3 - headless SteamVR without a tracker (the tracker must be OFF and unplugged)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$Repo\start-headless.ps1"
```
Expected console output (about 15 s):
```
vrserver running, PID <n>
Log: <Root>\logs\vrserver.txt
Room Setup wizard detected (PID <n>), closing it.
Room Setup wizard closed gracefully (window close sent: True).
```
(The last line may instead read `... did not exit after a window close (sent: False); terminated PID <n>.` -
see P7; both are fine.) Wait about 60 s, then check:

1. Processes: `Get-Process vrserver, vrcompositor, vrdashboard, vrmonitor` are all running, and
   **`vrmonitor` is still running after 60 s** (P1: it exits on its own when the DirectX DLL is missing).
   `Get-Process steamvr_room_setup` finds nothing.
2. Current-run log lines in `logs\vrserver.txt` (rule 6):
   ```
   ... vrserver 2.18.4 startup with PID=<n>, config=<Root>\config, runtime=<Root>, arch=win64
   ... Driver 'null' started activation of tracked device with serial number 'Null Serial Number'
   ... Loaded server driver null (IServerTrackedDeviceProvider_004) from <Root>\drivers\null\bin\win64\driver_null.dll
   ... Active HMD set to null.Null Serial Number
   ... Loaded server driver lighthouse (IServerTrackedDeviceProvider_004) from <Root>\drivers\lighthouse\bin\win64\driver_lighthouse.dll
   ... Read chaperone JSON from <Root>\config\chaperone_info.vrchap
   ... Failed to read chaperone file from <Root>\config\chaperone_info.vrchap        <- expected and harmless (P6)
   ```
   `lighthouse: Attached HID Devices:` lists the dongle (`28DE, 2101: ... Watchman Dongle`) if it is plugged in.
3. `& "$Root\bin\win64\vrcmd.exe" --info` shows `Device 0 - null.Null Serial Number - Null Model Number - HMD ...`.
4. **No DirectX popup**: the Windows System log has no new `Application Popup` event (Event ID 26) naming
   `d3dx10_43.dll`:
   ```powershell
   Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Application Popup'; StartTime=(Get-Date).AddMinutes(-10)} -ErrorAction SilentlyContinue |
       Select TimeCreated, Id, Message
   ```
   Empty output is the expected result. (On the laptop, before the DLL was installed, every start logged
   `Application popup: vrmonitor.exe - System Error : The code execution cannot proceed because d3dx10_43.dll was not found.`)
5. Stop: `powershell -NoProfile -ExecutionPolicy Bypass -File "$Repo\stop-headless.ps1"` ->
   `SteamVR stopped cleanly.` and `Get-Process vr*, steamvr_room_setup` shows nothing.

### Phase 4 - tracker connected by USB cable (ask the user to do the hardware steps)

Ask the user to power the two base stations, connect the VIVE Tracker 3.0 to the PC with its USB cable and
keep it in view of both base stations, then start SteamVR again (`start-headless.ps1`) and check:

- `vrcmd --info` lists, besides the null HMD, a `Tracker` and two `Tracking Reference` devices, e.g. (example
  serials from the laptop, yours will differ):
  ```
  Device 1 - lighthouse.LHR-3642A33E - VIVE Tracker 3.0 MV by HTC - Tracker - {htc}vr_tracker_vive_3_0
  Device 2 - lighthouse.LHB-E0AC4139 - Valve SR Imp by Valve Corporation - Tracking Reference - lh_basestation_valve_gen2
  Device 3 - lighthouse.LHB-529D9B7A - Valve SR Imp by Valve Corporation - Tracking Reference - lh_basestation_valve_gen2
  ```
- Current-run log lines, in this order, a few seconds apart:
  ```
  Driver 'lighthouse' started activation of tracked device with serial number 'LHR-<tracker>'
  Driver 'lighthouse' started activation of tracked device with serial number 'LHB-<base 1>'
  Driver 'lighthouse' started activation of tracked device with serial number 'LHB-<base 2>'
  lighthouse: LHR-<tracker> C: ----- BOOTSTRAPPED base <id> (immediate) distance 1.28m ... -----
  lighthouse: LHR-<tracker> C: ----- CALIBRATED base <id> at pitch ... deg roll ... deg -----
  lighthouse: Creating new universe <id> because there were no compatible existing universes     (first time only)
  lighthouse: Selected existing universe <id> (<base id> is primary)                              (later runs)
  lighthouse: LHR-<tracker> C: ----- SECONDARY base <id> distance ... -----
  lighthouse: LHR-<tracker> C: ----- RELATIONSHIP bases <id> <-> <id> distance ..., angle ... deg -----
  ```
  **Both base stations must appear** (two `LHB-` activations and a `SECONDARY base` line). If only one is
  seen or tracking is unstable, see P9 (base station channel conflict).
- **The wired pattern** (observed on the laptop on 2026-11-19 with the tracker on a USB cable): Windows lists
  the tracker as a USB device (`USB\VID_28DE&PID_2300\LHR-<tracker>`, status OK, plus HID interfaces
  `MI_00`/`MI_01`/`MI_02`), and the current run of `vrserver.txt` shows the tracker's three HID interfaces in
  the `Attached HID Devices` list, followed by the driver finishing the device:
  ```
  lighthouse: Attached HID Devices:
  lighthouse:     28DE, 2300: s/n LHR-<tracker>: IMU (interface 0)
  lighthouse:     28DE, 2300: s/n LHR-<tracker>: Optical (interface 1)
  lighthouse:     28DE, 2300: s/n LHR-<tracker>: Controller (interface 2)
  ...
  Driver 'lighthouse' finished adding tracked device with serial number 'LHR-<tracker>'
  ```
  (`LHR-<tracker>` is the tracker's own serial, `3642A33E` on the laptop. In the wireless case of Phase 5 the
  only HID entry is the dongle, `28DE, 2101: ... Watchman Dongle`.) Check it with
  `Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_28DE*'`.

Keep the output as evidence, stop SteamVR with `stop-headless.ps1`.

### Phase 5 - wireless tracker (pairing is done BY THE USER)

Do not pair on your own. Ask the user to do the following with the dongle plugged into the PC and SteamVR
running (`start-headless.ps1`):

1. In the **SteamVR Status** window (the small window with the headset/tracker icons) open its menu (the
   three-line button) and choose **Devices -> Pair Controller** **[unverified wording of the menu]**. The
   pairing window is titled "Controller Pairing" and asks you to select the controller type: choose
   **HTC Vive Tracker** (these texts are in the installed SteamVR resources).
2. Hold the tracker's power button for about 2 seconds until it enters pairing mode (HTC's developer guide:
   "press the Power button on VIVE Tracker (3.0) for 2 seconds to enter pairing mode"). The LED blinks blue
   while pairing **[from HTC's documentation and general knowledge; not observed in this project]**; a **solid
   green LED means the tracker is connected and tracking** (confirmed by the user on the laptop: "Tracker is on,
   LED is green" while it was tracking wirelessly).
3. When SteamVR reports success the tracker icon appears in the Status window.

Verify that it is now wireless: in the current run the log shows
`lighthouse: LHR-<tracker>: Connected to receiver <dongle serial>` (the receiver is the dongle, example from
the laptop: `Connected to receiver 0459798878`) and the dongle is listed as `Watchman Dongle` in
`Attached HID Devices`. Then ask the user to unplug the USB cable and confirm tracking continues
(`vrcmd --info` still lists the tracker). Notes: a wireless tracker is switched off by SteamVR when SteamVR
exits, so it must be switched on again after each start (see P10). If the pairing window says "No pairable
devices detected" check that the dongle is plugged in; if it says "It looks like your controllers are already
connected" all of the dongle's slots are taken (turn off one of the connected devices). Both texts are from the
installed SteamVR resources.

### Phase 6 - bridge and SceneRotator

1. Ask the user to set up Reaper: SceneRotator on the Ambisonic track(s), in the plug-in's OSC settings the
   **receive port = 9000**, and **leave the three Flip toggles off** (the bridge handles directions). The
   bridge also sends `/SceneRotator/rotationSequence 0`, which selects `Yaw->Pitch->Roll` in the plug-in.
2. Start everything with one command, in a console the user can see (the keys need that console):
   ```powershell
   & "$Repo\start-headtracker.cmd"
   ```
   (or `start-headtracker.ps1`; extra arguments are passed to the bridge, e.g. `start-headtracker.cmd --front=+y --port 9001`).
   Expected console output (the tracker appears about 15 s after the start if it is switched on):
   ```
   [headtracker] Starting SteamVR ...
   ... vrserver running ... Room Setup wizard closed gracefully ...
   [headtracker] Running the bridge: python openvr-osc.py --scenerotator
   OpenVR OSC - SceneRotator mode
     sending /SceneRotator/ypr (yaw pitch roll, degrees, rotationSequence 0) to 127.0.0.1:9000 at 100 Hz
     tracker axis pointing to the front of the head: -y
   tracker LHR-<serial>: tracking
   recentered: heading <deg> deg in the tracking space, gravity in tracker axes (+0.00, -0.03, -1.00)
   sent yaw  +0.03  pitch  +0.06  roll  -0.02   [r]ecenter [q]uit
   ```
   Keys: **`r` or space** = recenter (look straight ahead with the head level), **`q`** = quit. When the bridge
   ends the launcher stops SteamVR again (if the launcher started it). The first line after `recentered` shows
   the gravity direction in tracker axes: for a tracker lying flat with its top face up it is about
   `(0, 0, -1)` - a quick check of the mounting.
3. **Direction check** with the user, wearing the tracker on the headphone band (press `r` while looking
   straight ahead). The status line shows what is sent; SceneRotator shows the same values:

   | head movement | value sent (approx.) |
   | --- | --- |
   | turn the head 30 degrees to the left | yaw about **-30**, pitch and roll about 0 |
   | tilt the nose up by 20 degrees | pitch about **+20** |
   | tilt the right ear toward the right shoulder by 15 degrees | roll about **-15** |

   The sound scene must stay fixed in the room while the head moves. (The bridge sends the *scene* rotation,
   the inverse of the head rotation; on the laptop the user confirmed in Reaper that the directions are right
   with the defaults.)
4. **Mounting.** The default `--front=-y` means: the tracker lies flat on the headband (docking face on the
   band, top face up) with the edge that carries the LED pointing to the front of the head. If the user
   mounts it differently, pass `--front` with the tracker axis that points forward (`+x -x +y -y +z -z`, in
   the OpenVR device frame; write negative values as `--front=-x`). In that frame +z points from the top face
   toward the mounting face, +y toward the narrow (pogo-pin/USB-C) end, +x to the side **[inferred from the
   installed render model and HTC's guide figures, confirmed by gravity readings on the laptop]**; the LED
   side is toward -y **[inferred, about 70 percent sure; the user confirmed the direction check works with
   the default]**. Symptoms: a 90 degree error (yaw and pitch/roll axes mixed up) means the wrong one of
   x/y; a 180 degree error (head left turns the scene the wrong way) means the opposite sign. The front axis
   must be at least 30 degrees away from vertical at recenter (P11). `--tracker-serial LHR-...` selects a
   tracker when several are present.
5. All bridge options: `--ip`, `--port` (default 9000 in this mode), `--prefix`, `--rate`,
   `--no-rotation-sequence`, `--duration`, `--front`, `--tracker-serial`, `--scenerotator` (see `bridge\README.md`).

### Phase 7 - final report to the user

Give the user a short report: the Root, the SteamVR version, the output of `setup.ps1 -DryRun` after setup
(everything in place), the registration and settings contents, the evidence from phases 3-6 (log lines,
`vrcmd --info`, no Event 26), the serials you saw (dongle, tracker, base stations), the `--front` value in use,
what you could not verify and anything the user still has to do (e.g. re-pair, base station channels).

## 5. Known pitfalls (symptom -> cause -> fix)

**P1. vrmonitor shows an error popup "d3dx10_43.dll was not found" and vrmonitor exits after under a minute.**
Cause: `vrmonitor.exe` (and `overlay_viewer.exe`) import the legacy DirectX 10 helper `d3dx10_43.dll`, which only
the DirectX June 2010 runtime installs. The System log gets an `Application Popup` event (ID 26) at every
start. Fix: install the "DirectX End-User Runtimes (June 2010)", re-run `setup.ps1 -DryRun` (it checks
System32 and SysWOW64), restart (a reboot was done on the laptop).

**P2. `setup.ps1` says SteamVR is missing or incomplete.** Cause: wrong folder or an incomplete download.
Fix: SteamVR must be in the parent folder of the repository with `bin\win64\vrpathreg.exe`, `vrstartup.exe`,
`vrserver.exe` and the folders `drivers\lighthouse`, `drivers\null`. Do not copy anything into it by hand;
ask the user to complete the DepotDownloader download.

**P3. `start-headless.ps1` stops with "runtime is ..., expected ..." or "requireHmd is not false".** Cause:
`setup.ps1` was not run, or `-Root` differs from the registered runtime. Fix: run `setup.ps1`; check
`vrpathreg.exe show`.

**P4. "vrserver already running" from `start-headless.ps1`.** Fix: `stop-headless.ps1` first (or use
`start-headtracker.ps1`, which uses a running SteamVR and leaves it running afterwards).

**P5. SteamVR cannot start without Steam?** It can: `vrstartup.exe` (what `start-headless.ps1` runs) works with
no Steam client and no fake registry keys; the "Steam is not running" type of error does not occur.
Do not install Steam.

**P6. The Room Setup wizard opens at every start.** Cause: vrmonitor logs `[System] Chaperone indicates
room setup`, `Launching room setup, because calibration state was 201`, then launches
`tools\steamvr_room_setup`. There is no setting that disables it, and a hand-made `config\chaperone_info.vrchap`
does **not** help: SteamVR reads it without error, but the calibration state (201) is decided about 4 s
after the start, before the lighthouse universe exists, so the wizard still launches. Fix (built in):
`start-headless.ps1` waits up to 30 s (`-RoomSetupWaitSec`) for the wizard, closes its window, and
terminates only that process if it stays alive; `-KeepRoomSetup` leaves it open. `vrserver.txt` also logs
`Failed to read chaperone file from ...chaperone_info.vrchap`: harmless. The "Room Setup (C201)" status
alert in the SteamVR Status window is cosmetic, because there is no headset to calibrate.

**P7. `Room Setup wizard did not exit after a window close (sent: False); terminated PID <n>`.** Expected:
the wizard sometimes has no window within the 8 s grace period, so the script falls back to terminating that
one process. Both outcomes are fine.

**P8. `entering standby` / `leaving standby` lines every few seconds or minutes.** Harmless: the null HMD
has no user presence, so SteamVR idles. Observed once on the laptop: `lighthouse: Device LHR-<tracker> powering
off upon entering standby` about 40 s after `entering standby` **[not investigated; a wireless tracker may switch
off when SteamVR idles for a while; switching it on again or moving it brings it back and the bridge keeps
waiting and resumes]**.

**P9. Only one base station is seen, or tracking jumps.** Cause: two base stations on the same channel. The
symptom is this line in the current run of `vrserver.txt`:
`lighthouse: LHR-<tracker> C: Saw sync on beam channel conflict on ch <n>` (on the laptop, on 2026-11-19, with
one base station visible: `... Saw sync on beam channel conflict on ch 0`). After the user changed one base
station's channel, a later run had no "conflict" line, both base stations were seen, and the log showed
`lighthouse: LHR-<tracker> C: SOB: add S-2` followed by `SOB: add S-1 also seeing S-2`. Fix (ask the user):
give each base station its own channel (Base Station 2.0: set the channel on the unit, see its manual;
SteamVR learns the channels into `config\lighthouse\lighthousedb.json` as `sobChannel`), restart SteamVR and
check for two `LHB-` activations and a `SECONDARY base` line.

**P10. A wireless tracker is switched off when SteamVR exits** (log: `powering off upon entering standby`
or at shutdown). Fix: switch it on again after each start; the bridge shows `waiting for a tracker (SteamVR
is running, retrying)...` and connects when it appears. It does not send while the tracker pose is not valid.

**P11. `WARNING: waiting to recenter: the front axis (-y) is only <n> deg from vertical ...`.** Cause: the
tracker axis chosen with `--front` points (nearly) up or down, so the front direction of the head is not
defined. The bridge sends nothing until the pose allows it (automatic recenter) or drops the `r` key press
(manual recenter, the old calibration stays). Fix: hold or mount the tracker so that the axis is at least 30
degrees from vertical, or pass another `--front`.

**P12. Python version.** Tested with Python 3.15.2 and these pins: `colorama==0.4.6`, `openvr==2.12.1401`,
`python-osc==1.10.3`, `reprint==0.6.0`, `six==1.17.0` (`bridge\requirements.txt`). `setup.ps1` warns for other
versions. If pip cannot install a pin on another Python version, install the closest versions available
(`python -m pip install openvr python-osc colorama reprint six`), then run
`python -B -I tests\test_scenerotator.py` and the bridge; tell the user which versions were used. Note that
`openvr` (pyopenvr) 2.x returns `str` where 1.x returned `bytes`; the bundled `bridge\triad_openvr` already
handles both.

**P13. `setup.ps1` stops with "SteamVR is running".** Fix: `stop-headless.ps1`, then re-run (see rule 3).

**P14. Pressing Ctrl+C in `start-headtracker.cmd` ends with "Terminate batch job (Y/N)?".** That prompt is cmd.exe's
own and appears after the bridge stopped and SteamVR was shut down cleanly. Answer Y. Quitting with `q` does
not show it, and `start-headtracker.ps1` run directly does not either.

**P15. `start-headtracker.cmd` window stays open with "Press any key".** The launcher or the bridge ended with an
error (exit code shown). Exit codes of `start-headtracker.ps1`: 0 bridge ended normally (q or Ctrl+C), 2 a
check failed before anything was started (SteamVR files, scripts, bridge folder, python), 3 `start-headless.ps1`
failed (the launcher stops a half-started SteamVR and does not run the bridge), 4 SteamVR could not be
stopped, otherwise the bridge's own exit code.

**P16. The bridge's old mode (`python bridge\openvr-osc.py --track tracker`) sometimes lists no tracker.** Cause:
`triad_openvr` discovers devices once at start and misses a tracker whose pose is momentarily invalid. The
SceneRotator mode does not have this problem: it retries until SteamVR and the tracker are there.

**P17. `bridge\openvr-osc.py` messages are not received by SceneRotator.** The plug-in only accepts
`/SceneRotator/ypr` with exactly three float arguments (an OSC array drops the whole datagram); this bridge
sends them correctly. Check the receive port (9000), that Flip is off, and that nothing else (a second bridge)
uses the port. To look at the traffic without Reaper run the bridge with `--port 9100` and your own UDP listener.

## 6. Machine-specific values: do NOT copy them, do not expect them to match

These belong to the laptop's hardware and history. They are examples only; your PC will show different ones
and that is correct:

- Serial numbers: tracker `LHR-3642A33E`, base stations `LHB-529D9B7A` and `LHB-E0AC4139`, dongle `0459798878`.
- The lighthouse universe id (`1795153620`), `config\lighthouse\lighthousedb.json` and `config\lighthouse\lhr-*\config.json`
  (calibration and radio data of that tracker/base pair; SteamVR creates its own).
- The GPU entries and window positions SteamVR writes into `steamvr.vrsettings` (`GpuSpeed`, `DesktopUI`,
  `LastKnown`), the heading printed at recenter, the `vrserver` PIDs and timestamps.
- Never copy `config\lighthouse` from another PC.

## 7. Done checklist

- [ ] `setup.ps1 -DryRun` ends with "everything is already in place" and `setup.ps1 -RunTests` passed.
- [ ] `vrpathreg.exe show` points at `$Root`, `$Root\config`, `$Root\logs`; `steamvr.vrsettings` has the four keys.
- [ ] Headless start: `Active HMD set to null.Null Serial Number`, lighthouse driver loaded, vrmonitor stays up
      for 60 s, no new Event ID 26 for `d3dx10_43.dll`, room-setup wizard closed, clean stop.
- [ ] Tracker (USB, then wireless): in `vrcmd --info`, both base stations seen, `BOOTSTRAPPED`/`CALIBRATED`,
      `Connected to receiver <dongle>` for the wireless case.
- [ ] `start-headtracker.cmd`: `tracker ...: tracking`, `recentered: ...`, `sent yaw ... pitch ... roll ...` lines.
- [ ] SceneRotator receives on port 9000 with Flip off; the direction check of Phase 6 matches the table.
- [ ] `q` quits the bridge and SteamVR is stopped (0 `vr*` processes); the final report was given to the user.
- [ ] Nothing was installed except the Python packages; no Steam; no SteamVR file edited; nothing committed.
