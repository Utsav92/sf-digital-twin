#!/usr/bin/env bash
# 3-minute split-screen film (car chase cam | architecture drone), 24 fps = 4320 frames per view.
# EEVEE, 960x1080 per view, 64 samples, 4K PBR textures, volumetric fog, area lights, motion blur.
# Resumable: existing frames are skipped; each view retries up to 15 times if Blender crashes.
#   ./src/cine/render_film.sh            render both views in parallel, then compose renders/film/sf_twin_film.mp4
#   ./src/cine/render_film.sh compose    compose whatever frames exist (preview the cut so far)
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
N=4320
COMMON=(--pilot --lod lod1 --res 960x1080 --samples 64 --preset sunny --look golden --fog 0.3
        --atmo 0.0009 --atmo-size 2400 --area 0.6 --lamp-lights 150 --mblur 0.35 --seconds 180)
mkdir -p renders/film
view() {  # view <car|drone>
  local k=$1 n=0
  while [ "$(ls renders/film/$k 2>/dev/null | grep -c '^frame_')" -lt $N ] && [ $n -lt 15 ]; do
    SF_TEX_RES=4k $B -b --factory-startup -P src/blender/render_city.py -- "${COMMON[@]}" --anim cine_$k \
      --frames 1-$N --out renders/film/$k.png >> logs/film_$k.log 2>&1
    n=$((n + 1))
  done
}
compose() { $B -b --factory-startup -P src/cine/compose_film.py -- renders/film/car renders/film/drone renders/film/sf_twin_film.mp4 24 2>&1 | grep -E "COMPOSED|Traceback"; }
if [ "$1" = "compose" ]; then compose; exit 0; fi
while pgrep -f render_8k.sh > /dev/null; do sleep 30; done   # let the 8K stills finish first (GPU)
view car & view drone & wait
compose
