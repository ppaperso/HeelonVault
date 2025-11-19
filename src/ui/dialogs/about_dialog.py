"""
Dialogue 'À propos' de l'application
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
from src.version import get_version_info


def show_about_dialog(parent):
    """Affiche le dialogue À propos
    
    Args:
        parent: Fenêtre parente
    """
    version_info = get_version_info()
    
    # Créer le dialogue
    about = Adw.AboutDialog()
    
    # Informations de base
    about.set_application_name(version_info['app_name'])
    about.set_version(version_info['version'])
    about.set_comments(version_info['description'])
    about.set_copyright(version_info['copyright'])
    about.set_license_type(Gtk.License.MIT_X11)
    
    # Icône
    about.set_application_icon("dialog-password-symbolic")
    
    # Développeurs
    about.set_developers([version_info['author']])
    
    # Site web (optionnel)
    # about.set_website("https://github.com/...")
    # about.set_website_label("Site web du projet")
    
    # Description détaillée
    details = """Gestionnaire de mots de passe sécurisé pour Linux

🔒 Fonctionnalités principales :
• Chiffrement AES-256-GCM
• Gestion multi-utilisateurs
• Import/Export CSV
• Générateur de mots de passe
• Organisation par catégories et tags
• Protection contre les attaques par force brute

🛠️ Technologies :
• Python 3.8+
• GTK4 + Libadwaita
• Cryptography (AES-256)
• SQLite3

📖 Documentation disponible dans le dossier docs/"""
    
    about.set_release_notes(details)
    
    # Afficher le dialogue
    about.present(parent)
