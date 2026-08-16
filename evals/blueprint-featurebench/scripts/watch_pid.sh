#!/usr/bin/env bash
# Wait for a specific PID to exit. Avoids the pgrep self-match trap: a monitor
# whose own command line contains the pattern it greps for will match itself
# and report "still running" forever.
#   bash scripts/watch_pid.sh <pid> [poll_seconds]
PID="${1:?usage: watch_pid.sh <pid> [poll_seconds]}"
POLL="${2:-30}"
while kill -0 "$PID" 2>/dev/null; do sleep "$POLL"; done
echo "PID_${PID}_EXITED"
