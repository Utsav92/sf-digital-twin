#!/usr/bin/env bash
# Add canyon-fill views to the splat capture (skips views already captured), rebuild full + lite splats.
# Pauses the film render meanwhile (SIGSTOP) and always resumes it.
cd "$(dirname "$0")/../.."
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
resume() { for p in $(pgrep -f "render_city.py.*cine_"); do kill -CONT $p; done; }
trap resume EXIT
for p in $(pgrep -f "render_city.py.*cine_"); do kill -STOP $p; done
$B -b --factory-startup -P src/blender/render_city.py -- --pilot --lod lod1 --no-ocean --res 1280x720 --samples 32 \
  --preset sunny --splat-capture data/splat --splat-skip-existing --out renders/cinematic/unused.png 2>&1 | grep -E "SPLAT|Traceback"
.venv/bin/python src/cine/build_splat.py data/splat out/splat/sf_twin_pilot 0.9 0.3 0.45
.venv/bin/python src/cine/build_splat.py data/splat out/splat/sf_twin_pilot_lite 1.6 0.5 0.8
