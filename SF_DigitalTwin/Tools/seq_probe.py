import unreal
print("SFSQ", [n for n in dir(unreal.MovieSceneSequenceExtensions) if "bind" in n.lower()])
print("SFSQ2", [n for n in dir(unreal.MovieSceneBindingExtensions) if "id" in n.lower()])
print("SFSQ3", [n for n in dir(unreal.MovieSceneCameraCutSection) if "bind" in n.lower()])
