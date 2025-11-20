#!/bin/bash
# Script de lancement de l'application en mode développement
# Données stockées dans ./data/ (isolées de la production)

set -e

# IMPORTANT: Mode développement activé
export DEV_MODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv-dev"
APP_FILE="${SCRIPT_DIR}/password_manager.py"

# Vérifier que le venv de dev existe, sinon le créer
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Environnement virtuel de dev non trouvé. Création..."
    # Créer venv avec accès aux packages système (pour GTK4/PyGObject)
    python3 -m venv --system-site-packages "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r "${SCRIPT_DIR}/requirements.txt" > /dev/null 2>&1
    echo "✅ Environnement virtuel de dev créé: $VENV_DIR/"
else
    source "$VENV_DIR/bin/activate"
fi

echo "🔐 Lancement du gestionnaire de mots de passe (mode développement)"
echo "================================================================="
echo ""
echo "📦 Venv: venv-dev/"
echo "🐍 Python: $(python --version)"
echo "📂 Données: ./data/ (isolé de la production)"
echo ""
echo "👥 Compte admin par défaut:"
echo "   Username: admin"
echo "   Password: admin"
echo "   ⚠️  Changez ce mot de passe après la première connexion!"
echo ""
echo "================================================================="
echo ""

# Activer le venv et lancer l'application
source "${VENV_DIR}/bin/activate"
python3 "$APP_FILE"

echo ""
echo "✅ Application fermée"
