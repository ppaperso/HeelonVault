#!/usr/bin/env bash
# Development launcher (Rust-only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_DIR="${SCRIPT_DIR}/rust"
DEV_DB_DIR="${SCRIPT_DIR}/data"
DEV_DB_PATH="${DEV_DB_DIR}/heelonvault-rust-dev.db"

if [[ ! -d "$RUST_DIR" ]]; then
  echo "[ERROR] Rust directory not found: $RUST_DIR"
  exit 1
fi

mkdir -p "$DEV_DB_DIR"
export HEELONVAULT_DB_PATH="$DEV_DB_PATH"

cd "$RUST_DIR"
exec cargo run
