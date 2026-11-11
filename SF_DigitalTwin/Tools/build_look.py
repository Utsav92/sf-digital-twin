"""Game-look lighting for the current map: physical sun, sky atmosphere, volumetric clouds + fog, Lumen, VSM, grade. Env SF_MAP, SF_SUN_ALT, SF_SUN_AZ."""
import os, unreal
MAP = os.environ.get("SF_MAP", "SF_City")
alt = float(os.environ.get("SF_SUN_ALT", "13")); az = float(os.environ.get("SF_SUN_AZ", "262"))
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem); eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les.load_level(f"/Game/Maps/{MAP}")
for a in eas.get_all_level_actors():
    if a.get_class().get_name() in ("DirectionalLight", "SkyAtmosphere", "SkyLight", "ExponentialHeightFog", "VolumetricCloud", "PostProcessVolume") or a.get_actor_label() == "OceanPlane":
        eas.destroy_actor(a)
# Sun: Unreal yaw is clockwise from +X(east) with Y flipped; az is compass bearing of the sun. pitch = -altitude.
yaw = az - 90.0
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 200000)); sun.set_actor_label("Sun")
sun.set_actor_rotation(unreal.Rotator(0, -alt, yaw), False)
c = sun.get_component_by_class(unreal.DirectionalLightComponent)
c.set_editor_property("atmosphere_sun_light", True); c.set_editor_property("intensity", 14.0)
try: c.set_editor_property("light_color", unreal.Color(255, 214, 170, 255))
except Exception as e: print("SFLOOK_SKIP sun colour", e)
c.set_editor_property("light_source_angle", 0.5); c.set_editor_property("cast_shadows", True)
c.set_editor_property("cast_cloud_shadows", True) if hasattr(c, "cast_cloud_shadows") else None
sa = eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0)); sac = sa.get_component_by_class(unreal.SkyAtmosphereComponent)
for n, v in (("aerial_perspective_start_depth", 0.1), ("ground_albedo", unreal.Color(18, 40, 60, 255)), ("mie_scattering_scale", 0.05)):
    try: sac.set_editor_property(n, v)
    except Exception as e: print("SFLOOK_SKIP sky", n, str(e)[:80])
sl = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 100000)); sc = sl.get_component_by_class(unreal.SkyLightComponent)
sc.set_editor_property("real_time_capture", True); sc.set_editor_property("intensity", 1.3)
vc = eas.spawn_actor_from_class(unreal.VolumetricCloud, unreal.Vector(0, 0, 0))
fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0)); fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
fc.set_editor_property("fog_density", 0.004); fc.set_editor_property("fog_height_falloff", 0.35)
fc.set_editor_property("enable_volumetric_fog", True); fc.set_editor_property("start_distance", 20000.0)
for _n in ("fog_inscattering_luminance", "inscattering_color_cubemap_angle"):
    pass
try:
    fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.45, 0.58, 0.8, 1))
except Exception as e:
    print("SFLOOK_SKIP fog colour", str(e)[:100])
try:
    pl = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, -300)); pl.set_actor_label("OceanPlane")
    pl.static_mesh_component.set_static_mesh(unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane"))
    pl.set_actor_scale3d(unreal.Vector(100000, 100000, 1))
    mat = unreal.EditorAssetLibrary.load_asset("/Game/Materials/M_SF_Master")
    mi = unreal.EditorAssetLibrary.load_asset("/Game/Materials/MI_SF_Ocean") or unreal.AssetToolsHelpers.get_asset_tools().create_asset("MI_SF_Ocean", "/Game/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", mat); unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(0.01, 0.05, 0.10, 1)); unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, "Roughness", 0.45)
    unreal.EditorAssetLibrary.save_loaded_asset(mi); pl.static_mesh_component.set_material(0, unreal.EditorAssetLibrary.load_asset("/Game/Materials/MI_SF_MAT_Water_Bay") or mi)
except Exception as e: print("SFLOOK_SKIP ocean", str(e)[:120])
# water was a near-mirror: grazing-angle reflection of the bright horizon read as a white band
_ar = unreal.AssetRegistryHelpers.get_asset_registry(); _nw = 0
for _a in _ar.get_assets_by_path("/Game/Materials", recursive=False):
    if "Water" in str(_a.asset_name) and str(_a.asset_class_path.asset_name) == "MaterialInstanceConstant":
        _m = _a.get_asset(); unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(_m, "Roughness", 0.3); unreal.EditorAssetLibrary.save_loaded_asset(_m); _nw += 1
print("SFLOOK water instances roughened", _nw)
ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0)); ppv.set_editor_property("unbound", True); ppv.set_actor_label("PP_Grade")
s = ppv.settings
def S(n, v):
    try:
        s.set_editor_property(n, v); s.set_editor_property("override_" + n, True)
    except Exception as e:
        print("SFLOOK_SKIP", n, str(e)[:120])
S("auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM)
S("auto_exposure_min_brightness", 0.6); S("auto_exposure_max_brightness", 6.0); S("auto_exposure_bias", 0.3)
S("bloom_intensity", 0.5); S("bloom_threshold", 1.0)
S("vignette_intensity", 0.35); S("film_grain_intensity", 0.05) if hasattr(s, "film_grain_intensity") else None
S("color_saturation", unreal.Vector4(0.9, 0.9, 0.9, 1.0)); S("color_contrast", unreal.Vector4(1.12, 1.12, 1.12, 1.0))
S("film_slope", 0.9); S("film_toe", 0.55); S("film_shoulder", 0.26); S("film_black_clip", 0.0); S("film_white_clip", 0.04)
S("bloom_intensity", 0.7); S("scene_color_tint", unreal.LinearColor(1.0, 0.97, 0.93, 1.0))
S("dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.LUMEN)
S("reflection_method", unreal.ReflectionMethod.LUMEN)
S("lumen_final_gather_quality", 1.0) if hasattr(s, "lumen_final_gather_quality") else None
ppv.settings = s
les.save_current_level(); print("SFLOOK_DONE", MAP, "sun alt", alt, "az", az)
