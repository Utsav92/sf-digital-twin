import unreal
ml = unreal.MaterialEditingLibrary
for sp, col in (("Broadleaf",(0.07,0.20,0.04)),("Conifer",(0.03,0.12,0.05)),("Palm",(0.10,0.24,0.05))):
    m = unreal.EditorAssetLibrary.load_asset(f"/Game/Props/SM_Tree_{sp}/SM_Tree_{sp}/StaticMeshes/SM_Tree_{sp}")
    slots = [str(s.material_slot_name)+":"+(s.material_interface.get_name() if s.material_interface else "None") for s in m.static_materials]
    print("SFTM", sp, slots, "nanite", m.get_editor_property("nanite_settings").enabled)
    for si, s in enumerate(m.static_materials):
        mi = s.material_interface
        if mi and isinstance(mi, unreal.MaterialInstanceConstant):
            print("SFTM params", [str(p.parameter_info.name) for p in mi.get_editor_property("vector_parameter_values")])
            ml.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(*((0.10,0.06,0.03) if si == 0 else col), 1.0))
            ml.set_material_instance_scalar_parameter_value(mi, "Roughness", 0.85)
            unreal.EditorAssetLibrary.save_loaded_asset(mi)
print("SFTM_DONE")
