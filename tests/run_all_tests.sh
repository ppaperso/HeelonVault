#!/bin/bash
# Script pour lancer tous les tests d'intégration

echo "🧪 Lancement des tests d'intégration"
echo "=" 70 | tr ' ' '='

VENV_PYTHON="./venvpwdmanager/bin/python"
TEST_DIR="tests/integration"

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
