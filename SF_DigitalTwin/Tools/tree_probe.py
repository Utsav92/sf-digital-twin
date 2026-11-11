import unreal
for n in ("MI_SF_MI_tree_crown_0_TwoSided","MI_SF_MI_tree_trunk_0_TwoSided"):
    mi = unreal.EditorAssetLibrary.load_asset("/Game/Materials/"+n) or unreal.EditorAssetLibrary.load_asset("/Game/Props/SM_Tree_Broadleaf/SM_Tree_Broadleaf/Materials/"+n)
    print("SFTP", n, mi.get_path_name() if mi else None, "parent", mi.get_editor_property("parent").get_name() if mi else None)
    if mi:
        print("SFTP vec", [(str(p.parameter_info.name), p.parameter_value) for p in mi.get_editor_property("vector_parameter_values")])
        print("SFTP sca", [(str(p.parameter_info.name), p.parameter_value) for p in mi.get_editor_property("scalar_parameter_values")])
        print("SFTP tex", [(str(p.parameter_info.name), p.parameter_value.get_name()) for p in mi.get_editor_property("texture_parameter_values")])
        print("SFTP sw", mi.get_editor_property("base_property_overrides"))
