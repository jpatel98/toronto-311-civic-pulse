#!/bin/bash
# 311 Civic Pulse - standalone nightly refresh (no Hermes involvement).
# Runs the open-data pipeline, regenerates AI briefs, redeploys Netlify.
# Scheduled by systemd user timer (toronto311-refresh.timer).
# Logs to logs/refresh.log; on failure also notifies a Discord webhook (if configured).
set -o pipefail

PROJ="/home/jigar/dev/jobs/toronto311"
LOG_DIR="$PROJ/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh.log"
STAMP=$(date '+%Y-%m-%d %H:%M:%S')

# systemd user units do not inherit the login shell PATH; node lives under fnm
export PATH="/home/jigar/.local/share/fnm/node-versions/v24.15.0/installation/bin:$PATH"
export HOME="/home/jigar"

echo "[$STAMP] refresh start" >> "$LOG"

if ! python3 "$PROJ/pipeline.py" >> "$LOG" 2>&1; then
  echo "[$STAMP] FAILURE: pipeline" >> "$LOG"
  tail -5 "$LOG" | "$PROJ/notify.sh" 2>/dev/null
  exit 1
fi

cp "$PROJ/data/out/civic-pulse.json" "$PROJ/site/dist/data/civic-pulse.json"

cd "$PROJ/site" || exit 1
if ! npx -y netlify-cli deploy --prod --dir dist >> "$LOG" 2>&1; then
  echo "[$STAMP] FAILURE: netlify deploy" >> "$LOG"
  tail -5 "$LOG" | "$PROJ/notify.sh" 2>/dev/null
  exit 1
fi

echo "[$STAMP] ok" >> "$LOG"
exit 0
