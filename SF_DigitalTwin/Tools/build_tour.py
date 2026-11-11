"""Build /Game/Cinematics/SF_Tour: one CineCamera per shot (spawnable), camera-cut track, transform keys from tour.json."""
import json, os, unreal
J = json.load(open(os.path.expanduser("~/sf_twin/SF_DigitalTwin/Tools/tour.json")))
FPS = J["fps"]; tools = unreal.AssetToolsHelpers.get_asset_tools()
ONLY = os.environ.get("SF_ONLY_SHOT"); SEQ = os.environ.get("SF_SEQ_NAME", "SF_Tour")
if ONLY: J["shots"] = [x for x in J["shots"] if x["name"] == ONLY]
path = "/Game/Cinematics/" + SEQ
if unreal.EditorAssetLibrary.does_asset_exist(path): unreal.EditorAssetLibrary.delete_asset(path)
seq = tools.create_asset(SEQ, "/Game/Cinematics", unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
seq.set_display_rate(unreal.FrameRate(FPS, 1)); seq.set_tick_resolution(unreal.FrameRate(FPS * 100, 1))
total = sum(s["frames"] for s in J["shots"]); seq.set_playback_start(0); seq.set_playback_end(total)
cut = seq.add_track(unreal.MovieSceneCameraCutTrack)
t0 = 0
for s in J["shots"]:
    b = seq.add_spawnable_from_class(unreal.CineCameraActor); b.set_name("Cam_" + s["name"])
    tmpl = b.get_object_template(); comp = tmpl.get_cine_camera_component() or tmpl.get_component_by_class(unreal.CineCameraComponent) or tmpl.get_editor_property('camera_component')
    comp.set_editor_property("current_focal_length", s["focal"]); comp.set_editor_property("current_aperture", 4.0)
    comp.filmback = unreal.CameraFilmbackSettings(sensor_width=24.89, sensor_height=14.0)
    comp.set_editor_property("constrain_aspect_ratio", False)
    fs = comp.get_editor_property("focus_settings"); fs.focus_method = unreal.CameraFocusMethod.DISABLE; comp.set_editor_property("focus_settings", fs)
    tr = b.add_track(unreal.MovieScene3DTransformTrack); sec = tr.add_section(); sec.set_range(t0, t0 + s["frames"] + 1)
    ch = sec.get_all_channels()   # loc xyz, rot roll pitch yaw, scale xyz
    for k, x, y, z, pitch, yaw in s["keys"]:
        f = unreal.FrameNumber(t0 + k)
        for c, v in zip(ch[:6], (x, y, z, 0.0, pitch, yaw)): c.add_key(f, v)
    cs = cut.add_section(); cs.set_range(t0, t0 + s["frames"])
    cs.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq, b))
    t0 += s["frames"]
unreal.EditorAssetLibrary.save_loaded_asset(seq)
print("SFTOUR_DONE frames", total, "shots", len(J["shots"]))
