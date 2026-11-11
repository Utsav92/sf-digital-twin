"""Street props (Blender side): GN instancing of a street lamp + 3 vehicle prototypes onto the props
point cloud. Point attributes (paint, moving) propagate to instances; car paint reads 'paint' through an
INSTANCER attribute node. Lamp heads / car lights emit only at night (SF_Globals.night)."""
import bmesh
import bpy
import numpy as np
from bpy_common import ROOT
import materials

PROC = ROOT / "data/processed"
M = {n: i for i, n in enumerate(materials.SLOTS["props"])}


def _box(bm, cx, cy, cz, sx, sy, sz, mat, taper=1.0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    v = r["verts"]
    for p in v:
        if p.co.z > 0 and taper != 1.0:
            p.co.x *= taper
            p.co.y *= taper
    bmesh.ops.scale(bm, verts=v, vec=(sx, sy, sz))
    bmesh.ops.translate(bm, verts=v, vec=(cx, cy, cz))
    for f in {f for p in v for f in p.link_faces}:
        f.material_index = M[mat]
    return v


def _quad_light(bm, x, y0, y1, z0, z1, mat, facing):
    vs = [bm.verts.new((x, y0, z0)), bm.verts.new((x, y1, z0)), bm.verts.new((x, y1, z1)), bm.verts.new((x, y0, z1))]
    f = bm.faces.new(vs if facing > 0 else vs[::-1])
    f.material_index = M[mat]


def _proto(name, build, coll):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    for n in materials.SLOTS["props"]:
        me.materials.append(materials.get_mat(n))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def lamp(bm):  # 7.5 m cobra-head lamp, arm along +X (yaw points it at the road)
    _box(bm, 0, 0, 3.75, 0.16, 0.16, 7.5, "lamp_pole", taper=0.6)
    _box(bm, 0.9, 0, 7.45, 1.8, 0.1, 0.1, "lamp_pole")
    _box(bm, 1.75, 0, 7.35, 0.6, 0.28, 0.14, "lamp_pole")
    _box(bm, 1.75, 0, 7.27, 0.5, 0.22, 0.02, "lamp_glow")


def _wheel(bm, x, y):
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.33, radius2=0.33, depth=0.24)
    bmesh.ops.rotate(bm, verts=r["verts"], cent=(0, 0, 0),
                     matrix=__import__("mathutils").Matrix.Rotation(1.5708, 3, "X"))
    bmesh.ops.translate(bm, verts=r["verts"], vec=(x, y, 0.33))
    for f in {f for v in r["verts"] for f in v.link_faces}:
        f.material_index = M["car_tire"]
        f.smooth = True


def car(L, W, H, cabin_h, cabin_l, cabin_off, paint="car_paint_0"):
    def f(bm):  # +X = forward
        body = _box(bm, 0, 0, 0.32 + (H - 0.32) / 2, L, W, H - 0.32, paint)
        cab = _box(bm, cabin_off, 0, H + cabin_h / 2, cabin_l, W * 0.9, cabin_h, "car_glass", taper=0.80)
        edges = list({e for v in body + cab for e in v.link_edges})
        bmesh.ops.bevel(bm, geom=edges, offset=0.12, segments=2, affect="EDGES", profile=0.6)
        for fc in bm.faces:
            fc.smooth = True
            if fc.material_index == M["lamp_pole"]:  # bevel-created faces default to slot 0 -> body paint
                fc.material_index = M[paint]
        for sx in (-1, 1):
            for sy in (-1, 1):
                _wheel(bm, sx * L * 0.32, sy * (W / 2 - 0.13))
        _quad_light(bm, L / 2 + 0.01, -W / 2 + 0.15, -W / 2 + 0.45, H - 0.35, H - 0.2, "headlight", 1)
        _quad_light(bm, L / 2 + 0.01, W / 2 - 0.45, W / 2 - 0.15, H - 0.35, H - 0.2, "headlight", 1)
        _quad_light(bm, -L / 2 - 0.01, -W / 2 + 0.1, -W / 2 + 0.4, H - 0.3, H - 0.15, "taillight", -1)
        _quad_light(bm, -L / 2 - 0.01, W / 2 - 0.4, W / 2 - 0.1, H - 0.3, H - 0.15, "taillight", -1)
    return f


def _cyl(bm, x, y, z0, z1, r, mat, seg=10):
    c = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=z1 - z0)
    bmesh.ops.translate(bm, verts=c["verts"], vec=(x, y, (z0 + z1) / 2))
    for f in {f for v in c["verts"] for f in v.link_faces}:
        f.material_index = M[mat]
        f.smooth = True


def _quad_y(bm, y, x0, x1, z0, z1, mat, facing=1):
    vs = [bm.verts.new((x0, y, z0)), bm.verts.new((x1, y, z0)), bm.verts.new((x1, y, z1)), bm.verts.new((x0, y, z1))]
    f = bm.faces.new(vs if facing > 0 else vs[::-1])
    f.material_index = M[mat]


def hydrant(bm):
    _cyl(bm, 0, 0, 0.0, 0.62, 0.11, "hydrant_red")
    _cyl(bm, 0, 0, 0.62, 0.70, 0.13, "hydrant_red")
    _box(bm, 0, 0, 0.45, 0.34, 0.10, 0.10, "hydrant_red")  # side nozzles
    _box(bm, 0, 0, 0.30, 0.10, 0.22, 0.14, "hydrant_red")  # pumper port


def bench(bm):  # seat faces +X? no: back to the road, seat toward +X... slats along Y
    for i in range(4):
        _box(bm, 0.0, 0, 0.45, 0.45, 1.6, 0.04, "wood_bench")  # seat (one block, slat look via texture)
        break
    _box(bm, -0.22, 0, 0.72, 0.04, 1.6, 0.34, "wood_bench")   # back
    for sy in (-0.7, 0.7):
        _box(bm, 0, sy, 0.22, 0.4, 0.05, 0.44, "metal_steel")  # legs
        _box(bm, -0.2, sy, 0.45, 0.05, 0.05, 0.5, "metal_steel")


def trash_bin(bm):
    _cyl(bm, 0, 0, 0.0, 0.95, 0.27, "bin_green", seg=12)
    _cyl(bm, 0, 0, 0.95, 1.02, 0.29, "metal_steel", seg=12)


def signal(bm):  # mast arm along +X over the road, signal head faces +Y (toward approaching traffic)
    _box(bm, 0, 0, 3.4, 0.22, 0.22, 6.8, "metal_signal", taper=0.7)
    _box(bm, 2.6, 0, 6.3, 5.2, 0.12, 0.12, "metal_signal")
    for hx in (2.2, 4.4):  # two heads
        _box(bm, hx, 0.0, 5.55, 0.42, 0.34, 1.15, "metal_signal")
        _quad_y(bm, 0.176, hx - 0.12, hx + 0.12, 5.88, 6.06, "signal_red", 1)
        _quad_y(bm, 0.176, hx - 0.12, hx + 0.12, 5.12, 5.30, "signal_green", 1)
    _box(bm, 5.1, 0, 5.9, 0.8, 0.04, 0.3, "metal_signal")  # street-name plate


def pedestrian(ci):
    def f(bm):
        for sy in (-0.09, 0.09):
            _box(bm, 0, sy, 0.43, 0.15, 0.15, 0.86, "ped_pants")      # legs
            _box(bm, 0, sy * 2.3, 1.12, 0.1, 0.1, 0.55, f"ped_cloth_{ci}")  # arms
        _box(bm, 0, 0, 1.18, 0.24, 0.44, 0.58, f"ped_cloth_{ci}", taper=0.9)  # torso
        sph = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=0.11)
        bmesh.ops.translate(bm, verts=sph["verts"], vec=(0, 0, 1.58))
        for fc in {fc for v in sph["verts"] for fc in v.link_faces}:
            fc.material_index = M["ped_skin"]
            fc.smooth = True
    return f


def protos():
    coll = bpy.data.collections.get("prop_protos")
    if coll:
        return coll
    coll = bpy.data.collections.new("prop_protos")
    bpy.context.scene.collection.children.link(coll)
    coll.hide_render = True
    _proto("00_lamp", lamp, coll)
    bodies = [("sedan", (4.6, 1.8, 1.0, 0.45, 2.4, -0.2)), ("suv", (4.8, 1.95, 1.15, 0.6, 2.8, -0.3)),
              ("van", (5.4, 2.0, 1.25, 0.95, 3.6, -0.6))]
    k = 1
    for name, dims in bodies:       # index = 1 + type*8 + paint (matches geom/props.py)
        for ci in range(len(materials.PAINTS)):
            _proto(f"{k:02d}_{name}_{ci}", car(*dims, paint=f"car_paint_{ci}"), coll)
            k += 1
    for name, fn in (("hydrant", hydrant), ("bench", bench), ("bin", trash_bin), ("signal", signal)):
        _proto(f"{k:02d}_{name}", fn, coll)  # 25 hydrant, 26 bench, 27 bin, 28 signal (matches geom/props.py)
        k += 1
    for ci in range(len(materials.PED_CLOTH)):  # 29..34 pedestrians
        _proto(f"{k:02d}_ped_{ci}", pedestrian(ci), coll)
        k += 1
    return coll


def node_group():
    ng = bpy.data.node_groups.get("prop_instancer")
    if ng:
        return ng
    ng = bpy.data.node_groups.new("prop_instancer", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    ci = N.new("GeometryNodeCollectionInfo")
    ci.inputs["Collection"].default_value = protos()
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    iop = N.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True
    a_cls = N.new("GeometryNodeInputNamedAttribute")
    a_cls.data_type = "INT"
    a_cls.inputs["Name"].default_value = "cls"
    a_rot = N.new("GeometryNodeInputNamedAttribute")
    a_rot.data_type = "FLOAT"
    a_rot.inputs["Name"].default_value = "rot"
    comb = N.new("ShaderNodeCombineXYZ")
    L.new(gi.outputs["Geometry"], iop.inputs["Points"])
    L.new(ci.outputs["Instances"], iop.inputs["Instance"])
    L.new(a_cls.outputs["Attribute"], iop.inputs["Instance Index"])
    L.new(a_rot.outputs["Attribute"], comb.inputs["Z"])
    L.new(comb.outputs["Vector"], iop.inputs["Rotation"])
    L.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


def build(tile, scn, rep):
    for lod in ("lod1", "lod0"):
        f = PROC / "tiles" / tile["id"] / f"mesh_props_{lod}.npz"
        if not f.exists():
            continue
        d = np.load(f)
        n = len(d["verts"])
        if n == 0:
            continue
        me = bpy.data.meshes.new(f"props_{tile['name']}_{lod}")
        me.vertices.add(n)
        me.vertices.foreach_set("co", d["verts"].astype(np.float32).ravel())
        for key, typ in (("p_cls", "INT"), ("p_rot", "FLOAT"), ("p_paint", "FLOAT"), ("p_moving", "INT"),
                         ("p_kind", "INT")):
            me.attributes.new(key[2:], typ, "POINT").data.foreach_set("value", d[key].ravel())
        ob = bpy.data.objects.new(f"props_{tile['name']}_{lod}", me)
        ob.modifiers.new("instancer", "NODES").node_group = node_group()
        top = bpy.data.collections[f"tile_{tile['name']}_{lod.upper()}"]
        cname = f"Props_{tile['name']}" + ("" if lod == "lod1" else "_lod0")
        c = bpy.data.collections.get(cname) or bpy.data.collections.new(cname)
        if c.name not in top.children:
            top.children.link(c)
        c.objects.link(ob)
        ob["tile_id"], ob["layer"], ob["lod"] = tile["id"], "props", lod
        k = d["p_kind"]
        rep["objects"][ob.name] = {"instances": int(n), "lamps": int((k == 0).sum()), "cars": int((k == 1).sum()),
                                   "verts": int(n), "polys": 0, "tris": int((k == 0).sum() * 48 + (k == 1).sum() * 100 + (k >= 2).sum() * 80)}
