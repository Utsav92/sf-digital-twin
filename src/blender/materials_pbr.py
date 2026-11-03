"""Textured PBR materials (CC0 Poly Haven sets, data/raw/textures) for the 'game look'. Runs inside Blender.

All meshes carry metre-scale UVs ('UVMap': walls = metres along facade x height; everything else = city-frame
XY metres), so a texture set repeats every `size_m` metres via a Mapping node.
materials.get_mat() dispatches here first; returns None for names not handled.
"""
import json

import bpy

from bpy_common import ROOT

_MAN = None


def man():
    global _MAN
    if _MAN is None:
        p = ROOT / "data/raw/textures/textures_manifest.json"
        _MAN = json.loads(p.read_text())["sets"] if p.exists() else {}
    return _MAN


def _img(path, noncolor):
    p = str(ROOT / path)
    im = bpy.data.images.load(p, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
    return im


def texset(nt, role, scale_mul=1.0, uv=None):
    """Image nodes for a texture set -> (color socket, roughness socket, normal socket)."""
    s = man()[role]
    if uv is None:
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = "UVMap"
        uv = uvn.outputs["UV"]
    mp = nt.nodes.new("ShaderNodeMapping")
    k = 1.0 / (s["size_m"] * scale_mul)
    mp.inputs["Scale"].default_value = (k, k, k)
    nt.links.new(uv, mp.inputs["Vector"])
    out = {}
    for short, nc in (("diff", False), ("rough", True), ("nor", True)):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = _img(s["maps"][short], nc)
        t.interpolation = "Smart" if short == "diff" else "Linear"
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        out[short] = t.outputs["Color"]
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.8
    nt.links.new(out["nor"], nm.inputs["Color"])
    return out["diff"], out["rough"], nm.outputs["Normal"]


def _new(name):
    m = bpy.data.materials.new(name)
    m["sf_material"] = name
    m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes["Principled BSDF"]


def _tint(nt, col, rgb, amount=0.85):
    """Multiply a texture by an RGB tint (normalised so mid-grey textures land on the tint)."""
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = amount
    nt.links.new(col, mix.inputs["A"])
    mix.inputs["B"].default_value = (*[min(1.0, c * 2.2) for c in rgb], 1)
    return mix.outputs["Result"]


def ground(name, role, rgb, amount=0.7, scale_mul=1.0, rough_mul=1.0):
    m, nt, b = _new(name)
    c, r, n = texset(nt, role, scale_mul)
    nt.links.new(_tint(nt, c, rgb, amount), b.inputs["Base Color"])
    from materials import _math
    nt.links.new(_math(nt, "MULTIPLY", r, rough_mul), b.inputs["Roughness"])
    nt.links.new(n, b.inputs["Normal"])
    return m


def road(name, rgb, scale_mul=1.0):
    """Asphalt + wetness (scene property sf_wetness via SF_Globals): darker, glossy, puddles in noise lows."""
    from materials import _math, globals_group
    m, nt, b = _new(name)
    c, r, n = texset(nt, "asphalt", scale_mul)
    base = _tint(nt, c, rgb, 0.6)
    gg = nt.nodes.new("ShaderNodeGroup")
    gg.node_tree = globals_group()
    wet = gg.outputs["wetness"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.35
    nz.inputs["Detail"].default_value = 6
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    puddle = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", nz.outputs["Fac"], 0.55), wet)
    dark = nt.nodes.new("ShaderNodeMix")
    dark.data_type = "RGBA"
    dark.blend_type = "MULTIPLY"
    nt.links.new(_math(nt, "MULTIPLY", wet, 0.55), dark.inputs["Factor"])
    nt.links.new(base, dark.inputs["A"])
    dark.inputs["B"].default_value = (0.35, 0.35, 0.37, 1)
    nt.links.new(dark.outputs["Result"], b.inputs["Base Color"])
    rough = _math(nt, "SUBTRACT", r, _math(nt, "MULTIPLY", wet, 0.45))
    rough = _math(nt, "MAXIMUM", _math(nt, "SUBTRACT", rough, _math(nt, "MULTIPLY", puddle, 1.0)), 0.03)
    nt.links.new(rough, b.inputs["Roughness"])
    # puddles flatten the normal
    nm = nt.nodes.new("ShaderNodeMix")
    nm.data_type = "VECTOR"
    nt.links.new(puddle, nm.inputs["Factor"])
    nt.links.new(n, nm.inputs["A"])
    nt.links.new(geo.outputs["Normal"], nm.inputs["B"])
    nt.links.new(nm.outputs["Result"], b.inputs["Normal"])
    return m


def facade(name, tall):
    """Facade: textured plaster tinted by per-building palette (or brick for ~22% of low-rise), reflective
    windows on a metre-scale grid, night emission from SF_Globals.night."""
    import materials as M
    m = M.facade_material(name, tall)  # procedural base graph (palette, windows, emission)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    mixc = [n for n in nt.nodes if n.bl_idname == "ShaderNodeMix" and n.data_type == "RGBA"][0]
    pal = mixc.inputs["A"].links[0].from_socket  # palette colour
    uvn = [n for n in nt.nodes if n.bl_idname == "ShaderNodeUVMap"][0]
    c, r, n = texset(nt, "plaster" if not tall else "concrete", 1.0, uv=uvn.outputs["UV"])
    tinted = nt.nodes.new("ShaderNodeMix")
    tinted.data_type = "RGBA"
    tinted.blend_type = "MULTIPLY"
    tinted.inputs["Factor"].default_value = 1.0
    nt.links.new(pal, tinted.inputs["A"])
    gain = nt.nodes.new("ShaderNodeMix")
    gain.data_type = "RGBA"
    gain.blend_type = "MULTIPLY"
    gain.inputs["Factor"].default_value = 1.0
    nt.links.new(c, gain.inputs["A"])
    gain.inputs["B"].default_value = (1.9, 1.9, 1.9, 1)
    nt.links.new(gain.outputs["Result"], tinted.inputs["B"])
    wall = tinted.outputs["Result"]
    if not tall:  # brick for a hashed subset of buildings
        cb, rb, nb = texset(nt, "brick", 1.0, uv=uvn.outputs["UV"])
        attr = [x for x in nt.nodes if x.bl_idname == "ShaderNodeAttribute"][0]
        h = M._hash1d(nt, M._math(nt, "ADD", attr.outputs["Fac"], 0.37))
        isb = M._math(nt, "LESS_THAN", h, 0.22)
        sel = nt.nodes.new("ShaderNodeMix")
        sel.data_type = "RGBA"
        nt.links.new(isb, sel.inputs["Factor"])
        nt.links.new(wall, sel.inputs["A"])
        nt.links.new(cb, sel.inputs["B"])
        wall = sel.outputs["Result"]
        nsel = nt.nodes.new("ShaderNodeMix")
        nsel.data_type = "VECTOR"
        nt.links.new(isb, nsel.inputs["Factor"])
        nt.links.new(n, nsel.inputs["A"])
        nt.links.new(nb, nsel.inputs["B"])
        n = nsel.outputs["Result"]
    nt.links.new(wall, mixc.inputs["A"])
    # windows flatten the normal (glass), walls keep the texture normal
    mask_src = mixc.inputs["Factor"].links[0].from_socket
    nmx = nt.nodes.new("ShaderNodeMix")
    nmx.data_type = "VECTOR"
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nt.links.new(mask_src, nmx.inputs["Factor"])
    nt.links.new(n, nmx.inputs["A"])
    nt.links.new(geo.outputs["Normal"], nmx.inputs["B"])
    nt.links.new(nmx.outputs["Result"], b.inputs["Normal"])
    b.inputs["Specular IOR Level"].default_value = 0.6
    return m


def roof(name, pitched):
    import materials as M
    m = M.roof_material(name, pitched)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    c, r, n = texset(nt, "roof_tiles" if pitched else "concrete", 1.0)
    ramp_out = b.inputs["Base Color"].links[0].from_socket
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(ramp_out, mix.inputs["A"])
    g = nt.nodes.new("ShaderNodeMix")
    g.data_type = "RGBA"
    g.blend_type = "MULTIPLY"
    g.inputs["Factor"].default_value = 1.0
    nt.links.new(c, g.inputs["A"])
    g.inputs["B"].default_value = (2.0, 2.0, 2.0, 1) if not pitched else (1.4, 1.4, 1.4, 1)
    nt.links.new(g.outputs["Result"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    nt.links.new(r, b.inputs["Roughness"])
    nt.links.new(n, b.inputs["Normal"])
    return m


def glass_tower(name):
    m, nt, b = _new(name)
    b.inputs["Base Color"].default_value = (0.12, 0.17, 0.22, 1)
    b.inputs["Metallic"].default_value = 0.85
    b.inputs["Roughness"].default_value = 0.06
    return m


def foliage(name, rgb, var=0.35):
    """Leaves: object-space colour variation + a little translucency (backlit glow) and soft sheen."""
    from materials import _math  # noqa: F401
    m, nt, b = _new(name)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.6
    nz.inputs["Detail"].default_value = 3
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*[c * (1 - var) for c in rgb], 1)
    ramp.color_ramp.elements[1].color = (*[min(1, c * (1 + var)) for c in rgb], 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.65
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    nt.links.new(ramp.outputs["Color"], tr.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.25
    out = nt.nodes["Material Output"]
    nt.links.new(b.outputs["BSDF"], mix.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return m


BUILDERS = {
    "tree_crown": lambda n: foliage(n, (0.13, 0.25, 0.08)),
    "tree_conifer": lambda n: foliage(n, (0.07, 0.16, 0.07), 0.25),
    "tree_palm": lambda n: foliage(n, (0.20, 0.32, 0.11)),
    "road_motorway": lambda n: road(n, (0.20, 0.20, 0.21)),
    "road_arterial": lambda n: road(n, (0.19, 0.19, 0.20)),
    "road_local": lambda n: road(n, (0.22, 0.22, 0.22)),
    "road_service": lambda n: road(n, (0.27, 0.26, 0.25)),
    "bridge_deck": lambda n: road(n, (0.24, 0.24, 0.25)),
    "sidewalk": lambda n: ground(n, "concrete", (0.62, 0.61, 0.58), 0.5),
    "path": lambda n: ground(n, "gravel", (0.55, 0.52, 0.46), 0.5),
    "pier": lambda n: ground(n, "concrete", (0.45, 0.43, 0.40), 0.6),
    "paved": lambda n: ground(n, "concrete", (0.44, 0.43, 0.41), 0.6),
    "industrial": lambda n: ground(n, "concrete", (0.42, 0.41, 0.38), 0.6),
    "commercial": lambda n: ground(n, "concrete", (0.45, 0.44, 0.42), 0.6),
    "residential": lambda n: ground(n, "concrete", (0.42, 0.41, 0.38), 0.6),
    "ground": lambda n: ground(n, "gravel", (0.38, 0.35, 0.29), 0.7),
    "construction": lambda n: ground(n, "gravel", (0.50, 0.44, 0.35), 0.7),
    "rail_yard": lambda n: ground(n, "gravel", (0.36, 0.32, 0.28), 0.7),
    "grass": lambda n: ground(n, "grass", (0.26, 0.40, 0.15), 0.75),
    "park": lambda n: ground(n, "grass", (0.23, 0.40, 0.14), 0.75),
    "golf": lambda n: ground(n, "grass", (0.28, 0.48, 0.17), 0.8, 2.0),
    "sport": lambda n: ground(n, "grass", (0.30, 0.47, 0.20), 0.8, 2.0),
    "cemetery": lambda n: ground(n, "grass", (0.30, 0.40, 0.20), 0.75),
    "scrub": lambda n: ground(n, "grass", (0.34, 0.37, 0.20), 0.75),
    "forest": lambda n: ground(n, "forest", (0.20, 0.26, 0.13), 0.7),
    "wetland": lambda n: ground(n, "grass", (0.25, 0.32, 0.20), 0.7),
    "beach": lambda n: ground(n, "sand", (0.78, 0.71, 0.55), 0.5),
    "rock": lambda n: ground(n, "rock", (0.47, 0.44, 0.40), 0.5),
    "seabed": lambda n: ground(n, "sand", (0.25, 0.26, 0.22), 0.7),
    "bldg_wall": lambda n: facade(n, False),
    "bldg_wall_tall": lambda n: facade(n, True),
    "bldg_roof": lambda n: roof(n, False),
    "bldg_roof_pitched": lambda n: roof(n, True),
    "white_stone": lambda n: ground(n, "plaster", (0.86, 0.84, 0.80), 0.8),
    "concrete": lambda n: ground(n, "concrete", (0.66, 0.64, 0.60), 0.6),
    "terracotta": lambda n: ground(n, "plaster", (0.72, 0.48, 0.33), 0.9),
    "stadium_brick": lambda n: ground(n, "brick", (0.55, 0.30, 0.22), 0.3),
    "glass": glass_tower,
}


def get(name):
    if not man() or name not in BUILDERS:
        return None
    return BUILDERS[name](name)
