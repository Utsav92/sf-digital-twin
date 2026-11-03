#!/usr/bin/env bash
# Game-look showcase stills (EEVEE + VFX stack). ./src/blender/render_showcase.sh [res]
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
RES=${1:-1920x1080}
R() { "$B" -b --factory-startup -P src/blender/render_city.py -- --lod auto --res $RES "$@" 2>&1 | grep -E "RENDER|LAMPS"; }
mkdir -p renders/showcase
R --lod1-radius 1100 --target -100,-100,22 --cam -960,-958,14.6 --lens 30 --preset blue_hour --wet 0.8 --look dusk \
  --dof 180,4 --lamp-lights 400 --out renders/showcase/01_market_st_blue_hour.png &
R --lod1-radius 1500 --target -500,-350,90 --az 235 --elev 13 --dist 1500 --lens 40 --preset golden_hour \
  --look golden --out renders/showcase/02_skyline_golden_hour.png &
wait
R --lod1-radius 1500 --target -200,-400,40 --az 140 --elev 9 --dist 1300 --lens 32 --preset night --wet 0.5 \
  --look night --lamp-lights 600 --out renders/showcase/03_embarcadero_night.png &
R --lod1-radius 2200 --target -7700,2900,120 --cam -6900,1500,110 --lens 30 --preset golden_hour --look golden \
  --out renders/showcase/04_golden_gate_golden_hour.png &
wait
R --lod1-radius 1800 --target -700,-500,120 --cam -4738,-4589,300 --lens 50 --preset golden_hour --look golden \
  --out renders/showcase/05_twin_peaks_view.png &
R --lod1-radius 1500 --target -500,-300,60 --az 215 --elev 20 --dist 1400 --lens 30 --preset golden_hour \
  --look golden --out renders/showcase/06_after_same_camera_as_phase10.png &
wait
