"""Dialogue de connexion."""

from collections.abc import Callable

import gi  # type: ignore[import]

from src.i18n import _
from src.models.user_info import UserInfo
from src.services.auth_service import AuthService
from src.ui.password_strength import evaluate_password_strength
from src.version import get_version

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


class LoginDialog(Adw.Window):
    """Dialogue de connexion."""

    def __init__(
        self,
        parent: Gtk.Window,
        auth_service: AuthService,
        username: str,
        callback: Callable[[UserInfo, str], None],
    ) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 250)
        self.set_title(_("Login"))
        self.auth_service = auth_service
        self.username = username
        self.callback = callback

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)
        box.set_valign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        icon.set_pixel_size(64)
        box.append(icon)

        title = Gtk.Label(label=_("Hello, %s") % username)
        title.set_css_classes(["title-2"])
        box.append(title)

        subtitle = Gtk.Label(label=_("Enter your master password"))
        box.append(subtitle)

        version_label = Gtk.Label(label=_("v%s") % get_version())
        version_label.set_css_classes(["caption", "dim-label"])
        version_label.set_margin_top(10)

        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.connect("changed", self._on_password_changed)
        self.password_entry.connect("activate", lambda _x: self.on_login())
        box.append(self.password_entry)

        self.strength_label = Gtk.Label(label="", xalign=0)
        self.strength_label.set_css_classes(["caption", "dim-label"])
        box.append(self.strength_label)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        box.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)

        cancel_btn = Gtk.Button(label=_("Back"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)

        login_btn = Gtk.Button(label=_("Sign in"))
        login_btn.set_css_classes(["suggested-action"])
        login_btn.connect("clicked", lambda _x: self.on_login())
        button_box.append(login_btn)

        box.append(button_box)
        box.append(version_label)
        self.set_content(box)
        self.password_entry.grab_focus()

    def _on_password_changed(self, entry: Gtk.PasswordEntry) -> None:
        password = entry.get_text()
        score, label, css = evaluate_password_strength(password)
        if score == 0:
            self.strength_label.set_text("")
            self.strength_label.set_css_classes(["caption", "dim-label"])
            return
        self.strength_label.set_text(_("Strength: %s") % label)
        self.strength_label.set_css_classes(["caption", css])

    def on_login(self) -> None:
        password = self.password_entry.get_text()
        if not password:
            self.show_error(_("Please enter your password"))
            return
        user_info_dict = self.auth_service.authenticate(self.username, password)
        if user_info_dict:
            user_info = UserInfo(**user_info_dict)
            self.callback(user_info, password)
            self.close()
        else:
            self.show_error(_("Incorrect password"))
            self.password_entry.set_text("")
            self.password_entry.grab_focus()

    def show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
