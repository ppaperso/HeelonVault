"""Dialogue de réinitialisation de mot de passe."""

import gi  # type: ignore[import]

from src.i18n import _
from src.services.auth_service import AuthService
from src.services.master_password_validator import MasterPasswordValidator
from src.ui.password_form_utils import (
    _password_policy_guidance_text,
    _validate_password_rules,
    apply_new_password_feedback,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


class ResetPasswordDialog(Adw.Window):
    """Réinitialisation de mot de passe (admin)."""

    def __init__(self, parent: Gtk.Window, auth_service: AuthService, username: str) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(540, 540)
        self.set_title(_("Reset password"))
        self.auth_service = auth_service
        self.username = username

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)

        title = Gtk.Label(label=_("Reset password for '%s'") % username)
        title.set_css_classes(["title-3"])
        title.set_wrap(True)
        box.append(title)

        warning = Gtk.Label(
            label=_("⚠️ The user will need to use this new master password")
        )
        warning.set_css_classes(["caption"])
        warning.set_wrap(True)
        box.append(warning)

        password_label = Gtk.Label(label=_("New master password"), xalign=0)
        box.append(password_label)

        self.password_rules_label = Gtk.Label(
            label=_password_policy_guidance_text(),
            xalign=0,
        )
        self.password_rules_label.set_wrap(True)
        self.password_rules_label.set_css_classes(["caption", "dim-label"])
        self.password_rules_label.set_margin_bottom(4)
        box.append(self.password_rules_label)

        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.connect("changed", self._on_new_password_changed)
        box.append(self.password_entry)

        self.new_password_strength_label = Gtk.Label(label="", xalign=0)
        self.new_password_strength_label.set_css_classes(["caption", "dim-label"])
        box.append(self.new_password_strength_label)

        self.password_checklist_label = Gtk.Label(label="", xalign=0)
        self.password_checklist_label.set_wrap(True)
        self.password_checklist_label.set_css_classes(["caption", "dim-label"])
        self.password_checklist_label.set_margin_bottom(5)
        box.append(self.password_checklist_label)

        confirm_label = Gtk.Label(label=_("Confirm master password"), xalign=0)
        box.append(confirm_label)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        box.append(self.confirm_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        box.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        reset_btn = Gtk.Button(label=_("Reset"))
        reset_btn.set_css_classes(["destructive-action"])
        reset_btn.connect("clicked", self.on_reset_clicked)
        button_box.append(reset_btn)
        box.append(button_box)

        self.set_content(box)

    def _on_new_password_changed(self, entry: Gtk.PasswordEntry) -> None:
        apply_new_password_feedback(
            entry.get_text(),
            self.new_password_strength_label,
            self.password_checklist_label,
        )

    def on_reset_clicked(self, _button: Gtk.Button) -> None:
        password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()

        is_valid, errors, _score = MasterPasswordValidator.validate(password)
        if not is_valid:
            error_msg = _("Password does not meet minimum requirements:\n")
            error_msg += "\n".join(f"• {err}" for err in errors[:3])
            self.show_error(error_msg)
            return

        error = _validate_password_rules(password, confirm)
        if error:
            self.show_error(error)
            return
        if self.auth_service.reset_user_password(self.username, password):
            dialog = Adw.MessageDialog.new(self)
            dialog.set_heading(_("Success"))
            dialog.set_body(_("Password for '%s' has been reset.") % self.username)
            dialog.add_response("ok", _("OK"))
            dialog.connect("response", lambda _d, _r: self.close())
            dialog.present()
        else:
            self.show_error(_("Error while resetting password"))

    def show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
