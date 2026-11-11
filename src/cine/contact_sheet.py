"""Contact sheet of PNG frames (Blender python, no PIL): blender -b -P contact_sheet.py -- out.png cols f1 f2 ..."""
import sys
import bpy
import numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
out, cols, fs = a[0], int(a[1]), a[2:]
ims = [bpy.data.images.load(f) for f in fs]
w, h = ims[0].size
sc = 2
rows = (len(ims) + cols - 1) // cols
o = np.zeros((rows * (h // sc), cols * (w // sc), 4), np.float32)
for i, im in enumerate(ims):
    px = np.array(im.pixels[:], np.float32).reshape(im.size[1], im.size[0], 4)[::sc, ::sc]
    r, c = divmod(i, cols)
    o[(rows - 1 - r) * (h // sc):(rows - r) * (h // sc), c * (w // sc):(c + 1) * (w // sc)] = px[:h // sc, :w // sc]
img = bpy.data.images.new("s", o.shape[1], o.shape[0])
img.pixels = o.ravel()
img.filepath_raw = out
img.file_format = "PNG"
img.save()
