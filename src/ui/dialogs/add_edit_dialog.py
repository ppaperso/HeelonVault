"""Dialogue d'ajout ou de modification d'une entrée."""

import gi
from typing import Any, List

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
from .helpers import present_alert
from .password_generator_dialog import PasswordGeneratorDialog


def split_tags(text: str) -> List[str]:
    return [tag.strip() for tag in text.split(',') if tag.strip()]


class AddEditDialog(Adw.Window):
    """Dialogue d'ajout/édition d'entrée"""

    def __init__(self, parent, db: Any, entry=None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(620, 780)
        self.db = db
        self.entry = entry
        self.parent_window = parent
        self.set_title("Modifier l'entrée" if entry else "Nouvelle entrée")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(680)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title_row, self.title_entry = self.create_entry_row("Titre *", entry['title'] if entry else "")
        content.append(title_row)

        cat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        cat_label = Gtk.Label(label="Catégorie", xalign=0)
        cat_box.append(cat_label)

        self.category_dropdown = Gtk.DropDown()
        categories = self.db.get_all_categories()
        cat_names = [cat[0] for cat in categories]
        string_list = Gtk.StringList()
        for cat in cat_names:
            string_list.append(cat)
        self.category_dropdown.set_model(string_list)

        if entry and entry['category']:
            try:
                idx = cat_names.index(entry['category'])
                self.category_dropdown.set_selected(idx)
            except ValueError:
                pass

        cat_box.append(self.category_dropdown)
        content.append(cat_box)

        tags_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        tags_label = Gtk.Label(label="Tags (séparés par des virgules)", xalign=0)
        tags_box.append(tags_label)

        self.tags_entry = Gtk.Entry()
        if entry and entry['tags']:
            self.tags_entry.set_text(", ".join(entry['tags']))
        tags_box.append(self.tags_entry)
        content.append(tags_box)

        username_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        username_label = Gtk.Label(label="👤 Nom d'utilisateur / Login (optionnel)", xalign=0)
        username_box.append(username_label)

        self.username_entry = Gtk.Entry()
        self.username_entry.set_text(entry['username'] if entry and entry['username'] else "")
        self.username_entry.set_placeholder_text("Ex: user@exemple.com ou mon_login")
        username_box.append(self.username_entry)

        username_hint = Gtk.Label(label="Pour les sites web, entrez votre identifiant de connexion", xalign=0)
        username_hint.set_css_classes(['caption', 'dim-label'])
        username_box.append(username_hint)
        content.append(username_box)

        pass_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        pass_label = Gtk.Label(label="Mot de passe *", xalign=0)
        pass_box.append(pass_label)

        pass_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.password_entry = Gtk.PasswordEntry()
        if entry:
            self.password_entry.set_text(entry['password'])
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.set_hexpand(True)
        pass_input_box.append(self.password_entry)

        gen_btn = Gtk.Button(label="Générer")
        gen_btn.connect("clicked", self.on_generate_clicked)
        pass_input_box.append(gen_btn)

        pass_box.append(pass_input_box)
        content.append(pass_box)

        url_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        url_label = Gtk.Label(label="🌐 URL (optionnel)", xalign=0)
        url_box.append(url_label)

        self.url_entry = Gtk.Entry()
        if entry and entry['url']:
            self.url_entry.set_text(entry['url'])
        self.url_entry.set_placeholder_text("https://exemple.com")
        url_box.append(self.url_entry)
        content.append(url_box)

        notes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        notes_label = Gtk.Label(label="📝 Notes", xalign=0)
        notes_box.append(notes_label)

        # Créer un ScrolledWindow pour le TextView
        notes_scrolled = Gtk.ScrolledWindow()
        notes_scrolled.set_min_content_height(150)
        notes_scrolled.set_vexpand(True)
        notes_scrolled.set_hexpand(True)
        
        self.notes_text = Gtk.TextView()
        self.notes_text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes_text.set_left_margin(10)
        self.notes_text.set_right_margin(10)
        self.notes_text.set_top_margin(10)
        self.notes_text.set_bottom_margin(10)
        
        if entry and entry['notes']:
            buffer = self.notes_text.get_buffer()
            buffer.set_text(entry['notes'])
        
        notes_scrolled.set_child(self.notes_text)
        notes_box.append(notes_scrolled)
        content.append(notes_box)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)

        cancel_btn = Gtk.Button(label="Annuler")
        cancel_btn.connect("clicked", lambda b: self.close())
        action_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Valider")
        save_btn.set_css_classes(['suggested-action'])
        save_btn.connect("clicked", self.on_save_clicked)
        action_box.append(save_btn)

        content.append(action_box)

        scrolled.set_child(content)
        box.append(scrolled)
        self.set_content(box)

    def create_entry_row(self, label_text, value):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        label = Gtk.Label(label=label_text, xalign=0)
        label.set_css_classes(['title-4'])
        box.append(label)

        entry = Gtk.Entry()
        entry.set_text(value)
        box.append(entry)
        return box, entry

    def on_generate_clicked(self, button):
        dialog = PasswordGeneratorDialog(self, self.set_generated_password)
        dialog.present()

    def set_generated_password(self, password: str):
        self.password_entry.set_text(password)

    def on_save_clicked(self, button):
        title = self.title_entry.get_text()
        username = self.username_entry.get_text()
        password = self.password_entry.get_text()
        url = self.url_entry.get_text()

        selected = self.category_dropdown.get_selected()
        category = self.category_dropdown.get_model().get_string(selected) if selected != Gtk.INVALID_LIST_POSITION else ""

        tags_text = self.tags_entry.get_text()
        tags = split_tags(tags_text)

        notes_buffer = self.notes_text.get_buffer()
        notes = notes_buffer.get_text(notes_buffer.get_start_iter(), notes_buffer.get_end_iter(), False)

        if not title or not password:
            present_alert(
                self,
                "Champs requis",
                "Le titre et le mot de passe sont obligatoires.",
                [("ok", "OK")],
                default="ok",
            )
            return

        if self.entry:
            self.db.update_entry(self.entry['id'], title, username, password, url, notes, category, tags)
        else:
            self.db.add_entry(title, username, password, url, notes, category, tags)

        if hasattr(self.parent_window, 'load_entries'):
            self.parent_window.load_entries()
        if hasattr(self.parent_window, 'load_tags'):
            self.parent_window.load_tags()

        self.close()
