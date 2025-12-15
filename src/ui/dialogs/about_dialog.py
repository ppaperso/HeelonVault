"""
Dialogue 'À propos' de l'application
"""

import os

from src.version import get_version_info

import gi  # type: ignore[import]

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw  # noqa: E402


def show_about_dialog(parent):
    """Affiche le dialogue À propos
    
    Args:
        parent: Fenêtre parente
    """
    version_info = get_version_info()
    
    # Créer le dialogue
    about = Adw.AboutDialog()
    
    # Informations de base avec mode dev si applicable
    version_text = version_info['version']
    if os.environ.get('DEV_MODE', '').lower() in ('1', 'true', 'yes'):
        version_text += " (Mode Développement)"
    
    about.set_application_name(version_info['app_name'])
    about.set_version(version_text)
    
    # Description enrichie avec les fonctionnalités
    description_enrichie = """Gestionnaire de mots de passe sécurisé pour Linux

🔒 Chiffrement AES-256-GCM • Gestion multi-utilisateurs
📥 Import/Export CSV • 🎲 Générateur sécurisé
🏷️ Organisation par catégories et tags"""
    
    about.set_comments(description_enrichie)
    about.set_copyright(version_info['copyright'])
    about.set_license_type(Gtk.License.MIT_X11)
    
    # Icône
    about.set_application_icon("dialog-password-symbolic")
    
    # Développeurs
    about.set_developers([version_info['author']])
    
    # Site web (optionnel)
    # about.set_website("https://github.com/ppaperso/Gestionnaire_mot_passe")
    # about.set_website_label("GitHub")
    
    # Afficher le dialogue
    about.present(parent)
