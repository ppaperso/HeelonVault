"""Dialogue de sélection d'utilisateur au démarrage de l'application."""

import gi  # type: ignore[import]

from src.i18n import _
from src.version import __app_display_name__

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk  # noqa: E402


class UserSelectionDialog(Adw.ApplicationWindow):
    """Dialogue de sélection d'utilisateur.

    Premier écran affiché au lancement de l'application.
    Liste tous les utilisateurs disponibles sans possibilité d'en créer de nouveaux.
    Seul un admin peut créer de nouveaux comptes via le menu de gestion.
    """

    def __init__(self, app, user_manager, callback):
        """Initialise le dialogue de sélection.

        Args:
            app: Instance de l'application GTK
            user_manager: Instance du service d'authentification
            callback: Fonction appelée après authentification réussie
        """
        super().__init__(application=app)
        self.set_default_size(450, 500)
        self.set_title(_("Sélection d'utilisateur"))
        self.user_manager = user_manager
        self.callback = callback
        self.app_ref = app

        self._build_ui()
        self.load_users()

    def _build_ui(self):
        """Construit l'interface utilisateur."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_top(20)
        content.set_margin_bottom(40)

        # Titre
        title = Gtk.Label(label=__app_display_name__)
        title.set_css_classes(['title-1'])
        content.append(title)

        subtitle = Gtk.Label(label=_("Sélectionnez votre compte"))
        subtitle.set_css_classes(['title-4'])
        content.append(subtitle)

        # Liste des utilisateurs
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)

        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(['boxed-list'])
        self.users_listbox.connect("row-activated", self.on_user_selected)
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)

        # Note informative
        info = Gtk.Label(
            label=_("ℹ️ Pour créer un nouveau compte, connectez-vous en tant qu'administrateur")
        )
        info.set_css_classes(['caption', 'dim-label'])
        info.set_wrap(True)
        content.append(info)

        box.append(content)
        self.set_content(box)

    def load_users(self):
        """Charge la liste des utilisateurs depuis la base de données."""
        self.users_listbox.remove_all()

        users = self.user_manager.get_all_users()
        for username, role, _created_at, last_login in users:
            row = Gtk.ListBoxRow()
            row.username = username

            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            user_box.set_margin_start(12)
            user_box.set_margin_end(12)
            user_box.set_margin_top(12)
            user_box.set_margin_bottom(12)

            # Icône
            icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            icon.set_pixel_size(32)
            user_box.append(icon)

            # Infos utilisateur
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_hexpand(True)

            name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name_label = Gtk.Label(label=username, xalign=0)
            name_label.set_css_classes(['title-4'])
            name_box.append(name_label)

            badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            if role == 'admin':
                admin_label = Gtk.Label(label=_("Admin"))
                admin_label.set_css_classes(['caption', 'accent'])
                badges_box.append(admin_label)

            if badges_box.get_first_child() is not None:
                name_box.append(badges_box)

            info_box.append(name_box)

            if last_login:
                last_login_label = Gtk.Label(
                    label=_("Dernière connexion: %s") % last_login[:16],
                    xalign=0
                )
                last_login_label.set_css_classes(['caption', 'dim-label'])
                info_box.append(last_login_label)

            user_box.append(info_box)

            # Flèche
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            user_box.append(arrow)

            row.set_child(user_box)
            self.users_listbox.append(row)

    def on_user_selected(self, _listbox, row):
        """Callback quand un utilisateur est sélectionné.

        Ouvre le dialogue de connexion pour demander le mot de passe.

        Args:
            listbox: Liste des utilisateurs
            row: Ligne sélectionnée
        """
        from .login_dialog import LoginDialog
        username = row.username
        LoginDialog(self, self.user_manager, username, self.callback).present()
