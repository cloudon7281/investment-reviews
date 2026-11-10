#!/usr/bin/env bash
set -euo pipefail

: "${CONFIG_PATH:?CONFIG_PATH must be set}"

metrics_dir="${METRICS_TEXTFILE_DIR:-/textfile}"

# Write a node_exporter textfile atomically (SDI, "Metrics and health" — jobs-only metrics). The
# temp name is deliberately NOT derived from the destination: a *.prom glob must never see a
# partial file, and a collector racing the rename must not find two candidates (kicker#19).
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

# The activity snapshot for investment-analysis: this service's trade history and benchmarks, published as
# interfaces E and F into the investment-reviews-exports store (README.md, "Activity Snapshot";
# investment-analysis#1, decision D13). It runs after the spreadsheet update, whatever that update's result,
# and its own failure never changes this job's exit status: it has its own metric family instead, whose
# cadence lets the estate's silent-producer detection report an export that stops.
export_rc=0
base_dir="$(python -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["portfolio"]["base_dir"])' "$CONFIG_PATH")" \
  && python -m portfolio --mode portfolio-activity-snapshot --base-dir "$base_dir" --export-dir "${EXPORT_DIR:-/exports}" \
  || export_rc=$?
echo "[$(date -Is)] finished the activity snapshot (exit=${export_rc})"

if [ -d "$metrics_dir" ]; then
  export_file="${metrics_dir}/investment-reviews-export.prom"
  # The last success is carried over a failed night, so a failure does not read as never having worked.
  last_ok="$(sed -n 's/^investment_reviews_export_last_success_timestamp_seconds //p' "$export_file" 2>/dev/null || true)"
  if [ "$export_rc" -eq 0 ]; then ok=1; last_ok=$(date +%s); else ok=0; fi
  write_metric_file "$export_file" \
    "# HELP investment_reviews_export_ok Whether the last activity snapshot published both documents (1) or not (0)." \
    "# TYPE investment_reviews_export_ok gauge" \
    "investment_reviews_export_ok ${ok}" \
    "# HELP investment_reviews_export_last_success_timestamp_seconds Unix timestamp (UTC) of the last activity snapshot that published both documents." \
    "# TYPE investment_reviews_export_last_success_timestamp_seconds gauge" \
    "investment_reviews_export_last_success_timestamp_seconds ${last_ok:-0}"
fi

# 2 means the portfolio update worked; do not fail the kicker job for a mail problem.
if [ "$rc" -eq 2 ]; then
  exit 0
fi
exit "$rc"
