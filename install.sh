#!/usr/bin/env bash
# Installer for HeelonVault - déploie le binaire pré-compilé

set -euo pipefail

APP_NAME="HeelonVault"
APP_ID="com.heelonvault.rust"
INSTALL_DIR="/opt/heelonvault"
DATA_DIR="$INSTALL_DIR/data"
LOGS_DIR="$INSTALL_DIR/logs"
DB_FILE="$DATA_DIR/heelonvault-rust-dev.db"
BACKUP_DIR="/var/backups/heelonvault"
SYSTEM_APPS_DIR="/usr/share/applications"
DESKTOP_FILE="$APP_ID.desktop"
LEGACY_DESKTOP_FILE="heelonvault.desktop"
DESKTOP_PATH="$SYSTEM_APPS_DIR/$DESKTOP_FILE"
LEGACY_DESKTOP_PATH="$SYSTEM_APPS_DIR/$LEGACY_DESKTOP_FILE"
ICON_THEME_DIR="/usr/share/icons/hicolor"
LOCAL_ICON_DIR="$INSTALL_DIR/icons"
LOCAL_ICON_PATH="$LOCAL_ICON_DIR/heelonvault.png"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRIMARY_ICON_SOURCE="$SCRIPT_DIR/resources/icons/hicolor/256x256/apps/heelonvault.png"

# ─── Prérequis ────────────────────────────────────────────────────────────────

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ERROR] Run with sudo."
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/heelonvault" ]]; then
  echo "[ERROR] Binaire 'heelonvault' introuvable dans $SCRIPT_DIR"
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/heelonvault.desktop" ]]; then
  echo "[ERROR] Fichier desktop 'heelonvault.desktop' introuvable dans $SCRIPT_DIR"
  exit 1
fi

if [[ ! -f "$PRIMARY_ICON_SOURCE" ]]; then
  echo "[ERROR] Icône principale introuvable : $PRIMARY_ICON_SOURCE"
  exit 1
fi

# ─── Détection installation existante ────────────────────────────────────────

FRESH_INSTALL=true
KEEP_DATA=true

if [[ -d "$INSTALL_DIR" ]]; then
  FRESH_INSTALL=false
  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║       HeelonVault est déjà installé                 ║"
  echo "╚══════════════════════════════════════════════════════╝"

  if [[ -f "$DB_FILE" ]]; then
    echo ""
    echo "  Une base de données existante a été détectée :"
    echo "  $DB_FILE"
    echo ""
    echo "  Que souhaitez-vous faire ?"
    echo "  [1] Conserver les données (mise à jour, backup automatique) [défaut]"
    echo "  [2] Repartir de zéro (suppression complète, backup automatique)"
    echo ""
    read -rp "  Votre choix [1/2] : " choice
    case "${choice:-1}" in
      2)
        KEEP_DATA=false
        echo ""
        echo "  ⚠  Les données seront supprimées après backup."
        ;;
      *)
        KEEP_DATA=true
        echo ""
        echo "  ✓  Les données seront conservées."
        ;;
    esac
  else
    echo "  Aucune base de données détectée, mise à jour simple."
    KEEP_DATA=false
  fi
  echo ""
fi

# ─── Backup de la base de données ────────────────────────────────────────────

if [[ -f "$DB_FILE" ]]; then
  TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
  BACKUP_FILE="$BACKUP_DIR/heelonvault_backup_${TIMESTAMP}.db"
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  cp "$DB_FILE" "$BACKUP_FILE"
  echo "[INFO] Backup de la base de données → $BACKUP_FILE"
fi

# ─── Nettoyage ────────────────────────────────────────────────────────────────

if [[ "$FRESH_INSTALL" == false ]]; then
  if [[ "$KEEP_DATA" == true ]]; then
    # Mise à jour : on garde data/ intact, on nettoie le reste
    echo "[INFO] Mise à jour : conservation de data/"
    find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 \
      ! -name 'data' \
      -exec rm -rf {} +
  else
    # Repartir de zéro : suppression complète
    echo "[INFO] Suppression complète de $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
  fi
fi

# ─── Installation ─────────────────────────────────────────────────────────────

echo "[INFO] Déploiement vers $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$LOGS_DIR"
mkdir -p "$LOCAL_ICON_DIR"

cp "$SCRIPT_DIR/heelonvault" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/heelonvault.desktop" "$INSTALL_DIR/"

for f in README.md QUICKSTART.md; do
  [[ -f "$SCRIPT_DIR/$f" ]] && cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/"
done

# Générer run.sh
cat > "$INSTALL_DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/heelonvault"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
APP_DATA_DIR="$DATA_HOME/heelonvault"
APP_STATE_DIR="$STATE_HOME/heelonvault"
DB_PATH="$APP_DATA_DIR/heelonvault-rust.db"
LOG_DIR="$APP_STATE_DIR/logs"
LEGACY_DB_PATH="/opt/heelonvault/data/heelonvault-rust-dev.db"

umask 077
mkdir -p "$APP_DATA_DIR" "$LOG_DIR"

if [[ ! -f "$DB_PATH" && -r "$LEGACY_DB_PATH" ]]; then
  cp -n "$LEGACY_DB_PATH" "$DB_PATH" 2>/dev/null || true
fi

cd /opt/heelonvault
export HEELONVAULT_DB_PATH="$DB_PATH"
export HEELONVAULT_LOG_DIR="$LOG_DIR"
exec /opt/heelonvault/heelonvault "$@"
EOF

chmod +x "$INSTALL_DIR/heelonvault"
chmod +x "$INSTALL_DIR/run.sh"

# ─── Icônes ───────────────────────────────────────────────────────────────────

echo "[INFO] Installation des icônes..."
install -m 644 "$PRIMARY_ICON_SOURCE" "$LOCAL_ICON_PATH"

for size in 48x48 128x128 256x256; do
  SRC="$SCRIPT_DIR/resources/icons/hicolor/$size/apps/heelonvault.png"
  DST="$ICON_THEME_DIR/$size/apps"
  if [[ -f "$SRC" ]]; then
    mkdir -p "$DST"
    install -m 644 "$SRC" "$DST/heelonvault.png"
    install -m 644 "$SRC" "$DST/$APP_ID.png"
  fi
done

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$ICON_THEME_DIR" 2>/dev/null || true
fi

# ─── Droits ───────────────────────────────────────────────────────────────────

chown -R root:root "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$DATA_DIR"
chmod 755 "$LOGS_DIR"
chown -R root:root "$BACKUP_DIR" 2>/dev/null || true

# ─── Dépendances runtime ──────────────────────────────────────────────────────

echo "[INFO] Vérification des dépendances runtime..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  desktop-file-utils \
  libgtk-4-1 \
  libadwaita-1-0 \
  libsqlite3-0 \
  libglib2.0-0

# ─── Raccourci bureau ─────────────────────────────────────────────────────────

echo "[INFO] Installation du raccourci bureau..."
cat > "$DESKTOP_PATH" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=Gestionnaire de mots de passe
Exec=/opt/heelonvault/run.sh
TryExec=/opt/heelonvault/run.sh
Icon=$LOCAL_ICON_PATH
Terminal=false
Categories=System;Security;
Keywords=security;secret;encryption;vault;password;
StartupNotify=true
StartupWMClass=$APP_ID
EOF

chmod 644 "$DESKTOP_PATH"

# Compatibilite legacy: certains environnements recherchent encore heelonvault.desktop.
cat > "$LEGACY_DESKTOP_PATH" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=Gestionnaire de mots de passe
Exec=/opt/heelonvault/run.sh
TryExec=/opt/heelonvault/run.sh
Icon=$LOCAL_ICON_PATH
Terminal=false
Categories=System;Security;
Keywords=security;secret;encryption;vault;password;
StartupNotify=true
StartupWMClass=$APP_ID
EOF
chmod 644 "$LEGACY_DESKTOP_PATH"

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$DESKTOP_PATH"
  desktop-file-validate "$LEGACY_DESKTOP_PATH"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$SYSTEM_APPS_DIR" 2>/dev/null || true
fi

# Verification explicite de la pose des artefacts critiques.
if [[ ! -x "$INSTALL_DIR/run.sh" ]]; then
  echo "[ERROR] Lanceur terminal manquant ou non executable: $INSTALL_DIR/run.sh"
  exit 1
fi

if [[ ! -f "$DESKTOP_PATH" ]]; then
  echo "[ERROR] Lanceur desktop non installe: $DESKTOP_PATH"
  exit 1
fi

if [[ ! -f "$LEGACY_DESKTOP_PATH" ]]; then
  echo "[ERROR] Lanceur desktop legacy non installe: $LEGACY_DESKTOP_PATH"
  exit 1
fi

# ─── Résumé ───────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            Installation terminée                    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "[OK] Binaire installé : $INSTALL_DIR/heelonvault"
echo "[OK] Lanceur installé : $DESKTOP_PATH"
echo "[OK] Lanceur compat installé : $LEGACY_DESKTOP_PATH"
echo "[OK] Lancement terminal : $INSTALL_DIR/run.sh"
echo "[OK] Base utilisateur : ~/.local/share/heelonvault/heelonvault-rust.db"
echo "[OK] Logs utilisateur : ~/.local/state/heelonvault/logs"
echo "[OK] L'application est disponible dans le menu applicatif GNOME"
echo "[OK] Test menu: gtk-launch $APP_ID"