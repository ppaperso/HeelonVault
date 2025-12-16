"""Fenêtre principale de l'application de gestion de mots de passe."""

from __future__ import annotations

import logging
from typing import Optional

from src.config.environment import is_dev_mode
from src.i18n import _
from src.models.password_entry import PasswordEntry
from src.services.password_service import PasswordService
from src.ui.dialogs.add_edit_dialog import AddEditDialog
from src.ui.dialogs.entry_details_dialog import EntryDetailsDialog
from src.ui.dialogs.helpers import present_alert

import gi  # type: ignore[import]

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Gdk  # type: ignore[attr-defined]  # noqa: E402

logger = logging.getLogger(__name__)


def analyze_password_strength(password: str) -> tuple[int, str, str]:
    """Retourne (score, libellé, classe CSS) pour la force d'un mot de passe."""
    if not password:
        return (0, _("Aucun"), "error")

    score = 0
    length = len(password)

    if length >= 12:
        score += 2
    elif length >= 8:
        score += 1

    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(not c.isalnum() for c in password)

    complexity = sum([has_lower, has_upper, has_digit, has_special])
    if complexity >= 3:
        score += 2
    elif complexity >= 2:
        score += 1

    if score >= 4:
        return (4, _("Très fort"), "success")
    if score >= 3:
        return (3, _("Fort"), "success")
    if score >= 2:
        return (2, _("Moyen"), "warning")
    return (1, _("Faible"), "error")


class PasswordCard(Gtk.FlowBoxChild):
    """Carte affichant une entrée de mot de passe."""

    def __init__(
        self,
        entry: PasswordEntry,
        parent_window: 'PasswordManagerWindow',
        password_age: Optional[int] = None,
        is_duplicate: bool = False,
    ):
        super().__init__()
        self.entry = entry
        self.entry_id = entry.id
        self.parent_window = parent_window
        self.password_age = password_age
        self.is_duplicate = is_duplicate

        frame = Gtk.Frame()
        frame.set_css_classes(['card'])

        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content_box.set_margin_start(16)
        content_box.set_margin_end(16)
        content_box.set_margin_top(16)
        content_box.set_margin_bottom(16)
        content_box.set_size_request(260, -1)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_box.set_hexpand(True)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_box.set_hexpand(True)

        icon_name = self._get_icon_for_entry(entry.category, entry.url)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(32)
        header_box.append(icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)

        strength_score, strength_label, strength_color = analyze_password_strength(entry.password)

        title_label = Gtk.Label(label=entry.title, xalign=0)
        title_label.set_css_classes(['title-4', strength_color])
        title_label.set_ellipsize(3)
        title_label.set_max_width_chars(24)
        title_label.set_tooltip_text(_("Mot de passe %s") % strength_label.lower())
        title_box.append(title_label)

        if entry.category:
            cat_label = Gtk.Label(label=entry.category, xalign=0)
            cat_label.set_css_classes(['caption', 'dim-label'])
            cat_label.set_ellipsize(3)
            cat_label.set_max_width_chars(24)
            title_box.append(cat_label)

        header_box.append(title_box)

        badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        if is_duplicate:
            dup_badge = Gtk.Label(label="⚠")
            dup_badge.set_css_classes(['warning'])
            dup_badge.set_tooltip_text(_("Mot de passe dupliqué"))
            badges_box.append(dup_badge)

        if password_age is not None and password_age > 90:
            renew_badge = Gtk.Label(label="🔄")
            renew_badge.set_tooltip_text(_("Mot de passe ancien (%s jours)") % password_age)
            renew_badge.set_css_classes(['error' if password_age > 180 else 'warning'])
            badges_box.append(renew_badge)

        if badges_box.get_first_child() is not None:
            header_box.append(badges_box)

        info_box.append(header_box)

        meta_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        if entry.username:
            user_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            user_icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            user_icon.set_pixel_size(16)
            user_row.append(user_icon)
            user_label = Gtk.Label(label=entry.username, xalign=0)
            user_label.set_css_classes(['body'])
            user_label.set_ellipsize(3)
            user_label.set_max_width_chars(28)
            user_row.append(user_label)
            meta_grid.append(user_row)

        if entry.url:
            url_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            globe_icon = Gtk.Image.new_from_icon_name("network-workgroup-symbolic")
            globe_icon.set_pixel_size(16)
            url_row.append(globe_icon)
            url_label = Gtk.Label(label=entry.url, xalign=0)
            url_label.set_css_classes(['caption'])
            url_label.set_ellipsize(3)
            url_label.set_max_width_chars(28)
            url_row.append(url_label)
            meta_grid.append(url_row)

        info_box.append(meta_grid)

        if entry.tags:
            tags_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            for tag in entry.tags[:2]:
                tag_label = Gtk.Label(label=f"#{tag}")
                tag_label.set_css_classes(['caption', 'accent'])
                tags_box.append(tag_label)
            if len(entry.tags) > 2:
                extra_label = Gtk.Label(label=f"+{len(entry.tags)-2}")
                extra_label.set_css_classes(['caption', 'dim-label'])
                tags_box.append(extra_label)
            info_box.append(tags_box)

        content_box.append(info_box)

        actions_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        actions_column.set_valign(Gtk.Align.START)

        if entry.username:
            actions_column.append(self._build_action_button(
                "avatar-default-symbolic",
                _("Copier le nom d'utilisateur"),
                lambda _btn: self._copy_to_clipboard(entry.username, _("Nom d'utilisateur copié"))
            ))

        actions_column.append(self._build_action_button(
            "dialog-password-symbolic",
            _("Copier le mot de passe"),
            lambda _btn: self._copy_to_clipboard(entry.password, _("Mot de passe copié"))
        ))

        if entry.url:
            actions_column.append(self._build_action_button(
                "edit-copy-symbolic",
                _("Copier l'URL"),
                lambda _btn: self._copy_to_clipboard(entry.url, _("URL copiée"))
            ))
            actions_column.append(self._build_action_button(
                "web-browser-symbolic",
                _("Ouvrir dans le navigateur"),
                lambda _btn: self._open_url(entry.url),
                extra_classes=['suggested-action']
            ))

        content_box.append(actions_column)

        frame.set_child(content_box)
        self.set_child(frame)

    def _build_action_button(self, icon_name, tooltip, callback, extra_classes=None):
        button = Gtk.Button()
        button.set_icon_name(icon_name)
        button.set_tooltip_text(tooltip)
        button.set_css_classes(['flat'])
        if extra_classes:
            for cls in extra_classes:
                button.add_css_class(cls)
        button.connect("clicked", callback)
        return button

    def _copy_to_clipboard(self, text: str, message: str) -> None:
        if self.parent_window:
            self.parent_window.copy_to_clipboard(text, message)

    def _open_url(self, url: str) -> None:
        if self.parent_window:
            self.parent_window.open_url(url)

    @staticmethod
    def _get_icon_for_entry(category: str, url: str) -> str:
        if url:
            domain = url.lower()
            if 'google' in domain:
                return 'web-browser-symbolic'
            if 'github' in domain:
                return 'software-update-available-symbolic'
            if any(site in domain for site in ('facebook', 'twitter', 'instagram')):
                return 'user-available-symbolic'
            if 'mail' in domain or 'gmail' in domain:
                return 'mail-send-symbolic'
            return 'network-server-symbolic'

        if category:
            cat_lower = category.lower()
            if 'social' in cat_lower:
                return 'user-available-symbolic'
            if 'mail' in cat_lower or 'email' in cat_lower:
                return 'mail-send-symbolic'
            if 'bank' in cat_lower or 'finance' in cat_lower:
                return 'security-high-symbolic'
            if 'work' in cat_lower or 'travail' in cat_lower:
                return 'briefcase-symbolic'
            if 'shopping' in cat_lower or 'achat' in cat_lower:
                return 'shopping-cart-symbolic'
        return 'dialog-password-symbolic'


class PasswordManagerWindow(Adw.ApplicationWindow):
    """Fenêtre principale affichant les entrées de mots de passe."""

    def __init__(self, app, password_service: PasswordService, user_info: dict):
        super().__init__(application=app, title=_("Gestionnaire de mots de passe"))
        self.password_service = password_service
        self.user_info = user_info
        self.current_category_filter = "Toutes"
        self.current_tag_filter: Optional[str] = None
        self._clipboard_clear_source_id: Optional[int] = None
        self._clipboard_token = 0

        self._init_layout()
        self.load_categories()
        self.load_tags()
        self.load_entries()
        logger.info(
            "Fenêtre principale prête pour %s (role=%s)",
            user_info['username'],
            user_info['role'],
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _init_layout(self) -> None:
        display = self.get_display()
        try:
            if display and (monitor := display.get_monitors()[0]):
                geometry = monitor.get_geometry()
                width = int(geometry.width * 0.7)
                height = int(geometry.height * 0.7)
            else:
                width, height = 1400, 900
        except Exception:
            width, height = 1400, 900
        self.set_default_size(width, height)
        self.window_width = width

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        add_button = Gtk.Button(icon_name="list-add-symbolic")
        add_button.connect("clicked", self.on_add_clicked)
        header.pack_start(add_button)

        welcome_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        user_icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        welcome_box.append(user_icon)
        welcome_label = Gtk.Label(label=_("Bonjour, %s") % self.user_info['username'])
        welcome_label.set_css_classes(['title-4'])
        welcome_box.append(welcome_label)

        if self.user_info['role'] == 'admin':
            admin_badge = Gtk.Label(label=_("Admin"))
            admin_badge.set_css_classes(['caption', 'accent'])
            welcome_box.append(admin_badge)

        if is_dev_mode():
            dev_badge = Gtk.Label(label=_("🔧 MODE DÉVELOPPEMENT"))
            dev_badge.set_css_classes(['caption', 'warning'])
            welcome_box.append(dev_badge)

        header.set_title_widget(welcome_box)

        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append(_("Importer depuis CSV"), "app.import_csv")
        menu.append(_("Changer mon mot de passe"), "app.change_own_password")
        if self.user_info['role'] == 'admin':
            menu.append(_("Gérer les utilisateurs"), "app.manage_users")
            menu.append(_("Gérer les sauvegardes"), "app.manage_backups")
        menu.append(_("Changer de compte"), "app.switch_user")
        menu.append(_("Déconnexion"), "app.logout")
        about_section = Gio.Menu()
        about_section.append(_("À propos"), "app.about")
        menu.append_section(None, about_section)
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        main_box.append(header)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)

        sidebar = self._build_sidebar()
        paned.set_start_child(sidebar)
        paned.set_resize_start_child(False)
        paned.set_position(int(self.window_width * 0.3))

        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_content.set_hexpand(True)
        main_content.set_vexpand(True)

        self.empty_state = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.empty_state.set_valign(Gtk.Align.CENTER)
        self.empty_state.set_halign(Gtk.Align.CENTER)
        empty_icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.set_css_classes(['dim-label'])
        self.empty_state.append(empty_icon)
        empty_label = Gtk.Label(label=_("Aucune entrée"))
        empty_label.set_css_classes(['title-2', 'dim-label'])
        self.empty_state.append(empty_label)
        empty_hint = Gtk.Label(label=_("Cliquez sur + pour ajouter votre première entrée"))
        empty_hint.set_css_classes(['body', 'dim-label'])
        self.empty_state.append(empty_hint)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(30)
        self.flowbox.set_min_children_per_line(1)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_margin_start(20)
        self.flowbox.set_margin_end(20)
        self.flowbox.set_margin_top(20)
        self.flowbox.set_margin_bottom(20)
        self.flowbox.set_row_spacing(16)
        self.flowbox.set_column_spacing(16)
        self.flowbox.connect("child-activated", self.on_card_activated)

        scrolled.set_child(self.flowbox)
        main_content.append(self.empty_state)
        main_content.append(scrolled)

        paned.set_end_child(main_content)
        main_box.append(paned)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(main_box)
        self.set_content(self.toast_overlay)

    def _build_sidebar(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(250, -1)
        sidebar.set_css_classes(['background'])

        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        search_box.set_margin_start(12)
        search_box.set_margin_end(12)
        search_box.set_margin_top(12)
        search_box.set_margin_bottom(6)
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text(_("Rechercher..."))
        search_entry.connect("search-changed", self.on_search_changed)
        search_box.append(search_entry)
        sidebar.append(search_box)

        sidebar.append(Gtk.Separator())

        cat_label = Gtk.Label(label=_("Catégories"))
        cat_label.set_css_classes(['title-4'])
        cat_label.set_margin_start(12)
        cat_label.set_margin_top(12)
        cat_label.set_margin_bottom(6)
        cat_label.set_xalign(0)
        sidebar.append(cat_label)

        cat_scroll = Gtk.ScrolledWindow()
        cat_scroll.set_vexpand(True)
        cat_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cat_scroll.set_min_content_height(150)
        self.category_listbox = Gtk.ListBox()
        self.category_listbox.set_css_classes(['navigation-sidebar'])
        self.category_listbox.connect("row-selected", self.on_category_selected)
        cat_scroll.set_child(self.category_listbox)
        sidebar.append(cat_scroll)

        sidebar.append(Gtk.Separator())

        tag_label = Gtk.Label(label=_("Tags"))
        tag_label.set_css_classes(['title-4'])
        tag_label.set_margin_start(12)
        tag_label.set_margin_top(8)
        tag_label.set_margin_bottom(6)
        tag_label.set_xalign(0)
        sidebar.append(tag_label)

        tag_scroll = Gtk.ScrolledWindow()
        tag_scroll.set_vexpand(True)
        tag_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        tag_scroll.set_min_content_height(100)
        tag_scroll.set_margin_bottom(12)

        self.tag_flowbox = Gtk.FlowBox()
        self.tag_flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.tag_flowbox.set_margin_start(12)
        self.tag_flowbox.set_margin_end(12)
        self.tag_flowbox.set_max_children_per_line(1)
        self.tag_flowbox.connect("child-activated", self.on_tag_selected)
        tag_scroll.set_child(self.tag_flowbox)
        sidebar.append(tag_scroll)

        return sidebar

    # ------------------------------------------------------------------
    # Chargement des données
    # ------------------------------------------------------------------
    def load_categories(self) -> None:
        self.category_listbox.remove_all()

        all_row = Gtk.ListBoxRow()
        all_label = Gtk.Label(label=_("📂 Toutes"))
        all_label.set_xalign(0)
        all_label.set_margin_start(12)
        all_label.set_margin_end(12)
        all_label.set_margin_top(6)
        all_label.set_margin_bottom(6)
        all_row.set_child(all_label)
        all_row.category_name = "Toutes"
        self.category_listbox.append(all_row)

        for category in self.password_service.list_categories():
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=f"  {category.name}")
            label.set_xalign(0)
            label.set_margin_start(12)
            label.set_margin_end(12)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            row.set_child(label)
            row.category_name = category.name
            self.category_listbox.append(row)

    def load_tags(self) -> None:
        while (child := self.tag_flowbox.get_first_child()) is not None:
            self.tag_flowbox.remove(child)

        for tag in self.password_service.list_tags():
            tag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            tag_box.set_css_classes(['card'])
            label = Gtk.Label(label=f"#{tag}")
            label.set_css_classes(['caption'])
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            tag_box.append(label)
            child = Gtk.FlowBoxChild()
            child.set_child(tag_box)
            child.tag_name = tag
            self.tag_flowbox.append(child)

    def load_entries(self) -> None:
        while (child := self.flowbox.get_first_child()) is not None:
            self.flowbox.remove(child)

        entries = self.password_service.list_entries(
            category_filter=self.current_category_filter,
            tag_filter=self.current_tag_filter,
        )
        duplicates = self.password_service.detect_duplicates()

        if not entries:
            self.empty_state.set_visible(True)
            self.flowbox.set_visible(False)
            return

        self.empty_state.set_visible(False)
        self.flowbox.set_visible(True)

        for entry in entries:
            password_age = self.password_service.get_password_age_days(entry.id or 0)
            is_duplicate = bool(entry.id and entry.id in duplicates)
            card = PasswordCard(
                entry,
                self,
                password_age=password_age,
                is_duplicate=is_duplicate,
            )
            self.flowbox.append(card)

    # ------------------------------------------------------------------
    # Interactions utilisateur
    # ------------------------------------------------------------------
    def on_category_selected(self, _listbox, row):
        if row:
            self.current_category_filter = row.category_name
            self.current_tag_filter = None
            self.tag_flowbox.unselect_all()
            self.load_entries()

    def on_tag_selected(self, _flowbox, child):
        if child and hasattr(child, 'tag_name'):
            self.current_tag_filter = child.tag_name
            self.current_category_filter = "Toutes"
            self.category_listbox.select_row(self.category_listbox.get_row_at_index(0))
            self.load_entries()

    def on_search_changed(self, search_entry: Gtk.SearchEntry):
        text = search_entry.get_text().lower()

        def filter_func(flow_child: Gtk.FlowBoxChild) -> bool:
            entry = getattr(flow_child, 'entry', None)
            if not entry or not text:
                return True
            searchable = [entry.title.lower(), entry.username.lower(), entry.category.lower()]
            searchable.extend(tag.lower() for tag in entry.tags)
            return any(text in item for item in searchable if item)

        self.flowbox.set_filter_func(filter_func if text else None)

    def on_card_activated(self, _flowbox, child):
        if child and hasattr(child, 'entry') and child.entry.id is not None:
            self.on_edit_clicked(child.entry.id)

    def on_add_clicked(self, _button):
        dialog = AddEditDialog(self, self.password_service)
        dialog.present()

    def on_edit_clicked(self, entry_id: int):
        entry = self.password_service.get_entry(entry_id)
        if not entry:
            logger.warning("Entrée %s introuvable pour édition", entry_id)
            return
        dialog = AddEditDialog(self, self.password_service, entry)
        dialog.present()

    def on_delete_clicked(self, entry_id: int):
        present_alert(
            self,
            _("Confirmer la suppression"),
            _("Êtes-vous sûr de vouloir supprimer cette entrée ?"),
            [("cancel", _("Annuler")), ("delete", _("Supprimer"))],
            default="cancel",
            close="cancel",
            destructive="delete",
            on_response=lambda response: self.delete_confirmed(response, entry_id),
        )

    def delete_confirmed(self, response: str, entry_id: int):
        if response == "delete":
            self.password_service.delete_entry(entry_id)
            self.load_entries()
            self.load_tags()

    def show_entry_details(self, entry_id: int):
        entry = self.password_service.get_entry(entry_id)
        if not entry:
            return
        EntryDetailsDialog(
            self,
            entry,
            edit_callback=self.on_edit_clicked,
            delete_callback=self.on_delete_clicked,
        ).present()

    # ------------------------------------------------------------------
    # Utilitaires (presse-papiers, notifications, navigation)
    # ------------------------------------------------------------------
    def copy_to_clipboard(self, text: str, message: str = _("Copié dans le presse-papiers")) -> None:
        clipboard = self.get_clipboard()
        if not clipboard:
            logger.warning("Clipboard non disponible pour la copie")
            return
        self._set_clipboard_text(clipboard, text)
        self.show_toast(message)
        self._schedule_clipboard_clear()

    def _set_clipboard_text(self, clipboard: Gdk.Clipboard, text: str) -> None:
        try:
            bytes_value = GLib.Bytes.new(text.encode('utf-8'))
            provider = Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", bytes_value)
            clipboard.set_content(provider)
            self._persist_clipboard(clipboard)
        except Exception as exc:
            logger.exception("Impossible d'écrire dans le presse-papiers: %s", exc)

    def _persist_clipboard(self, clipboard: Gdk.Clipboard) -> None:
        try:
            clipboard.store_async(
                GLib.PRIORITY_DEFAULT,
                None,
                self._on_clipboard_store_finished,
                None,
            )
        except AttributeError:
            pass
        except Exception as exc:
            logger.debug("Impossible de persister le presse-papiers: %s", exc)

    def _on_clipboard_store_finished(self, clipboard, result, _data):
        try:
            clipboard.store_finish(result)
        except Exception as exc:
            logger.debug("store_finish a échoué: %s", exc)

    def _schedule_clipboard_clear(self) -> None:
        self._clipboard_token += 1
        token = self._clipboard_token
        if self._clipboard_clear_source_id:
            GLib.source_remove(self._clipboard_clear_source_id)
            self._clipboard_clear_source_id = None
        self._clipboard_clear_source_id = GLib.timeout_add_seconds(
            30,
            lambda token=token: self._clear_clipboard_if_token(token),
        )

    def _clear_clipboard_if_token(self, token: int) -> bool:
        if token != self._clipboard_token:
            return False
        clipboard = self.get_clipboard()
        if clipboard:
            try:
                bytes_value = GLib.Bytes.new(b'')
                provider = Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", bytes_value)
                clipboard.set_content(provider)
                self.show_toast(_("Presse-papiers vidé pour sécurité"))
            except Exception as exc:
                logger.warning("Impossible de vider le presse-papiers: %s", exc)
        self._clipboard_clear_source_id = None
        return False

    def show_toast(self, message: str) -> None:
        from src.ui.notifications import toast as show_toast

        show_toast(self, message)

    def open_url(self, url: str) -> None:
        import subprocess

        from src.ui.notifications import error as show_error

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            logger.exception("Erreur lors de l'ouverture de l'URL %s", url)
            show_error(self, _("Impossible d'ouvrir l'URL :\n%s") % str(exc), heading=_("Erreur"))
