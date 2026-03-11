"""Modèle de données pour un vault (coffre-fort) utilisateur."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Vault:
    """Représente un vault associé à un utilisateur.

    Un vault correspond à une base de données de mots de passe indépendante
    (passwords_{uuid}.db). Chaque utilisateur possède au moins un vault
    marqué is_default=True (le vault "Personal" créé à l'inscription).
    """

    id: int
    user_id: int
    name: str
    uuid: str
    is_default: bool = False
    created_at: datetime | None = None

    def __str__(self) -> str:
        default_marker = " [default]" if self.is_default else ""
        return f"Vault(id={self.id}, name={self.name!r}, uuid={self.uuid}{default_marker})"
