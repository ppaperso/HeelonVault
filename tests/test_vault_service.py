"""Tests unitaires pour VaultService (phase 2b)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.services.vault_service import VaultService


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def users_db_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "users.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            workspace_uuid TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO users (username, workspace_uuid) VALUES ('alice', 'uuid-alice-1111')"
    )
    conn.execute(
        "INSERT INTO users (username, workspace_uuid) VALUES ('bob', 'uuid-bob-2222')"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def service(users_db_path: Path, data_dir: Path) -> Iterator[VaultService]:
    svc = VaultService(users_db_path, data_dir)
    yield svc
    svc.close()


class TestGetActiveVault:
    def test_bootstraps_personal_from_workspace_uuid(self, service: VaultService) -> None:
        vault = service.get_active_vault(user_id=1)
        assert vault.name == "Personal"
        assert vault.uuid == "uuid-alice-1111"
        assert vault.is_default is True

    def test_returns_existing_default(self, service: VaultService) -> None:
        service.get_active_vault(user_id=1)
        vault = service.get_active_vault(user_id=1)
        assert vault.uuid == "uuid-alice-1111"


class TestCreateVault:
    def test_create_vault_generates_files(self, service: VaultService, data_dir: Path) -> None:
        service.get_active_vault(user_id=1)
        vault = service.create_vault(user_id=1, name="Work", master_password="secret")
        db_path = data_dir / f"passwords_{vault.uuid}.db"
        salt_path = data_dir / f"salt_{vault.uuid}.bin"
        assert db_path.exists()
        assert salt_path.exists()

    def test_create_vault_requires_master_password(self, service: VaultService) -> None:
        with pytest.raises(ValueError):
            service.create_vault(user_id=1, name="Work", master_password="")


class TestDeleteVault:
    def test_refuses_delete_last_vault(self, service: VaultService) -> None:
        active = service.get_active_vault(user_id=1)
        assert service.delete_vault(active.id, user_id=1) is False

    def test_delete_removes_files_and_row(self, service: VaultService, data_dir: Path) -> None:
        active = service.get_active_vault(user_id=1)
        extra = service.create_vault(user_id=1, name="Work", master_password="secret")
        assert service.delete_vault(extra.id, user_id=1) is True

        db_path = data_dir / f"passwords_{extra.uuid}.db"
        salt_path = data_dir / f"salt_{extra.uuid}.bin"
        assert not db_path.exists()
        assert not salt_path.exists()

        vaults = service.list_vaults(user_id=1)
        assert len(vaults) == 1
        assert vaults[0].id == active.id

    def test_delete_default_promotes_another(self, service: VaultService) -> None:
        active = service.get_active_vault(user_id=1)
        other = service.create_vault(user_id=1, name="Work", master_password="secret")

        assert service.delete_vault(active.id, user_id=1) is True
        new_active = service.get_active_vault(user_id=1)
        assert new_active.id == other.id


class TestSwitchRenameList:
    def test_switch_vault_updates_default(self, service: VaultService) -> None:
        service.get_active_vault(user_id=1)
        v2 = service.create_vault(user_id=1, name="Work", master_password="secret")

        active = service.switch_vault(user_id=1, vault_id=v2.id)
        assert active.id == v2.id

    def test_switch_rejects_foreign_vault(self, service: VaultService) -> None:
        service.get_active_vault(user_id=1)
        b_vault = service.get_active_vault(user_id=2)
        with pytest.raises(ValueError):
            service.switch_vault(user_id=1, vault_id=b_vault.id)

    def test_rename_vault(self, service: VaultService) -> None:
        vault = service.get_active_vault(user_id=1)
        assert service.rename_vault(vault.id, "Mon coffre") is True
        vaults = service.list_vaults(user_id=1)
        assert vaults[0].name == "Mon coffre"

    def test_list_vaults(self, service: VaultService) -> None:
        service.get_active_vault(user_id=1)
        service.create_vault(user_id=1, name="Work", master_password="secret")
        assert len(service.list_vaults(user_id=1)) == 2
