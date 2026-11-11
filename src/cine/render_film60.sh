#!/usr/bin/env bash
# 60 s / 1800 frames / 1080p30 audio-reactive film from the existing Blender city scene.
#   TRACK=/path/song.mp3 ./src/cine/render_film60.sh audio     conform + analyse (TRACK optional: placeholder is synthesised)
#   ./src/cine/render_film60.sh render [a-b]                   resumable render of frames a-b (default 1-1800)
#   ./src/cine/render_film60.sh encode                         mux + verify -> renders/film60/SF_Musical_Digital_Twin_60s.mp4
# Options via env: TRACK_START (s into the source), FADE_OUT (s, default 3), SAMPLES (default 64), RES (default 1920x1080)
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}; PY=.venv/bin/python
D=data/film60; mkdir -p $D renders/film60
audio() {
  if [ -n "$TRACK" ]; then $PY pipelines/audio/prepare_audio.py "$TRACK" $D/track_60s.wav --start "${TRACK_START:-0}" --fade-out "${FADE_OUT:-3}"
  elif [ ! -f $D/track_60s.wav ]; then
    $PY pipelines/audio/make_placeholder_track.py $D/placeholder_raw.wav && $PY pipelines/audio/prepare_audio.py $D/placeholder_raw.wav $D/track_60s.wav
  fi
  $PY pipelines/audio/analyze_audio.py $D/track_60s.wav $D/features.json
}
render() {
  local range=${1:-1-1800} n=0 last=${1##*-}; last=${last:-1800}
  while [ $n -lt 15 ]; do
    SF_TEX_RES=${TEX:-8k} $B -b --factory-startup -P src/blender/render_city.py -- --pilot --lod lod1 --res ${RES:-1920x1080} \
      --samples ${SAMPLES:-128} --preset golden_hour --look golden --fog 0.3 --atmo 0.0009 --atmo-size 2400 --area 0.6 \
      --lamp-lights 150 --mblur 0.35 --seconds 180 --anim cine_both --film60 --frames $range --out renders/film60/frames.png \
      >> logs/film60.log 2>&1
    a=${range%-*}; done_ct=$(ls renders/film60/frames 2>/dev/null | grep -c '^frame_')
    [ $(( $(seq $a $last | while read i; do [ -f renders/film60/frames/frame_$(printf %04d $i).png ] || echo x; done | wc -l) )) -eq 0 ] && break
    n=$((n + 1))
  done
}
case "$1" in
  audio) audio ;;
  render) [ -f $D/features.json ] || audio; render "$2" ;;
  encode) $PY pipelines/video/encode_60s.py && $PY pipelines/video/verify_video.py ;;
  *) echo "usage: $0 audio|render [a-b]|encode"; exit 2 ;;
esac
