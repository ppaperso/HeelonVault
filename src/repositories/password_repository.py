"""Couche d'accès aux données pour les entrées de mots de passe."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.models.category import Category, DEFAULT_CATEGORIES
from src.models.password_entry import PasswordRecord

logger = logging.getLogger(__name__)


class PasswordRepository:
    """Encapsule toutes les requêtes SQLite liées aux mots de passe."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._has_changes = False
        self._init_db()

        try:
            db_path.chmod(0o600)
        except Exception:
            logger.debug("Impossible de définir les permissions sur %s", db_path)

        logger.debug("PasswordRepository initialisé sur %s", db_path)

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_changed TIMESTAMP
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

        self.conn.commit()
        logger.debug("Schéma SQLite vérifié pour %s", self.db_path)

    def close(self) -> None:
        self.conn.close()
        logger.debug("PasswordRepository: connexion fermée pour %s", self.db_path)

    # ------------------------------------------------------------------
    # Catégories & tags
    # ------------------------------------------------------------------
    def list_categories(self) -> List[Category]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, color, icon FROM categories ORDER BY name")
        categories = [
            Category(name=row[1], color=row[2] or "#999999", icon=row[3] or "folder-symbolic", id=row[0])
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

    def list_tags(self) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT tags FROM passwords WHERE tags IS NOT NULL AND tags != ''")
        tag_set = set()
        for (tags_json,) in cursor.fetchall():
            try:
                tags = json.loads(tags_json)
                tag_set.update(tags)
            except Exception:
                logger.debug("Tags invalides ignorés: %s", tags_json)
        return sorted(tag_set)

    # ------------------------------------------------------------------
    # CRUD entrées
    # ------------------------------------------------------------------
    def insert_entry(self, record: PasswordRecord) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO passwords (
                title, username, password_data, url, notes, category, tags, last_changed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                record.title,
                record.username,
                json.dumps(record.password_data),
                record.url,
                json.dumps(record.notes_data) if record.notes_data else None,
                record.category,
                json.dumps(record.tags if record.tags else []),
            ),
        )
        self.conn.commit()
        self._has_changes = True
        entry_id = cursor.lastrowid
        if entry_id is None:
            raise RuntimeError("Impossible de récupérer l'identifiant de l'entrée insérée")
        logger.debug("Entrée %s ajoutée", entry_id)
        return int(entry_id)

    def update_entry(self, record: PasswordRecord, *, password_changed: bool) -> None:
        if record.id is None:
            raise ValueError("update_entry nécessite un identifiant")

        cursor = self.conn.cursor()
        if password_changed:
            cursor.execute(
                """
                UPDATE passwords
                SET title=?, username=?, password_data=?, url=?, notes=?, category=?, tags=?,
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
                    record.id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE passwords
                SET title=?, username=?, password_data=?, url=?, notes=?, category=?, tags=?,
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
                    record.id,
                ),
            )
        self.conn.commit()
        self._has_changes = True
        logger.debug("Entrée %s mise à jour (mdp changé=%s)", record.id, password_changed)

    def delete_entry(self, entry_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM passwords WHERE id=?", (entry_id,))
        self.conn.commit()
        self._has_changes = True
        logger.debug("Entrée %s supprimée", entry_id)

    # ------------------------------------------------------------------
    # Lecture & requêtes
    # ------------------------------------------------------------------
    def get_entry(self, entry_id: int) -> Optional[PasswordRecord]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, title, username, password_data, url, notes, category, tags,
                   created_at, modified_at, last_changed
            FROM passwords WHERE id=?
            """,
            (entry_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_entries(
        self,
        *,
        category_filter: Optional[str] = None,
        search_text: Optional[str] = None,
    ) -> List[PasswordRecord]:
        query = [
            "SELECT id, title, username, password_data, url, notes, category, tags,",
            "created_at, modified_at, last_changed FROM passwords WHERE 1 = 1",
        ]
        params: List[str] = []

        if category_filter and category_filter not in ("", "Toutes"):
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

    def list_entries_for_duplicates(self) -> List[PasswordRecord]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, title, username, password_data, url, notes, category, tags, created_at, modified_at, last_changed FROM passwords"
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Méta
    # ------------------------------------------------------------------
    def has_unsaved_changes(self) -> bool:
        return self._has_changes

    def mark_as_saved(self) -> None:
        self._has_changes = False

    def get_password_last_changed(self, entry_id: int) -> Optional[datetime]:
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
            except Exception:
                logger.debug("Tags invalides pour l'entrée %s", row[0])
        notes_data = None
        if row[5]:
            try:
                notes_data = json.loads(row[5])
            except Exception:
                logger.debug("Notes invalides pour l'entrée %s", row[0])

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
            created_at=self._parse_timestamp(row[8]),
            modified_at=self._parse_timestamp(row[9]),
            last_changed=self._parse_timestamp(row[10]),
        )

    @staticmethod
    def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None