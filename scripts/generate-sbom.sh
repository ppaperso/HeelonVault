#!/usr/bin/env bash
# scripts/generate-sbom.sh
# Génère le SBOM CycloneDX 1.4 JSON à la racine du projet.
#
# Prérequis : cargo install cargo-cyclonedx
# Usage     : ./scripts/generate-sbom.sh
#
# À exécuter localement après tout ajout ou mise à jour de dépendance,
# puis committer sbom.cyclonedx.json avant de pousser.
# Le CI (job check-sbom) échoue si le fichier commité est obsolète.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if ! command -v cargo-cyclonedx &>/dev/null; then
    echo "[SBOM] cargo-cyclonedx not found — installing..."
    cargo install cargo-cyclonedx
fi

echo "[SBOM] Generating sbom.cyclonedx.json..."
cargo cyclonedx \
    --format json \
    --spec-version 1.4 \
    --override-filename sbom.cyclonedx

COMPONENT_COUNT=$(jq '.components | length' sbom.cyclonedx.json)
echo "[SBOM] Done — ${COMPONENT_COUNT} components inventoried."
echo "[SBOM] Next step: commit sbom.cyclonedx.json if dependencies changed."
