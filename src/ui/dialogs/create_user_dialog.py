"""Dialogue de création d'utilisateur."""

from collections.abc import Callable

import gi  # type: ignore[import]

from src.i18n import _
from src.services.auth_service import AuthService
from src.services.master_password_validator import MasterPasswordValidator
from src.ui.password_form_utils import (
    _password_policy_checklist_text,
    _password_policy_guidance_text,
    _validate_password_rules,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


class CreateUserDialog(Adw.Window):
    """Création d'utilisateur (admin)."""

    def __init__(
        self,
        parent: Gtk.Window,
        auth_service: AuthService,
        on_success: Callable[[], None],
    ) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(560, 640)
        self.set_title(_("Create account"))
        self.auth_service = auth_service
        self.on_success_callback = on_success

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_top(20)
        content.set_margin_bottom(40)

        title = Gtk.Label(label=_("Create a new account"))
        title.set_css_classes(["title-2"])
        content.append(title)

        username_label = Gtk.Label(label=_("Username"), xalign=0)
        content.append(username_label)
        self.username_entry = Gtk.Entry()
        content.append(self.username_entry)

        password_label = Gtk.Label(label=_("Master password"), xalign=0)
        content.append(password_label)

        self.password_rules_label = Gtk.Label(
            label=_password_policy_guidance_text(),
            xalign=0,
        )
        self.password_rules_label.set_wrap(True)
        self.password_rules_label.set_css_classes(["caption", "dim-label"])
        self.password_rules_label.set_margin_bottom(4)
        content.append(self.password_rules_label)

        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.connect("changed", self.on_password_changed)
        content.append(self.password_entry)

        self.strength_label = Gtk.Label(label="")
        self.strength_label.set_css_classes(["caption"])
        self.strength_label.set_xalign(0)
        self.strength_label.set_margin_bottom(5)
        content.append(self.strength_label)

        self.password_checklist_label = Gtk.Label(label="", xalign=0)
        self.password_checklist_label.set_wrap(True)
        self.password_checklist_label.set_css_classes(["caption", "dim-label"])
        self.password_checklist_label.set_margin_bottom(5)
        content.append(self.password_checklist_label)

        confirm_label = Gtk.Label(label=_("Confirm master password"), xalign=0)
        content.append(confirm_label)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        content.append(self.confirm_entry)

        role_label = Gtk.Label(label=_("Role"), xalign=0)
        content.append(role_label)
        role_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        role_box.set_margin_bottom(10)
        self.role_user = Gtk.CheckButton(label=_("User"))
        self.role_user.set_active(True)
        role_box.append(self.role_user)
        self.role_admin = Gtk.CheckButton(label=_("Administrator"))
        self.role_admin.set_group(self.role_user)
        role_box.append(self.role_admin)
        content.append(role_box)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        content.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        create_btn = Gtk.Button(label=_("Create account"))
        create_btn.set_css_classes(["suggested-action"])
        create_btn.connect("clicked", self.on_create_clicked)
        button_box.append(create_btn)
        content.append(button_box)

        box.append(content)
        self.set_content(box)

    def on_password_changed(self, entry: Gtk.PasswordEntry) -> None:
        """Affiche la force du mot de passe en temps réel."""
        password = entry.get_text()
        if len(password) == 0:
            self.strength_label.set_text("")
            self.strength_label.set_css_classes(["caption"])
            self.password_checklist_label.set_text("")
            return

        _, _, score = MasterPasswordValidator.validate(password)
        strength = MasterPasswordValidator.get_strength_description(score)

        if score >= 80:
            self.strength_label.set_css_classes(["caption", "success"])
        elif score >= 60:
            self.strength_label.set_css_classes(["caption", "warning"])
        else:
            self.strength_label.set_css_classes(["caption", "error"])

        self.strength_label.set_text(f"Strength: {strength} ({score}/100)")

        self.password_checklist_label.set_text(_password_policy_checklist_text(password))

    def on_create_clicked(self, _button: Gtk.Button) -> None:
        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()

        if len(username) < 3:
            self.show_error(_("Username must contain at least 3 characters"))
            return

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
        role = "admin" if self.role_admin.get_active() else "user"
        if self.auth_service.create_user(username, password, role):
            self.on_success_callback()
            self.close()
        else:
            self.show_error(_("This username already exists"))

    def show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
