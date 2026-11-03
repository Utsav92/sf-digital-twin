"""Phase 1 sanity scene: root collection props, one tile collection + anchor, a numpy-built
10 m cube placed in the tile frame, a sun at SF latitude, camera, render.

blender -b -P src/blender/phase1_test_cube.py -- [--engine EEVEE|CYCLES|WORKBENCH]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import math

import bpy
import numpy as np
from bpy_common import (ROOT, outward_normal_fraction, save_blend_atomic, layer_tile_collection, load_tile_index, mesh_from_numpy,
                        render_png, reset_scene, root_collection, script_args, set_engine, tile_anchor)

args = script_args()
engine = args[args.index("--engine") + 1] if "--engine" in args else "EEVEE"

scn = reset_scene()
idx = load_tile_index()
root = root_collection(idx)
tile = idx["tiles"]["t+00_+00"]          # tile NE of the Ferry Building, offset (250, 250)
coll = layer_tile_collection(root, "Buildings", tile)
anchor = tile_anchor(tile, coll)

# 10 m cube on a 40 m ground plate, built with foreach_set (no bpy.ops primitives)
s = 5.0
v = np.array([[x, y, z] for z in (0, 2 * s) for y in (-s, s) for x in (-s, s)], np.float32)
f = np.array([[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]])
cube = bpy.data.objects.new("test_cube", mesh_from_numpy("test_cube", v, f))
coll.objects.link(cube)
cube.parent = anchor
cube["source_id"] = "phase1_test"

g = 20.0
gv = np.array([[-g, -g, 0], [g, -g, 0], [g, g, 0], [-g, g, 0]], np.float32)
ground = bpy.data.objects.new("ground", mesh_from_numpy("ground", gv, np.array([[0, 1, 2, 3]])))
coll.objects.link(ground)
ground.parent = anchor

for ob, col in ((cube, (0.8, 0.35, 0.2, 1)), (ground, (0.5, 0.5, 0.5, 1))):
    m = bpy.data.materials.new(ob.name + "_mat")
    m.diffuse_color = col
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = col
    ob.data.materials.append(m)

world = bpy.data.worlds.new("World")
scn.world = world
world.color = (0.4, 0.5, 0.65)
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.4, 0.5, 0.65, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
scn.collection.objects.link(sun)
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(40), 0, math.radians(30))

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scn.collection.objects.link(cam)
scn.camera = cam
target = np.array(tile["offset_city"]) + [0, 0, 5]
cam.location = target + [28, -32, 22]
d = target - np.array(cam.location)
cam.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)

eng = set_engine(scn, engine)
out = ROOT / "renders/phase1_test_cube.png"
dt = render_png(out, (1280, 800))
save_blend_atomic(ROOT / "out/tiles/phase1_test.blend")

wm = cube.matrix_world.translation
print(f"PHASE1 blender={bpy.app.version_string} engine={eng} render={dt:.2f}s")
print(f"PHASE1 cube world=({wm.x:.1f},{wm.y:.1f},{wm.z:.1f}) expected=(250.0,250.0,0.0)")
print(f"PHASE1 root props: {dict(root.items())}")
print(f"PHASE1 cube outward normals: {outward_normal_fraction(cube.data):.2f} (expect 1.00)")
sharp = np.zeros(6, bool); cube.data.attributes["sharp_face"].data.foreach_get("value", sharp)
print(f"PHASE1 cube flat-shaded faces: {int(sharp.sum())}/6")
print(f"PHASE1 wrote {out}")
