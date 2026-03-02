"""Dialogue de génération de mot de passe."""

import gi  # type: ignore[import]

from src.i18n import _
from src.services.password_generator import PasswordGenerator

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk  # type: ignore[attr-defined]  # noqa: E402


class PasswordGeneratorDialog(Adw.Window):
    """Dialogue de génération de mot de passe"""

    def __init__(self, parent, callback):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(500, 550)
        self.set_title(_("Générateur de mots de passe"))
        self.callback = callback

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        self.password_display = Gtk.Entry()
        self.password_display.set_editable(False)
        self.password_display.set_css_classes(['title-3'])
        content.append(self.password_display)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_bottom(10)

        copy_btn = Gtk.Button(label=_("Copier"))
        copy_btn.connect("clicked", self.on_copy_clicked)
        button_box.append(copy_btn)

        use_btn = Gtk.Button(label=_("Utiliser ce mot de passe"))
        use_btn.set_css_classes(['suggested-action'])
        use_btn.connect("clicked", self.on_use_clicked)
        button_box.append(use_btn)

        content.append(button_box)

        separator = Gtk.Separator()
        separator.set_margin_top(10)
        separator.set_margin_bottom(10)
        content.append(separator)

        type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        type_box.set_homogeneous(True)

        self.random_btn = Gtk.ToggleButton(label=_("Aléatoire"))
        self.random_btn.set_active(True)
        self.random_btn.connect("toggled", self.on_type_changed)
        type_box.append(self.random_btn)

        self.passphrase_btn = Gtk.ToggleButton(label=_("Phrase de passe"))
        self.passphrase_btn.connect("toggled", self.on_type_changed)
        type_box.append(self.passphrase_btn)

        content.append(type_box)

        self.random_options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        length_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        length_label = Gtk.Label(label=_("Longueur:"))
        length_label.set_xalign(0)
        length_label.set_hexpand(True)
        length_box.append(length_label)

        self.length_spin = Gtk.SpinButton()
        self.length_spin.set_range(12, 64)
        self.length_spin.set_increments(1, 4)
        self.length_spin.set_value(20)
        self.length_spin.connect("value-changed", lambda x: self.generate_password())
        length_box.append(self.length_spin)
        self.random_options.append(length_box)

        self.uppercase_check = Gtk.CheckButton(label=_("Majuscules (A-Z)"))
        self.uppercase_check.set_active(True)
        self.uppercase_check.connect("toggled", lambda x: self.generate_password())
        self.random_options.append(self.uppercase_check)

        self.lowercase_check = Gtk.CheckButton(label=_("Minuscules (a-z)"))
        self.lowercase_check.set_active(True)
        self.lowercase_check.connect("toggled", lambda x: self.generate_password())
        self.random_options.append(self.lowercase_check)

        self.digits_check = Gtk.CheckButton(label=_("Chiffres (0-9)"))
        self.digits_check.set_active(True)
        self.digits_check.connect("toggled", lambda x: self.generate_password())
        self.random_options.append(self.digits_check)

        self.symbols_check = Gtk.CheckButton(label=_("Symboles (!@#$...)"))
        self.symbols_check.set_active(True)
        self.symbols_check.connect("toggled", lambda x: self.generate_password())
        self.random_options.append(self.symbols_check)

        self.ambiguous_check = Gtk.CheckButton(
            label=_("Exclure caractères ambigus (0, O, l, 1, I)")
        )
        self.ambiguous_check.set_active(True)
        self.ambiguous_check.connect("toggled", lambda x: self.generate_password())
        self.random_options.append(self.ambiguous_check)

        content.append(self.random_options)

        self.passphrase_options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.passphrase_options.set_visible(False)

        words_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        words_label = Gtk.Label(label=_("Nombre de mots:"))
        words_label.set_xalign(0)
        words_label.set_hexpand(True)
        words_box.append(words_label)

        self.words_spin = Gtk.SpinButton()
        self.words_spin.set_range(4, 8)
        self.words_spin.set_increments(1, 1)
        self.words_spin.set_value(5)
        self.words_spin.connect("value-changed", lambda x: self.generate_password())
        words_box.append(self.words_spin)
        self.passphrase_options.append(words_box)

        content.append(self.passphrase_options)

        regenerate_btn = Gtk.Button(label=_("Régénérer"))
        regenerate_btn.set_margin_top(10)
        regenerate_btn.connect("clicked", lambda x: self.generate_password())
        content.append(regenerate_btn)

        box.append(content)
        self.set_content(box)

        self.generate_password()

    def on_type_changed(self, button):
        if button == self.random_btn and button.get_active():
            self.passphrase_btn.set_active(False)
            self.random_options.set_visible(True)
            self.passphrase_options.set_visible(False)
            self.generate_password()
        elif button == self.passphrase_btn and button.get_active():
            self.random_btn.set_active(False)
            self.random_options.set_visible(False)
            self.passphrase_options.set_visible(True)
            self.generate_password()

    def generate_password(self):
        if self.random_btn.get_active():
            password = PasswordGenerator.generate(
                length=int(self.length_spin.get_value()),
                use_uppercase=self.uppercase_check.get_active(),
                use_lowercase=self.lowercase_check.get_active(),
                use_digits=self.digits_check.get_active(),
                use_symbols=self.symbols_check.get_active(),
                exclude_ambiguous=self.ambiguous_check.get_active(),
            )
        else:
            password = PasswordGenerator.generate_passphrase(
                word_count=int(self.words_spin.get_value())
            )
        self.password_display.set_text(password)

    def on_copy_clicked(self, button):
        self.get_clipboard().set(self.password_display.get_text())

    def on_use_clicked(self, button):
        self.callback(self.password_display.get_text())
        self.close()
