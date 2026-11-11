"""Original (own-made) game props for Unreal: 3 unit tree prototypes, a low-poly car, a pedestrian, and a rigged wheeled-vehicle FBX.
blender -b --factory-startup -P src/blender/export_game_assets.py
Out: out/unreal/props/*.usdc (static), out/unreal/props/SK_Vehicle.fbx (armature: Root + 4 wheel bones)."""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy, bmesh
from bpy_common import ROOT
OUT = ROOT / "out/unreal/props"; OUT.mkdir(parents=True, exist_ok=True)

def mat(name, rgb, rough=0.6, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    return m

def obj_from_bm(name, bm, mats, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    ob = bpy.data.objects.new(name, me); ob.location = loc; bpy.context.scene.collection.objects.link(ob); return ob

def box(bm, sx, sy, sz, cx=0, cy=0, cz=0, mi=0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=r["verts"]); bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=r["verts"])
    for f in {f for v in r["verts"] for f in v.link_faces}: f.material_index = mi

def cyl(bm, r, depth, cx, cy, cz, axis_x=True, seg=20, mi=0):
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=depth)
    if axis_x: bmesh.ops.rotate(bm, verts=res["verts"], cent=(0, 0, 0), matrix=__import__("mathutils").Matrix.Rotation(math.pi / 2, 3, "Y"))
    bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=res["verts"])
    for f in {f for v in res["verts"] for f in v.link_faces}: f.material_index = mi

def export_usd(objs, path, root):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.wm.usd_export(filepath=str(path), selected_objects_only=True, export_materials=True, generate_preview_surface=True, export_uvmaps=True,
                          export_normals=True, triangulate_meshes=True, use_instancing=False, root_prim_path=root, export_animation=False, meters_per_unit=1.0)

# ---- trees: reuse the pipeline's unit prototypes (crown radius 1, height 1); one USD each
import trees_instancing as ti
coll = ti.protos("lod1")
for o in list(coll.objects):
    nm = "SM_Tree_" + o.name.split("_")[1].capitalize()
    o2 = o.copy(); o2.data = o.data.copy(); o2.name = nm; bpy.context.scene.collection.objects.link(o2)
    export_usd([o2], OUT / f"{nm}.usdc", f"/{nm}")

# ---- car (static): 4.4 x 1.8 x 1.45 m, origin at ground centre
paint, glass, tire = mat("MAT_Paint_SutroRed", (0.55, 0.05, 0.04), 0.35, 0.3), mat("MAT_Glass_Curtain", (0.05, 0.1, 0.14), 0.05, 0.6), mat("MAT_Road_Asphalt_Local", (0.03, 0.03, 0.03), 0.9)
def car_body():
    bm = bmesh.new(); box(bm, 4.4, 1.8, 0.7, 0, 0, 0.65, 0); box(bm, 2.3, 1.62, 0.6, -0.15, 0, 1.25, 1); return obj_from_bm("SM_Car_Body", bm, [paint, glass])
wheels = {"FL": (1.35, 0.85), "FR": (1.35, -0.85), "RL": (-1.35, 0.85), "RR": (-1.35, -0.85)}
body = car_body(); parts = [body]
for k, (x, y) in wheels.items():
    bm = bmesh.new(); cyl(bm, 0.34, 0.24, 0, 0, 0, True, 20, 0); w = obj_from_bm(f"SM_Car_Wheel_{k}", bm, [tire], (x, y, 0.34)); parts.append(w)
bpy.ops.object.select_all(action="DESELECT")
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = body; bpy.ops.object.join()
car = bpy.context.view_layer.objects.active; car.name = "SM_Car"; export_usd([car], OUT / "SM_Car.usdc", "/SM_Car")

# ---- pedestrian (static): 1.75 m, torso + legs + head + arms
skin, shirt, trs = mat("MAT_Skin", (0.75, 0.55, 0.45), 0.7), mat("MAT_Cloth_Blue", (0.12, 0.2, 0.45), 0.9), mat("MAT_Cloth_Dark", (0.06, 0.06, 0.08), 0.9)
bm = bmesh.new(); box(bm, 0.22, 0.4, 0.62, 0, 0, 1.2, 1); box(bm, 0.18, 0.16, 0.85, 0, 0.1, 0.43, 2); box(bm, 0.18, 0.16, 0.85, 0, -0.1, 0.43, 2)
box(bm, 0.14, 0.12, 0.6, 0, 0.27, 1.2, 1); box(bm, 0.14, 0.12, 0.6, 0, -0.27, 1.2, 1); box(bm, 0.2, 0.18, 0.24, 0, 0, 1.62, 0)
ped = obj_from_bm("SM_Pedestrian", bm, [skin, shirt, trs]); export_usd([ped], OUT / "SM_Pedestrian.usdc", "/SM_Pedestrian")

# ---- rigged wheeled vehicle (FBX): Root + wheel bones at wheel centres, weighted per wheel/body
bpy.ops.object.select_all(action="DESELECT")
vparts = []
vb = car_body(); vb.name = "Body"; vparts.append(vb)
for k, (x, y) in wheels.items():
    bm = bmesh.new(); cyl(bm, 0.34, 0.24, 0, 0, 0, True, 20, 0); vparts.append(obj_from_bm(f"Wheel_{k}", bm, [tire], (x, y, 0.34)))
for o in vparts: o.select_set(True)
bpy.context.view_layer.objects.active = vb; bpy.ops.object.join(); veh = bpy.context.view_layer.objects.active; veh.name = "SK_Vehicle_Mesh"
# vertex groups by nearest wheel (verts with z<0.7 and |x|>1.0 and wheel-radius proximity)
me = veh.data; vg = {n: veh.vertex_groups.new(name=n) for n in ["Root"] + [f"Wheel_{k}" for k in wheels]}
for v in me.vertices:
    assigned = False
    for k, (x, y) in wheels.items():
        if abs(v.co.x - x) < 0.36 and abs(v.co.y - y) < 0.2 and v.co.z < 0.72: vg[f"Wheel_{k}"].add([v.index], 1.0, "REPLACE"); assigned = True; break
    if not assigned: vg["Root"].add([v.index], 1.0, "REPLACE")
arm = bpy.data.armatures.new("SK_Vehicle_Skel"); ao = bpy.data.objects.new("Armature", arm); bpy.context.scene.collection.objects.link(ao)
bpy.context.view_layer.objects.active = ao; bpy.ops.object.mode_set(mode="EDIT")
rb = arm.edit_bones.new("Root"); rb.head = (0, 0, 0.3); rb.tail = (0, 0, 0.6)
for k, (x, y) in wheels.items():
    b = arm.edit_bones.new(f"Wheel_{k}"); b.head = (x, y, 0.34); b.tail = (x, y + (0.2 if y > 0 else -0.2), 0.34); b.parent = rb
bpy.ops.object.mode_set(mode="OBJECT")
veh.parent = ao; mod = veh.modifiers.new("Armature", "ARMATURE"); mod.object = ao
bpy.ops.object.select_all(action="DESELECT"); ao.select_set(True); veh.select_set(True); bpy.context.view_layer.objects.active = ao
bpy.ops.export_scene.fbx(filepath=str(OUT / "SK_Vehicle.fbx"), use_selection=True, object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                         bake_anim=False, axis_forward="-Y", axis_up="Z", apply_unit_scale=True, global_scale=1.0, path_mode="COPY", embed_textures=False)
print("GAMEASSETS_DONE", sorted(p.name for p in OUT.iterdir()))
