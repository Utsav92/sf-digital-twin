"""Camera rigs (Phase 10): full-city aerials (N/E/S/W), a neighbourhood fly-through on a keyframed path,
and street-level cameras. City frame (origin Ferry Building), metres. Runs inside Blender."""
import math

import bpy
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
