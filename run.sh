#!/usr/bin/env bash
# Production launcher (Rust-only)

set -euo pipefail

APP_DIR="/opt/heelonvault"
BIN_PATH="${APP_DIR}/rust/target/release/heelonvault-rust"
PROD_DB_DIR="/var/lib/heelonvault-rust-shared"
PROD_DB_PATH="${PROD_DB_DIR}/heelonvault.db"

if [[ ! -x "$BIN_PATH" ]]; then
  echo "[ERROR] Rust binary not found: $BIN_PATH"
  echo "Build it with: cd ${APP_DIR}/rust && cargo build --release"
  exit 1
fi

mkdir -p "$PROD_DB_DIR"
export HEELONVAULT_DB_PATH="$PROD_DB_PATH"

exec "$BIN_PATH"
