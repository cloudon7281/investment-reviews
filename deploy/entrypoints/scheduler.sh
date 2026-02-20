#!/usr/bin/env bash
set -euo pipefail

: "${CONFIG_PATH:?CONFIG_PATH must be set}"
: "${SCHEDULE_LOCAL_TIME:?SCHEDULE_LOCAL_TIME must be set (e.g. 22:05)}"
: "${TZ:?TZ must be set (e.g. Europe/London)}"

mkdir -p /data/logs/daily_updates

logfile=/data/logs/daily_updates/cron.log

tz="$TZ"
time_local="$SCHEDULE_LOCAL_TIME"

run_once() {
  echo "[$(date -Is)] starting scheduled investment-reviews run" | tee -a "$logfile"
  python /app/update_google_sheet.py --config "$CONFIG_PATH" >>"$logfile" 2>&1
  rc=$?
  echo "[$(date -Is)] finished scheduled investment-reviews run (exit=$rc)" | tee -a "$logfile"
  return $rc
}

while true; do
  now=$(date +%s)

  # Next target time in the configured timezone.
  today_target=$(TZ="$tz" date -d "today ${time_local}" +%s)
  if [ "$now" -lt "$today_target" ]; then
    target=$today_target
  else
    target=$(TZ="$tz" date -d "tomorrow ${time_local}" +%s)
  fi

  sleep_for=$(( target - now ))
  if [ "$sleep_for" -lt 0 ]; then
    sleep_for=60
  fi

  echo "[$(date -Is)] sleeping ${sleep_for}s until next scheduled run (${tz} ${time_local})" | tee -a "$logfile"
  sleep "$sleep_for"

  run_once || true

  # Avoid tight loop if clock jumps.
  sleep 60
done
