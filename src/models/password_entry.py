"""
Modèle de données pour une entrée de mot de passe.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


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
    id: Optional[int] = None
    url: str = ""
    notes: str = ""
    category: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    
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
    notes_data: Optional[dict] = None
