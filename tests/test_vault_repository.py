"""Tests unitaires pour VaultRepository.

Chaque test repart d'une DB SQLite vierge (pytest tmp_path).
Les tests couvrent : create, list_for_user, get_default,
rename, delete, set_default et les gardes (default non supprimable,
UUID unique, vault d'un autre user).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.models.vault import Vault
from src.repositories.vault_repository import VaultRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Crée un users.db minimal avec deux utilisateurs de test."""
    path = tmp_path / "users.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT UNIQUE NOT NULL,
            workspace_uuid TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO users (username, workspace_uuid) VALUES ('alice', 'uuid-alice-0000')"
    )
    conn.execute(
        "INSERT INTO users (username, workspace_uuid) VALUES ('bob',   'uuid-bob-0000')"
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def repo(db_path: Path) -> VaultRepository:
    r = VaultRepository(db_path)
    yield r
    r.close()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

class TestCreate:
    def test_returns_vault_instance(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        assert isinstance(vault, Vault)

    def test_id_is_assigned(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        assert vault.id is not None and vault.id > 0

    def test_fields_match(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Work")
        assert vault.user_id == 1
        assert vault.name == "Work"
        assert len(vault.uuid) > 0

    def test_default_is_false(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        assert vault.is_default is False

    def test_explicit_uuid_preserved(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Work", vault_uuid="my-fixed-uuid")
        assert vault.uuid == "my-fixed-uuid"

    def test_auto_uuid_generated_when_absent(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        assert vault.uuid  # non vide

    def test_uuid_uniqueness_enforced(self, repo: VaultRepository) -> None:
        repo.create(user_id=1, name="V1", vault_uuid="duplicate-uuid")
        with pytest.raises(sqlite3.IntegrityError):
            repo.create(user_id=2, name="V2", vault_uuid="duplicate-uuid")

    def test_sequential_ids_differ(self, repo: VaultRepository) -> None:
        v1 = repo.create(user_id=1, name="V1")
        v2 = repo.create(user_id=1, name="V2")
        assert v1.id != v2.id


# ---------------------------------------------------------------------------
# list_for_user
# ---------------------------------------------------------------------------

class TestListForUser:
    def test_empty_when_no_vaults(self, repo: VaultRepository) -> None:
        assert repo.list_for_user(user_id=1) == []

    def test_returns_own_vaults_only(self, repo: VaultRepository) -> None:
        repo.create(user_id=1, name="Alice Vault")
        repo.create(user_id=2, name="Bob Vault")
        result = repo.list_for_user(user_id=1)
        assert len(result) == 1
        assert result[0].name == "Alice Vault"

    def test_default_vault_listed_first(self, repo: VaultRepository) -> None:
        repo.create(user_id=1, name="V1")
        v2 = repo.create(user_id=1, name="V2")
        repo.set_default(v2.id, user_id=1)
        vaults = repo.list_for_user(user_id=1)
        assert vaults[0].id == v2.id

    def test_multiple_vaults_all_returned(self, repo: VaultRepository) -> None:
        for name in ("Personal", "Work", "Finance"):
            repo.create(user_id=1, name=name)
        assert len(repo.list_for_user(user_id=1)) == 3


# ---------------------------------------------------------------------------
# get_default
# ---------------------------------------------------------------------------

class TestGetDefault:
    def test_none_when_no_vaults(self, repo: VaultRepository) -> None:
        assert repo.get_default(user_id=1) is None

    def test_none_when_no_default_set(self, repo: VaultRepository) -> None:
        repo.create(user_id=1, name="Personal")  # is_default stays False
        assert repo.get_default(user_id=1) is None

    def test_returns_default_after_set_default(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        repo.set_default(vault.id, user_id=1)
        default = repo.get_default(user_id=1)
        assert default is not None
        assert default.id == vault.id

    def test_is_default_flag_true(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        repo.set_default(vault.id, user_id=1)
        default = repo.get_default(user_id=1)
        assert default.is_default is True

    def test_returns_none_for_user_without_default(self, repo: VaultRepository) -> None:
        # alice has a default; bob has none
        v = repo.create(user_id=1, name="Alice")
        repo.set_default(v.id, user_id=1)
        assert repo.get_default(user_id=2) is None


# ---------------------------------------------------------------------------
# set_default
# ---------------------------------------------------------------------------

class TestSetDefault:
    def test_returns_true_on_success(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        assert repo.set_default(vault.id, user_id=1) is True

    def test_returns_false_wrong_user(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Alice")
        assert repo.set_default(vault.id, user_id=2) is False

    def test_only_one_default_at_a_time(self, repo: VaultRepository) -> None:
        v1 = repo.create(user_id=1, name="V1")
        v2 = repo.create(user_id=1, name="V2")
        repo.set_default(v1.id, user_id=1)
        repo.set_default(v2.id, user_id=1)
        vaults = repo.list_for_user(user_id=1)
        defaults = [v for v in vaults if v.is_default]
        assert len(defaults) == 1
        assert defaults[0].id == v2.id

    def test_previous_default_cleared(self, repo: VaultRepository) -> None:
        v1 = repo.create(user_id=1, name="V1")
        v2 = repo.create(user_id=1, name="V2")
        repo.set_default(v1.id, user_id=1)
        repo.set_default(v2.id, user_id=1)
        vaults = {v.id: v for v in repo.list_for_user(user_id=1)}
        assert vaults[v1.id].is_default is False

    def test_returns_false_nonexistent_vault(self, repo: VaultRepository) -> None:
        assert repo.set_default(9999, user_id=1) is False

    def test_cross_user_defaults_independent(self, repo: VaultRepository) -> None:
        va = repo.create(user_id=1, name="Alice vault")
        vb = repo.create(user_id=2, name="Bob vault")
        repo.set_default(va.id, user_id=1)
        repo.set_default(vb.id, user_id=2)
        assert repo.get_default(user_id=1).id == va.id
        assert repo.get_default(user_id=2).id == vb.id


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

class TestRename:
    def test_rename_succeeds(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Old")
        assert repo.rename(vault.id, "New") is True

    def test_name_updated_in_db(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Old")
        repo.rename(vault.id, "New")
        vaults = repo.list_for_user(user_id=1)
        assert vaults[0].name == "New"

    def test_rename_nonexistent_vault_returns_false(self, repo: VaultRepository) -> None:
        assert repo.rename(9999, "Whatever") is False


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_non_default_vault(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="To Delete")
        assert repo.delete(vault.id) is True

    def test_vault_removed_from_list(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="To Delete")
        repo.delete(vault.id)
        assert repo.list_for_user(user_id=1) == []

    def test_delete_default_vault_blocked(self, repo: VaultRepository) -> None:
        vault = repo.create(user_id=1, name="Personal")
        repo.set_default(vault.id, user_id=1)
        assert repo.delete(vault.id) is False

    def test_default_vault_still_exists_after_blocked_delete(
        self, repo: VaultRepository
    ) -> None:
        vault = repo.create(user_id=1, name="Personal")
        repo.set_default(vault.id, user_id=1)
        repo.delete(vault.id)
        assert len(repo.list_for_user(user_id=1)) == 1

    def test_delete_nonexistent_vault_returns_false(
        self, repo: VaultRepository
    ) -> None:
        assert repo.delete(9999) is False

    def test_delete_only_removes_target(self, repo: VaultRepository) -> None:
        v1 = repo.create(user_id=1, name="Keep")
        v2 = repo.create(user_id=1, name="Remove")
        repo.delete(v2.id)
        remaining = repo.list_for_user(user_id=1)
        assert len(remaining) == 1
        assert remaining[0].id == v1.id
