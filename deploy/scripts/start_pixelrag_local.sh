#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f memory_stack.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source memory_stack.env
  set +a
fi

python tools/build_tiles.py

if command -v pixelrag >/dev/null 2>&1; then
  pixelrag index build
  pixelrag serve --index-dir "${PIXELRAG_INDEX_DIR:-./my_index}" --port "${PIXELRAG_SERVE_PORT:-30001}"
else
  echo "pixelrag CLI not found; tiles built. Install PixelRAG to index and serve." >&2
  exit 1
fi
