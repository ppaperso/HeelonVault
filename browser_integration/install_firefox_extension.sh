#!/bin/bash
# Script d'installation de l'extension Firefox pour Password Manager

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_DIR="$SCRIPT_DIR/firefox_extension"

echo "╔════════════════════════════════════════════════════╗"
echo "║   🦊 Installation Extension Firefox              ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Vérifier que l'extension existe
if [ ! -d "$EXTENSION_DIR" ]; then
    echo "❌ Répertoire d'extension non trouvé: $EXTENSION_DIR"
    exit 1
fi

# Vérifier les fichiers requis
REQUIRED_FILES=(
    "manifest.json"
    "background.js"
    "content.js"
    "popup.html"
    "popup.js"
    "popup.css"
    "icons/icon-48.png"
    "icons/icon-96.png"
)

echo "📋 Vérification des fichiers..."
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$EXTENSION_DIR/$file" ]; then
        echo "❌ Fichier manquant: $file"
        exit 1
    fi
    echo "   ✅ $file"
done

echo ""
echo "📦 Préparation de l'extension..."

# Créer un fichier README pour l'extension
cat > "$EXTENSION_DIR/README.txt" << 'EOF'
Password Manager - Extension Firefox
====================================

Cette extension permet d'intégrer votre gestionnaire de mots de passe
avec Firefox pour :
- Auto-compléter les formulaires de connexion
- Rechercher vos identifiants
- Générer des mots de passe sécurisés
- Sauvegarder de nouveaux identifiants

Installation :
1. Ouvrir Firefox
2. Aller dans about:debugging
3. Cliquer sur "Ce Firefox" (This Firefox)
4. Cliquer sur "Charger un module temporaire"
5. Sélectionner le fichier manifest.json de cette extension

Note: L'extension doit être rechargée à chaque redémarrage de Firefox
sauf si elle est signée par Mozilla.

Pour un usage permanent, vous devez :
- Signer l'extension via https://addons.mozilla.org
- Ou utiliser Firefox Developer Edition / Nightly avec extensions.webextensions.keepUuidOnUninstall=true
EOF

echo "✅ README créé"

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║          🎉 Extension prête à installer !        ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "📂 Emplacement de l'extension:"
echo "   $EXTENSION_DIR"
echo ""
echo "🔧 Installation dans Firefox :"
echo ""
echo "   Méthode 1 - Temporaire (recommandé pour le test) :"
echo "   ------------------------------------------------"
echo "   1. Ouvrir Firefox"
echo "   2. Aller dans: about:debugging#/runtime/this-firefox"
echo "   3. Cliquer sur 'Charger un module complémentaire temporaire...'"
echo "   4. Sélectionner: $EXTENSION_DIR/manifest.json"
echo ""
echo "   Méthode 2 - Via web-ext (pour le développement) :"
echo "   ------------------------------------------------"
echo "   cd $EXTENSION_DIR"
echo "   npx web-ext run"
echo ""
echo "   Méthode 3 - Permanent (nécessite signature Mozilla) :"
echo "   -----------------------------------------------------"
echo "   1. Créer un compte sur https://addons.mozilla.org"
echo "   2. Packager l'extension:"
echo "      cd $EXTENSION_DIR"
echo "      zip -r ../password-manager.xpi *"
echo "   3. Soumettre pour signature sur addons.mozilla.org"
echo ""
echo "⚠️  Important :"
echo "   - Le Native Messaging Host doit être installé"
echo "   - Lancez d'abord: cd .. && ./install_native_host.sh"
echo ""
echo "🧪 Test rapide :"
echo "   1. Installer l'extension (méthode 1 ou 2)"
echo "   2. Vérifier l'icône 🔐 dans la barre d'outils"
echo "   3. Cliquer dessus pour ouvrir le popup"
echo "   4. Le statut doit afficher 'Connecté' (point vert)"
echo ""
echo "📚 Documentation complète:"
echo "   $SCRIPT_DIR/README.md"
echo ""

# Proposer de lancer web-ext si disponible
if command -v npx &> /dev/null; then
    echo "💡 Voulez-vous lancer l'extension maintenant avec web-ext ? (o/N)"
    read -r response
    if [[ "$response" =~ ^[Oo]$ ]]; then
        echo ""
        echo "🚀 Lancement de Firefox avec l'extension..."
        cd "$EXTENSION_DIR"
        npx web-ext run
    fi
else
    echo "💡 Pour un développement plus facile, installez web-ext:"
    echo "   npm install -g web-ext"
    echo "   Puis lancez: cd $EXTENSION_DIR && web-ext run"
fi
