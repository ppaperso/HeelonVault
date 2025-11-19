#!/bin/bash
# Script de lancement du container avec Podman

set -e

IMAGE_NAME="password-manager"
IMAGE_TAG="latest"
CONTAINER_NAME="password-manager-app"

# Créer le répertoire pour les données persistantes si inexistant
DATA_DIR="${HOME}/.local/share/passwordmanager-container"
mkdir -p "${DATA_DIR}"

echo "🔐 Lancement du gestionnaire de mots de passe..."
echo ""

# Vérifier si le container existe déjà
if podman ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "⚠️  Le container existe déjà. Suppression..."
    podman rm -f ${CONTAINER_NAME} 2>/dev/null || true
fi

# Lancer le container avec accès X11
podman run -it --rm \
    --name ${CONTAINER_NAME} \
    --network host \
    --security-opt label=type:container_runtime_t \
    -e DISPLAY="${DISPLAY}" \
    -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY}" \
    -e XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}:${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}:rw" 2>/dev/null || true \
    -v "${DATA_DIR}:/data:Z" \
    --device /dev/dri \
    ${IMAGE_NAME}:${IMAGE_TAG}

echo ""
echo "✅ Application terminée."
