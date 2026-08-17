#!/bin/bash
# Reads a Discord webhook URL from .env.discord (gitignored) and posts stdin
# as a message. Silent if no webhook is configured.
WEBHOOK=$(grep -E '^WEBHOOK_URL=' "$(dirname "$0")/.env.discord" 2>/dev/null | head -1 | cut -d= -f2-)
if [ -n "$WEBHOOK" ]; then
  PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'content': sys.stdin.read()[:1800]}))")
  curl -s -X POST "$WEBHOOK" -H "Content-Type: application/json" -d "$PAYLOAD" > /dev/null 2>&1
fi
exit 0
