# SteamVR-OSC

Head tracking for binaural monitoring of Ambisonics, without a VR headset and without Steam: a **VIVE
Tracker 3.0** on a headphone band is tracked by **SteamVR running headless**, and a small Python bridge sends
its rotation over OSC to the **IEM SceneRotator** plug-in (for example in Reaper), which keeps the sound
scene fixed in the room while you move your head.

This repository contains everything needed to set up another Windows PC the same way: the launch scripts,
the SteamVR settings, the OSC bridge, a self-test and a guide for an AI agent that does the installation
with you (`INSTRUCTIONS.md`).

## Layout

```
C:\SteamVR\                    SteamVR itself (downloaded by you with DepotDownloader; not part of this repo)
  SteamVR-OSC\                 this repository (clone it here; the scripts use the parent folder as SteamVR root)
    INSTRUCTIONS.md            step-by-step guide for an AI agent (phases, expected output, pitfalls)
    setup.ps1                  idempotent setup: checks, OpenVR registration, headless settings, pip
    start-headtracker.cmd/.ps1 one command: start SteamVR, run the bridge, stop SteamVR afterwards
    start-headless.ps1         start SteamVR headless (closes the Room Setup wizard)
    stop-headless.ps1          stop SteamVR cleanly
    config\steamvr.vrsettings  the four headless settings that setup.ps1 merges into SteamVR's config
    bridge\                    the OSC bridge (openvr-osc.py, triad_openvr, requirements, README, CREDITS)
    tests\test_scenerotator.py self-test of the math and the send loop (no SteamVR needed)
```

## Quick start

1. **Install the prerequisites yourself**
   - SteamVR, downloaded with DepotDownloader into `C:\SteamVR` (no Steam client; do not install Steam).
     The setup was made with SteamVR 2.18.4.
   - Python (tested with 3.15.2, "Add python.exe to PATH"), Git for Windows, and the **DirectX End-User
     Runtimes (June 2010)** (provides `d3dx10_43.dll`; without it SteamVR's vrmonitor shows an error popup).
   - Hardware: a VIVE Tracker 3.0 with its dongle, two lighthouse base stations, Reaper with the IEM Plug-in Suite.
2. **Clone this repository into the SteamVR folder**
   ```
   cd C:\SteamVR
   git clone <url of this repository> SteamVR-OSC
   ```
3. **Let an agent do it, or do it by hand**
   - With an AI agent: tell it to follow `C:\SteamVR\SteamVR-OSC\INSTRUCTIONS.md`. It asks you for the hardware
     steps (connecting the tracker, pairing it with the dongle, base station channels).
   - By hand:
     ```powershell
     powershell -NoProfile -ExecutionPolicy Bypass -File C:\SteamVR\SteamVR-OSC\setup.ps1 -DryRun
     powershell -NoProfile -ExecutionPolicy Bypass -File C:\SteamVR\SteamVR-OSC\setup.ps1 -RunTests
     ```
     The dry run reports what would change; the second command does it (registers OpenVR, merges the
     headless settings into `C:\SteamVR\config\steamvr.vrsettings`, installs the Python packages, runs the
     self-test). It can be run again at any time and stops if SteamVR is running. Then pair the tracker with the
     dongle yourself: SteamVR Status window, menu, Devices, Pair Controller, "HTC Vive Tracker", and hold the
     tracker's power button for about 2 seconds.

## Daily use

Switch on the tracker (it is switched off when SteamVR exits), then double-click or run
`C:\SteamVR\SteamVR-OSC\start-headtracker.cmd`. It starts SteamVR, waits for the tracker, and runs the
bridge in the same window. Keys in that window:

| key | action |
| --- | --- |
| `r` or space | recenter: look straight ahead with your head level, then press it |
| `q` | quit the bridge; SteamVR is stopped again (if the launcher started it) |

Ctrl+C also quits (the .cmd then asks "Terminate batch job (Y/N)?", answer Y). Extra arguments are passed to
the bridge, for example `start-headtracker.cmd --front=+y --port 9001`. If SteamVR was already running when
you start the launcher it is used and left running. The bridge recenters by itself shortly after the tracker
is first seen, so start it while looking straight ahead.

Bridge options (all described in `bridge\README.md`): `--front` (the tracker axis that points to the front of the
head, default `-y` = tracker lying flat on the band with the LED edge forward; `+x -x +y -y +z -z`),
`--tracker-serial`, `--ip`, `--port`, `--prefix`, `--rate`, `--no-rotation-sequence`, `--duration`.

## SceneRotator settings

- In the plug-in's OSC settings set the **receive port to 9000** (the bridge default; change both with `--port`).
- Leave the three **Flip** toggles **off**; the bridge handles the directions. It also sends
  `/SceneRotator/rotationSequence 0` so the plug-in uses Yaw->Pitch->Roll.
- Quick direction check: turn your head 30 degrees to the left -> the bridge sends yaw about -30; nose up 20
  degrees -> pitch about +20; right ear down 15 degrees -> roll about -15. The sound scene must stay fixed.

## What `start-headless.ps1` does

It starts SteamVR with `vrstartup.exe` (no Steam needed), waits for `vrserver`, then closes the **Room Setup**
wizard that SteamVR opens at every start when there is no headset (`-KeepRoomSetup` keeps it,
`-RoomSetupWaitSec` sets how long to wait for it). `stop-headless.ps1` shuts SteamVR down with
`vrstartup.exe -shutdown` (`-Force` kills leftovers). Both use the parent folder of the repository as the
SteamVR root; `-Root` overrides it.

## Troubleshooting

`INSTRUCTIONS.md` section 5 lists the problems met while building this setup (missing DirectX DLL, Room Setup
wizard, base station channel conflict, standby, Python versions, the Ctrl+C prompt, ...) with their causes and fixes.

## Credits and licensing

The bridge is a modified copy of [OpenVR-OSC](https://github.com/BarakChamo/OpenVR-OSC) by BarakChamo and
contains a copy of [triad_openvr](https://github.com/TriadSemi/triad_openvr) by Triad Semiconductor; see
`bridge\CREDITS.md` for the exact versions and changes. Neither upstream repository contained a license file
at the versions used here, so check with the authors before redistributing this repository publicly.
SteamVR and the DirectX runtime are not part of this repository and remain under their own licenses.
