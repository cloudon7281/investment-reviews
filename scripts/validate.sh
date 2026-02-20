#!/usr/bin/env bash
set -euo pipefail

# SDI v1: validate that the scheduler container is up.

proj=${COMPOSE_PROJECT_NAME:-investment-reviews}

# Using docker compose by project name; no need for compose file path.
if ! docker ps --format '{{.Names}}' | grep -q '^investment-reviews-scheduler$'; then
  echo "ERROR: investment-reviews-scheduler container not running" >&2
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | sed -n '1,200p' >&2
  exit 1
fi

echo "OK: investment-reviews-scheduler is running"
