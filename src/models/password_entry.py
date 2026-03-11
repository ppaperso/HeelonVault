"""
Modèle de données pour une entrée de mot de passe.
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PasswordEntry:
    """Représente une entrée de mot de passe stockée.

    Attributes:
        id: Identifiant unique de l'entrée
        title: Titre/nom de l'entrée
        username: Nom d'utilisateur associé
        password: Mot de passe (en clair pour l'utilisation, chiffré en base)
        url: URL du service
        notes: Notes additionnelles
        category: Catégorie de l'entrée
        tags: Liste de tags
        created_at: Date de création
        modified_at: Date de dernière modification
    """
    title: str
    username: str
    password: str
    id: int | None = None
    url: str = ""
    notes: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    password_validity_days: int | None = 90
    created_at: datetime | None = None
    modified_at: datetime | None = None
    usage_count: int = 0
    strength_score: int = -1

    def __str__(self) -> str:
        return f"PasswordEntry(id={self.id}, title='{self.title}', category='{self.category}')"

    def matches_search(self, search_text: str) -> bool:
        """Vérifie si l'entrée correspond à un texte de recherche.

        Args:
            search_text: Texte à rechercher

        Returns:
            bool: True si l'entrée correspond
        """
        search_lower = search_text.lower()
        return (
            search_lower in self.title.lower() or
            search_lower in self.username.lower() or
            search_lower in self.url.lower()
        )

    def has_tag(self, tag: str) -> bool:
        """Vérifie si l'entrée possède un tag spécifique.

        Args:
            tag: Tag à vérifier

        Returns:
            bool: True si le tag existe
        """
        return tag in self.tags


@dataclass
class EncryptedPasswordEntry:
    """Représente une entrée de mot de passe avec données chiffrées.

    Attributes:
        password_data: Données du mot de passe chiffré (dict avec nonce et ciphertext)
        notes_data: Données des notes chiffrées
    """
    password_data: dict
    notes_data: dict | None = None


@dataclass
class PasswordRecord:
    """Représente une entrée persistée dans SQLite (données chiffrées)."""

    title: str
    username: str
    password_data: dict[str, str]
    id: int | None = None
    url: str = ""
    notes_data: dict[str, str] | None = None
    category: str = ""
    tags: list[str] = field(default_factory=list)
    password_validity_days: int | None = 90
    created_at: datetime | None = None
    modified_at: datetime | None = None
    last_changed: datetime | None = None
    usage_count: int = 0
