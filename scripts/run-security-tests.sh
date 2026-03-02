#!/bin/bash
# Script de test SÉCURISÉ - S'assure que nous sommes en mode DEV
# et exécute les tests dans le venv-dev

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${ROOT_DIR}/venv-dev"

echo "🛡️  TESTS DE SÉCURITÉ - MODE DEV UNIQUEMENT"
echo "============================================="
echo ""

# VÉRIFICATION CRITIQUE : Mode DEV obligatoire
export DEV_MODE=1

# Vérifier que le répertoire de données sera bien dans ./data
DATA_CHECK=$(python3 -c "
import os
import sys
os.environ['DEV_MODE'] = '1'
sys.path.insert(0, '$ROOT_DIR')
from src.config.environment import get_data_directory, is_dev_mode
data_dir = get_data_directory()
is_dev = is_dev_mode()
print(f'{data_dir}|{is_dev}')
")

DATA_DIR=$(echo $DATA_CHECK | cut -d'|' -f1)
IS_DEV=$(echo $DATA_CHECK | cut -d'|' -f2)

echo "🔍 Vérifications de sécurité :"
echo "   DEV_MODE        : $DEV_MODE"
echo "   is_dev_mode()   : $IS_DEV"
echo "   Répertoire data : $DATA_DIR"
echo ""

# VÉRIFICATION CRITIQUE : Le chemin NE DOIT PAS contenir /var/lib/heelonvault-shared
if [[ "$DATA_DIR" == *"/var/lib/heelonvault-shared"* ]]; then
    echo "❌ ERREUR CRITIQUE : Le répertoire de données pointe vers la PRODUCTION !"
    echo "   $DATA_DIR"
    echo ""
    echo "   Les tests sont ANNULÉS pour protéger vos données."
    echo "   Vérifiez que DEV_MODE=1 est bien défini."
    exit 1
fi

# Vérifier que is_dev_mode retourne True
if [ "$IS_DEV" != "True" ]; then
    echo "❌ ERREUR : is_dev_mode() retourne False"
    echo "   Les tests sont ANNULÉS."
    exit 1
fi

echo "✅ SÉCURITÉ VÉRIFIÉE : Mode DEV actif, données isolées"
echo ""

# Activer le venv-dev
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Erreur : venv-dev n'existe pas"
    echo "   Exécutez d'abord : ./run-dev.sh"
    exit 1
fi

source "$VENV_DIR/bin/activate"
echo "✅ Environnement virtuel : venv-dev/"
echo ""

# Afficher la version de Python
PYTHON_VERSION=$(python --version)
echo "🐍 Python : $PYTHON_VERSION"
echo ""

# Exécuter les tests
echo "============================================="
echo "🧪 EXÉCUTION DES TESTS"
echo "============================================="
echo ""

python "${ROOT_DIR}/test_security_improvements.py"

echo ""
echo "============================================="
echo "✅ TESTS TERMINÉS"
echo "============================================="
echo ""
echo "Prochaines étapes :"
echo "  1. Vérifier les résultats ci-dessus"
echo "  2. Lire IMPLEMENTATION_GUIDE.md"
echo "  3. Appliquer les modifications dans le code"
echo "  4. Tester l'application : ./run-dev.sh"
echo ""
