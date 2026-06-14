#!/usr/bin/env bash
set -euo pipefail

: "${CONFIG_PATH:?CONFIG_PATH must be set}"

echo "[$(date -Is)] starting investment-reviews run"
python /app/update_google_sheet.py --config "$CONFIG_PATH"
rc=$?
echo "[$(date -Is)] finished investment-reviews run (exit=$rc)"

# On success, emit a node_exporter textfile metric (SDI §11 jobs-only metrics).
# The metrics dir is monitoring's metrics-textfile shared store (SDI §12), mounted
# rw by registration. Skip silently if it isn't mounted (e.g. a local run).
metrics_dir="${METRICS_TEXTFILE_DIR:-/textfile}"
if [ "$rc" -eq 0 ] && [ -d "$metrics_dir" ]; then
  ts=$(date +%s)
  tmp="$(mktemp "${metrics_dir}/.investment-reviews.prom.XXXXXX")"
  {
    echo "# HELP investment_reviews_last_success_timestamp_seconds Unix timestamp (UTC) of last successful investment-reviews update."
    echo "# TYPE investment_reviews_last_success_timestamp_seconds gauge"
    echo "investment_reviews_last_success_timestamp_seconds ${ts}"
  } > "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "${metrics_dir}/investment-reviews.prom"
  echo "[$(date -Is)] wrote ${metrics_dir}/investment-reviews.prom (ts=${ts})"
fi

exit $rc
