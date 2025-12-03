#!/bin/bash
# Wrapper PRODUCTION pour le native messaging host
# Utilise l'environnement de production (venv, data/)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# Mode production (pas de DEV_MODE)
export DEV_MODE=0

# Détecter le venv de production
if [ -d "$APP_DIR/venv" ]; then
    VENV="$APP_DIR/venv"
elif [ -d "$APP_DIR/venv-dev" ]; then
    VENV="$APP_DIR/venv-dev"
else
    echo '{"status":"error","error":"Aucun venv trouvé"}' >&2
    exit 1
fi

# Activer le venv et lancer le script
exec "$VENV/bin/python3" "$SCRIPT_DIR/native_host.py" "$@"
