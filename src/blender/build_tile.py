"""Build tile .blend files from prepped meshes. Runs inside Blender.

blender -b --factory-startup -P src/blender/build_tile.py -- --tiles t+00_+00,t-01_+00 [--force]
Output: out/tiles/<id>/<id>.blend with
  collection tile_<i>_<j>_LOD1 -> Terrain_<i>_<j>, Water_<i>_<j>, Roads_<i>_<j>, ... (LOD1 meshes)
  collection tile_<i>_<j>_LOD0 -> Terrain_<i>_<j>_lod0, Buildings_<i>_<j>_lod0, ...
Objects are in tile-local coordinates (tile centre = origin); placement is by instance transform.
Writes out/tiles/<id>/build.json with per-object polygon counts and build time.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy_common import ROOT, load_tile_index, mesh_from_npz, reset_scene, save_blend_atomic, script_args  # noqa
import materials  # noqa: E402

PROC = ROOT / "data/processed"
OUT = ROOT / "out/tiles"
# npz layer name -> (collection layer name, material slot set)
LAYERS = {"terrain": "Terrain", "water": "Water", "roads": "Roads", "rail": "Rail", "buildings": "Buildings",
          "trees": "Trees", "landmarks": "Landmarks", "details": "Details"}


def collection(name, parent):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in parent.children:
        parent.children.link(c)
    return c


def build_mesh_layer(layer, lod, tile, parent, rep):
    f = PROC / "tiles" / tile["id"] / f"mesh_{layer}_{lod}.npz"
    if not f.exists():
        return
    d = np.load(f)
    if len(d["sizes"]) == 0:
        return
    suffix = "" if lod == "lod1" else "_lod0"
    cname = f"{LAYERS[layer]}_{tile['name']}{suffix}"
    coll = collection(cname, parent)
    coll["tile_id"] = tile["id"]
    coll["lod"] = lod
    me = mesh_from_npz(f"{layer}_{tile['name']}_{lod}", d, flat=layer in ("buildings", "landmarks", "details"))
    slot_layer = "roads" if layer == "landmarks" else layer
    if layer == "landmarks":
        names = json.loads(str(d["meta"]))["materials"]
        for n in names:
            me.materials.append(materials.get_mat(n))
    else:
        materials.assign_slots(me, slot_layer)
    key = "f_mat" if "f_mat" in d.files else ("f_cls" if "f_cls" in d.files else None)
    if key:
        me.polygons.foreach_set("material_index", d[key].astype(np.int32))
    ob = bpy.data.objects.new(f"{layer}_{tile['name']}_{lod}", me)
    coll.objects.link(ob)
    ob["tile_id"] = tile["id"]
    ob["layer"] = layer
    ob["lod"] = lod
    rep["objects"][ob.name] = {"polys": len(me.polygons), "verts": len(me.vertices),
                               "tris": int(np.maximum(d["sizes"] - 2, 0).sum())}


def build_tile(tile, index):
    t0 = time.time()
    reset_scene()
    scn = bpy.context.scene
    rep = {"id": tile["id"], "objects": {}}
    for lod in ("lod1", "lod0"):
        top = collection(f"tile_{tile['name']}_{lod.upper()}", scn.collection)
        top["tile_id"] = tile["id"]
        top["offset_city"] = list(tile["offset_city"])
        top["bounds_city"] = list(tile["bounds_city"])
        top["lod"] = lod
        top["crs"] = index["crs"]
        for layer in LAYERS:
            if layer == "trees":
                continue  # instanced separately (Phase 8)
            build_mesh_layer(layer, lod, tile, top, rep)
    import props_instancing
    import trees_instancing
    trees_instancing.build(tile, scn, rep)
    props_instancing.build(tile, scn, rep)
    out = OUT / tile["id"] / f"{tile['id']}.blend"
    save_blend_atomic(out)
    # LOD0-only companion file: the master links this one so LOD1 data is never read for the city view
    top1 = bpy.data.collections.get(f"tile_{tile['name']}_LOD1")
    if top1 is not None:
        for o in list(top1.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for c in list(top1.children_recursive) + [top1]:
            bpy.data.collections.remove(c)
        bpy.data.orphans_purge(do_recursive=True)
    save_blend_atomic(OUT / tile["id"] / f"{tile['id']}_lod0.blend")
    rep["seconds"] = round(time.time() - t0, 2)
    rep["blend_bytes"] = out.stat().st_size
    rep["tris_total"] = sum(o["tris"] for o in rep["objects"].values())
    (OUT / tile["id"] / "build.json").write_text(json.dumps(rep, indent=1))
    return rep


def main():
    args = script_args()
    ids = args[args.index("--tiles") + 1].split(",")
    index = load_tile_index()
    for tid in ids:
        r = build_tile(index["tiles"][tid], index)
        print(f"BUILT {tid} tris={r['tris_total']:,} {r['seconds']} s", flush=True)


main()
