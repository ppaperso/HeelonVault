#!/bin/bash
# Script de lancement de l'application en mode développement
# Utilise le venv venvpwdmanager

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venvpwdmanager"
APP_FILE="${SCRIPT_DIR}/password_manager.py"

# Vérifier que le venv existe
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Erreur: Le venv 'venvpwdmanager' n'existe pas"
    echo "   Lancez d'abord: ./test-app.sh"
    exit 1
fi

echo "🔐 Lancement du gestionnaire de mots de passe (mode développement)"
echo "================================================================="
echo ""
echo "📦 Utilisation du venv: venvpwdmanager"
echo "🐍 Python: $(source ${VENV_DIR}/bin/activate && python --version)"
echo ""
echo "ℹ️  Données stockées dans: ~/.local/share/passwordmanager/"
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
