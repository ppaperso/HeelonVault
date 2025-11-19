"""
Modèle de données pour les catégories.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Category:
    """Représente une catégorie d'entrées de mots de passe.
    
    Attributes:
        name: Nom unique de la catégorie
        color: Couleur hexadécimale pour l'affichage
        icon: Nom de l'icône symbolic GTK
        id: Identifiant unique (optionnel)
    """
    name: str
    color: str = "#999999"
    icon: str = "folder-symbolic"
    id: Optional[int] = None
    
    def __str__(self) -> str:
        return f"Category(name='{self.name}', color='{self.color}')"


# Catégories par défaut
DEFAULT_CATEGORIES = [
    Category(name="Personnel", color="#3584e4", icon="user-home-symbolic"),
    Category(name="Travail", color="#f66151", icon="briefcase-symbolic"),
    Category(name="Finance", color="#33d17a", icon="credit-card-symbolic"),
    Category(name="Social", color="#9141ac", icon="user-available-symbolic"),
    Category(name="Autres", color="#986a44", icon="folder-symbolic"),
]
