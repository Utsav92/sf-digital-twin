#!/usr/bin/env bash
# Reproduce the SF digital twin from scratch (idempotent: cached downloads/tiles are skipped).
#   ./run_all.sh                         full city, phases 1-12
#   ./run_all.sh --pilot                 2x2 km Financial District / SoMa / North Beach (16 tiles)
#   ./run_all.sh --tiles t+00_+00,t-01_+00
#   ./run_all.sh --phases 6,7            selected phases only
#   ./run_all.sh --force                 rebuild cached outputs
set -euo pipefail
cd "$(dirname "$0")"
export BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
PY=.venv/bin/python
PILOT=0; TILES=""; PHASES="1,2,3,4,5,6,7,8,9,10,11,12"; FORCE=""
while [[ $# -gt 0 ]]; do case "$1" in
  --pilot) PILOT=1;; --tiles) TILES="$2"; shift;; --phases) PHASES="$2"; shift;;
  --force) FORCE="--force";; *) echo "unknown arg $1"; exit 2;; esac; shift; done
SEL=(); [[ $PILOT == 1 ]] && SEL+=(--pilot); [[ -n "$TILES" ]] && SEL+=(--tiles "$TILES")
CHK=(); [[ $PILOT == 1 ]] && CHK+=(--pilot)
mkdir -p logs
has() { [[ ",$PHASES," == *",$1,"* ]]; }
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a logs/run_all.log; }
B() { "$BLENDER" -b --factory-startup -P "$@"; }

if [[ ! -x $PY ]]; then
  command -v uv >/dev/null || export PATH="$HOME/.local/bin:$PATH"
  uv venv --python 3.12 .venv && uv pip install --python $PY -r requirements.txt
fi

if has 1; then log "phase 1: setup, CRS, tile grid"
  "$BLENDER" --version | head -1
  $PY src/prep/make_tile_grid.py
  B src/blender/phase1_test_cube.py -- --engine EEVEE > logs/phase1.log 2>&1
  $PY src/checks/check_phase1.py; fi
if has 2; then log "phase 2: fetch sources"
  $PY src/fetch/fetch_all.py $FORCE | tee logs/phase2_fetch.log
  $PY src/checks/check_phase2.py; fi
if has 3; then log "phase 3: prep (OSM, DEM, boundary, buildings, trees, bridges, tiles)"
  $PY src/prep/osm_extract.py
  $PY src/prep/prep_dem.py
  $PY src/prep/make_tile_grid.py --boundary data/processed/boundary/sf_land.gpkg
  $PY src/prep/prep_buildings.py
  $PY src/prep/prep_trees.py
  $PY src/prep/prep_water.py
  $PY src/prep/prep_bridges.py
  $PY src/prep/mesh_ocean.py
  $PY src/prep/prep_tiles.py "${SEL[@]}" $FORCE
  $PY src/checks/check_phase3.py "${CHK[@]}"; fi
if has 4 || has 5 || has 6 || has 7 || has 8; then log "phases 4-8: per-tile meshes"
  $PY src/prep/mesh_tiles.py "${SEL[@]}" $FORCE; fi
if has 9; then log "phase 9: landmarks"
  $PY src/geom/landmarks.py
  $PY src/prep/mesh_tiles.py --layers buildings --force "${SEL[@]}"; fi
if has 4 || has 5 || has 6 || has 7 || has 8 || has 9 || has 10; then log "build tile .blend files"
  $PY src/blender/build_tiles.py "${SEL[@]}" $FORCE; fi
if [[ $PILOT == 0 && -z "$TILES" ]]; then
  for c in 4 5 6 7 9; do has $c && $PY src/checks/check_phase$c.py; done
fi
if has 10; then log "phase 10: material/lighting verification renders"
  for P in golden_hour night; do
    B src/blender/render_city.py -- --lod auto --lod1-radius 1500 --target -500,-300,60 --az 215 --elev 20 \
      --dist 1400 --lens 30 --preset $P --out renders/phase10_pilot_$P.png > /dev/null 2>&1; done; fi
if has 11; then log "phase 11: Unreal export prep (USD tiles, hero landmarks, instances, manifest)"
  IDS=$($PY -c "
import json,sys; sys.path.insert(0,'src'); from prep.prep_tiles import select_tiles
idx=json.load(open('data/processed/tile_index.json'))
print(','.join(t['id'] for t in select_tiles(idx, $PILOT==1, '${TILES}' or None)))")
  B src/blender/export_unreal.py -- --tiles "$IDS" --landmarks > logs/phase11_export.log 2>&1
  $PY src/prep/export_manifest.py "${SEL[@]}"
  $PY src/checks/check_phase11.py
  B src/blender/assemble_master.py > logs/phase11_master.log 2>&1; fi
if has 12; then log "phase 12: city-wide validation renders"
  for R in aerial_N aerial_E aerial_S aerial_W; do
    B src/blender/render_city.py -- --lod lod0 --rig $R --preset golden_hour --res 1920x1080 --dist 12000 \
      --out renders/phase12_city_$R.png > /dev/null 2>&1; done
  $PY src/checks/render_spots.py --set landmarks --out renders/phase9_landmarks.png
  $PY src/checks/render_spots.py --set intersections --out renders/phase6_intersections.png
  $PY src/checks/stats.py; fi
log "done (phases=$PHASES pilot=$PILOT tiles=${TILES:-all})"
