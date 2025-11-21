#!/bin/bash

# Script de test pour la fonctionnalité d'import CSV
# Ce script génère un fichier CSV de test et vérifie que l'import fonctionne

set -e

# ⚠️ SÉCURITÉ: Forcer le mode développement pour les tests
export DEV_MODE=1

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS SUR ENVIRONNEMENT DE DÉVELOPPEMENT    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔒 Mode DEV activé: DEV_MODE=$DEV_MODE"
echo "📂 Données de test: src/data/"
echo ""
echo "🧪 Test de la fonctionnalité d'import CSV"
echo "=========================================="

# Activer l'environnement virtuel
if [ -d "venvpwdmanager" ]; then
    source venvpwdmanager/bin/activate
    echo "✅ Environnement virtuel activé"
else
    echo "❌ Erreur: venvpwdmanager introuvable"
    exit 1
fi

# Vérifier que les modules existent
echo ""
echo "📦 Vérification des modules..."
python3 -c "from src.services.csv_importer import CSVImporter; print('✅ csv_importer.py OK')" || exit 1
python3 -c "from src.ui.dialogs.import_dialog import ImportCSVDialog; print('✅ import_dialog.py OK')" || exit 1

# Créer un fichier CSV de test s'il n'existe pas
if [ ! -f "test_import_lastpass.csv" ]; then
    echo ""
    echo "📝 Création du fichier de test..."
    cat > test_import_lastpass.csv << 'EOF'
https://github.com;john.doe@email.com;MySecretPass123!;GitHub Account
https://gmail.com;jane.smith@gmail.com;Gmail2024Secure;Gmail Personnel
https://twitter.com;@myhandle;Tw1tt3rP@ss;Twitter
https://www.amazon.com;shopper123;AmazonBuy456;Amazon Shopping
EOF
    echo "✅ Fichier test_import_lastpass.csv créé"
fi

# Exécuter les tests unitaires
echo ""
echo "🧪 Exécution des tests unitaires..."
python3 -m unittest tests.unit.test_csv_importer -v

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Tous les tests sont passés avec succès!"
    echo ""
    echo "📋 Fichiers de test disponibles:"
    echo "   - test_import_lastpass.csv (sans en-tête)"
    echo "   - test_import_lastpass_with_header.csv (avec en-tête)"
    echo ""
    echo "🚀 Vous pouvez maintenant lancer l'application:"
    echo "   ./run-dev.sh"
    echo ""
    echo "💡 Pour tester l'import:"
    echo "   1. Lancez l'application"
    echo "   2. Connectez-vous (admin/admin)"
    echo "   3. Menu → 'Importer depuis CSV'"
    echo "   4. Sélectionnez un fichier de test"
else
    echo ""
    echo "❌ Certains tests ont échoué"
    exit 1
fi
