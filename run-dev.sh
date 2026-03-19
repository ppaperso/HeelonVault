#!/usr/bin/env bash
# Development launcher (Rust-only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_DB_DIR="${SCRIPT_DIR}/data"
DEV_DB_PATH="${DEV_DB_DIR}/heelonvault-rust-dev.db"
DEV_LOG_DIR="${SCRIPT_DIR}/logs"

if [[ ! -f "${SCRIPT_DIR}/Cargo.toml" ]]; then
  echo "[ERROR] Cargo.toml not found at repository root: ${SCRIPT_DIR}/Cargo.toml"
  exit 1
fi

mkdir -p "$DEV_DB_DIR"
export HEELONVAULT_DB_PATH="$DEV_DB_PATH"
export HEELONVAULT_LOG_DIR="$DEV_LOG_DIR"
export HEELONVAULT_LOG_LEVEL="debug"

cd "$SCRIPT_DIR"
exec cargo run
