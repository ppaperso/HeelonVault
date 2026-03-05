"""
Informations de version de l'application
"""

__version__ = "0.4.0-Bêta"
__app_name__ = "HeelonVault"
__app_icon__ = "🔐"
__app_display_name__ = f"{__app_icon__} {__app_name__}"
__app_id__ = "org.heelonys.heelonvault"
__description__ = "Gestionnaire de mots de passe sécurisé pour Linux"
__author__ = "HEELONYS"
__website__ = "https://github.com/heelonys/heelonvault"
__license__ = "MIT"
__copyright__ = "Copyright © 2026"


def get_version() -> str:
    """Retourne la version de l'application"""
    return __version__


def get_version_info() -> dict:
    """Retourne toutes les informations de version"""
    return {
        "version": __version__,
        "app_name": __app_name__,
        "app_icon": __app_icon__,
        "app_display_name": __app_display_name__,
        "app_id": __app_id__,
        "description": __description__,
        "author": __author__,
        "website": __website__,
        "license": __license__,
        "copyright": __copyright__,
    }
