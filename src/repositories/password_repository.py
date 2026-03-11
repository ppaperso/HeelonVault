"""Couche d'accès aux données pour les entrées de mots de passe."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.models.category import DEFAULT_CATEGORIES, Category
from src.models.password_entry import PasswordRecord

if TYPE_CHECKING:
    from src.services.backup_service import BackupService

logger = logging.getLogger(__name__)


class PasswordRepository:
    """Encapsule toutes les requêtes SQLite liées aux mots de passe."""

    def __init__(self, db_path: Path, backup_service: BackupService | None = None):
        self.db_path = db_path
        self.backup_service = backup_service
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._has_changes = False
        self._init_db()

        try:
            db_path.chmod(0o600)
        except OSError:
            logger.debug("Unable to set permissions on %s", db_path)

        logger.debug("PasswordRepository initialized on %s", db_path)

    # ------------------------------------------------------------------
    # Initialisation & fermeture
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                username TEXT,
                password_data TEXT NOT NULL,
                url TEXT,
                notes TEXT,
                category TEXT,
                tags TEXT,
                password_validity_days INTEGER DEFAULT 90,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_changed TIMESTAMP,
                deleted_at TIMESTAMP NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT,
                icon TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        for category in DEFAULT_CATEGORIES:
            cursor.execute(
                """
                INSERT OR IGNORE INTO categories (name, color, icon)
                VALUES (?, ?, ?)
                """,
                (category.name, category.color, category.icon),
            )
        # Migration: Ajouter la colonne deleted_at si elle n'existe pas
        migration_needed = False
        try:
            cursor.execute("SELECT deleted_at FROM passwords LIMIT 1")
        except sqlite3.OperationalError:
            migration_needed = True

        if migration_needed:
            # Backup automatique avant migration
            if self.backup_service:
                # Extraire le username du nom de fichier (passwords_username.db)
                username = self.db_path.stem.replace("passwords_", "")
                logger.info(
                    "Migration detected: creating automatic backup for %s",
                    username,
                )
                backup_path = self.backup_service.create_backup(self.db_path, username)
                if backup_path:
                    logger.info("✅ Pre-migration backup created: %s", backup_path.name)
                else:
                    logger.warning(
                        "⚠️  Unable to create pre-migration backup, migration continues"
                    )

            logger.info("Migration: adding deleted_at column")
            cursor.execute("ALTER TABLE passwords ADD COLUMN deleted_at TIMESTAMP NULL")

        validity_migration_needed = False
        try:
            cursor.execute("SELECT password_validity_days FROM passwords LIMIT 1")
        except sqlite3.OperationalError:
            validity_migration_needed = True

        if validity_migration_needed:
            logger.info("Migration: adding password_validity_days column")
            cursor.execute(
                "ALTER TABLE passwords ADD COLUMN password_validity_days INTEGER DEFAULT 90"
            )
        usage_migration_needed = False
        try:
            cursor.execute("SELECT usage_count FROM passwords LIMIT 1")
        except sqlite3.OperationalError:
            usage_migration_needed = True

        if usage_migration_needed:
            logger.info("Migration: adding usage_count column")
            cursor.execute(
                "ALTER TABLE passwords ADD COLUMN usage_count INTEGER DEFAULT 0"
            )

        self.conn.commit()
        logger.debug("SQLite schema verified for %s", self.db_path)

    def close(self) -> None:
        self.conn.close()
        logger.debug("PasswordRepository: connection closed for %s", self.db_path)

    # ------------------------------------------------------------------
    # Catégories & tags
    # ------------------------------------------------------------------
    def list_categories(self) -> list[Category]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, color, icon FROM categories ORDER BY name")
        categories = [
            Category(
                name=row[1],
                color=row[2] or "#999999",
                icon=row[3] or "folder-symbolic",
                id=row[0],
            )
            for row in cursor.fetchall()
        ]
        return categories

    def add_category(self, category: Category) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO categories (name, color, icon) VALUES (?, ?, ?)",
            (category.name, category.color, category.icon),
        )
        self.conn.commit()

    def category_exists(self, name: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM categories WHERE name=?", (name,))
        return cursor.fetchone() is not None

    def rename_category(self, old_name: str, new_name: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE name=?", (old_name,))
        if not cursor.fetchone():
            return False

        cursor.execute("UPDATE categories SET name=? WHERE name=?", (new_name, old_name))
        # Cascade on entries in the active vault DB.
        cursor.execute("UPDATE passwords SET category=? WHERE category=?", (new_name, old_name))
        self.conn.commit()
        self._has_changes = True
        return True

    def delete_category(self, name: str, fallback_name: str = "Autres") -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE name=?", (name,))
        if not cursor.fetchone():
            return False

        cursor.execute(
            "UPDATE passwords SET category=? WHERE category=?",
            (fallback_name, name),
        )
        cursor.execute("DELETE FROM categories WHERE name=?", (name,))
        self.conn.commit()
        self._has_changes = True
        return True

    @staticmethod
    def is_default_category(name: str) -> bool:
        return name in {category.name for category in DEFAULT_CATEGORIES}

    def list_tags(self) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT tags FROM passwords WHERE tags IS NOT NULL AND tags != ''"
        )
        tag_set = set()
        for (tags_json,) in cursor.fetchall():
            try:
                tags = json.loads(tags_json)
                tag_set.update(tags)
            except (json.JSONDecodeError, TypeError):
                logger.debug("Ignored invalid tags: %s", tags_json)
        return sorted(tag_set)

    def count_entries(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM passwords WHERE deleted_at IS NULL")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # CRUD entrées
    # ------------------------------------------------------------------
    def insert_entry(self, record: PasswordRecord) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO passwords (
                title, username, password_data, url, notes, category, tags,
                password_validity_days, usage_count, last_changed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                record.title,
                record.username,
                json.dumps(record.password_data),
                record.url,
                json.dumps(record.notes_data) if record.notes_data else None,
                record.category,
                json.dumps(record.tags if record.tags else []),
                record.password_validity_days,
                record.usage_count,
            ),
        )
        self.conn.commit()
        self._has_changes = True
        entry_id = cursor.lastrowid
        if entry_id is None:
            raise RuntimeError(
                "Unable to retrieve inserted entry identifier"
            )
        logger.debug("Entry %s inserted", entry_id)
        return int(entry_id)

    def update_entry(self, record: PasswordRecord, *, password_changed: bool) -> None:
        if record.id is None:
            raise ValueError("update_entry requires an identifier")

        cursor = self.conn.cursor()
        if password_changed:
            cursor.execute(
                """
                UPDATE passwords
                SET title=?, username=?, password_data=?, url=?, notes=?, category=?, tags=?,
                    password_validity_days=?, usage_count=?,
                    modified_at=CURRENT_TIMESTAMP,
                    last_changed=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    record.title,
                    record.username,
                    json.dumps(record.password_data),
                    record.url,
                    json.dumps(record.notes_data) if record.notes_data else None,
                    record.category,
                    json.dumps(record.tags if record.tags else []),
                    record.password_validity_days,
                    record.usage_count,
                    record.id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE passwords
                SET title=?, username=?, password_data=?, url=?, notes=?, category=?, tags=?,
                    password_validity_days=?, usage_count=?,
                    modified_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    record.title,
                    record.username,
                    json.dumps(record.password_data),
                    record.url,
                    json.dumps(record.notes_data) if record.notes_data else None,
                    record.category,
                    json.dumps(record.tags if record.tags else []),
                    record.password_validity_days,
                    record.usage_count,
                    record.id,
                ),
            )
        self.conn.commit()
        self._has_changes = True
        logger.debug(
            "Entry %s updated (password changed=%s)", record.id, password_changed
        )

    def update_encrypted_payload(
        self,
        entry_id: int,
        password_data: dict[str, str],
        notes_data: dict[str, str] | None,
    ) -> None:
        """Met à jour uniquement les blobs chiffrés d'une entrée."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE passwords
            SET password_data = ?, notes = ?
            WHERE id = ?
            """,
            (
                json.dumps(password_data),
                json.dumps(notes_data) if notes_data else None,
                entry_id,
            ),
        )
        self._has_changes = True

    def delete_entry(self, entry_id: int) -> None:
        """Déplace une entrée vers la corbeille (soft delete)."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE passwords SET deleted_at = CURRENT_TIMESTAMP WHERE id=?",
            (entry_id,),
        )
        self.conn.commit()
        self._has_changes = True
        logger.debug("Entry %s moved to trash", entry_id)

    def restore_entry(self, entry_id: int) -> None:
        """Restaure une entrée de la corbeille."""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE passwords SET deleted_at = NULL WHERE id=?", (entry_id,))
        self.conn.commit()
        self._has_changes = True
        logger.debug("Entry %s restored from trash", entry_id)

    def delete_entry_permanently(self, entry_id: int) -> None:
        """Supprime définitivement une entrée (ne peut pas être restaurée)."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM passwords WHERE id=?", (entry_id,))
        self.conn.commit()
        self._has_changes = True
        logger.debug("Entry %s permanently deleted", entry_id)

    def list_trash(self) -> list[PasswordRecord]:
        """Liste toutes les entrées dans la corbeille."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, title, username, password_data, url, notes, category, tags,
                     password_validity_days, created_at, modified_at, last_changed, usage_count
            FROM passwords WHERE deleted_at IS NOT NULL
            ORDER BY deleted_at DESC
            """
        )
        rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def empty_trash(self) -> int:
        """Vide complètement la corbeille (suppression définitive).

        Retourne le nombre d'entrées supprimées.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM passwords WHERE deleted_at IS NOT NULL")
        count = cursor.fetchone()[0]

        cursor.execute("DELETE FROM passwords WHERE deleted_at IS NOT NULL")
        self.conn.commit()
        self._has_changes = True
        logger.debug("%d entry/entries permanently deleted from trash", count)
        return count

    # ------------------------------------------------------------------
    # Lecture & requêtes
    # ------------------------------------------------------------------
    def get_entry(
        self, entry_id: int, include_deleted: bool = False
    ) -> PasswordRecord | None:
        cursor = self.conn.cursor()
        query = """
            SELECT id, title, username, password_data, url, notes, category, tags,
                     password_validity_days, created_at, modified_at, last_changed, usage_count
            FROM passwords WHERE id=?
        """
        if not include_deleted:
            query += " AND deleted_at IS NULL"

        cursor.execute(query, (entry_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_entries(
        self,
        *,
        category_filter: str | None = None,
        search_text: str | None = None,
        include_deleted: bool = False,
    ) -> list[PasswordRecord]:
        query = [
            "SELECT id, title, username, password_data, url, notes, category, tags,",
            "password_validity_days, created_at, modified_at, last_changed, usage_count ",
            "FROM passwords WHERE 1 = 1",
        ]
        params: list[str] = []

        # Exclure les entrées supprimées par défaut
        if not include_deleted:
            query.append("AND deleted_at IS NULL")

        if category_filter and category_filter not in ("", "All", "Toutes"):
            query.append("AND category = ?")
            params.append(category_filter)

        if search_text:
            like = f"%{search_text}%"
            query.append("AND (title LIKE ? OR username LIKE ? OR url LIKE ?)")
            params.extend([like, like, like])

        query.append("ORDER BY title COLLATE NOCASE")

        cursor = self.conn.cursor()
        cursor.execute(" ".join(query), params)
        rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_entries_for_duplicates(self) -> list[PasswordRecord]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, title, username, password_data, url, notes, category, tags, "
            "password_validity_days, created_at, modified_at, last_changed, usage_count "
            "FROM passwords"
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def increment_usage_count(self, entry_id: int, amount: int = 1) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE passwords
            SET usage_count = COALESCE(usage_count, 0) + ?,
                modified_at = CURRENT_TIMESTAMP
            WHERE id = ? AND deleted_at IS NULL
            """,
            (amount, entry_id),
        )
        self.conn.commit()
        self._has_changes = True

    # ------------------------------------------------------------------
    # Méta
    # ------------------------------------------------------------------
    def has_unsaved_changes(self) -> bool:
        return self._has_changes

    def mark_as_saved(self) -> None:
        self._has_changes = False

    def get_password_last_changed(self, entry_id: int) -> datetime | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT last_changed FROM passwords WHERE id=?", (entry_id,))
        result = cursor.fetchone()
        if not result or not result[0]:
            return None
        return self._parse_timestamp(result[0])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _row_to_record(self, row: sqlite3.Row) -> PasswordRecord:
        tags = []
        if row[7]:
            try:
                tags = json.loads(row[7])
            except (json.JSONDecodeError, TypeError):
                logger.debug("Invalid tags for entry %s", row[0])
        notes_data = None
        if row[5]:
            try:
                notes_data = json.loads(row[5])
            except (json.JSONDecodeError, TypeError):
                logger.debug("Invalid notes for entry %s", row[0])

        password_data = json.loads(row[3]) if row[3] else {}

        return PasswordRecord(
            id=row[0],
            title=row[1],
            username=row[2] or "",
            password_data=password_data,
            url=row[4] or "",
            notes_data=notes_data,
            category=row[6] or "",
            tags=tags,
            password_validity_days=row[8],
            usage_count=int(row[12] or 0),
            created_at=self._parse_timestamp(row[9]),
            modified_at=self._parse_timestamp(row[10]),
            last_changed=self._parse_timestamp(row[11]),
        )

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
