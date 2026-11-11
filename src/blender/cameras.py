"""Camera rigs (Phase 10): full-city aerials (N/E/S/W), a neighbourhood fly-through on a keyframed path,
and street-level cameras. City frame (origin Ferry Building), metres. Runs inside Blender."""
import math

import bpy
import numpy as np
from mathutils import Vector

CITY_CENTER = Vector((-4500, -3500, 80))
FLY_WAYPOINTS = [  # (x, y, z) camera, (x, y, z) look-at ; Ocean Beach -> GG Park -> Twin Peaks -> Mission -> FiDi
    ((-11600, -3200, 160), (-8500, -3250, 20)),
    ((-8000, -3500, 140), (-5500, -3300, 40)),
    ((-5600, -4300, 360), (-3000, -3000, 60)),
    ((-3000, -4300, 160), (-1200, -1500, 80)),
    ((-1700, -1800, 260), (-300, -500, 150)),
    ((-300, -2200, 200), (200, 600, 40)),
]
STREET = {  # name: (eye xyz, look-at xyz)
    "street_market_st": ((-1040, -795, 7.0), (-200, -50, 20.0)),
    "street_lombard": ((-2230, 650, 75.0), (-2236, 714, 60.0)),
    "street_embarcadero": ((300, -1200, 8.0), (0, 0, 15.0)),
}


def _cam(name, coll, loc, target, lens=35):
    c = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    coll.objects.link(c)
    c.location = Vector(loc)
    c.data.lens = lens
    c.data.clip_start, c.data.clip_end = 0.5, 60000
    d = Vector(target) - c.location
    c.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return c


def add_rigs(scn, fps=24, seconds=40):
    coll = bpy.data.collections.get("Cameras") or bpy.data.collections.new("Cameras")
    if coll.name not in scn.collection.children:
        scn.collection.children.link(coll)
    rigs = {}
    for name, az in (("aerial_N", 0), ("aerial_E", 90), ("aerial_S", 180), ("aerial_W", 270)):
        a = math.radians(az)
        loc = CITY_CENTER + Vector((math.sin(a), math.cos(a), 0)) * 11000 + Vector((0, 0, 6500))
        rigs[name] = _cam(name, coll, loc, CITY_CENTER, lens=30)
    # fly-through: camera + look-at empty, keyed at waypoints with smooth interpolation
    cam = _cam("flythrough", coll, FLY_WAYPOINTS[0][0], FLY_WAYPOINTS[0][1], lens=28)
    tgt = bpy.data.objects.new("flythrough_target", None)
    coll.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    n = len(FLY_WAYPOINTS)
    for i, (p, t) in enumerate(FLY_WAYPOINTS):
        f = 1 + round(i * (seconds * fps - 1) / (n - 1))
        cam.location, tgt.location = p, t
        cam.keyframe_insert("location", frame=f)
        tgt.keyframe_insert("location", frame=f)
    scn.frame_start, scn.frame_end, scn.render.fps = 1, seconds * fps, fps
    rigs["flythrough"] = cam
    for name, (p, t) in STREET.items():
        rigs[name] = _cam(name, coll, p, t, lens=24)
    return rigs


# ----------------------------------------------------------------------------- motion rigs (drone / drive)
# Market St corridor (city frame, metres): Van Ness end -> Ferry Building. Paths follow it; z comes from the scene.
MARKET = ((-960.0, -958.0), (-120.0, -95.0))


def ground_z(scn, x, y, prefer=("roads_", "terrain_")):
    """Height of the road/terrain surface under (x, y): ray down, skipping roofs, trees, cars and awnings."""
    import bpy as _b
    deps = _b.context.evaluated_depsgraph_get()
    z0 = 900.0
    for _ in range(12):
        hit, loc, _n, _i, ob, _m = scn.ray_cast(deps, Vector((x, y, z0)), Vector((0, 0, -1)))
        if not hit:
            return 0.0
        nm = ob.name if ob else ""
        if nm.startswith(prefer) or (ob and ob.get("layer") in ("roads", "terrain")):
            return loc.z
        z0 = loc.z - 0.05
    return 0.0


def _catmull(P, n):
    P = np.asarray(P, float)
    P = np.vstack([P[0], P, P[-1]])
    out = []
    for i in range(1, len(P) - 2):
        for t in np.linspace(0, 1, max(2, n // (len(P) - 3)), endpoint=False):
            out.append(0.5 * ((2 * P[i]) + (-P[i - 1] + P[i + 1]) * t + (2 * P[i - 1] - 5 * P[i] + 4 * P[i + 1] - P[i + 2]) * t * t
                              + (-P[i - 1] + 3 * P[i] - 3 * P[i + 1] + P[i + 2]) * t ** 3))
    out.append(P[-2])
    return np.array(out)


def add_motion_rig(scn, kind, seconds=12.0, fps=24, lens=None, drive_lane=2.6):
    """'drive' = first-person hood camera 1.5 m up, driving down the right lane of Market St (GTA-style chase
    framing slightly ahead); 'drone' = smooth fly-in that climbs from 40 m to 150 m along the same corridor and
    sweeps right over the waterfront. Keys every 0.25 s, linear interpolation over a Catmull-Rom path."""
    (x0, y0), (x1, y1) = MARKET
    d = np.array([x1 - x0, y1 - y0])
    L = np.linalg.norm(d)
    d /= L
    right = np.array([d[1], -d[0]])
    n_keys = int(seconds * 4) + 1
    if kind == "drive":
        wp = [np.array([x0, y0]) + d * L * t + right * drive_lane for t in np.linspace(0.02, 0.95, 14)]
        path = _catmull(wp, n_keys + 20)
        idx = np.linspace(0, len(path) - 1, n_keys)
        xy = np.array([np.interp(idx, np.arange(len(path)), path[:, k]) for k in (0, 1)]).T
        z = np.array([ground_z(scn, *p) for p in xy])
        eye = np.c_[xy, z + 1.55]
        ahead = np.vstack([eye[min(i + 6, n_keys - 1)] for i in range(n_keys)])
        look = ahead + np.array([0, 0, 0.3])
        ahead_xy = ahead[:, :2]
        look[-6:, :2] = eye[-1, :2] + d * (np.arange(1, 7)[:, None] * 6.0)
    else:
        hs = [40, 46, 55, 70, 95, 130, 150]
        wp = []
        for t, hgt in zip(np.linspace(0.0, 0.9, len(hs)), hs):
            p = np.array([x0, y0]) + d * L * t + right * (t ** 2 * 120.0)
            wp.append((p, hgt))
        path = _catmull([np.r_[p, h] for p, h in wp], n_keys + 20)
        idx = np.linspace(0, len(path) - 1, n_keys)
        xyz = np.array([np.interp(idx, np.arange(len(path)), path[:, k]) for k in range(3)]).T
        zg = np.array([ground_z(scn, *p[:2]) for p in xyz])
        eye = np.c_[xyz[:, :2], zg + xyz[:, 2]]
        look = np.vstack([np.r_[eye[min(i + 8, n_keys - 1), :2] + d * 140.0 + right * 20.0,
                               ground_z(scn, *(eye[min(i + 8, n_keys - 1), :2] + d * 140.0)) + 18.0]
                          for i in range(n_keys)])
    coll = bpy.data.collections.get("Cameras") or bpy.data.collections.new("Cameras")
    if coll.name not in scn.collection.children:
        scn.collection.children.link(coll)
    cam = _cam(f"{kind}_cam", coll, eye[0], look[0], lens=lens or (24 if kind == "drive" else 28))
    tgt = bpy.data.objects.new(f"{kind}_target", None)
    coll.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    nf = int(seconds * fps)
    for i in range(n_keys):
        f = 1 + round(i * (nf - 1) / (n_keys - 1))
        cam.location, tgt.location = eye[i], look[i]
        cam.keyframe_insert("location", frame=f)
        tgt.keyframe_insert("location", frame=f)
    for ob in (cam, tgt):
        for fc in ob.animation_data.action.fcurves if hasattr(ob.animation_data.action, "fcurves") else []:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
    scn.frame_start, scn.frame_end, scn.render.fps = 1, nf, fps
    return cam


# ----------------------------------------------------------------------------- cinematic rigs (3-minute film)
def _gauss(a, sigma):
    a = np.asarray(a, float)
    if sigma <= 0:
        return a
    k = np.exp(-0.5 * (np.arange(-int(4 * sigma), int(4 * sigma) + 1) / sigma) ** 2)
    k /= k.sum()
    pad = len(k) // 2
    ap = np.pad(a, [(pad, pad)] + [(0, 0)] * (a.ndim - 1), mode="edge")
    return np.stack([np.convolve(ap[:, c], k, mode="valid") for c in range(a.shape[1])], 1) if a.ndim > 1 \
        else np.convolve(ap, k, mode="valid")


def _key(ob, pts, frames, rot=None):
    for p, f in zip(pts, frames):
        ob.location = p
        ob.keyframe_insert("location", frame=int(f))
        if rot is not None:
            ob.rotation_euler = rot[int(np.where(frames == f)[0][0])]
            ob.keyframe_insert("rotation_euler", frame=int(f))
    act = ob.animation_data.action
    for fc in getattr(act, "fcurves", []):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def _route():
    import json
    from pathlib import Path
    r = json.loads((Path(__file__).resolve().parents[2] / "data/processed/hero_route.json").read_text())
    return np.array(r["xy"], float)


def build_hero_car(scn, name="hero_car", paint="car_paint_5"):
    import props_instancing as pi
    import materials
    me = bpy.data.meshes.new(name)
    import bmesh as _bm
    bm = _bm.new()
    pi.car(4.8, 1.9, 1.05, 0.5, 2.6, -0.25, paint=paint)(bm)
    bm.to_mesh(me)
    bm.free()
    for n in materials.SLOTS["props"]:
        me.materials.append(materials.get_mat(n))
    ob = bpy.data.objects.new(name, me)
    scn.collection.objects.link(ob)
    return ob


def add_cine_car(scn, seconds=180.0, fps=24, speed_profile=True):
    """Hero car drives the whole hero route (3rd-person chase camera 8 m behind / 2.7 m up, GTA style).
    Returns the camera. Heights from the scene (road surface)."""
    xy = _route()
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    L = seg[-1]
    nf = int(seconds * fps)
    frames = np.unique(np.r_[np.arange(1, nf + 1, 4), nf])
    t = (frames - 1) / (nf - 1)
    # ease in/out over the first/last 4 s, constant cruise between (still covers the whole route)
    ease = 4.0 / seconds
    u = np.clip(t, 0, 1)
    # distance fraction from a trapezoid velocity profile
    def dist(uu):
        d = np.where(uu < ease, 0.5 * (uu ** 2) / ease, np.where(uu > 1 - ease, (1 - ease) - 0.5 * ((1 - uu) ** 2) / ease, uu - ease / 2))
        return d / (1 - ease)  # normalise: trapezoid area = 1 - ease
    s = np.clip(dist(u), 0, 1) * L

    d0 = (xy[3] - xy[0]) / np.linalg.norm(xy[3] - xy[0])
    d1 = (xy[-1] - xy[-4]) / np.linalg.norm(xy[-1] - xy[-4])

    def at(sd):
        sd = np.asarray(sd, float)
        p = np.c_[np.interp(np.clip(sd, 0, L), seg, xy[:, 0]), np.interp(np.clip(sd, 0, L), seg, xy[:, 1])]
        p = p + np.where((sd < 0)[:, None], sd[:, None] * d0[None, :], 0.0) + \
            np.where((sd > L)[:, None], (sd - L)[:, None] * d1[None, :], 0.0)
        return p

    # road height: sample every 4 m, smooth
    sg = np.arange(0, L + 4, 4.0)
    pts = at(sg)
    zg = _gauss(np.array([ground_z(scn, *p) for p in pts]), 2.0)
    zat = lambda sd: np.interp(np.clip(sd, 0, L), sg, zg)  # noqa: E731  (flat beyond the ends)
    car_xy = at(s)
    ahead = at(s + 3.0)
    heading = np.arctan2(ahead[:, 1] - car_xy[:, 1], ahead[:, 0] - car_xy[:, 0])
    heading = np.unwrap(heading)
    heading = _gauss(heading, 2.0)
    pitch = -np.arctan2(zat(s + 2.0) - zat(s - 2.0), 4.0)
    car_p = np.c_[car_xy, zat(s) + 0.06]
    rot = np.c_[np.zeros(len(s)), pitch, heading]
    car = build_hero_car(scn)
    coll = bpy.data.collections.get("Cameras") or bpy.data.collections.new("Cameras")
    if coll.name not in scn.collection.children:
        scn.collection.children.link(coll)
    _key(car, car_p, frames, rot)
    back = at(s - 9.0)
    eye = np.c_[back, zat(s - 9.0) + 2.9]
    eye = _gauss(eye, 3.0)
    look = np.c_[at(s + 6.0), zat(s + 6.0) + 1.3]
    look = _gauss(look, 3.0)
    cam = _cam("cine_car_cam", coll, eye[0], look[0], lens=22)
    tgt = bpy.data.objects.new("cine_car_target", None)
    coll.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    _key(cam, eye, frames)
    _key(tgt, look, frames)
    scn.frame_start, scn.frame_end, scn.render.fps = 1, nf, fps
    return cam


def _clearance(scn, p, want=14.0, probe=38.0, iters=4):
    """Push a drone point out of geometry: stay `want` m above whatever is below, and >= `probe` m (soft)
    from walls found by 12 horizontal rays."""
    deps = bpy.context.evaluated_depsgraph_get()
    p = np.array(p, float)
    for _ in range(iters):
        hit, loc, *_ = scn.ray_cast(deps, Vector((p[0], p[1], 900.0)), Vector((0, 0, -1)))
        if hit and p[2] < loc.z + want:
            p[2] = loc.z + want
        moved = False
        for k in range(12):
            a = k * math.pi / 6
            d = Vector((math.cos(a), math.sin(a), 0))
            h, l, *_ = scn.ray_cast(deps, Vector(p), d, distance=probe)
            if h:
                dist = (Vector(l) - Vector(p)).length
                p[:2] -= np.array([d.x, d.y]) * (probe - dist) * 0.9
                moved = True
        if not moved:
            break
    return p


def tall_cluster():
    """Centroid (city frame) + max roof height of the tallest pilot buildings (data/processed/hero_cluster.json,
    written by src/cine/make_route.py)."""
    import json
    from pathlib import Path
    r = json.loads((Path(__file__).resolve().parents[2] / "data/processed/hero_cluster.json").read_text())
    return np.array(r["center"], float), float(r["top"])


def add_cine_drone(scn, seconds=180.0, fps=24):
    """Architecture drone: waterfront rise -> descending orbit of the tallest cluster -> flight down the Market St
    canyon -> climbing pull-back over the bay. Every key is pushed out of geometry (ray-cast clearance)."""
    import json
    from pathlib import Path
    cache = Path(__file__).resolve().parents[2] / f"data/processed/cine_drone_keys_{int(seconds)}.json"
    if cache.exists():  # clearance ray-casting is slow: computed once, reused by every render process
        kd = json.loads(cache.read_text())
        eye, look, frames = np.array(kd["eye"]), np.array(kd["look"]), np.array(kd["frames"])
        coll = bpy.data.collections.get("Cameras") or bpy.data.collections.new("Cameras")
        if coll.name not in scn.collection.children:
            scn.collection.children.link(coll)
        cam = _cam("cine_drone_cam", coll, eye[0], look[0], lens=24)
        tgt = bpy.data.objects.new("cine_drone_target", None)
        coll.objects.link(tgt)
        con = cam.constraints.new("TRACK_TO")
        con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
        _key(cam, eye, frames)
        _key(tgt, look, frames)
        scn.frame_start, scn.frame_end, scn.render.fps = 1, int(seconds * fps), fps
        return cam
    C, top = tall_cluster()
    (x0, y0), (x1, y1) = MARKET
    d = np.array([x1 - x0, y1 - y0])
    d /= np.linalg.norm(d)
    right = np.array([d[1], -d[0]])
    nf = int(seconds * fps)
    frames = np.unique(np.r_[np.arange(1, nf + 1, 4), nf])
    t = (frames - 1) / (nf - 1)
    cz = ground_z(scn, *C)
    eye = np.zeros((len(t), 3))
    look = np.zeros((len(t), 3))
    mkt = lambda f: np.array([x0, y0]) + d * (np.linalg.norm([x1 - x0, y1 - y0])) * f  # noqa: E731
    for i, u in enumerate(t):
        if u < 0.14:  # approach from the bay
            k = u / 0.14
            a0 = math.atan2(*(np.array([300, 80]) - C)[::-1])
            pos = C + 520 * np.array([math.cos(a0), math.sin(a0)]) * (1 - 0.3 * k)
            eye[i] = [*pos, 90 + 110 * k]
            look[i] = [*C, cz + 70]
        elif u < 0.53:  # descending orbit, 1.25 turns
            k = (u - 0.14) / 0.39
            a = math.atan2(*(np.array([300, 80]) - C)[::-1]) + k * 1.25 * 2 * math.pi
            r = 520 - 170 * k
            eye[i] = [C[0] + r * math.cos(a), C[1] + r * math.sin(a), cz + 300 - 150 * k + 14 * math.sin(k * 9)]
            look[i] = [*(C + 25 * np.array([math.cos(a + 1.2), math.sin(a + 1.2)])), cz + 120 - 20 * k]
        elif u < 0.80:  # canyon flight down Market St toward the Ferry Building
            k = (u - 0.53) / 0.27
            f = 0.12 + 0.8 * k
            sway = 7 * math.sin(k * 8)
            eye[i] = [*(mkt(f) + right * sway * 0.4), cz + 58 - 14 * math.sin(k * math.pi)]
            ah = mkt(min(f + 0.16, 1.05))
            look[i] = [*ah, cz + 38 + 8 * math.sin(k * 5)]
        else:  # pull back and climb over the bay, looking back at the skyline
            k = (u - 0.80) / 0.20
            base = mkt(0.92) + right * 40
            pos = base + d * 420 * k + right * (160 * k)
            eye[i] = [*pos, cz + 70 + 190 * k]
            look[i] = [*(C * (1 - 0.15) + mkt(0.5) * 0.15), cz + 90]
    eye = _gauss(eye, 6.0)
    look = _gauss(look, 6.0)
    canyon = (t >= 0.50) & (t < 0.82)  # inside the street canyon: tight clearance; elsewhere stay well off roofs
    for i in range(len(eye)):  # keep clear of geometry, then smooth again
        eye[i] = _clearance(scn, eye[i], want=16.0 if canyon[i] else 38.0, probe=12.0 if canyon[i] else 60.0)
    eye = _gauss(eye, 4.0)
    for i in range(len(eye)):
        eye[i] = _clearance(scn, eye[i], want=16.0 if canyon[i] else 38.0, probe=12.0 if canyon[i] else 60.0, iters=2)
    cache.write_text(json.dumps({"eye": eye.tolist(), "look": look.tolist(), "frames": frames.tolist()}))
    return add_cine_drone(scn, seconds, fps)


# ----------------------------------------------------------------------------- Gaussian-splat capture views
def splat_views(scn, step=330.0, alt=210.0, street_every=80.0):
    """Calibrated capture views of the pilot district: oblique aerials (4 headings, 50 deg down) and nadirs on a
    grid, plus street-level views (forward/back/left/right) along the hero route. -> list of (eye, look, tag)."""
    views = []
    for x in np.arange(-1300.0, 301.0, step):
        for y in np.arange(-800.0, 801.0, step):
            z = ground_z(scn, x, y)
            if z < 0.3:
                continue
            hit, loc, *_ = scn.ray_cast(bpy.context.evaluated_depsgraph_get(), Vector((x, y, 900.0)), Vector((0, 0, -1)))
            top = loc.z if hit else z
            eye = np.array([x, y, max(z + alt, top + 50.0)])  # never inside a tower
            views.append((eye, eye + np.array([0, 0, -100.0]) + np.array([0.01, 0, 0]), "nadir"))
            for hd in (0, 90, 180, 270):
                a = math.radians(hd)
                dirv = np.array([math.sin(a) * math.cos(math.radians(50)), math.cos(a) * math.cos(math.radians(50)),
                                 -math.sin(math.radians(50))])
                views.append((eye, eye + dirv * 300.0, f"obl{hd}"))
    xy = _route()
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    street_start = len(views)
    for sd in np.arange(10.0, seg[-1] - 10, street_every):
        p0 = np.array([np.interp(sd, seg, xy[:, 0]), np.interp(sd, seg, xy[:, 1])])
        p1 = np.array([np.interp(sd + 6, seg, xy[:, 0]), np.interp(sd + 6, seg, xy[:, 1])])
        d = (p1 - p0) / (np.linalg.norm(p1 - p0) + 1e-9)
        z = ground_z(scn, *p0)
        eye = np.array([*p0, z + 4.5])
        for name, dv in (("fwd", d), ("back", -d), ("left", np.array([-d[1], d[0]])), ("right", np.array([d[1], -d[0]]))):
            views.append((eye, eye + np.array([dv[0] * 40, dv[1] * 40, 6.0]), f"street_{name}"))
    # canyon fill (appended last so earlier view indices stay valid): low cameras over OPEN streets in the tower
    # core, looking along the streets (-15 deg) and steeply down (-65 deg), to see what the aerials cannot
    deps = bpy.context.evaluated_depsgraph_get()
    for cx in np.arange(-1000.0, 40.0, 130.0):
        for cy in np.arange(-850.0, -40.0, 130.0):
            spot = None
            for ox in np.arange(-45, 46, 15):
                for oy in np.arange(-45, 46, 15):
                    x, y = cx + ox, cy + oy
                    z = ground_z(scn, x, y)
                    hit, loc, *_ = scn.ray_cast(deps, Vector((x, y, 900.0)), Vector((0, 0, -1)))
                    if hit and abs(loc.z - z) < 2.5 and z > 0.3:
                        spot = (x, y, z)
                        break
                if spot:
                    break
            if not spot:
                continue
            eye = np.array([spot[0], spot[1], spot[2] + 45.0])
            for hd in (0, 90, 180, 270):
                a = math.radians(hd)
                dv = np.array([math.sin(a) * math.cos(math.radians(15)), math.cos(a) * math.cos(math.radians(15)),
                               -math.sin(math.radians(15))])
                views.append((eye, eye + dv * 80.0, f"fill{hd}"))
            views.append((eye, eye + np.array([0.01, 0, -60.0]), "fillnadir"))
    return views
