"""Couche d'accès aux données pour la table secret_items."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid as uuid_mod
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.secret_item import SecretItem

logger = logging.getLogger(__name__)


class SecretRepository:
    """Gère le stockage des nouveaux secrets dans passwords_<uuid>.db."""

    def __init__(self, db_path: Path, backup_service: Any | None = None) -> None:
        self.db_path = db_path
        self.backup_service = backup_service
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        logger.debug("SecretRepository initialized on %s", db_path)

    def _init_db(self) -> None:
        """Crée la table `secret_items` si absente (idempotent, compatible migration)."""
        self.conn.execute(
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
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_secret_items_type ON secret_items(secret_type)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_secret_items_title ON secret_items(title)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_secret_items_expires ON secret_items(expires_at)"
        )
        self.conn.commit()

    def create_item(self, item: SecretItem) -> SecretItem:
        """Insère un secret et retourne l'objet avec id/item_uuid/timestamps."""
        item_uuid = item.item_uuid or str(uuid_mod.uuid4())
        now_iso = self._now_iso()
        payload_blob = self._payload_to_blob(item.payload)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO secret_items (
                secret_type, title, metadata_json, secret_blob, blob_storage,
                tags, expires_at, created_at, modified_at, usage_count, item_uuid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.secret_type,
                item.title,
                json.dumps(item.metadata),
                payload_blob,
                item.blob_storage,
                json.dumps(item.tags),
                self._dt_to_iso(item.expires_at),
                now_iso,
                now_iso,
                int(item.usage_count),
                item_uuid,
            ),
        )
        self.conn.commit()

        item_id = cursor.lastrowid
        if item_id is None:
            raise sqlite3.DatabaseError("Unable to retrieve inserted secret identifier")

        created = SecretItem(
            id=int(item_id),
            item_uuid=item_uuid,
            secret_type=item.secret_type,
            title=item.title,
            metadata=dict(item.metadata),
            payload=payload_blob,
            tags=list(item.tags),
            blob_storage=item.blob_storage,
            expires_at=item.expires_at,
            created_at=datetime.fromisoformat(now_iso),
            modified_at=datetime.fromisoformat(now_iso),
            usage_count=int(item.usage_count),
        )
        logger.debug("Secret item %s created in %s", created.id, self.db_path.name)
        return created

    def get_item(self, item_id: int) -> SecretItem | None:
        """Retourne un secret par id, ou None."""
        row = self.conn.execute(
            """
            SELECT id, secret_type, title, metadata_json, secret_blob, blob_storage,
                   tags, expires_at, created_at, modified_at, usage_count, item_uuid
            FROM secret_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
        return self._row_to_item(row) if row else None

    def get_item_by_uuid(self, item_uuid: str) -> SecretItem | None:
        """Retourne un secret par UUID stable, ou None."""
        row = self.conn.execute(
            """
            SELECT id, secret_type, title, metadata_json, secret_blob, blob_storage,
                   tags, expires_at, created_at, modified_at, usage_count, item_uuid
            FROM secret_items
            WHERE item_uuid = ?
            """,
            (item_uuid,),
        ).fetchone()
        return self._row_to_item(row) if row else None

    def list_items(
        self,
        secret_type: str | None = None,
        search_text: str | None = None,
    ) -> list[SecretItem]:
        """Liste les secrets avec filtres simples (type + titre)."""
        query_parts = [
            "SELECT id, secret_type, title, metadata_json, secret_blob, blob_storage,",
            "tags, expires_at, created_at, modified_at, usage_count, item_uuid",
            "FROM secret_items WHERE 1 = 1",
        ]
        params: list[str] = []

        if secret_type:
            query_parts.append("AND secret_type = ?")
            params.append(secret_type)

        if search_text:
            query_parts.append("AND title LIKE ?")
            params.append(f"%{search_text}%")

        query_parts.append("ORDER BY title COLLATE NOCASE")
        rows = self.conn.execute(" ".join(query_parts), params).fetchall()
        return [self._row_to_item(row) for row in rows]

    def update_item(self, item: SecretItem) -> SecretItem:
        """Met à jour un secret existant et retourne la version persistée."""
        if item.id is None:
            raise ValueError("update_item requires an identifier")

        modified_at_iso = self._now_iso()
        cursor = self.conn.execute(
            """
            UPDATE secret_items
               SET secret_type = ?,
                   title = ?,
                   metadata_json = ?,
                   secret_blob = ?,
                   blob_storage = ?,
                   tags = ?,
                   expires_at = ?,
                   modified_at = ?,
                   usage_count = ?
             WHERE id = ?
            """,
            (
                item.secret_type,
                item.title,
                json.dumps(item.metadata),
                self._payload_to_blob(item.payload),
                item.blob_storage,
                json.dumps(item.tags),
                self._dt_to_iso(item.expires_at),
                modified_at_iso,
                int(item.usage_count),
                item.id,
            ),
        )
        self.conn.commit()

        if cursor.rowcount == 0:
            raise ValueError(f"Secret item {item.id} not found")

        updated = self.get_item(item.id)
        if updated is None:
            raise sqlite3.DatabaseError("Updated secret item cannot be reloaded")
        logger.debug("Secret item %s updated", item.id)
        return updated

    def delete_item(self, item_id: int) -> bool:
        """Supprime définitivement un secret."""
        cursor = self.conn.execute("DELETE FROM secret_items WHERE id = ?", (item_id,))
        self.conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug("Secret item %s deleted", item_id)
        return deleted

    def record_usage(self, item_id: int, amount: int = 1) -> None:
        """Incrémente le compteur d'usage d'un secret."""
        self.conn.execute(
            """
            UPDATE secret_items
               SET usage_count = COALESCE(usage_count, 0) + ?,
                   modified_at = ?
             WHERE id = ?
            """,
            (amount, self._now_iso(), item_id),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _row_to_item(self, row: sqlite3.Row) -> SecretItem:
        metadata = self._load_json_object(row["metadata_json"])
        tags = self._load_json_list(row["tags"])
        expires_at = self._parse_timestamp(row["expires_at"])
        created_at = self._parse_timestamp(row["created_at"])
        modified_at = self._parse_timestamp(row["modified_at"])

        return SecretItem(
            id=int(row["id"]),
            item_uuid=str(row["item_uuid"]),
            secret_type=str(row["secret_type"]),
            title=str(row["title"]),
            metadata=metadata,
            payload=bytes(row["secret_blob"]),
            tags=tags,
            blob_storage=str(row["blob_storage"]),
            expires_at=expires_at,
            created_at=created_at,
            modified_at=modified_at,
            usage_count=int(row["usage_count"] or 0),
        )

    @staticmethod
    def _payload_to_blob(payload: str | bytes | bytearray | memoryview) -> bytes:
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, bytearray):
            return bytes(payload)
        if isinstance(payload, memoryview):
            return payload.tobytes()
        return payload.encode("utf-8")

    @staticmethod
    def _load_json_object(raw: str) -> dict[str, Any]:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _load_json_list(raw: str) -> list[str]:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dt_to_iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat(timespec="seconds")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")
