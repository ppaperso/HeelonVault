"""Dialogue de création de vault (multi-vault)."""

from __future__ import annotations

import gi  # type: ignore[import]

from src.i18n import _

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


class CreateVaultDialog(Adw.Window):
    """Collecte le nom du vault et le mot de passe maître associé."""

    def __init__(self, parent: Gtk.Window) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title(_("Create vault"))
        self.set_default_size(460, 320)

        self._success = False
        self._vault_name = ""
        self._master_password = ""

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        root.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        group = Adw.PreferencesGroup.new()

        self.name_row = Adw.EntryRow.new()
        self.name_row.set_title(_("Vault name"))
        self.name_row.set_text(_("New vault"))
        group.add(self.name_row)

        self.password_row = Adw.PasswordEntryRow.new()
        self.password_row.set_title(_("Master password"))
        group.add(self.password_row)

        content.append(group)

        self.error_label = Gtk.Label(label="", xalign=0)
        self.error_label.set_css_classes(["caption", "error"])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        content.append(self.error_label)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.connect("clicked", lambda _b: self.close())
        actions.append(cancel_btn)

        create_btn = Gtk.Button(label=_("Create"))
        create_btn.set_css_classes(["suggested-action"])
        create_btn.connect("clicked", self._on_create_clicked)
        actions.append(create_btn)

        content.append(actions)
        root.append(content)

        self.set_content(root)

    def _on_create_clicked(self, _button: Gtk.Button) -> None:
        name = self.name_row.get_text().strip()
        master_password = self.password_row.get_text()

        if not name:
            self._show_error(_("Vault name is required."))
            return
        if len(master_password) < 8:
            self._show_error(_("Master password must contain at least 8 characters."))
            return

        self._vault_name = name
        self._master_password = master_password
        self._success = True
        self.close()

    def _show_error(self, message: str) -> None:
        self.error_label.set_label(message)
        self.error_label.set_visible(True)

    def get_success(self) -> bool:
        return self._success

    def get_vault_name(self) -> str:
        return self._vault_name

    def get_master_password(self) -> str:
        return self._master_password
