"""Split-screen film: left = car chase cam, right = drone. 1920x1080, H.264 via Blender's FFmpeg.
blender -b --factory-startup -P src/cine/compose_film.py -- <car_dir> <drone_dir> <out.mp4> [fps] [max_frames]
Frames are matched by file order; if one view is shorter, the last frame is held."""
import sys
from pathlib import Path

import bpy

a = sys.argv[sys.argv.index("--") + 1:]
car_dir, drone_dir, out = Path(a[0]), Path(a[1]), Path(a[2])
fps = int(a[3]) if len(a) > 3 else 24
cap = int(a[4]) if len(a) > 4 else 10 ** 9
cars = sorted(car_dir.glob("frame_*.png"))[:cap]
drones = sorted(drone_dir.glob("frame_*.png"))[:cap]
n = max(len(cars), len(drones))
scn = bpy.context.scene
scn.render.resolution_x, scn.render.resolution_y, scn.render.resolution_percentage = 1920, 1080, 100
scn.render.fps, scn.frame_start, scn.frame_end = fps, 1, n
seq = scn.sequence_editor_create()
S = seq.strips


def add(files, ch, dx, name):
    st = S.new_image(name, str(files[0]), channel=ch, frame_start=1, fit_method="ORIGINAL")
    for f in files[1:]:
        st.elements.append(f.name)
    if len(files) < n:  # hold the last frame
        st.frame_final_duration = n
        try:
            st.use_freeze_frame = True
        except AttributeError:
            pass
    st.transform.offset_x = dx
    return st


add(cars, 1, -480, "car")
add(drones, 2, 480, "drone")
try:  # labels
    for ch, txt, x in ((3, "CAR CAM", 0.25), (4, "DRONE CAM", 0.75)):
        t = S.new_effect(f"label{ch}", "TEXT", channel=ch, frame_start=1, length=n)
        t.text, t.font_size, t.location = txt, 34, (x, 0.94)
        t.color, t.use_shadow = (1, 1, 1, 0.9), True
except Exception as e:  # noqa: BLE001
    print("labels skipped:", e)
STILL = out.suffix == ".png"  # layout check: render frame 1 only
scn.render.use_compositing = False
scn.view_settings.view_transform = "Standard"  # frames are already display-referred PNGs
if STILL:
    scn.render.image_settings.file_format = "PNG"
    scn.render.filepath = str(out)
    scn.frame_current = 1
    bpy.ops.render.render(write_still=True)
    print("COMPOSED", out)
    raise SystemExit
try:
    scn.render.image_settings.media_type = "VIDEO"
except (AttributeError, TypeError):
    pass
scn.render.image_settings.file_format = "FFMPEG"
scn.render.ffmpeg.format, scn.render.ffmpeg.codec = "MPEG4", "H264"
scn.render.ffmpeg.constant_rate_factor, scn.render.ffmpeg.ffmpeg_preset = "PERC_LOSSLESS", "GOOD"
scn.render.filepath = str(out.with_suffix(""))
bpy.ops.render.render(animation=True)
print("COMPOSED", out, n, "frames")
