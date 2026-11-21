# Credits

The bridge in this folder builds on two open-source projects:

- **OpenVR-OSC** by BarakChamo (made at ITP NYU): https://github.com/BarakChamo/OpenVR-OSC .
  `openvr-osc.py` started as a copy of that project (taken at its `master`, commit f0342c9). The
  original device-to-OSC loop is kept as the default mode (`run_legacy`); the head-tracking mode
  for IEM SceneRotator (`--scenerotator`) and the argument handling were added here.
- **triad_openvr** by Triad Semiconductor: https://github.com/TriadSemi/triad_openvr .
  `triad_openvr\triad_openvr.py` is that file at upstream commit
  `1f705800cfac01058fc4e00e3b81bb7cd341562b`, with one change: values returned by pyopenvr 2.x
  `getStringTrackedDeviceProperty` are `str`, so the `.decode('utf-8')` calls were replaced by a
  helper that decodes only `bytes`.
- Both rely on [pyopenvr](https://github.com/cmbruns/pyopenvr) by cmbruns and on python-osc.

Neither upstream repository contained a license file at the commits used here. Check with the
authors before redistributing this code publicly.
