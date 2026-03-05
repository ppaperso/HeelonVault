#!/bin/bash
# =============================================================================
# build-and-sign.sh — Build, tag et signature cosign de l'image HeelonVault
#
# Prérequis :
#   - podman installé
#   - cosign installé (https://docs.sigstore.dev/cosign/installation/)
#   - Être connecté au registry : podman login ghcr.io
#
# Usage :
#   ./build-and-sign.sh [VERSION]
#   ./build-and-sign.sh 1.0.0
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTAINERFILE_PATH="${SCRIPT_DIR}/Containerfile"
CONTAINER_IGNOREFILE="${SCRIPT_DIR}/.containerignore"
VCS_REF="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
SECURITY_POLICY_URL="https://github.com/heelonys/heelonvault/blob/main/SECURITY.md"
SBOM_PROVENANCE="syft-spdx-json+cosign-attach"

# --- Configuration -----------------------------------------------------------
REGISTRY="ghcr.io/heelonys"
IMAGE_NAME="heelonvault"
VERSION="${1:-$(date +%Y%m%d)}"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}"

echo "🔨 Build HeelonVault ${VERSION}"
echo "================================================="

# --- Build multi-stage -------------------------------------------------------
echo "📦 Building image..."
podman build \
  --file "${CONTAINERFILE_PATH}" \
  --ignorefile "${CONTAINER_IGNOREFILE}" \
  --pull=always \
  --tag "${FULL_IMAGE}:${VERSION}" \
  --tag "${FULL_IMAGE}:latest" \
  --build-arg VCS_REF="${VCS_REF}" \
  --build-arg SECURITY_POLICY_URL="${SECURITY_POLICY_URL}" \
  --build-arg SBOM_PROVENANCE="${SBOM_PROVENANCE}" \
  --label "org.opencontainers.image.version=${VERSION}" \
  --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "${REPO_ROOT}"

echo "✅ Image built: ${FULL_IMAGE}:${VERSION}"

# --- Inspection de la taille -------------------------------------------------
echo ""
echo "📊 Image size:"
podman image inspect "${FULL_IMAGE}:${VERSION}" \
  --format "{{.Size}}" | numfmt --to=iec

# --- Push --------------------------------------------------------------------
echo ""
echo "📤 Pushing to registry..."
podman push "${FULL_IMAGE}:${VERSION}"
podman push "${FULL_IMAGE}:latest"

# --- Signature cosign --------------------------------------------------------
echo ""
echo "🔐 Signing with cosign (keyless via Sigstore)..."
cosign sign \
  --yes \
  "${FULL_IMAGE}:${VERSION}"

echo ""
echo "✅ Image signed: ${FULL_IMAGE}:${VERSION}"

# --- Génération SBOM ---------------------------------------------------------
echo ""
echo "📋 Generating SBOM..."
if command -v syft &> /dev/null; then
  syft "${FULL_IMAGE}:${VERSION}" \
    -o spdx-json \
    > "${SCRIPT_DIR}/heelonvault-${VERSION}-sbom.spdx.json"

  # Attacher le SBOM à l'image
  cosign attach sbom \
    --sbom "${SCRIPT_DIR}/heelonvault-${VERSION}-sbom.spdx.json" \
    "${FULL_IMAGE}:${VERSION}"

  echo "✅ SBOM attached: ${SCRIPT_DIR}/heelonvault-${VERSION}-sbom.spdx.json"
else
  echo "⚠️  syft non installé — SBOM ignoré (https://github.com/anchore/syft)"
fi

echo ""
echo "================================================="
echo "✅ Done: ${FULL_IMAGE}:${VERSION}"
echo ""
echo "Vérification de la signature :"
echo "  cosign verify ${FULL_IMAGE}:${VERSION} --certificate-identity-regexp='.*' --certificate-oidc-issuer='https://token.actions.githubusercontent.com'"
