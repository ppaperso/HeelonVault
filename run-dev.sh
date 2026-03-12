#!/bin/bash
# Script de lancement de l'application en mode développement
# Données stockées dans ./data/ (isolées de la production)

set -e

# IMPORTANT: Mode développement activé
export DEV_MODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv-dev"
APP_FILE="${SCRIPT_DIR}/heelonvault.py"
VENV_PYTHON="${VENV_DIR}/bin/python3"
DEV_DESKTOP_DIR="${HOME}/.local/share/applications"
DEV_DESKTOP_FILE="${DEV_DESKTOP_DIR}/org.heelonys.heelonvault.dev.desktop"
DEV_ICONS_DIR="${HOME}/.local/share/icons/hicolor"
SOURCE_ICONS_DIR="${SCRIPT_DIR}/src/resources/icons/hicolor"

# ---------------------------------------------------------------------------
# Vérification Python 3.14
# ---------------------------------------------------------------------------
SYSTEM_PYTHON="python3.14"
if ! command -v python3.14 &>/dev/null; then
    SYSTEM_PYTHON="python3"
fi

PY_VERSION=$("$SYSTEM_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
if [[ "$PY_VERSION" != "3.14" ]]; then
    echo "❌ Python 3.14 requis, trouvé : $PY_VERSION"
    echo "   Vérifiez votre PATH ou installez Python 3.14"
    exit 1
fi

# ---------------------------------------------------------------------------
# Version applicative (lue depuis src/version.py, pas hardcodée)
# ---------------------------------------------------------------------------
APP_VERSION=$(grep -oP '(?<=__version__ = ")[^"]+' "${SCRIPT_DIR}/src/version.py" 2>/dev/null || echo "unknown")

ensure_dev_desktop_entry() {
    mkdir -p "$DEV_DESKTOP_DIR"
    cat > "$DEV_DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=${APP_VERSION}
Type=Application
Name=HeelonVault (Dev)
Comment=HeelonVault development launcher
Exec=${SCRIPT_DIR}/run-dev.sh
Icon=heelonvault
Terminal=false
Categories=Utility;Security;
StartupNotify=true
StartupWMClass=org.heelonys.heelonvault.dev
EOF
    update-desktop-database "$DEV_DESKTOP_DIR" 2>/dev/null || true
}

ensure_dev_icons() {
    if [ ! -d "$SOURCE_ICONS_DIR" ]; then
        return
    fi

    mkdir -p "$DEV_ICONS_DIR"
    cp -a "$SOURCE_ICONS_DIR/." "$DEV_ICONS_DIR/"
    gtk-update-icon-cache -f "$DEV_ICONS_DIR" 2>/dev/null || true
}

create_venv() {
    echo "📦 Création/Réparation de venv-dev..."
    rm -rf "$VENV_DIR"
    "$SYSTEM_PYTHON" -m venv --system-site-packages "$VENV_DIR"
    VENV_PYTHON="${VENV_DIR}/bin/python3"
    echo "✅ Environnement virtuel de dev prêt: $VENV_DIR/"
}

# Vérifier que le venv de dev existe, sinon le créer
if [ ! -d "$VENV_DIR" ]; then
    create_venv
fi

# Vérifier que le Python de venv-dev est valide
if ! "$VENV_PYTHON" -c "import sys" > /dev/null 2>&1; then
    echo "⚠️  venv-dev invalide détecté (interpréteur cassé)."
    create_venv
fi

# Synchroniser les dépendances à chaque lancement (venv existant ou nouveau)
echo "🔄 Synchronisation des dépendances dans venv-dev..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "${SCRIPT_DIR}/requirements.txt"

ensure_dev_desktop_entry
ensure_dev_icons

# ---------------------------------------------------------------------------
# Diagnostic schéma des bases vault
# ---------------------------------------------------------------------------
echo "🗄️  État des bases vault :"
for db in "${SCRIPT_DIR}"/src/data/passwords_*.db; do
    if [ -f "$db" ]; then
        db_name=$(basename "$db")
        schema_ver=$(sqlite3 "$db" "SELECT value FROM metadata WHERE key='schema_version';" 2>/dev/null || echo "")
        echo "   • ${db_name}  →  schema_version = ${schema_ver:-1 (absent)}"
    fi
done
echo ""

echo "🔐 Lancement du gestionnaire de mots de passe (mode développement)"
echo "================================================================="
echo ""
echo "📦 Venv: venv-dev/"
echo "🐍 Python: $($VENV_PYTHON --version)"
echo "🏷️  Version: ${APP_VERSION}"
echo "📂 Données: ./src/data/ (isolé de la production)"
echo ""
echo "👥 Compte admin par défaut:"
echo "   Email: admin@local.heelonvault"
echo "   Username: admin"
echo "   Password: admin"
echo "   ⚠️  Changez ce mot de passe après la première connexion!"
echo ""
echo "================================================================="
echo ""

# Activer le venv et lancer l'application
"$VENV_PYTHON" "$APP_FILE"

echo ""
echo "✅ Application fermée"