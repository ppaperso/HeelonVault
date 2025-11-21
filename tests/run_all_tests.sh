#!/bin/bash
# Script pour lancer tous les tests d'intégration

# ⚠️ SÉCURITÉ: Forcer le mode développement pour les tests
export DEV_MODE=1

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS SUR ENVIRONNEMENT DE DÉVELOPPEMENT    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔒 Mode DEV activé: DEV_MODE=$DEV_MODE"
echo "📂 Données de test: src/data/"
echo ""
echo "🧪 Lancement des tests d'intégration"
echo "=" 70 | tr ' ' '='

VENV_PYTHON="./venv-dev/bin/python"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT"
TEST_DIR="tests/integration"
LOG_TEST_SCRIPT="$REPO_ROOT/tests/test-logging.sh"

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

total=0
passed=0
failed=0

# Lancer chaque test
for test_file in $TEST_DIR/test_*.py; do
    if [ -f "$test_file" ]; then
        total=$((total + 1))
        test_name=$(basename "$test_file")
        echo ""
        echo "▶️  Test: $test_name"
        echo "─────────────────────────────────────"
        
        if $VENV_PYTHON "$test_file" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ PASS${NC}"
            passed=$((passed + 1))
        else
            echo -e "${RED}❌ FAIL${NC}"
            failed=$((failed + 1))
            # Afficher l'erreur
            $VENV_PYTHON "$test_file"
        fi
    fi
done

if [ -x "$LOG_TEST_SCRIPT" ]; then
    echo ""
    echo "▶️  Test: logging rotation"
    echo "─────────────────────────────────────"
    if "$LOG_TEST_SCRIPT" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}"
        passed=$((passed + 1))
    else
        echo -e "${RED}❌ FAIL${NC}"
        failed=$((failed + 1))
        "$LOG_TEST_SCRIPT"
    fi
fi
# Résumé
echo ""
echo "=" 70 | tr ' ' '='
echo "📊 Résumé des tests"
echo "=" 70 | tr ' ' '='
echo "Total: $total"
echo -e "${GREEN}Passés: $passed${NC}"
if [ $failed -gt 0 ]; then
    echo -e "${RED}Échoués: $failed${NC}"
else
    echo "Échoués: $failed"
fi
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}🎉 Tous les tests ont réussi !${NC}"
    exit 0
else
    echo -e "${RED}⚠️  Certains tests ont échoué${NC}"
    exit 1
fi
