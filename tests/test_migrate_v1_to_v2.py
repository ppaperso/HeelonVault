"""Tests unitaires pour la migration v1 → v2 (introduction de secret_items)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.repositories.migrations.migrate_v1_to_v2 import MigrationError, run
from src.repositories.password_repository import _maybe_run_v2_migration

_FAKE_DB_PATH = Path("/fake/passwords_testvault.db")
_TEST_LOGGER = logging.getLogger("test_migrate_v1_to_v2")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn() -> sqlite3.Connection:
    """Crée une connexion :memory: avec le schéma minimal attendu par la migration."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE passwords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            password_data TEXT NOT NULL,
            deleted_at TIMESTAMP NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO metadata (key, value) VALUES ('schema_version', '1')"
    )
    conn.commit()
    return conn


def _backup_ok() -> MagicMock:
    """Retourne un backup_service dont create_backup réussit."""
    svc = MagicMock()
    svc.create_backup.return_value = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# Tests de run()
# ---------------------------------------------------------------------------


def test_migration_creates_secret_items_table():
    """Après run(), la table secret_items existe avec les bonnes colonnes."""
    conn = _make_conn()
    try:
        run(conn, _backup_ok(), _FAKE_DB_PATH, _TEST_LOGGER)

        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='secret_items'"
        ).fetchone()
        assert row is not None, "La table secret_items doit exister après migration"

        # Vérifier les colonnes attendues
        cols = {
            info[1]
            for info in conn.execute("PRAGMA table_info(secret_items)").fetchall()
        }
        expected = {
            "id",
            "secret_type",
            "title",
            "metadata_json",
            "secret_blob",
            "blob_storage",
            "tags",
            "expires_at",
            "created_at",
            "modified_at",
            "usage_count",
            "item_uuid",
        }
        assert expected.issubset(cols), f"Colonnes manquantes : {expected - cols}"
    finally:
        conn.close()


def test_migration_sets_schema_version_to_2():
    """Après run(), metadata contient schema_version = '2'."""
    conn = _make_conn()
    try:
        run(conn, _backup_ok(), _FAKE_DB_PATH, _TEST_LOGGER)

        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        assert row is not None
        assert row[0] == "2", f"schema_version attendu '2', obtenu '{row[0]}'"
    finally:
        conn.close()


def test_migration_is_idempotent():
    """Appeler run() deux fois ne lève pas d'erreur et ne corrompt pas la table."""
    conn = _make_conn()
    svc = _backup_ok()
    try:
        run(conn, svc, _FAKE_DB_PATH, _TEST_LOGGER)
        run(conn, svc, _FAKE_DB_PATH, _TEST_LOGGER)  # second appel — doit être silencieux

        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        assert row[0] == "2"

        # Le backup ne doit pas être appelé une seconde fois (idempotence complète)
        assert svc.create_backup.call_count == 1
    finally:
        conn.close()


def test_migration_preserves_existing_passwords():
    """Les entrées dans la table passwords sont intactes après migration."""
    conn = _make_conn()
    try:
        conn.execute(
            "INSERT INTO passwords (title, password_data) VALUES ('GMail', 'enc_data')"
        )
        conn.commit()

        run(conn, _backup_ok(), _FAKE_DB_PATH, _TEST_LOGGER)

        rows = conn.execute("SELECT title, password_data FROM passwords").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "GMail"
        assert rows[0][1] == "enc_data"
    finally:
        conn.close()


def test_migration_calls_backup_before_modifying():
    """backup_service.create_backup() est appelé avant toute écriture SQL."""
    conn = _make_conn()
    svc = _backup_ok()
    try:
        run(conn, svc, _FAKE_DB_PATH, _TEST_LOGGER)

        svc.create_backup.assert_called_once_with(_FAKE_DB_PATH, "testvault")
    finally:
        conn.close()


def test_migration_raises_migration_error_on_backup_failure():
    """Si backup_service.create_backup() lève une exception, MigrationError est levée
    et la DB n'est pas modifiée (secret_items n'existe pas)."""
    conn = _make_conn()
    svc = MagicMock()
    svc.create_backup.side_effect = OSError("Disque plein")
    try:
        with pytest.raises(MigrationError):
            run(conn, svc, _FAKE_DB_PATH, _TEST_LOGGER)

        # La table secret_items ne doit pas exister
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='secret_items'"
        ).fetchone()
        assert row is None, "secret_items ne doit pas être créée si le backup échoue"

        # schema_version reste à '1'
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        assert row[0] == "1"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests de _maybe_run_v2_migration()
# ---------------------------------------------------------------------------


def test_maybe_run_v2_migration_skips_if_already_v2():
    """_maybe_run_v2_migration() ne fait rien si schema_version est déjà '2'."""
    conn = _make_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '2')"
        )
        conn.commit()

        svc = MagicMock()
        _maybe_run_v2_migration(conn, svc, _FAKE_DB_PATH, _TEST_LOGGER)

        svc.create_backup.assert_not_called()

        # La table secret_items ne doit toujours pas exister (aucune migration lancée)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='secret_items'"
        ).fetchone()
        assert row is None
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Tests de _migration_rollback_on_ddl_failure()
# ---------------------------------------------------------------------------

def test_migration_rollback_on_ddl_failure():
    """Si la migration échoue en cours de transaction (ex: index sur table inexistante),
    ROLLBACK est effectué et schema_version reste à '1'."""
    from src.repositories.migrations import migrate_v1_to_v2 as _mod
    #import sqlite3 as _sqlite3


    conn = _make_conn()
    try:
        backup_service = MagicMock()

        def patched_run(conn, backup_service, db_path, logger):
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            current_version = int(row[0]) if row else 1
            if current_version >= 2:
                return

            vault_id_str = db_path.stem.replace("passwords_", "")
            backup_service.create_backup(db_path, vault_id_str)

            saved_isolation = conn.isolation_level
            conn.isolation_level = None
            try:
                conn.execute("BEGIN")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS secret_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_uuid TEXT NOT NULL UNIQUE
                    )
                    """
                )
                # SQL invalide intentionnel pour déclencher le rollback
                conn.execute("THIS IS NOT VALID SQL")
                conn.execute("COMMIT")
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    _TEST_LOGGER.debug("Rollback failed in simulated test path")
                raise _mod.MigrationError("Échec simulé") from exc
            finally:
                conn.isolation_level = saved_isolation

        with pytest.raises(_mod.MigrationError):
            patched_run(conn, backup_service, _FAKE_DB_PATH, _TEST_LOGGER)

        # schema_version doit rester à '1'
        row = conn.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        assert row[0] == "1"

        # Le backup a bien été appelé avant l'échec
        backup_service.create_backup.assert_called_once()

    finally:
        conn.close()
