"""'Game look' render stack for EEVEE: engine quality, atmosphere via the mist pass, and a compositor
post chain (bloom, lens dispersion, grade, S-curve, vignette, grain). Runs inside Blender.

apply(scn, look="day"|"dusk"|"night", fog=1.0, dof=None)
"""
import bpy

LOOKS = {
    #        fog colour            fog start, depth, max   glare thr, glare str  lift          gain          grain
    "day":    ((0.74, 0.80, 0.88), 900.0, 22000.0, 0.28, 1.4, 0.35, (0.98, 1.00, 1.03), (1.03, 1.01, 0.97), 0.025),
    "golden": ((0.90, 0.78, 0.66), 1200.0, 26000.0, 0.22, 1.2, 0.45, (0.96, 0.99, 1.05), (1.09, 1.01, 0.90), 0.025),
    "dusk":   ((0.80, 0.62, 0.58), 500.0, 10000.0, 0.40, 1.0, 0.55, (0.99, 0.99, 1.02), (1.10, 1.01, 0.90), 0.03),
    "night": ((0.10, 0.12, 0.18), 300.0, 6000.0, 0.50, 0.6, 0.90, (0.95, 0.99, 1.08), (1.06, 1.00, 0.94), 0.035),
}


def engine(scn, samples=64):
    e = scn.eevee
    for attr, val in (("taa_render_samples", samples), ("use_raytracing", True), ("ray_tracing_method", "SCREEN"),
                      ("use_fast_gi", True), ("fast_gi_method", "GLOBAL_ILLUMINATION"), ("fast_gi_resolution", "2"),
                      ("fast_gi_distance", 40.0), ("shadow_resolution_scale", 1.0), ("shadow_ray_count", 2),
                      ("shadow_step_count", 8), ("use_shadows", True), ("gi_diffuse_bounces", 2)):
        try:
            setattr(e, attr, val)
        except (AttributeError, TypeError):
            pass
    try:
        e.ray_tracing_options.resolution_scale = "1"
        e.ray_tracing_options.use_denoise = True
    except (AttributeError, TypeError):
        pass
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Base Contrast"
    except TypeError:
        pass
    scn.render.film_transparent = False


def _n(g, t, **inputs):
    n = g.nodes.new(t)
    for k, v in inputs.items():
        try:
            n.inputs[k].default_value = v
        except (KeyError, TypeError):
            setattr(n, k, v)
    return n


def compositor(scn, look):
    fog, fstart, fdepth, fmax, gthr, gstr, lift, gain, grain = LOOKS[look]
    vl = bpy.context.view_layer
    vl.use_pass_mist = True
    w = scn.world
    w.mist_settings.start, w.mist_settings.depth, w.mist_settings.falloff = fstart, fdepth, "QUADRATIC"
    g = bpy.data.node_groups.new("SF_GameLook", "CompositorNodeTree")
    g.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    L = g.links
    rl = g.nodes.new("CompositorNodeRLayers")
    # 1) atmospheric perspective: fog colour mixed in by the mist pass (clamped to fmax)
    fogf = _n(g, "ShaderNodeMath", operation="MULTIPLY")
    L.new(rl.outputs["Mist"], fogf.inputs[0])
    fogf.inputs[1].default_value = fmax
    fogmix = _n(g, "ShaderNodeMix")
    fogmix.data_type = "RGBA"
    L.new(fogf.outputs[0], fogmix.inputs["Factor"])
    L.new(rl.outputs["Image"], fogmix.inputs["A"])
    fogmix.inputs["B"].default_value = (*fog, 1)
    # 2) bloom
    gl = g.nodes.new("CompositorNodeGlare")
    for k, v in (("Type", "Fog Glow"), ("Quality", "High"), ("Threshold", gthr), ("Strength", gstr),
                 ("Size", 0.7), ("Smoothness", 0.4)):
        try:
            gl.inputs[k].default_value = v
        except (KeyError, TypeError, ValueError):
            pass
    L.new(fogmix.outputs["Result"], gl.inputs["Image"])
    # 3) lens dispersion (subtle chromatic aberration)
    ld = g.nodes.new("CompositorNodeLensdist")
    ld.inputs["Dispersion"].default_value = 0.004
    L.new(gl.outputs["Image"], ld.inputs["Image"])
    # 4) grade: lift/gain (cool shadows, warm highlights, restrained)
    cb = g.nodes.new("CompositorNodeColorBalance")
    try:
        cb.inputs["Type"].default_value = "Lift/Gamma/Gain"
    except (KeyError, TypeError):
        pass
    lifts = [i for i in cb.inputs if i.name == "Lift"]
    gains = [i for i in cb.inputs if i.name == "Gain"]
    for sock, val in ((lifts, lift), (gains, gain)):
        for s in sock:
            try:
                s.default_value = (*val, 1) if len(s.default_value) == 4 else val
                break
            except (TypeError, ValueError):
                continue
    L.new(ld.outputs["Image"], cb.inputs["Image"])
    # 5) gentle S-curve
    cv = g.nodes.new("CompositorNodeCurveRGB")
    c = cv.mapping.curves[3]
    c.points.new(0.25, 0.21)
    c.points.new(0.75, 0.79)
    cv.mapping.update()
    L.new(cb.outputs["Image"], cv.inputs["Image"])
    # 6) vignette
    em = g.nodes.new("CompositorNodeEllipseMask")
    for k, v in (("Size", (0.92, 0.85)), ("Value", 1.0), ("Mask", 0.0)):
        try:
            em.inputs[k].default_value = v
        except (KeyError, TypeError, ValueError):
            pass
    bl = g.nodes.new("CompositorNodeBlur")
    for k, v in (("Size", (300, 300)),):
        try:
            bl.inputs[k].default_value = v
        except (KeyError, TypeError, ValueError):
            pass
    L.new(em.outputs[0], bl.inputs[0])
    vig = _n(g, "ShaderNodeMix")
    vig.data_type = "RGBA"
    vig.blend_type = "MULTIPLY"
    vfac = _n(g, "ShaderNodeMath", operation="SUBTRACT")
    vfac.inputs[0].default_value = 1.0
    L.new(bl.outputs[0], vfac.inputs[1])
    vs = _n(g, "ShaderNodeMath", operation="MULTIPLY")
    L.new(vfac.outputs[0], vs.inputs[0])
    vs.inputs[1].default_value = 0.45
    L.new(vs.outputs[0], vig.inputs["Factor"])
    L.new(cv.outputs["Image"], vig.inputs["A"])
    vig.inputs["B"].default_value = (0.0, 0.0, 0.0, 1)
    out_sock = vig.outputs["Result"]
    # 7) film grain
    try:
        nz = g.nodes.new("ShaderNodeTexWhiteNoise")
        nz.noise_dimensions = "2D"
        ctr = _n(g, "ShaderNodeMath", operation="SUBTRACT")
        L.new(nz.outputs["Value"], ctr.inputs[0])
        ctr.inputs[1].default_value = 0.5
        amt = _n(g, "ShaderNodeMath", operation="MULTIPLY")
        L.new(ctr.outputs[0], amt.inputs[0])
        amt.inputs[1].default_value = grain * 0.6
        add = _n(g, "ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "ADD"
        add.inputs["Factor"].default_value = 1.0
        L.new(out_sock, add.inputs["A"])
        L.new(amt.outputs[0], add.inputs["B"])
        out_sock = add.outputs["Result"]
    except Exception as e:  # noqa: BLE001
        print(f"VFX grain skipped: {e}")
    o = g.nodes.new("NodeGroupOutput")
    L.new(out_sock, o.inputs["Image"])
    scn.compositing_node_group = g
    return g


def apply(scn, look="day", dof=None, samples=64):
    engine(scn, samples)
    compositor(scn, look)
    if dof and scn.camera:  # dof = (focus distance m, f-stop)
        d = scn.camera.data.dof
        d.use_dof, d.focus_distance, d.aperture_fstop = True, dof[0], dof[1]
    print(f"VFX look={look} dof={dof}")
