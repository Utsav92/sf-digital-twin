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
    _proto(f"0_broadleaf_{lod}", [(_cyl(0.06, 0, 0.45), "tree_trunk"),
                                  (_ico(1.0, 0.68, 0.35, 0 if lo else 1), "tree_crown")], coll)
    _proto(f"1_conifer_{lod}", [(_cyl(0.05, 0, 0.25), "tree_trunk"),
                                (_cone(0.9, 0.15, 1.0, 5 if lo else 8), "tree_conifer")], coll)
    _proto(f"2_palm_{lod}", [(_cyl(0.04, 0, 0.9), "tree_trunk"),
                             (_ico(1.0, 0.93, 0.18, 0), "tree_palm")], coll)
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
