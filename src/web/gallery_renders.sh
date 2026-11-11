#!/usr/bin/env bash
# Web gallery assets: an EEVEE render of the Market St hero camera (the Cycles one is renders/8k/market_st_cycles_8k.png),
# then JPEGs sized for the browser (sips, built in to macOS).
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
$B -b --factory-startup -P src/blender/render_city.py -- --pilot --lod lod1 --res 3840x2160 --samples 64 \
  --target -150,-120,18 --cam -960,-958,26 --lens 32 --preset sunny --look golden --fog 0.25 --atmo 0.0009 \
  --atmo-size 1800 --area 0.8 --lamp-lights 150 --out renders/8k/market_st_eevee_4k.png 2>&1 | grep -E "RENDER|Traceback"
W=web/renders
sips -s format jpeg -s formatOptions 82 -Z 3200 renders/8k/market_st_cycles_8k.png --out $W/market_cycles.jpg >/dev/null
sips -s format jpeg -s formatOptions 82 -Z 3200 renders/8k/market_st_eevee_4k.png --out $W/market_eevee.jpg >/dev/null
sips -s format jpeg -s formatOptions 82 -Z 3200 renders/8k/sf_city_aerial_8k.png --out $W/city_aerial_eevee.jpg >/dev/null
sips -s format jpeg -s formatOptions 82 -Z 3200 renders/8k/sf_city_topdown_8k.png --out $W/city_topdown_eevee.jpg >/dev/null
ls -la $W
