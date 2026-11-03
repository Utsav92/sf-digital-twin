"""Assemble out/city/sf_master.blend: every built tile linked (not copied) as a collection instance at its
manifest offset (LOD0 visible = whole city opens fast; LOD1 instances present but hidden, toggled by
sf_set_lod(radius_m, centre) or the 'LOD1' collection), far ocean, lighting preset, camera rigs.
Root collection custom props carry CRS/origin/grid.

blender -b --factory-startup -P src/blender/assemble_master.py -- [--preset golden_hour]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy_common import ROOT, load_tile_index, mesh_from_npz, reset_scene, root_collection, save_blend_atomic, \
    script_args  # noqa: E402
import cameras  # noqa: E402
import lighting  # noqa: E402
import materials  # noqa: E402

LOD_SWITCH = '''
import bpy, math
from pathlib import Path
def sf_set_lod(radius_m=1500.0, centre=(0.0, 0.0)):
    """Link LOD1 for tiles within radius of centre (city frame) on demand and hide their LOD0; elsewhere LOD0.
    LOD1 data is only loaded for the tiles you ask for (keeps the master light)."""
    city = bpy.data.collections["City_LOD1"]
    for o in [o for o in bpy.data.objects if o.get("sf_instance") and o["sf_lod"] == "lod0"]:
        near = math.hypot(o.location.x - centre[0], o.location.y - centre[1]) < radius_m
        o.hide_viewport = o.hide_render = near
        name = o.name.replace("_LOD0", "_LOD1")
        if near and name not in bpy.data.objects:
            lib = bpy.path.abspath(o.instance_collection.library.filepath).replace("_lod0.blend", ".blend")
            with bpy.data.libraries.load(lib, link=True, relative=True) as (src, dst):
                dst.collections = [o.instance_collection.name.replace("_LOD0", "_LOD1")]
            inst = bpy.data.objects.new(name, None)
            inst.instance_type, inst.instance_collection = "COLLECTION", dst.collections[0]
            inst.location = o.location
            inst["sf_instance"], inst["sf_lod"] = True, "lod1"
            city.objects.link(inst)
        if name in bpy.data.objects:
            bpy.data.objects[name].hide_viewport = bpy.data.objects[name].hide_render = not near
'''


def main():
    a = script_args()
    t0 = time.time()
    scn = reset_scene()
    idx = load_tile_index()
    root = root_collection(idx)
    colls = {}
    for lod in ("LOD0", "LOD1"):
        c = bpy.data.collections.new(f"City_{lod}")
        root.children.link(c)
        colls[lod] = c
    n = 0
    for t in idx["tiles"].values():
        if t["status"] != "build":
            continue
        path = ROOT / "out/tiles" / t["id"] / f"{t['id']}_lod0.blend"  # LOD0-only companion
        if not path.exists():
            continue
        names = [f"tile_{t['name']}_LOD0"]  # LOD1 is linked on demand by sf_set_lod()
        with bpy.data.libraries.load(str(path), link=True, relative=True) as (src, dst):
            dst.collections = [c for c in src.collections if c in names]
        for c in dst.collections:
            lod = c.name.rsplit("_", 1)[-1]
            inst = bpy.data.objects.new(f"inst_{t['name']}_{lod}", None)
            inst.instance_type = "COLLECTION"
            inst.instance_collection = c
            inst.location = t["offset_city"]
            inst["sf_instance"], inst["sf_lod"], inst["tile_id"] = True, lod.lower(), t["id"]
            colls[lod].objects.link(inst)
            if lod == "LOD1":
                inst.hide_viewport = inst.hide_render = True
        n += 1
    oc = ROOT / "data/processed/city_ocean.npz"
    me = mesh_from_npz("far_ocean", np.load(oc))
    me.materials.append(materials.get_mat("water_bay"))
    root.objects.link(bpy.data.objects.new("far_ocean", me))
    lighting.apply_preset(scn, a[a.index("--preset") + 1] if "--preset" in a else "golden_hour")
    cameras.add_rigs(scn)
    scn.camera = bpy.data.objects["aerial_S"]
    txt = bpy.data.texts.new("sf_lod_switch.py")
    txt.write(LOD_SWITCH)
    txt.use_module = True
    out = ROOT / "out/city/sf_master.blend"
    save_blend_atomic(out)
    print(f"MASTER tiles={n} -> {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.1f} MB) in {time.time() - t0:.1f} s")


main()
