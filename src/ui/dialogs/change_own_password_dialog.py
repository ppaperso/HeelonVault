"""Dialogue de changement de mot de passe utilisateur."""

from collections.abc import Callable

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
from gi.repository import Adw, GLib, Gtk  # noqa: E402


class ChangeOwnPasswordDialog(Adw.Window):
    """Dialogue pour changer son mot de passe maître."""

    def __init__(
        self,
        parent: Gtk.Window,
        auth_service: AuthService,
        username: str,
        on_change_master_password: Callable[[str, str], bool] | None = None,
    ) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(560, 600)
        self.set_title(_("Change my password"))
        self.auth_service = auth_service
        self.username = username
        self.on_change_master_password = on_change_master_password

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)

        title = Gtk.Label(label=_("Change your master password"))
        title.set_css_classes(["title-3"])
        title.set_wrap(True)
        box.append(title)

        info = Gtk.Label(
            label=_(
                "For security reasons, you must first enter your current password."
            )
        )
        info.set_css_classes(["caption", "dim-label"])
        info.set_wrap(True)
        box.append(info)

        current_label = Gtk.Label(label=_("Current password"), xalign=0)
        current_label.set_css_classes(["title-4"])
        box.append(current_label)
        self.current_entry = Gtk.PasswordEntry()
        self.current_entry.set_show_peek_icon(True)
        box.append(self.current_entry)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(10)
        separator.set_margin_bottom(10)
        box.append(separator)

        new_label = Gtk.Label(label=_("New master password"), xalign=0)
        new_label.set_css_classes(["title-4"])
        box.append(new_label)

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

        confirm_label = Gtk.Label(label=_("Confirm new master password"), xalign=0)
        box.append(confirm_label)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        box.append(self.confirm_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        box.append(self.error_label)

        self.progress_label = Gtk.Label(label="")
        self.progress_label.set_css_classes(["caption", "dim-label"])
        self.progress_label.set_visible(False)
        self.progress_label.set_wrap(True)
        box.append(self.progress_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        self.change_btn = Gtk.Button(label=_("Change password"))
        self.change_btn.set_css_classes(["suggested-action"])
        self.change_btn.connect("clicked", self.on_change_clicked)
        button_box.append(self.change_btn)
        box.append(button_box)

        self.set_content(box)

    def _on_new_password_changed(self, entry: Gtk.PasswordEntry) -> None:
        apply_new_password_feedback(
            entry.get_text(),
            self.new_password_strength_label,
            self.password_checklist_label,
        )

    def on_change_clicked(self, _button: Gtk.Button) -> None:
        current = self.current_entry.get_text()
        new_password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()
        self.error_label.set_visible(False)
        self.progress_label.set_visible(False)

        if not current:
            self.show_error(_("Please enter your current password"))
            return
        if not self.auth_service.verify_user(self.username, current):
            self.show_error(_("❌ Incorrect current password"))
            self.current_entry.set_text("")
            self.current_entry.grab_focus()
            return

        is_valid, errors, _score = MasterPasswordValidator.validate(new_password)
        if not is_valid:
            error_msg = _("Password does not meet minimum requirements:\n")
            error_msg += "\n".join(f"• {err}" for err in errors[:3])
            self.show_error(error_msg)
            return

        error = _validate_password_rules(new_password, confirm)
        if error:
            self.show_error(error)
            return
        if new_password == current:
            self.show_error(_("New password must be different from the current one"))
            return

        self.progress_label.set_text(
            _(
                "🔐 Vault re-encryption in progress... "
                "This operation may take a few moments."
            )
        )
        self.progress_label.set_visible(True)
        self.change_btn.set_sensitive(False)
        self.current_entry.set_sensitive(False)
        self.password_entry.set_sensitive(False)
        self.confirm_entry.set_sensitive(False)

        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

        if self.on_change_master_password:
            changed = self.on_change_master_password(current, new_password)
        else:
            changed = self.auth_service.change_user_password(self.username, current, new_password)

        if changed:
            dialog = Adw.MessageDialog.new(self)
            dialog.set_heading(_("✅ Success"))
            dialog.set_body(_("Your master password has been changed successfully."))
            dialog.add_response("ok", _("OK"))
            dialog.connect("response", lambda _d, _r: self.close())
            dialog.present()
        else:
            self.progress_label.set_visible(False)
            self.change_btn.set_sensitive(True)
            self.current_entry.set_sensitive(True)
            self.password_entry.set_sensitive(True)
            self.confirm_entry.set_sensitive(True)
            self.show_error(
                _("❌ Error while changing password or re-encrypting the vault")
            )

    def show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
