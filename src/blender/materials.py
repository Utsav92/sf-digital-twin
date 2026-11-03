"""Material library (procedural PBR, no image textures). Runs inside Blender.

Every layer maps a per-face class to a material slot via SLOTS[layer]; builders set material_index.
Materials are created once per .blend and reused (get_mat is idempotent).
"""
from __future__ import annotations

import bpy

# name: (base RGB, roughness, metallic, noise_scale (0 = none), noise_strength)
LIB = {
    # terrain / land
    "ground":       ((0.34, 0.31, 0.25), 0.95, 0.0, 0.08, 0.25),
    "seabed":       ((0.22, 0.24, 0.20), 1.00, 0.0, 0.03, 0.20),
    "beach":        ((0.76, 0.69, 0.52), 0.95, 0.0, 0.30, 0.15),
    "grass":        ((0.27, 0.42, 0.16), 0.90, 0.0, 0.12, 0.30),
    "park":         ((0.23, 0.40, 0.14), 0.90, 0.0, 0.10, 0.30),
    "forest":       ((0.12, 0.24, 0.09), 0.95, 0.0, 0.06, 0.35),
    "scrub":        ((0.35, 0.38, 0.20), 0.95, 0.0, 0.10, 0.30),
    "golf":         ((0.30, 0.50, 0.18), 0.85, 0.0, 0.05, 0.20),
    "cemetery":     ((0.30, 0.40, 0.20), 0.90, 0.0, 0.10, 0.20),
    "sport":        ((0.32, 0.48, 0.22), 0.85, 0.0, 0.00, 0.00),
    "paved":        ((0.42, 0.41, 0.40), 0.85, 0.0, 0.20, 0.15),
    "industrial":   ((0.45, 0.43, 0.40), 0.85, 0.0, 0.20, 0.15),
    "rail_yard":    ((0.36, 0.32, 0.28), 0.90, 0.0, 0.30, 0.20),
    "construction": ((0.52, 0.45, 0.35), 0.95, 0.0, 0.20, 0.20),
    "rock":         ((0.45, 0.42, 0.38), 0.90, 0.0, 0.25, 0.30),
    "wetland":      ((0.25, 0.32, 0.20), 0.70, 0.0, 0.10, 0.30),
    "residential":  ((0.40, 0.39, 0.36), 0.90, 0.0, 0.15, 0.15),
    "commercial":   ((0.44, 0.43, 0.41), 0.85, 0.0, 0.15, 0.15),
    # water
    "water_bay":    ((0.05, 0.13, 0.17), 0.05, 0.0, 0.00, 0.00),
    "water_lake":   ((0.06, 0.15, 0.14), 0.05, 0.0, 0.00, 0.00),
    # roads & rail
    "road_motorway":    ((0.20, 0.20, 0.21), 0.80, 0.0, 0.40, 0.08),
    "road_arterial":    ((0.18, 0.18, 0.19), 0.80, 0.0, 0.40, 0.08),
    "road_local":       ((0.22, 0.22, 0.22), 0.85, 0.0, 0.40, 0.08),
    "road_service":     ((0.30, 0.29, 0.28), 0.85, 0.0, 0.40, 0.08),
    "path":             ((0.55, 0.52, 0.46), 0.90, 0.0, 0.30, 0.10),
    "sidewalk":         ((0.62, 0.61, 0.58), 0.85, 0.0, 0.40, 0.08),
    "bridge_deck":      ((0.30, 0.30, 0.31), 0.70, 0.0, 0.30, 0.08),
    "bridge_struct":    ((0.55, 0.55, 0.56), 0.60, 0.2, 0.00, 0.00),
    "ggb_orange":       ((0.75, 0.20, 0.08), 0.55, 0.1, 0.00, 0.00),
    "rail_track":       ((0.25, 0.22, 0.20), 0.70, 0.3, 0.50, 0.15),
    "rail_cable_car":   ((0.35, 0.28, 0.20), 0.70, 0.3, 0.50, 0.15),
    "pier":             ((0.48, 0.45, 0.40), 0.85, 0.0, 0.30, 0.15),
    # buildings
    "bldg_wall":        ((0.70, 0.67, 0.62), 0.85, 0.0, 0.00, 0.00),
    "bldg_wall_tall":   ((0.55, 0.60, 0.64), 0.30, 0.3, 0.00, 0.00),
    "bldg_roof":        ((0.40, 0.39, 0.38), 0.90, 0.0, 0.00, 0.00),
    "bldg_roof_pitched": ((0.45, 0.30, 0.25), 0.80, 0.0, 0.00, 0.00),
    # vegetation
    "tree_trunk":       ((0.25, 0.18, 0.12), 0.95, 0.0, 0.00, 0.00),
    "tree_crown":       ((0.16, 0.30, 0.11), 0.90, 0.0, 0.00, 0.00),
    "tree_conifer":     ((0.10, 0.22, 0.10), 0.90, 0.0, 0.00, 0.00),
    "tree_palm":        ((0.25, 0.38, 0.15), 0.85, 0.0, 0.00, 0.00),
    # landmarks
    "concrete":         ((0.68, 0.66, 0.62), 0.85, 0.0, 0.00, 0.00),
    "white_stone":      ((0.85, 0.84, 0.80), 0.70, 0.0, 0.00, 0.00),
    "glass":            ((0.30, 0.40, 0.48), 0.10, 0.6, 0.00, 0.00),
    "gold":             ((0.83, 0.65, 0.25), 0.35, 1.0, 0.00, 0.00),
    "copper_green":     ((0.30, 0.55, 0.45), 0.60, 0.3, 0.00, 0.00),
    "sutro_red":        ((0.70, 0.12, 0.08), 0.60, 0.3, 0.00, 0.00),
    "sutro_white":      ((0.85, 0.85, 0.85), 0.60, 0.3, 0.00, 0.00),
    "stadium_brick":    ((0.55, 0.28, 0.20), 0.85, 0.0, 0.00, 0.00),
    "terracotta":       ((0.70, 0.45, 0.30), 0.80, 0.0, 0.00, 0.00),
}

SLOTS = {
    "terrain": ["ground", "seabed", "beach", "grass", "park", "forest", "scrub", "golf", "cemetery", "sport",
                "paved", "industrial", "rail_yard", "construction", "rock", "wetland", "residential",
                "commercial"],
    "water": ["water_bay", "water_lake"],
    "roads": ["road_motorway", "road_arterial", "road_local", "road_service", "path", "sidewalk",
              "bridge_deck", "bridge_struct", "pier"],
    "rail": ["rail_track", "rail_cable_car", "bridge_struct"],
    "buildings": ["bldg_wall", "bldg_roof", "bldg_wall_tall", "bldg_roof_pitched"],
    "trees": ["tree_trunk", "tree_crown", "tree_conifer", "tree_palm"],
}


MATLIB = None


def _from_library(name):
    """Link `name` from the shared material library (out/city/sf_materials.blend) if it exists."""
    global MATLIB
    from bpy_common import ROOT
    lib = ROOT / "out/city/sf_materials.blend"
    if not lib.exists():
        return None
    with bpy.data.libraries.load(str(lib), link=True, relative=True) as (src, dst):
        if name not in src.materials:
            return None
        dst.materials = [name]
    return dst.materials[0]


def get_mat(name: str, local: bool = False) -> bpy.types.Material:
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    if not local:  # tiles link shared materials -> textures load once per render, not once per tile
        m = _from_library(name)
        if m is not None:
            return m
    import materials_pbr  # textured (CC0) game-look materials take precedence when textures are present
    m = materials_pbr.get(name)
    if m is not None:
        return m
    if name in SPECIAL:
        return SPECIAL[name](name)
    return get_mat_basic(name, *LIB[name][:2])


def get_mat_basic(name: str, rgb=None, rough=None) -> bpy.types.Material:
    _rgb, _rough, metal, nscale, nstr = LIB[name]
    rgb = rgb or _rgb
    rough = _rough if rough is None else rough
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    m.roughness = rough
    m.metallic = metal
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if nscale > 0:  # world-space noise variation, scale in 1/m
        tc = nt.nodes.new("ShaderNodeNewGeometry")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = nscale
        nz.inputs["Detail"].default_value = 4.0
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = nstr
        mix.inputs["A"].default_value = (*rgb, 1)
        nt.links.new(tc.outputs["Position"], nz.inputs["Vector"])
        nt.links.new(nz.outputs["Color"], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    if name.startswith("water"):
        bsdf.inputs["IOR"].default_value = 1.33
        try:
            bsdf.inputs["Coat Weight"].default_value = 0.3
        except KeyError:
            pass
    m["sf_material"] = name
    return m


def assign_slots(me: bpy.types.Mesh, layer: str) -> None:
    for n in SLOTS[layer]:
        me.materials.append(get_mat(n))


def hypsometric_override() -> bpy.types.Material:
    """Elevation-coloured material (world Z) for hillshade verification renders."""
    m = bpy.data.materials.get("hypso") or bpy.data.materials.new("hypso")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -40
    mr.inputs["From Max"].default_value = 300
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    stops = [(0.0, (0.02, 0.05, 0.20)), (0.115, (0.10, 0.30, 0.55)), (0.12, (0.20, 0.45, 0.18)),
             (0.30, (0.55, 0.62, 0.30)), (0.55, (0.62, 0.48, 0.30)), (0.80, (0.55, 0.42, 0.35)),
             (1.0, (0.95, 0.95, 0.95))]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for p, c in stops[1:-1]:
        e = cr.elements.new(p)
        e.color = (*c, 1)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


# ---------------------------------------------------------------- Phase 10: procedural PBR specials
SF_PASTELS = [(0.86, 0.84, 0.78), (0.93, 0.91, 0.86), (0.80, 0.74, 0.64), (0.72, 0.78, 0.80),
              (0.78, 0.82, 0.74), (0.90, 0.84, 0.70), (0.84, 0.76, 0.74), (0.66, 0.66, 0.64),
              (0.95, 0.95, 0.93), (0.74, 0.70, 0.66)]


def globals_group():
    """Shared shader group 'SF_Globals' -> night, wetness. Reads scene custom properties sf_night / sf_wetness
    through View Layer attribute lookups, so a render/master scene controls materials that live in linked
    (read-only) tile libraries."""
    g = bpy.data.node_groups.get("SF_Globals")
    if g:
        return g
    g = bpy.data.node_groups.new("SF_Globals", "ShaderNodeTree")
    for n in ("night", "wetness"):
        g.interface.new_socket(name=n, in_out="OUTPUT", socket_type="NodeSocketFloat")
    out = g.nodes.new("NodeGroupOutput")
    for i, n in enumerate(("night", "wetness")):
        a = g.nodes.new("ShaderNodeAttribute")
        a.attribute_type = "VIEW_LAYER"
        a.attribute_name = f"sf_{n}"
        g.links.new(a.outputs["Fac"], out.inputs[i])
    return g


def set_globals(night=0.0, wetness=0.0, scn=None):
    scn = scn or bpy.context.scene
    scn["sf_night"] = float(night)
    scn["sf_wetness"] = float(wetness)


def _math(nt, op, a, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def _hash1d(nt, w):
    n = nt.nodes.new("ShaderNodeTexWhiteNoise")
    n.noise_dimensions = "1D"
    nt.links.new(w, n.inputs["W"])
    return n.outputs["Value"]


def facade_material(name, tall):
    """Walls: per-building tint (hash of face attribute 'bid'), procedural window grid from metre-scale UVs,
    random lit windows at night (SF_Globals.night). tall=True -> glass curtain wall with mullions."""
    m = bpy.data.materials.new(name)
    m["sf_material"] = name
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UVMap"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uvn.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs["X"], sep.outputs["Y"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "bid"
    bidh = _hash1d(nt, attr.outputs["Fac"])
    bay, floor_h = (1.6, 3.9) if tall else (2.8, 3.3)
    # window mask
    uc = _math(nt, "FRACT", _math(nt, "DIVIDE", u, bay))
    vc = _math(nt, "FRACT", _math(nt, "DIVIDE", v, floor_h))
    lo_u, hi_u, lo_v, hi_v = (0.03, 0.97, 0.04, 0.96) if tall else (0.22, 0.78, 0.30, 0.85)
    mu = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", uc, lo_u), _math(nt, "LESS_THAN", uc, hi_u))
    mv = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", vc, lo_v), _math(nt, "LESS_THAN", vc, hi_v))
    above = _math(nt, "GREATER_THAN", v, 0.9 if tall else 2.6)
    mask = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", mu, mv), above)
    # wall colour: palette by building hash (stucco) or blue-grey glass curtain
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    pal = SF_PASTELS if not tall else [(0.10, 0.11, 0.12), (0.16, 0.16, 0.17), (0.22, 0.22, 0.21),
                                       (0.13, 0.15, 0.17), (0.30, 0.30, 0.29)]  # mullion / spandrel colours
    els = ramp.color_ramp.elements
    els[0].color = (*pal[0], 1)
    els[1].position, els[1].color = 1.0 - 1e-3, (*pal[-1], 1)
    for i, c in enumerate(pal[1:-1], 1):
        e = els.new(i / len(pal))
        e.color = (*c, 1)
    nt.links.new(bidh, ramp.inputs["Fac"])
    glass = (0.05, 0.07, 0.09, 1) if not tall else (0.26, 0.30, 0.33, 1)
    mixc = nt.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    nt.links.new(mask, mixc.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], mixc.inputs["A"])
    mixc.inputs["B"].default_value = glass
    if tall:  # per-tower glass tint: blue / green / bronze / silver / dark
        gr = nt.nodes.new("ShaderNodeValToRGB")
        gr.color_ramp.interpolation = "CONSTANT"
        tints = [(0.20, 0.27, 0.34), (0.22, 0.30, 0.28), (0.33, 0.27, 0.20), (0.36, 0.37, 0.38), (0.12, 0.14, 0.17)]
        e = gr.color_ramp.elements
        e[0].color = (*tints[0], 1)
        e[1].position, e[1].color = 1 - 1e-3, (*tints[-1], 1)
        for i, c in enumerate(tints[1:-1], 1):
            e.new(i / len(tints)).color = (*c, 1)
        nt.links.new(_hash1d(nt, _math(nt, "ADD", attr.outputs["Fac"], 0.71)), gr.inputs["Fac"])
        nt.links.new(gr.outputs["Color"], mixc.inputs["B"])
    nt.links.new(mixc.outputs["Result"], bsdf.inputs["Base Color"])
    rough = _math(nt, "ADD", 0.85 if not tall else 0.45, _math(nt, "MULTIPLY", mask, -0.78 if not tall else -0.41))
    nt.links.new(rough, bsdf.inputs["Roughness"])
    met = _math(nt, "MULTIPLY", mask, 0.0 if not tall else 0.65)
    nt.links.new(met, bsdf.inputs["Metallic"])
    # night: random ~35% of windows lit, warm
    wid = _math(nt, "ADD", _math(nt, "FLOOR", _math(nt, "DIVIDE", u, bay)),
                _math(nt, "MULTIPLY", _math(nt, "FLOOR", _math(nt, "DIVIDE", v, floor_h)), 131.0))
    wid = _math(nt, "ADD", wid, _math(nt, "MULTIPLY", attr.outputs["Fac"], 0.618))
    lit = _math(nt, "GREATER_THAN", _hash1d(nt, wid), 0.85)
    gg = nt.nodes.new("ShaderNodeGroup")
    gg.node_tree = globals_group()
    em = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", mask, lit), gg.outputs["night"])
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.72, 0.42, 1)
    nt.links.new(_math(nt, "MULTIPLY", em, 2.2), bsdf.inputs["Emission Strength"])
    return m


def roof_material(name, pitched):
    m = bpy.data.materials.new(name)
    m["sf_material"] = name
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "bid"
    h = _hash1d(nt, attr.outputs["Fac"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    a, b = ((0.42, 0.25, 0.20), (0.28, 0.28, 0.30)) if pitched else ((0.30, 0.30, 0.31), (0.62, 0.60, 0.56))
    ramp.color_ramp.elements[0].color = (*a, 1)
    ramp.color_ramp.elements[1].color = (*b, 1)
    nt.links.new(h, ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return m


def water_material(name, rgb):
    m = bpy.data.materials.new(name)
    m["sf_material"] = name
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = 0.14
    bsdf.inputs["IOR"].default_value = 1.33
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.18
    nz.inputs["Detail"].default_value = 10
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def road_material(name, rgb, rough):
    """Asphalt with world-space grain; wetness (SF_Globals) darkens it and drops roughness (puddle sheen)."""
    m = get_mat_basic(name, rgb, rough)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    gg = nt.nodes.new("ShaderNodeGroup")
    gg.node_tree = globals_group()
    nt.links.new(_math(nt, "SUBTRACT", rough, _math(nt, "MULTIPLY", gg.outputs["wetness"], rough - 0.08)),
                 bsdf.inputs["Roughness"])
    return m


SPECIAL = {
    "bldg_wall": lambda n: facade_material(n, False),
    "bldg_wall_tall": lambda n: facade_material(n, True),
    "bldg_roof": lambda n: roof_material(n, False),
    "bldg_roof_pitched": lambda n: roof_material(n, True),
    "water_bay": lambda n: water_material(n, (0.025, 0.08, 0.11)),
    "water_lake": lambda n: water_material(n, (0.05, 0.12, 0.10)),
    "road_motorway": lambda n: road_material(n, (0.20, 0.20, 0.21), 0.8),
    "road_arterial": lambda n: road_material(n, (0.18, 0.18, 0.19), 0.8),
    "road_local": lambda n: road_material(n, (0.22, 0.22, 0.22), 0.85),
}


# ---------------------------------------------------------------- props: cars + street lamps
CAR_COLORS = [(0.85, 0.85, 0.83), (0.04, 0.04, 0.045), (0.55, 0.56, 0.57), (0.28, 0.29, 0.30), (0.06, 0.10, 0.22),
              (0.45, 0.04, 0.03), (0.75, 0.75, 0.76), (0.12, 0.20, 0.14), (0.52, 0.42, 0.30), (0.02, 0.15, 0.35)]


def car_paint(name):
    m = bpy.data.materials.new(name)
    m["sf_material"] = name
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_type = "INSTANCER"
    a.attribute_name = "paint"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    e = ramp.color_ramp.elements
    e[0].color = (*CAR_COLORS[0], 1)
    e[1].position, e[1].color = 1 - 1e-3, (*CAR_COLORS[-1], 1)
    for i, c in enumerate(CAR_COLORS[1:-1], 1):
        e.new(i / len(CAR_COLORS)).color = (*c, 1)
    nt.links.new(a.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Metallic"].default_value = 0.4
    try:
        b.inputs["Coat Weight"].default_value = 0.8
        b.inputs["Coat Roughness"].default_value = 0.05
    except KeyError:
        pass
    return m


def night_emitter(name, rgb, strength, base=(0.9, 0.9, 0.85), day_strength=0.0):
    """Emission scaled by SF_Globals.night (headlights, tail lights, lamp heads)."""
    m = bpy.data.materials.new(name)
    m["sf_material"] = name
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = 0.2
    b.inputs["Emission Color"].default_value = (*rgb, 1)
    gg = nt.nodes.new("ShaderNodeGroup")
    gg.node_tree = globals_group()
    s = _math(nt, "ADD", _math(nt, "MULTIPLY", gg.outputs["night"], strength), day_strength)
    nt.links.new(s, b.inputs["Emission Strength"])
    return m


LIB.update({
    "car_glass": ((0.03, 0.035, 0.04), 0.05, 0.3, 0.0, 0.0),
    "car_tire": ((0.03, 0.03, 0.03), 0.9, 0.0, 0.0, 0.0),
    "lamp_pole": ((0.18, 0.19, 0.20), 0.5, 0.7, 0.0, 0.0),
})
SPECIAL.update({
    "car_paint": car_paint,
    "headlight": lambda n: night_emitter(n, (1.0, 0.95, 0.85), 40.0),
    "taillight": lambda n: night_emitter(n, (1.0, 0.05, 0.02), 15.0, base=(0.5, 0.02, 0.02), day_strength=0.3),
    "lamp_glow": lambda n: night_emitter(n, (1.0, 0.72, 0.42), 60.0),
})
PAINTS = [(0.86, 0.86, 0.84), (0.03, 0.03, 0.035), (0.55, 0.56, 0.57), (0.26, 0.27, 0.28), (0.05, 0.09, 0.22),
          (0.50, 0.03, 0.03), (0.70, 0.71, 0.72), (0.10, 0.17, 0.13)]


def paint_mat(name, rgb):
    m = bpy.data.materials.new(name)
    m["sf_material"] = name
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Metallic"].default_value = 0.05
    try:
        b.inputs["Coat Weight"].default_value = 0.45
        b.inputs["Coat Roughness"].default_value = 0.08
    except KeyError:
        pass
    return m


for _i, _c in enumerate(PAINTS):
    SPECIAL[f"car_paint_{_i}"] = (lambda c: (lambda n: paint_mat(n, c)))(_c)
SLOTS["props"] = ["lamp_pole", "lamp_glow", "car_glass", "car_tire", "headlight", "taillight"] + \
    [f"car_paint_{i}" for i in range(len(PAINTS))]
