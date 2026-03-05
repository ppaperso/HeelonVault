"""Page de gestion du compte utilisateur connecté."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import gi

from src.config.environment import get_data_directory
from src.i18n import _, get_supported_languages, normalize_language, set_language
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
        self.add_css_class("manage-account-dialog")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(620, 560)
        self.set_title(_("Manage my account"))

        self.auth_service = auth_service
        self.current_user = current_user
        self.on_profile_updated = on_profile_updated
        self.on_change_password = on_change_password
        self.on_change_email = on_change_email
        self.on_reconfigure_2fa = on_reconfigure_2fa

        self.avatar_file_dialog: Gtk.FileChooserNative | None = None
        self.language_codes: list[str] = []
        self.language_dropdown: Gtk.DropDown | None = None
        self.save_name_btn: Gtk.Button | None = None
        self.avatar_remove_action_btn: Gtk.Button | None = None
        self.avatar_actions_popover: Gtk.Popover | None = None
        self.toast_overlay: Adw.ToastOverlay | None = None
        self._language_selection_ready = False
        self.selected_language = normalize_language(self.current_user.get("language"))

        self._build_ui()
        self._refresh_avatar_preview()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_show_title(True)
        toolbar.add_top_bar(header)

        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_vexpand(True)
        toolbar.set_content(content_scroll)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(620)
        clamp.set_tightening_threshold(420)
        content_scroll.set_child(clamp)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        clamp.set_child(content)

        intro = Gtk.Label(
            label=_("Update identity and security settings for this account."),
            xalign=0,
        )
        intro.set_css_classes(["dim-label", "account-intro"])
        intro.set_wrap(True)
        content.append(intro)

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
            size=40,
            text=self.current_user.get("username", "?"),
            show_initials=True,
        )
        self.avatar_preview.add_css_class("avatar-preview-compact")
        avatar_row.add_prefix(self.avatar_preview)

        modify_avatar_btn = Gtk.Button(label=_("Modify..."))
        modify_avatar_btn.set_css_classes(["flat", "account-inline-btn"])
        modify_avatar_btn.connect("clicked", self.on_avatar_actions_clicked)
        avatar_row.add_suffix(modify_avatar_btn)

        self.avatar_actions_popover = Gtk.Popover.new()
        self.avatar_actions_popover.set_autohide(True)
        self.avatar_actions_popover.set_has_arrow(True)
        self.avatar_actions_popover.set_position(Gtk.PositionType.BOTTOM)
        self.avatar_actions_popover.set_parent(modify_avatar_btn)

        avatar_actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        avatar_actions_box.set_margin_top(6)
        avatar_actions_box.set_margin_bottom(6)
        avatar_actions_box.set_margin_start(6)
        avatar_actions_box.set_margin_end(6)

        choose_avatar_action_btn = Gtk.Button(label=_("Choose image"))
        choose_avatar_action_btn.set_halign(Gtk.Align.FILL)
        choose_avatar_action_btn.set_css_classes(["flat", "account-popover-action"])
        choose_avatar_action_btn.connect("clicked", self.on_avatar_choose_action_clicked)
        avatar_actions_box.append(choose_avatar_action_btn)

        remove_avatar_action_btn = Gtk.Button(label=_("Remove avatar"))
        remove_avatar_action_btn.set_halign(Gtk.Align.FILL)
        remove_avatar_action_btn.set_css_classes(
            ["flat", "destructive-action", "account-popover-action"]
        )
        remove_avatar_action_btn.connect("clicked", self.on_avatar_remove_action_clicked)
        avatar_actions_box.append(remove_avatar_action_btn)
        self.avatar_remove_action_btn = remove_avatar_action_btn

        self.avatar_actions_popover.set_child(avatar_actions_box)

        username_row = Adw.ActionRow()
        username_row.set_title(_("Account name"))
        username_row.set_subtitle(_("Shown in the interface and profile card"))
        profile_group.add(username_row)

        self.username_entry = Gtk.Entry()
        self.username_entry.set_hexpand(True)
        self.username_entry.set_text(self.current_user.get("username", ""))
        self.username_entry.set_placeholder_text(_("e.g. Patrick"))
        self.username_entry.connect("changed", self.on_username_changed)
        self.username_entry.connect("activate", self.on_save_username_clicked)
        username_row.add_suffix(self.username_entry)

        save_name_btn = Gtk.Button(label=_("Save"))
        save_name_btn.set_css_classes(["suggested-action", "account-inline-btn"])
        save_name_btn.set_sensitive(False)
        save_name_btn.set_visible(False)
        save_name_btn.connect("clicked", self.on_save_username_clicked)
        username_row.add_suffix(save_name_btn)
        self.save_name_btn = save_name_btn

        language_row = Adw.ActionRow()
        language_row.set_title(_("Interface language"))
        language_row.set_subtitle(_("Select your preferred display language"))
        profile_group.add(language_row)

        supported_languages = get_supported_languages()
        self.language_codes = [lang["code"] for lang in supported_languages]
        language_labels = [self._format_language_label(lang) for lang in supported_languages]
        self.language_dropdown = Gtk.DropDown.new_from_strings(language_labels)
        self.language_dropdown.add_css_class("account-compact-dropdown")
        self.language_dropdown.connect("notify::selected", self.on_language_selected)

        if self.selected_language in self.language_codes:
            self.language_dropdown.set_selected(self.language_codes.index(self.selected_language))

        language_row.add_suffix(self.language_dropdown)
        self._language_selection_ready = True

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
        pwd_btn.set_css_classes(["flat", "account-inline-btn"])
        pwd_btn.connect("clicked", lambda _b: self.on_change_password())
        change_pwd_row.add_suffix(pwd_btn)

        change_email_row = Adw.ActionRow()
        change_email_row.set_title(_("Email address"))
        change_email_row.set_subtitle(self.current_user.get("email", "—"))
        security_group.add(change_email_row)

        email_btn = Gtk.Button(label=_("Edit"))
        email_btn.set_css_classes(["flat", "account-inline-btn"])
        email_btn.connect("clicked", lambda _b: self.on_change_email())
        change_email_row.add_suffix(email_btn)

        reconfigure_2fa_row = Adw.ActionRow()
        reconfigure_2fa_row.set_title(_("Two-factor authentication (2FA)"))
        reconfigure_2fa_row.set_subtitle(_("Link or reconfigure a trusted device"))
        security_group.add(reconfigure_2fa_row)

        twofa_btn = Gtk.Button(label=_("Reconfigure"))
        twofa_btn.set_css_classes(["flat", "account-inline-btn"])
        twofa_btn.connect("clicked", lambda _b: self.on_reconfigure_2fa())
        reconfigure_2fa_row.add_suffix(twofa_btn)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(toolbar)
        self.set_content(self.toast_overlay)

    def _refresh_avatar_preview(self) -> None:
        username = self.current_user.get("username", "?")
        self.avatar_preview.set_text(username)

        avatar_path = self.current_user.get("avatar_path")
        if self.avatar_remove_action_btn:
            self.avatar_remove_action_btn.set_sensitive(bool(avatar_path))

        if not avatar_path:
            self.avatar_preview.set_custom_image(None)
            return

        try:
            texture = Gdk.Texture.new_from_filename(str(avatar_path))
            self.avatar_preview.set_custom_image(texture)
        except Exception:
            self.avatar_preview.set_custom_image(None)

    def _show_status(self, message: str, status_type: str = "info") -> None:
        if not self.toast_overlay:
            return

        toast = Adw.Toast.new(message)
        if status_type == "error":
            toast.set_timeout(5)
        elif status_type == "warning":
            toast.set_timeout(4)
        else:
            toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def on_username_changed(self, _entry: Gtk.Entry) -> None:
        if not self.save_name_btn:
            return

        current_username = self.current_user.get("username", "")
        new_username = self.username_entry.get_text().strip()
        is_dirty = bool(new_username) and new_username != current_username
        self.save_name_btn.set_visible(is_dirty)
        self.save_name_btn.set_sensitive(is_dirty)

    def on_avatar_actions_clicked(self, button: Gtk.Button) -> None:
        if not self.avatar_actions_popover:
            return

        _ = button
        self.avatar_actions_popover.popup()

    def on_avatar_choose_action_clicked(self, _button: Gtk.Button) -> None:
        if self.avatar_actions_popover:
            self.avatar_actions_popover.popdown()
        self.on_choose_avatar_clicked(_button)

    def on_avatar_remove_action_clicked(self, _button: Gtk.Button) -> None:
        if self.avatar_actions_popover:
            self.avatar_actions_popover.popdown()
        self.on_clear_avatar_clicked(_button)

    def _format_language_label(self, language: dict[str, str]) -> str:
        code = normalize_language(language.get("code", ""))
        fallback_emoji_map = {
            "en": "🇬🇧",
            "fr": "🇫🇷",
            "de": "🇩🇪",
            "it": "🇮🇹",
        }
        emoji = (language.get("emoji") or "").strip() or fallback_emoji_map.get(code, "")
        native_name = language.get("native_name", code)
        return f"{emoji} {native_name}" if emoji else native_name

    def on_language_selected(self, dropdown: Gtk.DropDown, _pspec) -> None:
        if not self._language_selection_ready:
            return

        selected_index = dropdown.get_selected()
        if selected_index < 0 or selected_index >= len(self.language_codes):
            return

        language_code = self.language_codes[selected_index]
        if language_code == self.selected_language:
            return

        user_id = self.current_user.get("id")
        if not user_id:
            self._show_status(_("❌ User not found"), "error")
            return

        resolved = normalize_language(language_code)
        previous_language = self.selected_language

        if not self.auth_service.update_user_language(user_id, resolved):
            self._language_selection_ready = False
            if previous_language in self.language_codes:
                dropdown.set_selected(self.language_codes.index(previous_language))
            self._language_selection_ready = True
            self._show_status(_("❌ Unable to update language"), "error")
            return

        self.selected_language = set_language(resolved)
        self.current_user["language"] = self.selected_language
        self.on_profile_updated({"language": self.selected_language})
        self._show_status(_("✅ Interface language updated"), "success")

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
        self.on_username_changed(self.username_entry)
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
