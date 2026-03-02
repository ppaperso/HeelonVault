"""Dialog de vérification du code TOTP lors de la connexion.

Ce module fournit une interface pour :
- Saisir le code TOTP à 6 chiffres
- Vérifier le code avec le secret stocké
- Permettre l'utilisation d'un code de secours
"""

import logging

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


class VerifyTOTPDialog(Adw.Window):
    """Dialog pour vérifier le code TOTP lors de la connexion."""

    def __init__(self, parent, totp_service, auth_service, user_info, **kwargs):
        """Initialise le dialog de vérification TOTP.

        Args:
            parent: Fenêtre parente
            totp_service: Service TOTP
            auth_service: Service d'authentification
            user_info: Informations de l'utilisateur (dict)
        """
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(500, 400)
        self.set_title("Double Authentification")

        self.totp_service = totp_service
        self.auth_service = auth_service
        self.user_info = user_info

        # État
        self.verified = False
        self.use_backup_code = False

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
        content_box.set_margin_top(20)
        content_box.set_margin_bottom(20)
        content_box.set_margin_start(20)
        content_box.set_margin_end(20)
        content_box.set_vexpand(True)
        content_box.set_valign(Gtk.Align.CENTER)
        main_box.append(content_box)

        # Icône et titre
        icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        icon_box.set_halign(Gtk.Align.CENTER)
        content_box.append(icon_box)

        icon_label = Gtk.Label()
        icon_label.set_markup("<span size='xx-large'>🔐</span>")
        icon_box.append(icon_label)

        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold'>Double Authentification</span>")
        icon_box.append(title_label)

        # Stack pour changer entre code normal et code de secours
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        content_box.append(self.stack)

        # === Page 1 : Code TOTP normal ===
        totp_page = self._build_totp_page()
        self.stack.add_named(totp_page, "totp")

        # === Page 2 : Code de secours ===
        backup_page = self._build_backup_code_page()
        self.stack.add_named(backup_page, "backup")

        # Lien pour passer aux codes de secours
        self.switch_link = Gtk.LinkButton()
        self.switch_link.set_label("Utiliser un code de secours")
        self.switch_link.set_halign(Gtk.Align.CENTER)
        self.switch_link.connect("activate-link", self._on_switch_mode)
        content_box.append(self.switch_link)

        # Boutons d'action
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(20)
        main_box.append(action_box)

        cancel_button = Gtk.Button(label="Annuler")
        cancel_button.connect("clicked", lambda b: self.close())
        action_box.append(cancel_button)

        self.verify_button = Gtk.Button(label="Vérifier")
        self.verify_button.add_css_class("suggested-action")
        self.verify_button.set_sensitive(False)
        self.verify_button.connect("clicked", self._on_verify_clicked)
        action_box.append(self.verify_button)

    def _build_totp_page(self) -> Gtk.Widget:
        """Construit la page de saisie du code TOTP."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_valign(Gtk.Align.CENTER)

        # Description
        desc = Gtk.Label()
        desc.set_text(
            "Entrez le code à 6 chiffres affiché dans votre application "
            "d'authentification."
        )
        desc.set_wrap(True)
        desc.set_justify(Gtk.Justification.CENTER)
        box.append(desc)

        # Entry pour le code
        self.totp_entry = Gtk.Entry()
        self.totp_entry.set_placeholder_text("000000")
        self.totp_entry.set_max_length(6)
        self.totp_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.totp_entry.set_halign(Gtk.Align.CENTER)
        self.totp_entry.set_width_chars(10)
        self.totp_entry.add_css_class("large-entry")
        self.totp_entry.connect("changed", self._on_code_changed)
        self.totp_entry.connect("activate", self._on_verify_clicked)
        box.append(self.totp_entry)

        # Statut
        self.totp_status = Gtk.Label()
        self.totp_status.set_margin_top(10)
        box.append(self.totp_status)

        return box

    def _build_backup_code_page(self) -> Gtk.Widget:
        """Construit la page de saisie du code de secours."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_valign(Gtk.Align.CENTER)

        # Description
        desc = Gtk.Label()
        desc.set_text("Entrez l'un de vos codes de secours (format: XXXX-XXXX-XX).")
        desc.set_wrap(True)
        desc.set_justify(Gtk.Justification.CENTER)
        box.append(desc)

        # Entry pour le code de secours
        self.backup_entry = Gtk.Entry()
        self.backup_entry.set_placeholder_text("XXXX-XXXX-XX")
        self.backup_entry.set_max_length(12)
        self.backup_entry.set_halign(Gtk.Align.CENTER)
        self.backup_entry.set_width_chars(15)
        self.backup_entry.connect("changed", self._on_code_changed)
        self.backup_entry.connect("activate", self._on_verify_clicked)
        box.append(self.backup_entry)

        # Avertissement
        warning = Gtk.Label()
        warning.set_markup(
            "<span size='small'>⚠️  Chaque code de secours ne peut être "
            "utilisé qu'une seule fois.</span>"
        )
        warning.add_css_class("dim-label")
        box.append(warning)

        # Statut
        self.backup_status = Gtk.Label()
        self.backup_status.set_margin_top(10)
        box.append(self.backup_status)

        return box

    def _on_switch_mode(self, link_button):
        """Change entre code TOTP et code de secours."""
        current_page = self.stack.get_visible_child_name()

        if current_page == "totp":
            self.stack.set_visible_child_name("backup")
            self.switch_link.set_label("Utiliser le code TOTP")
            self.use_backup_code = True
            self.backup_entry.grab_focus()
        else:
            self.stack.set_visible_child_name("totp")
            self.switch_link.set_label("Utiliser un code de secours")
            self.use_backup_code = False
            self.totp_entry.grab_focus()

        # Réinitialiser le statut du bouton
        self._on_code_changed(None)
        return True

    def _on_code_changed(self, entry):
        """Appelé quand le code change."""
        if self.use_backup_code:
            code = self.backup_entry.get_text().strip()
            # Code de secours : 10 caractères + 2 tirets
            self.verify_button.set_sensitive(len(code) >= 10)
        else:
            code = self.totp_entry.get_text().strip()
            # Code TOTP : 6 chiffres
            self.verify_button.set_sensitive(len(code) == 6 and code.isdigit())

    def _on_verify_clicked(self, button):
        """Vérifie le code saisi."""
        try:
            # Récupérer le secret TOTP chiffré
            secret_encrypted = self.auth_service.get_2fa_secret(self.user_info['id'])
            if not secret_encrypted:
                self._show_error("Erreur : secret 2FA introuvable.")
                return

            # Déchiffrer le secret
            secret = self.totp_service.decrypt_secret(secret_encrypted)

            if self.use_backup_code:
                # Vérifier le code de secours
                code = self.backup_entry.get_text().strip().upper()

                # Récupérer les codes de secours
                backup_codes_encrypted = self.auth_service.get_backup_codes(self.user_info['id'])
                if not backup_codes_encrypted:
                    self._show_status("❌ Aucun code de secours disponible.", "error", backup=True)
                    return

                backup_codes_hashed = self.totp_service.decrypt_backup_codes(
                    backup_codes_encrypted
                )
                is_valid, matched_hash = self.totp_service.verify_backup_code(
                    code, backup_codes_hashed
                )

                if is_valid:
                    # Marquer le code comme utilisé
                    updated_codes = self.totp_service.mark_backup_code_used(
                        backup_codes_encrypted,
                        matched_hash
                    )
                    self.auth_service.update_backup_codes(self.user_info['id'], updated_codes)

                    self.verified = True
                    self._show_status("✅ Code de secours valide !", "success", backup=True)

                    # Fermer après un court délai
                    from gi.repository import GLib
                    GLib.timeout_add(500, lambda: self.close())
                else:
                    self._show_status("❌ Code de secours invalide.", "error", backup=True)
            else:
                # Vérifier le code TOTP
                code = self.totp_entry.get_text().strip()
                is_valid = self.totp_service.verify_totp(secret, code)

                if is_valid:
                    self.verified = True
                    self._show_status("✅ Code valide !", "success", backup=False)

                    # Fermer après un court délai
                    from gi.repository import GLib
                    GLib.timeout_add(500, lambda: self.close())
                else:
                    self._show_status("❌ Code incorrect. Réessayez.", "error", backup=False)

        except Exception as e:
            logger.exception("Erreur vérification TOTP")
            self._show_error(f"Erreur : {e}")

    def _show_status(self, message: str, status_type: str = "info", backup: bool = False):
        """Affiche un message de statut.

        Args:
            message: Message à afficher
            status_type: 'info', 'success', 'error', 'warning'
            backup: True pour afficher sur la page backup, False pour TOTP
        """
        label = self.backup_status if backup else self.totp_status
        label.set_text(message)

        # Réinitialiser les classes CSS
        label.remove_css_class("success")
        label.remove_css_class("error")
        label.remove_css_class("warning")

        # Ajouter la classe appropriée
        if status_type == "success":
            label.add_css_class("success")
        elif status_type == "error":
            label.add_css_class("error")
        elif status_type == "warning":
            label.add_css_class("warning")

    def _show_error(self, message: str):
        """Affiche une erreur dans un dialog."""
        dialog = Adw.MessageDialog.new(self, "Erreur", message)
        dialog.add_response("ok", "OK")
        dialog.present()

    def get_verified(self) -> bool:
        """Retourne True si le code a été vérifié avec succès."""
        return self.verified
