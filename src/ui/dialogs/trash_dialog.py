"""Dialogue de gestion de la corbeille."""

import logging
from collections.abc import Callable

import gi  # type: ignore[import]

from src.i18n import _
from src.models.password_entry import PasswordEntry
from src.services.password_service import PasswordService

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


class TrashDialog(Adw.Window):
    """Dialogue pour gérer la corbeille."""

    def __init__(
        self,
        parent,
        password_service: PasswordService,
        on_change_callback: Callable[[], None],
    ):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(800, 600)
        self.set_title(_("Corbeille"))

        self.password_service = password_service
        self.on_change_callback = on_change_callback
        self.parent_window = parent

        # Box principale
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)

        # Bouton vider la corbeille
        empty_button = Gtk.Button(label=_("Vider la corbeille"))
        empty_button.set_css_classes(["destructive-action"])
        empty_button.connect("clicked", self.on_empty_trash_clicked)
        header.pack_end(empty_button)

        box.append(header)

        # Contenu scrollable
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_vexpand(True)

        self.list_box = Gtk.ListBox()
        self.list_box.set_css_classes(["boxed-list"])
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)

        self.scrolled.set_child(self.list_box)
        box.append(self.scrolled)

        self.set_content(box)
        self.load_trash_entries()

    def load_trash_entries(self):
        """Charge les entrées de la corbeille."""
        # Vider la liste
        while True:
            row = self.list_box.get_row_at_index(0)
            if not row:
                break
            self.list_box.remove(row)

        # Charger les entrées
        entries = self.password_service.list_trash()

        if not entries:
            # Afficher un message si la corbeille est vide
            empty_status = Adw.StatusPage()
            empty_status.set_icon_name("user-trash-symbolic")
            empty_status.set_title(_("Corbeille vide"))
            empty_status.set_description(_("Les entrées supprimées apparaîtront ici"))
            self.scrolled.set_child(empty_status)
            return

        # Afficher les entrées
        self.scrolled.set_child(self.list_box)
        for entry in entries:
            row = self._create_entry_row(entry)
            self.list_box.append(row)

    def _create_entry_row(self, entry: PasswordEntry) -> Gtk.ListBoxRow:
        """Crée une ligne pour une entrée de la corbeille."""
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        # Vérifier que l'ID existe
        if entry.id is None:
            logger.warning("Entrée sans ID trouvée dans la corbeille")
            return row

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_start(12)
        hbox.set_margin_end(12)
        hbox.set_margin_top(12)
        hbox.set_margin_bottom(12)

        # Info sur l'entrée
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_hexpand(True)

        title_label = Gtk.Label(label=entry.title, xalign=0)
        title_label.set_css_classes(["heading"])
        vbox.append(title_label)

        details = []
        if entry.username:
            details.append(entry.username)
        if entry.url:
            details.append(entry.url)
        if entry.category:
            details.append(f"📁 {entry.category}")

        if details:
            details_label = Gtk.Label(label=" • ".join(details), xalign=0)
            details_label.set_css_classes(["dim-label", "caption"])
            details_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            vbox.append(details_label)

        hbox.append(vbox)

        # Boutons d'action
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        entry_id = entry.id  # Capturer l'ID pour éviter les problèmes de type

        # Bouton restaurer
        restore_button = Gtk.Button(label=_("Restaurer"))
        restore_button.set_css_classes(["suggested-action"])
        restore_button.connect("clicked", lambda _, eid=entry_id: self.on_restore_clicked(eid))  # type: ignore
        button_box.append(restore_button)

        # Bouton supprimer définitivement
        delete_button = Gtk.Button(label=_("Supprimer définitivement"))
        delete_button.set_css_classes(["destructive-action"])
        delete_button.connect(
            "clicked", lambda _, eid=entry_id: self.on_delete_permanently_clicked(eid)  # type: ignore
        )
        button_box.append(delete_button)

        hbox.append(button_box)
        row.set_child(hbox)

        return row

    def on_restore_clicked(self, entry_id: int):
        """Restaure une entrée de la corbeille."""
        try:
            self.password_service.restore_entry(entry_id)
            self.load_trash_entries()
            self.on_change_callback()
            self._show_toast(_("Entrée restaurée"))
        except Exception as e:
            logger.exception("Erreur lors de la restauration")
            self._show_error(_("Erreur lors de la restauration"), str(e))

    def on_delete_permanently_clicked(self, entry_id: int):
        """Supprime définitivement une entrée."""
        from src.ui.dialogs.helpers import present_alert

        present_alert(
            self,
            _("Supprimer définitivement ?"),
            _("Cette action est irréversible. L'entrée sera supprimée définitivement."),
            [("cancel", _("Annuler")), ("delete", _("Supprimer définitivement"))],
            default="cancel",
            close="cancel",
            destructive="delete",
            on_response=lambda response: self._delete_permanently_confirmed(
                response, entry_id
            ),
        )

    def _delete_permanently_confirmed(self, response: str, entry_id: int):
        """Callback après confirmation de suppression définitive."""
        if response == "delete":
            try:
                self.password_service.delete_entry_permanently(entry_id)
                self.load_trash_entries()
                self.on_change_callback()
                self._show_toast(_("Entrée supprimée définitivement"))
            except Exception as e:
                logger.exception("Erreur lors de la suppression définitive")
                self._show_error(_("Erreur lors de la suppression"), str(e))

    def on_empty_trash_clicked(self, _button):
        """Vide complètement la corbeille."""
        from src.ui.dialogs.helpers import present_alert

        entries = self.password_service.list_trash()
        if not entries:
            self._show_toast(_("La corbeille est déjà vide"))
            return

        present_alert(
            self,
            _("Vider la corbeille ?"),
            _(
                "Toutes les entrées seront supprimées définitivement. "
                "Cette action est irréversible."
            ),
            [("cancel", _("Annuler")), ("delete", _("Vider la corbeille"))],
            default="cancel",
            close="cancel",
            destructive="delete",
            on_response=self._empty_trash_confirmed,
        )

    def _empty_trash_confirmed(self, response: str):
        """Callback après confirmation du vidage de la corbeille."""
        if response == "delete":
            try:
                count = self.password_service.empty_trash()
                self.load_trash_entries()
                self.on_change_callback()
                self._show_toast(
                    _("Corbeille vidée ({} entrée(s) supprimée(s))").format(count)
                )
            except Exception as e:
                logger.exception("Erreur lors du vidage de la corbeille")
                self._show_error(_("Erreur lors du vidage de la corbeille"), str(e))

    def _show_toast(self, message: str):
        """Affiche un toast sur la fenêtre parente."""
        if hasattr(self.parent_window, "show_toast"):
            self.parent_window.show_toast(message)

    def _show_error(self, title: str, message: str):
        """Affiche une erreur."""
        from src.ui.notifications import error as show_error

        show_error(title, message)
