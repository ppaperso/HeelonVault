#!/bin/bash
# Script pour signer l'extension avec web-ext

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_DIR="$SCRIPT_DIR/firefox_extension"

echo "╔════════════════════════════════════════════════════╗"
echo "║   🔏 Signature de l'extension avec web-ext      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Vérifier si web-ext est installé
if ! command -v web-ext &> /dev/null && ! command -v npx &> /dev/null; then
    echo "❌ Erreur: ni web-ext ni npx ne sont installés"
    echo ""
    echo "📦 Installation requise:"
    echo "   Option 1 - Installer web-ext globalement:"
    echo "   npm install -g web-ext"
    echo ""
    echo "   Option 2 - Installer npm (npx sera inclus):"
    echo "   sudo dnf install npm"
    echo ""
    exit 1
fi

# Demander les clés API
echo "🔑 Configuration des clés API"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -f "$SCRIPT_DIR/.webext-credentials" ]; then
    echo "📋 Fichier de credentials trouvé: .webext-credentials"
    echo ""
    echo "Voulez-vous utiliser les credentials sauvegardées ? (o/N)"
    read -r use_saved
    
    if [[ "$use_saved" =~ ^[Oo]$ ]]; then
        source "$SCRIPT_DIR/.webext-credentials"
        echo "✅ Credentials chargées"
    else
        rm "$SCRIPT_DIR/.webext-credentials"
    fi
fi

if [ -z "$JWT_ISSUER" ] || [ -z "$JWT_SECRET" ]; then
    echo "Pour obtenir vos clés API:"
    echo "1. Aller sur: https://addons.mozilla.org/developers/addon/api/key/"
    echo "2. Cliquer sur 'Generate new credentials'"
    echo "3. Copier les valeurs ci-dessous"
    echo ""
    
    echo "JWT Issuer (user:xxxxx:xxx):"
    read -r JWT_ISSUER
    echo ""
    
    echo "JWT Secret:"
    read -rs JWT_SECRET
    echo ""
    
    # Proposer de sauvegarder
    echo ""
    echo "💾 Voulez-vous sauvegarder ces credentials pour plus tard ? (o/N)"
    echo "   (Stocké dans .webext-credentials - à ne pas committer !)"
    read -r save_creds
    
    if [[ "$save_creds" =~ ^[Oo]$ ]]; then
        cat > "$SCRIPT_DIR/.webext-credentials" << EOF
# Credentials pour web-ext sign
# NE PAS COMMITTER CE FICHIER !
export JWT_ISSUER="$JWT_ISSUER"
export JWT_SECRET="$JWT_SECRET"
EOF
        chmod 600 "$SCRIPT_DIR/.webext-credentials"
        
        # Ajouter au .gitignore
        if [ -f "$SCRIPT_DIR/../.gitignore" ]; then
            if ! grep -q ".webext-credentials" "$SCRIPT_DIR/../.gitignore"; then
                echo "browser_integration/.webext-credentials" >> "$SCRIPT_DIR/../.gitignore"
            fi
        fi
        
        echo "✅ Credentials sauvegardées dans .webext-credentials"
    fi
fi

echo ""
echo "🚀 Signature de l'extension..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$EXTENSION_DIR"

# Utiliser web-ext ou npx
if command -v web-ext &> /dev/null; then
    WEB_EXT_CMD="web-ext"
else
    WEB_EXT_CMD="npx web-ext"
    echo "📦 Utilisation de npx (téléchargement de web-ext...)"
fi

# Signer avec unlisted (pas de listing public)
echo "⏳ Signature en cours (peut prendre 2-5 minutes)..."
echo ""

$WEB_EXT_CMD sign \
    --api-key="$JWT_ISSUER" \
    --api-secret="$JWT_SECRET" \
    --channel=unlisted \
    --artifacts-dir="$EXTENSION_DIR/web-ext-artifacts"

if [ $? -eq 0 ]; then
    echo ""
    echo "╔════════════════════════════════════════════════════╗"
    echo "║           ✅ SIGNATURE RÉUSSIE !                  ║"
    echo "╚════════════════════════════════════════════════════╝"
    echo ""
    
    # Trouver le fichier .xpi créé
    XPI_FILE=$(find "$EXTENSION_DIR/web-ext-artifacts" -name "*.xpi" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    
    if [ -n "$XPI_FILE" ]; then
        echo "📦 Extension signée créée:"
        echo "   $XPI_FILE"
        echo ""
        
        SIZE=$(du -h "$XPI_FILE" | cut -f1)
        echo "📊 Taille: $SIZE"
        echo ""
        
        echo "🚀 Installation:"
        echo ""
        echo "   Méthode 1 - Ligne de commande:"
        echo "   firefox \"$XPI_FILE\""
        echo ""
        echo "   Méthode 2 - Glisser-déposer:"
        echo "   Glissez le fichier .xpi dans Firefox"
        echo ""
        echo "   Méthode 3 - Menu Firefox:"
        echo "   Outils > Add-ons > ⚙️ > Install Add-on From File..."
        echo ""
        
        echo "✨ L'extension sera PERMANENTE après installation !"
        echo ""
        
        # Proposer d'installer directement
        echo "Voulez-vous installer l'extension maintenant ? (o/N)"
        read -r install_now
        
        if [[ "$install_now" =~ ^[Oo]$ ]]; then
            if command -v firefox &> /dev/null; then
                firefox "$XPI_FILE" &
                echo "🦊 Firefox lancé avec l'extension"
            else
                echo "❌ Firefox non trouvé dans le PATH"
            fi
        fi
    else
        echo "⚠️  Fichier .xpi non trouvé dans web-ext-artifacts/"
    fi
else
    echo ""
    echo "❌ Erreur lors de la signature"
    echo ""
    echo "Causes possibles:"
    echo "  - Clés API incorrectes"
    echo "  - Problème de connexion internet"
    echo "  - Extension déjà soumise avec cette version"
    echo ""
    echo "Solution:"
    echo "  - Vérifier vos clés sur https://addons.mozilla.org/developers/addon/api/key/"
    echo "  - Incrémenter la version dans manifest.json"
    echo "  - Réessayer dans quelques minutes"
fi
