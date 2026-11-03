"""CRS + local-frame helpers. Runs in the prep venv (needs pyproj), NOT inside Blender.

World frame  : EPSG:26910 (UTM 10N, meters).
City frame   : world minus origin (Ferry Building), meters. x=east, y=north.
Tile frame   : city frame minus the tile center (tile.offset). Blender geometry lives here.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "city.json"


@lru_cache(maxsize=1)
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


@lru_cache(maxsize=1)
def _fwd() -> Transformer:
    return Transformer.from_crs("EPSG:4326", config()["crs"], always_xy=True)


@lru_cache(maxsize=1)
def _inv() -> Transformer:
    return Transformer.from_crs(config()["crs"], "EPSG:4326", always_xy=True)


@lru_cache(maxsize=1)
def origin_world() -> tuple[float, float]:
    o = config()["origin"]
    x, y = _fwd().transform(o["lon"], o["lat"])
    return float(x), float(y)


def lonlat_to_world(lon, lat):
    return _fwd().transform(np.asarray(lon, float), np.asarray(lat, float))


def world_to_lonlat(x, y):
    return _inv().transform(np.asarray(x, float), np.asarray(y, float))


def world_to_city(x, y):
    ox, oy = origin_world()
    return np.asarray(x, float) - ox, np.asarray(y, float) - oy


def city_to_world(x, y):
    ox, oy = origin_world()
    return np.asarray(x, float) + ox, np.asarray(y, float) + oy


def lonlat_to_city(lon, lat):
    return world_to_city(*lonlat_to_world(lon, lat))


def city_to_lonlat(x, y):
    return world_to_lonlat(*city_to_world(x, y))
