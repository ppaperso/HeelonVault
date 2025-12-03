#!/bin/bash
# Script d'installation PRODUCTION de l'extension Firefox Password Manager
# Installe la version de production qui utilise data/

set -e

echo "╔════════════════════════════════════════════════════╗"
echo "║   📦 Installation Extension Firefox (PRODUCTION)  ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# 1. Créer le manifest native-messaging pour PRODUCTION
echo "📝 Création du manifest native messaging (PRODUCTION)..."
MANIFEST_DIR="$HOME/.mozilla/native-messaging-hosts"
mkdir -p "$MANIFEST_DIR"

cat > "$MANIFEST_DIR/com.passwordmanager.native.json" << EOF
{
  "name": "com.passwordmanager.native",
  "description": "Native messaging host pour Password Manager",
  "path": "$SCRIPT_DIR/native_host_wrapper.sh",
  "type": "stdio",
  "allowed_extensions": [
    "password-manager@example.com"
  ]
}
EOF

chmod 644 "$MANIFEST_DIR/com.passwordmanager.native.json"
echo "✅ Manifest créé: $MANIFEST_DIR/com.passwordmanager.native.json"

# 2. Vérifier que le wrapper prod est exécutable
if [ ! -x "$SCRIPT_DIR/native_host_wrapper.sh" ]; then
    chmod +x "$SCRIPT_DIR/native_host_wrapper.sh"
    echo "✅ Wrapper prod rendu exécutable"
fi

# 3. Vérifier la configuration de l'extension prod
echo ""
echo "📝 Vérification de l'extension PRODUCTION..."
BACKGROUND_JS="$SCRIPT_DIR/firefox_extension/background.js"

# S'assurer que l'extension utilise le nom de production
if grep -q 'com.passwordmanager.native.dev"' "$BACKGROUND_JS"; then
    sed -i 's/com.passwordmanager.native.dev"/com.passwordmanager.native"/g' "$BACKGROUND_JS"
    echo "✅ Extension configurée pour utiliser le native host PRODUCTION"
fi

# 4. Instructions pour Firefox
echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║   🦊 Installation dans Firefox                    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "📋 Pour une installation PERMANENTE (Recommandé pour PROD):"
echo "   1. Signer l'extension:"
echo "      cd $SCRIPT_DIR"
echo "      ./package_for_signing.sh"
echo "      ./sign_extension.sh"
echo ""
echo "   2. Installer le .xpi généré"
echo ""
echo "📋 Pour une installation temporaire (Tests):"
echo "   1. Ouvrir Firefox"
echo "   2. Aller sur: about:debugging#/runtime/this-firefox"
echo "   3. Cliquer 'Charger un module complémentaire temporaire...'"
echo "   4. Sélectionner: $SCRIPT_DIR/firefox_extension/manifest.json"
echo ""
echo "🎯 Données utilisées:"
echo "   Base de données: $APP_DIR/data/passwords_admin.db"
echo "   Logs: ~/.local/share/passwordmanager/native_host.log"
echo ""
echo "⚠️  IMPORTANT:"
echo "   - Les données de PRODUCTION sont utilisées"
echo "   - Assurez-vous d'avoir lancé l'application au moins une fois"
echo "   - Pour des tests, utilisez install_dev.sh à la place"
echo ""
echo "✅ Installation PRODUCTION terminée!"
echo ""
