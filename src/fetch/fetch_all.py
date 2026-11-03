"""Phase 2: download + cache every source for the full city into data/raw (immutable cache).

Idempotent: a source whose output already exists is skipped unless --force.
Every download goes to <file>.part and is renamed on success.
Writes data/raw/fetch_manifest.json (url, bytes, sha256, records, license, fetched_at).

python src/fetch/fetch_all.py [--force] [--only buildings,dem,...]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

RAW = crs.ROOT / "data/raw"
MANIFEST = RAW / "fetch_manifest.json"
SODA = "https://data.sf.gov/resource"
UA = {"User-Agent": "sf-digital-twin/0.1 (research; contact via repo)"}

LICENSES = {
    "datasf": "DataSF open data: ODC Public Domain Dedication and License (PDDL) 1.0",
    "osm": "OpenStreetMap: ODbL 1.0, (c) OpenStreetMap contributors",
    "usgs": "USGS 3DEP: US public domain",
    "noaa": "NOAA NCEI DEM mosaic: US public domain",
    "census": "US Census Bureau cartographic boundary: US public domain",
    "sfmta": "SFMTA GTFS: SFMTA open data terms of use",
}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def download(url: str, out: Path, params=None, retries=4, timeout=600) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    for k in range(retries):
        try:
            with requests.get(url, params=params, headers=UA, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(part, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            part.replace(out)
            return out
        except Exception as e:  # noqa: BLE001
            log(f"  retry {k + 1}/{retries} {out.name}: {e}")
            time.sleep(3 * (k + 1))
    raise RuntimeError(f"failed: {url}")


# ---------------------------------------------------------------- sources
def soda_geojson(dataset: str, out: Path, page=50000) -> dict:
    """Page through a Socrata dataset as GeoJSON and write one FeatureCollection."""
    n = int(requests.get(f"{SODA}/{dataset}.json", params={"$select": "count(*)"},
                         headers=UA, timeout=60).json()[0]["count"])
    feats = []
    tmpdir = out.parent / f".{out.stem}_pages"
    for off in range(0, n, page):
        pp = tmpdir / f"{off:07d}.geojson"
        if not pp.exists():
            download(f"{SODA}/{dataset}.geojson", pp,
                     params={"$limit": page, "$offset": off, "$order": ":id"})
        feats += json.loads(pp.read_text())["features"]
        log(f"  {dataset}: {len(feats)}/{n}")
    part = out.with_name(out.name + ".part")
    part.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    part.replace(out)
    for pp in tmpdir.glob("*"):
        pp.unlink()
    tmpdir.rmdir()
    return {"records": len(feats), "source_count": n}


def soda_csv(dataset: str, out: Path) -> dict:
    n = int(requests.get(f"{SODA}/{dataset}.json", params={"$select": "count(*)"},
                         headers=UA, timeout=60).json()[0]["count"])
    download(f"{SODA}/{dataset}.csv", out, params={"$limit": n + 1000, "$order": ":id"})
    rows = sum(1 for _ in open(out, encoding="utf-8")) - 1  # approximation if fields have newlines
    return {"records_lines": rows, "source_count": n}


def fetch_dem_3dep(out_dir: Path, workers=4, chunk_m=2000) -> dict:
    """USGS 3DEP 1 m bare-earth via ImageServer exportImage, chunked over the full grid extent."""
    idx = json.loads((crs.ROOT / "data/processed/tile_index.json").read_text())
    ox, oy = crs.origin_world()
    x0, y0, x1, y1 = idx["extent_city"]
    X0, Y0 = ox + x0, oy + y0
    nx, ny = math.ceil((x1 - x0) / chunk_m), math.ceil((y1 - y0) / chunk_m)
    url = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
    jobs = []
    for i in range(nx):
        for j in range(ny):
            bx0, by0 = X0 + i * chunk_m, Y0 + j * chunk_m
            p = out_dir / f"3dep1m_{int(bx0)}_{int(by0)}.tif"
            jobs.append((p, {
                "bbox": f"{bx0},{by0},{bx0 + chunk_m},{by0 + chunk_m}", "bboxSR": 26910, "imageSR": 26910,
                "size": f"{chunk_m},{chunk_m}", "format": "tiff", "pixelType": "F32",
                "noDataInterpretation": "esriNoDataMatchAny",
                "interpolation": "RSP_BilinearInterpolation", "f": "image"}))
    log(f"  3DEP: {nx * ny} chunks, {len(jobs)} to fetch")
    def get(p, prm, depth=0):
        """On persistent server errors, split the chunk into 4 quadrants (down to 500 m)."""
        try:
            return download(url, p, prm, retries=3 if depth < 2 else 6)
        except RuntimeError:
            if depth >= 2:
                raise
            bx0, by0, bx1, by1 = map(float, prm["bbox"].split(","))
            h = (bx1 - bx0) / 2
            log(f"  split {p.name} -> 4 x {h:.0f} m")
            for qx in (bx0, bx0 + h):
                for qy in (by0, by0 + h):
                    q = out_dir / f"3dep1m_{int(qx)}_{int(qy)}_{int(h)}.tif"
                    if not q.exists():
                        get(q, {**prm, "bbox": f"{qx},{qy},{qx + h},{qy + h}", "size": f"{int(h)},{int(h)}"},
                            depth + 1)

    def covered(p):  # chunk already present whole or as quadrants
        return p.exists() or len(list(out_dir.glob(p.stem + "_*.tif"))) >= 4

    jobs = [(p, prm) for p, prm in jobs if not covered(p)]
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(get, p, prm): p for p, prm in jobs}
        for k, f in enumerate(cf.as_completed(futs)):
            f.result()
            if k % 8 == 0:
                log(f"  3DEP {k + 1}/{len(jobs)}")
    files = sorted(out_dir.glob("3dep1m_*.tif"))
    return {"chunks": len(files), "chunk_m": chunk_m, "res_m": 1.0,
            "bytes": sum(f.stat().st_size for f in files)}


def fetch_dem_ncei(out: Path, res=5.0) -> dict:
    """NOAA NCEI DEM_all mosaic (best-available topobathy incl. SF Bay CUDEM), NAVD88."""
    idx = json.loads((crs.ROOT / "data/processed/tile_index.json").read_text())
    ox, oy = crs.origin_world()
    x0, y0, x1, y1 = idx["extent_city"]
    w, h = int((x1 - x0) / res), int((y1 - y0) / res)
    download("https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer/exportImage", out,
             params={"bbox": f"{ox + x0},{oy + y0},{ox + x1},{oy + y1}", "bboxSR": 26910, "imageSR": 26910,
                     "size": f"{w},{h}", "format": "tiff", "pixelType": "F32",
                     "interpolation": "RSP_BilinearInterpolation", "f": "image"})
    return {"size_px": [w, h], "res_m": res}


SOURCES = {
    # name: (license key, output path, fetch fn, url-for-manifest)
    "boundary_neighborhoods": ("datasf", "datasf/analysis_neighborhoods.geojson",
                               lambda p: soda_geojson("j2bu-swwd", p), f"{SODA}/j2bu-swwd"),
    "buildings": ("datasf", "datasf/building_footprints.geojson",
                  lambda p: soda_geojson("ynuv-fyni", p), f"{SODA}/ynuv-fyni"),
    "street_trees": ("datasf", "datasf/street_trees.csv",
                     lambda p: soda_csv("tkzw-k3nq", p), f"{SODA}/tkzw-k3nq"),
    "parks_rpd": ("datasf", "datasf/rpd_parks.geojson",
                  lambda p: soda_geojson("3nje-yn2u", p), f"{SODA}/3nje-yn2u"),
    "osm": ("osm", "osm/SanFrancisco.osm.pbf",
            lambda p: download("https://download.bbbike.org/osm/bbbike/SanFrancisco/SanFrancisco.osm.pbf", p)
            and {}, "https://download.bbbike.org/osm/bbbike/SanFrancisco/"),
    "census_counties": ("census", "census/cb_2023_us_county_500k.zip",
                        lambda p: download("https://www2.census.gov/geo/tiger/GENZ2023/shp/"
                                           "cb_2023_us_county_500k.zip", p) and {},
                        "https://www2.census.gov/geo/tiger/GENZ2023/shp/"),
    "dem_3dep": ("usgs", "dem/3dep1m", fetch_dem_3dep,
                 "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"),
    "dem_ncei": ("noaa", "dem/ncei_topobathy_5m.tif", fetch_dem_ncei,
                 "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer"),
    # optional (future live layers): 511.org requires a free API key in $SF511_API_KEY
    "gtfs_muni": ("sfmta", "gtfs/muni_gtfs.zip",
                  lambda p: download("https://api.511.org/transit/datafeeds", p,
                                     params={"api_key": os.environ["SF511_API_KEY"], "operator_id": "SF"}) and {},
                  "https://api.511.org/transit/datafeeds?operator_id=SF"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for name, (lic, rel, fn, url) in SOURCES.items():
        if only and name not in only:
            continue
        out = RAW / rel
        is_dir = out.suffix == ""
        done = (out.is_dir() and name in man and man[name].get("complete")) if is_dir else out.exists()
        if done and not a.force and name in man:
            log(f"skip {name} (cached)")
            continue
        if name == "gtfs_muni" and not os.environ.get("SF511_API_KEY"):
            log("skip gtfs_muni (optional; set SF511_API_KEY to fetch Muni GTFS for live layers)")
            continue
        log(f"fetch {name}")
        t = time.time()
        if is_dir:
            out.mkdir(parents=True, exist_ok=True)
        info = fn(out) or {}
        rec = {"url": url, "path": rel, "license": LICENSES[lic],
               "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
               "seconds": round(time.time() - t, 1), **info, "complete": True}
        if not is_dir:
            rec["bytes"] = out.stat().st_size
            rec["sha256"] = sha256(out)
        man[name] = rec
        MANIFEST.write_text(json.dumps(man, indent=1))
        log(f"  done {name}: {({k: v for k, v in rec.items() if k not in ('url', 'license', 'sha256')})}")


if __name__ == "__main__":
    main()
