"""Fenêtre de sélection d'utilisateur."""

from collections.abc import Callable

import gi  # type: ignore[import]

from src.i18n import _
from src.models.user_info import UserInfo
from src.services.auth_service import AuthService
from src.version import __app_display_name__, get_version

from .login_dialog import LoginDialog

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


class UserSelectionDialog(Adw.ApplicationWindow):
    """Fenêtre de sélection d'utilisateur."""

    def __init__(
        self,
        app: Adw.Application,
        auth_service: AuthService,
        callback: Callable[[UserInfo, str], None],
    ) -> None:
        super().__init__(application=app)
        self.set_default_size(450, 500)
        self.set_title(_("User selection"))
        self.auth_service = auth_service
        self.callback = callback

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_top(20)
        content.set_margin_bottom(40)

        title = Gtk.Label(label=_(__app_display_name__))
        title.set_css_classes(["title-1"])
        content.append(title)

        version_label = Gtk.Label(label=_("Version %s") % get_version())
        version_label.set_css_classes(["caption", "dim-label"])
        content.append(version_label)

        subtitle = Gtk.Label(label=_("Select your account"))
        subtitle.set_css_classes(["title-4"])
        content.append(subtitle)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(["boxed-list"])
        self.users_listbox.connect("row-activated", self.on_user_selected)
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)

        self.load_users()
        box.append(content)
        self.set_content(box)

    def load_users(self) -> None:
        self.users_listbox.remove_all()
        users = self.auth_service.get_all_users()
        for username, role, _created_at, last_login in users:
            row = Gtk.ListBoxRow()
            row.set_data("username", username)
            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            user_box.set_margin_start(12)
            user_box.set_margin_end(12)
            user_box.set_margin_top(12)
            user_box.set_margin_bottom(12)
            icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            icon.set_pixel_size(32)
            user_box.append(icon)
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
            if last_login:
                last_login_label = Gtk.Label(
                    label=_("Last login: %s") % last_login[:16], xalign=0
                )
                last_login_label.set_css_classes(["caption", "dim-label"])
                info_box.append(last_login_label)
            user_box.append(info_box)
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            user_box.append(arrow)
            row.set_child(user_box)
            self.users_listbox.append(row)

    def on_user_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        username = row.get_data("username")
        LoginDialog(self, self.auth_service, username, self.callback).present()
