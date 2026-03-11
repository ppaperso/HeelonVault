"""Dialogue de gestion des categories du vault actif."""

from __future__ import annotations

import gi  # type: ignore[import]

from src.i18n import _
from src.models.category import Category
from src.services.password_service import PasswordService

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


class ManageCategoriesDialog(Adw.Window):
    """Permet de creer, renommer et supprimer des categories."""

    def __init__(
        self,
        parent: Gtk.Window,
        password_service: PasswordService,
        on_changed: object | None = None,
    ) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(560, 560)
        self.set_title(_("Manage categories"))

        self.password_service = password_service
        self._on_changed = on_changed

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(Adw.HeaderBar())

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        self.parent_box = content

        title = Gtk.Label(label=_("Manage categories"), xalign=0)
        title.set_css_classes(["title-2"])
        content.append(title)

        self.categories_group = Adw.PreferencesGroup.new()
        content.append(self.categories_group)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        actions.set_halign(Gtk.Align.END)
        new_btn = Gtk.Button(label=_("New category"))
        new_btn.set_css_classes(["suggested-action"])
        new_btn.connect("clicked", self._on_new_category_clicked)
        actions.append(new_btn)
        content.append(actions)

        root.append(content)
        self.set_content(root)

        self.refresh()

    def refresh(self) -> None:
        # Adw.PreferencesGroup manages internal children; replace it entirely when refreshing.
        self.parent_box.remove(self.categories_group)
        self.categories_group = Adw.PreferencesGroup.new()
        categories = self.password_service.list_categories()
        for category in categories:
            self.categories_group.add(self._build_row(category))
        self.parent_box.append(self.categories_group)

    def _build_row(self, category: Category) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(category.name)

        if self.password_service.is_default_category(category.name):
            badge = Gtk.Label(label=_("default"))
            badge.add_css_class("status-role-admin")
            row.add_suffix(badge)

        rename_btn = Gtk.Button(icon_name="document-edit-symbolic")
        rename_btn.set_tooltip_text(_("Rename category"))
        rename_btn.set_css_classes(["flat", "circular"])
        rename_btn.connect("clicked", lambda _b: self._on_rename_clicked(category.name))
        row.add_suffix(rename_btn)

        delete_btn = Gtk.Button(icon_name="user-trash-symbolic")
        delete_btn.set_tooltip_text(_("Delete category"))
        delete_btn.set_css_classes(["flat", "circular", "destructive-action"])
        delete_btn.set_sensitive(not self.password_service.is_default_category(category.name))
        delete_btn.connect("clicked", lambda _b: self._on_delete_clicked(category.name))
        row.add_suffix(delete_btn)

        return row

    def _notify_changed(self) -> None:
        if callable(self._on_changed):
            self._on_changed()

    def _open_name_dialog(
        self,
        heading: str,
        initial_value: str,
        on_submit: object,
    ) -> None:
        dialog = Adw.MessageDialog.new(self, heading, "")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        entry = Gtk.Entry()
        entry.set_text(initial_value)
        entry.set_activates_default(True)
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        entry.set_margin_start(8)
        entry.set_margin_end(8)
        dialog.set_extra_child(entry)

        def on_response(_dlg, response: str) -> None:
            if response == "ok":
                value = entry.get_text().strip()
                if callable(on_submit):
                    on_submit(value)

        dialog.connect("response", on_response)
        dialog.present()

    def _on_new_category_clicked(self, _button: Gtk.Button) -> None:
        def submit(name: str) -> None:
            if not name:
                return
            if self.password_service.category_exists(name):
                return
            self.password_service.add_category(Category(name=name))
            self.refresh()
            self._notify_changed()

        self._open_name_dialog(_("New category"), "", submit)

    def _on_rename_clicked(self, old_name: str) -> None:
        def submit(new_name: str) -> None:
            if not new_name or new_name == old_name:
                return
            if self.password_service.category_exists(new_name):
                return
            if self.password_service.rename_category(old_name, new_name):
                self.refresh()
                self._notify_changed()

        self._open_name_dialog(_("Rename category"), old_name, submit)

    def _on_delete_clicked(self, name: str) -> None:
        dialog = Adw.MessageDialog.new(
            self,
            _("Delete category"),
            _(
                "Delete category %(name)s? Associated entries will move to category 'Autres'."
            )
            % {"name": name},
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dlg, response: str) -> None:
            if response != "delete":
                return
            if self.password_service.delete_category(name, "Autres"):
                self.refresh()
                self._notify_changed()

        dialog.connect("response", on_response)
        dialog.present()
