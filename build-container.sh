#!/bin/bash
# Script de build du container avec Podman

set -e

IMAGE_NAME="password-manager"
IMAGE_TAG="latest"

echo "🐋 Construction de l'image du gestionnaire de mots de passe..."
echo "📦 Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

# Build avec Podman
podman build \
    --tag ${IMAGE_NAME}:${IMAGE_TAG} \
    --format docker \
    --layers \
    .

echo ""
echo "✅ Image construite avec succès !"
echo ""
echo "📊 Informations sur l'image:"
podman images ${IMAGE_NAME}:${IMAGE_TAG}

echo ""
echo "🚀 Pour lancer l'application, utilisez:"
echo "   ./run-container.sh"
