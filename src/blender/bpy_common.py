"""Shared helpers for headless Blender builders. Runs INSIDE Blender (bpy), stdlib + numpy only.

Conventions
- 1 BU = 1 m, Z up. Geometry for a tile is authored in the tile frame (centered on the tile),
  then the tile's objects are parented to an empty placed at tile.offset_city.
- Collections: root "SF" -> layer collections "Terrain", "Water", ... -> "<layer>_<i>_<j>".
- Root collection custom props: crs, origin_lon/lat, origin_world_xy, tile_size_m, grid ranges.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ("Terrain", "Water", "Land", "Roads", "Rail", "Buildings", "Trees", "Landmarks")


def script_args() -> list[str]:
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def load_config() -> dict:
    return json.loads((ROOT / "config/city.json").read_text())


def load_tile_index() -> dict:
    return json.loads((ROOT / "data/processed/tile_index.json").read_text())


def reset_scene() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0   # no .blend1 backups; outputs are rebuildable
    scn = bpy.context.scene
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 1.0
    scn.unit_settings.length_unit = "METERS"
    return scn


def root_collection(index: dict) -> bpy.types.Collection:
    scn = bpy.context.scene
    root = bpy.data.collections.get("SF")
    if root is None:
        root = bpy.data.collections.new("SF")
        scn.collection.children.link(root)
    root["crs"] = index["crs"]
    root["origin_name"] = index["origin"]["name"]
    root["origin_lon"] = index["origin"]["lon"]
    root["origin_lat"] = index["origin"]["lat"]
    root["origin_world_xy"] = list(index["origin"]["world_xy"])
    root["tile_size_m"] = index["tile_size_m"]
    root["grid_i_range"] = list(index["i_range"])
    root["grid_j_range"] = list(index["j_range"])
    root["units"] = "1 BU = 1 m, Z up, NAVD88 m"
    return root


def layer_tile_collection(root, layer: str, tile: dict) -> bpy.types.Collection:
    assert layer in LAYERS, layer
    lc = root.children.get(layer) or bpy.data.collections.new(layer)
    if lc.name not in root.children:
        root.children.link(lc)
    name = f"{layer}_{tile['name']}"
    tc = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if tc.name not in lc.children:
        lc.children.link(tc)
    tc["tile_id"] = tile["id"]
    tc["offset_city"] = list(tile["offset_city"])
    tc["bounds_city"] = list(tile["bounds_city"])
    return tc


def tile_anchor(tile: dict, coll) -> bpy.types.Object:
    """Empty at the tile's city-frame offset; tile geometry is parented to it."""
    name = f"anchor_{tile['name']}"
    a = bpy.data.objects.get(name) or bpy.data.objects.new(name, None)
    if a.name not in coll.objects:
        coll.objects.link(a)
    a.location = tile["offset_city"]
    a["tile_id"] = tile["id"]
    a.empty_display_size = 10
    return a


def mesh_from_numpy(name: str, verts: np.ndarray, faces: np.ndarray, flat: bool = True) -> bpy.types.Mesh:
    """Bulk mesh creation via foreach_set. faces: (F, k) int array of equal-arity polygons.
    flat=True writes the sharp_face attribute (Blender >=4.1 defaults new polys to smooth)."""
    me = bpy.data.meshes.new(name)
    verts = np.ascontiguousarray(verts, dtype=np.float32)
    faces = np.ascontiguousarray(faces, dtype=np.int32)
    nf, k = faces.shape
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(nf * k)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * k, k, dtype=np.int32))
    if flat:
        attr = me.attributes.get("sharp_face") or me.attributes.new("sharp_face", "BOOLEAN", "FACE")
        attr.data.foreach_set("value", np.ones(nf, dtype=bool))
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    return me


def mesh_from_npz(name: str, d, flat: bool = True) -> bpy.types.Mesh:
    """Mesh from the meshio npz layout (verts, loops, sizes, f_* face attributes)."""
    verts, loops, sizes = d["verts"], d["loops"].astype(np.int32), d["sizes"].astype(np.int32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.ascontiguousarray(verts, np.float32).ravel())
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops)
    me.polygons.add(len(sizes))
    starts = np.zeros(len(sizes), np.int32)
    if len(sizes):
        starts[1:] = np.cumsum(sizes)[:-1]
    me.polygons.foreach_set("loop_start", starts)
    for k in d.files:
        if k.startswith("f_") and len(d[k]) == len(sizes):
            a = d[k]
            typ = "FLOAT" if a.dtype.kind == "f" else "INT"
            attr = me.attributes.new(k[2:], typ, "FACE")
            attr.data.foreach_set("value", a.astype(np.float32 if typ == "FLOAT" else np.int32))
    if "uv" in d.files and len(d["uv"]) == len(loops):
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.ascontiguousarray(d["uv"], np.float32).ravel())
    if flat and len(sizes):
        attr = me.attributes.new("sharp_face", "BOOLEAN", "FACE")
        attr.data.foreach_set("value", np.ones(len(sizes), dtype=bool))
    me.update(calc_edges=True)
    return me


def outward_normal_fraction(me) -> float:
    """Fraction of faces whose normal points away from the mesh centroid (closed convex sanity check)."""
    n = len(me.polygons)
    nrm = np.empty(n * 3, np.float32); me.polygons.foreach_get("normal", nrm)
    ctr = np.empty(n * 3, np.float32); me.polygons.foreach_get("center", ctr)
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co)
    c = co.reshape(-1, 3).mean(0)
    return float(((nrm.reshape(-1, 3) * (ctr.reshape(-1, 3) - c)).sum(1) > 0).mean())


def set_engine(scn, engine: str = "EEVEE", samples: int = 32) -> str:
    """Pick a render engine robustly across Blender 4.x/5.x ids."""
    # add-on engines (Cycles) are not in the static RNA enum, so try-assign instead
    want = {"EEVEE": ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"],
            "CYCLES": ["CYCLES"], "WORKBENCH": ["BLENDER_WORKBENCH"]}[engine]
    for ident in want:
        try:
            scn.render.engine = ident
            break
        except TypeError:
            continue
    else:
        raise RuntimeError(f"render engine {engine} unavailable")
    if scn.render.engine == "CYCLES":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scn.cycles.device = "GPU"
        scn.cycles.samples = samples
    elif "EEVEE" in scn.render.engine:
        scn.eevee.taa_render_samples = samples
    return scn.render.engine


def save_blend_atomic(path: Path) -> None:
    """Write to <path>.tmp.blend then os.replace, so crashes/parallel runs never leave a partial file."""
    import os
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.tmp.blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(tmp), copy=True, compress=True)
    os.replace(tmp, path)


def render_png(path: Path, res=(1600, 1000)) -> float:
    scn = bpy.context.scene
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.resolution_percentage = 100
    scn.render.image_settings.file_format = "PNG"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    t = time.time()
    bpy.ops.render.render()
    import os
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.tmp.png")
    bpy.data.images["Render Result"].save_render(str(tmp))
    os.replace(tmp, path)
    return time.time() - t
