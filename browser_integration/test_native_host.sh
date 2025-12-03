#!/bin/bash
# Script de test du Native Messaging Host

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# Détecter l'environnement virtuel (priorité à venv-dev pour les tests)
if [ -d "$APP_DIR/venv-dev" ]; then
    VENV="$APP_DIR/venv-dev"
    ENV_NAME="DÉVELOPPEMENT (venv-dev)"
elif [ -d "$APP_DIR/venv" ]; then
    VENV="$APP_DIR/venv"
    ENV_NAME="PRODUCTION (venv)"
else
    echo "❌ Aucun environnement virtuel trouvé"
    echo "   Lancez ./install.sh ou créez venv-dev pour les tests"
    exit 1
fi

PYTHON="$VENV/bin/python3"

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS DU NATIVE MESSAGING HOST              ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔍 Environnement: $ENV_NAME"
echo "🐍 Python: $PYTHON"
echo "📂 Script: $SCRIPT_DIR/native_host.py"
echo ""

# Fonction helper pour tester
test_message() {
    local test_name="$1"
    local message="$2"
    
    echo "📍 $test_name"
    echo "   Requête: $message"
    
    # Envoyer le message et capturer la réponse
    response=$(echo "$message" | "$PYTHON" "$SCRIPT_DIR/native_host.py" 2>&1)
    
    if [ $? -eq 0 ]; then
        # Décoder la réponse (skip les 4 premiers bytes de longueur)
        echo "   Réponse: $response" | tail -c +5 2>/dev/null || echo "   Réponse brute: $response"
        echo "   ✅ OK"
    else
        echo "   ❌ ERREUR"
        echo "   $response"
    fi
    echo ""
}

# Test 1: Ping
test_message "Test 1: Ping" '{"action":"ping"}'

# Test 2: Check Status
test_message "Test 2: Check Status" '{"action":"check_status"}'

# Test 3: Generate Password
test_message "Test 3: Generate Password" '{"action":"generate_password","length":20}'

# Test 4: Search Credentials
test_message "Test 4: Search Credentials" '{"action":"search_credentials","url":"https://github.com"}'

# Test 5: Action invalide
test_message "Test 5: Action invalide (doit échouer)" '{"action":"invalid_action"}'

# Test 6: Message malformé
test_message "Test 6: Message malformé (doit échouer)" '{"invalid":"json'

echo "════════════════════════════════════════════════════"
echo "✅ Tests terminés!"
echo ""
echo "📋 Logs disponibles dans:"
echo "   ~/.local/share/passwordmanager/native_host.log"
echo ""
echo "💡 Pour suivre les logs en temps réel:"
echo "   tail -f ~/.local/share/passwordmanager/native_host.log"
