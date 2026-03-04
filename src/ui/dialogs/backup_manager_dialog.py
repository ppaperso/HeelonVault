"""
Dialogue de gestion des sauvegardes (admin uniquement)
"""

import logging

import gi  # type: ignore[import]

from src.i18n import _
from src.ui.notifications import error as show_error
from src.ui.notifications import toast as show_toast

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


class BackupManagerDialog(Adw.Window):
    """Dialogue de gestion des sauvegardes (admin uniquement)

    Permet aux administrateurs de :
    - Visualiser toutes les sauvegardes existantes
    - Voir le statut de chaque sauvegarde
    - Créer une sauvegarde manuelle
    - Consulter les instructions de restauration
    """

    def __init__(self, parent, backup_service, current_username: str):
        """Initialise le dialogue de gestion des sauvegardes.

        Args:
            parent: Fenêtre parente
            backup_service: Instance du BackupService
            current_username: Nom de l'utilisateur actuel
        """
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(700, 600)
        self.set_title(_("Backup management"))

        self.backup_service = backup_service
        self.current_username = current_username
        self.parent_window = parent

        self._build_ui()
        self.load_backups()

    def _build_ui(self):
        """Construit l'interface utilisateur."""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header
        header = Adw.HeaderBar()
        main_box.append(header)

        # Contenu scrollable
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        # Titre et description
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        title = Gtk.Label(label=_("💾 Backup management"))
        title.set_css_classes(['title-2'])
        title.set_halign(Gtk.Align.START)
        title_box.append(title)

        subtitle = Gtk.Label(
            label=_(
                "Back up and restore all system data "
                "(all users)"
            )
        )
        subtitle.set_css_classes(['dim-label'])
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_wrap(True)
        title_box.append(subtitle)

        content.append(title_box)

        # Section : Créer une sauvegarde manuelle
        manual_backup_group = Adw.PreferencesGroup()
        manual_backup_group.set_title(_("Full system backup"))
        manual_backup_group.set_description(
            _("Create a backup of ALL data (all users)")
        )

        manual_backup_row = Adw.ActionRow()
        manual_backup_row.set_title(_("Create a system backup now"))
        manual_backup_row.set_subtitle(
            _("Backup: users.db + all passwords_*.db + all salt_*.bin")
        )

        backup_button = Gtk.Button(label=_("💾 Create"))
        backup_button.set_css_classes(['suggested-action'])
        backup_button.set_valign(Gtk.Align.CENTER)
        backup_button.connect("clicked", self.on_create_backup_clicked)
        manual_backup_row.add_suffix(backup_button)

        manual_backup_group.add(manual_backup_row)
        content.append(manual_backup_group)

        # Section : Liste des sauvegardes
        backups_group = Adw.PreferencesGroup()
        backups_group.set_title(_("Existing system backups"))
        backups_group.set_description(_("List of all full system backups"))

        self.backups_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.backups_list.set_css_classes(['boxed-list'])

        backups_group.add(self.backups_list)
        content.append(backups_group)

        # Section : Instructions de restauration
        restore_group = Adw.PreferencesGroup()
        restore_group.set_title(_("📋 Restore instructions"))
        restore_group.set_description(_("How to restore a backup"))

        instructions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        instructions_box.set_margin_start(12)
        instructions_box.set_margin_end(12)
        instructions_box.set_margin_top(12)
        instructions_box.set_margin_bottom(12)

        steps = [
            ("1️⃣", _("Close the application completely")),
            ("2️⃣", _("Open the backups folder (button below)")),
            ("3️⃣", _("Open the folder system_backup_YYYYMMDD_HHMMSS")),
            ("4️⃣", _("Copy ALL files from the backup folder")),
            ("5️⃣", _("Paste and replace in the main data folder")),
            ("6️⃣", _("Restart the application")),
        ]

        for emoji, step in steps:
            step_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

            emoji_label = Gtk.Label(label=emoji)
            emoji_label.set_width_chars(3)
            step_box.append(emoji_label)

            step_label = Gtk.Label(label=step)
            step_label.set_halign(Gtk.Align.START)
            step_label.set_wrap(True)
            step_label.set_xalign(0)
            step_box.append(step_label)

            instructions_box.append(step_box)

        # Bouton pour ouvrir le dossier des sauvegardes
        open_folder_row = Adw.ActionRow()
        open_folder_row.set_title(_("Open backups folder"))
        open_folder_row.set_subtitle(str(self.backup_service.backup_dir))

        open_button = Gtk.Button(label=_("📁 Open"))
        open_button.set_valign(Gtk.Align.CENTER)
        open_button.connect("clicked", self.on_open_folder_clicked)
        open_folder_row.add_suffix(open_button)

        instructions_box.append(open_folder_row)

        restore_expander = Gtk.Expander()
        restore_expander.set_label(_("Show instructions"))
        restore_expander.set_child(instructions_box)

        restore_group.add(restore_expander)
        content.append(restore_group)

        scrolled.set_child(content)
        main_box.append(scrolled)

        self.set_content(main_box)

    def load_backups(self):
        """Charge et affiche la liste des sauvegardes système."""
        # Vider la liste actuelle
        while True:
            child = self.backups_list.get_first_child()
            if child is None:
                break
            self.backups_list.remove(child)

        # Récupérer les sauvegardes système
        backups = self.backup_service.list_system_backups()

        if not backups:
            # Aucune sauvegarde
            empty_row = Adw.ActionRow()
            empty_row.set_title(_("No system backup available"))
            empty_row.set_subtitle(
                _("Create your first full backup with the button above")
            )

            empty_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
            empty_icon.set_css_classes(['dim-label'])
            empty_row.add_prefix(empty_icon)

            self.backups_list.append(empty_row)
            logger.debug("No system backups found")
            return

        # Afficher chaque sauvegarde
        for backup_folder in backups:
            try:
                info = self.backup_service.get_system_backup_info(backup_folder)

                backup_row = Adw.ActionRow()
                backup_row.set_title(info['name'])

                # Calculer la taille en format lisible
                size_kb = info['size'] / 1024
                size_str = f"{size_kb:.1f} Ko" if size_kb < 1024 else f"{size_kb/1024:.1f} Mo"

                # Afficher le nombre de fichiers et la taille
                backup_row.set_subtitle(
                    _("📅 %(created)s • 📦 %(count)s files • 💾 %(size)s")
                    % {
                        "created": info['created_str'],
                        "count": info['file_count'],
                        "size": size_str,
                    }
                )

                # Icône de statut (OK si le dossier existe)
                status_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                status_icon.set_css_classes(['success'])
                backup_row.add_prefix(status_icon)

                # Ajouter un bouton pour voir les détails
                details_button = Gtk.Button(label=_("Details"))
                details_button.set_valign(Gtk.Align.CENTER)
                details_button.connect("clicked", self.on_show_backup_details, info)
                backup_row.add_suffix(details_button)

                self.backups_list.append(backup_row)

            except Exception as e:
                logger.exception("Error loading backup info for %s: %s", backup_folder, e)

        logger.info("Loaded %d system backups", len(backups))

    def on_create_backup_clicked(self, button):
        """Crée une sauvegarde complète du système."""
        logger.info("Creating full system backup")

        # Désactiver le bouton pendant la création
        button.set_sensitive(False)
        button.set_label(_("⏳ Creating..."))

        def do_backup():
            """Effectue la sauvegarde (dans le thread principal)."""
            try:
                backup_folder = self.backup_service.create_full_system_backup()

                if backup_folder:
                    logger.info("System backup created: %s", backup_folder.name)

                    show_toast(
                        self.parent_window or self,
                        _("✅ System backup created: %s") % backup_folder.name,
                        timeout=4,
                    )

                    # Rafraîchir la liste
                    self.load_backups()

                    button.set_label(_("💾 Create"))
                    button.set_sensitive(True)
                else:
                    logger.error("Failed to create system backup")
                    self.show_error_dialog(_("Failed to create system backup"))
                    button.set_label(_("💾 Create"))
                    button.set_sensitive(True)

            except Exception as e:
                logger.exception("Error while creating system backup: %s", e)
                self.show_error_dialog(_("Error: %s") % str(e))
                button.set_label(_("💾 Create"))
                button.set_sensitive(True)

        # Utiliser GLib.idle_add pour exécuter dans le thread principal
        GLib.idle_add(do_backup)

    def on_show_backup_details(self, _button, info: dict):
        """Affiche les détails d'une sauvegarde.

        Args:
            button: Bouton cliqué
            info: Informations sur la sauvegarde
        """
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(_("Details: %s") % info['name'])

        # Construire le message avec la liste des fichiers
        message = _("📅 Date: %s\n") % info['created_str']
        message += _("📦 Number of files: %s\n") % info['file_count']

        size_kb = info['size'] / 1024
        size_str = f"{size_kb:.1f} Ko" if size_kb < 1024 else f"{size_kb/1024:.1f} Mo"
        message += _("💾 Total size: %s\n") % size_str

        if info.get('files'):
            message += _("\n📄 Backed-up files:\n")
            for filename in info['files']:
                message += _("  • %s\n") % filename

        dialog.set_body(message)
        dialog.add_response("ok", _("OK"))
        dialog.present()

    def on_open_folder_clicked(self, _button):
        """Ouvre le dossier des sauvegardes dans le gestionnaire de fichiers."""
        import subprocess

        try:
            # Utiliser xdg-open pour ouvrir le dossier
            subprocess.Popen(['xdg-open', str(self.backup_service.backup_dir)])  # noqa: S603, S607
            logger.info("Opening backups folder: %s", self.backup_service.backup_dir)
        except Exception as e:
            logger.exception("Error while opening folder: %s", e)
            self.show_error_dialog(_("Unable to open folder: %s") % str(e))

    def show_error_dialog(self, message: str):
        """Affiche un dialogue d'erreur.

        Args:
            message: Message d'erreur à afficher
        """
        show_error(self, message, heading=_("Error"))
