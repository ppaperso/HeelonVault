#!/bin/bash

# Test du système de versioning

echo "🔍 Test du système de versioning"
echo "=================================="

# Activer l'environnement virtuel
if [ -d "venvpwdmanager" ]; then
    source venvpwdmanager/bin/activate
    echo "✅ Environnement virtuel activé"
else
    echo "❌ Erreur: venvpwdmanager introuvable"
    exit 1
fi

# Test 1: Vérifier que le module version existe
echo ""
echo "📦 Test 1: Module version"
python3 -c "from src.version import get_version, get_version_info; print('✅ Module version OK')" || { echo "❌ Échec"; exit 1; }

# Test 2: Récupérer la version
echo ""
echo "📦 Test 2: Récupération de la version"
VERSION=$(python3 -c "from src.version import get_version; print(get_version())")
echo "   Version actuelle: $VERSION"

if [ "$VERSION" == "0.2.0-beta" ]; then
    echo "✅ Version correcte: $VERSION"
else
    echo "❌ Version incorrecte. Attendu: 0.2.0-beta, Obtenu: $VERSION"
    exit 1
fi

# Test 3: Vérifier les informations de version
echo ""
echo "📦 Test 3: Informations complètes"
python3 << 'EOF'
from src.version import get_version_info

info = get_version_info()
print(f"   Nom: {info['app_name']}")
print(f"   Version: {info['version']}")
print(f"   Description: {info['description']}")
print(f"   Auteur: {info['author']}")
print(f"   Licence: {info['license']}")
print(f"   Copyright: {info['copyright']}")
print("✅ Toutes les informations sont présentes")
EOF

# Test 4: Vérifier que le dialogue About fonctionne
echo ""
echo "📦 Test 4: Module about_dialog"
python3 -c "from src.ui.dialogs.about_dialog import show_about_dialog; print('✅ Module about_dialog OK')" || { echo "❌ Échec"; exit 1; }

echo ""
echo "================================================"
echo "✅ Tous les tests de versioning sont passés!"
echo "================================================"
echo ""
echo "📋 Version de l'application: $VERSION"
echo ""
echo "🚀 Pour voir le versioning dans l'application:"
echo "   1. Lancez l'application: ./run-dev.sh"
echo "   2. Sur l'écran de sélection, vous verrez 'Version 0.2.0-beta'"
echo "   3. Sur l'écran de connexion, vous verrez 'v0.2.0-beta'"
echo "   4. Dans le menu principal → 'À propos' pour voir tous les détails"
