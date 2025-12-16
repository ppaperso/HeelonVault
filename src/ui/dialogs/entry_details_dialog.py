"""Dialogue d'informations détaillées sur une entrée de mot de passe."""

from typing import Callable

from src.models.password_entry import PasswordEntry

import gi  # type: ignore[import]

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib  # type: ignore[attr-defined]  # noqa: E402


class EntryDetailsDialog(Adw.Window):
    """Dialogue moderne pour afficher les détails d'une entrée."""

    def __init__(
        self,
        parent,
        entry: PasswordEntry,
        edit_callback: Callable[[int], None],
        delete_callback: Callable[[int], None],
    ):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 700)
        self.entry = entry
        self.edit_callback = edit_callback
        self.delete_callback = delete_callback
        self.parent_window = parent

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        box.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(640)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_start(30)
        content.set_margin_end(30)
        content.set_margin_top(30)
        content.set_margin_bottom(30)

        title_label = Gtk.Label(label=entry.title, xalign=0)
        title_label.set_css_classes(['title-1'])
        title_label.set_wrap(True)
        content.append(title_label)

        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        meta_box.set_margin_bottom(10)

        if entry.category:
            cat_label = Gtk.Label(label=f"📁 {entry.category}")
            cat_label.set_css_classes(['caption'])
            meta_box.append(cat_label)

        for tag in entry.tags:
            tag_label = Gtk.Label(label=f"#{tag}")
            tag_label.set_css_classes(['caption', 'accent'])
            meta_box.append(tag_label)

        content.append(meta_box)

        sep1 = Gtk.Separator()
        content.append(sep1)

        if entry.username:
            username_box = self._create_field_box("👤 Nom d'utilisateur", entry.username, copyable=True)
            content.append(username_box)

        password_box = self._create_field_box("🔑 Mot de passe", entry.password, copyable=True, is_password=True)
        content.append(password_box)

        if entry.url:
            url_box = self._create_field_box("🌐 URL", entry.url, copyable=True, is_url=True)
            content.append(url_box)

        if entry.notes:
            notes_label = Gtk.Label(label="📝 Notes", xalign=0)
            notes_label.set_css_classes(['title-4'])
            notes_label.set_margin_top(10)
            content.append(notes_label)

            notes_frame = Gtk.Frame()
            notes_frame.set_css_classes(['card'])

            notes_text = Gtk.Label(label=entry.notes, xalign=0, wrap=True)
            notes_text.set_margin_start(15)
            notes_text.set_margin_end(15)
            notes_text.set_margin_top(15)
            notes_text.set_margin_bottom(15)
            notes_frame.set_child(notes_text)
            content.append(notes_frame)

        sep2 = Gtk.Separator()
        sep2.set_margin_top(10)
        content.append(sep2)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.CENTER)
        action_box.set_margin_top(10)

        edit_btn = Gtk.Button(label="✏️  Modifier")
        edit_btn.set_css_classes(['suggested-action'])
        edit_btn.connect("clicked", lambda x: self._on_edit())
        action_box.append(edit_btn)

        delete_btn = Gtk.Button(label="🗑️  Supprimer")
        delete_btn.set_css_classes(['destructive-action'])
        delete_btn.connect("clicked", lambda x: self._on_delete())
        action_box.append(delete_btn)

        content.append(action_box)

        scrolled.set_child(content)
        box.append(scrolled)
        self.set_content(box)

    def _create_field_box(self, label_text, value, copyable=False, is_password=False, is_url=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        label = Gtk.Label(label=label_text, xalign=0)
        label.set_css_classes(['title-4'])
        box.append(label)

        value_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        value_entry = Gtk.Entry()
        value_entry.set_text(value)
        value_entry.set_editable(False)
        value_entry.set_hexpand(True)

        if is_password:
            value_entry.set_visibility(False)

        value_box.append(value_entry)

        if is_password:
            show_btn = Gtk.Button(icon_name="view-reveal-symbolic")
            show_btn.set_tooltip_text("Afficher/masquer")
            show_btn.connect("clicked", lambda x: value_entry.set_visibility(not value_entry.get_visibility()))
            value_box.append(show_btn)

        if copyable:
            copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
            copy_btn.set_tooltip_text("Copier")
            copy_btn.connect(
                "clicked",
                lambda x, label=label_text: self._copy_to_clipboard(value, f"{label} copié")
            )
            value_box.append(copy_btn)

        if is_url and value:
            open_btn = Gtk.Button(icon_name="web-browser-symbolic")
            open_btn.set_tooltip_text("Ouvrir dans le navigateur")
            open_btn.connect("clicked", lambda x: self._open_url(value))
            value_box.append(open_btn)

        box.append(value_box)
        return box

    def _copy_to_clipboard(self, text, message="Copié dans le presse-papiers"):
        if self.parent_window and hasattr(self.parent_window, "copy_to_clipboard"):
            self.parent_window.copy_to_clipboard(text, message)
            return
        clipboard = self.get_clipboard()
        if clipboard:
            try:
                bytes_value = GLib.Bytes.new(text.encode('utf-8'))
                provider = Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", bytes_value)
                clipboard.set_content(provider)
                clipboard.store_async(None, self._on_clipboard_store_finished, None)
            except Exception as exc:
                print(f"Impossible de copier dans le presse-papiers: {exc}")

    def _on_clipboard_store_finished(self, clipboard, result, _data):
        try:
            clipboard.store_finish(result)
        except Exception:
            pass

    def _open_url(self, url):
        import subprocess

        try:
            subprocess.Popen(['xdg-open', url])
        except Exception as e:
            print(f"Erreur lors de l'ouverture de l'URL: {e}")

    def _on_edit(self):
        self.close()
        if self.entry.id is not None:
            self.edit_callback(self.entry.id)

    def _on_delete(self):
        """Demander confirmation avant de supprimer"""
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading("Confirmer la suppression")
        dialog.set_body(
            f"Êtes-vous sûr de vouloir supprimer l'entrée '{self.entry.title}' ?\n\nCette action est irréversible."
        )
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("delete", "Supprimer")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda d, r: self._on_delete_confirmed(r))
        dialog.present()
    
    def _on_delete_confirmed(self, response):
        """Callback de confirmation de suppression"""
        if response == "delete":
            self.close()
            if self.entry.id is not None:
                self.delete_callback(self.entry.id)
