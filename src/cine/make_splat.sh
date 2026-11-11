#!/usr/bin/env bash
# Gaussian splat of the pilot district: capture calibrated RGB+depth views in Blender, then build the splat.
#   ./src/cine/make_splat.sh [aerial_voxel_m] [street_voxel_m]     -> out/splat/sf_twin_pilot.{ply,splat,json}
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
$B -b --factory-startup -P src/blender/render_city.py -- --pilot --lod lod1 --no-ocean --res 1280x720 --samples 32 \
  --preset sunny --splat-capture data/splat $SPLAT_EXTRA --out renders/cinematic/unused.png 2>&1 | grep -E "SPLAT|Traceback"
.venv/bin/python src/cine/build_splat.py data/splat out/splat/sf_twin_pilot ${1:-1.0} ${2:-0.3}
