"""Sun/sky for San Francisco with a time-of-day parameter. Runs inside Blender.

solar_position() implements the NOAA solar calculator equations (accuracy ~0.01 deg, ample here).
setup_sun_sky(scene, "2026-06-21T17:00", tz=-7) -> sun lamp + physical sky aligned to the sun.
Blender axes: +X east, +Y north (city frame), Z up.
"""
from __future__ import annotations

import datetime as dt
import math

import bpy

SF_LAT, SF_LON = 37.7749, -122.4194


def solar_position(when: dt.datetime, lat=SF_LAT, lon=SF_LON) -> tuple[float, float]:
    """(elevation_deg, azimuth_deg clockwise from north) for a timezone-aware datetime."""
    u = when.astimezone(dt.timezone.utc)
    jd = (u - dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc)).total_seconds() / 86400 + 2451545.0
    jc = (jd - 2451545) / 36525
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    c = (math.sin(math.radians(m)) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(math.radians(2 * m)) * (0.019993 - 0.000101 * jc) + math.sin(math.radians(3 * m)) * 0.000289)
    tl = l0 + c
    om = 125.04 - 1934.136 * jc
    lam = tl - 0.00569 - 0.00478 * math.sin(math.radians(om))
    eps0 = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(math.radians(om))
    dec = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lam))))
    y = math.tan(math.radians(eps / 2)) ** 2
    eqt = 4 * math.degrees(y * math.sin(2 * math.radians(l0)) - 2 * e * math.sin(math.radians(m))
                           + 4 * e * y * math.sin(math.radians(m)) * math.cos(2 * math.radians(l0))
                           - 0.5 * y * y * math.sin(4 * math.radians(l0)) - 1.25 * e * e * math.sin(2 * math.radians(m)))
    mins = u.hour * 60 + u.minute + u.second / 60
    tst = (mins + eqt + 4 * lon) % 1440
    ha = tst / 4 - 180 if tst / 4 >= 0 else tst / 4 + 180
    la, de, h = math.radians(lat), math.radians(dec), math.radians(ha)
    zen = math.acos(max(-1, min(1, math.sin(la) * math.sin(de) + math.cos(la) * math.cos(de) * math.cos(h))))
    az = math.degrees(math.acos(max(-1, min(1, (math.sin(la) * math.cos(zen) - math.sin(de))
                                              / (math.cos(la) * math.sin(zen))))))
    az = (az + 180) % 360 if ha > 0 else (540 - az) % 360
    return 90 - math.degrees(zen), az


def setup_sun_sky(scn, when: str = "2026-09-21T16:00", tz_hours: float = -7, strength: float = 1.0):
    t = dt.datetime.fromisoformat(when).replace(tzinfo=dt.timezone(dt.timedelta(hours=tz_hours)))
    elev, az = solar_position(t)
    sun = bpy.data.objects.get("Sun") or bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    if sun.name not in scn.collection.objects:
        scn.collection.objects.link(sun)
    # below the horizon the sun contributes nothing; the sky fades through civil twilight (-6..+6 deg)
    sun.data.energy = 0.0 if elev <= 0 else 4.5 * strength * math.sin(math.radians(max(elev, 1))) ** 0.35
    twilight = min(1.0, max(0.004, (elev + 6.0) / 12.0))
    sun.data.angle = math.radians(0.53)
    # light travels along -Z of the lamp: tilt by zenith, then spin so it points away from the sun azimuth
    sun.rotation_euler = (math.radians(90 - max(elev, 0.5)), 0, math.radians(180 - az))
    sun["elevation_deg"], sun["azimuth_deg"], sun["time"] = elev, az, when
    world = scn.world or bpy.data.worlds.new("World")
    scn.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeTexSky")
    for st in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "NISHITA"):
        try:
            sky.sky_type = st
            break
        except TypeError:
            continue
    for attr, val in (("sun_elevation", math.radians(max(elev, 0.5))), ("sun_rotation", math.radians(90 - az)),
                      ("altitude", 50.0), ("air_density", 1.0), ("aerosol_density", 2.0), ("dust_density", 2.0), ("sun_disc", True)):
        try:
            setattr(sky, attr, val)
        except (AttributeError, TypeError):
            pass
    # 5.x physical sky is very bright: weak as fill light, full strength where the camera sees it
    bg.inputs["Strength"].default_value = 0.05 * strength * twilight
    bgc = nt.nodes.new("ShaderNodeBackground")
    bgc.inputs["Strength"].default_value = 0.6 * strength * twilight
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(sky.outputs["Color"], bgc.inputs["Color"])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg.outputs["Background"], mix.inputs[1])
    nt.links.new(bgc.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return elev, az


# ---------------------------------------------------------------- Phase 10: presets, haze, glare
# Haze is 0 in Blender: an EEVEE world volume over 10+ km extinguishes the whole frame (verified black
# render, Phase 10). Atmospheric perspective/fog is done properly in Unreal (Exponential Height Fog).
PRESETS = {
    #              local time (PDT)      night  exposure  haze density  sky   moon
    "golden_hour": ("2026-09-21T18:35", 0.15, 0.3, 0.0, 1.0, 0.0),
    "midday":      ("2026-06-21T13:00", 0.00, -0.3, 0.0, 1.0, 0.0),
    "blue_hour":   ("2026-09-21T19:25", 0.45, 1.4, 0.0, 1.0, 0.0),
    "night":       ("2026-09-21T22:30", 1.00, 0.2, 0.0, 1.0, 0.06),
}


def apply_preset(scn, name="golden_hour", wetness=0.0):
    import materials
    when, night, expo, haze, sky, moon = PRESETS[name]
    elev, az = setup_sun_sky(scn, when)
    materials.set_globals(night=night, wetness=wetness)
    scn.view_settings.exposure = expo
    nt = scn.world.node_tree
    if haze > 0:  # atmospheric perspective: thin volume scatter in the world
        vs = nt.nodes.new("ShaderNodeVolumeScatter")
        vs.inputs["Density"].default_value = haze
        vs.inputs["Color"].default_value = (0.75, 0.82, 0.92, 1) if night < 0.5 else (0.25, 0.28, 0.35, 1)
        nt.links.new(vs.outputs[0], nt.nodes["World Output"].inputs["Volume"])
        for attr, val in (("volumetric_end", 25000.0), ("volumetric_tile_size", "8"),
                          ("volumetric_samples", 32)):
            try:
                setattr(scn.eevee, attr, val)
            except (AttributeError, TypeError):
                pass
    if moon > 0:
        mo = bpy.data.objects.new("Moon", bpy.data.lights.new("Moon", "SUN"))
        scn.collection.objects.link(mo)
        mo.data.energy = moon
        mo.data.color = (0.6, 0.7, 1.0)
        mo.rotation_euler = (math.radians(40), 0, math.radians(200))
    if night >= 0.5:
        add_glare(scn)
    scn["lighting_preset"] = name
    return elev, az


def add_glare(scn):
    """Bloom-like glare for emissive windows (compositor). Works with the 5.x node-group compositor and
    falls back to the legacy scene node tree; skipped (logged) if neither API is available."""
    try:
        if hasattr(scn, "compositing_node_group"):
            g = bpy.data.node_groups.new("SF_Comp", "CompositorNodeTree")
            g.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            rl = g.nodes.new("CompositorNodeRLayers")
            gl = g.nodes.new("CompositorNodeGlare")
            out = g.nodes.new("NodeGroupOutput")
            for attr, val in (("glare_type", "FOG_GLOW"), ("quality", "MEDIUM"), ("size", 7), ("threshold", 1.0)):
                try:
                    setattr(gl, attr, val)
                except (AttributeError, TypeError):
                    pass
            for nm, val in (("Type", "Fog Glow"), ("Threshold", 1.0), ("Size", 0.6), ("Strength", 0.8)):
                if nm in gl.inputs:
                    try:
                        gl.inputs[nm].default_value = val
                    except (TypeError, ValueError):
                        pass
            g.links.new(rl.outputs["Image"], gl.inputs["Image"])
            g.links.new(gl.outputs["Image"], out.inputs["Image"])
            scn.compositing_node_group = g
        else:
            scn.use_nodes = True
            t = scn.node_tree
            rl, comp = t.nodes["Render Layers"], t.nodes["Composite"]
            gl = t.nodes.new("CompositorNodeGlare")
            gl.glare_type, gl.threshold, gl.size = "FOG_GLOW", 1.0, 7
            t.links.new(rl.outputs["Image"], gl.inputs["Image"])
            t.links.new(gl.outputs["Image"], comp.inputs["Image"])
        print("GLARE ok")
    except Exception as e:  # noqa: BLE001
        print(f"GLARE skipped: {e}")
