#!/bin/bash
# Script d'installation DEV de l'extension Firefox Password Manager
# Installe la version de développement qui utilise src/data/

set -e

echo "╔════════════════════════════════════════════════════╗"
echo "║   📦 Installation Extension Firefox (DEV)         ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# 1. Créer le manifest native-messaging pour DEV
echo "📝 Création du manifest native messaging (DEV)..."
MANIFEST_DIR="$HOME/.mozilla/native-messaging-hosts"
mkdir -p "$MANIFEST_DIR"

cat > "$MANIFEST_DIR/com.passwordmanager.native.dev.json" << EOF
{
  "name": "com.passwordmanager.native.dev",
  "description": "Native messaging host pour Password Manager (DEV)",
  "path": "$SCRIPT_DIR/native_host_wrapper_dev.sh",
  "type": "stdio",
  "allowed_extensions": [
    "password-manager-dev@example.com"
  ]
}
EOF

chmod 644 "$MANIFEST_DIR/com.passwordmanager.native.dev.json"
echo "✅ Manifest créé: $MANIFEST_DIR/com.passwordmanager.native.dev.json"

# 2. Vérifier que le wrapper dev est exécutable
if [ ! -x "$SCRIPT_DIR/native_host_wrapper_dev.sh" ]; then
    chmod +x "$SCRIPT_DIR/native_host_wrapper_dev.sh"
    echo "✅ Wrapper dev rendu exécutable"
fi

# 3. Modifier l'extension dev pour utiliser le bon native host
echo ""
echo "📝 Configuration de l'extension DEV..."
BACKGROUND_JS="$SCRIPT_DIR/firefox_extension_dev/background.js"

# Vérifier si le connectNative utilise le bon nom
if grep -q 'com.passwordmanager.native"' "$BACKGROUND_JS"; then
    sed -i 's/com.passwordmanager.native"/com.passwordmanager.native.dev"/g' "$BACKGROUND_JS"
    echo "✅ Extension configurée pour utiliser le native host DEV"
fi

# 4. Instructions pour Firefox
echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║   🦊 Installation dans Firefox                    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "📋 Méthode 1 - Installation temporaire (Recommandé pour DEV):"
echo "   1. Ouvrir Firefox"
echo "   2. Aller sur: about:debugging#/runtime/this-firefox"
echo "   3. Cliquer 'Charger un module complémentaire temporaire...'"
echo "   4. Sélectionner: $SCRIPT_DIR/firefox_extension_dev/manifest.json"
echo ""
echo "📋 Méthode 2 - Installation avec web-ext:"
echo "   cd $SCRIPT_DIR"
echo "   npx web-ext run --source-dir=firefox_extension_dev"
echo ""
echo "🎯 Données utilisées:"
echo "   Base de données: $APP_DIR/src/data/passwords_admin.db"
echo "   Logs: $APP_DIR/logs/native_host_dev.log"
echo ""
echo "🔍 Vérification:"
echo "   - Ouvrir Firefox"
echo "   - Cliquer sur l'icône de l'extension (badge [DEV])"
echo "   - Vérifier que le statut est 🟢 Connecté"
echo "   - Les credentials de src/data/ doivent apparaître"
echo ""
echo "✅ Installation DEV terminée!"
echo ""
