"""
Dialogue d'importation de CSV
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ImportCSVDialog(Adw.Window):
    """Dialogue pour importer des mots de passe depuis un fichier CSV"""
    
    def __init__(self, parent, db, csv_importer):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Importer depuis CSV")
        self.set_default_size(600, 500)
        
        self.parent_window = parent
        self.db = db
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
        title_label = Gtk.Label(label="Importer des mots de passe")
        title_label.set_css_classes(['title-2'])
        title_label.set_xalign(0)
        content.append(title_label)
        
        desc_label = Gtk.Label(
            label="Importez vos mots de passe depuis un export CSV de LastPass ou d'un autre gestionnaire."
        )
        desc_label.set_wrap(True)
        desc_label.set_xalign(0)
        desc_label.set_css_classes(['dim-label'])
        content.append(desc_label)
        
        # Groupe de sélection de fichier
        file_group = Adw.PreferencesGroup()
        file_group.set_title("Fichier CSV")
        
        # Ligne de sélection de fichier
        file_row = Adw.ActionRow()
        file_row.set_title("Fichier")
        file_row.set_subtitle("Sélectionnez votre fichier d'export CSV")
        
        select_button = Gtk.Button(label="Choisir un fichier")
        select_button.set_valign(Gtk.Align.CENTER)
        select_button.connect("clicked", self.on_select_file_clicked)
        file_row.add_suffix(select_button)
        
        self.file_label = Gtk.Label(label="Aucun fichier sélectionné")
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
        options_group.set_title("Options d'import")
        
        # Format
        format_row = Adw.ComboRow()
        format_row.set_title("Format du fichier")
        format_row.set_subtitle("Sélectionnez le format de votre export")
        
        format_model = Gtk.StringList()
        formats = self.csv_importer.get_supported_formats()
        self.format_list = []
        for format_name, description in formats.items():
            format_model.append(description)
            self.format_list.append(format_name)
        
        format_row.set_model(format_model)
        format_row.set_selected(0)  # LastPass par défaut
        self.format_row = format_row
        
        options_group.add(format_row)
        
        # En-tête
        header_row = Adw.SwitchRow()
        header_row.set_title("Première ligne = en-tête")
        header_row.set_subtitle("Activer si la première ligne contient les noms de colonnes")
        header_row.set_active(False)
        self.header_switch = header_row
        
        options_group.add(header_row)
        
        content.append(options_group)
        
        # Zone d'aperçu/résultats
        preview_group = Adw.PreferencesGroup()
        preview_group.set_title("Aperçu")
        
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
        buffer.set_text("Sélectionnez un fichier pour voir un aperçu...")
        
        preview_scroll.set_child(self.preview_text)
        preview_group.add(preview_scroll)
        
        content.append(preview_group)
        
        # Boutons d'action
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(10)
        
        cancel_button = Gtk.Button(label="Annuler")
        cancel_button.connect("clicked", lambda b: self.close())
        button_box.append(cancel_button)
        
        self.import_button = Gtk.Button(label="Importer")
        self.import_button.set_css_classes(['suggested-action'])
        self.import_button.set_sensitive(False)
        self.import_button.connect("clicked", self.on_import_clicked)
        button_box.append(self.import_button)
        
        content.append(button_box)
        
        main_box.append(content)
        self.set_content(main_box)
    
    def on_select_file_clicked(self, button):
        """Ouvre le sélecteur de fichier"""
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title("Sélectionner un fichier CSV")
        
        # Filtre pour CSV
        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("Fichiers CSV")
        csv_filter.add_pattern("*.csv")
        
        all_filter = Gtk.FileFilter()
        all_filter.set_name("Tous les fichiers")
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
            logger.error(f"Erreur lors de la sélection du fichier: {e}")
    
    def show_preview(self):
        """Affiche un aperçu du fichier"""
        if not self.selected_file:
            return
        
        try:
            with open(self.selected_file, 'r', encoding='utf-8') as f:
                # Lire les 10 premières lignes
                lines = []
                for i, line in enumerate(f):
                    if i >= 10:
                        break
                    lines.append(line.strip())
                
                preview_text = "Aperçu des premières lignes:\n\n"
                preview_text += "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))
                
                if len(lines) == 10:
                    preview_text += "\n\n... (fichier tronqué pour l'aperçu)"
                
                buffer = self.preview_text.get_buffer()
                buffer.set_text(preview_text)
                
        except Exception as e:
            buffer = self.preview_text.get_buffer()
            buffer.set_text(f"Erreur lors de la lecture du fichier:\n{str(e)}")
    
    def on_import_clicked(self, button):
        """Lance l'importation"""
        if not self.selected_file:
            return
        
        # Désactiver le bouton pendant l'import
        self.import_button.set_sensitive(False)
        button.set_label("Importation en cours...")
        
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
        
        self.import_result = result
        
        if result['success']:
            # Sauvegarder dans la base de données
            saved_count = 0
            failed_count = 0
            
            for entry in result['entries']:
                try:
                    self.db.add_entry(
                        name=entry['name'],
                        username=entry['username'],
                        password=entry['password'],
                        url=entry['url'],
                        notes=entry['notes'],
                        category=entry['category'],
                        tags=entry['tags']
                    )
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Erreur lors de la sauvegarde de l'entrée {entry['name']}: {e}")
                    failed_count += 1
            
            # Afficher le résumé
            self.show_import_summary(saved_count, failed_count, result)
        else:
            # Afficher les erreurs
            self.show_import_errors(result)
        
        # Réactiver le bouton
        self.import_button.set_sensitive(True)
        button.set_label("Importer")
    
    def show_import_summary(self, saved_count, failed_count, result):
        """Affiche un résumé de l'importation"""
        summary = f"✅ Importation terminée\n\n"
        summary += f"Entrées importées avec succès: {saved_count}\n"
        
        if failed_count > 0:
            summary += f"Entrées échouées: {failed_count}\n"
        
        if result.get('warnings'):
            summary += f"\n⚠️  Avertissements ({len(result['warnings'])}):\n"
            for warning in result['warnings'][:5]:  # Limiter à 5
                summary += f"  • {warning}\n"
            if len(result['warnings']) > 5:
                summary += f"  ... et {len(result['warnings']) - 5} autres\n"
        
        if result.get('errors'):
            summary += f"\n❌ Erreurs ({len(result['errors'])}):\n"
            for error in result['errors'][:5]:  # Limiter à 5
                summary += f"  • {error}\n"
            if len(result['errors']) > 5:
                summary += f"  ... et {len(result['errors']) - 5} autres\n"
        
        buffer = self.preview_text.get_buffer()
        buffer.set_text(summary)
        
        # Mettre à jour l'interface parent
        if hasattr(self.parent_window, 'refresh_list'):
            self.parent_window.refresh_list()
        
        # Afficher une notification
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading("Import terminé")
        dialog.set_body(f"{saved_count} mots de passe ont été importés avec succès.")
        dialog.add_response("ok", "OK")
        dialog.connect("response", lambda d, r: self.close())
        dialog.present()
    
    def show_import_errors(self, result):
        """Affiche les erreurs d'importation"""
        error_text = "❌ Échec de l'importation\n\n"
        
        if result.get('errors'):
            error_text += "Erreurs:\n"
            for error in result['errors']:
                error_text += f"  • {error}\n"
        
        buffer = self.preview_text.get_buffer()
        buffer.set_text(error_text)
        
        # Afficher un dialogue d'erreur
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading("Erreur d'import")
        dialog.set_body("L'importation a échoué. Vérifiez le format du fichier.")
        dialog.add_response("ok", "OK")
        dialog.present()
