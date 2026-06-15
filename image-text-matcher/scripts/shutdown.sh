#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

log() {
  printf '%s\n' "$1"
}

if ! command -v docker >/dev/null 2>&1; then
  log "Docker is not installed or not on PATH."
  exit 1
fi

log "Stopping Docker Compose services for ${PROJECT_DIR}."
docker compose -f "${PROJECT_DIR}/docker-compose.yml" down
log "Shutdown complete."
