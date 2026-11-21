from __future__ import print_function
import argparse
import math
import time
import sys
import random
from triad_openvr import triad_openvr
from pythonosc import osc_message_builder
from pythonosc import osc_bundle_builder
from pythonosc import udp_client
from reprint import output
from colorama import Fore, Back, Style

# ======================================================================================
# SceneRotator mode: pure math (no OpenVR, no OSC, no I/O)
# ======================================================================================
#
# Conventions (see README, "SceneRotator mode"):
#   * OpenVR tracking space: right-handed, +x right, +y up, -z forward (metres).
#     A pose matrix is device -> tracking space; its columns are the device axes
#     (x, y, z) expressed in tracking space.
#   * IEM / ambiX world: x front, y left, z up. IEM_FROM_OPENVR converts tracking-space
#     coordinates to IEM coordinates (x = -z_ov, y = -x_ov, z = y_ov).
#   * Head frame: x = front, y = left, z = up (same handedness as the IEM world).
#   * SceneRotator rotates the Ambisonic scene by the angles it is sent, so for head
#     tracking we send the INVERSE of the head rotation. With rotationSequence = 0
#     its matrix is Rx(roll) * Ry(pitch) * Rz(yaw), which is exactly the inverse of a
#     head rotation Rz(yaw_h) * Ry(pitch_h) * Rx(roll_h) for (yaw, pitch, roll) =
#     (-yaw_h, -pitch_h, -roll_h).

IEM_FROM_OPENVR = ((0.0, 0.0, -1.0),
                   (-1.0, 0.0, 0.0),
                   (0.0, 1.0, 0.0))

# Tracker axis (OpenVR device frame) that points to the front of the head.
FRONT_AXES = {
    '+x': (1.0, 0.0, 0.0), '-x': (-1.0, 0.0, 0.0),
    '+y': (0.0, 1.0, 0.0), '-y': (0.0, -1.0, 0.0),
    '+z': (0.0, 0.0, 1.0), '-z': (0.0, 0.0, -1.0),
}
DEFAULT_FRONT = '-y'

TRACKING_UP = (0.0, 1.0, 0.0)  # +y is up in OpenVR tracking space (gravity aligned)

# The front axis must be at least this far from vertical, otherwise "front" is not defined
# by the tracker pose (the head's front direction is the front axis projected to horizontal).
MIN_FRONT_ANGLE_FROM_VERTICAL_DEG = 30.0


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def scale(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def norm(v):
    return math.sqrt(dot(v, v))


def normalize(v):
    n = norm(v)
    return (v[0] / n, v[1] / n, v[2] / n)


def transpose(m):
    return tuple(tuple(m[r][c] for r in range(3)) for c in range(3))


def mat_mul(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def mat_vec(m, v):
    return tuple(sum(m[r][k] * v[k] for k in range(3)) for r in range(3))


def rot_x(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def rot_y(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def rot_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def rotation_from_pose(pose34):
    """3x3 rotation (tracker axes in tracking space) from an OpenVR 3x4 pose matrix."""
    return tuple(tuple(float(pose34[r][c]) for c in range(3)) for r in range(3))


def is_finite_matrix(m):
    return all(math.isfinite(m[r][c]) for r in range(3) for c in range(3))


def format_vec(v):
    return "(%+.2f, %+.2f, %+.2f)" % (v[0], v[1], v[2])


def head_mount_matrix(r_tracker, front_axis):
    """Fixed tracker -> head rotation M, calibrated while the head is level and upright.

    Columns of M are the head axes (front, left, up) expressed in tracker coordinates.
    'up' is gravity (tracking-space +y) seen from the tracker, which absorbs any tilt of
    the mounting. 'front' is the chosen tracker axis projected onto the horizontal
    plane (perpendicular to up). Raises ValueError if that axis is within
    MIN_FRONT_ANGLE_FROM_VERTICAL_DEG of vertical (then the front direction is ill-defined).
    """
    up = mat_vec(transpose(r_tracker), TRACKING_UP)
    nominal = FRONT_AXES[front_axis]
    from_vertical = math.degrees(math.acos(max(-1.0, min(1.0, abs(dot(nominal, up))))))
    if from_vertical < MIN_FRONT_ANGLE_FROM_VERTICAL_DEG:
        raise ValueError("the front axis (%s) is only %.0f deg from vertical (gravity is %s in tracker axes); "
                         "its direction is not defined well enough. Hold the tracker so that this axis is at "
                         "least %.0f deg from vertical, or choose another --front axis"
                         % (front_axis, from_vertical, format_vec(up), MIN_FRONT_ANGLE_FROM_VERTICAL_DEG))
    front = sub(nominal, scale(up, dot(nominal, up)))
    front = normalize(front)
    left = cross(up, front)
    return ((front[0], left[0], up[0]),
            (front[1], left[1], up[1]),
            (front[2], left[2], up[2]))


def head_world_orientation(r_tracker, mount):
    """Head frame -> IEM world rotation: H = C * R_tracker * M."""
    return mat_mul(mat_mul(IEM_FROM_OPENVR, r_tracker), mount)


def heading_deg(h):
    """Yaw (about world up, counter-clockwise from above) of the head front axis."""
    return math.degrees(math.atan2(h[1][0], h[0][0]))


def scene_angles_sequence0(r_scene):
    """(yaw, pitch, roll) in degrees such that Rx(roll) * Ry(pitch) * Rz(yaw) == r_scene.

    This is IEM SceneRotator's matrix for rotationSequence = 0 (yaw -> pitch -> roll,
    extrinsic). Pitch is in [-90, 90], yaw and roll in [-180, 180].
    """
    sin_b = max(-1.0, min(1.0, r_scene[0][2]))
    pitch = math.asin(sin_b)
    if abs(sin_b) > 1.0 - 1e-9:  # gimbal lock: only yaw +- roll is defined, put it all in yaw
        roll = 0.0
        yaw = math.atan2(r_scene[1][0], r_scene[1][1])
    else:
        yaw = math.atan2(-r_scene[0][1], r_scene[0][0])
        roll = math.atan2(-r_scene[1][2], r_scene[2][2])
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


class HeadMapper(object):
    """Maps tracker rotations to the SceneRotator yaw/pitch/roll to send."""

    def __init__(self, front_axis):
        if front_axis not in FRONT_AXES:
            raise ValueError("front axis must be one of %s" % ", ".join(sorted(FRONT_AXES)))
        self.front_axis = front_axis
        self.mount = None
        self.heading0 = 0.0
        self.up_tracker = None   # gravity (up) in tracker axes at the last recenter

    @property
    def calibrated(self):
        return self.mount is not None

    def reset(self):
        self.mount = None
        self.up_tracker = None

    def recenter(self, r_tracker):
        """Call while the user looks straight ahead with the head level.

        Recomputes the mounting offset from gravity and zeroes yaw to the current heading.
        Raises ValueError (and keeps the previous calibration) if it cannot be computed.
        """
        mount = head_mount_matrix(r_tracker, self.front_axis)
        h0 = head_world_orientation(r_tracker, mount)
        self.mount = mount
        self.heading0 = heading_deg(h0)
        self.up_tracker = (mount[0][2], mount[1][2], mount[2][2])

    def head_relative(self, r_tracker):
        """Head orientation relative to the recentered heading (IEM axes)."""
        h = head_world_orientation(r_tracker, self.mount)
        return mat_mul(rot_z(-self.heading0), h)

    def scene_ypr(self, r_tracker):
        """(yaw, pitch, roll) in degrees for /SceneRotator/ypr with rotationSequence 0."""
        scene = transpose(self.head_relative(r_tracker))
        return scene_angles_sequence0(scene)


# ======================================================================================
# SceneRotator mode: OpenVR access, console handling and the send loop
# ======================================================================================

SETTLE_SECONDS = 0.5   # tracker pose must be valid this long before the automatic recenter
RETRY_NOTICE_SECONDS = 10.0
STATUS_INTERVAL_TTY = 0.2
STATUS_INTERVAL_PIPE = 1.0


def _to_str(value):
    return value.decode('utf-8') if isinstance(value, bytes) else value


class TrackerLink(object):
    """Connects to SteamVR and follows one tracker; never raises, reconnects on its own.

    poll() returns (state, rotation) with state one of:
      'no_steamvr'  - cannot connect to SteamVR (retried about once a second)
      'no_tracker'  - connected, but no matching tracker is connected (rescanned ~1 s)
      'lost'        - tracker connected, but its pose is not valid right now
      'ok'          - rotation is the tracker's 3x3 rotation matrix
    """

    RETRY_INTERVAL = 1.0

    def __init__(self, serial=None):
        import openvr
        self.openvr = openvr
        self.wanted_serial = serial
        self.vr = None
        self.index = None
        self.serial = None
        self.generation = 0          # increases on every (re)connection to SteamVR
        self.poses = (openvr.TrackedDevicePose_t * openvr.k_unMaxTrackedDeviceCount)()
        self._next_retry = 0.0

    def close(self):
        if self.vr is not None:
            try:
                self.openvr.shutdown()
            except Exception:
                pass
        self.vr = None
        self.index = None
        self.serial = None

    def _connect(self):
        try:
            # Background: never starts SteamVR itself, fails if it is not running.
            self.vr = self.openvr.init(self.openvr.VRApplication_Background)
        except Exception:
            self.vr = None
            return False
        self.generation += 1
        self.index = None
        self.serial = None
        return True

    def _find_tracker(self):
        ov = self.openvr
        for i in range(ov.k_unMaxTrackedDeviceCount):
            if not self.vr.isTrackedDeviceConnected(i):
                continue
            if self.vr.getTrackedDeviceClass(i) != ov.TrackedDeviceClass_GenericTracker:
                continue
            serial = _to_str(self.vr.getStringTrackedDeviceProperty(i, ov.Prop_SerialNumber_String))
            if self.wanted_serial and serial != self.wanted_serial:
                continue
            self.index, self.serial = i, serial
            return True
        return False

    def _quit_requested(self):
        ov = self.openvr
        event = ov.VREvent_t()
        while self.vr.pollNextEvent(event):
            if event.eventType == ov.VREvent_Quit:
                return True
        return False

    def poll(self):
        now = time.monotonic()
        try:
            if self.vr is None:
                if now < self._next_retry:
                    return 'no_steamvr', None
                if not self._connect():
                    self._next_retry = now + self.RETRY_INTERVAL
                    return 'no_steamvr', None
            if self._quit_requested():
                try:
                    self.vr.acknowledgeQuit_Exiting()
                except Exception:
                    pass
                self.close()
                self._next_retry = now + self.RETRY_INTERVAL
                return 'no_steamvr', None
            if self.index is None:
                if now < self._next_retry:
                    return 'no_tracker', None
                if not self._find_tracker():
                    self._next_retry = now + self.RETRY_INTERVAL
                    return 'no_tracker', None
            ov = self.openvr
            self.vr.getDeviceToAbsoluteTrackingPose(ov.TrackingUniverseStanding, 0, self.poses)
            pose = self.poses[self.index]
            if not pose.bDeviceIsConnected:
                self.index = None
                self.serial = None
                self._next_retry = now + self.RETRY_INTERVAL
                return 'no_tracker', None
            if not pose.bPoseIsValid:
                return 'lost', None
            rotation = rotation_from_pose(pose.mDeviceToAbsoluteTracking)
            if not is_finite_matrix(rotation):
                return 'lost', None
            return 'ok', rotation
        except Exception:
            # SteamVR went away mid-call or similar: drop the connection and retry
            self.close()
            self._next_retry = now + self.RETRY_INTERVAL
            return 'no_steamvr', None


def make_key_reader():
    """Returns a function giving the next pressed key (lower case) or None.

    Uses msvcrt, i.e. keys are read from the Windows console (no Enter needed).
    Without a console / on other platforms it returns None forever.
    """
    try:
        import msvcrt
    except ImportError:
        return lambda: None

    def read():
        if not msvcrt.kbhit():
            return None
        ch = msvcrt.getwch()
        if ch in ('\x00', '\xe0'):   # function/arrow key: swallow the second code
            msvcrt.getwch()
            return None
        return ch.lower()
    return read


def osc_address(prefix, name):
    return prefix.rstrip('/') + '/' + name


def run_scenerotator(args, key_reader=None, link=None, client=None, clock=time.monotonic,
                     sleep=time.sleep, out=sys.stdout):
    """Head-tracking loop. The keyword arguments exist so the loop can be tested."""
    mapper = HeadMapper(args.front)
    link = link or TrackerLink(args.tracker_serial)
    client = client or udp_client.SimpleUDPClient(args.ip, args.port)
    key_reader = key_reader or make_key_reader()
    tty = out.isatty()
    ypr_address = osc_address(args.prefix, 'ypr')
    sequence_address = osc_address(args.prefix, 'rotationSequence')
    period = 1.0 / max(1, args.rate)

    def say(text):
        # finish a status line first so messages never overwrite it
        if tty:
            out.write('\r' + ' ' * 100 + '\r')
        out.write(text + '\n')
        out.flush()

    def send_sequence():
        if args.no_rotation_sequence:
            return
        client.send_message(sequence_address, 0.0)

    say("OpenVR OSC - SceneRotator mode")
    say("  sending %s (yaw pitch roll, degrees, rotationSequence 0) to %s:%d at %d Hz"
        % (ypr_address, args.ip, args.port, args.rate))
    say("  tracker axis pointing to the front of the head: %s%s"
        % (args.front, "" if not args.tracker_serial else ", tracker serial %s" % args.tracker_serial))
    say("  keys: r = recenter (look straight ahead, head level), q = quit; Flip toggles in the plugin must stay off")
    send_sequence()

    state_prev = None
    valid_since = None
    calibration_key = None    # (SteamVR session, tracker serial) the calibration belongs to
    recenter_pending = False
    recenter_manual = False
    last_notice = 0.0
    last_warning = -1e9
    last_status = 0.0
    last_ypr = None
    start = clock()
    next_tick = clock()
    quit_requested = False
    try:
        while not quit_requested:
            now = clock()
            if args.duration and now - start >= args.duration:
                break

            # keys
            while True:
                key = key_reader()
                if key is None:
                    break
                if key == 'q':
                    quit_requested = True
                elif key in ('r', ' '):
                    recenter_pending = True
                    recenter_manual = True
                    say("recenter requested")

            state, rotation = link.poll()

            if state != state_prev:
                say(state_message(state, link.serial))
                state_prev = state
                last_notice = now
                if state == 'ok':
                    send_sequence()  # the plugin may have been loaded after the script started
            elif state in ('no_steamvr', 'no_tracker') and now - last_notice >= RETRY_NOTICE_SECONDS:
                say("still " + state_message(state, link.serial))
                last_notice = now

            if state == 'ok':
                # a new SteamVR session or a different tracker invalidates the calibration
                if mapper.calibrated and calibration_key != (link.generation, link.serial):
                    mapper.reset()
                if valid_since is None:
                    valid_since = now
                if not mapper.calibrated and now - valid_since >= SETTLE_SECONDS:
                    recenter_pending = True
                if recenter_pending:
                    try:
                        mapper.recenter(rotation)
                        calibration_key = (link.generation, link.serial)
                        recenter_pending = False
                        recenter_manual = False
                        say("recentered: heading %.1f deg in the tracking space, gravity in tracker axes %s"
                            % (mapper.heading0, format_vec(mapper.up_tracker)))
                        send_sequence()
                    except ValueError as error:
                        if recenter_manual:
                            # a key press fails once and is dropped; the old calibration (if any) stays
                            recenter_pending = False
                            recenter_manual = False
                            say("WARNING: cannot recenter: %s" % error)
                        elif now - last_warning >= 2.0:
                            # automatic recenter keeps trying until the pose allows it, nothing is sent meanwhile
                            say("WARNING: waiting to recenter: %s" % error)
                            last_warning = now
                if mapper.calibrated:
                    last_ypr = mapper.scene_ypr(rotation)
                    client.send_message(ypr_address, [float(v) for v in last_ypr])
            else:
                valid_since = None

            # compact status line
            interval = STATUS_INTERVAL_TTY if tty else STATUS_INTERVAL_PIPE
            if now - last_status >= interval:
                last_status = now
                if last_ypr is not None and state == 'ok':
                    line = "sent yaw %+7.2f  pitch %+7.2f  roll %+7.2f   [r]ecenter [q]uit" % last_ypr
                else:
                    line = "not sending (%s)   [r]ecenter [q]uit" % state
                if tty:
                    out.write('\r' + line.ljust(100)[:100])
                else:
                    out.write(line + '\n')
                out.flush()

            next_tick += period
            delay = next_tick - clock()
            if delay > 0:
                sleep(delay)
            elif delay < -period:
                next_tick = clock()  # more than a tick behind: skip ahead instead of bursting
    except KeyboardInterrupt:
        pass
    finally:
        if tty:
            out.write('\n')
        out.write("stopped\n")
        out.flush()
        link.close()


def state_message(state, serial):
    if state == 'no_steamvr':
        return "waiting for SteamVR (retrying)..."
    if state == 'no_tracker':
        return "waiting for a tracker (SteamVR is running, retrying)..."
    if state == 'lost':
        return "tracker %s: pose not valid, not sending" % serial
    return "tracker %s: tracking" % serial


# ======================================================================================
# Original mode: send all tracked devices as /<type>/<n> [x y z yaw pitch roll]
# ======================================================================================

def run_legacy(args):
    print(Back.CYAN + Fore.WHITE + Style.BRIGHT +
    """                            \n      OpenVR OSC 1.0        \n                            \n"""
     + Style.RESET_ALL)

    # Initialize Tria's OpenVR wrapper and print discovered objects
    v = triad_openvr.triad_openvr()
    print(Style.DIM)
    v.print_discovered_objects()
    print(Style.RESET_ALL)

    # Sort through all discovered devices and keep track by type
    deviceCount = 0
    devices = {
        'tracker': [],
        'hmd': [],
        'controller': [],
        'tracking reference': []
    }

    for deviceName, device in v.devices.items():
        device._id = deviceName.split("_").pop()
        devices[device.device_class.lower()].append(device)
        deviceCount += 1

    # pose tracking interval
    interval = 1/250

    # initialize OSC client
    client = udp_client.SimpleUDPClient(args.ip, args.port)

    # print some stuff
    print(Fore.GREEN + "\rSending OSC tracking data on " + args.ip + ":" + str(args.port), end="\n\n")
    print(Fore.YELLOW + '{0: <13}'.format("OSC address") + '{0: <9}'.format("X") + '{0: <9}'.format("Y") + '{0: <9}'.format("Z") + '{0: <9}'.format("Yaw") + '{0: <9}'.format("Pitch") + '{0: <9}'.format("Roll"))

    with output(output_type="list", initial_len=5, interval=0) as output_list:

        while(True):
            start = time.time()

            # Initialize OSC bundle for all tracked controllers
            bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)

            # iterate over tracked device types and build OSC messages
            di = 0
            for deviceType in args.track:
                for device in devices[deviceType]:
                    # get device post
                    pose = device.get_pose_euler()

                    # Build message and add to bundle
                    msg = osc_message_builder.OscMessageBuilder(address="/" + deviceType + "/" + device._id)
                    msg.add_arg(device.get_pose_euler())
                    bundle.add_content(msg.build())

                    ### report device pose in the console
                    txt = Fore.CYAN + '{0: <13}'.format(deviceType + device._id) + Fore.WHITE + Style.BRIGHT
                    for each in pose:
                        txt += '{0: <8}'.format("%.4f" % each)
                        txt += " "
                    output_list[di] = txt
                    di += 1

            # Send the bundle
            client.send(bundle.build())

            # wait for next tick
            sleep_time = interval-(time.time()-start)
            if sleep_time>0:
                time.sleep(sleep_time)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Send OpenVR tracking data over OSC. Default mode: all devices as /<type>/<n>. "
                    "With --scenerotator: head tracking for IEM SceneRotator from one tracker.")
    parser.add_argument("--ip", default="127.0.0.1", help="ip of the OSC server")
    parser.add_argument("--port", type=int, default=None,
                        help="port the OSC server is listening on (default 7000, or 9000 with --scenerotator)")
    parser.add_argument("--track", nargs="*", default=["hmd", "tracker", "controller"], help="devices to track (hmd, tracker, controller)")
    parser.add_argument("--freq", type=int, default=250, help="tracking frequency (in ms)")
    parser.add_argument("--mode", choices=['euler', 'quaternion'], default="euler", help="get pose data in euler angles or quaternions")

    group = parser.add_argument_group("SceneRotator mode")
    group.add_argument("--scenerotator", action="store_true",
                       help="send head-tracking rotation for IEM SceneRotator from one tracker")
    group.add_argument("--tracker-serial", default=None, metavar="SERIAL",
                       help="use the tracker with this serial number (default: first tracker found)")
    group.add_argument("--front", default=DEFAULT_FRONT, choices=sorted(FRONT_AXES), metavar="{+x,-x,+y,-y,+z,-z}",
                       help="tracker axis (OpenVR device frame) that points to the front of the head; "
                            "write negative values as --front=-x (default -y: the LED side of a Vive "
                            "Tracker 3.0, the wide edge opposite the pogo-pin/USB end, points forward)")
    group.add_argument("--prefix", default="/SceneRotator/", help="OSC address prefix (default /SceneRotator/)")
    group.add_argument("--rate", type=int, default=100, help="messages per second (default 100)")
    group.add_argument("--no-rotation-sequence", action="store_true",
                       help="do not send <prefix>rotationSequence 0 (yaw->pitch->roll) at start and on recenter")
    group.add_argument("--duration", type=float, default=0, metavar="SECONDS",
                       help="exit after this many seconds (default: run until q / Ctrl+C)")
    args = parser.parse_args(argv)
    if args.port is None:
        args.port = 9000 if args.scenerotator else 7000
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.scenerotator:
        run_scenerotator(args)
    else:
        run_legacy(args)


if __name__ == "__main__":
    main()
