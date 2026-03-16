#!/usr/bin/env bash
# Rust-only installer for HeelonVault

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ERROR] Run with sudo."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/heelonvault"
DATA_DIR="/var/lib/heelonvault-rust-shared"
DESKTOP_FILE="heelonvault.desktop"
SYSTEM_APPS_DIR="/usr/share/applications"

if ! command -v cargo >/dev/null 2>&1; then
  echo "[ERROR] cargo not found. Install Rust toolchain first."
  exit 1
fi

echo "[INFO] Deploying to ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.vscode/' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude 'target/' \
  "$SCRIPT_DIR/" "$INSTALL_DIR/"

chown -R root:root "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/run.sh" "$INSTALL_DIR/run-dev.sh"

echo "[INFO] Building release binary"
cd "$INSTALL_DIR/rust"
cargo build --release

mkdir -p "$DATA_DIR"
chown root:root "$DATA_DIR"
chmod 750 "$DATA_DIR"

if [[ -f "$INSTALL_DIR/$DESKTOP_FILE" ]]; then
  cp "$INSTALL_DIR/$DESKTOP_FILE" "$SYSTEM_APPS_DIR/"
  sed -i "s|^Exec=.*|Exec=$INSTALL_DIR/run.sh|" "$SYSTEM_APPS_DIR/$DESKTOP_FILE"
  update-desktop-database "$SYSTEM_APPS_DIR" 2>/dev/null || true
fi

echo "[OK] Installation complete"
echo "[OK] Launch with: $INSTALL_DIR/run.sh"
