#!/usr/bin/env bash
# Render a saved .flp to MP3 with FL's command-line renderer (Song mode).
# FL must be closed first: a running instance ignores the render args.
# Usage: scripts/render_mp3.sh path/to/project.flp
set -euo pipefail

case "$1" in
  /*) flp="$1" ;;  # absolute paths pass through untouched (FL may see folders this shell can't)
  *) flp="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")" ;;
esac
app="${FL_APP:-$(ls -d /Applications/FL\ Studio*.app | sort | tail -1)}"

if pgrep -x OsxFL >/dev/null; then
  echo "FL Studio is running — save, quit it, then re-run." >&2
  exit 1
fi

echo "Rendering $flp with $(basename "$app")…"
# -F"<flp>" opens and quits without rendering on macOS FL 2026; pass the project positionally.
open -W -n -a "$app" --args -R -Emp3 "$flp"

mp3="${flp%.flp}.mp3"
if [[ -f "$mp3" ]]; then
  ls -la "$mp3"
else
  echo "No $mp3 found — check FL's default render folder, or export manually (File → Export → MP3)." >&2
  exit 1
fi
