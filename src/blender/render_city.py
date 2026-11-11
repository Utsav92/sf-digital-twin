"""Assemble tiles via linked collection instances and render verification views. Runs inside Blender.

blender -b --factory-startup -P src/blender/render_city.py -- \
   [--pilot | --tiles a,b | --all] [--lod lod0|lod1|auto] [--view top|aerial] [--az 225] [--elev 35]
   [--target x,y,z] [--dist 3000] [--lens 50] [--cam x,y,z] [--hypso] [--time 2026-09-21T16:00]
   [--hide Buildings,Trees] [--res 1920x1200] [--engine EEVEE] [--samples 32] --out renders/x.png
--lod auto: LOD1 for tiles within --lod1-radius of the target, LOD0 elsewhere.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from bpy_common import ROOT, load_tile_index, render_png, reset_scene, script_args, set_engine  # noqa: E402
import lighting  # noqa: E402
import materials  # noqa: E402


def opt(args, k, d=None, f=str):
    return f(args[args.index(k) + 1]) if k in args else d


def vec(s):
    return Vector([float(v) for v in s.split(",")])


def link_tile(tile, lod):
    path = ROOT / "out/tiles" / tile["id"] / f"{tile['id']}.blend"
    if not path.exists():
        return None
    cname = f"tile_{tile['name']}_{lod.upper()}"
    with bpy.data.libraries.load(str(path), link=True) as (src, dst):
        dst.collections = [c for c in src.collections if c == cname]
    if not dst.collections:
        return None
    coll = dst.collections[0]
    inst = bpy.data.objects.new(f"inst_{tile['name']}_{lod}", None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = coll
    inst.location = tile["offset_city"]
    inst["tile_id"] = tile["id"]
    bpy.context.scene.collection.objects.link(inst)
    return inst


def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def main():
    a = script_args()
    scn = reset_scene()
    idx = load_tile_index()
    tiles = [t for t in idx["tiles"].values() if t["status"] == "build"]
    if "--pilot" in a:
        tiles = [t for t in tiles if t["pilot"]]
    if "--tiles" in a:
        want = set(opt(a, "--tiles").split(","))
        tiles = [t for t in tiles if t["id"] in want]
    lod = opt(a, "--lod", "lod0")
    target = vec(opt(a, "--target", "0,0,0")) if "--target" in a else None
    xs = [t["bounds_city"][0] for t in tiles] + [t["bounds_city"][2] for t in tiles]
    ys = [t["bounds_city"][1] for t in tiles] + [t["bounds_city"][3] for t in tiles]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    target = target or Vector((cx, cy, 0))
    r1 = opt(a, "--lod1-radius", 1200, float)
    n = {"lod0": 0, "lod1": 0}
    for t in tiles:
        L = lod
        if lod == "auto":
            ox, oy, _ = t["offset_city"]
            L = "lod1" if math.hypot(ox - target.x, oy - target.y) < r1 else "lod0"
        if link_tile(t, L):
            n[L] += 1
    import os
    tex = os.environ.get("SF_TEX_RES")
    if tex in ("4k", "8k"):  # hero renders: point the shared material library at the hi-res texture build
        hi = ROOT / f"out/city/sf_materials_{tex}.blend"
        for lib in bpy.data.libraries:
            if Path(lib.filepath).name == "sf_materials.blend" and hi.exists():
                lib.filepath = str(hi)
                lib.reload()
                print(f"TEXRES {tex}: material library -> {hi.name}")
    oc = ROOT / "data/processed/city_ocean.npz"
    if oc.exists() and "--no-ocean" not in a:
        from bpy_common import mesh_from_npz
        me = mesh_from_npz("far_ocean", np.load(oc))
        me.materials.append(materials.get_mat("water_bay"))
        scn.collection.objects.link(bpy.data.objects.new("far_ocean", me))
    hide = set(opt(a, "--hide", "").split(",")) - {""}
    if hide:
        for c in bpy.data.collections:
            if any(c.name.startswith(h + "_") for h in hide):
                for o in c.objects:
                    o.hide_render = True
    eng = set_engine(scn, opt(a, "--engine", "EEVEE"), opt(a, "--samples", 32, int))
    try:
        scn.view_settings.view_transform = "AgX"
    except TypeError:
        scn.view_settings.view_transform = "Filmic"
    if "--preset" in a:
        elev, az = lighting.apply_preset(scn, opt(a, "--preset"), wetness=opt(a, "--wet", 0.0, float))
    else:
        elev, az = lighting.setup_sun_sky(scn, opt(a, "--time", "2026-09-21T15:30"))
    if "--hypso" in a:
        bpy.context.view_layer.material_override = materials.hypsometric_override()
    if "EEVEE" in eng:
        for attr, val in (("use_shadows", True), ("shadow_ray_count", 2), ("use_raytracing", True),
                          ("use_gtao", True)):
            try:
                setattr(scn.eevee, attr, val)
            except AttributeError:
                pass

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scn.collection.objects.link(cam)
    scn.camera = cam
    cam.data.clip_start, cam.data.clip_end = max(0.3, opt(a, "--dist", 3000, float) / 3000), 60000
    res = [int(v) for v in opt(a, "--res", "1920x1200").split("x")]
    view = opt(a, "--view", "aerial")
    if view == "top":
        cam.data.type = "ORTHO"
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        cam.data.ortho_scale = max(w, h * res[0] / res[1]) * 1.02
        cam.location = (cx, cy, 5000)
        cam.rotation_euler = (0, 0, 0)
    else:
        cam.data.lens = opt(a, "--lens", 35, float)
        if "--cam" in a:
            cam.location = vec(opt(a, "--cam"))
        else:
            az_c, el_c = math.radians(opt(a, "--az", 200, float)), math.radians(opt(a, "--elev", 35, float))
            dist = opt(a, "--dist", 3000, float)
            cam.location = target + Vector((math.sin(az_c) * math.cos(el_c), math.cos(az_c) * math.cos(el_c),
                                            math.sin(el_c))) * dist
        look_at(cam, target)
    if "--anim" in a:  # animated camera: drone | drive (Market St corridor), --seconds N, --frames a-b
        import cameras
        kind = opt(a, "--anim")
        if kind == "cine_car":
            scn.camera = cameras.add_cine_car(scn, opt(a, "--seconds", 180.0, float))
        elif kind == "cine_drone":
            scn.camera = cameras.add_cine_drone(scn, opt(a, "--seconds", 180.0, float))
        elif kind == "cine_both":  # for --save-blend: hero car + chase cam AND the drone, car cam active
            cameras.add_cine_drone(scn, opt(a, "--seconds", 180.0, float))
            scn.camera = cameras.add_cine_car(scn, opt(a, "--seconds", 180.0, float))
        else:
            scn.camera = cameras.add_motion_rig(scn, kind, opt(a, "--seconds", 12.0, float))
        cam = scn.camera
        if "--mblur" in a:  # subtle motion blur for the film
            for obj_, attr, val in ((scn.render, "use_motion_blur", True), (scn.render, "motion_blur_shutter", opt(a, "--mblur", 0.35, float)),
                                    (scn.eevee, "use_motion_blur", True), (scn.eevee, "motion_blur_shutter", opt(a, "--mblur", 0.35, float))):
                try:
                    setattr(obj_, attr, val)
                except (AttributeError, TypeError):
                    pass
    if "--rig" in a:  # use a named camera rig from cameras.py (frame for animated rigs)
        import cameras
        rigs = cameras.add_rigs(scn)
        scn.camera = rigs[opt(a, "--rig")]
        scn.frame_set(opt(a, "--frame", 1, int))
    if "--lamp-lights" in a:  # real point lights on the N street lamps nearest the camera (rest emissive)
        nmax = opt(a, "--lamp-lights", 300, int)
        pts = []
        for t in tiles:
            f = ROOT / "data/processed/tiles" / t["id"] / "mesh_props_lod1.npz"
            if f.exists():
                d = np.load(f)
                k = d["p_kind"] == 0
                if k.any():
                    v, r = d["verts"][k], d["p_rot"][k]
                    head = np.c_[v[:, 0] + 1.75 * np.cos(r), v[:, 1] + 1.75 * np.sin(r), v[:, 2] + 7.1]
                    pts.append(head + np.array(t["offset_city"]))
        if pts:
            P = np.concatenate(pts)
            c = np.array(scn.camera.location)
            near = P[np.argsort(np.linalg.norm(P - c, axis=1))[:nmax]]
            ld = bpy.data.lights.new("street_lamp", "POINT")
            ld.energy, ld.color, ld.shadow_soft_size = 900.0, (1.0, 0.70, 0.42), 0.25
            try:
                ld.use_shadow = False
            except AttributeError:
                pass
            for i, q in enumerate(near):
                o = bpy.data.objects.new(f"lamp_light_{i}", ld)
                o.location = q
                scn.collection.objects.link(o)
            print(f"LAMPS {len(near)} point lights")
    if "--atmo" in a:  # subtle volumetric fog box around the view target (density per metre)
        lighting.atmosphere(scn, (target.x, target.y, target.z), size=opt(a, "--atmo-size", 1400.0, float),
                            density=opt(a, "--atmo", 0.0012, float))
    if "--area" in a:  # cinematic fill + kicker area lights
        lighting.area_lights(scn, scn.camera, target, az, power=opt(a, "--area", 1.0, float))
    if "--look" in a:  # game-look VFX stack (engine quality + compositor post)
        import vfx
        dof = tuple(float(v) for v in opt(a, "--dof").split(",")) if "--dof" in a else None
        vfx.apply(scn, opt(a, "--look"), dof=dof, samples=opt(a, "--samples", 64, int),
                  fog_scale=opt(a, "--fog", 1.0, float))
    out = ROOT / opt(a, "--out", "renders/test.png")
    if "--save-blend" in a:  # write an openable scene instead of rendering
        scn.render.resolution_x, scn.render.resolution_y = res
        bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / opt(a, "--save-blend")), compress=True, relative_remap=True)
        print(f"SAVEDBLEND {opt(a, '--save-blend')}", flush=True)
        return
    if "--splat-capture" in a:  # calibrated RGB + exact depth for every view -> Gaussian splat (src/cine/build_splat.py)
        import cameras
        import json
        import vfx
        d = ROOT / opt(a, "--splat-capture")
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "views").mkdir(exist_ok=True)
        W, H = res
        cam.data.lens, cam.data.clip_start, cam.data.clip_end = 20.0, 0.3, 8000.0
        vs = cameras.splat_views(scn)[::opt(a, "--splat-stride", 1, int)]
        print(f"SPLAT views {len(vs)}", flush=True)
        # depth material: euclidean view distance hi/lo-encoded in two channels (float16-safe, ~1.6 cm)
        dm = bpy.data.materials.new("splat_depth")
        dm.use_nodes = True
        nt = dm.node_tree
        nt.nodes.clear()
        cd = nt.nodes.new("ShaderNodeCameraData")
        def mth(op, x, y=None):
            n_ = nt.nodes.new("ShaderNodeMath")
            n_.operation = op
            nt.links.new(x, n_.inputs[0]) if not isinstance(x, float) else setattr(n_.inputs[0], "default_value", x)
            if y is not None:
                n_.inputs[1].default_value = y
            return n_.outputs[0]
        t_ = mth("DIVIDE", cd.outputs["View Distance"], 32.0)
        fl_ = mth("FLOOR", t_)
        fr_ = mth("SUBTRACT", t_)
        nt.links.new(fl_, nt.nodes[-1].inputs[1])  # t - floor(t)
        cb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(fl_, cb.inputs["X"])
        nt.links.new(fr_, cb.inputs["Y"])
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(cb.outputs["Vector"], em.inputs["Color"])
        mo = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], mo.inputs["Surface"])
        vl = bpy.context.view_layer
        spp = 32
        frames = []
        fx = 20.0 * W / 36.0
        for i, (eye, look, tag) in enumerate(vs):
            cam.location = Vector(eye)
            look_at(cam, look)
            bpy.context.view_layer.update()
            if "--splat-skip-existing" in a and (d / "views" / f"{i:04d}.npz").exists():
                frames.append({"file_path": f"images/{i:04d}.png", "transform_matrix": [list(r) for r in cam.matrix_world]})
                continue
            # RGB (display-referred, AgX) via the standard still path
            vl.material_override = None
            scn.render.film_transparent = False
            scn.render.filter_size = 1.5
            vfx.engine(scn, spp)
            png = d / "images" / f"{i:04d}.png"
            render_png(png, res)
            im = bpy.data.images.load(str(png))
            im.colorspace_settings.name = "Non-Color"
            rgb = np.empty(W * H * 4, np.float32)
            im.pixels.foreach_get(rgb)
            bpy.data.images.remove(im)
            rgb = (rgb.reshape(H, W, 4)[:, :, :3] * 255 + 0.5).astype(np.uint8)
            # depth pass: no AA, transparent sky, raw colour
            vl.material_override = dm
            scn.render.film_transparent = True
            scn.render.filter_size = 0.0
            scn.eevee.taa_render_samples = 1
            scn.view_settings.view_transform = "Raw"
            try:
                scn.view_settings.look = "None"
            except TypeError:
                pass
            bpy.ops.render.render()
            rr = bpy.data.images["Render Result"]
            ex = d / "_depth.exr"
            scn.render.image_settings.file_format = "OPEN_EXR"
            scn.render.image_settings.color_depth = "32"
            rr.save_render(str(ex))
            ei = bpy.data.images.load(str(ex))
            buf = np.empty(W * H * 4, np.float32)
            ei.pixels.foreach_get(buf)
            bpy.data.images.remove(ei)
            code = buf.reshape(H, W, 4)
            np.savez_compressed(d / "views" / f"{i:04d}.npz", code=code.astype(np.float16), rgb=rgb,
                                eye=np.array(eye, np.float64), R=np.array(cam.matrix_world.to_3x3(), np.float64),
                                fx=fx, W=W, H=H, tag=tag)
            frames.append({"file_path": f"images/{i:04d}.png", "transform_matrix": [list(r) for r in cam.matrix_world]})
            if i % 10 == 0:
                print(f"SPLATVIEW {i}/{len(vs)} {tag}", flush=True)
        (d / "transforms.json").write_text(json.dumps({"camera_model": "OPENCV", "fl_x": fx, "fl_y": fx, "cx": W / 2,
                                                       "cy": H / 2, "w": W, "h": H, "frames": frames}))
        print(f"SPLATDONE {len(vs)} views -> {d}", flush=True)
        return
    if "--anim" in a:  # per-frame loop through the SAME path as stills (compositor, LOD, instancing identical)
        if "--film60" in a:  # 60 s audio-reactive film timeline (src/blender/film60.py); no effect on other renders
            import film60
            film60.run(scn, a, render_png, res, out)
            return
        fa, fb = (int(v) for v in opt(a, "--frames", f"{scn.frame_start}-{scn.frame_end}").split("-"))
        fdir = out.with_suffix("")
        fdir.mkdir(parents=True, exist_ok=True)
        import time as _t
        t0 = _t.time()
        for fr in range(fa, fb + 1):
            fp = fdir / f"frame_{fr:04d}.png"
            if fp.exists() and "--force" not in a:
                continue
            scn.frame_set(fr)
            render_png(fp, res)
            print(f"FRAME {fr}/{fb} {_t.time() - t0:.0f}s", flush=True)
        print(f"RENDER {fdir} frames {fa}-{fb} engine={eng} time={_t.time() - t0:.1f}s", flush=True)
        return
    dt = render_png(out, res)
    print(f"RENDER {out} tiles lod0={n['lod0']} lod1={n['lod1']} engine={eng} sun elev={elev:.1f} az={az:.1f} "
          f"time={dt:.1f}s", flush=True)


main()
