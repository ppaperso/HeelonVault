#!/bin/bash
# Script pour packager l'extension Firefox et la préparer pour signature

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_DIR="$SCRIPT_DIR/firefox_extension"
OUTPUT_DIR="$SCRIPT_DIR/packages"
VERSION="0.1.0"

echo "╔════════════════════════════════════════════════════╗"
echo "║   📦 Package Extension Firefox pour Signature    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Créer le dossier de sortie
mkdir -p "$OUTPUT_DIR"

# Nom du package
PACKAGE_NAME="password-manager-${VERSION}.zip"
PACKAGE_PATH="$OUTPUT_DIR/$PACKAGE_NAME"

# Supprimer l'ancien package si existant
if [ -f "$PACKAGE_PATH" ]; then
    rm "$PACKAGE_PATH"
    echo "🗑️  Ancien package supprimé"
fi

echo "📦 Création du package..."
cd "$EXTENSION_DIR"

# Créer le ZIP avec tous les fichiers nécessaires
zip -r "$PACKAGE_PATH" \
    manifest.json \
    background.js \
    content.js \
    popup.html \
    popup.js \
    popup.css \
    icons/*.png \
    -x "*.svg" "README.txt"

echo "✅ Package créé: $PACKAGE_PATH"
echo ""

# Afficher la taille
SIZE=$(du -h "$PACKAGE_PATH" | cut -f1)
echo "📊 Taille: $SIZE"
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         🚀 Prochaines étapes pour la signature               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📝 Méthode 1 - Signature automatique avec web-ext (Recommandée)"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   1. Créer un compte sur https://addons.mozilla.org"
echo ""
echo "   2. Générer des clés API:"
echo "      → https://addons.mozilla.org/developers/addon/api/key/"
echo "      → Notez votre JWT_ISSUER et JWT_SECRET"
echo ""
echo "   3. Installer web-ext:"
echo "      npm install -g web-ext"
echo ""
echo "   4. Signer l'extension:"
echo "      cd $EXTENSION_DIR"
echo "      web-ext sign \\"
echo "        --api-key=YOUR_JWT_ISSUER \\"
echo "        --api-secret=YOUR_JWT_SECRET"
echo ""
echo "   5. Récupérer le fichier .xpi signé dans web-ext-artifacts/"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Méthode 2 - Signature manuelle (Alternative)"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   1. Aller sur: https://addons.mozilla.org/developers/addons"
echo ""
echo "   2. Cliquer sur 'Submit a New Add-on'"
echo ""
echo "   3. Choisir 'On this site' (self-distribution)"
echo ""
echo "   4. Uploader le fichier: $PACKAGE_PATH"
echo ""
echo "   5. Télécharger le .xpi signé après validation"
echo ""
echo "   6. Installer le .xpi dans Firefox:"
echo "      - Ouvrir le fichier .xpi avec Firefox, OU"
echo "      - Glisser-déposer le .xpi dans Firefox"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Méthode 3 - Firefox Developer/Nightly (Sans signature)"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   1. Installer Firefox Developer Edition ou Nightly"
echo ""
echo "   2. Aller dans about:config"
echo ""
echo "   3. Définir: xpinstall.signatures.required = false"
echo ""
echo "   4. Installer le .zip non signé comme .xpi"
echo ""
echo "   ⚠️  Cette méthode fonctionne uniquement avec Firefox Developer/Nightly"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Recommandation:"
echo "   → Utilisez la Méthode 1 (web-ext) pour un processus automatisé"
echo "   → La signature prend généralement 10-15 minutes"
echo "   → L'extension signée sera installable de façon permanente"
echo ""
echo "📚 Documentation:"
echo "   → https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/"
echo ""
