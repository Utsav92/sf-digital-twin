import unreal
ar = unreal.AssetRegistryHelpers.get_asset_registry()
n=0
for a in ar.get_assets_by_path("/Game/Geo/Tiles", recursive=True):
    if str(a.asset_class_path.asset_name)=="StaticMesh":
        m=a.get_asset(); bs=m.get_editor_property("body_setup")
        print("SFCOLL", a.asset_name, "trace", bs.get_editor_property("collision_trace_flag") if bs else None, "nanite", m.get_editor_property("nanite_settings").enabled)
        n+=1
        if n>=4: break
