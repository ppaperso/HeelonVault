"""Service applicatif pour la gestion des entrées de mots de passe."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from cryptography.exceptions import InvalidTag

from src.i18n import _
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
        category_filter: str | None = None,
        tag_filter: str | None = None,
        search_text: str | None = None,
    ) -> list[PasswordEntry]:
        records = self.repository.list_entries(
            category_filter=category_filter,
            search_text=search_text,
        )
        entries = [self._record_to_entry(record) for record in records]

        if tag_filter:
            entries = [entry for entry in entries if tag_filter in entry.tags]
        return entries

    def get_entry(self, entry_id: int) -> PasswordEntry | None:
        record = self.repository.get_entry(entry_id)
        if not record:
            return None
        return self._record_to_entry(record)

    def create_entry(self, entry: PasswordEntry) -> int:
        record = self._encrypt_entry(entry)
        entry_id = self.repository.insert_entry(record)
        logger.info("PasswordService: entry created (%s)", entry_id)
        return entry_id

    def update_entry(self, entry: PasswordEntry) -> None:
        if entry.id is None:
            raise ValueError(_("update_entry requires an identifier"))

        current = self.repository.get_entry(entry.id)
        if not current:
            raise ValueError(_("Entry %(id)s not found") % {"id": entry.id})

        password_changed = self._has_password_changed(current, entry.password)
        record = self._encrypt_entry(entry)
        record.id = entry.id
        self.repository.update_entry(record, password_changed=password_changed)
        logger.info("PasswordService: entry %s updated", entry.id)

    def delete_entry(self, entry_id: int) -> None:
        """Déplace une entrée vers la corbeille."""
        self.repository.delete_entry(entry_id)
        logger.info("PasswordService: entry %s moved to trash", entry_id)

    def restore_entry(self, entry_id: int) -> None:
        """Restaure une entrée de la corbeille."""
        self.repository.restore_entry(entry_id)
        logger.info("PasswordService: entry %s restored", entry_id)

    def delete_entry_permanently(self, entry_id: int) -> None:
        """Supprime définitivement une entrée."""
        self.repository.delete_entry_permanently(entry_id)
        logger.info("PasswordService: entry %s permanently deleted", entry_id)

    def list_trash(self) -> list[PasswordEntry]:
        """Liste les entrées dans la corbeille."""
        records = self.repository.list_trash()
        return [self._record_to_entry(record) for record in records]

    def empty_trash(self) -> int:
        """Vide complètement la corbeille. Retourne le nombre d'entrées supprimées."""
        count = self.repository.empty_trash()
        logger.info("PasswordService: trash emptied (%d entries)", count)
        return count

    # ------------------------------------------------------------------
    # Métadonnées
    # ------------------------------------------------------------------
    def list_categories(self) -> list[Category]:
        return self.repository.list_categories()

    def add_category(self, category: Category) -> None:
        self.repository.add_category(category)

    def list_tags(self) -> list[str]:
        return self.repository.list_tags()

    # ------------------------------------------------------------------
    # Analyse & outils
    # ------------------------------------------------------------------
    def detect_duplicates(self) -> dict[int, list[int]]:
        """Retourne un mapping entry_id -> autres ids partageant le même mot de passe."""
        duplicates: dict[str, list[int]] = {}
        for record in self.repository.list_entries_for_duplicates():
            try:
                password = self.crypto.decrypt(record.password_data)
            except (InvalidTag, KeyError, ValueError, TypeError) as e:
                logger.debug(
                    "Unable to decrypt entry %s: %s",
                    record.id,
                    e,
                )
                continue
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            duplicates.setdefault(pwd_hash, []).append(record.id or 0)

        result: dict[int, list[int]] = {}
        for ids in duplicates.values():
            if len(ids) <= 1:
                continue
            for entry_id in ids:
                result[entry_id] = [other for other in ids if other != entry_id]
        return result

    def get_password_age_days(self, entry_id: int) -> int | None:
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
        except (InvalidTag, KeyError, ValueError, TypeError):
            password = ""

        notes = ""
        if record.notes_data:
            try:
                notes = self.crypto.decrypt(record.notes_data)
            except (InvalidTag, KeyError, ValueError, TypeError):
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
            password_validity_days=record.password_validity_days,
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
            password_validity_days=entry.password_validity_days,
        )

    def _has_password_changed(self, record: PasswordRecord, new_password: str) -> bool:
        try:
            current_password = self.crypto.decrypt(record.password_data)
        except (InvalidTag, KeyError, ValueError, TypeError):
            return True
        return current_password != new_password
