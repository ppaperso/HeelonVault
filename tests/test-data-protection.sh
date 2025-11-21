#!/bin/bash
# Test de la protection des données améliorée

# ⚠️ SÉCURITÉ: Forcer le mode développement pour les tests
export DEV_MODE=1

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS SUR ENVIRONNEMENT DE DÉVELOPPEMENT    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔒 Mode DEV activé: DEV_MODE=$DEV_MODE"
echo "📂 Données de test: src/data/"
echo ""
echo "🔐 Test de la protection des données"
echo "===================================="
echo ""

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonction de test
test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ PASS${NC}: $2"
    else
        echo -e "${RED}❌ FAIL${NC}: $2"
    fi
}

echo -e "${BLUE}1. Test des permissions des fichiers${NC}"
echo "----------------------------------------"

# Vérifier les permissions en mode dev
DATA_DIR="src/data"

if [ -f "$DATA_DIR/users.db" ]; then
    PERM=$(stat -c '%a' "$DATA_DIR/users.db")
    if [ "$PERM" = "600" ]; then
        test_result 0 "users.db a les bonnes permissions (600)"
    else
        test_result 1 "users.db a les mauvaises permissions ($PERM au lieu de 600)"
    fi
else
    echo "⚠️  users.db n'existe pas encore"
fi

if [ -f "$DATA_DIR/passwords_admin.db" ]; then
    PERM=$(stat -c '%a' "$DATA_DIR/passwords_admin.db")
    if [ "$PERM" = "600" ]; then
        test_result 0 "passwords_admin.db a les bonnes permissions (600)"
    else
        test_result 1 "passwords_admin.db a les mauvaises permissions ($PERM au lieu de 600)"
    fi
else
    echo "⚠️  passwords_admin.db n'existe pas encore"
fi

if [ -f "$DATA_DIR/salt_admin.bin" ]; then
    PERM=$(stat -c '%a' "$DATA_DIR/salt_admin.bin")
    if [ "$PERM" = "600" ]; then
        test_result 0 "salt_admin.bin a les bonnes permissions (600)"
    else
        test_result 1 "salt_admin.bin a les mauvaises permissions ($PERM au lieu de 600)"
    fi
else
    echo "⚠️  salt_admin.bin n'existe pas encore"
fi

echo ""
echo -e "${BLUE}2. Test de l'existence du répertoire backups${NC}"
echo "---------------------------------------------"

if [ -d "$DATA_DIR/backups" ]; then
    test_result 0 "Répertoire backups/ existe"
    
    # Compter les sauvegardes
    BACKUP_COUNT=$(ls -1 "$DATA_DIR/backups/"*.db 2>/dev/null | wc -l)
    echo "📦 Nombre de sauvegardes : $BACKUP_COUNT"
    
    if [ $BACKUP_COUNT -gt 0 ]; then
        echo "📄 Dernières sauvegardes :"
        ls -lht "$DATA_DIR/backups/"*.db 2>/dev/null | head -5 | while read line; do
            echo "   $line"
        done
    fi
else
    test_result 1 "Répertoire backups/ n'existe pas"
fi

echo ""
echo -e "${BLUE}3. Test des services Python${NC}"
echo "--------------------------------"

# Test du module backup_service
source venv-dev/bin/activate 2>/dev/null
python3 -c "from src.services.backup_service import BackupService; print('Import OK')" 2>/dev/null
if [ $? -eq 0 ]; then
    test_result 0 "Module BackupService importable"
else
    test_result 1 "Module BackupService non importable"
fi

echo ""
echo -e "${BLUE}4. Test unitaires${NC}"
echo "-------------------"

python3 -m unittest tests.unit.test_backup_service 2>&1 | tail -3
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    test_result 0 "Tests unitaires du BackupService"
else
    test_result 1 "Tests unitaires du BackupService"
fi

echo ""
echo -e "${BLUE}5. Test de sécurité - Tentative de lecture non autorisée${NC}"
echo "-----------------------------------------------------------"

if [ -f "$DATA_DIR/passwords_admin.db" ]; then
    # Simuler une tentative de lecture par un autre processus (sans permissions)
    # On vérifie simplement que les permissions empêchent la lecture
    PERM=$(stat -c '%a' "$DATA_DIR/passwords_admin.db")
    if [ "$PERM" = "600" ]; then
        echo "✅ Les permissions 600 empêchent la lecture par d'autres utilisateurs"
        test_result 0 "Protection contre l'accès non autorisé"
    else
        echo "⚠️  Les permissions $PERM pourraient permettre un accès non autorisé"
        test_result 1 "Protection contre l'accès non autorisé"
    fi
else
    echo "⚠️  Aucun fichier à tester"
fi

echo ""
echo "===================================="
echo -e "${GREEN}✅ Tests de protection des données terminés${NC}"
echo "===================================="
echo ""
echo "📚 Pour plus d'informations, consultez :"
echo "   - docs/DATA_PROTECTION.md"
echo "   - CHANGELOG_DATA_PROTECTION.md"
