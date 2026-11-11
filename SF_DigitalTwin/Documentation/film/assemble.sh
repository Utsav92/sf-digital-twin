#!/bin/bash
# usage: assemble.sh <frames_dir> <out.mp4>   frames named sf.NNNN.png at 30 fps
set -e; D=$(cd "$(dirname "$0")" && pwd); F=$1; OUT=$2
say -v Daniel -r 188 -o /tmp/sf_vo.aiff -f "$D/narration.txt"
DUR=$(ffmpeg -i /tmp/sf_vo.aiff 2>&1 | awk -F'[:, ]+' '/Duration/{print $3*3600+$4*60+$5}')
TEMPO=$(python3 -c "print(max(1.0, round($DUR/48.5, 3)))")
echo "voice ${DUR}s tempo ${TEMPO}"
ffmpeg -y -framerate 30 -pattern_type glob -i "$F/sf*.png" -i /tmp/sf_vo.aiff \
  -vf "ass=$D/captions.ass,fade=t=in:st=0:d=0.5,fade=t=out:st=50:d=1" \
  -af "atempo=$TEMPO,apad=pad_dur=3,afade=t=out:st=49.5:d=1.5" \
  -c:v libx264 -crf 14 -preset slow -pix_fmt yuv420p -c:a aac -b:a 192k -t 51 -movflags +faststart "$OUT"
