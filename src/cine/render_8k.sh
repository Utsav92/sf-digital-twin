#!/usr/bin/env bash
# 8K (7680x4320) city stills. EEVEE for the whole city (2K textures, fits memory), Cycles path tracing + 8K PBR
# textures for the detailed pilot hero shot.   ./src/cine/render_8k.sh [samples]
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
S=${1:-128}
RES=7680x4320
$B -b --factory-startup -P src/blender/render_city.py -- --all --lod auto --lod1-radius 2500 --res $RES --samples 64 \
  --target -3500,-1500,0 --az 150 --elev 38 --dist 25000 --lens 40 --preset sunny --look golden --fog 0.2 \
  --out renders/8k/sf_city_aerial_8k.png 2>&1 | grep -E "RENDER|Traceback"
$B -b --factory-startup -P src/blender/render_city.py -- --all --lod lod0 --view top --res $RES --samples 64 \
  --preset midday --look day --fog 0.1 --out renders/8k/sf_city_topdown_8k.png 2>&1 | grep -E "RENDER|Traceback"
SF_TEX_RES=8k $B -b --factory-startup -P src/blender/render_city.py -- --pilot --lod lod1 --engine CYCLES --res $RES \
  --samples $S --target -150,-120,18 --cam -960,-958,26 --lens 32 --preset sunny --look golden --fog 0.25 \
  --atmo 0.0009 --atmo-size 1800 --area 0.8 --lamp-lights 150 --out renders/8k/market_st_cycles_8k.png 2>&1 | grep -E "RENDER|TEXRES|Traceback"
