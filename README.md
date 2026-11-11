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
Textures and sky HDRIs: Poly Haven, CC0 1.0 (`data/raw/textures/textures_manifest.json` lists every
asset). No other third-party assets are used: all 3D geometry is generated procedurally.

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

## Game-look rendering in Blender (EEVEE + VFX stack)
`./src/blender/render_showcase.sh [1920x1080]` renders `renders/showcase/` (contact sheet and before/after
images). Any view works through `render_city.py ... --preset golden_hour|midday|blue_hour|night --look
golden|day|dusk|night [--wet 0.8] [--dof 150,4] [--lamp-lights 400]`.
- **Materials:** CC0 Poly Haven PBR texture sets (asphalt, concrete, plaster, brick, clay roof tiles,
  aerial grass/sand/rock/forest, gravel) on metre-scale UVs. Facades get a per-building palette, about 22%
  brick, reflective windows and per-tower tinted glass curtain walls. Wet roads use puddles and gloss
  driven by `sf_wetness`. Cars have clear-coat paint in 8 colours. Foliage is translucent with colour
  variation.
- **All materials live in one shared library**, `out/city/sf_materials.blend`, which every tile links.
  This means textures load once per render: a city render uses 5.4 GB, where per-tile copies ran out of
  memory. Material tweaks need only `build_material_library.py`, not a tile rebuild.
- **Lighting:** physical sun from the solar position, warming near the horizon. A CC0 photographed sky
  HDRI per preset is used for the camera and reflections, rotated so its sun matches the real azimuth.
  Procedural sky provides fill. EEVEE ray-traced reflections, fast GI and soft shadows are enabled.
- **Post (compositor):** mist-pass atmospheric haze, Fog-Glow bloom, lens dispersion, lift/gain grade,
  S-curve, vignette and film grain.
- **Street life** (`geom/props.py`, deterministic): 55,335 street lamps and 334,612 parked and moving cars
  (3 body types, 8 paints, head and tail lights that turn on at night), Geometry Nodes instanced. At night
  the N nearest lamps become real point lights and the rest stay emissive.
- **Trees:** lobed, noise-displaced crowns, tiered conifers and frond palms (LOD1); cheap silhouettes
  (LOD0).

## Cinematic pipeline (Cycles path tracing, 8K PBR, street + facade detail, drone/drive)
`./src/blender/render_cinematic.sh preview|final|anim` (see the header of the script). Pilot district only for
now: the detail layer and new props are built for the 16 pilot tiles (`mesh_tiles.py --layers details,props --pilot`).
- **Engines:** EEVEE for fast previews (64 samples), Cycles path tracing for finals (`--engine CYCLES --samples
  128..256`), Metal GPU only (`set_engine` enables just the METAL device), OpenImageDenoise, adaptive sampling,
  AgX colour management, 3840x2160. Measured on the M5 Pro: one 4K frame at 128 samples takes about 4 minutes.
- **Textures:** CC0 Poly Haven photoscanned sets: asphalt, concrete, brick, plaster, metal (with metalness map) and
  wood at 2K/4K/8K. `SF_TEX_RES=4k|8k` repoints the shared material library at `sf_materials_<res>.blend` (build it
  with `SF_TEX_RES=8k blender -b -P src/blender/build_material_library.py`); the default stays 2K so city-wide
  renders fit in memory. Scale is set by metre-scale UVs (props use object-space projection). Glass is procedural.
- **Lighting:** physical sun + sky HDRI, soft area fill and warm kicker (`--area`), real point lights on nearby
  street lamps, a local volumetric fog box with forward scattering for god rays (`--atmo density`), compositor
  grade (bloom, lens dispersion, lift/gain, S-curve, vignette, grain). `--fog` scales the mist-pass haze.
- **Street detail** (`geom/details.py`, LOD1): curbs, double-yellow / dashed lane markings, parking-edge lines,
  zebra crosswalks at junctions. **Facades:** plinth, cornice and parapet rings, balconies with railings and window
  sills, placed on the facade shader's window grid so they line up with the glass.
- **Props** (`geom/props.py`, `props_instancing.py`): traffic signals with mast arms, fire hydrants, benches, bins,
  pedestrians (6 outfits), on sidewalk polygons only, plus the existing lamps, cars and trees.
- **Camera:** `--anim drone|drive --seconds N` flies or drives down Market St (ground height sampled from the scene).
  Frames go through the same path as stills into `renders/cinematic/<name>/frame_NNNN.png`, then
  `encode_video.py` makes an H.264 mp4 with Blender's built-in FFmpeg.
- **Not done:** window recesses (windows are shader-based), photogrammetry-scanned street props (Poly Haven has no
  hydrant/bench scans), a rigged driving car in frame, and the detail layer outside the pilot area.

### 3-minute split-screen film and 8K stills (`src/cine/`)
- `make_route.py` builds the hero-car route (2.2 km along Kearny, Geary, Market and Steuart streets, a graph walk
  over real OSM ways) and the tallest-tower cluster for the drone orbit. `props.py` keeps instanced traffic off the route.
- `cameras.add_cine_car`: red hero car driven along the route (eased start/stop, pitch from the road, ground height
  ray-cast), GTA-style chase camera 9 m behind / 2.9 m up. `cameras.add_cine_drone`: waterfront approach, descending
  orbit of the tower cluster, flight down the Market St canyon, climbing pull-back over the bay; every key is pushed
  out of geometry by ray-cast clearance (cached in `data/processed/cine_drone_keys_180.json`).
- `./src/cine/render_film.sh`: 4320 frames per view (960x1080, EEVEE 64 samples, 4K textures, volumetric fog, area
  lights, motion blur), resumable, then `compose_film.py` joins them into `renders/film/sf_twin_film.mp4`
  (1920x1080 split screen with labels). Run `render_film.sh compose` any time to cut what exists so far.
- `./src/cine/render_8k.sh`: 7680x4320 stills: whole-city aerial and top-down (EEVEE) and a Cycles path-traced
  pilot hero shot with 8K textures. Full 8K Cycles animation is not practical on this machine (hours per frame).
- Shell note: run these from bash scripts. In zsh, an unquoted `$VAR` holding several flags is NOT word-split, which
  silently renders with default settings.

### Web viewer (three.js): whole city + Gaussian splat + Blender renders (`web/`)
`./web/serve.sh` then open http://localhost:8000/ (browsers block `fetch()` from `file://`). All libraries are vendored
in `web/vendor` (three r160, OrbitControls, Sky, GaussianSplats3D 0.4.6), so it works offline.
- **City:** `src/web/export_city.py` writes all 618 LOD0 tiles (7.45M triangles, 54 MB gzipped) to `web/data/tiles/`:
  int16 positions, vertex colours from the land-use/road/facade palettes, instanced trees. Tiles stream in nearest-first.
  Buildings get procedural windows in the shader (same bay/floor grid as the Blender facade material) and lit windows at
  night. Sun/sky/fog/AgX tone mapping, real-time shadows, time-of-day slider.
- **Splat:** `web/splat/sf_twin_pilot_web.splat` (4.55M Gaussians, 146 MB; built with
  `build_splat.py data/splat <out> 2.4 0.8 1.2`). "Load Gaussian splat" streams it in and hides the mesh under it.
- **Cycles / EEVEE:** a web page cannot run either engine. The viewer overlays the real Blender renders
  (`web/renders/*.jpg`: Cycles 8K and EEVEE of the same Market St camera, EEVEE whole-city aerial/top-down) on the live view
  with a wipe slider, and "Go to render camera" puts the live camera at the render's pose.
- **Flythroughs:** the Blender drone keyframes and the hero-car route play in the live view (`data/paths.json`).

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
