# OpenVR OSC bridge
> Track pose data from OpenVR devices via OSC, with a head-tracking mode for IEM SceneRotator

This folder is the OpenVR-OSC bridge used by SteamVR-OSC: a compact Python utility for tracking OpenVR devices (HMDs, controllers, trackers) and getting their position and rotation values over OSC, plus a head-tracking mode (`--scenerotator`) that drives the IEM Plug-in Suite SceneRotator from one tracker. It is a modified copy of [BarakChamo/OpenVR-OSC](https://github.com/BarakChamo/OpenVR-OSC) that uses a copy of Triad's [Python OpenVR wrapper](https://github.com/TriadSemi/triad_openvr); see [CREDITS.md](CREDITS.md).

Paths below are relative to the SteamVR-OSC repository folder (normally `C:\SteamVR\SteamVR-OSC`).

## Setup

### Requirements

Python 3 (tested with 3.15.2), an existing OpenVR installation (SteamVR) and compatible hardware (HTC Vive tracker etc.). The dependencies are pinned in `bridge\requirements.txt` (pyopenvr 2.x, python-osc, colorama, reprint, six).

### Installation

`setup.ps1` in the repository folder does this for you (together with the SteamVR registration and settings). To install only the Python dependencies run `python -m pip install -r bridge\requirements.txt`.

## How to use

For head tracking run `start-headtracker.cmd` (or `start-headtracker.ps1`) in the repository folder: it starts SteamVR headless, runs the bridge in the SceneRotator mode in the same console and stops SteamVR when the bridge ends. Extra arguments are passed on to the bridge.

To run the bridge alone (SteamVR must be running) enter the following in your terminal:
  `python bridge\openvr-osc.py`

### Tracked devices

The following devices are tracked and sent via OSC:
- headsets (HMDs)
- controllers
- tracker units
The OSC messages sent are formated in as follows:
`\{DEVICE_TYPE}\{DEVICE_ID} - [f,f,f,f,f,f]`

### OSC message format

Each message contains multiple float values in an order set by the `pose mode`:

In `Euler` mode:
- x position
- y position
- z position
- yaw
- pitch
- roll

In `Quaternion` mode:
 - `TBC`

Each tracking cycle is sent as a bundle of individual messages, per device, that are time synced.

### Configuration options
There are several configuration options to customize the OSC feed and the tracking

<details>
  <summary>OSC server ip</summary>
  
  Set the ip of the OSC server - `--ip 169.78.65.21`
  Defaults to `127.0.0.1 (localhost)`.
</details>

<details>
  <summary>OSC server port</summary>
  
  Set the port of the OSC server - `--port 5000`
  Defaults to `7000`.
</details>

<details>
  <summary>tracked device type</summary>
 
  By default all device types are tracked but that can lead to unnecesary OSC traffic.
  If you know which device type you'd like to track (HMD, controllers, trackers), you can limit the tracking:
  
  `--track=[hmd|controller|tracker]`
</details>

<details>
  <summary>tracking frequency (coming soon)</summary>
  > coming soon
</details>

<details>
  <summary>pose mode (coming soon)</summary>
  
  > coming soon
</details>

## SceneRotator mode

`--scenerotator` turns the script into a head tracker for the [IEM Plug-in Suite](https://plugins.iem.at) SceneRotator (e.g. in Reaper, for binaural monitoring of Ambisonics). It follows **one** tracker (e.g. a Vive Tracker mounted on a headphone band) and sends the rotation that compensates the head movement. Without the flag the script behaves as described above.

```
python bridge\openvr-osc.py --scenerotator
python bridge\openvr-osc.py --scenerotator --front=-y --tracker-serial LHR-XXXXXXXX --port 9000
```

Start SteamVR first or afterwards: the script waits (and keeps retrying) for SteamVR and for the tracker, does not send while the tracker pose is invalid, and carries on after dropouts. It never starts SteamVR itself (`start-headtracker.cmd` does that for you).

### What is sent

- `/SceneRotator/ypr yaw pitch roll` - exactly three float32 arguments (no array), in degrees, about 100 times per second. The values are the *scene* rotation, i.e. the inverse of the head rotation, for the plugin's `yaw -> pitch -> roll` sequence.
- `/SceneRotator/rotationSequence 0` - sent at start, whenever the tracker (re)appears and on every recenter, so the plugin uses `Yaw->Pitch->Roll`. Turn this off with `--no-rotation-sequence` if you set the sequence yourself (then the plugin must be set to `Yaw->Pitch->Roll`).

### Plugin settings

- OSC receive port: `9000` (the default of this mode; change with `--port`). 
- The three **Flip** toggles (and Invert Quaternion) must stay **off**. Directions are handled here; if one axis turns out reversed, fix it with the mounting/`--front` option rather than the Flip toggle.
- Rotation sequence: set to `Yaw->Pitch->Roll` automatically by the message above.

### Keys

- `r` (or space): recenter - look straight ahead with your head level, then press it.
- `q`: quit (Ctrl+C works too; `start-headtracker.cmd` then asks "Terminate batch job (Y/N)?" after it has stopped SteamVR - answer Y).

The script also recenters automatically about half a second after the first valid tracker pose (and again if SteamVR is restarted or a different tracker shows up), so start it while you look straight ahead. A short dropout of the same tracker keeps the current calibration.

### Mounting and the front axis

Recentering handles everything that can be measured: *up* comes from gravity and *yaw zero* from the heading at that moment, so a tilted mount (or a not-perfectly-level start) does not matter for yaw. What cannot be measured from a single pose is which direction of the tracker points to the front of your head. Tell the script with `--front`, one of `+x`, `-x`, `+y`, `-y`, `+z`, `-z` (axes of the tracker in the OpenVR device frame; write negative values as `--front=-x`).

The default is `-y`, meant for a tracker lying flat (docking face down on the headband, top face up) with the side that carries the LED pointing to the front of the head. In the OpenVR device frame of the Vive Tracker 3.0, +z points from the top face toward the mounting face (so the top face looks along -z), +y toward the narrow end (the end with the pogo-pin port and the USB-C port) and +x to the side; the LED sits on the top face on the wide-edge side of the power button, i.e. toward -y. This follows from the tracker's render model and HTC's developer guide figures, not from an official statement of the axes. If the plugin rotates around the wrong axes when you nod or turn, try the other `--front` values (a 90 degree error means the wrong one of x/y, a 180 degree error the opposite sign). For best results the tracker should sit rigidly with its front/up plane lined up with the head's front/up plane (any tilt is fine, a sideways twist is not).

The front axis must be at least 30 degrees away from vertical when you recenter (if you, say, stand the tracker on its end and use `--front=-z`, keep it tilted). Otherwise the script prints a warning and refuses to recenter: an automatic recenter keeps waiting (nothing is sent), a manual one is dropped and the previous calibration stays in use. When it recenters it prints the gravity direction in tracker axes, e.g. `(+0.00, +0.00, -1.00)` for a tracker lying flat top face up, which is handy for checking the mounting.

### Options

| option | default | meaning |
| --- | --- | --- |
| `--scenerotator` | off | enable this mode |
| `--ip`, `--port` | `127.0.0.1`, `9000` | OSC target (the default port is 7000 without this mode) |
| `--prefix` | `/SceneRotator/` | OSC address prefix |
| `--tracker-serial` | first tracker found | choose the tracker by serial number (e.g. `LHR-3642A33E`) |
| `--front` | `-y` | tracker axis (`+x -x +y -y +z -z`) that points to the front of the head |
| `--rate` | `100` | messages per second |
| `--no-rotation-sequence` | off | do not send `rotationSequence` |
| `--duration` | run until `q` | exit after this many seconds |

## Using SteamVR without a headset

The SteamVR-OSC repository sets this up (`setup.ps1`) and starts it (`start-headless.ps1` / `start-headtracker.cmd`). The original description of the technique is in [this tutorial](http://help.triadsemi.com/steamvr-tracking/steamvr-tracking-without-an-hmd).

## Roadmap (from the original project)

- [ ] period check for device state and new tracked devices
- [ ] adjustable tracking frequency
- [ ] adjustable pose tracking mode (euler/quaternion)
- [ ] unique tracked device ids
