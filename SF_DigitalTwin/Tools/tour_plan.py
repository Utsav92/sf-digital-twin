"""Plan the 60 s tour: waypoints (lon, lat, metres above ground) -> Unreal camera keys. Run with sf_twin's venv python."""
import json, math
import numpy as np, rasterio
from pyproj import Transformer
ROOT = "/Users/utsav/sf_twin"
man = json.load(open(f"{ROOT}/out/city/manifest.json")); ox, oy = man["origin"]["world_xy"]
tr = Transformer.from_crs(4326, 26910, always_xy=True)
dem = rasterio.open(f"{ROOT}/data/processed/dem/dem_1m.tif"); dx, dy = tr.transform(0, 0)
def ue(lon, lat, agl):
    e, n = tr.transform(lon, lat); cx, cy = e - ox, n - oy
    try:   # sample DEM in world coords
        g = float(next(dem.sample([(e, n)]))[0]); g = 0.0 if not math.isfinite(g) or g < -50 else g
    except Exception: g = 0.0
    return np.array([cx * 100, -cy * 100, (max(g, 0.0) + agl) * 100])
ease = lambda t: t * t * (3 - 2 * t)
FPS = 30
def lookrot(p, q):
    d = q - p; return math.degrees(math.atan2(math.hypot(d[0], d[1]), 1) * 0) + math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))), math.degrees(math.atan2(d[1], d[0]))
def shot(name, secs, c0, c1, t0, t1, focal=28.0, orbit=None):
    n = int(secs * FPS); keys = []; lastyaw = None
    for k in range(0, n + 1, 15):
        u = ease(k / n)
        if orbit:
            (lo, la, r, a0, a1, agl) = orbit; a = math.radians(a0 + (a1 - a0) * u)
            c = ue(lo + r * math.cos(a) / 88000.0, la + r * math.sin(a) / 111200.0, agl); tgt = ue(*t0)
        else:
            c = ue(*c0) * (1 - u) + ue(*c1) * u; tgt = ue(*t0) * (1 - u) + ue(*t1) * u
        pitch, yaw = lookrot(c, tgt)
        if lastyaw is not None:
            while yaw - lastyaw > 180: yaw -= 360
            while yaw - lastyaw < -180: yaw += 360
        lastyaw = yaw; keys.append([k, *map(float, c), pitch, yaw])
    return {"name": name, "frames": n, "focal": focal, "keys": keys}
T = (-122.3969, 37.7897)   # Salesforce Tower
shots = [
 shot("reveal", 9, (-122.340, 37.812, 1200), (-122.372, 37.796, 450), (*T, 150), (*T, 200), 24),
 shot("bridge_pushin", 9, (-122.372, 37.788, 120), (-122.386, 37.789, 90), (*T, 150), (*T, 170), 35),
 shot("canyon_dive", 9, (-122.4010, 37.7930, 350), (-122.3990, 37.7905, 25), (*T, 120), (*T, 70), 24),
 shot("market_street", 9, (-122.3945, 37.7960, 130), (-122.4090, 37.7878, 130), (-122.3995, 37.7931, 70), (-122.4165, 37.7838, 70), 28),
 shot("twin_peaks", 9, (-122.4470, 37.7520, 450), (-122.4400, 37.7560, 700), (-122.40, 37.79, 100), (-122.40, 37.79, 100), 28),
 shot("tower_orbit", 8, None, None, (*T, 160), (*T, 160), 35, orbit=(T[0], T[1], 600, 200, 320, 260)),
 shot("pull_up", 7, (-122.392, 37.776, 400), (-122.392, 37.776, 3500), (-122.43, 37.76, 0), (-122.43, 37.76, 0), 24),
]
json.dump({"fps": FPS, "shots": shots}, open(f"{ROOT}/SF_DigitalTwin/Tools/tour.json", "w"))
print([(s["name"], s["frames"], len(s["keys"])) for s in shots], "total s", sum(s["frames"] for s in shots) / FPS)
print("salesforce check", ue(*T, 0).round(0), "expected approx", man["landmarks"]["salesforce"]["unreal_location_cm"])
