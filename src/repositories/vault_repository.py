"""Couche d'accès aux données pour les vaults utilisateurs."""

from __future__ import annotations

import logging
import sqlite3
import uuid as _uuid_mod
from datetime import datetime
from pathlib import Path

from src.models.vault import Vault

logger = logging.getLogger(__name__)


class VaultRepository:
    """Gère la table `vaults` dans users.db.

    Chaque vault représente un coffre-fort indépendant (passwords_{uuid}.db).
    Un utilisateur peut posséder plusieurs vaults ; un seul est marqué
    is_default=True à la fois.
    """

    def __init__(self, users_db_path: Path) -> None:
        self.db_path = users_db_path
        self.conn = sqlite3.connect(str(users_db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        logger.debug("VaultRepository initialized on %s", users_db_path)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Crée la table vaults et son index si absents."""
        self.conn.execute(
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
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vaults_user_id ON vaults(user_id)"
        )
        self.conn.commit()
        logger.debug("VaultRepository: schema initialized")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        user_id: int,
        name: str,
        vault_uuid: str | None = None,
    ) -> Vault:
        """Crée un nouveau vault pour l'utilisateur.

        Args:
            user_id:    ID de l'utilisateur propriétaire.
            name:       Nom du vault (ex. "Personal", "Work").
            vault_uuid: UUID à utiliser (généré automatiquement si absent).
                        Utile pour la migration depuis workspace_uuid.

        Returns:
            Le Vault créé avec son id assigné.
        """
        new_uuid = vault_uuid or str(_uuid_mod.uuid4())
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO vaults (user_id, name, uuid) VALUES (?, ?, ?)",
            (user_id, name, new_uuid),
        )
        self.conn.commit()
        vault_id = cursor.lastrowid

        if vault_id is None:
            raise sqlite3.DatabaseError("Failed to retrieve the last insert row ID.")

        logger.debug("Created vault id=%d name=%r for user_id=%d", vault_id, name, user_id)
        return Vault(id=vault_id, user_id=user_id, name=name, uuid=new_uuid)

    def list_for_user(self, user_id: int) -> list[Vault]:
        """Retourne tous les vaults d'un utilisateur (défaut en premier)."""
        cursor = self.conn.execute(
            """
            SELECT id, user_id, name, uuid, is_default, created_at
              FROM vaults
             WHERE user_id = ?
             ORDER BY is_default DESC, created_at ASC
            """,
            (user_id,),
        )
        return [self._row_to_vault(row) for row in cursor.fetchall()]

    def get_default(self, user_id: int) -> Vault | None:
        """Retourne le vault par défaut de l'utilisateur, ou None."""
        cursor = self.conn.execute(
            """
            SELECT id, user_id, name, uuid, is_default, created_at
              FROM vaults
             WHERE user_id = ? AND is_default = 1
             LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return self._row_to_vault(row) if row else None

    def rename(self, vault_id: int, name: str) -> bool:
        """Renomme un vault.

        Returns:
            True si la mise à jour a affecté exactement une ligne, False sinon.
        """
        cursor = self.conn.execute(
            "UPDATE vaults SET name = ? WHERE id = ?",
            (name, vault_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def delete(self, vault_id: int) -> bool:
        """Supprime un vault non-défaut.

        Le vault par défaut d'un utilisateur ne peut pas être supprimé
        directement : il faut d'abord promouvoir un autre vault.

        Returns:
            True si supprimé, False si introuvable ou si c'est le défaut.
        """
        row = self.conn.execute(
            "SELECT is_default FROM vaults WHERE id = ?", (vault_id,)
        ).fetchone()

        if row is None:
            logger.debug("delete: vault id=%d not found", vault_id)
            return False
        if bool(row["is_default"]):
            logger.warning("delete: refusing to delete default vault id=%d", vault_id)
            return False

        cursor = self.conn.execute("DELETE FROM vaults WHERE id = ?", (vault_id,))
        self.conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug("Deleted vault id=%d", vault_id)
        return deleted

    def set_default(self, vault_id: int, user_id: int) -> bool:
        """Définit un vault comme défaut pour l'utilisateur.

        Retire le flag is_default de tous les autres vaults du même user,
        puis positionne is_default=1 sur le vault ciblé. Opération atomique.

        Returns:
            True si réussi, False si le vault n'appartient pas à cet utilisateur.
        """
        row = self.conn.execute(
            "SELECT id FROM vaults WHERE id = ? AND user_id = ?",
            (vault_id, user_id),
        ).fetchone()

        if row is None:
            logger.warning(
                "set_default: vault id=%d does not belong to user_id=%d",
                vault_id, user_id,
            )
            return False

        self.conn.execute(
            "UPDATE vaults SET is_default = 0 WHERE user_id = ?", (user_id,)
        )
        self.conn.execute(
            "UPDATE vaults SET is_default = 1 WHERE id = ?", (vault_id,)
        )
        self.conn.commit()
        logger.debug("set_default: vault id=%d is now default for user_id=%d", vault_id, user_id)
        return True

    # ------------------------------------------------------------------
    # Utilitaires internes
    # ------------------------------------------------------------------

    def _row_to_vault(self, row: sqlite3.Row) -> Vault:
        created_at: datetime | None = None
        if row["created_at"]:
            try:
                created_at = datetime.fromisoformat(str(row["created_at"]))
            except (ValueError, TypeError):
                pass
        return Vault(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            uuid=row["uuid"],
            is_default=bool(row["is_default"]),
            created_at=created_at,
        )

    def close(self) -> None:
        """Ferme la connexion SQLite."""
        self.conn.close()
