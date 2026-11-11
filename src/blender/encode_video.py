"""Encode a PNG sequence to H.264 mp4 with Blender's built-in FFmpeg (no system ffmpeg needed).
blender -b --factory-startup -P src/blender/encode_video.py -- <frames_dir> <out.mp4> [fps]"""
import sys
from pathlib import Path
import bpy
a = sys.argv[sys.argv.index("--") + 1:]
d, out, fps = Path(a[0]), Path(a[1]), int(a[2]) if len(a) > 2 else 24
files = sorted(d.glob("frame_*.png"))
scn = bpy.context.scene
scn.sequence_editor_create()
st = scn.sequence_editor.strips.new_image("seq", str(files[0]), channel=1, frame_start=1)
for f in files[1:]:
    st.elements.append(f.name)
im = bpy.data.images.load(str(files[0]))
scn.render.resolution_x, scn.render.resolution_y, scn.render.resolution_percentage = im.size[0], im.size[1], 100
scn.render.fps, scn.frame_start, scn.frame_end = fps, 1, len(files)
scn.render.use_compositing = False
try:
    scn.render.image_settings.media_type = "VIDEO"
except (AttributeError, TypeError):
    pass
scn.render.image_settings.file_format = "FFMPEG"
scn.render.ffmpeg.format, scn.render.ffmpeg.codec = "MPEG4", "H264"
scn.render.ffmpeg.constant_rate_factor, scn.render.ffmpeg.ffmpeg_preset = "HIGH", "GOOD"
scn.view_settings.view_transform = "Standard"  # frames are already display-referred PNGs
scn.render.filepath = str(out.with_suffix(""))
bpy.ops.render.render(animation=True)
print("ENCODED", out, len(files), "frames")
