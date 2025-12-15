"""Service applicatif pour la gestion des entrées de mots de passe."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional

from src.models.category import Category
from src.models.password_entry import PasswordEntry, PasswordRecord
from src.repositories.password_repository import PasswordRepository
from src.services.crypto_service import CryptoService

logger = logging.getLogger(__name__)


class PasswordService:
    """Expose des opérations haut niveau pour la base de mots de passe."""

    def __init__(self, repository: PasswordRepository, crypto: CryptoService):
        self.repository = repository
        self.crypto = crypto

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list_entries(
        self,
        *,
        category_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        search_text: Optional[str] = None,
    ) -> List[PasswordEntry]:
        records = self.repository.list_entries(
            category_filter=category_filter,
            search_text=search_text,
        )
        entries = [self._record_to_entry(record) for record in records]

        if tag_filter:
            entries = [entry for entry in entries if tag_filter in entry.tags]
        return entries

    def get_entry(self, entry_id: int) -> Optional[PasswordEntry]:
        record = self.repository.get_entry(entry_id)
        if not record:
            return None
        return self._record_to_entry(record)

    def create_entry(self, entry: PasswordEntry) -> int:
        record = self._encrypt_entry(entry)
        entry_id = self.repository.insert_entry(record)
        logger.info("PasswordService: entrée créée (%s)", entry_id)
        return entry_id

    def update_entry(self, entry: PasswordEntry) -> None:
        if entry.id is None:
            raise ValueError("update_entry nécessite un identifiant")

        current = self.repository.get_entry(entry.id)
        if not current:
            raise ValueError(f"Entrée {entry.id} introuvable")

        password_changed = self._has_password_changed(current, entry.password)
        record = self._encrypt_entry(entry)
        record.id = entry.id
        self.repository.update_entry(record, password_changed=password_changed)
        logger.info("PasswordService: entrée %s mise à jour", entry.id)

    def delete_entry(self, entry_id: int) -> None:
        self.repository.delete_entry(entry_id)
        logger.info("PasswordService: entrée %s supprimée", entry_id)

    # ------------------------------------------------------------------
    # Métadonnées
    # ------------------------------------------------------------------
    def list_categories(self) -> List[Category]:
        return self.repository.list_categories()

    def add_category(self, category: Category) -> None:
        self.repository.add_category(category)

    def list_tags(self) -> List[str]:
        return self.repository.list_tags()

    # ------------------------------------------------------------------
    # Analyse & outils
    # ------------------------------------------------------------------
    def detect_duplicates(self) -> Dict[int, List[int]]:
        """Retourne un mapping entry_id -> autres ids partageant le même mot de passe."""
        duplicates: Dict[str, List[int]] = {}
        for record in self.repository.list_entries_for_duplicates():
            try:
                password = self.crypto.decrypt(record.password_data)
            except Exception:
                continue
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            duplicates.setdefault(pwd_hash, []).append(record.id or 0)

        result: Dict[int, List[int]] = {}
        for ids in duplicates.values():
            if len(ids) <= 1:
                continue
            for entry_id in ids:
                result[entry_id] = [other for other in ids if other != entry_id]
        return result

    def get_password_age_days(self, entry_id: int) -> Optional[int]:
        last_changed = self.repository.get_password_last_changed(entry_id)
        if not last_changed:
            return None
        return (datetime.now() - last_changed).days

    # ------------------------------------------------------------------
    # Persistance & cycle de vie
    # ------------------------------------------------------------------
    def has_unsaved_changes(self) -> bool:
        return self.repository.has_unsaved_changes()

    def mark_as_saved(self) -> None:
        self.repository.mark_as_saved()

    def close(self) -> None:
        self.repository.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _record_to_entry(self, record: PasswordRecord) -> PasswordEntry:
        try:
            password = self.crypto.decrypt(record.password_data)
        except Exception:
            password = ""

        notes = ""
        if record.notes_data:
            try:
                notes = self.crypto.decrypt(record.notes_data)
            except Exception:
                notes = ""

        return PasswordEntry(
            id=record.id,
            title=record.title,
            username=record.username,
            password=password,
            url=record.url,
            notes=notes,
            category=record.category,
            tags=record.tags,
            created_at=record.created_at,
            modified_at=record.modified_at,
        )

    def _encrypt_entry(self, entry: PasswordEntry) -> PasswordRecord:
        password_data = self.crypto.encrypt(entry.password)
        notes_data = self.crypto.encrypt(entry.notes) if entry.notes else None
        return PasswordRecord(
            id=entry.id,
            title=entry.title,
            username=entry.username,
            password_data=password_data,
            url=entry.url,
            notes_data=notes_data,
            category=entry.category,
            tags=entry.tags,
        )

    def _has_password_changed(self, record: PasswordRecord, new_password: str) -> bool:
        try:
            current_password = self.crypto.decrypt(record.password_data)
        except Exception:
            return True
        return current_password != new_password