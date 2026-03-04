"""Fenêtre principale de l'application de gestion de mots de passe."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import gi  # type: ignore[import]

from src.i18n import _
from src.models.password_entry import PasswordEntry
from src.models.user_info import UserInfo, UserInfoUpdate
from src.services.password_service import PasswordService
from src.ui.dialogs.add_edit_dialog import AddEditDialog
from src.ui.dialogs.entry_details_dialog import EntryDetailsDialog
from src.ui.dialogs.helpers import present_alert
from src.version import __app_name__, __copyright__, __version__

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

logger = logging.getLogger(__name__)


def analyze_password_strength(password: str) -> tuple[int, str, str]:
    """Retourne (score, libellé, classe CSS) pour la force d'un mot de passe."""
    if not password:
        return (0, _("None"), "error")

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
        return (4, _("Very strong"), "success")
    if score >= 3:
        return (3, _("Strong"), "success")
    if score >= 2:
        return (2, _("Medium"), "warning")
    return (1, _("Weak"), "error")


class PasswordCard(Gtk.FlowBoxChild):
    """Carte affichant une entrée de mot de passe."""

    def __init__(
        self,
        entry: PasswordEntry,
        parent_window: PasswordManagerWindow,
        password_age: int | None = None,
        is_duplicate: bool = False,
    ):
        super().__init__()
        self.entry = entry
        self.entry_id = entry.id
        self.parent_window = parent_window
        self.password_age = password_age
        self.is_duplicate = is_duplicate

        frame = Gtk.Frame()
        frame.set_css_classes(["card", "password-card"])

        strength_score, strength_label, strength_css = analyze_password_strength(
            entry.password
        )

        # ── Container principal ──────────────────────────────────────────
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.set_size_request(220, -1)

        # ── Bande de force en haut de la card ────────────────────────────
        strength_bar = Gtk.Box()
        strength_bar.set_css_classes(["card-strength-bar", f"card-strength-{strength_css}"])
        strength_bar.set_size_request(-1, 4)
        main_box.append(strength_bar)

        # ── Contenu interne ──────────────────────────────────────────────
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_start(12)
        inner.set_margin_end(12)
        inner.set_margin_top(10)
        inner.set_margin_bottom(8)

        # ── Header : icône dans badge + titres + alertes ─────────────────
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_box.set_hexpand(True)

        # Icône dans un conteneur circulaire teinté
        icon_name = self._get_icon_for_entry(entry.category, entry.url)
        icon_container = Gtk.Box()
        icon_container.set_css_classes(["card-icon-badge", f"card-icon-badge-{strength_css}"])
        icon_container.set_valign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(18)
        icon_container.append(icon)
        header_box.append(icon_container)

        # Titre + catégorie
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_box.set_hexpand(True)

        tooltip_parts = [_("%s") % strength_label]
        if entry.username:
            tooltip_parts.append(_("User: %s") % entry.username)
        if entry.url:
            tooltip_parts.append(_("URL: %s") % entry.url)
        if entry.tags:
            tooltip_parts.append(_("Tags: %s") % ", ".join(entry.tags))

        title_label = Gtk.Label(label=entry.title, xalign=0)
        title_label.set_css_classes(["card-title"])
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.set_max_width_chars(20)
        title_label.set_tooltip_text("\n".join(tooltip_parts))
        title_box.append(title_label)

        if entry.category:
            cat_label = Gtk.Label(label=entry.category, xalign=0)
            cat_label.set_css_classes(["card-category"])
            cat_label.set_ellipsize(Pango.EllipsizeMode.END)
            cat_label.set_max_width_chars(22)
            title_box.append(cat_label)

        header_box.append(title_box)

        # Alertes (duplicata / expiration)
        validity_days = entry.password_validity_days
        is_expired = (
            validity_days is not None
            and password_age is not None
            and password_age > validity_days
        )
        if is_duplicate or is_expired:
            alerts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            alerts_box.set_valign(Gtk.Align.START)
            if is_duplicate:
                dup = Gtk.Label(label="⚠")
                dup.set_css_classes(["card-alert-badge", "card-alert-warning"])
                dup.set_tooltip_text(_("Duplicate password"))
                alerts_box.append(dup)
            if is_expired and password_age is not None and validity_days is not None:
                overdue_days = password_age - validity_days
                age_cls = "card-alert-error" if overdue_days > 30 else "card-alert-warning"
                age_badge = Gtk.Label(label=f"{password_age}j")
                age_badge.set_css_classes(["card-alert-badge", age_cls])
                age_badge.set_tooltip_text(
                    _("Expired for %s days – needs renewal") % overdue_days
                )
                alerts_box.append(age_badge)
            header_box.append(alerts_box)

        inner.append(header_box)

        # ── Ligne identifiant (username ou domaine URL) ───────────────────
        hint_text = None
        if entry.username:
            hint_text = entry.username
        elif entry.url:
            # Extraire juste le domaine
            raw = entry.url.split("//")[-1].split("/")[0].replace("www.", "")
            hint_text = raw

        if hint_text:
            hint_label = Gtk.Label(label=hint_text, xalign=0)
            hint_label.set_css_classes(["card-hint"])
            hint_label.set_ellipsize(Pango.EllipsizeMode.END)
            hint_label.set_max_width_chars(26)
            inner.append(hint_label)

        # ── Separateur fin ────────────────────────────────────────────────
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_css_classes(["card-sep"])
        inner.append(sep)

        # ── Barre d'actions + tag pills ───────────────────────────────────
        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bottom_row.set_hexpand(True)

        # Groupe copie (gauche)
        copy_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        copy_box.set_valign(Gtk.Align.CENTER)
        copy_box.set_hexpand(True)

        if entry.username:
            copy_box.append(
                self._build_compact_action_button(
                    "avatar-default-symbolic",
                    _("Copy username"),
                    lambda _btn: self._copy_to_clipboard(
                        entry.username, _("Username copied")
                    ),
                )
            )

        copy_box.append(
            self._build_compact_action_button(
                "dialog-password-symbolic",
                _("Copy password"),
                lambda _btn: self._copy_to_clipboard(
                    entry.password, _("Password copied")
                ),
            )
        )

        if entry.url:
            copy_box.append(
                self._build_compact_action_button(
                    "web-browser-symbolic",
                    _("Open in browser"),
                    lambda _btn: self._open_url(entry.url),
                )
            )

        bottom_row.append(copy_box)

        # Tag pills (max 2) au centre
        if entry.tags:
            tags_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            tags_box.set_valign(Gtk.Align.CENTER)
            tags_box.set_margin_start(4)
            tags_box.set_margin_end(4)
            for tag in entry.tags[:2]:
                pill = Gtk.Label(label=f"# {tag}")
                pill.set_css_classes(["card-tag-pill"])
                tags_box.append(pill)
            if len(entry.tags) > 2:
                more = Gtk.Label(label=f"+{len(entry.tags) - 2}")
                more.set_css_classes(["card-tag-more"])
                tags_box.append(more)
            bottom_row.append(tags_box)

        # Bouton corbeille (droite, isolé)
        delete_btn = self._build_compact_action_button(
            "user-trash-symbolic",
            _("Move to trash"),
            lambda _btn: self._on_delete_clicked(),
            is_destructive=True,
        )
        delete_btn.set_css_classes(["flat", "circular", "card-delete-btn"])
        delete_btn.set_valign(Gtk.Align.CENTER)
        bottom_row.append(delete_btn)

        inner.append(bottom_row)
        main_box.append(inner)
        frame.set_child(main_box)
        self.set_child(frame)

    def _build_action_button(self, icon_name, tooltip, callback, extra_classes=None):
        button = Gtk.Button()
        button.set_icon_name(icon_name)
        button.set_tooltip_text(tooltip)
        button.set_css_classes(["flat"])
        if extra_classes:
            for cls in extra_classes:
                button.add_css_class(cls)
        button.connect("clicked", callback)
        return button

    def _build_compact_action_button(
        self, icon_name, tooltip, callback, is_destructive=False
    ):
        """Construit un bouton d'action compact pour l'affichage horizontal."""
        button = Gtk.Button()
        button.set_icon_name(icon_name)
        button.set_tooltip_text(tooltip)
        button.set_css_classes(["flat", "circular", "card-action-btn"])
        if is_destructive:
            button.add_css_class("destructive-action")
        button.connect("clicked", callback)
        return button

    def _copy_to_clipboard(self, text: str, message: str) -> None:
        if self.parent_window:
            self.parent_window.copy_to_clipboard(text, message)

    def _open_url(self, url: str) -> None:
        if self.parent_window:
            self.parent_window.open_url(url)

    def _on_delete_clicked(self) -> None:
        """Demande la suppression de cette entrée (mise à la corbeille)."""
        if self.parent_window and self.entry_id is not None:
            self.parent_window.on_delete_clicked(self.entry_id)

    @staticmethod
    def _get_icon_for_entry(category: str, url: str) -> str:
        if url:
            domain = url.lower()
            if "google" in domain:
                return "web-browser-symbolic"
            if "github" in domain:
                return "software-update-available-symbolic"
            if any(site in domain for site in ("facebook", "twitter", "instagram")):
                return "user-available-symbolic"
            if "mail" in domain or "gmail" in domain:
                return "mail-send-symbolic"
            return "network-server-symbolic"

        if category:
            cat_lower = category.lower()
            if "social" in cat_lower:
                return "user-available-symbolic"
            if "mail" in cat_lower or "email" in cat_lower:
                return "mail-send-symbolic"
            if "bank" in cat_lower or "finance" in cat_lower:
                return "security-high-symbolic"
            if "work" in cat_lower or "travail" in cat_lower:
                return "briefcase-symbolic"
            if "shopping" in cat_lower or "achat" in cat_lower:
                return "shopping-cart-symbolic"
        return "dialog-password-symbolic"


class PasswordManagerWindow(Adw.ApplicationWindow):
    """Fenêtre principale affichant les entrées de mots de passe."""

    def __init__(
        self,
        app: Adw.Application,
        password_service: PasswordService,
        user_info: UserInfo,
    ):
        super().__init__(application=app, title=__app_name__)
        self.password_service = password_service
        self.user_info = user_info
        self.current_category_filter = "All"
        self.current_tag_filter: str | None = None
        self._clipboard_clear_source_id: int | None = None
        self._clipboard_token = 0
        self.profile_last_login_value: Gtk.Label | None = None
        self.metric_logins_today_value: Gtk.Label | None = None
        self.metric_entries_value: Gtk.Label | None = None
        self.metric_categories_value: Gtk.Label | None = None
        self.metric_tags_value: Gtk.Label | None = None
        self.metric_weak_value: Gtk.Label | None = None
        self.metric_weak_badge: Gtk.Box | None = None
        self.main_stats_label: Gtk.Label | None = None
        self.profile_identity_avatar: Adw.Avatar | None = None
        self.profile_identity_name_label: Gtk.Label | None = None
        self._category_by_child: dict[Gtk.FlowBoxChild, str] = {}
        self._tag_by_child: dict[Gtk.FlowBoxChild, str] = {}

        self._init_layout()
        self.load_categories()
        self.load_tags()
        self.load_entries()
        self._refresh_sidebar_metrics()
        logger.info(
            "Main window ready for %s (role=%s)",
            user_info["username"],
            user_info.get("role"),
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _init_layout(self) -> None:
        display = self.get_display()
        try:
            monitor = display.get_monitors().get_item(0) if display else None
            if isinstance(monitor, Gdk.Monitor):
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

        date_label = Gtk.Label(label=self._get_long_french_date(), xalign=0.5)
        date_label.set_css_classes(["title-4", "header-date-label"])
        date_label.set_valign(Gtk.Align.CENTER)
        header.set_title_widget(date_label)

        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append(_("Import from CSV"), "app.import_csv")
        menu.append(_("Export to CSV"), "app.export_csv")
        menu.append(_("Trash"), "app.open_trash")
        menu.append(_("Manage my account"), "app.manage_account")
        if self.user_info.get("role") == "admin":
            menu.append(_("Manage users"), "app.manage_users")
            menu.append(_("Manage backups"), "app.manage_backups")
        menu.append(_("Switch account"), "app.switch_user")
        menu.append(_("Logout"), "app.logout")
        about_section = Gio.Menu()
        about_section.append(_("About"), "app.about")
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
        paned.set_position(int(self.window_width * 0.32))

        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_content.set_hexpand(True)
        main_content.set_vexpand(True)

        content_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content_header.set_margin_start(20)
        content_header.set_margin_end(20)
        content_header.set_margin_top(16)
        content_header.set_margin_bottom(0)

        cards_title = Gtk.Label(label=_("Your secure access"), xalign=0)
        cards_title.set_css_classes(["title-3"])
        content_header.append(cards_title)

        main_stats_label = Gtk.Label(label="", xalign=0)
        main_stats_label.set_css_classes(["caption", "dim-label"])
        content_header.append(main_stats_label)
        self.main_stats_label = main_stats_label

        self.empty_state = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.empty_state.set_valign(Gtk.Align.CENTER)
        self.empty_state.set_halign(Gtk.Align.CENTER)
        empty_icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.set_css_classes(["dim-label"])
        self.empty_state.append(empty_icon)
        empty_label = Gtk.Label(label=_("No entries"))
        empty_label.set_css_classes(["title-2", "dim-label"])
        self.empty_state.append(empty_label)
        empty_hint = Gtk.Label(
            label=_("Click + to add your first entry")
        )
        empty_hint.set_css_classes(["body", "dim-label"])
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
        main_content.append(content_header)
        main_content.append(self.empty_state)
        main_content.append(scrolled)
        main_content.append(self._build_dashboard_footer())

        paned.set_end_child(main_content)
        main_box.append(paned)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(main_box)
        self.set_content(self.toast_overlay)

    def _build_sidebar(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(320, -1)
        sidebar.set_css_classes(["background"])

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_vexpand(True)

        sidebar_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar_content.set_margin_start(12)
        sidebar_content.set_margin_end(12)
        sidebar_content.set_margin_top(12)
        sidebar_content.set_margin_bottom(12)

        branding_header = self._build_sidebar_branding_header()
        sidebar_content.append(branding_header)

        profile_card = self._build_profile_activity_card()
        sidebar_content.append(profile_card)

        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        search_box.set_css_classes(["card", "sidebar-card"])
        search_box.set_spacing(8)
        search_box.set_margin_start(4)
        search_box.set_margin_end(4)
        search_box.set_margin_top(0)
        search_box.set_margin_bottom(0)

        search_title = Gtk.Label(label=_("Search"), xalign=0)
        search_title.set_css_classes(["heading"])
        search_title.set_margin_start(12)
        search_title.set_margin_end(12)
        search_title.set_margin_top(12)
        search_box.append(search_title)

        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text(_("Search..."))
        search_entry.connect("search-changed", self.on_search_changed)
        search_entry.set_margin_start(12)
        search_entry.set_margin_end(12)
        search_box.append(search_entry)

        filters_box = Gtk.FlowBox()
        filters_box.set_selection_mode(Gtk.SelectionMode.NONE)
        filters_box.set_max_children_per_line(3)
        filters_box.set_min_children_per_line(1)
        filters_box.set_row_spacing(4)
        filters_box.set_column_spacing(4)
        filters_box.set_margin_top(6)
        filters_box.set_margin_start(12)
        filters_box.set_margin_end(12)
        filters_box.set_margin_bottom(12)

        self.search_filter_title = Gtk.CheckButton(label=_("Title"))
        self.search_filter_title.set_active(True)
        self.search_filter_title.connect(
            "toggled", lambda _: self.on_search_changed(search_entry)
        )
        filters_box.append(self.search_filter_title)

        self.search_filter_category = Gtk.CheckButton(label=_("Cat."))
        self.search_filter_category.set_active(True)
        self.search_filter_category.set_tooltip_text(_("Category"))
        self.search_filter_category.connect(
            "toggled", lambda _: self.on_search_changed(search_entry)
        )
        filters_box.append(self.search_filter_category)

        self.search_filter_username = Gtk.CheckButton(label=_("User"))
        self.search_filter_username.set_active(True)
        self.search_filter_username.set_tooltip_text(_("Username"))
        self.search_filter_username.connect(
            "toggled", lambda _: self.on_search_changed(search_entry)
        )
        filters_box.append(self.search_filter_username)

        self.search_filter_url = Gtk.CheckButton(label=_("URL"))
        self.search_filter_url.set_active(True)
        self.search_filter_url.connect(
            "toggled", lambda _: self.on_search_changed(search_entry)
        )
        filters_box.append(self.search_filter_url)

        self.search_filter_tags = Gtk.CheckButton(label=_("Tags"))
        self.search_filter_tags.set_active(True)
        self.search_filter_tags.connect(
            "toggled", lambda _: self.on_search_changed(search_entry)
        )
        filters_box.append(self.search_filter_tags)

        search_box.append(filters_box)
        sidebar_content.append(search_box)

        self.categories_expander = Adw.ExpanderRow()
        self.categories_expander.set_title(_("Categories"))
        self.categories_expander.set_expanded(True)
        self.categories_expander.set_css_classes(["card", "sidebar-expander"])

        cat_inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cat_inner_box.set_margin_start(12)
        cat_inner_box.set_margin_end(12)
        cat_inner_box.set_margin_top(6)
        cat_inner_box.set_margin_bottom(8)

        self.category_search_entry = Gtk.SearchEntry()
        self.category_search_entry.set_placeholder_text(_("Filter categories..."))
        self.category_search_entry.connect(
            "search-changed", self.on_category_search_changed
        )
        cat_inner_box.append(self.category_search_entry)

        self.category_flowbox = Gtk.FlowBox()
        self.category_flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.category_flowbox.set_margin_start(6)
        self.category_flowbox.set_margin_end(6)
        self.category_flowbox.set_row_spacing(4)
        self.category_flowbox.set_column_spacing(4)
        self.category_flowbox.set_max_children_per_line(20)
        self.category_flowbox.connect("child-activated", self.on_category_selected)
        cat_inner_box.append(self.category_flowbox)

        self.categories_expander.add_row(cat_inner_box)
        sidebar_content.append(self.categories_expander)

        self.tags_expander = Adw.ExpanderRow()
        self.tags_expander.set_title(_("Tags"))
        self.tags_expander.set_expanded(False)
        self.tags_expander.set_css_classes(["card", "sidebar-expander"])

        tags_inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tags_inner_box.set_margin_start(12)
        tags_inner_box.set_margin_end(12)
        tags_inner_box.set_margin_top(6)
        tags_inner_box.set_margin_bottom(8)

        self.tag_search_entry = Gtk.SearchEntry()
        self.tag_search_entry.set_placeholder_text(_("Filter tags..."))
        self.tag_search_entry.connect("search-changed", self.on_tag_search_changed)
        tags_inner_box.append(self.tag_search_entry)

        tag_scroll = Gtk.ScrolledWindow()
        tag_scroll.set_vexpand(True)
        tag_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        tag_scroll.set_min_content_height(220)

        self.tag_flowbox = Gtk.FlowBox()
        self.tag_flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.tag_flowbox.set_margin_start(6)
        self.tag_flowbox.set_margin_end(6)
        self.tag_flowbox.set_row_spacing(4)
        self.tag_flowbox.set_column_spacing(4)
        self.tag_flowbox.set_max_children_per_line(20)  # Plusieurs tags par ligne
        self.tag_flowbox.connect("child-activated", self.on_tag_selected)
        tag_scroll.set_child(self.tag_flowbox)

        tags_inner_box.append(tag_scroll)
        self.tags_expander.add_row(tags_inner_box)
        sidebar_content.append(self.tags_expander)

        sidebar_scroll.set_child(sidebar_content)
        sidebar.append(sidebar_scroll)

        return sidebar

    def _build_sidebar_branding_header(self) -> Gtk.Widget:
        """Construit le branding premium (logo + nom produit) en haut de la sidebar."""
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.set_css_classes(["card", "sidebar-branding"])
        card.set_margin_start(4)
        card.set_margin_end(4)

        ui_dir = Path(__file__).resolve().parents[1]
        logo_path = ui_dir / "assets" / "images" / "Logo_Heelonys_transparent.png"

        # Fallback rétrocompatibilité: ancien emplacement éventuel
        if not logo_path.exists():
            root_dir = Path(__file__).resolve().parents[3]
            logo_path = root_dir / "assets" / "images" / "Logo_Heelonys_transparent.png"

        if logo_path.exists():
            logo = Gtk.Picture.new_for_filename(str(logo_path))
            logo.set_content_fit(Gtk.ContentFit.CONTAIN)
            logo.set_size_request(24, 24)
            logo.set_can_shrink(True)
            logo.set_css_classes(["sidebar-brand-logo"])
        else:
            logo = Gtk.Image.new_from_icon_name("security-high-symbolic")
            logo.set_pixel_size(20)
            logo.set_css_classes(["sidebar-brand-logo"])

        card.append(logo)

        title = Gtk.Label(label=__app_name__, xalign=0)
        title.set_hexpand(True)
        title.set_valign(Gtk.Align.CENTER)
        title.set_css_classes(["sidebar-brand-title"])
        card.append(title)

        return card

    def _build_dashboard_footer(self) -> Gtk.Widget:
        """Construit le footer branding en bas du dashboard."""
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer.set_css_classes(["dashboard-footer"])
        footer.set_margin_start(20)
        footer.set_margin_end(20)
        footer.set_margin_top(0)
        footer.set_margin_bottom(12)

        today = datetime.now().strftime("%d/%m/%Y")
        footer_text = f"Heelonys · {__copyright__} · v{__version__} · {today}"

        label = Gtk.Label(label=footer_text, xalign=0)
        label.set_hexpand(True)
        label.set_css_classes(["dashboard-footer-label"])
        footer.append(label)

        return footer

    def _build_profile_activity_card(self) -> Gtk.Widget:
        """
        Status Card horizontale compacte :
        [Avatar | nom/rôle] │ [🔑 N / 📁 N / 🏷 N] │ [🕐 dernière connexion / 🛡 N à renforcer]
        """
        username = self.user_info.get("username", "?")
        role     = self.user_info.get("role", "user")

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        card.set_css_classes(["card", "status-card"])
        card.set_margin_start(4)
        card.set_margin_end(4)

        # ── IDENTITÉ (gauche) ─────────────────────────────────────────────
        identity_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        identity_box.set_margin_start(12)
        identity_box.set_margin_end(12)
        identity_box.set_margin_top(10)
        identity_box.set_margin_bottom(10)
        identity_box.set_valign(Gtk.Align.CENTER)

        profile_identity_avatar = Adw.Avatar(size=36, text=username, show_initials=True)
        self._apply_avatar_texture(
            profile_identity_avatar,
            self.user_info.get("avatar_path"),
        )
        profile_identity_avatar.set_valign(Gtk.Align.CENTER)
        identity_box.append(profile_identity_avatar)
        self.profile_identity_avatar = profile_identity_avatar

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        texts.set_valign(Gtk.Align.CENTER)

        profile_identity_name_label = Gtk.Label(label=username, xalign=0)
        profile_identity_name_label.set_css_classes(["status-username"])
        texts.append(profile_identity_name_label)
        self.profile_identity_name_label = profile_identity_name_label

        role_pill = Gtk.Label(label=role.upper(), xalign=0)
        role_pill.set_css_classes(["status-role-pill", f"status-role-{role}"])
        texts.append(role_pill)

        identity_box.append(texts)
        card.append(identity_box)

        # ── SÉPARATEUR ────────────────────────────────────────────────────
        card.append(self._build_vsep())

        # ── STATISTIQUES (centre) ─────────────────────────────────────────
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        stats_box.set_hexpand(True)
        stats_box.set_halign(Gtk.Align.CENTER)
        stats_box.set_valign(Gtk.Align.CENTER)
        stats_box.set_margin_start(8)
        stats_box.set_margin_end(8)

        chip_pw, self.metric_entries_value = self._build_stat_chip(
            "dialog-password-symbolic", "0", _("passwords")
        )
        chip_cat, self.metric_categories_value = self._build_stat_chip(
            "folder-symbolic", "0", _("categories")
        )
        chip_tags, self.metric_tags_value = self._build_stat_chip(
            "tag-symbolic", "0", _("tags")
        )

        stats_box.append(chip_pw)
        stats_box.append(self._build_inner_sep())
        stats_box.append(chip_cat)
        stats_box.append(self._build_inner_sep())
        stats_box.append(chip_tags)
        card.append(stats_box)

        # ── SÉPARATEUR ────────────────────────────────────────────────────
        card.append(self._build_vsep())

        # ── ALERTES + DERNIÈRE CONNEXION (droite) ─────────────────────────
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        right_box.set_margin_start(12)
        right_box.set_margin_end(12)
        right_box.set_margin_top(8)
        right_box.set_margin_bottom(8)
        right_box.set_valign(Gtk.Align.CENTER)

        # Dernière connexion
        login_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        login_row.set_valign(Gtk.Align.CENTER)
        _login_tt = _("<b>🔒 Last recorded login</b>\n"
                  "Verify this date matches\n"
                  "your last personal session.\n"
                  "\n"
                  "<i>If not, change your master password immediately\n"
                  "and alert your administrator.</i>")
        login_row.set_has_tooltip(True)
        login_row.set_tooltip_markup(_login_tt)
        login_icon = Gtk.Image.new_from_icon_name("alarm-symbolic")
        login_icon.set_pixel_size(16)
        login_icon.set_css_classes(["status-meta-icon"])
        login_icon.set_tooltip_markup(_login_tt)
        login_row.append(login_icon)
        profile_last_login_value = Gtk.Label(label="\u2014", xalign=0)
        profile_last_login_value.set_css_classes(["status-last-login"])
        profile_last_login_value.set_tooltip_markup(_login_tt)
        login_row.append(profile_last_login_value)
        self.profile_last_login_value = profile_last_login_value
        right_box.append(login_row)

        # Badge « À renforcer »
        metric_weak_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        metric_weak_badge.set_css_classes(["status-weak-badge", "status-weak-ok"])
        metric_weak_badge.set_valign(Gtk.Align.CENTER)
        _weak_tt = _("<b>🛡 Passwords to strengthen</b>\n"
                 "These entries have a <i>weak</i> or <i>medium</i> strength score.\n"
                 "\n"
                 "A robust password should contain:\n"
                 "  • At least <b>12 characters</b>\n"
                 "  • Uppercase, lowercase, digits <b>and</b> symbols\n"
                 "\n"
                 "<i>Click the related card to edit the entry.</i>")
        metric_weak_badge.set_has_tooltip(True)
        metric_weak_badge.set_tooltip_markup(_weak_tt)
        weak_icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        weak_icon.set_pixel_size(16)
        weak_icon.set_tooltip_markup(_weak_tt)
        metric_weak_badge.append(weak_icon)
        metric_weak_value = Gtk.Label(label=_("0 to strengthen"), xalign=0)
        metric_weak_value.set_css_classes(["status-weak-label"])
        metric_weak_value.set_tooltip_markup(_weak_tt)
        metric_weak_badge.append(metric_weak_value)
        right_box.append(metric_weak_badge)
        self.metric_weak_badge = metric_weak_badge
        self.metric_weak_value = metric_weak_value

        card.append(right_box)

        # Garder la ref logins_today à None (non affiché dans ce design)
        self.metric_logins_today_value = None

        return card

    # ── Helpers minimalistes pour la Status Card ──────────────────────────
    def _build_vsep(self) -> Gtk.Separator:
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_css_classes(["status-vsep"])
        sep.set_margin_top(10)
        sep.set_margin_bottom(10)
        return sep

    def _build_inner_sep(self) -> Gtk.Separator:
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_css_classes(["status-vsep"])
        sep.set_margin_top(14)
        sep.set_margin_bottom(14)
        return sep

    def _build_stat_chip(
        self, icon_name: str, initial_value: str, sub_label: str
    ) -> tuple[Gtk.Box, Gtk.Label]:
        chip = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        chip.set_css_classes(["status-stat-chip"])
        chip.set_valign(Gtk.Align.CENTER)
        chip.set_margin_start(8)
        chip.set_margin_end(8)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        top.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(15)
        icon.set_css_classes(["status-stat-icon"])
        top.append(icon)
        value_lbl = Gtk.Label(label=initial_value)
        value_lbl.set_css_classes(["status-stat-value"])
        top.append(value_lbl)
        chip.append(top)

        sub = Gtk.Label(label=sub_label)
        sub.set_css_classes(["status-stat-sub"])
        chip.append(sub)

        return chip, value_lbl

    # Conserver pour compatibilité (non utilisé mais référencé nulle part désormais)
    def _create_metric_tile(self, title: str, initial_value: str) -> tuple[Gtk.Box, Gtk.Label]:
        return self._build_stat_chip("dialog-password-symbolic", initial_value, title)

    def _format_login_timestamp(self, value: str | None) -> str:
        if not value:
            return _("First login")
        try:
            parsed = datetime.fromisoformat(str(value).replace(" ", "T", 1))
            return parsed.strftime("%d/%m/%Y • %H:%M")
        except ValueError:
            return str(value)

    def _get_long_french_date(self) -> str:
        """Retourne la date du jour en format long FR (ex: Mardi 3 mars 2026)."""
        days = [
            "Lundi",
            "Mardi",
            "Mercredi",
            "Jeudi",
            "Vendredi",
            "Samedi",
            "Dimanche",
        ]
        months = [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ]
        now = datetime.now()
        return f"{days[now.weekday()]} {now.day} {months[now.month - 1]} {now.year}"

    def _apply_avatar_texture(self, avatar: Adw.Avatar, avatar_path: str | None) -> None:
        """Applique une image d'avatar personnalisée si disponible."""
        if not avatar_path:
            avatar.set_custom_image(None)
            return

        try:
            texture = Gdk.Texture.new_from_filename(str(avatar_path))
            avatar.set_custom_image(texture)
        except Exception:
            avatar.set_custom_image(None)

    def refresh_account_profile(self, user_info: UserInfoUpdate) -> None:
        """Rafraîchit les éléments d'UI qui affichent le profil connecté."""
        self.user_info = user_info
        username = self.user_info.get("username", "?")
        avatar_path = self.user_info.get("avatar_path")

        if self.profile_identity_name_label:
            self.profile_identity_name_label.set_label(username)

        if self.profile_identity_avatar:
            self.profile_identity_avatar.set_text(username)
            self._apply_avatar_texture(self.profile_identity_avatar, avatar_path)

    def _refresh_sidebar_metrics(self) -> None:
        entries = self.password_service.list_entries()
        categories = self.password_service.list_categories()
        tags = self.password_service.list_tags()

        weak_passwords = sum(
            1 for entry in entries if analyze_password_strength(entry.password)[0] <= 2
        )

        if self.profile_last_login_value:
            self.profile_last_login_value.set_label(
                self._format_login_timestamp(
                    self.user_info.get("last_login_previous") or self.user_info.get("last_login")
                )
            )
        if self.metric_logins_today_value:
            self.metric_logins_today_value.set_label(
                str(int(self.user_info.get("login_count_today", 1)))
            )
        if self.metric_entries_value:
            self.metric_entries_value.set_label(str(len(entries)))
        if self.metric_categories_value:
            self.metric_categories_value.set_label(str(len(categories)))
        if self.metric_tags_value:
            self.metric_tags_value.set_label(str(len(tags)))
        if self.metric_weak_value:
            weak_text = (
                _("0 to strengthen")
                if weak_passwords == 0
                else _("%s to strengthen") % weak_passwords
            )
            self.metric_weak_value.set_label(weak_text)
            if self.metric_weak_badge:
                if weak_passwords > 0:
                    self.metric_weak_badge.set_css_classes(
                        ["status-weak-badge", "status-weak-warn"]
                    )
                    self.metric_weak_value.set_css_classes(
                        ["status-weak-label", "status-weak-label-warn"]
                    )
                else:
                    self.metric_weak_badge.set_css_classes(
                        ["status-weak-badge", "status-weak-ok"]
                    )
                    self.metric_weak_value.set_css_classes(["status-weak-label"])

    # ------------------------------------------------------------------
    # Chargement des données
    # ------------------------------------------------------------------
    def load_categories(self) -> None:
        while (child := self.category_flowbox.get_first_child()) is not None:
            self.category_flowbox.remove(child)
        self._category_by_child.clear()

        # Ajouter l'option "All"
        all_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        all_box.set_css_classes(["card"])
        all_label = Gtk.Label(label=_("📂 All"))
        all_label.set_css_classes(["caption"])
        all_label.set_margin_start(8)
        all_label.set_margin_end(8)
        all_label.set_margin_top(4)
        all_label.set_margin_bottom(4)
        all_box.append(all_label)
        all_child = Gtk.FlowBoxChild()
        all_child.set_child(all_box)
        self.category_flowbox.append(all_child)
        self._category_by_child[all_child] = "All"

        # Ajouter les catégories
        categories = self.password_service.list_categories()
        for category in categories:
            cat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            cat_box.set_css_classes(["card"])
            label = Gtk.Label(label=f"📁 {category.name}")
            label.set_css_classes(["caption"])
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            cat_box.append(label)
            child = Gtk.FlowBoxChild()
            child.set_child(cat_box)
            self.category_flowbox.append(child)
            self._category_by_child[child] = category.name

        # Mettre à jour le compteur dans le titre
        self.categories_expander.set_subtitle(f"{len(categories)} category(ies)")

    def load_tags(self) -> None:
        while (child := self.tag_flowbox.get_first_child()) is not None:
            self.tag_flowbox.remove(child)
        self._tag_by_child.clear()

        tags = self.password_service.list_tags()
        for tag in tags:
            tag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            tag_box.set_css_classes(["card"])
            label = Gtk.Label(label=f"#{tag}")
            label.set_css_classes(["caption"])
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            tag_box.append(label)
            child = Gtk.FlowBoxChild()
            child.set_child(tag_box)
            self.tag_flowbox.append(child)
            self._tag_by_child[child] = tag

        # Mettre à jour le compteur dans le titre
        self.tags_expander.set_subtitle(f"{len(tags)} tag(s)")

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
            if self.main_stats_label:
                if self.current_category_filter != "All" or self.current_tag_filter:
                    self.main_stats_label.set_label(_("No result for active filters"))
                else:
                    self.main_stats_label.set_label(_("Your vault is currently empty"))
            self._refresh_sidebar_metrics()
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

        if self.main_stats_label:
            if self.current_category_filter != "All" or self.current_tag_filter:
                self.main_stats_label.set_label(
                    _("%(shown)s displayed result(s) • %(total)s total entries")
                    % {
                        "shown": len(entries),
                        "total": len(self.password_service.list_entries()),
                    }
                )
            else:
                self.main_stats_label.set_label(
                    _("%(count)s entries in your vault") % {"count": len(entries)}
                )

        self._refresh_sidebar_metrics()

    # ------------------------------------------------------------------
    # Interactions utilisateur
    # ------------------------------------------------------------------
    def on_category_search_changed(self, search_entry: Gtk.SearchEntry):
        """Filtre les catégories affichées dans la sidebar"""
        search_text = search_entry.get_text().lower()

        for child, category_name in self._category_by_child.items():
            child.set_visible(search_text in category_name.lower())

    def on_category_selected(self, _flowbox, child):
        category_name = self._category_by_child.get(child)
        if category_name:
            self.current_category_filter = category_name
            self.current_tag_filter = None
            self.tag_flowbox.unselect_all()
            self.load_entries()

    def on_tag_search_changed(self, search_entry: Gtk.SearchEntry):
        """Filtre les tags affichés dans la sidebar"""
        search_text = search_entry.get_text().lower()

        for child, tag_name in self._tag_by_child.items():
            child.set_visible(search_text in tag_name.lower())

    def on_tag_selected(self, _flowbox, child):
        tag_name = self._tag_by_child.get(child)
        if tag_name:
            self.current_tag_filter = tag_name
            self.current_category_filter = "All"
            # S\u00e9lectionner "All" (premier enfant) dans les cat\u00e9gories
            first_child = self.category_flowbox.get_child_at_index(0)
            if first_child:
                self.category_flowbox.select_child(first_child)
            self.load_entries()

    def on_search_changed(self, search_entry: Gtk.SearchEntry):
        text = search_entry.get_text().lower()

        def filter_func(flow_child: Gtk.FlowBoxChild) -> bool:
            entry = getattr(flow_child, "entry", None)
            if not entry or not text:
                return True

            searchable = []

            # Ajouter les champs selon les filtres actifs
            if self.search_filter_title.get_active():
                searchable.append(entry.title.lower())

            if self.search_filter_category.get_active():
                searchable.append(entry.category.lower())

            if self.search_filter_username.get_active():
                searchable.append(entry.username.lower())

            if self.search_filter_url.get_active():
                searchable.append(entry.url.lower())

            if self.search_filter_tags.get_active():
                searchable.extend(tag.lower() for tag in entry.tags)

            return any(text in item for item in searchable if item)

        self.flowbox.set_filter_func(filter_func if text else None)

    def on_card_activated(self, _flowbox, child):
        if child and hasattr(child, "entry") and child.entry.id is not None:
            self.on_edit_clicked(child.entry.id)

    def on_add_clicked(self, _button):
        dialog = AddEditDialog(self, self.password_service)
        dialog.present()

    def on_edit_clicked(self, entry_id: int):
        entry = self.password_service.get_entry(entry_id)
        if not entry:
            logger.warning("Entry %s not found for editing", entry_id)
            return
        dialog = AddEditDialog(self, self.password_service, entry)
        dialog.present()

    def on_delete_clicked(self, entry_id: int):
        present_alert(
            self,
            _("Move to trash?"),
            _(
                "This entry will be moved to trash. You can restore it "
                "from the Trash menu."
            ),
            [("cancel", _("Cancel")), ("delete", _("Move to trash"))],
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
            self.show_toast(_("Entry moved to trash"))

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
    def copy_to_clipboard(
        self, text: str, message: str = _("Copied to clipboard")
    ) -> None:
        clipboard = self.get_clipboard()
        if not clipboard:
            logger.warning("Clipboard unavailable for copy operation")
            return
        self._set_clipboard_text(clipboard, text)
        self.show_toast(message)
        self._schedule_clipboard_clear()

    def _set_clipboard_text(self, clipboard: Gdk.Clipboard, text: str) -> None:
        try:
            bytes_value = GLib.Bytes.new(text.encode("utf-8"))
            provider = Gdk.ContentProvider.new_for_bytes(
                "text/plain;charset=utf-8", bytes_value
            )
            clipboard.set_content(provider)
            self._persist_clipboard(clipboard)
        except Exception as exc:
            logger.exception("Unable to write to clipboard: %s", exc)

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
            logger.debug("Unable to persist clipboard: %s", exc)

    def _on_clipboard_store_finished(self, clipboard, result, _data):
        try:
            clipboard.store_finish(result)
        except Exception as exc:
            logger.debug("store_finish failed: %s", exc)

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
                bytes_value = GLib.Bytes.new(b"")
                provider = Gdk.ContentProvider.new_for_bytes(
                    "text/plain;charset=utf-8", bytes_value
                )
                clipboard.set_content(provider)
                self.show_toast(_("Clipboard cleared for security"))
            except Exception as exc:
                logger.warning("Unable to clear clipboard: %s", exc)
        self._clipboard_clear_source_id = None
        return False

    def show_toast(self, message: str) -> None:
        from src.ui.notifications import toast as show_toast

        show_toast(self, message)

    def open_url(self, url: str) -> None:
        import subprocess

        from src.ui.notifications import error as show_error

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            # Commande système sûre : xdg-open est l'outil standard sur Linux
            subprocess.Popen(  # noqa: S603
                ["xdg-open", url],  # noqa: S607
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.exception("Error while opening URL %s", url)
            show_error(
                self,
                _("Unable to open URL:\n%s") % str(exc),
                heading=_("Error"),
            )
