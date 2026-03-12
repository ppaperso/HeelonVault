"""Tests unitaires pour SecretRepository (table secret_items)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models.secret_item import SecretItem
from src.repositories.migrations.migrate_v1_to_v2 import run as migrate_v1_to_v2
from src.repositories.secret_repository import SecretRepository


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Crée une base vault minimale (v1) sur disque pour tests repository."""
    path = tmp_path / "passwords_testvault.db"
    conn = sqlite3.connect(str(path))
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
    conn.execute("INSERT INTO metadata (key, value) VALUES ('schema_version', '1')")
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def migrated_db_path(db_path: Path) -> Path:
    """Applique la migration v1→v2 sur la DB de test."""
    conn = sqlite3.connect(str(db_path))
    backup_service = MagicMock()
    backup_service.create_backup.return_value = db_path.parent / "backup_pre_migration.db"
    migrate_v1_to_v2(conn, backup_service, db_path, MagicMock())
    conn.close()
    return db_path


@pytest.fixture()
def repo(migrated_db_path: Path) -> Iterator[SecretRepository]:
    """Repository prêt sur une DB déjà migrée v2."""
    repository = SecretRepository(migrated_db_path)
    yield repository
    repository.close()


def _make_item(**overrides) -> SecretItem:
    base = SecretItem(
        secret_type="api_token",
        title="GitHub Token",
        metadata={"provider": "github", "environment": "prod", "scopes": ["repo"]},
        payload=b"enc_payload_blob",
        tags=["work", "gh"],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_create_and_get_item(repo: SecretRepository) -> None:
    created = repo.create_item(_make_item())

    assert created.id is not None
    assert created.item_uuid

    fetched = repo.get_item(created.id)
    assert fetched is not None
    assert fetched.title == "GitHub Token"
    assert fetched.secret_type == "api_token"
    assert fetched.metadata["provider"] == "github"


def test_get_item_by_uuid_is_stable(repo: SecretRepository) -> None:
    created = repo.create_item(_make_item())

    fetched = repo.get_item_by_uuid(created.item_uuid or "")
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.item_uuid == created.item_uuid


def test_list_items_filters_by_type_and_search(repo: SecretRepository) -> None:
    repo.create_item(_make_item(title="GitHub Prod", secret_type="api_token"))
    repo.create_item(_make_item(title="Serveur SSH", secret_type="ssh_key"))

    api_only = repo.list_items(secret_type="api_token")
    assert len(api_only) == 1
    assert api_only[0].secret_type == "api_token"

    search = repo.list_items(search_text="Serveur")
    assert len(search) == 1
    assert search[0].title == "Serveur SSH"


def test_update_item_persists_changes(repo: SecretRepository) -> None:
    created = repo.create_item(_make_item())
    created.title = "GitHub Token Updated"
    created.metadata = {"provider": "github", "environment": "staging", "scopes": ["repo"]}
    created.tags = ["updated"]

    updated = repo.update_item(created)
    assert updated.title == "GitHub Token Updated"
    assert updated.metadata["environment"] == "staging"
    assert updated.tags == ["updated"]


def test_delete_item_removes_row(repo: SecretRepository) -> None:
    created = repo.create_item(_make_item())
    deleted = repo.delete_item(created.id or -1)

    assert deleted is True
    assert repo.get_item(created.id or -1) is None


def test_record_usage_increments_counter(repo: SecretRepository) -> None:
    created = repo.create_item(_make_item())
    repo.record_usage(created.id or -1, amount=3)

    fetched = repo.get_item(created.id or -1)
    assert fetched is not None
    assert fetched.usage_count == 3


def test_defaults_blob_storage_and_tags(repo: SecretRepository) -> None:
    created = repo.create_item(
        SecretItem(
            secret_type="api_token",
            title="No tags",
            metadata={"provider": "x", "environment": "dev", "scopes": []},
            payload=b"enc",
        )
    )

    fetched = repo.get_item(created.id or -1)
    assert fetched is not None
    assert fetched.blob_storage == "inline"
    assert fetched.tags == []


def test_secret_item_repr_never_leaks_payload(repo: SecretRepository) -> None:
    created = repo.create_item(_make_item(payload="super-secret-token"))
    fetched = repo.get_item(created.id or -1)
    assert fetched is not None

    rendered = repr(fetched)
    assert "super-secret-token" not in rendered
    assert "payload=" not in rendered


def test_secret_item_clear_payload() -> None:
    item = _make_item(payload="sensitive")
    item.clear_payload()
    assert item.payload == ""
