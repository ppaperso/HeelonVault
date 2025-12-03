#!/bin/bash
# Wrapper DEV pour le native messaging host
# Utilise l'environnement de développement (venv-dev, src/data/)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# Forcer le mode développement
export DEV_MODE=1

# Détecter le venv de développement
if [ -d "$APP_DIR/venv-dev" ]; then
    VENV="$APP_DIR/venv-dev"
elif [ -d "$APP_DIR/venv" ]; then
    VENV="$APP_DIR/venv"
else
    echo '{"status":"error","error":"Aucun venv trouvé"}' >&2
    exit 1
fi

# Lancer le native host en mode dev
exec "$VENV/bin/python3" "$SCRIPT_DIR/native_host.py" "$@"
