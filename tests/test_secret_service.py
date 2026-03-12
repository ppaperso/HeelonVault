"""Tests unitaires du SecretService (API minimale Day-1/Etape 3)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.repositories.migrations.migrate_v1_to_v2 import run as migrate_v1_to_v2
from src.repositories.secret_repository import SecretRepository
from src.services.crypto_service import CryptoService
from src.services.secret_service import SecretService


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
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
def service(db_path: Path) -> Iterator[SecretService]:
    conn = sqlite3.connect(str(db_path))
    backup_service = MagicMock()
    backup_service.create_backup.return_value = db_path.parent / "backup_pre_migration.db"
    migrate_v1_to_v2(conn, backup_service, db_path, MagicMock())
    conn.close()

    repository = SecretRepository(db_path)
    crypto = CryptoService("MasterPassword!Step3")
    svc = SecretService(repository, crypto)
    yield svc
    svc.close()


def test_create_api_token_and_reveal(service: SecretService) -> None:
    created = service.create_api_token(
        title="GitHub",
        token="ghp_1234567890",
        metadata={"provider": "github", "environment": "prod", "scopes": ["repo"]},
    )

    assert created.id is not None
    assert created.item_uuid
    assert created.payload == ""

    token = service.reveal_api_token(created.id)
    assert token == "ghp_1234567890"


def test_create_api_token_generates_token_hint(service: SecretService) -> None:
    created = service.create_api_token(
        title="AWS",
        token="aws-secret-token",
        metadata={"provider": "aws", "environment": "dev", "scopes": []},
    )

    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.metadata["token_hint"] == "****oken"


def test_reveal_increments_usage_count(service: SecretService) -> None:
    created = service.create_api_token(
        title="Stripe",
        token="sk_live_secret",
        metadata={"provider": "stripe", "environment": "prod", "scopes": ["rw"]},
    )

    service.reveal_api_token(created.id or -1)
    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.usage_count == 1


def test_get_item_by_uuid_returns_item(service: SecretService) -> None:
    created = service.create_api_token(
        title="Datadog",
        token="dd_secret",
        metadata={"provider": "datadog", "environment": "staging", "scopes": ["read"]},
    )

    item = service.get_item_by_uuid(created.item_uuid or "")
    assert item is not None
    assert item.id == created.id
    assert item.payload == ""


def test_delete_secret_removes_item(service: SecretService) -> None:
    created = service.create_api_token(
        title="Delete me",
        token="to_delete",
        metadata={"provider": "x", "environment": "other", "scopes": []},
    )

    service.delete_secret(created.id or -1)
    assert service.get_item(created.id or -1) is None


def test_get_expiring_soon_filters_deadline(service: SecretService) -> None:
    created = service.create_api_token(
        title="Near expiry",
        token="expiring_soon",
        metadata={"provider": "x", "environment": "prod", "scopes": []},
    )

    repo_item = service.repository.get_item(created.id or -1)
    assert repo_item is not None
    repo_item.expires_at = repo_item.created_at
    service.repository.update_item(repo_item)

    expiring = service.get_expiring_soon(days=1)
    assert any(item.id == created.id for item in expiring)


def test_create_api_token_rejects_invalid_metadata(service: SecretService) -> None:
    with pytest.raises(ValueError):
        service.create_api_token(
            title="Invalid",
            token="abc",
            metadata={"provider": "", "environment": "prod", "scopes": []},
        )

    created = service.create_api_token(
        title="Valid alias",
        token="abc",
        metadata={"provider": "x", "environment": "production", "scopes": []},
    )
    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.metadata["environment"] == "prod"

    created_upper = service.create_api_token(
        title="Valid uppercase alias",
        token="abc",
        metadata={"provider": "x", "environment": "PROD", "scopes": []},
    )
    item_upper = service.get_item(created_upper.id or -1)
    assert item_upper is not None
    assert item_upper.metadata["environment"] == "prod"

    with pytest.raises(ValueError):
        service.create_api_token(
            title="Invalid",
            token="abc",
            metadata={"provider": "x", "environment": "invalid", "scopes": []},
        )

    with pytest.raises(ValueError):
        service.create_api_token(
            title="Invalid",
            token="abc",
            metadata={"provider": "x", "environment": "prod", "scopes": "not-a-list"},
        )


def test_create_api_token_persists_notes_metadata(service: SecretService) -> None:
    created = service.create_api_token(
        title="Token with note",
        token="note_token",
        metadata={
            "provider": "github",
            "environment": "prod",
            "scopes": ["repo"],
            "notes": "Rotation trimestrielle",
        },
    )

    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.metadata["notes"] == "Rotation trimestrielle"


def test_update_api_token_without_new_token_preserves_payload(service: SecretService) -> None:
    created = service.create_api_token(
        title="Token updatable",
        token="token_initial_value",
        metadata={
            "provider": "github",
            "environment": "prod",
            "scopes": ["repo"],
            "notes": "initial",
        },
    )

    updated = service.update_api_token(
        item_id=created.id or -1,
        title="Token updatable v2",
        token=None,
        metadata={
            "provider": "github",
            "environment": "production",
            "scopes": ["repo", "workflow"],
            "notes": "updated note",
        },
    )

    assert updated.title == "Token updatable v2"
    assert updated.metadata["environment"] == "prod"
    assert updated.metadata["notes"] == "updated note"
    assert service.reveal_api_token(created.id or -1) == "token_initial_value"
