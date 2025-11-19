"""
Modèle de données pour un utilisateur du gestionnaire de mots de passe.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """Représente un utilisateur du système.
    
    Attributes:
        id: Identifiant unique de l'utilisateur
        username: Nom d'utilisateur unique
        role: Rôle de l'utilisateur ('admin' ou 'user')
        created_at: Date de création du compte
        last_login: Date de dernière connexion
    """
    id: int
    username: str
    role: str = 'user'
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    def is_admin(self) -> bool:
        """Vérifie si l'utilisateur est administrateur.
        
        Returns:
            bool: True si l'utilisateur est admin, False sinon
        """
        return self.role == 'admin'
    
    def __str__(self) -> str:
        return f"User(id={self.id}, username='{self.username}', role='{self.role}')"


@dataclass
class UserCredentials:
    """Représente les credentials d'un utilisateur pour l'authentification.
    
    Attributes:
        username: Nom d'utilisateur
        password_hash: Hash du mot de passe
        salt: Salt utilisé pour le hachage
    """
    username: str
    password_hash: str
    salt: bytes
