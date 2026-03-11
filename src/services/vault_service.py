"""Service métier de gestion des vaults multi-coffres."""

from __future__ import annotations

import logging
import secrets
import sqlite3
from pathlib import Path

from src.models.vault import Vault
from src.repositories.password_repository import PasswordRepository
from src.repositories.vault_repository import VaultRepository

logger = logging.getLogger(__name__)


class VaultService:
    """Orchestre la gestion applicative des vaults.

    Ce service repose sur `vaults` dans `users.db`, tout en synchronisant
    les fichiers disque associés:
      - passwords_{uuid}.db
      - salt_{uuid}.bin
    """

    def __init__(self, users_db_path: Path, data_dir: Path) -> None:
        self.users_db_path = users_db_path
        self.data_dir = data_dir
        self.repository = VaultRepository(users_db_path)

    def close(self) -> None:
        """Libère les ressources SQLite du repository."""
        self.repository.close()

    def list_vaults(self, user_id: int) -> list[Vault]:
        """Retourne tous les vaults de l'utilisateur."""
        return self.repository.list_for_user(user_id)

    def get_active_vault(self, user_id: int) -> Vault:
        """Retourne le vault actif (défaut) de l'utilisateur.

        Comportement de compatibilité:
        - Si aucun vault n'existe encore, bootstrap depuis users.workspace_uuid.
        - Si des vaults existent mais aucun défaut, le premier devient défaut.

        Raises:
            ValueError: si l'utilisateur est introuvable ou sans workspace_uuid.
        """
        active = self.repository.get_default(user_id)
        if active:
            return active

        vaults = self.repository.list_for_user(user_id)
        if vaults:
            first = vaults[0]
            self.repository.set_default(first.id, user_id)
            return self.repository.get_default(user_id) or first

        workspace_uuid = self._get_user_workspace_uuid(user_id)
        if not workspace_uuid:
            raise ValueError(f"user_id={user_id} has no workspace_uuid")

        personal = self.repository.create(
            user_id=user_id,
            name="Personal",
            vault_uuid=workspace_uuid,
        )
        self.repository.set_default(personal.id, user_id)
        return self.repository.get_default(user_id) or personal

    def create_vault(self, user_id: int, name: str, master_password: str) -> Vault:
        """Crée un vault et initialise ses artefacts disque.

        Le paramètre `master_password` est exigé par contrat de l'étape 2b.
        Dans ce service, il sert à valider le contexte d'appel et à garantir
        qu'un salt existe pour une dérivation PBKDF2 ultérieure.
        """
        if not master_password:
            raise ValueError("master_password is required")

        vault = self.repository.create(user_id=user_id, name=name)
        self._ensure_vault_storage(vault.uuid)
        return vault

    def delete_vault(self, vault_id: int, user_id: int) -> bool:
        """Supprime un vault (DB + salt + ligne en base).

        Refuse la suppression du dernier vault d'un utilisateur.
        Si le vault ciblé est le défaut, un autre vault est promu avant suppression.
        """
        vaults = self.repository.list_for_user(user_id)
        if len(vaults) <= 1:
            logger.warning("Refusing to delete last vault for user_id=%d", user_id)
            return False

        target = next((v for v in vaults if v.id == vault_id), None)
        if target is None:
            logger.warning("Vault id=%d not found for user_id=%d", vault_id, user_id)
            return False

        if target.is_default:
            replacement = next((v for v in vaults if v.id != vault_id), None)
            if replacement is None:
                logger.warning("No replacement vault available for user_id=%d", user_id)
                return False
            if not self.repository.set_default(replacement.id, user_id):
                return False

        deleted = self.repository.delete(vault_id)
        if not deleted:
            return False

        self._delete_vault_storage(target.uuid)
        return True

    def rename_vault(self, vault_id: int, name: str) -> bool:
        """Renomme un vault."""
        return self.repository.rename(vault_id, name)

    def switch_vault(self, user_id: int, vault_id: int) -> Vault:
        """Bascule le vault actif d'un utilisateur et le retourne.

        Raises:
            ValueError: si le vault n'appartient pas à l'utilisateur.
        """
        if not self.repository.set_default(vault_id, user_id):
            raise ValueError("vault does not belong to user")

        active = self.repository.get_default(user_id)
        if not active:
            raise RuntimeError("failed to resolve active vault after switch")
        return active

    def _get_user_workspace_uuid(self, user_id: int) -> str | None:
        conn = sqlite3.connect(str(self.users_db_path))
        try:
            row = conn.execute(
                "SELECT workspace_uuid FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return row[0]
        finally:
            conn.close()

    def _ensure_vault_storage(self, vault_uuid: str) -> None:
        """Assure la présence des fichiers DB + salt pour un vault."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        db_path = self.data_dir / f"passwords_{vault_uuid}.db"
        salt_path = self.data_dir / f"salt_{vault_uuid}.bin"

        if not salt_path.exists():
            salt_path.write_bytes(secrets.token_bytes(32))
            salt_path.chmod(0o600)

        # Initialise le schéma SQLite vide si nécessaire.
        repo = PasswordRepository(db_path)
        repo.close()
        try:
            db_path.chmod(0o600)
        except OSError:
            logger.debug("Unable to set permissions on %s", db_path)

    def _delete_vault_storage(self, vault_uuid: str) -> None:
        db_path = self.data_dir / f"passwords_{vault_uuid}.db"
        salt_path = self.data_dir / f"salt_{vault_uuid}.bin"

        for path in (db_path, salt_path):
            if path.exists():
                try:
                    path.unlink()
                except OSError as exc:
                    logger.warning("Unable to delete %s: %s", path, exc)
