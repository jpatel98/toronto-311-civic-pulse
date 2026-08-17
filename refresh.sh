#!/bin/bash
# 311 Civic Pulse - standalone nightly refresh (no Hermes involvement).
# Scheduled by systemd user timer (toronto311-refresh.timer).
# Logs to logs/refresh.log; on failure also notifies a Discord webhook (if configured).
#
# History: netlify-cli run inside the project dir with a relative --dir was
# observed clobbering dist/ (its .netlify local state + deploy cache) -> deploys
# silently shipped stale data ("0 files"). Fix: build fresh, deploy from a
# clean cwd with the explicit site ID and an absolute --dir, then self-check.
set -uo pipefail

PROJ="/home/jigar/dev/jobs/toronto311"
SITE_ID="1b58644f-22d9-4a78-8ef8-c6993f04488f"
LOG_DIR="$PROJ/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh.log"
STAMP=$(date '+%Y-%m-%d %H:%M:%S')

# systemd user units do not inherit the login shell PATH; node lives under fnm
export PATH="/home/jigar/.local/share/fnm/node-versions/v24.15.0/installation/bin:$PATH"
export HOME="/home/jigar"

fail() {
  echo "[$STAMP] FAILURE: $1" >> "$LOG"
  tail -5 "$LOG" | "$PROJ/notify.sh" 2>/dev/null
  exit 1
}

echo "[$STAMP] refresh start" >> "$LOG"

python3 "$PROJ/pipeline.py" >> "$LOG" 2>&1 || fail "pipeline"

cp "$PROJ/data/out/civic-pulse.json" "$PROJ/site/public/data/civic-pulse.json"

cd "$PROJ/site" || fail "cd site"
npm run build >> "$LOG" 2>&1 || fail "build"

# deploy from a clean cwd with explicit site id + absolute dir (no local state)
(cd /tmp && npx -y netlify-cli deploy --prod --dir "$PROJ/site/dist" --site "$SITE_ID") >> "$LOG" 2>&1 || fail "netlify deploy"

# self-check: deployed bundle must be the freshly generated one
cmp -s "$PROJ/data/out/civic-pulse.json" "$PROJ/site/dist/data/civic-pulse.json" || fail "dist JSON mismatch after deploy"

echo "[$STAMP] ok" >> "$LOG"
exit 0
