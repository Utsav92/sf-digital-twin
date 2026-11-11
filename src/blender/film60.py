"""60-second / 1,800-frame / 30 fps audio-reactive film, driven from render_city.py (--anim cine_both --film60).

Deterministic timeline: output frame k (1..1800) is time t=(k-1)/30 s. A segment table maps t onto time tau of the
existing 3-minute camera rigs (cine_drone_cam / cine_car_cam, keyed at 24 fps), so no rig is rebuilt or re-keyed.
Audio-reactive parameters are a pure function of data/film60/features.json (precomputed from the soundtrack), computed
for ALL frames up front, so rendering any sub-range (resume, test frames) gives identical pixels to a full run.

Reactive channels in this MVP (what is actually wired):
  sf_night   (window glow + lamp heads + car lights, via the SF_Globals shader group)  <- storyboard curve + bass + beat pulse
  sf_wetness (reflective roads from 10 s)                                             <- storyboard curve
  exposure   (darkens toward the climax so the glow reads)                            <- storyboard curve
NOT yet wired (needs new Blender shader/particle work): facade pattern animation (mid), particle sparks (treble),
geometry deformation (bass), Gaussian-splat / point-cloud transition (30-40 s), simulated traffic."""
import json
import math
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
FPS, NF, RIG_FPS = 30, 1800, 24

# (t0, t1, rig, tau0, tau1)  tau = seconds on the 180 s rig timeline
SEGMENTS = [
    (0, 10, "drone", 0, 25),      # aerial establishing: waterfront approach / rise
    (10, 20, "drone", 30, 60),    # descending orbit into the financial district
    (20, 30, "car", 40, 60),      # street drive (chase cam on the hero car), 2x
    (30, 40, "drone", 95, 120),   # Market St canyon flight (point-cloud transform is Phase 2)
    (40, 50, "drone", 120, 144),  # climax: canyon flight, max glow
    (50, 60, "drone", 148, 180),  # pull-back and climb over the bay, skyline reveal
]
CAM_NAME = {"drone": "cine_drone_cam", "car": "cine_car_cam"}
# storyboard curves: (t, value) piecewise linear
NIGHT = [(0, 0.10), (10, 0.25), (20, 0.45), (30, 0.55), (40, 0.80), (50, 0.90), (60, 0.50)]
WET = [(0, 0.0), (10, 0.0), (20, 0.55), (60, 0.55)]
EXPO = [(0, -0.3), (20, -0.45), (40, -0.75), (50, -0.8), (60, -0.4)]


def curve(pts, t):
    if t <= pts[0][0]:
        return pts[0][1]
    for (a, va), (b, vb) in zip(pts, pts[1:]):
        if t <= b:
            return va + (vb - va) * (t - a) / (b - a)
    return pts[-1][1]


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def segment_for(t):
    for s in SEGMENTS:
        if t < s[1]:
            return s
    return SEGMENTS[-1]


def camera_time(t):
    """Output time t (s) -> (rig, scene frame float on the 24 fps rig timeline)."""
    t0, t1, rig, a, b = segment_for(t)
    tau = a + (b - a) * min(1.0, (t - t0) / (t1 - t0))
    return rig, tau * RIG_FPS + 1


def reactive_timeline(features_path):
    """Per-frame reactive params for all 1,800 frames (sequential smoothing, so computed once, in order)."""
    d = json.loads(Path(features_path).read_text())
    rows = d["features"]
    assert len(rows) == NF and abs(d["fps"] - FPS) < 1e-9, f"features.json must have {NF} frames @ {FPS} fps"
    dt = 1.0 / FPS
    bass_s, pulse = 0.0, 0.0
    out = []
    for k, f in enumerate(rows):
        t = k * dt
        tau = 0.03 if f["bass"] > bass_s else 0.25  # fast attack, slow release: no strobing
        bass_s += (f["bass"] - bass_s) * (1 - math.exp(-dt / tau))
        pulse = max(pulse, f["beatStrength"]) if f["beat"] else pulse * math.exp(-dt / 0.18)
        base = curve(NIGHT, t)
        night = min(1.0, base + 0.30 * bass_s * (0.5 + base) + 0.18 * pulse)
        out.append({"t": t, "night": night, "wet": curve(WET, t), "exposure": curve(EXPO, t),
                    "bass": bass_s, "pulse": pulse})
    return out


def apply_frame(scn, p, cams):
    scn["sf_night"] = float(p["night"])
    scn["sf_wetness"] = float(p["wet"])
    scn.view_settings.exposure = float(p["exposure"])


def run(scn, a, render_png, res, out):
    import time as _t
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d  # noqa: E731
    fa, fb = (int(v) for v in opt("--frames", f"1-{NF}").split("-"))
    assert 1 <= fa <= fb <= NF
    feats = opt("--features", str(ROOT / "data/film60/features.json"))
    timeline = reactive_timeline(feats)
    cams = {k: bpy.data.objects[v] for k, v in CAM_NAME.items()}
    scn.render.fps, scn.render.fps_base = FPS, 1.0
    fdir = Path(out).with_suffix("")
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "timeline.json").write_text(json.dumps({"fps": FPS, "frames": NF, "segments": SEGMENTS, "params": timeline}))
    t0 = _t.time()
    for fr in range(fa, fb + 1):
        fp = fdir / f"frame_{fr:04d}.png"
        if fp.exists() and "--force" not in a:
            continue
        t = (fr - 1) / FPS
        rig, f = camera_time(t)
        scn.camera = cams[rig]
        fi = int(math.floor(f))
        scn.frame_set(fi, subframe=f - fi)
        apply_frame(scn, timeline[fr - 1], cams)
        render_png(fp, res)
        print(f"FRAME {fr}/{fb} t={t:.2f}s rig={rig} night={timeline[fr - 1]['night']:.2f} {_t.time() - t0:.0f}s", flush=True)
    print(f"RENDER {fdir} frames {fa}-{fb} time={_t.time() - t0:.1f}s", flush=True)
