#!/usr/bin/env python3
"""
Migration multi-vault HeelonVault
==================================
Ajoute la table `vaults` dans users.db et crée un vault "Personal"
(is_default=True) pour chaque utilisateur existant, en réutilisant
son workspace_uuid comme UUID du vault.

Idempotent : peut être rejouée sans risque sur une base déjà migrée.

Usage
-----
    python scripts/migrate_to_multivault.py [--db /chemin/vers/users.db]

Si --db est absent, le chemin est détecté via src.config.environment
(respecte DEV_MODE et HEELONVAULT_DATA_DIR).
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap PYTHONPATH pour les imports src.*
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entrée principale
# ---------------------------------------------------------------------------

def run_migration(db_path: Path | None = None) -> None:
    """Exécute la migration multi-vault.

    Args:
        db_path: Chemin explicite vers users.db.
                 Si None, détecté via src.config.environment.
    """
    if db_path is None:
        from src.config.environment import get_data_directory  # noqa: PLC0415
        data_dir = get_data_directory()
        db_path = data_dir / "users.db"

    if not db_path.exists():
        logger.error("Fichier introuvable : %s", db_path)
        sys.exit(1)

    logger.info("=== Migration multi-vault démarrée ===")
    logger.info("Base de données : %s", db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        _create_vaults_table(conn)
        _migrate_users(conn)
        logger.info("=== Migration terminée avec succès ===")
    except Exception:
        logger.exception("Erreur inattendue — rollback")
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_vaults_table(conn: sqlite3.Connection) -> None:
    """Crée la table vaults et son index si absents."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vaults (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL
                            REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT    NOT NULL,
            uuid        TEXT    NOT NULL UNIQUE,
            is_default  BOOLEAN NOT NULL DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vaults_user_id ON vaults(user_id)"
    )
    conn.commit()
    logger.info("Table 'vaults' : vérifiée / créée.")


def _migrate_users(conn: sqlite3.Connection) -> None:
    """Crée un vault 'Personal' pour chaque utilisateur sans vault."""
    users = conn.execute(
        "SELECT id, username, workspace_uuid FROM users"
    ).fetchall()

    if not users:
        logger.info("Aucun utilisateur trouvé — rien à migrer.")
        return

    migrated = 0
    skipped_no_uuid = 0
    skipped_already_done = 0

    for user in users:
        user_id: int = user["id"]
        username: str = user["username"]
        workspace_uuid: str | None = user["workspace_uuid"]

        # Cas 1 : pas d'UUID dans users (compte legacy incomplet)
        if not workspace_uuid:
            logger.warning(
                "  [SKIP]  user=%r (id=%d) — workspace_uuid absent, ignoré.",
                username, user_id,
            )
            skipped_no_uuid += 1
            continue

        # Cas 2 : vault déjà présent pour cet UUID (idempotence)
        existing = conn.execute(
            "SELECT id FROM vaults WHERE uuid = ?", (workspace_uuid,)
        ).fetchone()

        if existing:
            logger.info(
                "  [SKIP]  user=%r (id=%d) — vault déjà migré (uuid=%s).",
                username, user_id, workspace_uuid,
            )
            skipped_already_done += 1
            continue

        # Cas 3 : migration effective
        conn.execute(
            """
            INSERT INTO vaults (user_id, name, uuid, is_default)
            VALUES (?, 'Personal', ?, 1)
            """,
            (user_id, workspace_uuid),
        )
        conn.commit()
        logger.info(
            "  [OK]    user=%r (id=%d) — vault 'Personal' créé (uuid=%s).",
            username, user_id, workspace_uuid,
        )
        migrated += 1

    logger.info(
        "Résumé : %d migré(s) | %d déjà migré(s) | %d sans UUID.",
        migrated, skipped_already_done, skipped_no_uuid,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migration multi-vault HeelonVault — ajoute la table vaults dans users.db"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        metavar="PATH",
        help="Chemin vers users.db (détecté automatiquement si absent)",
    )
    args = parser.parse_args()
    run_migration(args.db)
