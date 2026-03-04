"""Configuration d'environnement partagée."""

from __future__ import annotations

import logging
import os
from pathlib import Path


def _env_to_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in ('1', 'true', 'yes')


logger = logging.getLogger(__name__)


def is_dev_mode() -> bool:
    """Indique si l'application tourne en mode développement."""
    return _env_to_bool(os.environ.get('DEV_MODE'))


def get_data_directory() -> Path:
    """Retourne le dossier de données selon l'environnement."""
    if is_dev_mode():
        dev_dir = Path(__file__).resolve().parent.parent / 'data'
        dev_dir.mkdir(parents=True, exist_ok=True)
        logger.info('DEVELOPMENT mode - Data directory: %s', dev_dir)
        return dev_dir

    prod_dir = Path('/var/lib/heelonvault-shared')
    prod_dir.mkdir(parents=True, exist_ok=True)
    logger.info('PRODUCTION mode - Data directory: %s', prod_dir)
    return prod_dir
