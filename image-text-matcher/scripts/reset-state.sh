#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_BASE_DIR="${PROJECT_DIR}/data/images"
PROCESSED_IMAGE_DIR="${PROJECT_DIR}/data/processed"
FORCE=0

usage() {
  cat <<EOF
Usage: ./scripts/reset-state.sh [--force]

Stops the Docker Compose stack, removes Compose volumes, and clears stored image
files while preserving tracked .gitkeep placeholders.
EOF
}

log() {
  printf '%s\n' "$1"
}

while (($# > 0)); do
  case "$1" in
    --force | --yes)
      FORCE=1
      shift
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    *)
      log "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  log "Docker is not installed or not on PATH."
  exit 1
fi

if ((FORCE == 0)); then
  log "This will permanently remove Docker database volumes and stored files for ${PROJECT_DIR}:"
  log "  images: ${IMAGE_BASE_DIR}"
  log "  processed images: ${PROCESSED_IMAGE_DIR}"
  printf 'Type RESET to continue: '

  if [[ ! -t 0 ]]; then
    log ""
    log "Refusing to prompt without a TTY. Re-run with --force."
    exit 1
  fi

  read -r confirmation
  if [[ "${confirmation}" != "RESET" ]]; then
    log "Reset cancelled."
    exit 1
  fi
fi

docker compose -f "${PROJECT_DIR}/docker-compose.yml" down -v

PROJECT_DIR="${PROJECT_DIR}" python3 - <<'PY'
from __future__ import annotations

import os
from pathlib import Path


project_dir = Path(os.environ["PROJECT_DIR"]).resolve()
image_dirs = [
    project_dir / "data" / "images",
    project_dir / "data" / "processed",
]


def clear_directory(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    preserved = {path.resolve() for path in root.rglob(".gitkeep")}

    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        resolved = path.resolve()
        if resolved in preserved:
            continue

        if path.is_symlink() or path.is_file():
            path.unlink()
            continue

        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


for directory in image_dirs:
    clear_directory(directory)
    print(f"Cleared directory: {directory}")
PY

log "Reset complete. Start fresh with: docker compose up --build"
