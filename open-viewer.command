#!/bin/sh
# macOS / Linux: double-click (macOS) or run ./open-viewer.command
cd "$(dirname "$0")"
command -v python3 >/dev/null && exec python3 scripts/viewer.py || exec python scripts/viewer.py
