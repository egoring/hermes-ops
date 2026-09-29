#!/bin/bash
# Verify that SOUL.md edits are actually live on every Hermes profile.
#
# A gateway restart can report success and still leave the old process running
# (drain waits on in-flight work), so compare process start time against file
# mtime rather than trusting the restart command's output.
#
# Topologies:
#   multiplexed  one host gateway serves every profile; its PID is in
#                ~/.hermes/gateway_state.json and "served_profiles" lists them
#   per-profile  each profile runs its own gateway (matched by "profiles/<p>")
#
# Usage: verify_fleet.sh [profile ...]        (default: every dir under profiles/)

set -u
HOME_DIR="$HOME/.hermes"
PROFILES_ROOT="$HOME_DIR/profiles"
STATE="$HOME_DIR/gateway_state.json"

# Host gateway PID + served profiles (empty when not multiplexed / no state file)
HOST_PID=""
SERVED=""
if [ -f "$STATE" ]; then
  read -r HOST_PID SERVED < <(python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get("pid") or "", ",".join(d.get("served_profiles") or []))' "$STATE" 2>/dev/null)
  # Ignore a stale PID from a dead process
  if [ -n "$HOST_PID" ] && ! kill -0 "$HOST_PID" 2>/dev/null; then HOST_PID=""; SERVED=""; fi
fi

if [ "$#" -gt 0 ]; then
  PROFILES=("$@")
else
  PROFILES=()
  for d in "$PROFILES_ROOT"/*/; do
    [ -d "$d" ] && PROFILES+=("$(basename "$d")")
  done
fi

for p in "${PROFILES[@]}"; do
  soul="$PROFILES_ROOT/$p/SOUL.md"
  [ -f "$soul" ] || { printf '%-14s no SOUL.md\n' "$p"; continue; }

  # Prefer the multiplexing host when it serves this profile
  if [ -n "$HOST_PID" ] && [[ ",$SERVED," == *",$p,"* ]]; then
    pid="$HOST_PID"; via="host"
  else
    pid=$(pgrep -f "profiles/$p" | head -1); via="own"
  fi
  if [ -z "$pid" ]; then
    printf '%-14s NOT SERVED\n' "$p"
    continue
  fi

  started_raw=$(ps -o lstart= -p "$pid" 2>/dev/null)
  started=$(date -jf "%a %b %e %T %Y" "$started_raw" +%s 2>/dev/null)
  edited=$(stat -f %m "$soul" 2>/dev/null)

  if [ -n "$started" ] && [ -n "$edited" ] && [ "$started" -gt "$edited" ]; then
    printf '%-14s LIVE      pid=%s (%s)\n' "$p" "$pid" "$via"
  else
    printf '%-14s STALE     pid=%s (%s)  restart needed: SOUL.md newer than process\n' "$p" "$pid" "$via"
  fi
done
