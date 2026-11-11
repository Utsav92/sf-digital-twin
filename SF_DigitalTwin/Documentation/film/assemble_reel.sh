#!/bin/bash
# usage: assemble_reel.sh <frames_dir> <out.mp4>   1080x1920 portrait, 30 fps, ~24 s
set -e; D=$(cd "$(dirname "$0")" && pwd); F=$1; OUT=$2
say -v Daniel -r 185 -o /tmp/sf_reel_vo.aiff -f "$D/narration_reel.txt"
DUR=$(ffmpeg -i /tmp/sf_reel_vo.aiff 2>&1 | awk -F'[:, ]+' '/Duration/{print $3*3600+$4*60+$5}')
TEMPO=$(python3 -c "print(max(1.0, round($DUR/22.5, 3)))")
echo "voice ${DUR}s tempo ${TEMPO}"
ffmpeg -y -framerate 30 -pattern_type glob -i "$F/reel*.png" -i /tmp/sf_reel_vo.aiff \
  -vf "scale=1080:1920,ass=$D/captions_reel.ass,fade=t=in:st=0:d=0.3,fade=t=out:st=23.4:d=0.6" \
  -af "atempo=$TEMPO,apad=pad_dur=2,afade=t=out:st=23:d=1" \
  -c:v libx264 -crf 16 -preset slow -pix_fmt yuv420p -c:a aac -b:a 192k -t 24 -movflags +faststart "$OUT"
