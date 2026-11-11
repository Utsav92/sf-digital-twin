"""Phase 11 (Blender side): Unreal-ready USD per tile + hero landmark assets. Runs inside Blender.

blender -b --factory-startup -P src/blender/export_unreal.py -- --tiles a,b [--landmarks]
- materials renamed 1:1 to Unreal master-material names (config/unreal_materials.json); duplicates merged
- buildings get a corner colour attribute 'Col' (vertex colour in UE):
    R = per-building hash (tint/variation), G = height / 400 m, B = type (0 low-rise, 0.5 tower >40 m), A = 1
  terrain 'Col': R = land-use class / 32 (material blending masks)
- LOD1 collection only (Nanite replaces LOD chains); trees are NOT in the USD (instance CSVs instead)
- triangulated, UVs (UVMap, metres), normals, UsdPreviewSurface materials, metersPerUnit = 1, Z up
Outputs out/unreal/tiles/<id>/<id>.usdc and out/unreal/landmarks/<asset>.usdc
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy_common import ROOT, load_tile_index, mesh_from_npz, reset_scene, script_args  # noqa: E402
import materials  # noqa: E402

MAP = {k: v for k, v in json.loads((ROOT / "config/unreal_materials.json").read_text()).items() if k != "comment"}
OUT = ROOT / "out/unreal"


def canonical_materials():
    canon = {}
    for me in bpy.data.meshes:
        for i, m in enumerate(me.materials):
            if m is None:
                continue
            src = m.get("sf_material", m.name)
            tgt = MAP.get(src, "MAT_" + src.title().replace("_", ""))
            if tgt not in canon:
                if m.library is not None:  # linked from sf_materials.blend: name is read-only, use a local copy
                    m = m.copy()
                m.name = tgt
                canon[tgt] = m
            me.materials[i] = canon[tgt]


def corner_colors(me, kind):
    n = len(me.loops)
    if n == 0:
        return
    sizes = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", sizes)
    col = np.ones((len(me.polygons), 4), np.float32)
    if kind == "buildings" and "bid" in me.attributes:
        bid = np.zeros(len(me.polygons), np.int32)
        me.attributes["bid"].data.foreach_get("value", bid)
        col[:, 0] = (np.sin(bid * 12.9898) * 43758.5453) % 1.0
        z = np.zeros(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", z)
        z = z.reshape(-1, 3)[:, 2]
        loops = np.zeros(n, np.int32)
        me.loops.foreach_get("vertex_index", loops)
        # building height: per-bid z range
        corner_bid = np.repeat(bid, sizes)
        u, inv = np.unique(corner_bid, return_inverse=True)
        lo = np.full(len(u), np.inf)
        hi = np.full(len(u), -np.inf)
        np.minimum.at(lo, inv, z[loops])
        np.maximum.at(hi, inv, z[loops])
        h = (hi - lo)[np.searchsorted(u, bid)]
        col[:, 1] = np.clip(h / 400.0, 0, 1)
        col[:, 2] = np.where(h > 40, 0.5, 0.0)
    elif kind == "terrain" and "cls" in me.attributes:
        c = np.zeros(len(me.polygons), np.int32)
        me.attributes["cls"].data.foreach_get("value", c)
        col[:, 0] = c / 32.0
    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    attr.data.foreach_set("color", np.repeat(col, sizes, axis=0).ravel())


def export_objects(objs, path, root):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.usd_export(filepath=str(path), selected_objects_only=True, export_materials=True,
                          generate_preview_surface=True, export_uvmaps=True, export_normals=True,
                          export_mesh_colors=True, triangulate_meshes=True, use_instancing=False,
                          evaluation_mode="RENDER", export_custom_properties=True, root_prim_path=root,
                          export_animation=False, meters_per_unit=1.0)


def share_textures(tex_dir):
    """USD export copies every texture next to each file; keep one shared copy in out/unreal/textures and symlink to it."""
    import shutil
    tex_dir = Path(tex_dir)
    if not tex_dir.is_dir() or tex_dir.is_symlink():
        return
    shared = OUT / "textures"
    shared.mkdir(parents=True, exist_ok=True)
    for f in tex_dir.iterdir():
        if not (shared / f.name).exists():
            shutil.move(str(f), shared / f.name)
    shutil.rmtree(tex_dir)
    tex_dir.symlink_to(os.path.relpath(shared, tex_dir.parent))


def export_tile(tile):
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out/tiles" / tile["id"] / f"{tile['id']}.blend"))
    canonical_materials()
    top = bpy.data.collections[f"tile_{tile['name']}_LOD1"]
    objs = [o for o in top.all_objects if o.type == "MESH" and o.get("layer") not in ("trees", "props")]  # props (cars, lamps) are PCG/instance data, not tile mesh
    for o in objs:
        corner_colors(o.data, o.get("layer"))
        o["tile_id"], o["sf_layer"] = tile["id"], o.get("layer")
    p = OUT / "tiles" / tile["id"] / f"{tile['id']}.usdc"
    export_objects(objs, p, f"/Tile_{tile['name'].replace('-', 'm')}")
    share_textures(p.parent / "textures")
    print(f"USD {tile['id']} objects={len(objs)} -> {p.relative_to(ROOT)}", flush=True)


def export_landmarks():
    assets = json.loads((ROOT / "data/processed/landmarks/assets.json").read_text())
    for name in assets:
        reset_scene()
        d = np.load(ROOT / "data/processed/landmarks" / f"{name}.npz")
        me = mesh_from_npz(f"SM_Landmark_{name}", d, flat=True)
        for n in json.loads(str(d["meta"]))["materials"]:
            me.materials.append(materials.get_mat(n))
        me.polygons.foreach_set("material_index", d["f_mat"].astype(np.int32))
        ob = bpy.data.objects.new(f"SM_Landmark_{name}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob["pivot_city_m"] = assets[name]["pivot_city_m"]
        canonical_materials()
        p = OUT / "landmarks" / f"SM_Landmark_{name}.usdc"
        export_objects([ob], p, f"/SM_Landmark_{name}")
        share_textures(p.parent / "textures")
        print(f"USD landmark {name} -> {p.relative_to(ROOT)}", flush=True)


def main():
    a = script_args()
    idx = load_tile_index()
    if "--tiles" in a:
        for tid in a[a.index("--tiles") + 1].split(","):
            export_tile(idx["tiles"][tid])
    if "--landmarks" in a:
        export_landmarks()


main()
