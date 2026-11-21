"""Self-test for the SceneRotator mode of bridge/openvr-osc.py (math, state machine, arguments).
No SteamVR and no network needed; it imports the bridge from ..\\bridge relative to this file.
Run from anywhere: python -B -I tests\\test_scenerotator.py   (exit code 0 = all passed)"""
import importlib.util
import io
import math
import os
import random
import sys

BRIDGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "bridge")
BRIDGE = os.path.normpath(BRIDGE)
sys.path.insert(0, BRIDGE)
spec = importlib.util.spec_from_file_location("openvr_osc", os.path.join(BRIDGE, "openvr-osc.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + ((" - " + detail) if detail else ""))
    if not ok:
        failures.append(name)


def plugin_matrix_sequence0(yaw_deg, pitch_deg, roll_deg):
    """Transcription of IEM SceneRotator calcRotationMatrix, rotationSequence < 0.5 branch."""
    a, b, c = (math.radians(v) for v in (yaw_deg, pitch_deg, roll_deg))
    ca, cb, cy = math.cos(a), math.cos(b), math.cos(c)
    sa, sb, sy = math.sin(a), math.sin(b), math.sin(c)
    return ((ca * cb, -sa * cb, sb),
            (sa * cy + ca * sb * sy, ca * cy - sa * sb * sy, -cb * sy),
            (sa * sy - ca * sb * cy, ca * sy + sa * sb * cy, cb * cy))


def max_diff(a, b):
    return max(abs(a[r][c] - b[r][c]) for r in range(3) for c in range(3))


C = m.IEM_FROM_OPENVR
CT = m.transpose(C)


def level_mount(front):
    """True head axes in tracker coordinates for a tracker lying top-face-up on the head:
    up = -z_ov (top face is toward -z), front = the chosen tracker axis."""
    f = m.FRONT_AXES[front]
    up = (0.0, 0.0, -1.0) if abs(f[2]) < 0.5 else (0.0, 1.0, 0.0)   # z axes: tracker standing on its apex end
    left = m.cross(up, f)
    return ((f[0], left[0], up[0]), (f[1], left[1], up[1]), (f[2], left[2], up[2]))


def tracker_rotation(head_rel, heading0_deg, mount_true):
    """R_T such that C * R_T * M = Rz(heading0) * head_rel (the inverse of the pipeline)."""
    h_world = m.mat_mul(m.rot_z(heading0_deg), head_rel)
    return m.mat_mul(m.mat_mul(CT, h_world), m.transpose(mount_true))


def head_rotation(yaw, pitch, roll):
    return m.mat_mul(m.mat_mul(m.rot_z(yaw), m.rot_y(pitch)), m.rot_x(roll))


def det(a):
    return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
            - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
            + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))


print("== 1. basic sign checks (default front +y, level mount)")
mount = level_mount('+y')
check("mount is a proper rotation", abs(det(mount) - 1) < 1e-12)
heading0 = 37.0   # arbitrary world heading of the user's front at recenter
mapper = m.HeadMapper('+y')
r0 = tracker_rotation(head_rotation(0, 0, 0), heading0, mount)
check("tracker rotation is proper", abs(det(r0) - 1) < 1e-12)
mapper.recenter(r0)
check("heading recovered", abs(mapper.heading0 - heading0) < 1e-9, "%.9f" % mapper.heading0)
y, p, r = mapper.scene_ypr(r0)
check("recenter pose gives 0/0/0", max(abs(y), abs(p), abs(r)) < 1e-9, "%.2e %.2e %.2e" % (y, p, r))

cases = [
    ("head yaw LEFT 30", head_rotation(30, 0, 0), (-30, 0, 0)),
    ("head yaw RIGHT 30", head_rotation(-30, 0, 0), (30, 0, 0)),
    ("head nose UP 20", head_rotation(0, -20, 0), (0, 20, 0)),
    ("head nose DOWN 20", head_rotation(0, 20, 0), (0, -20, 0)),
    ("head RIGHT ear down 15", head_rotation(0, 0, 15), (0, 0, -15)),
    ("head LEFT ear down 15", head_rotation(0, 0, -15), (0, 0, 15)),
]
for name, hr, expected in cases:
    got = mapper.scene_ypr(tracker_rotation(hr, heading0, mount))
    ok = all(abs(g - e) < 1e-9 for g, e in zip(got, expected))
    check(name + " -> sent %s" % (expected,), ok, "got %.6f %.6f %.6f" % got)

# physical sanity of the sign claims: nose up moves the front axis up, right ear down moves the right ear down
nose_up = m.mat_vec(head_rotation(0, -20, 0), (1, 0, 0))
check("nose-up head rotation raises the front axis", nose_up[2] > 0.3, "z=%.3f" % nose_up[2])
right_ear = m.mat_vec(head_rotation(0, 0, 15), (0, -1, 0))
check("right-ear-down rotation lowers the right ear", right_ear[2] < -0.2, "z=%.3f" % right_ear[2])
yaw_left = m.mat_vec(head_rotation(30, 0, 0), (1, 0, 0))
check("yaw-left rotation moves the front axis toward +y (left)", yaw_left[1] > 0.4, "y=%.3f" % yaw_left[1])

print("== 2. round trip against the plugin's sequence-0 matrix (random rotations)")
random.seed(1)
worst = 0.0
for n in range(5000):
    front = random.choice(sorted(m.FRONT_AXES))
    mt = level_mount(front)
    mp = m.HeadMapper(front)
    h0 = random.uniform(-180, 180)
    mp.recenter(tracker_rotation(head_rotation(0, 0, 0), h0, mt))
    hr = head_rotation(random.uniform(-180, 180), random.uniform(-89, 89), random.uniform(-180, 180))
    y, p, r = mp.scene_ypr(tracker_rotation(hr, h0, mt))
    rebuilt = plugin_matrix_sequence0(y, p, r)
    worst = max(worst, max_diff(rebuilt, m.transpose(hr)))
check("5000 random rotations, all four front axes: max |plugin(sent) - inverse head| < 1e-6",
      worst < 1e-6, "max error %.3e" % worst)

print("== 3. gimbal lock (head pitch exactly +-90)")
for pitch in (90.0, -90.0):
    hr = head_rotation(25, pitch, 40)
    y, p, r = mapper.scene_ypr(tracker_rotation(hr, heading0, mount))
    err = max_diff(plugin_matrix_sequence0(y, p, r), m.transpose(hr))
    check("pitch %+.0f: finite output and round trip" % pitch,
          all(math.isfinite(v) for v in (y, p, r)) and err < 1e-6, "ypr %.2f %.2f %.2f err %.1e" % (y, p, r, err))

print("== 4. tilted mounting (calibrated from gravity at recenter)")
for label, tilt in (("20 deg about the left-right axis", m.rot_y(20)),
                    ("20 deg about the front axis", m.rot_x(20)),
                    ("-20 deg about the left-right axis", m.rot_y(-20))):
    mt = m.mat_mul(level_mount('+y'), tilt)   # tracker tilted relative to the head
    mp = m.HeadMapper('+y')
    mp.recenter(tracker_rotation(head_rotation(0, 0, 0), heading0, mt))
    y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(0, 0, 0), heading0, mt))
    check("tilt %s: 0/0/0 at recenter" % label, max(abs(y), abs(p), abs(r)) < 1e-6, "%.2e %.2e %.2e" % (y, p, r))
    y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(30, 0, 0), heading0, mt))
    check("tilt %s: head yaw-left 30 -> -30/0/0" % label,
          abs(y + 30) < 1e-6 and abs(p) < 1e-6 and abs(r) < 1e-6, "%.6f %.6f %.6f" % (y, p, r))
    y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(0, -20, 0), heading0, mt))
    check("tilt %s: head nose-up 20 -> 0/+20/0" % label,
          abs(y) < 1e-6 and abs(p - 20) < 1e-6 and abs(r) < 1e-6, "%.6f %.6f %.6f" % (y, p, r))
mt = m.mat_mul(level_mount('+y'), m.mat_mul(m.rot_y(20), m.rot_x(20)))
mp = m.HeadMapper('+y')
mp.recenter(tracker_rotation(head_rotation(0, 0, 0), heading0, mt))
y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(0, 0, 0), heading0, mt))
check("combined tilt: 0/0/0 at recenter (by construction)", max(abs(y), abs(p), abs(r)) < 1e-6)
y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(30, 0, 0), heading0, mt))
print("INFO  combined 20 deg (left-right axis) + 20 deg (front axis) tilt, head yaw-left 30 -> %.3f %.3f %.3f "
      "(yaw about gravity is exact whatever the mount)" % (y, p, r))
y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(0, -20, 0), heading0, mt))
print("INFO  same mount, head nose-up 20 (expected 0 +20 0) -> %.3f %.3f %.3f "
      "(pitch/roll are exact only if the tracker's front axis lies in the head's front/up plane; "
      "otherwise the horizontal front direction is off by the residual yaw of the mount)" % (y, p, r))

print("== 5. recenter semantics")
mp = m.HeadMapper('+y')
mt = level_mount('+y')
mp.recenter(tracker_rotation(head_rotation(0, 0, 0), 10.0, mt))
# user turns 50 deg left, recenters there: yaw becomes the new zero, pitch/roll stay gravity-referenced
mp.recenter(tracker_rotation(head_rotation(50, 0, 0), 10.0, mt))
y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(50, 0, 0), 10.0, mt))
check("recentering while turned 50 deg left gives 0/0/0", max(abs(y), abs(p), abs(r)) < 1e-9)
y, p, r = mp.scene_ypr(tracker_rotation(head_rotation(80, 0, 0), 10.0, mt))
check("30 deg further left -> -30", abs(y + 30) < 1e-9)
try:
    m.HeadMapper('up')
    check("unknown front axis is refused", False, "no error")
except ValueError:
    check("unknown front axis is refused", True)
check("all six axes are accepted", all(m.HeadMapper(a) for a in ('+x', '-x', '+y', '-y', '+z', '-z')))
bad = m.HeadMapper('+y')
bad.recenter(tracker_rotation(head_rotation(0, 0, 0), 10.0, level_mount('+y')))
old_mount, old_heading = bad.mount, bad.heading0
try:
    # tracker +y axis (the front axis) pointing straight up in the world: rotation about x by +90
    # sends device +y to world +z_ov; we need device +y -> world +y_ov, i.e. identity
    bad.recenter(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
    check("vertical front axis raises ValueError", False, "no error")
except ValueError as e:
    check("vertical front axis raises ValueError", True, str(e)[:90])
check("failed recenter keeps the previous calibration", bad.mount == old_mount and bad.heading0 == old_heading)

print("== 5b. front axis close to gravity")


def r_with_front_angle(front, angle_from_vertical_deg):
    """Tracker rotation (about the world x axis) whose given front axis is closest to the wanted angle from vertical."""
    best = None
    for a in range(0, 360):
        r = m.rot_x(a)   # columns = device axes in tracking space
        axis = m.mat_vec(r, m.FRONT_AXES[front])
        ang = math.degrees(math.acos(max(-1, min(1, abs(axis[1])))))
        if best is None or abs(ang - angle_from_vertical_deg) < best[0]:
            best = (abs(ang - angle_from_vertical_deg), r, ang)
    return best[1], best[2]


for ang_wanted, expect_ok in ((5, False), (15, False), (29, False), (31, True), (45, True), (80, True)):
    r, ang = r_with_front_angle('-y', ang_wanted)
    mp = m.HeadMapper('-y')
    try:
        mp.recenter(r)
        ok, msg = True, "accepted"
    except ValueError as e:
        ok, msg = False, str(e)
    check("front axis %.0f deg from vertical -> %s" % (ang, "accepted" if expect_ok else "refused"), ok == expect_ok, msg[:90])
    if not expect_ok:
        check("  refusal leaves the mapper uncalibrated; message names the angle and gravity",
              (not mp.calibrated) and ("deg from vertical" in msg) and ("gravity is (" in msg))
r, ang = r_with_front_angle('-y', 15)
try:
    m.HeadMapper('-y').recenter(r)
except ValueError as e:
    print("INFO  example warning text: " + str(e))

print("== 6. run_scenerotator state machine (fake link, fake client, fake clock)")


class FakeClient:
    def __init__(self, clock=None):
        self.sent = []
        self.times = []
        self.clock = clock

    def send_message(self, address, value):
        self.sent.append((address, value))
        self.times.append(self.clock() if self.clock else 0.0)


class FakeLink:
    """Yields scripted (state, rotation) pairs, one per poll; repeats the last one."""

    def __init__(self, script):
        self.script = list(script)
        self.generation = 1
        self.serial = "LHR-TEST"
        self.closed = False

    def poll(self):
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if callable(item):
            item = item(self)
        return item

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


class Args:
    front = '+y'
    tracker_serial = None
    ip = '127.0.0.1'
    port = 9000
    prefix = '/SceneRotator/'
    rate = 100
    no_rotation_sequence = False
    duration = 0


def run(script, keys=(), duration=10.0, args=None, link=None):
    global last_client
    clock = Clock()
    client = FakeClient(clock)
    last_client = client
    link = link or FakeLink(script)
    key_list = list(keys)   # (time, key)

    def reader():
        if key_list and clock.t >= key_list[0][0]:
            return key_list.pop(0)[1]
        return None
    a = args or Args()
    a.duration = duration
    out = io.StringIO()
    m.run_scenerotator(a, key_reader=reader, link=link, client=client, clock=clock, sleep=clock.sleep, out=out)
    return client.sent, out.getvalue(), link


ypr_msgs = lambda sent: [v for a, v in sent if a == '/SceneRotator/ypr']
seq_msgs = lambda sent: [v for a, v in sent if a == '/SceneRotator/rotationSequence']

R_ok = tracker_rotation(head_rotation(0, 0, 0), 20.0, level_mount('+y'))
R_left = tracker_rotation(head_rotation(30, 0, 0), 20.0, level_mount('+y'))

sent, text, _ = run([('ok', R_ok)], duration=2.0)
check("rotationSequence 0.0 sent first, as float", sent[0] == ('/SceneRotator/rotationSequence', 0.0) and isinstance(sent[0][1], float))
first_ypr_t = None
n_ypr = len(ypr_msgs(sent))
check("auto recenter after settle; ~100 Hz afterwards", 140 < n_ypr < 160, "%d messages in 2 s (0.5 s settle)" % n_ypr)
check("ypr args are three plain floats", all(isinstance(v, list) and len(v) == 3 and all(type(x) is float for x in v) for v in ypr_msgs(sent)))
check("stationary tracker -> 0/0/0", all(max(abs(x) for x in v) < 1e-9 for v in ypr_msgs(sent)))

sent, text, _ = run([('ok', R_ok)] * 1, duration=3.0, keys=[(1.5, 'q')])
check("q quits the loop early", len(ypr_msgs(sent)) < 120 and 'stopped' in text, "%d ypr messages" % len(ypr_msgs(sent)))

# recenter key: the tracker is 30 deg left from t=1.0 on; before the key the output is -30, after it 0
seq = [('ok', R_ok)] * 100 + [('ok', R_left)]
sent, text, _ = run(seq, duration=3.0, keys=[(2.0, 'r')])
vals = ypr_msgs(sent)
check("before 'r': head yaw-left 30 -> -30", any(abs(v[0] + 30) < 1e-6 for v in vals))
check("after 'r': back to 0/0/0", max(abs(x) for x in vals[-1]) < 1e-9, "last %s" % vals[-1])
check("'r' re-sends rotationSequence", len(seq_msgs(sent)) >= 3, "%d rotationSequence messages" % len(seq_msgs(sent)))

# tracker missing at the start, then appears; SteamVR missing first
script = [('no_steamvr', None)] * 100 + [('no_tracker', None)] * 100 + [('lost', None)] * 20 + [('ok', R_ok)]
sent, text, _ = run(script, duration=6.0)
first_ypr = min(t for (a, v), t in zip(sent, last_client.times) if a == '/SceneRotator/ypr')
before = [a for (a, v), t in zip(sent, last_client.times) if t < 2.2]
check("only rotationSequence is sent while SteamVR/tracker are missing or the pose is invalid (t < 2.2 s)",
      all(a == '/SceneRotator/rotationSequence' for a in before) and before, "%d message(s) before t=2.2 s" % len(before))
check("ypr starts after the pose is valid for the 0.5 s settle time", 2.65 < first_ypr < 2.8, "first ypr at t=%.2f s" % first_ypr)
check("retry messages printed", "waiting for SteamVR" in text and "waiting for a tracker" in text and "pose not valid" in text,
      " | ".join(l for l in text.splitlines() if 'wait' in l or 'valid' in l or 'tracking' in l)[:200])

# no ypr at all while invalid
sent, text, _ = run([('lost', None)], duration=3.0)
check("no ypr while the pose is invalid", len(ypr_msgs(sent)) == 0)

# tracker disappears and comes back: calibration kept, output continues
script = [('ok', R_ok)] * 100 + [('no_tracker', None)] * 50 + [('ok', R_left)] * 300
sent, text, _ = run(script, duration=5.0)
vals = ypr_msgs(sent)
check("after a dropout the old calibration is kept (yaw-left 30 -> -30)", abs(vals[-1][0] + 30) < 1e-6, "last %s" % vals[-1])

# new SteamVR session (generation++) forces a new recenter
def new_session(link):
    link.generation += 1
    return ('ok', R_left)


script = [('ok', R_ok)] * 100 + [new_session] + [('ok', R_left)] * 300
sent, text, _ = run(script, duration=5.0)
vals = ypr_msgs(sent)
check("new SteamVR session recenters again (0/0/0 with the new pose)", max(abs(x) for x in vals[-1]) < 1e-9, "last %s" % vals[-1])

# --no-rotation-sequence
a = Args()
a.no_rotation_sequence = True
sent, text, _ = run([('ok', R_ok)], duration=1.0, args=a)
check("--no-rotation-sequence sends none", len(seq_msgs(sent)) == 0)

# custom prefix without trailing slash
a = Args()
a.prefix = '/Other'
sent, text, _ = run([('ok', R_ok)], duration=1.0, args=a)
check("custom prefix", any(addr == '/Other/ypr' for addr, v in sent) and any(addr == '/Other/rotationSequence' for addr, v in sent))

# front axis nearly vertical: warning, nothing sent (auto), then recovers when the pose allows it
a = Args()
a.front = '-y'
R_bad, ang_bad = r_with_front_angle('-y', 10)
R_good, ang_good = r_with_front_angle('-y', 80)
script = [('ok', R_bad)] * 400 + [('ok', R_good)]
sent, text, _ = run(script, duration=8.0, args=a)
warn_lines = [l for l in text.splitlines() if 'WARNING' in l]
first_ypr = min(t for (ad, v), t in zip(sent, last_client.times) if ad == '/SceneRotator/ypr')
check("auto recenter with the front axis %.0f deg from vertical: warns, sends no ypr while it lasts" % ang_bad,
      len(warn_lines) >= 1 and first_ypr >= 3.99,"%d warning(s), first ypr at t=%.2f s" % (len(warn_lines), first_ypr))
check("  warnings are throttled (<= 1 per 2 s) and say what to do",
      len(warn_lines) <= 4 and "least 30 deg from vertical" in warn_lines[0], warn_lines[0][:120])
check("  once the pose allows it the mapper calibrates and sends 0/0/0", max(abs(x) for x in ypr_msgs(sent)[-1]) < 1e-9)

# manual recenter fails while the old calibration stays in use
a = Args()
a.front = '-y'
script = [('ok', R_good)] * 150 + [('ok', R_bad)] * 300
sent, text, _ = run(script, duration=5.0, args=a, keys=[(3.0, 'r')])
warn_lines = [l for l in text.splitlines() if 'WARNING' in l]
check("manual 'r' with a bad front axis: one warning, old calibration keeps being used",
      len(warn_lines) == 1 and "cannot recenter" in warn_lines[0] and len(ypr_msgs(sent)) > 400,
      "%d warning(s); %d ypr messages" % (len(warn_lines), len(ypr_msgs(sent))))

print("== 7. argument parsing")
check("legacy defaults (port 7000)", m.parse_args([]).port == 7000 and not m.parse_args([]).scenerotator)
ns = m.parse_args(['--scenerotator'])
check("scenerotator defaults (port 9000, prefix, front -y, rate 100)",
      (ns.port, ns.prefix, ns.front, ns.rate) == (9000, '/SceneRotator/', '-y', 100))
check("--front=-x", m.parse_args(['--scenerotator', '--front=-x']).front == '-x')
check("--front=+z / --front=-z", m.parse_args(['--scenerotator', '--front=+z']).front == '+z'
      and m.parse_args(['--scenerotator', '--front=-z']).front == '-z')
check("--port overrides", m.parse_args(['--scenerotator', '--port', '9100']).port == 9100)

print()
print("FAILED: %s" % failures if failures else "ALL TESTS PASSED")
sys.exit(1 if failures else 0)
