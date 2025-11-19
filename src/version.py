"""
Informations de version de l'application
"""

__version__ = "0.1.0-beta"
__app_name__ = "Gestionnaire de Mots de Passe"
__description__ = "Gestionnaire de mots de passe sécurisé pour Linux"
__author__ = "Password Manager Team"
__license__ = "MIT"
__copyright__ = "Copyright © 2025"

def get_version():
    """Retourne la version de l'application"""
    return __version__

def get_version_info():
    """Retourne toutes les informations de version"""
    return {
        'version': __version__,
        'app_name': __app_name__,
        'description': __description__,
        'author': __author__,
        'license': __license__,
        'copyright': __copyright__
    }
