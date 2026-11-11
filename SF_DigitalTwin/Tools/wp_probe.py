import unreal
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem); eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les.load_level("/Game/Maps/SF_City")
w = unreal.EditorLevelLibrary.get_editor_world()
wp = w.get_world_settings()
print("SFWP ws", [p for p in dir(wp) if "partition" in p.lower()])
acts = eas.get_all_level_actors()
a = [x for x in acts if x.get_class().get_name()=="StaticMeshActor"][0]
print("SFWP actor props", [p for p in dir(a) if "spatial" in p.lower() or "loaded" in p.lower()])
for c in ("RuntimePartitionLHGrid","WorldPartitionRuntimeHashSet","RuntimePartitionPersistent"):
    k = getattr(unreal, c, None); print("SFWP class", c, bool(k), [p for p in dir(k) if not p.startswith("_")][:40] if k else "")
