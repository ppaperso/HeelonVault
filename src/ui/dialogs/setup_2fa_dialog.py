"""Dialog de configuration de l'authentification à double facteur (2FA).

Ce module fournit une interface pour :
- Afficher le QR code pour l'application d'authentification
- Vérifier le code TOTP saisi
- Afficher et confirmer les codes de secours
"""

import logging

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, GdkPixbuf, GLib, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


class Setup2FADialog(Adw.Window):
    """Dialog pour configurer l'authentification à double facteur.

    Processus :
    1. Génération du secret TOTP et affichage du QR code
    2. Vérification du code TOTP saisi par l'utilisateur
    3. Génération et affichage des codes de secours
    4. Confirmation finale
    """

    def __init__(
        self,
        parent,
        totp_service,
        auth_service,
        user_info,
        reconfiguration: bool = False,
        **kwargs,
    ):
        """Initialise le dialog de configuration 2FA.

        Args:
            parent: Fenêtre parente
            totp_service: Service TOTP
            auth_service: Service d'authentification
            user_info: Informations de l'utilisateur (dict)
            reconfiguration: True pour relier un nouvel appareil TOTP
        """
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 700)
        self.reconfiguration = reconfiguration
        if self.reconfiguration:
            self.set_title("Reconfiguration de la double authentification")
        else:
            self.set_title("Configuration 2FA Obligatoire")

        self.totp_service = totp_service
        self.auth_service = auth_service
        self.user_info = user_info

        # État
        self.secret = None
        self.backup_codes = []
        self.codes_confirmed = False
        self.totp_verified = False

        # Construction de l'UI
        self._build_ui()

        # Générer le secret et afficher le QR code
        self._generate_secret_and_qr()

    def _build_ui(self):
        """Construit l'interface utilisateur."""
        # Container principal
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(self.main_box)

        # Header bar
        header = Adw.HeaderBar()
        self.main_box.append(header)

        # Scroll container
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.main_box.append(scrolled)

        # Content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content_box.set_margin_top(20)
        content_box.set_margin_bottom(20)
        content_box.set_margin_start(20)
        content_box.set_margin_end(20)
        scrolled.set_child(content_box)

        # === ÉTAPE 1 : Introduction ===
        intro_group = Adw.PreferencesGroup()
        if self.reconfiguration:
            intro_group.set_title("🔐 Relier un nouvel appareil 2FA")
            intro_group.set_description(
                "Utilisez cette procédure pour relier un nouvel appareil "
                "d'authentification (Google Authenticator, Authy, etc.). "
                "Les anciens codes TOTP seront remplacés."
            )
        else:
            intro_group.set_title("🔒 Double Authentification Obligatoire")
            intro_group.set_description(
                "Pour votre sécurité, la double authentification (2FA) est maintenant "
                "obligatoire. Vous aurez besoin d'une application d'authentification "
                "(Google Authenticator, Authy, etc.)."
            )
        content_box.append(intro_group)

        # === ÉTAPE 2 : QR Code ===
        qr_group = Adw.PreferencesGroup()
        if self.reconfiguration:
            qr_group.set_title("📱 Étape 1 : Scannez le nouveau QR Code")
        else:
            qr_group.set_title("📱 Étape 1 : Scannez le QR Code")
        qr_group.set_description(
            "Ouvrez votre application d'authentification et scannez ce QR code."
        )
        content_box.append(qr_group)

        # Container pour le QR code
        self.qr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.qr_box.set_halign(Gtk.Align.CENTER)
        qr_group.add(self.qr_box)

        self.qr_image = Gtk.Picture()
        self.qr_image.set_can_shrink(False)
        self.qr_box.append(self.qr_image)

        # Label pour le secret (en cas de problème avec QR code)
        self.secret_label = Gtk.Label()
        self.secret_label.set_wrap(True)
        self.secret_label.set_selectable(True)
        self.secret_label.add_css_class("monospace")
        self.qr_box.append(self.secret_label)

        # === ÉTAPE 3 : Vérification du code ===
        verify_group = Adw.PreferencesGroup()
        verify_group.set_title("🔢 Étape 2 : Vérifiez le code")
        verify_group.set_description(
            "Entrez le code à 6 chiffres affiché dans votre application pour "
            "vérifier la configuration."
        )
        content_box.append(verify_group)

        # Entry pour le code TOTP
        code_row = Adw.ActionRow()
        code_row.set_title("Code de vérification")
        verify_group.add(code_row)

        self.code_entry = Gtk.Entry()
        self.code_entry.set_placeholder_text("000000")
        self.code_entry.set_max_length(6)
        self.code_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.code_entry.set_width_chars(8)
        self.code_entry.connect("changed", self._on_code_changed)
        self.code_entry.connect("activate", self._on_verify_clicked)
        code_row.add_suffix(self.code_entry)

        # Bouton de vérification
        self.verify_button = Gtk.Button(label="Vérifier")
        self.verify_button.add_css_class("suggested-action")
        self.verify_button.set_sensitive(False)
        self.verify_button.connect("clicked", self._on_verify_clicked)
        code_row.add_suffix(self.verify_button)

        # Message de statut
        self.status_label = Gtk.Label()
        self.status_label.set_margin_top(10)
        verify_group.add(self.status_label)

        # === ÉTAPE 4 : Codes de secours (caché au début) ===
        self.backup_codes_group = Adw.PreferencesGroup()
        self.backup_codes_group.set_title("🔑 Étape 3 : Codes de Secours")
        self.backup_codes_group.set_description(
            "⚠️  IMPORTANT : Conservez ces codes en lieu sûr. "
            "Ils vous permettront de vous connecter si vous perdez l'accès à "
            "votre application d'authentification. "
            "Chaque code ne peut être utilisé qu'une seule fois."
        )
        self.backup_codes_group.set_visible(False)
        content_box.append(self.backup_codes_group)

        # Text view pour les codes
        self.codes_textview = Gtk.TextView()
        self.codes_textview.set_editable(False)
        self.codes_textview.set_monospace(True)
        self.codes_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.codes_textview.set_size_request(-1, 200)
        self.codes_textview.add_css_class("card")

        codes_scrolled = Gtk.ScrolledWindow()
        codes_scrolled.set_child(self.codes_textview)
        codes_scrolled.set_margin_top(10)
        codes_scrolled.set_margin_bottom(10)
        self.backup_codes_group.add(codes_scrolled)

        # Checkbox de confirmation
        self.confirm_codes_check = Gtk.CheckButton(
            label="✓ J'ai sauvegardé ces codes en lieu sûr"
        )
        self.confirm_codes_check.connect("toggled", self._on_confirm_codes_toggled)
        self.backup_codes_group.add(self.confirm_codes_check)

        # === Boutons d'action ===
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_margin_top(10)
        action_box.set_margin_bottom(10)
        action_box.set_margin_start(20)
        action_box.set_margin_end(20)
        action_box.set_halign(Gtk.Align.END)
        self.main_box.append(action_box)

        # Bouton Terminer
        self.finish_button = Gtk.Button(label="Terminer")
        self.finish_button.add_css_class("suggested-action")
        self.finish_button.set_sensitive(False)
        self.finish_button.connect("clicked", self._on_finish_clicked)
        action_box.append(self.finish_button)

    def _generate_secret_and_qr(self):
        """Génère le secret TOTP et affiche le QR code."""
        try:
            # Générer le secret
            self.secret = self.totp_service.generate_secret()

            # Générer le QR code
            email = self.user_info.get('email', 'user@example.com')
            qr_bytes = self.totp_service.generate_qr_code(self.secret, email)

            # Afficher le QR code
            loader = GdkPixbuf.PixbufLoader()
            loader.write(qr_bytes)
            loader.close()
            pixbuf = loader.get_pixbuf()
            if pixbuf is None:
                raise ValueError("QR code invalide: pixbuf non généré")

            # Redimensionner si nécessaire
            if pixbuf.get_width() > 300:
                pixbuf = pixbuf.scale_simple(300, 300, GdkPixbuf.InterpType.BILINEAR)

            self.qr_image.set_pixbuf(pixbuf)

            # Afficher le secret en texte (fallback)
            self.secret_label.set_text(f"Clé manuelle : {self.secret}")

            logger.info("QR code 2FA généré avec succès")

        except Exception as e:
            logger.exception("Erreur génération QR code")
            self._show_error(f"Erreur lors de la génération du QR code : {e}")

    def _on_code_changed(self, entry):
        """Appelé quand le code change."""
        code = entry.get_text().strip()
        # Activer le bouton si c'est 6 chiffres
        self.verify_button.set_sensitive(len(code) == 6 and code.isdigit())

    def _on_verify_clicked(self, _button):
        """Vérifie le code TOTP saisi."""
        code = self.code_entry.get_text().strip()

        if len(code) != 6 or not code.isdigit():
            self._show_status("❌ Le code doit être composé de 6 chiffres", "error")
            return

        # Vérifier le code
        is_valid = self.totp_service.verify_totp(self.secret, code)

        if is_valid:
            self.totp_verified = True
            self._show_status("✅ Code vérifié avec succès !", "success")
            self.code_entry.set_sensitive(False)
            self.verify_button.set_sensitive(False)

            # Passer à l'étape suivante : afficher les codes de secours
            GLib.timeout_add(500, self._show_backup_codes)
        else:
            self._show_status("❌ Code incorrect. Réessayez.", "error")
            self.code_entry.select_region(0, -1)

    def _show_backup_codes(self):
        """Génère et affiche les codes de secours."""
        try:
            # Générer les codes
            self.backup_codes = self.totp_service.generate_backup_codes()

            # Afficher dans le text view
            buffer = self.codes_textview.get_buffer()
            codes_text = "\n".join(self.backup_codes)
            buffer.set_text(codes_text)

            # Afficher le groupe
            self.backup_codes_group.set_visible(True)

            logger.info("Codes de secours 2FA générés")

        except Exception as e:
            logger.exception("Erreur génération codes de secours")
            self._show_error(f"Erreur lors de la génération des codes de secours : {e}")

        return False

    def _on_confirm_codes_toggled(self, check_button):
        """Appelé quand la checkbox de confirmation change."""
        self.codes_confirmed = check_button.get_active()
        self.finish_button.set_sensitive(self.codes_confirmed)

    def _on_finish_clicked(self, _button):
        """Finalise la configuration 2FA."""
        if not self.totp_verified or not self.codes_confirmed:
            self._show_error("Veuillez vérifier le code et confirmer les codes de secours.")
            return

        try:
            # Chiffrer le secret TOTP
            secret_encrypted = self.totp_service.encrypt_secret(self.secret)

            # Chiffrer les codes de secours
            backup_codes_encrypted = self.totp_service.encrypt_backup_codes(self.backup_codes)

            # Sauvegarder dans la base de données
            success = self.auth_service.setup_2fa(
                self.user_info['id'],
                secret_encrypted,
                backup_codes_encrypted
            )

            if success:
                # Confirmer le 2FA
                self.auth_service.confirm_2fa(self.user_info['id'])
                if self.reconfiguration:
                    logger.info("Reconfiguration 2FA terminée avec succès")
                else:
                    logger.info("Configuration 2FA terminée avec succès")
                self.close()
            else:
                self._show_error("Erreur lors de la sauvegarde de la configuration 2FA.")

        except Exception as e:
            logger.exception("Erreur finalisation 2FA")
            self._show_error(f"Erreur : {e}")

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

    def _show_error(self, message: str):
        """Affiche une erreur dans un dialog."""
        dialog = Adw.MessageDialog.new(self, "Erreur", message)
        dialog.add_response("ok", "OK")
        dialog.present()

    def get_success(self) -> bool:
        """Retourne True si la configuration 2FA a réussi."""
        return self.totp_verified and self.codes_confirmed
