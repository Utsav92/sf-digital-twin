"""Road classification, widths (m) and draw offsets shared by prep_roads (bridges) and geom.roads."""
from __future__ import annotations

import math
import re

import numpy as np

# material slot indices (materials.SLOTS["roads"])
MOTORWAY, ARTERIAL, LOCAL, SERVICE, PATH, SIDEWALK, BRIDGE_DECK, BRIDGE_STRUCT, PIER = range(9)
CLASS = {
    "motorway": MOTORWAY, "motorway_link": MOTORWAY, "trunk": ARTERIAL, "trunk_link": ARTERIAL,
    "primary": ARTERIAL, "primary_link": ARTERIAL, "secondary": ARTERIAL, "secondary_link": ARTERIAL,
    "tertiary": LOCAL, "tertiary_link": LOCAL, "residential": LOCAL, "unclassified": LOCAL,
    "living_street": LOCAL, "service": SERVICE, "pedestrian": PATH, "footway": PATH, "path": PATH,
    "cycleway": PATH, "steps": PATH, "track": PATH,
}
DEFAULT_LANES = {"motorway": 3, "motorway_link": 1, "trunk": 2, "trunk_link": 1, "primary": 2,
                 "primary_link": 1, "secondary": 2, "secondary_link": 1, "tertiary": 2, "tertiary_link": 1,
                 "residential": 2, "unclassified": 2, "living_street": 1, "service": 1}
LANE_W = {MOTORWAY: 3.6, ARTERIAL: 3.4, LOCAL: 3.2, SERVICE: 3.0}
PATH_W = {"pedestrian": 6.0, "footway": 2.0, "path": 2.0, "cycleway": 2.5, "steps": 2.5, "track": 3.0}
PARKING_W = 2.4
SIDEWALK_W = 2.6
# vertical offsets above terrain (m) -> layered, no z-fighting
Z_OFF = {MOTORWAY: 0.12, ARTERIAL: 0.12, LOCAL: 0.12, SERVICE: 0.11, PATH: 0.10, SIDEWALK: 0.22, PIER: 0.08}
# priority for clean intersections: earlier classes are cut out of later ones
PRIORITY = [MOTORWAY, ARTERIAL, LOCAL, SERVICE, SIDEWALK, PATH]
SKIP_FOOTWAY = {"sidewalk", "crossing", "traffic_island", "access_aisle"}


def num(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return np.nan
    m = re.match(r"^\s*([\d.]+)", str(v).split(";")[0])
    return float(m.group(1)) if m else np.nan


def width(row) -> float:
    hw = row.highway
    c = CLASS[hw]
    w = num(row.width)
    if c == PATH:
        return float(w) if 0.8 < w < 30 else PATH_W.get(hw, 2.0)
    if 3 < w < 60:
        return float(w)
    lanes = num(row.lanes)
    if not (0 < lanes < 13):
        lanes = DEFAULT_LANES.get(hw, 2)
        if tag(row.oneway) == "yes" and hw in ("residential", "tertiary", "unclassified"):
            lanes = 1
    w = lanes * LANE_W[c]
    # SF city streets carry curbside parking on both sides (not freeways, ramps, service, Lombard bricks)
    if c in (ARTERIAL, LOCAL) and not hw.endswith("_link") and tag(row.surface) not in ("paving_stones", "sett"):
        w += 2 * PARKING_W
    if c == MOTORWAY:
        w += 2.0  # shoulders
    return float(w)


def has_sidewalk(row) -> bool:
    return CLASS[row.highway] in (ARTERIAL, LOCAL) and tag(row.sidewalk) not in ("no", "none") \
        and not row.highway.endswith("_link")


def tag(v):
    """Missing OSM tag (None / NaN) -> None, else str."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)


def is_ground(row) -> bool:
    lay = tag(row.layer) or ""
    return tag(row.bridge) in (None, "no") and tag(row.tunnel) in (None, "no") \
        and tag(getattr(row, "covered", None)) != "yes" and not lay.startswith("-")


def is_bridge(row) -> bool:
    return tag(row.bridge) not in (None, "no") and tag(row.tunnel) in (None, "no")
