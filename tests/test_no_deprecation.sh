#!/bin/bash
# Script pour vérifier l'absence de DeprecationWarning et d'erreurs critiques

# ⚠️ SÉCURITÉ: Forcer le mode développement pour les tests
export DEV_MODE=1

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS SUR ENVIRONNEMENT DE DÉVELOPPEMENT    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔒 Mode DEV activé: DEV_MODE=$DEV_MODE"
echo "📂 Données de test: src/data/"
echo ""
echo "🔍 Test de l'absence de DeprecationWarning et erreurs critiques GTK"
echo "====================================================================="
echo ""

cd "$(dirname "$0")/.." || exit 1

# Lancer l'application et capturer les warnings/erreurs pendant 15 secondes
timeout 15s ./run-dev.sh 2>&1 | tee /tmp/test_warnings.log &
APP_PID=$!

echo "⏳ Application lancée (PID: $APP_PID), attente de 15 secondes..."
sleep 15

# Analyser les logs
echo ""
echo "📊 Analyse des logs..."
echo "----------------------"

DEPRECATION_COUNT=$(grep -c "DeprecationWarning" /tmp/test_warnings.log 2>/dev/null || echo "0")
CRITICAL_COUNT=$(grep -c "CRITICAL" /tmp/test_warnings.log 2>/dev/null || echo "0")
FAILED_COUNT=$(grep -c "failed" /tmp/test_warnings.log 2>/dev/null || echo "0")

echo "❗ DeprecationWarning: $DEPRECATION_COUNT"
echo "❗ Messages CRITICAL: $CRITICAL_COUNT"
echo "❗ Assertions failed: $FAILED_COUNT"

echo ""
if [ "$DEPRECATION_COUNT" -eq 0 ] && [ "$CRITICAL_COUNT" -eq 0 ] && [ "$FAILED_COUNT" -eq 0 ]; then
    echo "✅ SUCCÈS : Aucun warning ou erreur critique détecté !"
    exit 0
else
    echo "❌ ÉCHEC : Des warnings ou erreurs critiques ont été détectés"
    echo ""
    echo "Détails des problèmes :"
    echo "-----------------------"
    if [ "$DEPRECATION_COUNT" -gt 0 ]; then
        echo "DeprecationWarnings détectés :"
        grep "DeprecationWarning" /tmp/test_warnings.log
    fi
    if [ "$CRITICAL_COUNT" -gt 0 ]; then
        echo "Messages CRITICAL détectés :"
        grep "CRITICAL" /tmp/test_warnings.log
    fi
    if [ "$FAILED_COUNT" -gt 0 ]; then
        echo "Assertions failed détectées :"
        grep "failed" /tmp/test_warnings.log
    fi
    exit 1
fi
