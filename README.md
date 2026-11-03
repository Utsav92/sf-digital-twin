# San Francisco Digital Twin

Georeferenced, real-scale, tiled 3D model of the City and County of San Francisco (Farallones excluded),
built entirely from open data by scripts. Blender is the data, geometry and asset factory. Unreal Engine 5 is
the planned final renderer (Phases 12-16, waiting on an Unreal install; see below).

## Quick start
```bash
./run_all.sh                 # whole city (make all)
./run_all.sh --pilot         # 2x2 km Financial District / SoMa / North Beach, 16 tiles (make pilot)
./run_all.sh --tiles t+00_+00,t-01_+00
./run_all.sh --phases 6,7    # selected phases; cached outputs are reused, --force rebuilds
make stats                   # totals -> out/city/stats.json
make unreal                  # fails clearly until Unreal Engine 5 is installed
```
Requires Blender (tested 5.2.3 LTS, `$BLENDER` overrides the path) and [uv](https://docs.astral.sh/uv/)
(creates `.venv`, Python 3.12, from `requirements.txt`). Measured on an Apple M5 Pro (15 cores, 24 GB):
fetch about 3 min, prep and mesh about 6 CPU-min, Blender tile builds about 20 s wall time for 618 tiles
with 6 processes.

## Reference frame
| Item | Value |
|---|---|
| Horizontal CRS | EPSG:26910, NAD83 / UTM 10N, metres |
| Vertical | NAVD88 metres; sea level drawn at 0.95 m (MSL, SF tide gauge 9414290) |
| Blender | 1 BU = 1 m, Z up |
| City frame | UTM minus origin (Ferry Building, UTM 553405.63 / 4183303.41); x = east, y = north |
| Tile frame | geometry relative to the tile centre; placed at `offset_city` (no large coordinates in Blender) |
| Grid | 500 m tiles, ID `t{i:+03d}_{j:+03d}`, 31 x 30 = 930 tiles, 618 built (land, within 150 m of land, or carrying a major bridge), 312 open water skipped |
| Unreal | cm, left-handed: UE.X = east*100, UE.Y = -north*100, UE.Z = up*100 (matches the USD importer for Z-up, metersPerUnit = 1 stages) |

## Data sources and licenses
| Data | Source | License |
|---|---|---|
| Building footprints + 2010 LiDAR heights (177,023) | DataSF `ynuv-fyni` | ODC PDDL 1.0 |
| Street Tree List (144,533) | DataSF `tkzw-k3nq` | ODC PDDL 1.0 |
| Analysis Neighborhoods (shoreline-clipped land) | DataSF `j2bu-swwd` | ODC PDDL 1.0 |
| RPD parks | DataSF `3nje-yn2u` | ODC PDDL 1.0 |
| Roads, rail, water, land use, piers, islands, OSM buildings/heights, park trees | OpenStreetMap (BBBike SanFrancisco extract, 2026-10-31) | ODbL 1.0, (c) OpenStreetMap contributors |
| 1 m bare-earth DEM | USGS 3DEP ImageServer | US public domain |
| Bathymetry / topobathy | NOAA NCEI DEM_all mosaic | US public domain |
| County boundaries (reference) | US Census cartographic boundary 2023 | US public domain |
| Muni GTFS (optional, live layers) | 511.org (needs `SF511_API_KEY`) | 511 SF Bay open data terms |

`data/raw/fetch_manifest.json` records the URL, size, sha256, record counts and fetch time for every source.
No third-party 3D assets or textures are used: all geometry and materials are procedural.

## Pipeline
```
fetch (src/fetch) -> prep (src/prep: OSM layers, merged DEM, land mask, building heights, trees, water levels,
bridge deck profiles, per-tile clip) -> mesh (src/geom via src/prep/mesh_tiles.py, numpy/shapely, per-tile .npz)
-> build (src/blender/build_tile.py: .npz -> per-tile .blend, collections <Layer>_<i>_<j>, LOD0/LOD1)
-> assemble (out/city/sf_master.blend, linked collection instances) -> export (USD/CSV/manifest for Unreal)
```
Every phase has an assertion script in `src/checks/` that exits non-zero on failure. Each phase also
writes verification renders into `renders/`.

### Key decisions (and why)
- **Building heights:** DataSF heights come from 2010 LiDAR, which predates Salesforce Tower, 181 Fremont and
  others (Salesforce reads 0.2 m). Resolved per building as `height_source`: OSM explicit height for towers
  over 40 m (391), OSM height/levels where the LiDAR is stale (796), LiDAR (167,423), small sheds kept low
  (5,317), neighbourhood median (373).
- **Building count:** 2,700 footprints lie south of the county line (Daly City/Brisbane) and are dropped.
  The city has 174,286 generic buildings plus 14 replaced by landmarks, against 174,323 in-city source
  footprints (-0.013%).
- **Terrain:** 3DEP on land and NOAA offshore, blended over 40 m. The lattice is 2 m (land tiles) or 10 m
  (water tiles). Values are bit-identical on shared edges, fine/coarse edges are stitched, and tile corners
  always take the coarse value. Lakes are carved 1.5 m below their surface. Terrain under roads is sunk
  0.35 m so draped roads never get poked through.
- **Roads:** per-class width from lanes plus parking lanes. Classes are unioned with priority subtraction,
  which gives clean intersections with no overlaps. Sidewalks are generated (OSM sidewalk/crossing ways are
  dropped to avoid doubles). Road polygons are draped on a 4 m grid, adaptively 2 m on rough terrain.
  Tunnels are omitted.
- **Bridges:** a city-wide 3D deck profile on a graph. Decks meet the ground at anchors and rise at no more
  than 5% to ground + 6.5 m x layer, or to the water clearance of the Golden Gate (67 m) and Bay Bridge.
- **Trees:** 148,005 data trees (DataSF + OSM) plus 60,661 procedural trees in OSM forest/wood polygons,
  flagged `source=procedural`. Instanced through Geometry Nodes, with 3 species classes.

## Unreal export (Phase 11, done for the pilot)
- `out/unreal/tiles/<id>/<id>.usdc`: LOD1 per tile, triangulated (Nanite-friendly), metre UVs (wall UV =
  metres along the facade x height), UsdPreviewSurface materials named 1:1 after Unreal master materials
  (`config/unreal_materials.json`, e.g. `MAT_Facade_Stucco`, `MAT_Glass_Curtain`,
  `MAT_Bridge_Steel_InternationalOrange`). Vertex colour `Col`: buildings R = per-building hash,
  G = height/400 m, B = tower flag; terrain R = land-use class / 32.
- `out/unreal/landmarks/SM_Landmark_*.usdc`: 12 hero assets, pivot at the base centre, with world placement
  in the manifest.
- `out/unreal/instances/<tile>_trees.csv`: transforms for HISM/PCG (UE cm, yaw, crown radius, height,
  species, source).
- `out/city/manifest.json`: per tile bounds, offsets (city m, UTM, UE cm), files, counts and triangles.
- Verified with pxr (`src/checks/check_phase11.py`): units and axis, no n-gons, UVs, material names, tile
  bounds = source within 1 cm, Salesforce hero top = in-city mesh within 10 cm. **The in-engine import check
  is pending until Unreal is installed.**

## Unreal Engine status
Unreal Engine is **not installed** on the build machine (`/Users/Shared/Epic Games` is absent).
Installing it needs the Epic Games Launcher, an Epic account and acceptance of the EULA, which cannot be
scripted. Once UE 5.x is installed there, `make unreal` will drive Phases 12-16.

## Known limitations
- No interiors. Roofs are flat except LiDAR-detected gables. Facades and windows are procedural (no texture
  sets yet). Vegetation uses 3 low-poly species prototypes.
- 2010 LiDAR heights for buildings that are not overridden by OSM. Footprints are current to 2023.
- 3DEP bare earth includes some excavation pits (e.g. the Transit Center) and is smoothed to 2 m.
- Road surface markings, curbs, street furniture, traffic signals and lamps are not modelled yet (planned
  as Unreal PCG / instance data).
- Bay Bridge East Span (SAS tower) and the Marin side of the Golden Gate are outside or at the edge of
  the extent. The West Span tower placement is fitted to published span lengths.
- Blender verification renders have no atmospheric haze: an EEVEE world volume at city scale blacks out
  the frame. Haze and fog are planned for Unreal height fog.
- The master .blend opens in about 10 s headless with about 8 GB peak RAM (LOD0 for the whole city, with
  LOD1 linked on demand by `sf_set_lod()`).
- Alcatraz cliff-edge paths: about 3% of their triangles dip under the rough terrain (city-wide 0.026%).

## Next steps for live layers
Muni vehicles from GTFS-Realtime (511.org): poll VehiclePositions, snap to the rail/road networks already in
the model, and drive animated instances (Blender keyframes or Unreal Mass/actors), keyed by `tile_id`.
Weather and traffic speeds drive the `sf_wetness`/`sf_night` scene globals and per-segment road attributes.
