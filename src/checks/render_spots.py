"""Render close-up spot checks (parallel headless Blender) and assemble a labelled contact sheet.

python src/checks/render_spots.py --set intersections --out renders/phase6_intersections.png [--hide ..]
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
SETS = {  # name: (lon, lat, cam azimuth, elevation, distance m[, target z])
    "landmarks": {
        "Salesforce Tower": (-122.39694, 37.78977, 225, 15, 900, 160),
        "Transamerica Pyramid": (-122.40278, 37.79519, 250, 15, 650, 120),
        "Coit Tower": (-122.40584, 37.80239, 200, 18, 260, 110),
        "Ferry Building": (-122.39340, 37.79554, 250, 18, 330, 25),
        "City Hall": (-122.41924, 37.77927, 270, 20, 380, 40),
        "Sutro Tower": (-122.45276, 37.75523, 120, 12, 700, 390),
        "Palace of Fine Arts": (-122.44843, 37.80284, 100, 25, 380, 20),
        "Oracle Park": (-122.38925, 37.77850, 200, 35, 600, 10),
        "Golden Gate Bridge": (-122.47830, 37.81800, 250, 12, 2600, 120),
        "Bay Bridge W span": (-122.38000, 37.79800, 200, 14, 2400, 80),
        "Grace Cathedral": (-122.41320, 37.79190, 250, 25, 260, 130),
        "St Mary's Cathedral": (-122.42560, 37.78450, 200, 25, 300, 60),
    },
    "intersections": {
        "Lombard St switchbacks": (-122.41875, 37.80210, 160, 40, 260),
        "US-101 / I-80 interchange": (-122.4105, 37.7690, 210, 38, 700),
        "I-280 / US-101 Alemany maze": (-122.4045, 37.7360, 200, 40, 800),
        "Market / Castro": (-122.43515, 37.76236, 200, 45, 260),
        "Market / Van Ness": (-122.41917, 37.77513, 200, 45, 300),
        "Embarcadero / Market": (-122.39500, 37.79453, 240, 40, 320),
        "Columbus / Broadway": (-122.40626, 37.79784, 200, 45, 260),
        "Geary / Masonic": (-122.44690, 37.78150, 200, 45, 300),
        "Haight / Ashbury": (-122.44687, 37.77005, 200, 50, 220),
        "19th Ave / Sloat": (-122.47567, 37.73450, 200, 45, 320),
        "3rd St / Cesar Chavez": (-122.38769, 37.75018, 200, 45, 320),
        "Bay Bridge W approach": (-122.3915, 37.7865, 250, 25, 900),
        "Presidio Pkwy tunnels": (-122.4590, 37.8025, 200, 35, 700),
        "Golden Gate Bridge S end": (-122.4770, 37.8085, 160, 25, 1300),
    },
}


def render(name, spec, outdir, extra):
    lon, lat, az, el, dist = spec[:5]
    tz = spec[5] if len(spec) > 5 else 0
    x, y = (float(v) for v in crs.lonlat_to_city(lon, lat))
    out = outdir / (name.replace("/", "_").replace(" ", "_") + ".png")
    cmd = [BLENDER, "-b", "--factory-startup", "-P", str(ROOT / "src/blender/render_city.py"), "--",
           "--lod", "auto", "--lod1-radius", str(max(700, dist * 1.2)), "--target", f"{x},{y},{tz}",
           "--az", str(az), "--elev", str(el), "--dist", str(dist), "--lens", "35", "--res", "960x640",
           "--time", "2026-09-21T14:00", "--out", str(out.relative_to(ROOT))] + extra
    subprocess.run(cmd, capture_output=True)
    return name, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="intersections")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hide", default="")
    ap.add_argument("--procs", type=int, default=5)
    a = ap.parse_args()
    outdir = ROOT / "renders/spots" / Path(a.out).stem
    outdir.mkdir(parents=True, exist_ok=True)
    extra = ["--hide", a.hide] if a.hide else []
    items = list(SETS[a.set].items())
    with ThreadPoolExecutor(a.procs) as ex:
        res = list(ex.map(lambda kv: render(kv[0], kv[1], outdir, extra), items))
    n = len(res)
    cols = 4 if n > 9 else 3
    rows = (n + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(cols * 6, rows * 4.1), dpi=90)
    for ax in axs.ravel():
        ax.axis("off")
    for ax, (name, p) in zip(axs.ravel(), res):
        if p.exists():
            ax.imshow(mpimg.imread(p))
        ax.set_title(name, fontsize=13)
    fig.tight_layout()
    fig.savefig(ROOT / a.out)
    print(f"wrote {a.out} ({sum(p.exists() for _, p in res)}/{n} renders)")


if __name__ == "__main__":
    main()
