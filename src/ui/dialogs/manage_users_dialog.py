"""Dialogue de gestion des utilisateurs."""

from pathlib import Path

import gi  # type: ignore[import]

from src.config.environment import get_data_directory
from src.i18n import _
from src.services.auth_service import AuthService

from .create_user_dialog import CreateUserDialog
from .reset_password_dialog import ResetPasswordDialog

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

DATA_DIR = get_data_directory()


class ManageUsersDialog(Adw.Window):
    """Interface de gestion des utilisateurs."""

    def __init__(
        self,
        parent: Gtk.Window,
        auth_service: AuthService,
        current_username: str,
    ) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 500)
        self.set_title(_("User management"))
        self.auth_service = auth_service
        self.current_username = current_username

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title = Gtk.Label(label=_("User management"))
        title.set_css_classes(["title-2"])
        content.append(title)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(["boxed-list"])
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)

        self.load_users()

        create_user_btn = Gtk.Button(label=_("➕ Create a new user"))
        create_user_btn.set_css_classes(["suggested-action", "pill"])
        create_user_btn.connect("clicked", self.on_create_user)
        content.append(create_user_btn)

        box.append(content)
        self.set_content(box)

    def load_users(self) -> None:
        self.users_listbox.remove_all()
        users = self.auth_service.get_all_users()
        for username, role, created_at, _last_login in users:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            user_box.set_margin_start(12)
            user_box.set_margin_end(12)
            user_box.set_margin_top(12)
            user_box.set_margin_bottom(12)
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_hexpand(True)
            name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name_label = Gtk.Label(label=username, xalign=0)
            name_label.set_css_classes(["title-4"])
            name_box.append(name_label)

            badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            if role == "admin":
                admin_label = Gtk.Label(label=_("Admin"))
                admin_label.set_css_classes(["caption", "accent"])
                badges_box.append(admin_label)
            if badges_box.get_first_child() is not None:
                name_box.append(badges_box)
            info_box.append(name_box)
            created_label = Gtk.Label(label=_("Created: %s") % created_at[:10], xalign=0)
            created_label.set_css_classes(["caption", "dim-label"])
            info_box.append(created_label)
            user_box.append(info_box)
            if username != self.current_username:
                action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                reset_btn = Gtk.Button(label=_("Reset password"))
                reset_btn.connect("clicked", lambda _b, u=username: self.on_reset_password(u))
                action_box.append(reset_btn)
                delete_btn = Gtk.Button(label=_("Delete"))
                delete_btn.set_css_classes(["destructive-action"])
                delete_btn.connect("clicked", lambda _b, u=username: self.on_delete_user(u))
                action_box.append(delete_btn)
                user_box.append(action_box)
            row.set_child(user_box)
            self.users_listbox.append(row)

    def on_create_user(self, _button: Gtk.Button) -> None:
        CreateUserDialog(self, self.auth_service, self.load_users).present()

    def on_reset_password(self, username: str) -> None:
        ResetPasswordDialog(self, self.auth_service, username).present()

    def on_delete_user(self, username: str) -> None:
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(_("Confirm deletion"))
        dialog.set_body(
            _(
                "Do you really want to delete user '%s'?\n\n"
                "All their data will be lost."
            )
            % username
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, response: self.delete_confirmed(response, username))
        dialog.present()

    def delete_confirmed(self, response: str, username: str) -> None:
        if response == "delete":
            if self.auth_service.delete_user(username):
                user_db = Path(DATA_DIR) / f"passwords_{username}.db"
                user_salt = Path(DATA_DIR) / f"salt_{username}.bin"
                if user_db.exists():
                    user_db.unlink()
                if user_salt.exists():
                    user_salt.unlink()
                self.load_users()
