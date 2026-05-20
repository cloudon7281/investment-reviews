#!/usr/bin/env bash
set -euo pipefail

: "${CONFIG_PATH:?CONFIG_PATH must be set}"

echo "[$(date -Is)] starting investment-reviews run"
python /app/update_google_sheet.py --config "$CONFIG_PATH"
rc=$?
echo "[$(date -Is)] finished investment-reviews run (exit=$rc)"
exit $rc
