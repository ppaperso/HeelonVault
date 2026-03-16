#!/usr/bin/env bash
# Rust-only updater for HeelonVault

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ERROR] Run with sudo."
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/heelonvault"
DATA_DIR="/var/lib/heelonvault-rust-shared"
BACKUP_DIR="/var/backups/heelonvault"
TS="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="${BACKUP_DIR}/heelonvault_${TS}.tar.gz"

if [[ ! -d "$INSTALL_DIR" ]]; then
  echo "[ERROR] Install directory not found: $INSTALL_DIR"
  exit 1
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "[ERROR] cargo not found. Install Rust toolchain first."
  exit 1
fi

mkdir -p "$BACKUP_DIR"
echo "[INFO] Creating backup: $ARCHIVE"
tar -czf "$ARCHIVE" -C / opt/heelonvault var/lib/heelonvault-rust-shared

if [[ ! -s "$ARCHIVE" ]]; then
  echo "[ERROR] Backup archive is missing or empty: $ARCHIVE"
  exit 1
fi

echo "[INFO] Verifying backup archive"
tar -tzf "$ARCHIVE" >/dev/null

echo "[INFO] Updating files from source"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.vscode/' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude 'target/' \
  "$SOURCE_DIR/" "$INSTALL_DIR/"

chmod +x "$INSTALL_DIR/run.sh" "$INSTALL_DIR/run-dev.sh"

echo "[INFO] Building release binary"
cd "$INSTALL_DIR/rust"
cargo build --release

mkdir -p "$DATA_DIR"
chown root:root "$DATA_DIR"
chmod 750 "$DATA_DIR"

echo "[OK] Update complete"
