"""Hero car route through the detailed pilot district (city frame, metres): a long smooth trail along real
OSM streets (graph walk, minimal turning angle, no repeated edges). Writes data/processed/hero_route.json
({"xy": [[x,y],...] densified every 2 m, "names": [...], "length": m}).  .venv/bin/python src/cine/make_route.py"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from geom import roadclass as rc  # noqa: E402

ROOT = crs.ROOT
BOX = (-1380.0, -900.0, 380.0, 900.0)  # pilot extent shrunk so the route stays on fully detailed tiles
TARGET = 2500.0


def main():
    ox, oy = crs.origin_world()
    r = gpd.read_parquet(ROOT / "data/processed/osm/roads.parquet")
    r = r[r.highway.isin(["primary", "secondary", "tertiary", "residential", "trunk", "unclassified", "primary_link"])]
    r = r[np.array([rc.is_ground(x) for x in r.itertuples()]) & (r.geom_type == "LineString").to_numpy()]
    edges = []
    for row in r.itertuples():
        xy = np.array(row.geometry.coords) - (ox, oy)
        if not (BOX[0] < xy[:, 0].min() and xy[:, 0].max() < BOX[2] and BOX[1] < xy[:, 1].min() and xy[:, 1].max() < BOX[3]):
            continue
        if shapely.LineString(xy).length < 15:
            continue
        edges.append((xy, row.name if isinstance(row.name, str) else "", row.highway))
    key = lambda p: (round(p[0] / 1.0), round(p[1] / 1.0))  # noqa: E731
    adj = {}
    for i, (xy, nm, hw) in enumerate(edges):
        adj.setdefault(key(xy[0]), []).append((i, 0))
        adj.setdefault(key(xy[-1]), []).append((i, 1))
    print(len(edges), "edges", len(adj), "nodes")
    best = None
    rng = np.random.default_rng(3)
    starts = [k for k, v in adj.items() if len(v) >= 2]
    for trial in range(400):
        k = starts[rng.integers(len(starts))]
        used, path, names, length, prev_dir = set(), [], [], 0.0, None
        while length < TARGET:
            cand = []
            for (i, end) in adj.get(k, []):
                if i in used:
                    continue
                xy = edges[i][0] if end == 0 else edges[i][0][::-1]
                d = xy[min(3, len(xy) - 1)] - xy[0]
                d /= np.linalg.norm(d) + 1e-9
                turn = 0.0 if prev_dir is None else np.degrees(np.arccos(np.clip(prev_dir @ d, -1, 1)))
                if turn > 110:
                    continue
                cand.append((turn + rng.uniform(0, 35) - (15 if edges[i][2] in ("primary", "secondary") else 0), i, xy))
            if not cand:
                break
            _, i, xy = min(cand, key=lambda c: c[0])
            used.add(i)
            seg = shapely.LineString(xy)
            if path:  # drop the duplicated junction vertex
                path.append(xy[1:])
            else:
                path.append(xy)
            names.append(edges[i][1])
            length += seg.length
            prev_dir = (xy[-1] - xy[-4 if len(xy) > 4 else 0])
            prev_dir /= np.linalg.norm(prev_dir) + 1e-9
            k = key(xy[-1])
        # score: length reached, few distinct turns
        score = min(length, TARGET) - 20 * len([n for n in names if n]) * 0
        if best is None or score > best[0]:
            best = (score, np.concatenate(path), names, length)
    score, pts, names, length = best
    line = shapely.LineString(pts)
    dense = shapely.get_coordinates(shapely.line_interpolate_point(line, np.arange(0, line.length, 2.0)))
    out = ROOT / "data/processed/hero_route.json"
    out.write_text(json.dumps({"xy": dense.round(2).tolist(), "names": names, "length": line.length}))
    print(f"route {line.length:.0f} m via", " > ".join(dict.fromkeys(n for n in names if n)), "->", out)


def cluster(top=14):
    """Tallest pilot buildings -> centroid (city frame) + max roof height, for the drone orbit."""
    import glob
    import pandas as pd
    ox, oy = crs.origin_world()
    rows = []
    for f in glob.glob(str(ROOT / "data/processed/tiles/*/buildings_meta.parquet")):
        d = Path(f).parent
        m = pd.read_parquet(f).set_index("bid")
        g = gpd.read_parquet(d / "buildings.parquet")[["bid", "geometry"]].set_index("bid")
        m = m.join(g, how="inner")
        for _, r in m.iterrows():
            cx, cy = r["geometry"].centroid.x - ox, r["geometry"].centroid.y - oy
            if -1450 < cx < 450 and -950 < cy < 950:  # pilot extent only
                rows.append((float(r["roof"]), cx, cy))
    rows.sort(reverse=True)
    t = np.array(rows[:top])
    out = ROOT / "data/processed/hero_cluster.json"
    out.write_text(json.dumps({"center": t[:, 1:].mean(0).tolist(), "top": float(t[:, 0].max()),
                               "towers": t.tolist()}))
    print("cluster centre", t[:, 1:].mean(0).round(0), "top roof", t[:, 0].max().round(0))


if __name__ == "__main__":
    main()
    cluster()
