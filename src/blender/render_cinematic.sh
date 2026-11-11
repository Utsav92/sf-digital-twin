#!/usr/bin/env bash
# Cinematic renders of the pilot district (Financial District / SoMa / North Beach, 16 tiles with street + facade detail).
#   ./src/blender/render_cinematic.sh preview            EEVEE 1080p, 64 samples (seconds)
#   ./src/blender/render_cinematic.sh final              Cycles path tracing, Metal GPU, 3840x2160, 128 samples, 8K textures (~4 min)
#   ./src/blender/render_cinematic.sh final 256          same at 256 samples
#   ./src/blender/render_cinematic.sh anim drone|drive [seconds] [eevee|cycles]   PNG sequence + mp4 (720p EEVEE by default)
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
CAM="--target -150,-120,18 --cam -960,-958,26 --lens 32"
LOOK="--preset golden_hour --look golden --fog 0.25 --atmo 0.0009 --atmo-size 1800 --area 0.8 --lamp-lights 150"
R() { "$B" -b --factory-startup -P src/blender/render_city.py -- --pilot --lod lod1 "$@"; }
mkdir -p renders/cinematic
case "$1" in
  preview) R --res 1920x1080 --samples 64 $CAM $LOOK --out renders/cinematic/preview_eevee.png ;;
  final)   SF_TEX_RES=8k R --engine CYCLES --res 3840x2160 --samples ${2:-128} $CAM $LOOK \
             --out renders/cinematic/market_st_cycles_4k.png ;;
  anim)    KIND=${2:-drone}; SEC=${3:-6}; ENG=${4:-eevee}
           if [[ $ENG == cycles ]]; then
             SF_TEX_RES=8k R --engine CYCLES --res 3840x2160 --samples 128 $LOOK --anim $KIND --seconds $SEC \
               --out renders/cinematic/${KIND}_cycles.png
           else
             R --res 1280x720 --samples 48 $LOOK --anim $KIND --seconds $SEC --out renders/cinematic/$KIND.png
           fi
           "$B" -b --factory-startup -P src/blender/encode_video.py -- renders/cinematic/${KIND}$([[ $ENG == cycles ]] && echo _cycles) \
             renders/cinematic/${KIND}$([[ $ENG == cycles ]] && echo _cycles).mp4 24 ;;
  *) echo "usage: $0 preview|final [samples]|anim drone|drive [seconds] [eevee|cycles]"; exit 2 ;;
esac
