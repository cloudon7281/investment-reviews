#!/usr/bin/env bash
set -euo pipefail

: "${CONFIG_PATH:?CONFIG_PATH must be set}"

mkdir -p /data/logs/daily_updates

logfile=/data/logs/daily_updates/cron.log

echo "[$(date -Is)] starting investment-reviews run" | tee -a "$logfile"
python /app/update_google_sheet.py --config "$CONFIG_PATH" >>"$logfile" 2>&1
rc=$?
echo "[$(date -Is)] finished investment-reviews run (exit=$rc)" | tee -a "$logfile"
exit $rc
