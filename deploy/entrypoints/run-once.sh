#!/usr/bin/env bash
set -euo pipefail

: "${CONFIG_PATH:?CONFIG_PATH must be set}"

metrics_dir="${METRICS_TEXTFILE_DIR:-/textfile}"

# Write a node_exporter textfile atomically (SDI §11 jobs-only metrics). The temp name is
# deliberately NOT derived from the destination: a *.prom glob must never see a partial
# file, and a collector racing the rename must not find two candidates (kicker#19).
write_metric_file() {
  local dest="$1"; shift
  local tmp
  tmp="$(mktemp "${metrics_dir}/.textfile.XXXXXX")"
  printf '%s\n' "$@" > "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$dest"
  echo "[$(date -Is)] wrote ${dest}"
}

echo "[$(date -Is)] starting investment-reviews run"

# `set -e` would abort the script on a non-zero exit before rc could ever be inspected —
# which is exactly why the previous `rc=$?` was dead code that could only ever read 0, and
# why a failed run silently skipped the metric write instead of reporting anything.
rc=0
python /app/update_google_sheet.py --config "$CONFIG_PATH" || rc=$?

echo "[$(date -Is)] finished investment-reviews run (exit=${rc})"

# Exit-code contract from update_google_sheet.main():
#   0  spreadsheet updated, alert channel healthy
#   2  spreadsheet updated, alert email undeliverable
#   3  notes could not be read: spreadsheet left alone, the report was emailed instead
#   *  the update itself failed
# 0 and 2 both mean the nightly pipeline succeeded, so both refresh the health metric.
# 3 does not: no report was produced, so the freshness metric is deliberately left to go
# stale until the notes are fixed, even though an email did go out
# (investment-reviews#38).
if [ -d "$metrics_dir" ] && { [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; }; then
  ts=$(date +%s)

  write_metric_file "${metrics_dir}/investment-reviews.prom" \
    "# HELP investment_reviews_last_success_timestamp_seconds Unix timestamp (UTC) of last successful investment-reviews update." \
    "# TYPE investment_reviews_last_success_timestamp_seconds gauge" \
    "investment_reviews_last_success_timestamp_seconds ${ts}"

  # Alert-channel health, tracked independently of the pipeline, so "the email is broken"
  # cannot hide behind a green pipeline. No `host` label: node_exporter already applies one
  # and a second collides into exported_host.
  if [ "$rc" -eq 2 ]; then ok=0; else ok=1; fi
  write_metric_file "${metrics_dir}/investment-reviews-alert.prom" \
    "# HELP investment_reviews_alert_delivery_ok Whether the last nightly run's alert email channel was healthy (1 ok, 0 undeliverable)." \
    "# TYPE investment_reviews_alert_delivery_ok gauge" \
    "investment_reviews_alert_delivery_ok ${ok}"
fi

# 2 means the portfolio update worked; do not fail the kicker job for a mail problem.
if [ "$rc" -eq 2 ]; then
  exit 0
fi
exit "$rc"
