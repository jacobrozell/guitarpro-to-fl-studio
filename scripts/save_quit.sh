#!/usr/bin/env bash
# Save the open FL project and quit, so render_mp3.sh can run.
# FL has no save API. This sends Cmd+S, then Cmd+Q, to the OsxFL process
# through System Events. The sender needs Accessibility permission.
#
# Cmd+S overwrites the project FL already has open. It does not Save As.
# Pass the .flp path to confirm its modification time changed before quitting.
#
# Usage: scripts/save_quit.sh [path/to/project.flp]
set -euo pipefail

flp="${1:-}"
pid="$(pgrep -x OsxFL)" || { echo "FL Studio is not running." >&2; exit 1; }

mtime() { stat -f %m "$1"; }

before=""
if [[ -n "$flp" ]]; then
  [[ -f "$flp" ]] || { echo "No such file: $flp" >&2; exit 1; }
  before="$(mtime "$flp")"
fi

osascript -e "tell application \"System Events\" to tell (first process whose unix id is $pid)
set frontmost to true
delay 0.4
keystroke \"s\" using command down
end tell"

sleep 2
if [[ -n "$before" ]]; then
  after="$(mtime "$flp")"
  if [[ "$after" == "$before" ]]; then
    echo "Save did not change $flp. Grant Accessibility to the app running this script." >&2
    exit 1
  fi
  echo "saved $flp"
fi

osascript -e "tell application \"System Events\" to tell (first process whose unix id is $pid)
set frontmost to true
delay 0.2
keystroke \"q\" using command down
end tell"

for _ in $(seq 1 20); do
  sleep 1
  if ! pgrep -x OsxFL >/dev/null; then
    echo "closed"
    exit 0
  fi
done

echo "FL is still running. A dialog may be waiting." >&2
exit 1
