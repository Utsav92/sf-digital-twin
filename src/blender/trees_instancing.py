"""Phase 8 (Blender side): tree point clouds + Geometry Nodes instancing of 3 low-poly prototypes.

Prototypes are unit-sized (crown radius 1, height 1) and live in collection 'tree_protos_<lod>' which is
NOT under the tile's top collection, so they never render at the origin; the GN modifier references them.
Instance index = point attribute 'cls' (0 broadleaf, 1 conifer, 2 palm); scale = 'scale'; Z rot = 'rot'.
"""
import math

import bmesh
import bpy
import numpy as np
from bpy_common import ROOT
import materials

PROC = ROOT / "data/processed"


def _proto(name, parts, coll):
    """parts: list of (bmesh-builder fn, material name)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    mats = []
    for fn, mat in parts:
        before = set(bm.faces)
        fn(bm)
        idx = len(mats)
        mats.append(mat)
        for f in set(bm.faces) - before:
            f.material_index = idx
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(materials.get_mat(m))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def _cyl(r, z0, z1, seg=5):
    def f(bm):
        res = bmesh.ops.create_cone(bm, cap_ends=False, segments=seg, radius1=r, radius2=r * 0.7, depth=z1 - z0)
        bmesh.ops.translate(bm, verts=res["verts"], vec=(0, 0, (z0 + z1) / 2))
    return f


def _ico(r, zc, sz=1.0, subdiv=1):
    def f(bm):
        res = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
        bmesh.ops.scale(bm, verts=res["verts"], vec=(r, r, r * sz))
        bmesh.ops.translate(bm, verts=res["verts"], vec=(0, 0, zc))
    return f


def _cone(r, z0, z1, seg=7):
    def f(bm):
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=0.0, depth=z1 - z0)
        bmesh.ops.translate(bm, verts=res["verts"], vec=(0, 0, (z0 + z1) / 2))
    return f


def _lobes(n_lobes, zc, sz, seed, detail=2):
    """Organic crown: several jittered, noise-displaced icosphere lobes, smooth shaded."""
    from mathutils import Vector, noise
    import random

    def f(bm):
        rnd = random.Random(seed)
        for k in range(n_lobes):
            r = 0.55 + 0.35 * rnd.random()
            c = Vector((rnd.uniform(-0.45, 0.45), rnd.uniform(-0.45, 0.45), zc + rnd.uniform(-0.12, 0.12)))
            res = bmesh.ops.create_icosphere(bm, subdivisions=detail, radius=r)
            for v in res["verts"]:
                d = 1.0 + 0.28 * noise.noise(v.co * 2.3 + Vector((seed, k, 0)))
                v.co = Vector((v.co.x * d + c.x, v.co.y * d + c.y, v.co.z * d * sz + c.z))
            for fc in {fc for v in res["verts"] for fc in v.link_faces}:
                fc.smooth = True
    return f


def _tiers(seed):
    from mathutils import Vector, noise

    def f(bm):
        for k, (z0, z1, r) in enumerate(((0.15, 0.55, 0.95), (0.40, 0.80, 0.72), (0.62, 1.0, 0.45))):
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=r, radius2=0.05, depth=z1 - z0)
            for v in res["verts"]:
                d = 1.0 + 0.18 * noise.noise(v.co * 4 + Vector((seed, k, 1)))
                v.co = Vector((v.co.x * d, v.co.y * d, v.co.z + (z0 + z1) / 2))
            for fc in {fc for v in res["verts"] for fc in v.link_faces}:
                fc.smooth = True
    return f


def _fronds(bm):
    import math as m
    for k in range(9):
        a = 2 * m.pi * k / 9
        ca, sa = m.cos(a), m.sin(a)
        pts = [(0.0, 0.92), (0.45, 0.97), (0.85, 0.88), (1.05, 0.72)]
        vs = []
        for (r, z) in pts:
            vs.append((bm.verts.new((ca * r - sa * 0.09, sa * r + ca * 0.09, z)),
                       bm.verts.new((ca * r + sa * 0.09, sa * r - ca * 0.09, z))))
        for (a0, b0), (a1, b1) in zip(vs[:-1], vs[1:]):
            fc = bm.faces.new((a0, b0, b1, a1))
            fc.smooth = True


def protos(lod):
    name = f"tree_protos_{lod}"
    coll = bpy.data.collections.get(name)
    if coll:
        return coll
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    coll.hide_render = True  # never rendered directly; referenced by the instancer
    lo = lod == "lod0"
    # unit trees: height 1.0, crown radius 1.0 in XY (scaled per point by (r, r, h))
    if lo:  # far LOD: cheap silhouettes
        _proto(f"0_broadleaf_{lod}", [(_cyl(0.06, 0, 0.45), "tree_trunk"),
                                      (_ico(1.0, 0.68, 0.35, 0), "tree_crown")], coll)
        _proto(f"1_conifer_{lod}", [(_cyl(0.05, 0, 0.25), "tree_trunk"),
                                    (_cone(0.9, 0.15, 1.0, 5), "tree_conifer")], coll)
        _proto(f"2_palm_{lod}", [(_cyl(0.04, 0, 0.9), "tree_trunk"), (_ico(1.0, 0.93, 0.18, 0), "tree_palm")], coll)
    else:   # near LOD: organic lobed crowns, tiered conifers, frond palms
        _proto(f"0_broadleaf_{lod}", [(_cyl(0.05, 0, 0.5, 7), "tree_trunk"),
                                      (_lobes(5, 0.68, 0.55, 3), "tree_crown")], coll)
        _proto(f"1_conifer_{lod}", [(_cyl(0.05, 0, 0.3, 7), "tree_trunk"), (_tiers(5), "tree_conifer")], coll)
        _proto(f"2_palm_{lod}", [(_cyl(0.035, 0, 0.92, 7), "tree_trunk"), (_fronds, "tree_palm")], coll)
    # palms: scale crown radius smaller relative to height is handled by data (crown_r)
    return coll


def node_group(lod):
    name = f"tree_instancer_{lod}"
    ng = bpy.data.node_groups.get(name)
    if ng:
        return ng
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N = ng.nodes
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    ci = N.new("GeometryNodeCollectionInfo")
    ci.inputs["Collection"].default_value = protos(lod)
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    ci.transform_space = "ORIGINAL"
    iop = N.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True

    def named(attr, dtype):
        n = N.new("GeometryNodeInputNamedAttribute")
        n.data_type = dtype
        n.inputs["Name"].default_value = attr
        return n
    a_cls, a_scale, a_rot = named("cls", "INT"), named("scale", "FLOAT_VECTOR"), named("rot", "FLOAT")
    comb = N.new("ShaderNodeCombineXYZ")
    L = ng.links
    L.new(gi.outputs["Geometry"], iop.inputs["Points"])
    L.new(ci.outputs["Instances"], iop.inputs["Instance"])
    L.new(a_cls.outputs["Attribute"], iop.inputs["Instance Index"])
    L.new(a_scale.outputs["Attribute"], iop.inputs["Scale"])
    L.new(a_rot.outputs["Attribute"], comb.inputs["Z"])
    L.new(comb.outputs["Vector"], iop.inputs["Rotation"])
    L.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return ng


def build(tile, scn, rep):
    for lod in ("lod1", "lod0"):
        f = PROC / "tiles" / tile["id"] / f"mesh_trees_{lod}.npz"
        if not f.exists():
            continue
        d = np.load(f)
        n = len(d["verts"])
        if n == 0:
            continue
        me = bpy.data.meshes.new(f"trees_{tile['name']}_{lod}")
        me.vertices.add(n)
        me.vertices.foreach_set("co", d["verts"].astype(np.float32).ravel())
        for key, typ in (("p_scale", "FLOAT_VECTOR"), ("p_cls", "INT"), ("p_rot", "FLOAT"), ("p_src", "INT")):
            a = me.attributes.new(key[2:], typ, "POINT")
            a.data.foreach_set("vector" if typ == "FLOAT_VECTOR" else "value", d[key].ravel())
        me.update()
        ob = bpy.data.objects.new(f"trees_{tile['name']}_{lod}", me)
        mod = ob.modifiers.new("instancer", "NODES")
        mod.node_group = node_group(lod)
        top = bpy.data.collections[f"tile_{tile['name']}_{lod.upper()}"]
        cname = f"Trees_{tile['name']}" + ("" if lod == "lod1" else "_lod0")
        c = bpy.data.collections.get(cname) or bpy.data.collections.new(cname)
        if c.name not in top.children:
            top.children.link(c)
        c.objects.link(ob)
        ob["tile_id"], ob["layer"], ob["lod"] = tile["id"], "trees", lod
        tris_per = {"lod1": (8 * 2 + 80, 8 + 16, 20 + 10), "lod0": (8 + 20, 6 + 10, 20 + 10)}[lod]
        cls = d["p_cls"]
        rep["objects"][ob.name] = {"instances": int(n), "verts": int(n), "polys": 0,
                                   "tris": int(sum(tris_per[k] * (cls == k).sum() for k in range(3)))}
