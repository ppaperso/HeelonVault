#!/usr/bin/env bash
set -euo pipefail

# Vérifie que la configuration de logs crée les fichiers au bon endroit
# et que la rotation conserve uniquement les 7 dernières traces.

# ⚠️ SÉCURITÉ: Forcer le mode développement pour les tests
export DEV_MODE=1

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS SUR ENVIRONNEMENT DE DÉVELOPPEMENT    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔒 Mode DEV activé: DEV_MODE=$DEV_MODE"
echo "📂 Données de test: src/data/"
echo ""

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
KEEP_COUNT=7
ITERATIONS=$((KEEP_COUNT + 2))

rm -rf "${LOG_DIR}"
mkdir -p "${LOG_DIR}"

export PYTHONPATH="${ROOT_DIR}"

declare -a created_logs=()

for i in $(seq 1 "${ITERATIONS}"); do
    ITERATION="${i}" python - <<'PY'
import os
import logging
from src.config.logging_config import configure_logging

configure_logging()
logging.getLogger(__name__).info(
    "Test de rotation des logs - iteration %s", os.environ["ITERATION"]
)
PY
    # Assurer des noms de fichiers uniques (suffixe seconde)
    sleep 1
    newest=$(ls -1t "${LOG_DIR}"/password_manager_*.log | head -n 1)
    created_logs+=("${newest}")
    echo "Création du log: ${newest}"
done

log_count=$(find "${LOG_DIR}" -maxdepth 1 -name 'password_manager_*.log' | wc -l)
if [[ "${log_count}" -ne "${KEEP_COUNT}" ]]; then
    echo "ÉCHEC: ${log_count} fichiers trouvés, ${KEEP_COUNT} attendus" >&2
    exit 1
fi

if [[ -e "${created_logs[0]}" || -e "${created_logs[1]}" ]]; then
    echo "ÉCHEC: les plus anciens fichiers existent toujours, la rotation ne fonctionne pas" >&2
    exit 1
fi

echo "✅ Rotation OK (${log_count} fichiers dans ${LOG_DIR})"
