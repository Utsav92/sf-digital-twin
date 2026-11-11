# Data licence audit
Source: the sf_twin README licence table and `data/raw/fetch_manifest.json` (URL, size, sha256). I did not re-fetch or re-verify licences in this session.

| Data | Source | Licence per sf_twin |
|---|---|---|
| Building footprints + 2010 LiDAR heights | DataSF ynuv-fyni | ODC PDDL 1.0 |
| Street trees, neighbourhoods, parks | DataSF tkzw-k3nq, j2bu-swwd, 3nje-yn2u | ODC PDDL 1.0 |
| Roads, rail, water, land use, OSM buildings | OpenStreetMap (BBBike extract 2026-10-31) | ODbL 1.0, attribution "(c) OpenStreetMap contributors" required |
| 1 m DEM | USGS 3DEP | US public domain |
| Bathymetry | NOAA NCEI | US public domain |
| Textures / HDRIs | Poly Haven | CC0 |
| Geometry | procedurally generated in sf_twin | original |

Open: Cesium ion datasets (needs account/terms), splat sources, Muni GTFS (needs a 511.org key). Procedural facades, roofs and landmark approximations are not exact building measurements; 2010 LiDAR heights are stale for newer towers (overridden by OSM where available).
