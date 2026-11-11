"""Show a splat .ply in Blender as a coloured point cloud (stock Blender cannot render Gaussians).
blender -b --factory-startup -P src/cine/splat_to_blend.py -- <in.ply> <out.blend> [max_points]
Converts the viewer frame (Y-down) back to the city frame (Z-up, metres, origin Ferry Building)."""
import sys
from pathlib import Path

import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
src, out = Path(a[0]), Path(a[1])
cap = int(a[2]) if len(a) > 2 else 3_000_000
with open(src, "rb") as fh:
    hdr = b""
    while b"end_header\n" not in hdr:
        hdr += fh.read(1)
off = len(hdr)
L = hdr.decode().split("\n")
n = int([l for l in L if l.startswith("element vertex")][0].split()[-1])
names = [l.split()[-1] for l in L if l.startswith("property")]
m = np.memmap(src, dtype=np.dtype([(k, "<f4") for k in names]), mode="r", offset=off, shape=(n,))
idx = np.arange(0, n, max(1, n // cap))
x, y, z = (np.array(m[k][idx]) for k in ("x", "y", "z"))
pos = np.c_[x, z, -y].astype(np.float32)                      # (x, y, z)_viewer -> city (x, north, up)
rgb = np.clip(np.stack([np.array(m[f"f_dc_{i}"][idx]) for i in range(3)], 1) * 0.28209479 + 0.5, 0, 1)
sc = np.exp(np.array(m["scale_0"][idx]))                      # in-plane radius -> point radius
bpy.ops.wm.read_factory_settings(use_empty=True)
pc = bpy.data.pointclouds.new("sf_twin_splat")
pc.resize(len(pos))
pc.attributes["position"].data.foreach_set("vector", pos.ravel())
rad = pc.attributes.new("radius", "FLOAT", "POINT")
rad.data.foreach_set("value", (sc * 0.75).astype(np.float32))
col = pc.attributes.new("Col", "FLOAT_COLOR", "POINT")
col.data.foreach_set("color", np.c_[rgb, np.ones(len(rgb))].astype(np.float32).ravel())
ob = bpy.data.objects.new("sf_twin_splat", pc)
bpy.context.scene.collection.objects.link(ob)
mat = bpy.data.materials.new("splat_color")
mat.use_nodes = True
nt = mat.node_tree
for nd in list(nt.nodes):
    nt.nodes.remove(nd)
at = nt.nodes.new("ShaderNodeAttribute")
at.attribute_name = "Col"
em = nt.nodes.new("ShaderNodeEmission")
mo = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(at.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], mo.inputs["Surface"])
ob.data.materials.append(mat)
# a camera over the Financial District + sky background so the cloud reads like the other renders
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
cam.location = (-650, -1100, 330)
cam.rotation_euler = (np.radians(62), 0, np.radians(-12))
cam.data.clip_end = 20000
bpy.context.scene.camera = cam
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.7, 0.9, 1)
bpy.context.scene.world = w
for scr in bpy.data.screens:  # nothing else needed; viewport shows points in Solid mode with attribute colour
    pass
bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
print("SAVEDSPLAT", len(pos), "points ->", out)
