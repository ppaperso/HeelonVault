#!/bin/bash
# Script de lancement de l'application HeelonVault (production)

set -e

# Assurer que les fichiers créés sont group-writable
umask 002

APP_DIR="/opt/heelonvault"
VENV_DIR="${APP_DIR}/venv"
VENV_PYTHON="${VENV_DIR}/bin/python3"
APP_FILE="${APP_DIR}/heelonvault.py"
REQ_FILE="${APP_DIR}/requirements.txt"

if [ ! -x "$VENV_PYTHON" ]; then
	echo "❌ Environnement de production introuvable: ${VENV_PYTHON}"
	exit 1
fi

if [ ! -f "$APP_FILE" ]; then
	echo "❌ Fichier application introuvable: ${APP_FILE}"
	exit 1
fi

if [ -f "$REQ_FILE" ]; then
	echo "🔄 Synchronisation des dépendances de production..."
	"$VENV_PYTHON" -m pip install --upgrade pip
	"$VENV_PYTHON" -m pip install -r "$REQ_FILE"
fi

"$VENV_PYTHON" "$APP_FILE"
