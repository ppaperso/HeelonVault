"""Dialog de mise à jour de l'email pour les utilisateurs migrés.

Ce module fournit une interface pour :
- Saisir un email valide
- Remplacer l'email temporaire @migration.local
"""

import logging

import gi
import validators

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


class UpdateEmailDialog(Adw.Window):
    """Dialog pour mettre à jour l'email d'un utilisateur migré."""

    def __init__(self, parent, auth_service, user_info, migration_required: bool = True, **kwargs):
        """Initialise le dialog de mise à jour d'email.

        Args:
            parent: Fenêtre parente
            auth_service: Service d'authentification
            user_info: Informations de l'utilisateur (dict)
            migration_required: True si la mise à jour est obligatoire (post-migration)
        """
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(550, 400)
        self.set_title("Mise à jour de l'email")

        self.auth_service = auth_service
        self.user_info = user_info
        self.migration_required = migration_required

        # État
        self.new_email = None
        self.updated = False

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

        # Icône et titre
        icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        icon_box.set_halign(Gtk.Align.CENTER)
        content_box.append(icon_box)

        icon_label = Gtk.Label()
        icon_label.set_markup("<span size='xx-large'>📧</span>")
        icon_box.append(icon_label)

        title_label = Gtk.Label()
        if self.migration_required:
            title_label.set_markup(
                "<span size='large' weight='bold'>Mise à jour de l'email requise</span>"
            )
        else:
            title_label.set_markup(
                "<span size='large' weight='bold'>Modifier votre adresse email</span>"
            )
        icon_box.append(title_label)

        # Message explicatif
        message_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        message_box.set_margin_top(20)
        content_box.append(message_box)

        info_label = Gtk.Label()
        if self.migration_required:
            info_label.set_markup(
                "Suite à la migration vers le nouveau système d'authentification, "
                "vous devez fournir votre adresse email réelle.\n\n"
                "Cette adresse sera utilisée comme identifiant de connexion."
            )
        else:
            info_label.set_markup(
                "Cette adresse sera utilisée comme identifiant de connexion.\n\n"
                "Assurez-vous d'utiliser une adresse que vous contrôlez."
            )
        info_label.set_wrap(True)
        info_label.set_justify(Gtk.Justification.CENTER)
        message_box.append(info_label)

        # Groupe de saisie
        input_group = Adw.PreferencesGroup()
        input_group.set_margin_top(20)
        content_box.append(input_group)

        # Row pour l'email actuel
        current_row = Adw.ActionRow()
        current_row.set_title("Email actuel (temporaire)")
        current_row.set_subtitle(self.user_info.get('email', 'unknown'))
        input_group.add(current_row)

        # Row pour le nouvel email
        email_row = Adw.ActionRow()
        email_row.set_title("Nouvel email")
        input_group.add(email_row)

        self.email_entry = Gtk.Entry()
        self.email_entry.set_placeholder_text("votre.email@example.com")
        self.email_entry.set_hexpand(True)
        self.email_entry.set_input_purpose(Gtk.InputPurpose.EMAIL)
        self.email_entry.connect("changed", self._on_email_changed)
        self.email_entry.connect("activate", self._on_update_clicked)
        email_row.add_suffix(self.email_entry)

        # Message de statut
        self.status_label = Gtk.Label()
        self.status_label.set_margin_top(10)
        self.status_label.set_wrap(True)
        content_box.append(self.status_label)

        # Avertissement
        if self.migration_required:
            warning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            warning_box.set_margin_top(10)
            warning_box.add_css_class("card")
            warning_box.add_css_class("warning")
            content_box.append(warning_box)

            warning_icon = Gtk.Label(label="⚠️")
            warning_box.append(warning_icon)

            warning_label = Gtk.Label()
            warning_label.set_markup(
                "<span size='small'><b>Important :</b> "
                "Vous ne pourrez plus utiliser votre ancien identifiant. "
                "Utilisez une adresse email que vous contrôlez.</span>"
            )
            warning_label.set_wrap(True)
            warning_label.set_hexpand(True)
            warning_box.append(warning_label)

        # Boutons d'action
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(20)
        main_box.append(action_box)

        self.update_button = Gtk.Button(label="Mettre à jour")
        self.update_button.add_css_class("suggested-action")
        self.update_button.set_sensitive(False)
        self.update_button.connect("clicked", self._on_update_clicked)
        action_box.append(self.update_button)

    def _on_email_changed(self, entry):
        """Appelé quand l'email change."""
        email = entry.get_text().strip()

        # Validation basique
        is_valid = len(email) > 0 and '@' in email and '.' in email
        self.update_button.set_sensitive(is_valid)

        # Effacer le statut
        self.status_label.set_text("")

    def _on_update_clicked(self, _button):
        """Met à jour l'email."""
        new_email = self.email_entry.get_text().strip()

        # Validation
        if not validators.email(new_email):
            self._show_status("❌ Adresse email invalide.", "error")
            self.email_entry.grab_focus()
            return

        # Vérifier que l'email n'est pas déjà utilisé
        if self.auth_service.email_exists(new_email):
            self._show_status("❌ Cette adresse email est déjà utilisée.", "error")
            self.email_entry.select_region(0, -1)
            return

        # Mettre à jour l'email
        try:
            success = self.auth_service.update_user_email(
                self.user_info['id'],
                new_email
            )

            if success:
                self.new_email = new_email
                self.updated = True
                self._show_status("✅ Email mis à jour avec succès !", "success")
                logger.info("Email mis à jour pour user_id=%s", self.user_info["id"])

                # Fermer après un court délai
                from gi.repository import GLib
                GLib.timeout_add(1000, lambda: self.close())
            else:
                self._show_status("❌ Erreur lors de la mise à jour.", "error")

        except Exception as e:
            logger.exception("Erreur mise à jour email")
            self._show_status(f"❌ Erreur : {e}", "error")

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

    def get_new_email(self) -> str:
        """Retourne le nouvel email (ou None)."""
        return self.new_email if self.updated else None
