"""Page de gestion du compte utilisateur connecté."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import gi

from src.config.environment import get_data_directory
from src.i18n import _
from src.models.user_info import UserInfo, UserInfoUpdate
from src.services.auth_service import AuthService

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402


class ManageAccountDialog(Adw.Window):
    """Dialogue centralisant les paramètres de compte utilisateur."""

    def __init__(
        self,
        parent: Gtk.Window,
        auth_service: AuthService,
        current_user: UserInfo,
        on_profile_updated: Callable[[UserInfoUpdate], None],
        on_change_password: Callable[[], None],
        on_change_email: Callable[[], None],
        on_reconfigure_2fa: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(700, 620)
        self.set_title(_("Manage my account"))

        self.auth_service = auth_service
        self.current_user = current_user
        self.on_profile_updated = on_profile_updated
        self.on_change_password = on_change_password
        self.on_change_email = on_change_email
        self.on_reconfigure_2fa = on_reconfigure_2fa

        self.avatar_file_dialog: Gtk.FileChooserNative | None = None

        self._build_ui()
        self._refresh_avatar_preview()

    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        root.append(header)

        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_vexpand(True)
        root.append(content_scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(14)
        content.set_margin_bottom(14)
        content.set_margin_start(14)
        content.set_margin_end(14)
        content_scroll.set_child(content)

        title = Gtk.Label(label=_("Manage my account"), xalign=0)
        title.set_css_classes(["title-2", "account-page-title"])
        content.append(title)

        subtitle = Gtk.Label(
            label=_("Single place for your identity, access, and sensitive settings."),
            xalign=0,
        )
        subtitle.set_css_classes(["dim-label", "account-page-subtitle"])
        subtitle.set_wrap(True)
        content.append(subtitle)

        profile_group = Adw.PreferencesGroup()
        profile_group.add_css_class("account-group")
        profile_group.set_title(_("Identity"))
        profile_group.set_description(_("Display name in the app and account avatar."))
        content.append(profile_group)

        avatar_row = Adw.ActionRow()
        avatar_row.set_title(_("Account avatar"))
        avatar_row.set_subtitle(_("Used in the dashboard profile card"))
        profile_group.add(avatar_row)

        self.avatar_preview = Adw.Avatar(
            size=48,
            text=self.current_user.get("username", "?"),
            show_initials=True,
        )
        avatar_row.add_prefix(self.avatar_preview)

        choose_avatar_btn = Gtk.Button(label=_("Choose"))
        choose_avatar_btn.set_css_classes(["pill", "account-action-btn"])
        choose_avatar_btn.connect("clicked", self.on_choose_avatar_clicked)
        avatar_row.add_suffix(choose_avatar_btn)

        clear_avatar_btn = Gtk.Button(label=_("Delete"))
        clear_avatar_btn.set_css_classes(["pill", "destructive-action", "account-action-btn"])
        clear_avatar_btn.connect("clicked", self.on_clear_avatar_clicked)
        avatar_row.add_suffix(clear_avatar_btn)

        username_row = Adw.ActionRow()
        username_row.set_title(_("Account name"))
        username_row.set_subtitle(_("Shown in the interface and profile card"))
        profile_group.add(username_row)

        self.username_entry = Gtk.Entry()
        self.username_entry.set_hexpand(True)
        self.username_entry.set_text(self.current_user.get("username", ""))
        self.username_entry.set_placeholder_text(_("e.g. Patrick"))
        username_row.add_suffix(self.username_entry)

        save_name_btn = Gtk.Button(label=_("Save"))
        save_name_btn.set_css_classes(["suggested-action", "pill", "account-action-btn"])
        save_name_btn.connect("clicked", self.on_save_username_clicked)
        username_row.add_suffix(save_name_btn)

        security_group = Adw.PreferencesGroup()
        security_group.add_css_class("account-group")
        security_group.set_title(_("Security"))
        security_group.set_description(_("Access, email, and two-factor authentication."))
        content.append(security_group)

        change_pwd_row = Adw.ActionRow()
        change_pwd_row.set_title(_("Master password"))
        change_pwd_row.set_subtitle(_("Renew your encryption credentials"))
        security_group.add(change_pwd_row)

        pwd_btn = Gtk.Button(label=_("Edit"))
        pwd_btn.set_css_classes(["pill", "account-action-btn"])
        pwd_btn.connect("clicked", lambda _b: self.on_change_password())
        change_pwd_row.add_suffix(pwd_btn)

        change_email_row = Adw.ActionRow()
        change_email_row.set_title(_("Email address"))
        change_email_row.set_subtitle(self.current_user.get("email", "—"))
        security_group.add(change_email_row)

        email_btn = Gtk.Button(label=_("Edit"))
        email_btn.set_css_classes(["pill", "account-action-btn"])
        email_btn.connect("clicked", lambda _b: self.on_change_email())
        change_email_row.add_suffix(email_btn)

        reconfigure_2fa_row = Adw.ActionRow()
        reconfigure_2fa_row.set_title(_("Two-factor authentication (2FA)"))
        reconfigure_2fa_row.set_subtitle(_("Link or reconfigure a trusted device"))
        security_group.add(reconfigure_2fa_row)

        twofa_btn = Gtk.Button(label=_("Reconfigure"))
        twofa_btn.set_css_classes(["pill", "account-action-btn"])
        twofa_btn.connect("clicked", lambda _b: self.on_reconfigure_2fa())
        reconfigure_2fa_row.add_suffix(twofa_btn)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.set_css_classes(["account-status"])
        self.status_label.set_wrap(True)
        content.append(self.status_label)

        self.set_content(root)

    def _refresh_avatar_preview(self) -> None:
        username = self.current_user.get("username", "?")
        self.avatar_preview.set_text(username)

        avatar_path = self.current_user.get("avatar_path")
        if not avatar_path:
            self.avatar_preview.set_custom_image(None)
            return

        try:
            texture = Gdk.Texture.new_from_filename(str(avatar_path))
            self.avatar_preview.set_custom_image(texture)
        except Exception:
            self.avatar_preview.set_custom_image(None)

    def _show_status(self, message: str, status_type: str = "info") -> None:
        self.status_label.set_text(message)
        self.status_label.remove_css_class("success")
        self.status_label.remove_css_class("warning")
        self.status_label.remove_css_class("error")

        if status_type == "success":
            self.status_label.add_css_class("success")
        elif status_type == "warning":
            self.status_label.add_css_class("warning")
        elif status_type == "error":
            self.status_label.add_css_class("error")

    def on_save_username_clicked(self, _button) -> None:
        new_username = self.username_entry.get_text().strip()
        user_id = self.current_user.get("id")
        if not user_id:
            self._show_status(_("❌ User not found"), "error")
            return

        if not new_username:
            self._show_status(_("❌ Name cannot be empty"), "error")
            return

        if new_username == self.current_user.get("username"):
            self._show_status(_("No changes to save"), "warning")
            return

        if not self.auth_service.update_username(user_id, new_username):
            self._show_status(_("❌ This name is already used or invalid"), "error")
            return

        self.current_user["username"] = new_username
        self._refresh_avatar_preview()
        self.on_profile_updated({"username": new_username})
        self._show_status(_("✅ Name updated"), "success")

    def on_choose_avatar_clicked(self, _button) -> None:
        dialog = Gtk.FileChooserNative.new(
            _("Choose an avatar"),
            self,
            Gtk.FileChooserAction.OPEN,
            _("Choose"),
            _("Cancel"),
        )
        filter_images = Gtk.FileFilter()
        filter_images.set_name(_("Images"))
        filter_images.add_mime_type("image/png")
        filter_images.add_mime_type("image/jpeg")
        filter_images.add_mime_type("image/webp")
        dialog.add_filter(filter_images)
        dialog.connect("response", self.on_avatar_dialog_response)
        self.avatar_file_dialog = dialog
        dialog.show()

    def on_avatar_dialog_response(self, dialog, response) -> None:
        if response != Gtk.ResponseType.ACCEPT:
            return

        selected = dialog.get_file()
        if not selected:
            return

        source_path = selected.get_path()
        if not source_path:
            return

        user_id = self.current_user.get("id")
        if not user_id:
            self._show_status(_("❌ User not found"), "error")
            return

        src = Path(source_path)
        ext = src.suffix.lower() if src.suffix else ".png"
        avatar_dir = get_data_directory() / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        target = avatar_dir / f"user_{user_id}{ext}"

        try:
            shutil.copy2(src, target)
            target.chmod(0o600)
        except Exception:
            self._show_status(_("❌ Unable to copy image"), "error")
            return

        if not self.auth_service.update_avatar_path(user_id, str(target)):
            self._show_status(_("❌ Unable to save avatar"), "error")
            return

        self.current_user["avatar_path"] = str(target)
        self._refresh_avatar_preview()
        self.on_profile_updated({"avatar_path": str(target)})
        self._show_status(_("✅ Avatar updated"), "success")

    def on_clear_avatar_clicked(self, _button) -> None:
        user_id = self.current_user.get("id")
        if not user_id:
            self._show_status(_("❌ User not found"), "error")
            return

        if not self.auth_service.update_avatar_path(user_id, None):
            self._show_status(_("❌ Unable to delete avatar"), "error")
            return

        self.current_user["avatar_path"] = None
        self._refresh_avatar_preview()
        self.on_profile_updated({"avatar_path": None})
        self._show_status(_("✅ Avatar deleted"), "success")
