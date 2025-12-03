#!/bin/bash
# Script de rechargement rapide de l'extension pour les tests

echo "🔄 Rechargement de l'extension Firefox"
echo "======================================"
echo ""

cd "$(dirname "$0")"

# Vérifier que Firefox est lancé
if ! pgrep -x "firefox" > /dev/null; then
    echo "⚠️  Firefox n'est pas lancé"
    echo "   Lancement de Firefox avec l'extension..."
    web-ext run --source-dir=firefox_extension &
    sleep 3
else
    echo "✅ Firefox détecté"
fi

echo ""
echo "📋 Instructions pour recharger l'extension:"
echo ""
echo "   1. Ouvrir Firefox"
echo "   2. Aller sur: about:debugging#/runtime/this-firefox"
echo "   3. Trouver 'Password Manager'"
echo "   4. Cliquer sur 'Recharger'"
echo ""
echo "🐛 Pour déboguer:"
echo ""
echo "   1. Cliquer 'Inspecter' sur l'extension"
echo "   2. Voir la console pour les messages"
echo "   3. Vérifier: isConnected = true"
echo ""
echo "📊 Tests disponibles:"
echo ""
echo "   ./test_direct_communication.py  - Test du native host"
echo "   tail -f ~/.local/share/passwordmanager/native_host.log  - Logs"
echo ""
echo "🔍 Résumé des corrections appliquées:"
echo ""
echo "   ✅ Status 'ok' → 'success'"
echo "   ✅ Gestion améliorée des promesses"
echo "   ✅ Mapping des actions de réponse"
echo "   ✅ Données de test ajoutées"
echo ""

# Tester la communication
echo "🧪 Test rapide du native host..."
if python3 test_direct_communication.py | grep -q "✅ OK"; then
    echo "   ✅ Native host fonctionne correctement"
else
    echo "   ❌ Problème avec le native host"
    echo "   Voir: ./test_direct_communication.py"
fi

echo ""
echo "📚 Documentation: DEBUGGING_GUIDE.md"
echo ""
