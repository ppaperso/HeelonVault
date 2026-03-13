"""Tests unitaires du SecretService (API minimale Day-1/Etape 3)."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models.secret_types import SECRET_TYPE_API_TOKEN, SECRET_TYPE_SSH_KEY
from src.repositories.migrations.migrate_v1_to_v2 import run as migrate_v1_to_v2
from src.repositories.secret_repository import SecretRepository
from src.services.crypto_service import CryptoService
from src.services.secret_service import SecretService
from src.services.ssh_key_utils import PassphraseMismatch, UnsupportedKeyFormat
from tests.fixtures.ssh_fixture_data import (
    ED25519_FINGERPRINT_SHA256,
    ED25519_PRIVATE_PATH,
    ED25519_PUBLIC_PATH,
    RSA_4096_FINGERPRINT_SHA256,
    RSA_4096_PASSPHRASE,
    RSA_4096_PRIVATE_PATH,
    RSA_4096_PUBLIC_PATH,
    read_text,
)


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


def test_create_ssh_key_and_reveal_private_key(service: SecretService) -> None:
    created = service.create_ssh_key(
        title="Deploy key",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
        metadata={"tags": ["infra", "prod"]},
    )

    assert created.id is not None
    assert created.secret_type == SECRET_TYPE_SSH_KEY
    assert created.payload == ""

    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.metadata["algorithm"] == "ed25519"
    assert item.metadata["fingerprint"] == ED25519_FINGERPRINT_SHA256
    assert item.metadata["has_passphrase"] is False

    private_key = service.reveal_ssh_private_key(created.id or -1)
    assert private_key.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")


def test_mixed_types_coexist_with_password_entries_without_interference(
    service: SecretService,
) -> None:
    # Insert a legacy password row directly to validate table coexistence.
    service.repository.conn.execute(
        "INSERT INTO passwords (title, password_data, deleted_at) VALUES (?, ?, NULL)",
        ("Ops Login", "enc_pwd_blob"),
    )
    service.repository.conn.commit()

    api_item = service.create_api_token(
        title="Ops API",
        token="ops_token_123",
        metadata={"provider": "ops", "environment": "prod", "scopes": ["read"]},
    )
    ssh_item = service.create_ssh_key(
        title="Ops SSH",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
        metadata={"tags": ["infra"]},
    )

    mixed_search = service.list_items(search_text="Ops")
    assert len(mixed_search) == 2
    assert {item.secret_type for item in mixed_search} == {
        SECRET_TYPE_API_TOKEN,
        SECRET_TYPE_SSH_KEY,
    }

    api_only = service.list_items(secret_type=SECRET_TYPE_API_TOKEN)
    ssh_only = service.list_items(secret_type=SECRET_TYPE_SSH_KEY)
    assert [item.id for item in api_only] == [api_item.id]
    assert [item.id for item in ssh_only] == [ssh_item.id]

    assert service.reveal_api_token(api_item.id or -1) == "ops_token_123"
    assert service.reveal_ssh_private_key(ssh_item.id or -1).startswith(
        "-----BEGIN OPENSSH PRIVATE KEY-----"
    )

    legacy_password_row = service.repository.conn.execute(
        "SELECT title, password_data FROM passwords WHERE title = ?",
        ("Ops Login",),
    ).fetchone()
    assert legacy_password_row is not None
    assert legacy_password_row["title"] == "Ops Login"
    assert legacy_password_row["password_data"] == "enc_pwd_blob"


def test_mixed_types_usage_count_is_isolated(service: SecretService) -> None:
    api_item = service.create_api_token(
        title="Usage API",
        token="usage_api",
        metadata={"provider": "usage", "environment": "prod", "scopes": []},
    )
    ssh_item = service.create_ssh_key(
        title="Usage SSH",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
        metadata={},
    )

    service.reveal_api_token(api_item.id or -1)
    service.reveal_api_token(api_item.id or -1)
    service.reveal_ssh_private_key(ssh_item.id or -1)

    api_after = service.get_item(api_item.id or -1)
    ssh_after = service.get_item(ssh_item.id or -1)
    assert api_after is not None
    assert ssh_after is not None
    assert api_after.usage_count == 2
    assert ssh_after.usage_count == 1


def test_create_ssh_key_with_rsa_passphrase(service: SecretService) -> None:
    created = service.create_ssh_key(
        title="Legacy RSA",
        private_key=read_text(RSA_4096_PRIVATE_PATH),
        public_key=read_text(RSA_4096_PUBLIC_PATH),
        metadata={},
        passphrase=RSA_4096_PASSPHRASE,
    )

    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.metadata["algorithm"] == "rsa"
    assert item.metadata["fingerprint"] == RSA_4096_FINGERPRINT_SHA256
    assert item.metadata["has_passphrase"] is True
    assert item.metadata["key_size"] == 4096


def test_update_ssh_key_is_metadata_only(service: SecretService) -> None:
    created = service.create_ssh_key(
        title="Server key",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
        metadata={"comment": "initial", "tags": ["old"]},
    )

    original_private_key = service.reveal_ssh_private_key(created.id or -1)

    updated = service.update_ssh_key(
        item_id=created.id or -1,
        title="Server key renamed",
        metadata={"comment": "rotated metadata", "tags": ["infra", "prod"]},
    )

    assert updated.title == "Server key renamed"
    assert updated.metadata["comment"] == "rotated metadata"

    private_key_after_update = service.reveal_ssh_private_key(created.id or -1)
    assert private_key_after_update == original_private_key


# ── PR2 : Import / Export ────────────────────────────────────────────────────

def test_import_ssh_key_from_file_ed25519(service: SecretService) -> None:
    result = service.import_ssh_key_from_file(ED25519_PRIVATE_PATH)

    assert result.id is not None
    assert result.secret_type == SECRET_TYPE_SSH_KEY
    assert result.payload == ""
    assert result.metadata["algorithm"] == "ed25519"
    assert result.metadata["fingerprint"] == ED25519_FINGERPRINT_SHA256
    assert result.metadata["has_passphrase"] is False


def test_import_ssh_key_from_file_rsa_with_passphrase(service: SecretService) -> None:
    result = service.import_ssh_key_from_file(
        RSA_4096_PRIVATE_PATH,
        passphrase=RSA_4096_PASSPHRASE,
    )

    assert result.id is not None
    assert result.metadata["algorithm"] == "rsa"
    assert result.metadata["fingerprint"] == RSA_4096_FINGERPRINT_SHA256
    assert result.metadata["has_passphrase"] is True
    assert result.metadata["key_size"] == 4096


def test_import_ssh_key_wrong_passphrase_raises_passphrase_mismatch(service: SecretService) -> None:
    with pytest.raises(PassphraseMismatch, match="passphrase"):
        service.import_ssh_key_from_file(RSA_4096_PRIVATE_PATH, passphrase="wrong!")


def test_ssh_operations_do_not_log_private_material(
    service: SecretService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    private_key = read_text(ED25519_PRIVATE_PATH)

    created = service.create_ssh_key(
        title="Log hygiene",
        private_key=private_key,
        public_key=read_text(ED25519_PUBLIC_PATH),
        metadata={},
    )
    service.reveal_ssh_private_key(created.id or -1)

    with pytest.raises(PassphraseMismatch):
        service.import_ssh_key_from_file(RSA_4096_PRIVATE_PATH, passphrase="not-the-right-one")

    logged = caplog.text
    assert "BEGIN OPENSSH PRIVATE KEY" not in logged
    assert private_key[:80] not in logged
    assert "not-the-right-one" not in logged


def test_import_ssh_key_unsupported_format_raises_unsupported_key_format(
    service: SecretService,
    tmp_path: Path,
) -> None:
    bad_key = tmp_path / "garbage_key"
    bad_key.write_text(
        "-----BEGIN GARBAGE KEY-----\nABCDEFGHIJKLMNOP\n-----END GARBAGE KEY-----\n"
    )
    (tmp_path / "garbage_key.pub").write_text(read_text(ED25519_PUBLIC_PATH))

    with pytest.raises(UnsupportedKeyFormat):
        service.import_ssh_key_from_file(bad_key)


def test_export_ssh_key_creates_file_with_correct_permissions(
    service: SecretService,
    tmp_path: Path,
) -> None:
    created = service.create_ssh_key(
        title="Export test key",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
    )

    dest = tmp_path / "exported_ed25519"
    service.export_ssh_key(created.id or -1, dest)

    assert dest.exists()
    mode_octal = oct(dest.stat().st_mode)
    assert mode_octal.endswith("600"), f"Expected 0o600 permissions, got {mode_octal}"
    content = dest.read_text("utf-8")
    assert "OPENSSH PRIVATE KEY" in content


def test_export_ssh_key_refuses_overwrite(service: SecretService, tmp_path: Path) -> None:
    created = service.create_ssh_key(
        title="Overwrite test key",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
    )

    dest = tmp_path / "existing_key"
    dest.write_text("original content here")

    with pytest.raises(FileExistsError):
        service.export_ssh_key(created.id or -1, dest)

    assert dest.read_text() == "original content here"


def test_reveal_ssh_key_increments_usage_count(service: SecretService) -> None:
    created = service.create_ssh_key(
        title="Usage count test",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
    )

    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.usage_count == 0

    service.reveal_ssh_private_key(created.id or -1)
    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.usage_count == 1

    service.reveal_ssh_private_key(created.id or -1)
    item = service.get_item(created.id or -1)
    assert item is not None
    assert item.usage_count == 2


def test_repr_does_not_leak_payload(service: SecretService) -> None:
    created = service.create_ssh_key(
        title="Repr leak test",
        private_key=read_text(ED25519_PRIVATE_PATH),
        public_key=read_text(ED25519_PUBLIC_PATH),
    )

    # Get item directly from repository (payload still set as encrypted bytes)
    raw_item = service.repository.get_item(created.id or -1)
    assert raw_item is not None
    assert raw_item.payload  # encrypted payload is present

    repr_str = repr(raw_item)
    assert "PRIVATE" not in repr_str
    assert "OPENSSH" not in repr_str
    assert "BEGIN" not in repr_str
