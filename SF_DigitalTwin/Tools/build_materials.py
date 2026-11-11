"""Create M_SF_Master + per-surface instances and reassign every imported tile/landmark mesh slot to them.
Slot materials are imported as MI_MAT_<Name>_<n>_TwoSided; <Name> picks the palette entry."""
import os, re, unreal
ONLY = [i for i in os.environ.get('SF_ONLY','').split(',') if i]
ar = unreal.AssetRegistryHelpers.get_asset_registry()
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
D = "/Game/Materials"

# name fragment -> (r,g,b, roughness, metallic). sRGB-ish values, matched in order.
PAL = [
 ("Glass_Curtain", (0.10,0.20,0.30, 0.05, 0.6)), ("Water_Bay", (0.05,0.20,0.30, 0.08, 0.0)), ("Water_Lake", (0.07,0.25,0.30, 0.1, 0.0)),
 ("InternationalOrange", (0.75,0.14,0.06, 0.45, 0.4)), ("Bridge_Steel", (0.45,0.47,0.5, 0.5, 0.6)), ("Bridge_Deck", (0.25,0.25,0.26, 0.85, 0.0)),
 ("Road_Asphalt", (0.07,0.07,0.075, 0.9, 0.0)), ("Sidewalk", (0.55,0.54,0.52, 0.9, 0.0)), ("Paving", (0.5,0.5,0.48, 0.9, 0.0)),
 ("Pier", (0.4,0.4,0.38, 0.9, 0.0)), ("Rail", (0.3,0.28,0.26, 0.95, 0.0)), ("Path", (0.5,0.45,0.35, 0.95, 0.0)),
 ("Facade_Brick", (0.45,0.2,0.15, 0.9, 0.0)), ("Facade_Stucco", (0.72,0.68,0.6, 0.9, 0.0)), ("Roof_Tile", (0.5,0.22,0.15, 0.85, 0.0)),
 ("Roof_Flat", (0.3,0.3,0.31, 0.9, 0.0)), ("Stone_White", (0.85,0.85,0.82, 0.8, 0.0)), ("Stone_Terracotta", (0.7,0.4,0.28, 0.85, 0.0)),
 ("Metal_Gold", (0.85,0.65,0.2, 0.3, 1.0)), ("Metal_Copper", (0.3,0.6,0.5, 0.4, 0.8)), ("Paint_SutroRed", (0.7,0.1,0.08, 0.5, 0.0)),
 ("Paint_White", (0.9,0.9,0.9, 0.5, 0.0)), ("Skin", (0.75,0.55,0.45, 0.7, 0.0)), ("Cloth_Blue", (0.12,0.2,0.45, 0.9, 0.0)), ("Cloth_Dark", (0.06,0.06,0.08, 0.9, 0.0)),
 ("Curb", (0.6,0.6,0.58, 0.9, 0.0)), ("MarkingWhite", (0.9,0.9,0.88, 0.6, 0.0)), ("MarkingYellow", (0.9,0.68,0.08, 0.6, 0.0)), ("Crosswalk", (0.9,0.9,0.88, 0.6, 0.0)),
 ("RailingMetal", (0.12,0.12,0.13, 0.5, 0.7)), ("Sill", (0.7,0.68,0.62, 0.85, 0.0)), ("BldgTrim", (0.74,0.71,0.65, 0.85, 0.0)), ("BalconySlab", (0.58,0.58,0.56, 0.9, 0.0)), ("Concrete", (0.55,0.55,0.55, 0.9, 0.0)),
 ("Grass", (0.15,0.32,0.1, 1.0, 0.0)), ("Ground_Sand", (0.76,0.68,0.5, 1.0, 0.0)), ("Ground_Seabed", (0.2,0.22,0.2, 1.0, 0.0)),
 ("ForestFloor", (0.12,0.2,0.08, 1.0, 0.0)), ("Scrub", (0.3,0.35,0.18, 1.0, 0.0)), ("Rock", (0.4,0.38,0.35, 0.95, 0.0)),
 ("Wetland", (0.2,0.3,0.2, 1.0, 0.0)), ("Gravel", (0.45,0.42,0.38, 1.0, 0.0)), ("Dirt", (0.4,0.3,0.2, 1.0, 0.0)),
 ("Ground_Urban", (0.4,0.4,0.38, 0.95, 0.0)), ("Ground", (0.35,0.3,0.22, 1.0, 0.0)),
 ("Bark", (0.2,0.14,0.1, 1.0, 0.0)), ("Foliage", (0.12,0.3,0.1, 0.9, 0.0)),
]

if not unreal.EditorAssetLibrary.does_asset_exist(f"{D}/M_SF_Master"):
    m = tools.create_asset("M_SF_Master", D, unreal.Material, unreal.MaterialFactoryNew())
    c = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -600, 0); c.set_editor_property("parameter_name", "Color")
    r = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -600, 200); r.set_editor_property("parameter_name", "Roughness"); r.set_editor_property("default_value", 0.9)
    mt = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -600, 300); mt.set_editor_property("parameter_name", "Metallic")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(mt, "", unreal.MaterialProperty.MP_METALLIC)
    m.set_editor_property("two_sided", True)
    mel.recompile_material(m); unreal.EditorAssetLibrary.save_loaded_asset(m)
master = unreal.EditorAssetLibrary.load_asset(f"{D}/M_SF_Master")

def conn(a, b, inp, out=""):
    mel.connect_material_expressions(a, out, b, inp)

def build_facade():
    """Procedural windows: UV = metres along facade x height (sf_twin export). Window grid, reflective glass, per-building tint via vertex colour R."""
    if unreal.EditorAssetLibrary.does_asset_exist(f"{D}/M_SF_Facade"):
        return unreal.EditorAssetLibrary.load_asset(f"{D}/M_SF_Facade")
    m = tools.create_asset("M_SF_Facade", D, unreal.Material, unreal.MaterialFactoryNew())
    X = lambda cls, x, y: mel.create_material_expression(m, cls, x, y)
    uv = X(unreal.MaterialExpressionTextureCoordinate, -1400, 0)
    tile = X(unreal.MaterialExpressionConstant2Vector, -1400, 150); tile.set_editor_property("r", 1/3.2); tile.set_editor_property("g", 1/3.6)
    mul = X(unreal.MaterialExpressionMultiply, -1200, 50); conn(uv, mul, "A"); conn(tile, mul, "B")
    fr = X(unreal.MaterialExpressionFrac, -1050, 50); conn(mul, fr, "")
    mx = X(unreal.MaterialExpressionComponentMask, -900, 0); mx.set_editor_property("r", True); mx.set_editor_property("g", False); conn(fr, mx, "")
    my = X(unreal.MaterialExpressionComponentMask, -900, 120); my.set_editor_property("r", False); my.set_editor_property("g", True); conn(fr, my, "")
    def window(src, lo, hi, y):  # saturate((x-lo)*60) * saturate((hi-x)*60)
        a = X(unreal.MaterialExpressionSubtract, -750, y); c1 = X(unreal.MaterialExpressionConstant, -900, y + 60); c1.set_editor_property("r", lo); conn(src, a, "A"); conn(c1, a, "B")
        am = X(unreal.MaterialExpressionMultiply, -620, y); k = X(unreal.MaterialExpressionConstant, -750, y + 60); k.set_editor_property("r", 60); conn(a, am, "A"); conn(k, am, "B")
        asat = X(unreal.MaterialExpressionSaturate, -500, y); conn(am, asat, "")
        b = X(unreal.MaterialExpressionSubtract, -750, y + 120); c2 = X(unreal.MaterialExpressionConstant, -900, y + 180); c2.set_editor_property("r", hi); conn(c2, b, "A"); conn(src, b, "B")
        bm = X(unreal.MaterialExpressionMultiply, -620, y + 120); conn(b, bm, "A"); conn(k, bm, "B")
        bsat = X(unreal.MaterialExpressionSaturate, -500, y + 120); conn(bm, bsat, "")
        o = X(unreal.MaterialExpressionMultiply, -380, y + 60); conn(asat, o, "A"); conn(bsat, o, "B"); return o
    wx = window(mx, 0.18, 0.82, 300); wy = window(my, 0.22, 0.78, 600)
    mask = X(unreal.MaterialExpressionMultiply, -250, 450); conn(wx, mask, "A"); conn(wy, mask, "B")
    vc = X(unreal.MaterialExpressionVertexColor, -900, -300)
    wall = X(unreal.MaterialExpressionVectorParameter, -700, -250); wall.set_editor_property("parameter_name", "WallColor")
    tint = X(unreal.MaterialExpressionLinearInterpolate, -450, -250)   # per-building brightness from VC.R
    lo = X(unreal.MaterialExpressionConstant, -700, -120); lo.set_editor_property("r", 0.65)
    hi = X(unreal.MaterialExpressionConstant, -700, -60); hi.set_editor_property("r", 1.2)
    vr = X(unreal.MaterialExpressionComponentMask, -750, -300); vr.set_editor_property("r", True); vr.set_editor_property("g", False); conn(vc, vr, "")
    conn(lo, tint, "A"); conn(hi, tint, "B"); conn(vr, tint, "Alpha")
    walltint = X(unreal.MaterialExpressionMultiply, -300, -250); conn(wall, walltint, "A"); conn(tint, walltint, "B")
    glass = X(unreal.MaterialExpressionVectorParameter, -700, 0); glass.set_editor_property("parameter_name", "GlassColor")
    base = X(unreal.MaterialExpressionLinearInterpolate, -100, 0); conn(walltint, base, "A"); conn(glass, base, "B"); conn(mask, base, "Alpha")
    rA = X(unreal.MaterialExpressionScalarParameter, -400, 700); rA.set_editor_property("parameter_name", "WallRoughness"); rA.set_editor_property("default_value", 0.88)
    rB = X(unreal.MaterialExpressionConstant, -400, 760); rB.set_editor_property("r", 0.06)
    rough = X(unreal.MaterialExpressionLinearInterpolate, -100, 700); conn(rA, rough, "A"); conn(rB, rough, "B"); conn(mask, rough, "Alpha")
    mB = X(unreal.MaterialExpressionScalarParameter, -400, 840); mB.set_editor_property("parameter_name", "GlassMetallic"); mB.set_editor_property("default_value", 0.45)
    met = X(unreal.MaterialExpressionMultiply, -100, 820); conn(mask, met, "A"); conn(mB, met, "B")
    glow = X(unreal.MaterialExpressionScalarParameter, -400, 960); glow.set_editor_property("parameter_name", "WindowGlow"); glow.set_editor_property("default_value", 0.0)
    em = X(unreal.MaterialExpressionMultiply, -100, 940); conn(mask, em, "A"); conn(glow, em, "B")
    P = unreal.MaterialProperty
    mel.connect_material_property(base, "", P.MP_BASE_COLOR); mel.connect_material_property(rough, "", P.MP_ROUGHNESS)
    mel.connect_material_property(met, "", P.MP_METALLIC); mel.connect_material_property(em, "", P.MP_EMISSIVE_COLOR)
    m.set_editor_property("two_sided", True)
    mel.recompile_material(m); unreal.EditorAssetLibrary.save_loaded_asset(m); return m
facade = build_facade()
FACADE = {"Facade_Stucco": (0.74,0.69,0.6), "Facade_Brick": (0.5,0.24,0.18), "Glass_Curtain": (0.35,0.45,0.55), "Stone_White": (0.85,0.85,0.8), "Concrete": (0.6,0.6,0.58)}

cache = {}
def inst_for(key):
    if key in cache: return cache[key]
    spec = next((v for k, v in PAL if k in key), (0.5, 0.5, 0.5, 0.9, 0.0))
    fk = next((k for k in FACADE if k in key), None)
    nm = "MI_SF_" + re.sub(r"[^A-Za-z0-9_]", "", key)
    p = f"{D}/{nm}"
    if unreal.EditorAssetLibrary.does_asset_exist(p):
        i = unreal.EditorAssetLibrary.load_asset(p)
    else:
        i = tools.create_asset(nm, D, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        if fk:
            i.set_editor_property("parent", facade)
            mel.set_material_instance_vector_parameter_value(i, "WallColor", unreal.LinearColor(*[x ** 2.2 for x in FACADE[fk]], 1))
            gc = (0.04, 0.09, 0.14) if "Glass" in key else (0.03, 0.06, 0.09)
            mel.set_material_instance_vector_parameter_value(i, "GlassColor", unreal.LinearColor(*gc, 1))
        else:
            i.set_editor_property("parent", master)
            mel.set_material_instance_vector_parameter_value(i, "Color", unreal.LinearColor(*[x ** 2.2 for x in spec[:3]], 1))
            mel.set_material_instance_scalar_parameter_value(i, "Roughness", spec[3])
            mel.set_material_instance_scalar_parameter_value(i, "Metallic", spec[4])
        unreal.EditorAssetLibrary.save_loaded_asset(i)
    cache[key] = i; return i

n = 0
for root in ("/Game/Geo/Tiles", "/Game/Landmarks", "/Game/Props"):
    for a in ar.get_assets_by_path(root, recursive=True):
        if str(a.asset_class_path.asset_name) != "StaticMesh": continue
        if ONLY and not (any(f"/{i}/" in str(a.package_name) for i in ONLY) or str(a.package_name).startswith("/Game/Props/")): continue
        sm = a.get_asset(); changed = False
        for idx, sl in enumerate(sm.static_materials):
            mi = sl.material_interface
            nm = mi.get_name() if mi else str(sl.material_slot_name)
            mm = re.search(r"(MAT_.+?)(?:_\d+)?(?:_TwoSided)?$", nm)
            key = mm.group(1) if mm else nm
            sm.set_material(idx, inst_for(key)); changed = True
        if changed: unreal.EditorAssetLibrary.save_loaded_asset(sm); n += 1
print("SFMAT meshes updated", n, "instances", len(cache), sorted(cache))
