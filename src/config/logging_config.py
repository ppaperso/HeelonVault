"""Configuration partagee du systeme de logs"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from .environment import is_dev_mode

LOG_PREFIX = "password_manager"
KEEP_LOG_FILES = 7
FALLBACK_DIR = Path("/tmp/password_manager_logs")


def _get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_target_directory() -> Path:
    if is_dev_mode():
        return _get_project_root() / "logs"
    return Path("/var/log/password_manager")


def _ensure_directory(path: Path) -> tuple[Path, str | None]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path, None
    except Exception as exc:
        fallback = FALLBACK_DIR
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback, str(exc)


def _rotate_logs(log_dir: Path, keep_files: int) -> list[str]:
    log_files = sorted(
        [p for p in log_dir.glob(f"{LOG_PREFIX}_*.log") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    removed: list[str] = []
    now = datetime.now()
    for index, path in enumerate(log_files):
        age_days = (now - datetime.fromtimestamp(path.stat().st_mtime)).days
        if index >= keep_files or age_days >= keep_files:
            try:
                removed.append(path.name)
                path.unlink()
            except OSError:
                continue
    return removed


def configure_logging() -> None:
    """Configure logging avec rotation quotidienne"""
    log_dir = _get_target_directory()
    fallback_reason = None

    log_dir, fallback_reason = _ensure_directory(log_dir)

    today = datetime.now().date()
    log_filename = log_dir / f"{LOG_PREFIX}_{today.strftime('%Y%m%d')}.log"
    level = logging.DEBUG if is_dev_mode() else logging.INFO

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError:
        root_logger.warning("Impossible d'ouvrir le fichier de log %s", log_filename)

    removed_logs = _rotate_logs(log_dir, KEEP_LOG_FILES)

    root_logger.info(
        "Logging initialise (mode=%s) dans %s",
        "DEV" if is_dev_mode() else "PROD",
        log_dir,
    )

    if fallback_reason:
        root_logger.warning(
            "Repertoire de log par defaut indisponible (%s), redirige vers %s",
            fallback_reason,
            log_dir,
        )

    if removed_logs:
        root_logger.debug("Anciennes traces supprimées : %s", ", ".join(removed_logs))
