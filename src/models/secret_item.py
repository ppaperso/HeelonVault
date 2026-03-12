"""Modèles de domaine pour les secrets non-password."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SecretItem:
    """Représente un secret en mémoire côté domaine/service.

    Note: `payload` est volontairement exclu du `repr` pour éviter toute fuite
    accidentelle dans les logs et traces de debug.
    """

    secret_type: str
    title: str
    metadata: dict[str, Any]
    payload: str | bytes = field(repr=False)
    tags: list[str] = field(default_factory=list)
    blob_storage: str = "inline"
    expires_at: datetime | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    usage_count: int = 0
    id: int | None = None
    item_uuid: str | None = None

    def clear_payload(self) -> None:
        """Nettoie le payload en mémoire (best effort hygiène mémoire)."""
        self.payload = ""


@dataclass(slots=True)
class SecretRecord:
    """Représente une ligne persistée SQLite pour `secret_items`."""

    secret_type: str
    title: str
    metadata: dict[str, Any]
    secret_blob: bytes = field(repr=False)
    tags: list[str] = field(default_factory=list)
    blob_storage: str = "inline"
    expires_at: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    usage_count: int = 0
    id: int | None = None
    item_uuid: str | None = None
