"""Dialogue d'importation de CSV"""

import logging
from pathlib import Path

import gi  # type: ignore[import]

from src.i18n import _
from src.models.password_entry import PasswordEntry
from src.services.password_service import PasswordService

from .helpers import present_alert

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


class ImportCSVDialog(Adw.Window):
    """Dialogue pour importer des mots de passe depuis un fichier CSV"""

    def __init__(self, parent, password_service: PasswordService, csv_importer):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title(_("Import from CSV"))
        self.set_default_size(600, 500)

        self.parent_window = parent
        self.password_service = password_service
        self.csv_importer = csv_importer
        self.selected_file = None
        self.import_result = None

        # Layout principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        header = Adw.HeaderBar()
        main_box.append(header)

        # Contenu avec préférences
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)

        # Titre et description
        title_label = Gtk.Label(label=_("Import passwords"))
        title_label.set_css_classes(['title-2'])
        title_label.set_xalign(0)
        content.append(title_label)

        desc_label = Gtk.Label(
            label=_(
                "Import your passwords from a LastPass CSV export or "
                "another password manager."
            )
        )
        desc_label.set_wrap(True)
        desc_label.set_xalign(0)
        desc_label.set_css_classes(['dim-label'])
        content.append(desc_label)

        # Groupe de sélection de fichier
        file_group = Adw.PreferencesGroup()
        file_group.set_title(_("CSV file"))

        # Ligne de sélection de fichier
        file_row = Adw.ActionRow()
        file_row.set_title(_("File"))
        file_row.set_subtitle(_("Select your CSV export file"))

        select_button = Gtk.Button(label=_("Choose file"))
        select_button.set_valign(Gtk.Align.CENTER)
        select_button.connect("clicked", self.on_select_file_clicked)
        file_row.add_suffix(select_button)

        self.file_label = Gtk.Label(label=_("No file selected"))
        self.file_label.set_css_classes(['caption', 'dim-label'])
        self.file_label.set_xalign(0)
        self.file_label.set_margin_top(5)

        file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        file_box.append(file_row)
        file_box.append(self.file_label)

        file_group.add(file_box)
        content.append(file_group)

        # Groupe d'options
        options_group = Adw.PreferencesGroup()
        options_group.set_title(_("Import options"))

        # Format
        format_row = Adw.ComboRow()
        format_row.set_title(_("File format"))
        format_row.set_subtitle(_("Select your export format"))

        format_model = Gtk.StringList()
        formats = self.csv_importer.get_supported_formats()
        self.format_list = []
        for format_name, description in formats.items():
            format_model.append(description)
            self.format_list.append(format_name)

        format_row.set_model(format_model)
        # Sélectionner CSV (,) par défaut (generic_comma est généralement en position 1)
        default_index = (
            self.format_list.index('generic_comma') if 'generic_comma' in self.format_list else 0
        )
        format_row.set_selected(default_index)
        self.format_row = format_row

        options_group.add(format_row)

        # En-tête
        header_row = Adw.SwitchRow()
        header_row.set_title(_("First row = header"))
        header_row.set_subtitle(_("Enable if the first row contains column names"))
        header_row.set_active(False)
        self.header_switch = header_row

        options_group.add(header_row)

        content.append(options_group)

        # Zone d'aperçu/résultats
        preview_group = Adw.PreferencesGroup()
        preview_group.set_title(_("Preview"))

        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_min_content_height(150)
        preview_scroll.set_vexpand(True)
        preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.preview_text = Gtk.TextView()
        self.preview_text.set_editable(False)
        self.preview_text.set_wrap_mode(Gtk.WrapMode.WORD)
        self.preview_text.set_margin_start(10)
        self.preview_text.set_margin_end(10)
        self.preview_text.set_margin_top(10)
        self.preview_text.set_margin_bottom(10)

        buffer = self.preview_text.get_buffer()
        buffer.set_text(_("Select a file to preview..."))

        preview_scroll.set_child(self.preview_text)
        preview_group.add(preview_scroll)

        content.append(preview_group)

        # Boutons d'action
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(10)

        cancel_button = Gtk.Button(label=_("Cancel"))
        cancel_button.connect("clicked", lambda b: self.close())
        button_box.append(cancel_button)

        self.import_button = Gtk.Button(label=_("Import"))
        self.import_button.set_css_classes(['suggested-action'])
        self.import_button.set_sensitive(False)
        self.import_button.connect("clicked", self.on_import_clicked)
        button_box.append(self.import_button)

        content.append(button_box)

        main_box.append(content)
        self.set_content(main_box)

    def on_select_file_clicked(self, _button):
        """Ouvre le sélecteur de fichier"""
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title(_("Select a CSV file"))

        # Filtre pour CSV
        csv_filter = Gtk.FileFilter()
        csv_filter.set_name(_("CSV files"))
        csv_filter.add_pattern("*.csv")

        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All files"))
        all_filter.add_pattern("*")

        filter_list = Gio.ListStore.new(Gtk.FileFilter)
        filter_list.append(csv_filter)
        filter_list.append(all_filter)

        file_dialog.set_filters(filter_list)
        file_dialog.set_default_filter(csv_filter)

        file_dialog.open(self, None, self.on_file_selected)

    def on_file_selected(self, dialog, result):
        """Callback après sélection du fichier"""
        try:
            file = dialog.open_finish(result)
            if file:
                self.selected_file = Path(file.get_path())
                self.file_label.set_label(str(self.selected_file))
                self.import_button.set_sensitive(True)

                # Afficher un aperçu
                self.show_preview()
        except Exception as e:
            logger.error("Error selecting file: %s", e)

    def show_preview(self):
        """Affiche un aperçu du fichier"""
        if not self.selected_file:
            return

        try:
            with open(self.selected_file, encoding='utf-8') as f:
                # Lire les 10 premières lignes
                lines = []
                for i, line in enumerate(f):
                    if i >= 10:
                        break
                    lines.append(line.strip())

                preview_text = _("Preview of first lines:\n\n")
                preview_text += "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))

                if len(lines) == 10:
                    preview_text += _("\n\n... (file truncated for preview)")

                buffer = self.preview_text.get_buffer()
                buffer.set_text(preview_text)

        except Exception as e:
            buffer = self.preview_text.get_buffer()
            buffer.set_text(_("Error while reading file:\n%s") % str(e))

    def on_import_clicked(self, button):
        """Lance l'importation"""
        if not self.selected_file:
            return

        # Désactiver le bouton pendant l'import
        self.import_button.set_sensitive(False)
        button.set_label(_("Importing..."))

        # Récupérer les options
        format_index = self.format_row.get_selected()
        format_name = self.format_list[format_index]
        has_header = self.header_switch.get_active()

        # Importer
        result = self.csv_importer.import_from_csv(
            self.selected_file,
            format_name=format_name,
            has_header=has_header
        )
        logger.info(
            "CSV import started for %s (format=%s, header=%s)",
            self.selected_file,
            format_name,
            has_header
        )

        self.import_result = result

        if result['success']:
            # Sauvegarder dans la base de données
            saved_count = 0
            failed_count = 0

            for entry in result['entries']:
                try:
                    password_entry = PasswordEntry(
                        title=entry['name'],
                        username=entry['username'],
                        password=entry['password'],
                        url=entry['url'],
                        notes=entry['notes'],
                        category=entry['category'],
                        tags=entry['tags'],
                    )
                    self.password_service.create_entry(password_entry)
                    saved_count += 1
                except Exception as e:
                    logger.error(
                        "Error while saving entry %s: %s",
                        entry["name"],
                        e,
                    )
                    failed_count += 1

            # Afficher le résumé
            logger.info(
                "CSV import finished: %d saved, %d failed, %d warnings",
                saved_count,
                failed_count,
                len(result.get('warnings', []))
            )
            self.show_import_summary(saved_count, failed_count, result)
        else:
            # Afficher les erreurs
            self.show_import_errors(result)

        # Réactiver le bouton
        self.import_button.set_sensitive(True)
        button.set_label(_("Import"))

    def show_import_summary(self, saved_count, failed_count, result):
        """Affiche un résumé de l'importation"""
        summary = _("✅ Import completed\n\n")
        summary += _("Entries imported successfully: %s\n") % saved_count

        if failed_count > 0:
            summary += _("Failed entries: %s\n") % failed_count

        if result.get('warnings'):
            summary += _("\n⚠️  Warnings (%s):\n") % len(result['warnings'])
            for warning in result['warnings'][:5]:  # Limiter à 5
                summary += f"  • {warning}\n"
            if len(result['warnings']) > 5:
                summary += _("  ... and %s more\n") % (len(result['warnings']) - 5)

        if result.get('errors'):
            summary += _("\n❌ Errors (%s):\n") % len(result['errors'])
            for error in result['errors'][:5]:  # Limiter à 5
                summary += f"  • {error}\n"
            if len(result['errors']) > 5:
                summary += _("  ... and %s more\n") % (len(result['errors']) - 5)

        buffer = self.preview_text.get_buffer()
        buffer.set_text(summary)

        # Afficher une notification
        present_alert(
            self,
            _("Import completed"),
            _("%s passwords were imported successfully.") % saved_count,
            [("ok", _("OK"))],
            default="ok",
            on_response=lambda response: self.on_import_complete(),
        )

    def on_import_complete(self):
        """Appelé quand l'import est terminé et que l'utilisateur ferme la notification"""
        # Rafraîchir la liste dans la fenêtre principale
        if hasattr(self.parent_window, 'load_entries'):
            self.parent_window.load_entries()
        if hasattr(self.parent_window, 'load_tags'):
            self.parent_window.load_tags()

        # Fermer la fenêtre d'import
        self.close()

    def show_import_errors(self, result):
        """Affiche les erreurs d'importation"""
        error_text = _("❌ Import failed\n\n")

        if result.get('errors'):
            error_text += _("Errors:\n")
            for error in result['errors']:
                error_text += f"  • {error}\n"

        buffer = self.preview_text.get_buffer()
        buffer.set_text(error_text)

        # Afficher un dialogue d'erreur
        present_alert(
            self,
            _("Import error"),
            _("Import failed. Check the file format."),
            [("ok", _("OK"))],
            default="ok",
        )
