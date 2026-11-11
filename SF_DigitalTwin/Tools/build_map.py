"""Build /Game/Maps/SF_Pilot from sf_twin manifest: tile meshes + landmarks at manifest Unreal cm locations. Env SF_MAP=name"""
import os, json, unreal
SF = os.path.expanduser("~/sf_twin")
man = json.load(open(f"{SF}/out/city/manifest.json"))
MAP = os.environ.get("SF_MAP", "SF_Pilot")
only_pilot = os.environ.get("SF_ALL", "0") != "1"
ar = unreal.AssetRegistryHelpers.get_asset_registry()
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

path = f"/Game/Maps/{MAP}"
if unreal.EditorAssetLibrary.does_asset_exist(path):
    unreal.EditorAssetLibrary.delete_asset(path)
les.new_level(path)

def find_mesh(root):
    for a in ar.get_assets_by_path(root, recursive=True):
        if str(a.asset_class_path.asset_name) == "StaticMesh":
            return a.get_asset()
    return None

def spawn_mesh(mesh, loc_cm, label):
    a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*loc_cm))
    a.set_actor_label(label)
    a.static_mesh_component.set_static_mesh(mesh)
    a.static_mesh_component.set_mobility(unreal.ComponentMobility.STATIC)
    return a

n = 0
for tid, t in man["tiles"].items():
    if only_pilot and not t.get("pilot"):
        continue
    m = find_mesh(f"/Game/Geo/Tiles/{tid}")
    if m is None:
        print("SFMAP missing tile mesh", tid); continue
    spawn_mesh(m, t["unreal_location_cm"], f"Tile_{tid}"); n += 1
nl = 0
for name, l in man["landmarks"].items():
    m = find_mesh(f"/Game/Landmarks/{name}")
    if m is None:
        print("SFMAP missing landmark", name); continue
    spawn_mesh(m, l["unreal_location_cm"], f"Landmark_{name}"); nl += 1

# Sky, sun, fog, player start near Salesforce Tower base (street level, east side)
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 100000)); sun.set_actor_rotation(unreal.Rotator(0, -35, 215), False)
sun.set_actor_label("Sun"); sun.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("atmosphere_sun_light", True)
eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
sl = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 50000)); sl.get_component_by_class(unreal.SkyLightComponent).set_editor_property("real_time_capture", True)
eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
sf = man["landmarks"]["salesforce"]["unreal_location_cm"]
ps = eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(sf[0] + 6000, sf[1], sf[2] + 3000))
print("SFMAP tiles", n, "landmarks", nl)
les.save_current_level()
print("SFMAP_DONE", path)
