#!/bin/bash
# Installation du Native Messaging Host pour Firefox et Chrome/Chromium

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
HOST_NAME="com.passwordmanager.native"

# Détecter l'environnement (dev ou production)
if [ -d "$APP_DIR/venv-dev" ]; then
    VENV_DIR="$APP_DIR/venv-dev"
    ENV_NAME="DÉVELOPPEMENT"
elif [ -d "$APP_DIR/venv" ]; then
    VENV_DIR="$APP_DIR/venv"
    ENV_NAME="PRODUCTION"
else
    echo "❌ Aucun environnement virtuel trouvé (venv-dev ou venv)"
    exit 1
fi

echo "🔧 Installation du Native Messaging Host"
echo "=========================================="
echo "🔍 Environnement détecté: $ENV_NAME"
echo "📦 Venv: $VENV_DIR"
echo ""

# Vérifier que Python est disponible
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé"
    exit 1
fi

# Vérifier que le venv existe
if [ ! -f "$VENV_DIR/bin/python3" ]; then
    echo "❌ Environnement virtuel non trouvé: $VENV_DIR"
    exit 1
fi

# Rendre le script Python exécutable
chmod +x "$SCRIPT_DIR/native_host.py"
echo "✅ Script Python rendu exécutable"

# Créer un wrapper qui utilise le bon venv
WRAPPER_SCRIPT="$SCRIPT_DIR/native_host_wrapper.sh"
cat > "$WRAPPER_SCRIPT" << 'WRAPPER_EOF'
#!/bin/bash
# Wrapper pour utiliser le bon environnement virtuel
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# Détecter le venv approprié
if [ -d "$APP_DIR/venv-dev" ]; then
    VENV="$APP_DIR/venv-dev"
elif [ -d "$APP_DIR/venv" ]; then
    VENV="$APP_DIR/venv"
else
    echo '{"status":"error","error":"Aucun venv trouvé"}' >&2
    exit 1
fi

# Activer le venv et lancer le script
exec "$VENV/bin/python3" "$SCRIPT_DIR/native_host.py" "$@"
WRAPPER_EOF

chmod +x "$WRAPPER_SCRIPT"
echo "✅ Wrapper créé: $WRAPPER_SCRIPT"

# Créer le manifeste Firefox
FIREFOX_DIR="$HOME/.mozilla/native-messaging-hosts"
mkdir -p "$FIREFOX_DIR"

cat > "$FIREFOX_DIR/$HOST_NAME.json" << EOF
{
  "name": "$HOST_NAME",
  "description": "Native messaging host pour Password Manager",
  "path": "$WRAPPER_SCRIPT",
  "type": "stdio",
  "allowed_extensions": [
    "password-manager@example.com"
  ]
}
EOF

echo "✅ Manifeste Firefox installé: $FIREFOX_DIR/$HOST_NAME.json"

# Créer le manifeste Chrome/Chromium
CHROME_DIR="$HOME/.config/google-chrome/NativeMessagingHosts"
CHROMIUM_DIR="$HOME/.config/chromium/NativeMessagingHosts"

for DIR in "$CHROME_DIR" "$CHROMIUM_DIR"; do
    if [ -d "$(dirname "$DIR")" ]; then
        mkdir -p "$DIR"
        
        cat > "$DIR/$HOST_NAME.json" << EOF
{
  "name": "$HOST_NAME",
  "description": "Native messaging host pour Password Manager",
  "path": "$WRAPPER_SCRIPT",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://[EXTENSION_ID]/"
  ]
}
EOF
        
        echo "✅ Manifeste Chrome installé: $DIR/$HOST_NAME.json"
    fi
done

# Créer le répertoire de logs
LOG_DIR="$HOME/.local/share/passwordmanager"
mkdir -p "$LOG_DIR"
echo "✅ Répertoire de logs créé: $LOG_DIR"

echo ""
echo "✅ Installation terminée!"
echo ""
echo "📝 Prochaines étapes:"
echo "   1. Installer l'extension navigateur"
echo "   2. Remplacer [EXTENSION_ID] dans les manifestes par l'ID réel"
echo "   3. Tester avec: ./test_native_host.sh"
echo ""
echo "📂 Emplacements des fichiers:"
echo "   Wrapper:  $WRAPPER_SCRIPT"
echo "   Script:   $SCRIPT_DIR/native_host.py"
echo "   Venv:     $VENV_DIR"
echo ""
echo "📂 Manifestes installés:"
echo "   Firefox: $FIREFOX_DIR/$HOST_NAME.json"
[ -d "$CHROME_DIR" ] && echo "   Chrome:  $CHROME_DIR/$HOST_NAME.json"
[ -d "$CHROMIUM_DIR" ] && echo "   Chromium: $CHROMIUM_DIR/$HOST_NAME.json"
