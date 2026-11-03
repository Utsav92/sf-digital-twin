"""Assemble tiles via linked collection instances and render verification views. Runs inside Blender.

blender -b --factory-startup -P src/blender/render_city.py -- \
   [--pilot | --tiles a,b | --all] [--lod lod0|lod1|auto] [--view top|aerial] [--az 225] [--elev 35]
   [--target x,y,z] [--dist 3000] [--lens 50] [--cam x,y,z] [--hypso] [--time 2026-09-21T16:00]
   [--hide Buildings,Trees] [--res 1920x1200] [--engine EEVEE] [--samples 32] --out renders/x.png
--lod auto: LOD1 for tiles within --lod1-radius of the target, LOD0 elsewhere.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from bpy_common import ROOT, load_tile_index, render_png, reset_scene, script_args, set_engine  # noqa: E402
import lighting  # noqa: E402
import materials  # noqa: E402


def opt(args, k, d=None, f=str):
    return f(args[args.index(k) + 1]) if k in args else d


def vec(s):
    return Vector([float(v) for v in s.split(",")])


def link_tile(tile, lod):
    path = ROOT / "out/tiles" / tile["id"] / f"{tile['id']}.blend"
    if not path.exists():
        return None
    cname = f"tile_{tile['name']}_{lod.upper()}"
    with bpy.data.libraries.load(str(path), link=True) as (src, dst):
        dst.collections = [c for c in src.collections if c == cname]
    if not dst.collections:
        return None
    coll = dst.collections[0]
    inst = bpy.data.objects.new(f"inst_{tile['name']}_{lod}", None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = coll
    inst.location = tile["offset_city"]
    inst["tile_id"] = tile["id"]
    bpy.context.scene.collection.objects.link(inst)
    return inst


def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def main():
    a = script_args()
    scn = reset_scene()
    idx = load_tile_index()
    tiles = [t for t in idx["tiles"].values() if t["status"] == "build"]
    if "--pilot" in a:
        tiles = [t for t in tiles if t["pilot"]]
    if "--tiles" in a:
        want = set(opt(a, "--tiles").split(","))
        tiles = [t for t in tiles if t["id"] in want]
    lod = opt(a, "--lod", "lod0")
    target = vec(opt(a, "--target", "0,0,0")) if "--target" in a else None
    xs = [t["bounds_city"][0] for t in tiles] + [t["bounds_city"][2] for t in tiles]
    ys = [t["bounds_city"][1] for t in tiles] + [t["bounds_city"][3] for t in tiles]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    target = target or Vector((cx, cy, 0))
    r1 = opt(a, "--lod1-radius", 1200, float)
    n = {"lod0": 0, "lod1": 0}
    for t in tiles:
        L = lod
        if lod == "auto":
            ox, oy, _ = t["offset_city"]
            L = "lod1" if math.hypot(ox - target.x, oy - target.y) < r1 else "lod0"
        if link_tile(t, L):
            n[L] += 1
    oc = ROOT / "data/processed/city_ocean.npz"
    if oc.exists() and "--no-ocean" not in a:
        from bpy_common import mesh_from_npz
        me = mesh_from_npz("far_ocean", np.load(oc))
        me.materials.append(materials.get_mat("water_bay"))
        scn.collection.objects.link(bpy.data.objects.new("far_ocean", me))
    hide = set(opt(a, "--hide", "").split(",")) - {""}
    if hide:
        for c in bpy.data.collections:
            if any(c.name.startswith(h + "_") for h in hide):
                for o in c.objects:
                    o.hide_render = True
    eng = set_engine(scn, opt(a, "--engine", "EEVEE"), opt(a, "--samples", 32, int))
    try:
        scn.view_settings.view_transform = "AgX"
    except TypeError:
        scn.view_settings.view_transform = "Filmic"
    if "--preset" in a:
        elev, az = lighting.apply_preset(scn, opt(a, "--preset"), wetness=opt(a, "--wet", 0.0, float))
    else:
        elev, az = lighting.setup_sun_sky(scn, opt(a, "--time", "2026-09-21T15:30"))
    if "--hypso" in a:
        bpy.context.view_layer.material_override = materials.hypsometric_override()
    if "EEVEE" in eng:
        for attr, val in (("use_shadows", True), ("shadow_ray_count", 2), ("use_raytracing", True),
                          ("use_gtao", True)):
            try:
                setattr(scn.eevee, attr, val)
            except AttributeError:
                pass

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scn.collection.objects.link(cam)
    scn.camera = cam
    cam.data.clip_start, cam.data.clip_end = max(0.3, opt(a, "--dist", 3000, float) / 3000), 60000
    res = [int(v) for v in opt(a, "--res", "1920x1200").split("x")]
    view = opt(a, "--view", "aerial")
    if view == "top":
        cam.data.type = "ORTHO"
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        cam.data.ortho_scale = max(w, h * res[0] / res[1]) * 1.02
        cam.location = (cx, cy, 5000)
        cam.rotation_euler = (0, 0, 0)
    else:
        cam.data.lens = opt(a, "--lens", 35, float)
        if "--cam" in a:
            cam.location = vec(opt(a, "--cam"))
        else:
            az_c, el_c = math.radians(opt(a, "--az", 200, float)), math.radians(opt(a, "--elev", 35, float))
            dist = opt(a, "--dist", 3000, float)
            cam.location = target + Vector((math.sin(az_c) * math.cos(el_c), math.cos(az_c) * math.cos(el_c),
                                            math.sin(el_c))) * dist
        look_at(cam, target)
    if "--rig" in a:  # use a named camera rig from cameras.py (frame for animated rigs)
        import cameras
        rigs = cameras.add_rigs(scn)
        scn.camera = rigs[opt(a, "--rig")]
        scn.frame_set(opt(a, "--frame", 1, int))
    out = ROOT / opt(a, "--out", "renders/test.png")
    dt = render_png(out, res)
    print(f"RENDER {out} tiles lod0={n['lod0']} lod1={n['lod1']} engine={eng} sun elev={elev:.1f} az={az:.1f} "
          f"time={dt:.1f}s", flush=True)


main()
