#!/usr/bin/env bash
# Serve the viewer locally (browsers block fetch() from file://).   ./web/serve.sh [port]
cd "$(dirname "$0")"
PORT=${1:-8000}
echo "Open http://localhost:$PORT/"
python3 -m http.server "$PORT"
