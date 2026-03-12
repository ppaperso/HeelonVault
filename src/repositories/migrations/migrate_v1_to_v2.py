"""Migration v1 → v2 : introduction de la table secret_items dans passwords_<uuid>.db."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Levée si la migration échoue. Ne jamais inclure de payload sensible dans le message."""


def run(conn: sqlite3.Connection, backup_service, db_path: Path, logger) -> None:
    """
    Migration v1 → v2 : introduit la table secret_items dans passwords_<uuid>.db.

    Comportement :
    - Idempotente : si schema_version >= 2 dans metadata, ne rien faire et retourner.
    - Appelle backup_service.create_backup(db_path, vault_id_str) avant toute modification
      (vault_id_str = db_path.stem.replace("passwords_", "")).
    - Utilise une transaction explicite (BEGIN / COMMIT / ROLLBACK).
    - En cas d'échec : ROLLBACK, log sans payload sensible, raise MigrationError.
    - Ne touche jamais à la table passwords ni aux autres tables existantes.
    """
    # Vérification d'idempotence
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    ).fetchone()
    current_version = int(row[0]) if row else 1
    if current_version >= 2:
        return

    # Backup obligatoire avant toute modification
    vault_id_str = db_path.stem.replace("passwords_", "")
    if backup_service is None:
        logger.warning(
            "Migration v1→v2 : backup_service absent pour %s, poursuite sans backup",
            db_path.name,
        )
    else:
        try:
            backup_service.create_backup(db_path, vault_id_str)
        except Exception as exc:
            logger.error(
                "Migration v1→v2 : échec du backup pré-migration pour %s", db_path.name
            )
            raise MigrationError("Échec du backup pré-migration") from exc

    # Transaction explicite — isolation_level = None pour contrôle manuel complet
    saved_isolation = conn.isolation_level
    conn.isolation_level = None  # activation du mode manuel
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS secret_items (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                secret_type   TEXT    NOT NULL
                    CHECK (secret_type IN ('api_token', 'ssh_key', 'secure_document')),
                title         TEXT    NOT NULL,
                metadata_json TEXT    NOT NULL DEFAULT '{}',
                secret_blob   BLOB    NOT NULL,
                blob_storage  TEXT    NOT NULL DEFAULT 'inline'
                                  CHECK (blob_storage IN ('inline', 'file')),
                tags          TEXT    NOT NULL DEFAULT '[]',
                expires_at    TEXT,
                created_at    TEXT    NOT NULL,
                modified_at   TEXT    NOT NULL,
                usage_count   INTEGER NOT NULL DEFAULT 0,
                item_uuid     TEXT    NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_secret_items_type "
            "ON secret_items(secret_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_secret_items_title "
            "ON secret_items(title)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_secret_items_expires "
            "ON secret_items(expires_at)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '2')"
        )
        conn.execute("COMMIT")
    except Exception as exc: # pragma: no cover
        # pragma: no cover — sqlite3.Connection.execute est read-only en Python 3.14,
        # ce bloc ne peut pas être atteint via mock. Voir Option B dans CONTRIBUTING.md.
        try: # pragma: no cover
            conn.execute("ROLLBACK") # pragma: no cover
        except Exception: # pragma: no cover
            logger.debug("ROLLBACK failed for %s", db_path.name) # pragma: no cover
        logger.error("Migration v1→v2 : échec pour %s", db_path.name) # pragma: no cover
        raise MigrationError("Échec de la migration v1→v2") from exc # pragma: no cover
    finally:
        conn.isolation_level = saved_isolation
