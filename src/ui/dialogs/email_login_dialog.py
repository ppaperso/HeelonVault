"""Dialog de connexion par email (remplace UserSelectionDialog).

Ce module fournit une interface pour :
- Saisir l'adresse email
- Saisir le mot de passe maître
- Lancer l'authentification
"""

import logging

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from src.version import __app_name__  # noqa: E402

logger = logging.getLogger(__name__)


class EmailLoginDialog(Adw.Window):
    """Dialog de connexion par email."""

    def __init__(self, parent, auth_service, login_tracker, **kwargs):
        """Initialise le dialog de connexion.

        Args:
            parent: Fenêtre parente
            auth_service: Service d'authentification
            login_tracker: Tracker des tentatives de connexion
        """
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(500, 500)
        self.set_title("Connexion")

        self.auth_service = auth_service
        self.login_tracker = login_tracker

        # État
        self.user_info = None
        self.master_password = None
        self.authenticated = False

        # Construction de l'UI
        self._build_ui()

    def _build_ui(self):
        """Construit l'interface utilisateur."""
        # Container principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header bar
        header = Adw.HeaderBar()
        main_box.append(header)

        # Content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content_box.set_margin_top(30)
        content_box.set_margin_bottom(30)
        content_box.set_margin_start(30)
        content_box.set_margin_end(30)
        content_box.set_vexpand(True)
        content_box.set_valign(Gtk.Align.CENTER)
        main_box.append(content_box)

        # Logo et titre
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        header_box.set_halign(Gtk.Align.CENTER)
        content_box.append(header_box)

        icon_label = Gtk.Label()
        icon_label.set_markup("<span size='xx-large'>🔐</span>")
        header_box.append(icon_label)

        title_label = Gtk.Label()
        title_label.set_markup(
            f"<span size='x-large' weight='bold'>{__app_name__}</span>"
        )
        header_box.append(title_label)

        subtitle_label = Gtk.Label()
        subtitle_label.set_markup("<span size='small'>Authentification sécurisée avec 2FA</span>")
        subtitle_label.add_css_class("dim-label")
        header_box.append(subtitle_label)

        # Groupe de saisie
        input_group = Adw.PreferencesGroup()
        input_group.set_margin_top(30)
        content_box.append(input_group)

        # Row pour l'email
        email_row = Adw.ActionRow()
        email_row.set_title("📧 Adresse email")
        input_group.add(email_row)

        self.email_entry = Gtk.Entry()
        self.email_entry.set_placeholder_text("votre.email@example.com")
        self.email_entry.set_hexpand(True)
        self.email_entry.set_input_purpose(Gtk.InputPurpose.EMAIL)
        self.email_entry.connect("changed", self._on_input_changed)
        self.email_entry.connect("activate", lambda e: self.password_entry.grab_focus())
        email_row.add_suffix(self.email_entry)

        # Row pour le mot de passe
        password_row = Adw.PasswordEntryRow()
        password_row.set_title("🔑 Mot de passe maître")
        self.password_entry = password_row
        password_row.connect("changed", self._on_input_changed)
        password_row.connect("activate", lambda e: self._on_login_clicked(None))
        input_group.add(password_row)

        # Message de statut
        self.status_label = Gtk.Label()
        self.status_label.set_margin_top(15)
        self.status_label.set_wrap(True)
        content_box.append(self.status_label)

        # Bouton de connexion
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(20)
        content_box.append(button_box)

        self.login_button = Gtk.Button(label="Se connecter")
        self.login_button.add_css_class("suggested-action")
        self.login_button.add_css_class("pill")
        self.login_button.set_size_request(200, 50)
        self.login_button.set_sensitive(False)
        self.login_button.connect("clicked", self._on_login_clicked)
        button_box.append(self.login_button)

        # Info sécurité
        security_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        security_box.set_margin_top(30)
        content_box.append(security_box)

        security_label = Gtk.Label()
        security_label.set_markup(
            "<span size='small'>🔒 Chiffrement AES-256-GCM • 2FA Obligatoire</span>"
        )
        security_label.add_css_class("dim-label")
        security_box.append(security_label)

        # Focus sur l'email au démarrage
        self.email_entry.grab_focus()

    def _on_input_changed(self, widget):
        """Appelé quand les champs changent."""
        email = self.email_entry.get_text().strip()
        password = self.password_entry.get_text().strip()

        # Activer le bouton si les deux champs sont remplis
        can_login = len(email) > 0 and len(password) > 0
        self.login_button.set_sensitive(can_login)

        # Effacer le statut
        self.status_label.set_text("")

    def _on_login_clicked(self, button):
        """Tente la connexion."""
        email = self.email_entry.get_text().strip()
        password = self.password_entry.get_text().strip()

        if not email or not password:
            self._show_status("❌ Veuillez remplir tous les champs.", "error")
            return

        # Hasher l'email pour le tracker
        email_hash = self.auth_service.hash_email(email)

        # Vérifier le rate limiting
        can_attempt, wait_time = self.login_tracker.check_can_attempt(email_hash)
        if not can_attempt:
            if wait_time >= 3600:
                minutes = wait_time // 60
                self._show_status(
                    f"🔒 Trop de tentatives. Veuillez réessayer dans {minutes} minutes.",
                    "error"
                )
            else:
                self._show_status(
                    f"⏳ Veuillez attendre {wait_time} seconde(s) avant de réessayer.",
                    "warning"
                )
            return

        # Désactiver les contrôles pendant l'authentification
        self._set_loading(True)
        self._show_status("🔄 Authentification en cours...", "info")

        # Utiliser un timeout pour ne pas bloquer l'UI
        GLib.timeout_add(100, lambda: self._authenticate(email, password, email_hash))

    def _authenticate(self, email: str, password: str, email_hash: str):
        """Effectue l'authentification (appelé de manière asynchrone).

        Args:
            email: Email de l'utilisateur
            password: Mot de passe
            email_hash: Hash de l'email pour le tracker
        """
        try:
            # Tenter l'authentification
            user_info = self.auth_service.authenticate_by_email(email, password, enforce_delay=True)

            if user_info:
                # Succès
                self.user_info = user_info
                self.master_password = password
                self.authenticated = True

                self.login_tracker.record_successful_attempt(email_hash)
                self._show_status("✅ Authentification réussie !", "success")

                logger.info(f"Authentification réussie pour {email}")

                # Fermer après un court délai
                GLib.timeout_add(500, lambda: self.close())
            else:
                # Échec
                self.login_tracker.record_failed_attempt(email_hash)
                self._show_status("❌ Email ou mot de passe incorrect.", "error")
                self.password_entry.set_text("")
                self.password_entry.grab_focus()
                self._set_loading(False)

        except Exception as e:
            logger.exception("Erreur lors de l'authentification")
            self._show_status(f"❌ Erreur : {e}", "error")
            self._set_loading(False)

        return False  # Ne pas répéter le timeout

    def _set_loading(self, loading: bool):
        """Active/désactive l'état de chargement.

        Args:
            loading: True pour activer, False pour désactiver
        """
        self.email_entry.set_sensitive(not loading)
        self.password_entry.set_sensitive(not loading)
        self.login_button.set_sensitive(not loading)

        if loading:
            self.login_button.set_label("Connexion...")
        else:
            self.login_button.set_label("Se connecter")

    def _show_status(self, message: str, status_type: str = "info"):
        """Affiche un message de statut.

        Args:
            message: Message à afficher
            status_type: 'info', 'success', 'error', 'warning'
        """
        self.status_label.set_text(message)

        # Réinitialiser les classes CSS
        self.status_label.remove_css_class("success")
        self.status_label.remove_css_class("error")
        self.status_label.remove_css_class("warning")

        # Ajouter la classe appropriée
        if status_type == "success":
            self.status_label.add_css_class("success")
        elif status_type == "error":
            self.status_label.add_css_class("error")
        elif status_type == "warning":
            self.status_label.add_css_class("warning")

    def get_user_info(self):
        """Retourne les informations utilisateur si authentifié."""
        return self.user_info if self.authenticated else None

    def get_master_password(self):
        """Retourne le mot de passe maître si authentifié."""
        return self.master_password if self.authenticated else None
