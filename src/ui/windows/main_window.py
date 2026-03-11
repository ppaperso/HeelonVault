"""Main application window with a premium 3-column Adwaita layout."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING, cast

import gi  # type: ignore[import]

from src.config.environment import get_data_directory
from src.i18n import _, ngettext
from src.models.category import Category
from src.models.password_entry import PasswordEntry
from src.models.user_info import UserInfo, UserInfoUpdate
from src.repositories.password_repository import PasswordRepository
from src.services.password_service import PasswordService
from src.services.password_strength_service import PasswordStrengthService
from src.services.security_audit_service import SecurityAuditService
from src.ui.dialogs.create_vault_dialog import CreateVaultDialog
from src.ui.dialogs.helpers import present_alert
from src.ui.dialogs.manage_categories_dialog import ManageCategoriesDialog
from src.ui.dialogs.password_generator_dialog import PasswordGeneratorDialog
from src.ui.widgets.security_dashboard_bar import SecurityDashboardBar
from src.version import __app_name__

if TYPE_CHECKING:
    from src.app.application import PasswordManagerApplication
    from src.models.vault import Vault
    from src.services.vault_service import VaultService

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

logger = logging.getLogger(__name__)


class EntryCard(Gtk.Box):
    """Entry card rendered inside the center grid."""

    def __init__(self, entry: PasswordEntry, strength_service: PasswordStrengthService):
        super().__init__()
        self.entry = entry
        self.strength_service = strength_service
        self.add_css_class("entry-list-row")
        self.usage_badge: Gtk.Label | None = None
        self.title_label: Gtk.Label | None = None
        self.hint_label: Gtk.Label | None = None
        self.tags_box: Gtk.Box | None = None
        self.strength_bar: Gtk.Box | None = None

        frame = Gtk.Frame()
        frame.set_css_classes(["password-card"])
        frame.add_css_class("entry-compact-card")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self.strength_bar = Gtk.Box()
        self.strength_bar.set_css_classes(["card-strength-bar", "entry-strength-bar"])
        self._refresh_strength(entry)
        row.append(self.strength_bar)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.set_margin_top(7)
        content.set_margin_bottom(7)
        content.set_margin_start(10)
        content.set_margin_end(10)
        content.set_hexpand(True)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.title_label = Gtk.Label(label=entry.title, xalign=0)
        self.title_label.set_css_classes(["card-title"])
        self.title_label.set_hexpand(True)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_row.append(self.title_label)

        self.usage_badge = Gtk.Label()
        self.usage_badge.set_css_classes(["card-alert-badge", "card-usage-badge"])
        self._update_usage_badge()
        title_row.append(self.usage_badge)

        content.append(title_row)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.hint_label = Gtk.Label(label=self._build_hint(entry), xalign=0)
        self.hint_label.set_css_classes(["card-hint"])
        self.hint_label.set_hexpand(True)
        self.hint_label.set_ellipsize(Pango.EllipsizeMode.END)
        bottom.append(self.hint_label)

        self.tags_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bottom.append(self.tags_box)
        self._refresh_tags(entry)

        content.append(bottom)

        row.append(content)
        frame.set_child(row)
        self.append(frame)

    def _update_usage_badge(self) -> None:
        if not self.usage_badge:
            return
        self.usage_badge.set_label(_("%(count)s uses") % {"count": self.entry.usage_count})

    def bump_usage(self) -> None:
        self.entry.usage_count += 1
        self._update_usage_badge()

    def refresh(self, entry: PasswordEntry) -> None:
        self.entry = entry
        if self.title_label:
            self.title_label.set_label(entry.title)
        if self.hint_label:
            self.hint_label.set_label(self._build_hint(entry))
        self._refresh_tags(entry)
        self._update_usage_badge()
        self._refresh_strength(entry)

    def _refresh_strength(self, entry: PasswordEntry) -> None:
        if not self.strength_bar:
            return
        score = entry.strength_score
        if score < 0:
            result = self.strength_service.evaluate(entry.password)
            score_raw = result.get("score", 0)
            score = score_raw if isinstance(score_raw, int) else 0
        for level in range(5):
            self.strength_bar.remove_css_class(f"strength-{level}")
        self.strength_bar.add_css_class(f"strength-{max(0, min(score, 4))}")

    def _refresh_tags(self, entry: PasswordEntry) -> None:
        if not self.tags_box:
            return
        while (child := self.tags_box.get_first_child()) is not None:
            self.tags_box.remove(child)
        for tag in entry.tags[:2]:
            tag_lbl = Gtk.Label(label=f"# {tag}")
            tag_lbl.set_css_classes(["card-tag-pill"])
            self.tags_box.append(tag_lbl)

    @staticmethod
    def _build_hint(entry: PasswordEntry) -> str:
        if entry.username:
            return entry.username
        if entry.url:
            return entry.url.split("//")[-1].split("/")[0].replace("www.", "")
        if entry.category:
            return entry.category
        return _("No metadata")


class PasswordManagerWindow(Adw.ApplicationWindow):
    """Main window showing vault filters, entry list and inline details."""

    def __init__(
        self,
        app: Adw.Application,
        password_service: PasswordService,
        strength_service: PasswordStrengthService,
        audit_service: SecurityAuditService,
        user_info: UserInfo,
        vault_service: VaultService,
        current_vault: Vault,
    ):
        super().__init__(application=app, title=__app_name__)

        self.password_service = password_service
        self.strength_service = strength_service
        self.audit_service = audit_service
        self.user_info = user_info
        self.app = app
        self.vault_service = vault_service
        self.current_vault = current_vault

        self.current_category_filter = "All"
        self.current_tag_filter: str | None = None
        self.current_security_filter: str | None = None
        self.current_search_text = ""
        self.current_sort_mode = "usage_desc"
        self.current_entry_id: int | None = None
        self.is_creating_new = False

        self._detail_dirty = False
        self._updating_detail = False
        self._clipboard_clear_source_id: int | None = None
        self._clipboard_token = 0

        self._category_by_row: dict[Gtk.ListBoxRow, str] = {}
        self._tag_by_child: dict[Gtk.FlowBoxChild, str] = {}
        self._entry_by_child: dict[Gtk.FlowBoxChild, PasswordEntry] = {}
        self._entry_child_by_id: dict[int, Gtk.FlowBoxChild] = {}
        self._entry_card_by_id: dict[int, EntryCard] = {}
        self._suppress_entry_selection = False
        self._suppress_filter_signals = False

        self.toast_overlay: Adw.ToastOverlay | None = None
        self.unsaved_badge: Gtk.Label | None = None

        self.sort_dropdown: Gtk.DropDown | None = None
        self.nav_toggle_button: Gtk.ToggleButton | None = None
        self.nav_revealer: Gtk.Revealer | None = None
        self.nav_scrim: Gtk.Button | None = None
        self.vault_listbox: Gtk.ListBox | None = None
        self._vault_by_row: dict[Gtk.ListBoxRow, Vault] = {}
        self._suppress_vault_signals = False
        self.user_avatar: Adw.Avatar | None = None
        self.user_name_label: Gtk.Label | None = None
        self.category_listbox: Gtk.ListBox | None = None
        self.tag_flowbox: Gtk.FlowBox | None = None
        self.entry_flowbox: Gtk.FlowBox | None = None
        self.entry_counter_label: Gtk.Label | None = None
        self.security_bar: SecurityDashboardBar | None = None
        self.empty_state_label: Gtk.Label | None = None
        self.zero_usage_label: Gtk.Label | None = None

        self.detail_header_title: Gtk.Label | None = None
        self.detail_meta_label: Gtk.Label | None = None
        self.detail_revert_button: Gtk.Button | None = None
        self.detail_delete_button: Gtk.Button | None = None

        self.detail_title_row: Adw.EntryRow | None = None
        self.detail_username_row: Adw.EntryRow | None = None
        self.detail_password_row: Adw.PasswordEntryRow | None = None
        self.detail_password_strength_inline_label: Gtk.Label | None = None
        self.detail_url_row: Adw.EntryRow | None = None
        self.detail_category_row: Adw.ComboRow | None = None
        self.detail_category_model: Gtk.StringList | None = None
        self._category_names: list[str] = []
        self.detail_tags_row: Adw.EntryRow | None = None
        self.detail_validity_row: Adw.SpinRow | None = None
        self.detail_notes_view: Gtk.TextView | None = None

        self._init_layout()
        self.refresh_vault_sidebar()
        self.load_categories()
        self.load_tags()
        self.load_entries()

        logger.info(
            "Main 3-column premium window ready for %s (role=%s)",
            self.user_info.get("username"),
            self.user_info.get("role"),
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _init_layout(self) -> None:
        self.set_default_size(1500, 920)

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        toolbar_view = Adw.ToolbarView()
        self.toast_overlay.set_child(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        add_button = Gtk.Button(icon_name="list-add-symbolic")
        add_button.set_tooltip_text(_("Create a new entry"))
        add_button.connect("clicked", self.on_add_clicked)
        header.pack_start(add_button)

        self.sort_dropdown = Gtk.DropDown.new_from_strings(
            [
                _("Sort: Most used"),
                _("Sort: Title (A-Z)"),
                _("Sort: Last modified (newest)"),
            ]
        )
        self.sort_dropdown.set_selected(0)
        self.sort_dropdown.connect("notify::selected", self._on_sort_changed)
        header.pack_end(self.sort_dropdown)

        panic_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        panic_box.add_css_class("panic-badge")

        panic_label = Gtk.Label(label=_("Panic"))
        panic_label.add_css_class("panic-badge-label")
        panic_box.append(panic_label)

        soft_lock_btn = Gtk.Button(icon_name="system-lock-screen-symbolic")
        soft_lock_btn.set_tooltip_text(_("Soft lock (logout)"))
        soft_lock_btn.set_css_classes(["flat", "circular", "card-action-btn", "panic-soft-btn"])
        soft_lock_btn.connect("clicked", self._on_soft_lock_clicked)
        panic_box.append(soft_lock_btn)

        panic_lock_btn = Gtk.Button(icon_name="process-stop-symbolic")
        panic_lock_btn.set_tooltip_text(_("Panic lock (purge and close app)"))
        panic_lock_btn.set_css_classes(["flat", "circular", "card-action-btn", "panic-hard-btn"])
        panic_lock_btn.connect("clicked", self._on_panic_lock_clicked)
        panic_box.append(panic_lock_btn)

        header.pack_end(panic_box)

        self.nav_toggle_button = Gtk.ToggleButton(icon_name="sidebar-show-left-symbolic")
        self.nav_toggle_button.set_tooltip_text(_("Open navigation"))
        self.nav_toggle_button.set_css_classes(["flat", "circular", "card-action-btn"])
        self.nav_toggle_button.connect("toggled", self._on_nav_toggle_toggled)
        header.pack_end(self.nav_toggle_button)

        outer_split = Adw.NavigationSplitView.new()
        outer_split.set_min_sidebar_width(260)
        outer_split.set_max_sidebar_width(340)
        outer_split.set_sidebar_width_fraction(0.22)

        inner_split = Adw.NavigationSplitView.new()
        inner_split.set_min_sidebar_width(360)
        inner_split.set_max_sidebar_width(650)
        inner_split.set_sidebar_width_fraction(0.52)

        sidebar_page = Adw.NavigationPage.new(self._build_sidebar_column(), _("Filters"))
        list_page = Adw.NavigationPage.new(self._build_list_column(), _("Entries"))
        detail_page = Adw.NavigationPage.new(self._build_detail_column(), _("Details"))

        inner_split.set_sidebar(list_page)
        inner_split.set_content(detail_page)

        center_page = Adw.NavigationPage.new(inner_split, _("Vault"))
        outer_split.set_sidebar(sidebar_page)
        outer_split.set_content(center_page)

        content_overlay = Gtk.Overlay()
        content_overlay.set_child(outer_split)

        self.nav_scrim = Gtk.Button()
        self.nav_scrim.set_visible(False)
        self.nav_scrim.set_halign(Gtk.Align.FILL)
        self.nav_scrim.set_valign(Gtk.Align.FILL)
        self.nav_scrim.set_hexpand(True)
        self.nav_scrim.set_vexpand(True)
        self.nav_scrim.set_can_focus(False)
        self.nav_scrim.add_css_class("nav-drawer-scrim")
        self.nav_scrim.connect("clicked", self._on_nav_scrim_clicked)
        content_overlay.add_overlay(self.nav_scrim)

        self.nav_revealer = Gtk.Revealer()
        self.nav_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        self.nav_revealer.set_transition_duration(220)
        self.nav_revealer.set_reveal_child(False)
        self.nav_revealer.set_halign(Gtk.Align.START)
        self.nav_revealer.set_valign(Gtk.Align.FILL)
        self.nav_revealer.set_child(self._build_right_navigation_panel())
        content_overlay.add_overlay(self.nav_revealer)

        toolbar_view.set_content(content_overlay)

    def _build_sidebar_column(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        root.set_margin_top(12)
        root.set_margin_bottom(12)

        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.user_avatar = Adw.Avatar(
            size=36,
            text=self.user_info.get("username", "?")[:2].upper(),
            show_initials=True,
        )
        self._apply_avatar_image(self.user_avatar, self.user_info.get("avatar_path"))
        profile_box.append(self.user_avatar)

        profile_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.user_name_label = Gtk.Label(label=self.user_info.get("username", "?"), xalign=0)
        self.user_name_label.set_css_classes(["heading"])
        profile_text.append(self.user_name_label)
        profile_sub = Gtk.Label(label=self.user_info.get("email", ""), xalign=0)
        profile_sub.set_css_classes(["caption", "dim-label"])
        profile_text.append(profile_sub)
        profile_box.append(profile_text)
        root.append(profile_box)

        vault_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vault_title = Gtk.Label(label=_("Vaults"), xalign=0)
        vault_title.set_hexpand(True)
        vault_title.set_css_classes(["heading"])
        vault_header.append(vault_title)

        add_vault_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_vault_btn.set_css_classes(["flat", "circular", "card-action-btn"])
        add_vault_btn.set_tooltip_text(_("Create vault"))
        add_vault_btn.connect("clicked", self._on_create_vault_clicked)
        vault_header.append(add_vault_btn)
        root.append(vault_header)

        vault_group = Adw.PreferencesGroup.new()

        self.vault_listbox = Gtk.ListBox()
        self.vault_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.vault_listbox.connect("row-selected", self._on_vault_selected)
        vault_group.add(self.vault_listbox)
        root.append(vault_group)

        categories_group = Adw.PreferencesGroup.new()
        categories_group.set_title(_("Catégories"))
        self.category_listbox = Gtk.ListBox()
        self.category_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.category_listbox.connect("row-selected", self.on_category_selected)
        categories_group.add(self.category_listbox)
        root.append(categories_group)

        tags_group = Adw.PreferencesGroup.new()
        tags_group.set_title(_("Étiquettes"))
        self.tag_flowbox = Gtk.FlowBox()
        self.tag_flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.tag_flowbox.set_max_children_per_line(3)
        self.tag_flowbox.set_row_spacing(6)
        self.tag_flowbox.set_column_spacing(6)
        self.tag_flowbox.connect("child-activated", self.on_tag_selected)
        tags_group.add(self.tag_flowbox)
        root.append(tags_group)

        tagline = Gtk.Label(label=_("Your secrets never leave your machine."), xalign=0)
        tagline.set_css_classes(["dim-label", "caption"])
        tagline.add_css_class("small")
        root.append(tagline)

        return Gtk.ScrolledWindow(child=root)

    def _build_list_column(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_start(12)
        root.set_margin_end(12)
        root.set_margin_top(12)
        root.set_margin_bottom(12)

        self.entry_counter_label = Gtk.Label(label="", xalign=0)
        self.entry_counter_label.set_css_classes(["title-4"])
        root.append(self.entry_counter_label)

        search = Gtk.SearchEntry()
        search.set_placeholder_text(_("Search in title, username or URL"))
        search.connect("search-changed", self.on_search_changed)
        root.append(search)

        self.security_bar = SecurityDashboardBar()
        self.security_bar.connect("filter-changed", self._on_security_filter)
        self.security_bar.set_visible(False)
        root.append(self.security_bar)

        self.entry_flowbox = Gtk.FlowBox()
        self.entry_flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.entry_flowbox.set_activate_on_single_click(True)
        self.entry_flowbox.set_valign(Gtk.Align.START)
        self.entry_flowbox.set_min_children_per_line(1)
        self.entry_flowbox.set_max_children_per_line(3)
        self.entry_flowbox.set_row_spacing(10)
        self.entry_flowbox.set_column_spacing(10)
        self.entry_flowbox.connect(
            "selected-children-changed", self._on_entry_selection_changed
        )

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.entry_flowbox)
        root.append(scroll)

        self.empty_state_label = Gtk.Label(label=_("No entries for current filters"))
        self.empty_state_label.set_css_classes(["dim-label"])
        self.empty_state_label.set_visible(False)
        root.append(self.empty_state_label)

        self.zero_usage_label = Gtk.Label(label="", xalign=0)
        self.zero_usage_label.set_css_classes(["caption", "dim-label"])
        self.zero_usage_label.set_visible(False)
        root.append(self.zero_usage_label)

        return root

    def _build_detail_column(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.add_css_class("detail-panel")
        root.set_margin_start(20)
        root.set_margin_end(20)
        root.set_margin_top(16)
        root.set_margin_bottom(16)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title_col.set_hexpand(True)

        self.detail_header_title = Gtk.Label(label=_("Select an entry"), xalign=0)
        self.detail_header_title.set_css_classes(["title-2"])
        title_col.append(self.detail_header_title)

        top.append(title_col)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_halign(Gtk.Align.END)

        self.detail_revert_button = Gtk.Button()
        self.detail_revert_button.set_icon_name("edit-undo-symbolic")
        self.detail_revert_button.set_tooltip_text(_("Revert changes"))
        self.detail_revert_button.set_css_classes(["flat", "circular", "card-action-btn"])
        self.detail_revert_button.connect("clicked", self._on_revert_clicked)
        actions.append(self.detail_revert_button)

        self.detail_delete_button = Gtk.Button()
        self.detail_delete_button.set_icon_name("user-trash-symbolic")
        self.detail_delete_button.set_tooltip_text(_("Move to trash"))
        self.detail_delete_button.set_css_classes(["flat", "circular", "card-delete-btn"])
        self.detail_delete_button.connect("clicked", self._on_delete_current_clicked)
        actions.append(self.detail_delete_button)

        top.append(actions)
        header_box.append(top)

        self.unsaved_badge = Gtk.Label(label=f"● {_('Unsaved changes')}", xalign=0)
        self.unsaved_badge.set_css_classes(["unsaved-indicator"])
        self.unsaved_badge.set_visible(False)
        header_box.append(self.unsaved_badge)

        self.detail_meta_label = Gtk.Label(label="", xalign=0)
        self.detail_meta_label.set_css_classes(["caption", "dim-label"])
        header_box.append(self.detail_meta_label)

        root.append(header_box)

        identifiers_group = Adw.PreferencesGroup.new()
        identifiers_group.set_title(_("Identifiants"))
        identifiers_group.set_margin_start(12)
        identifiers_group.set_margin_end(12)

        self.detail_title_row = Adw.EntryRow.new()
        self.detail_title_row.set_title(_("Title"))
        self.detail_title_row.add_css_class("detail-field")
        identifiers_group.add(self.detail_title_row)

        self.detail_username_row = Adw.EntryRow.new()
        self.detail_username_row.set_title(_("Username"))
        self.detail_username_row.add_css_class("detail-field")
        identifiers_group.add(self.detail_username_row)

        self.detail_password_row = Adw.PasswordEntryRow.new()
        self.detail_password_row.set_title(_("Password"))
        self.detail_password_row.add_css_class("detail-field")

        self.detail_password_strength_inline_label = Gtk.Label(label="", xalign=0)
        self.detail_password_strength_inline_label.set_css_classes(
            ["password-inline-strength", "card-hint"]
        )
        self.detail_password_strength_inline_label.set_valign(Gtk.Align.CENTER)
        self.detail_password_row.add_suffix(self.detail_password_strength_inline_label)

        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        copy_btn.set_css_classes(
            ["flat", "circular", "card-action-btn", "password-action-btn"]
        )
        copy_btn.set_tooltip_text(_("Copy password"))
        copy_btn.connect("clicked", self._on_copy_password_clicked)
        self.detail_password_row.add_suffix(copy_btn)

        gen_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        gen_btn.set_css_classes(
            ["flat", "circular", "card-action-btn", "password-action-btn"]
        )
        gen_btn.set_tooltip_text(_("Generate password"))
        gen_btn.connect("clicked", self._on_open_generator_clicked)
        self.detail_password_row.add_suffix(gen_btn)
        identifiers_group.add(self.detail_password_row)

        self.detail_url_row = Adw.EntryRow.new()
        self.detail_url_row.set_title(_("URL"))
        self.detail_url_row.add_css_class("detail-field")
        # Bouton launch URL
        open_url_btn = Gtk.Button(icon_name="web-browser-symbolic")
        open_url_btn.set_css_classes(["flat", "circular", "card-action-btn"])
        open_url_btn.set_tooltip_text(_("Open URL in browser"))
        open_url_btn.connect("clicked", self._on_open_url_clicked)
        self.detail_url_row.add_suffix(open_url_btn)

        identifiers_group.add(self.detail_url_row)

        root.append(identifiers_group)

        organization_group = Adw.PreferencesGroup.new()
        organization_group.set_title(_("Organisation"))
        organization_group.set_margin_start(12)
        organization_group.set_margin_end(12)

        self.detail_category_row = Adw.ComboRow.new()
        self.detail_category_row.set_title(_("Category"))
        self.detail_category_row.add_css_class("detail-field")
        self.detail_category_model = Gtk.StringList.new([])
        self.detail_category_row.set_model(self.detail_category_model)

        add_category_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_category_btn.set_css_classes(["flat", "circular", "card-action-btn"])
        add_category_btn.set_tooltip_text(_("New category"))
        add_category_btn.connect("clicked", self._on_add_category_inline_clicked)
        self.detail_category_row.add_suffix(add_category_btn)
        organization_group.add(self.detail_category_row)

        self.detail_tags_row = Adw.EntryRow.new()
        self.detail_tags_row.set_title(_("Tags"))
        self.detail_tags_row.add_css_class("detail-field")
        organization_group.add(self.detail_tags_row)

        root.append(organization_group)

        security_group = Adw.PreferencesGroup.new()
        security_group.set_title(_("Sécurité"))
        security_group.set_margin_start(12)
        security_group.set_margin_end(12)

        validity_adjustment = Gtk.Adjustment(value=90, lower=1, upper=3650, step_increment=1)
        self.detail_validity_row = Adw.SpinRow.new_with_range(1, 3650, 1)
        self.detail_validity_row.set_title(_("Password validity (days)"))
        self.detail_validity_row.set_adjustment(validity_adjustment)
        self.detail_validity_row.add_css_class("detail-field")
        security_group.add(self.detail_validity_row)

        root.append(security_group)

        notes_group = Adw.PreferencesGroup.new()
        notes_group.set_title(_("Notes"))
        notes_group.set_margin_start(12)
        notes_group.set_margin_end(12)

        notes_expander = Gtk.Expander(label=_("Show notes"))
        notes_expander.set_expanded(False)

        self.detail_notes_view = Gtk.TextView()
        self.detail_notes_view.add_css_class("detail-field")
        self.detail_notes_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.detail_notes_view.set_vexpand(False)

        notes_scroll = Gtk.ScrolledWindow()
        notes_scroll.set_min_content_height(96)
        notes_scroll.set_max_content_height(120)
        notes_scroll.set_child(self.detail_notes_view)
        notes_expander.set_child(notes_scroll)

        notes_group.add(notes_expander)
        root.append(notes_group)

        self._connect_detail_change_signals()
        self._set_detail_sensitive(False)
        self._mark_dirty(False)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_margin_start(20)
        wrapper.set_margin_end(20)
        wrapper.set_margin_top(16)
        wrapper.set_margin_bottom(16)
        wrapper.append(root)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(wrapper)
        return scrolled

    # ------------------------------------------------------------------
    # Navigation drawer
    # ------------------------------------------------------------------
    def _build_right_navigation_panel(self) -> Gtk.Widget:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.add_css_class("nav-drawer")
        panel.set_margin_top(12)
        panel.set_margin_start(12)
        panel.set_margin_bottom(12)
        panel.set_size_request(320, -1)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label=_("Navigation"), xalign=0)
        title.set_css_classes(["title-4", "nav-drawer-title"])
        title.set_hexpand(True)
        head.append(title)

        close_btn = Gtk.Button(icon_name="window-close-symbolic")
        close_btn.set_css_classes(["flat", "circular", "card-action-btn"])
        close_btn.set_tooltip_text(_("Close"))
        close_btn.connect("clicked", lambda _b: self._set_navigation_visible(False))
        head.append(close_btn)
        panel.append(head)

        nav_scroll = Gtk.ScrolledWindow()
        nav_scroll.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_start(6)
        content.set_margin_end(6)
        content.set_margin_top(4)
        content.set_margin_bottom(4)

        sections: list[tuple[str, list[tuple[str, str, str, bool]]]] = [
            (
                _("Account"),
                [(_("Manage account"), "manage_account", "avatar-default-symbolic", False)],
            ),
            (
                _("Data"),
                [
                    (_("Import CSV"), "import_csv", "document-open-symbolic", False),
                    (_("Export CSV"), "export_csv", "document-save-symbolic", False),
                    (_("Manage categories"), "manage_categories", "tag-symbolic", False),
                    (_("Backups"), "manage_backups", "folder-download-symbolic", False),
                    (_("Trash"), "open_trash", "user-trash-symbolic", False),
                ],
            ),
            (
                _("Security"),
                [(_("Security Report ✨"), "security_report", "security-high-symbolic", False)],
            ),
            (
                _("Administration"),
                [(_("Manage users"), "manage_users", "system-users-symbolic", False)],
            ),
            (
                _("Session"),
                [
                    (_("Switch user"), "switch_user", "system-switch-user-symbolic", False),
                    (_("Logout"), "logout", "system-log-out-symbolic", True),
                    (_("About"), "about", "help-about-symbolic", False),
                ],
            ),
        ]

        for section_title, actions in sections:
            section_lbl = Gtk.Label(label=section_title, xalign=0)
            section_lbl.set_css_classes(["caption", "dim-label", "nav-drawer-section"])
            content.append(section_lbl)

            for label, action_name, icon_name, destructive in actions:
                content.append(
                    self._build_nav_action_button(label, action_name, icon_name, destructive)
                )

        nav_scroll.set_child(content)
        panel.append(nav_scroll)
        return panel

    def _build_nav_action_button(
        self,
        label: str,
        action_name: str,
        icon_name: str,
        destructive: bool = False,
    ) -> Gtk.Button:
        button = Gtk.Button()
        button.set_hexpand(True)
        button.set_halign(Gtk.Align.FILL)
        button.set_css_classes(["flat", "app-menu-item", "nav-drawer-btn"])
        if destructive:
            button.add_css_class("app-menu-item-destructive")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_start(8)
        row.set_margin_end(8)
        row.set_margin_top(6)
        row.set_margin_bottom(6)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(18)
        row.append(icon)

        text = Gtk.Label(label=label, xalign=0)
        text.set_hexpand(True)
        row.append(text)

        chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
        chevron.add_css_class("dim-label")
        chevron.set_pixel_size(14)
        row.append(chevron)

        button.set_child(row)
        button.connect("clicked", lambda _b: self._on_nav_action_clicked(action_name))

        action = self.app.lookup_action(action_name)
        if action is None:
            button.set_sensitive(False)

        return button

    def _on_nav_toggle_toggled(self, button: Gtk.ToggleButton) -> None:
        self._set_navigation_visible(button.get_active())

    def _on_nav_scrim_clicked(self, _button: Gtk.Button) -> None:
        self._set_navigation_visible(False)

    def _set_navigation_visible(self, visible: bool) -> None:
        if self.nav_revealer:
            self.nav_revealer.set_reveal_child(visible)
        if self.nav_scrim:
            self.nav_scrim.set_visible(visible)
        if self.nav_toggle_button and self.nav_toggle_button.get_active() != visible:
            self.nav_toggle_button.set_active(visible)

    def _on_nav_action_clicked(self, action_name: str) -> None:
        self._set_navigation_visible(False)
        if self.app.lookup_action(action_name) is not None:
            self.app.activate_action(action_name, None)

    def _on_soft_lock_clicked(self, _button: Gtk.Button) -> None:
        """Quick lock for shoulder-surfing: logout but keep application alive."""
        self._set_navigation_visible(False)
        if self.app.lookup_action("logout") is not None:
            self.app.activate_action("logout", None)

    def _on_panic_lock_clicked(self, _button: Gtk.Button) -> None:
        """Emergency lock: purge in-memory UI/session refs then close app immediately."""
        dialog = Adw.MessageDialog.new(
            self,
            _("Panic lock"),
            _("Purge volatile data and close the application immediately?"),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("panic", _("Panic lock"))
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("panic", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_panic_dialog_response)
        dialog.present()

    def _on_panic_dialog_response(self, _dialog: Adw.MessageDialog, response: str) -> None:
        if response != "panic":
            return
        self._execute_panic_lock()

    def _execute_panic_lock(self) -> None:
        self._set_navigation_visible(False)
        self._panic_purge_memory_state()

        app = cast("PasswordManagerApplication", self.app)
        if getattr(app, "window", None) is self:
            app.window = None
        app.quit()

    def _panic_purge_memory_state(self) -> None:
        """Best-effort purge of volatile user data held by the active window/session."""
        if self._clipboard_clear_source_id:
            GLib.source_remove(self._clipboard_clear_source_id)
            self._clipboard_clear_source_id = None
        self._clipboard_token += 1
        self._clear_clipboard_now()

        self._clear_detail()
        self._set_detail_sensitive(False)

        self.current_entry_id = None
        self.current_search_text = ""
        self.current_tag_filter = None
        self.current_security_filter = None
        self._detail_dirty = False

        self._entry_by_child.clear()
        self._entry_child_by_id.clear()
        self._entry_card_by_id.clear()
        if self.entry_flowbox:
            self._clear_flowbox(self.entry_flowbox)

        try:
            self.password_service.close()
        except Exception:
            logger.exception("Panic lock: unable to close password service cleanly")

        app = cast("PasswordManagerApplication", self.app)
        vault_service = app.vault_service
        if vault_service is not None:
            try:
                vault_service.close()
            except Exception:
                logger.exception("Panic lock: unable to close vault service cleanly")
            app.vault_service = None

        app.password_service = None
        app.repository = None
        app.crypto_service = None
        app._session_master_password = None
        app.current_vault = None
        app.current_user = None
        app.current_db_path = None

    def _clear_clipboard_now(self) -> None:
        clipboard = self.get_clipboard()
        if not clipboard:
            return
        try:
            provider = Gdk.ContentProvider.new_for_bytes(
                "text/plain;charset=utf-8",
                GLib.Bytes.new(b""),
            )
            clipboard.set_content(provider)
        except Exception:
            logger.warning("Panic lock: unable to clear clipboard")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def load_categories(self) -> None:
        if not self.category_listbox:
            return

        self.refresh_category_combo()

        self._clear_listbox(self.category_listbox)
        self._category_by_row.clear()

        all_row = self._build_category_row(_("All categories"))
        self.category_listbox.append(all_row)
        self._category_by_row[all_row] = "All"

        for category in self.password_service.list_categories():
            row = self._build_category_row(category.name)
            self.category_listbox.append(row)
            self._category_by_row[row] = category.name

        first = self.category_listbox.get_row_at_index(0)
        if first:
            #self.category_listbox.select_row(first)
            self._suppress_filter_signals = True
            self.category_listbox.select_row(first)
            self._suppress_filter_signals = False

    def refresh_category_combo(self) -> None:
        if not self.detail_category_row:
            return

        categories = [category.name for category in self.password_service.list_categories()]
        if not categories:
            categories = ["Autres"]
            self.password_service.add_category(Category(name="Autres"))

        selected_before = self._selected_category_name()
        self._category_names = categories
        self.detail_category_model = Gtk.StringList.new(categories)
        self.detail_category_row.set_model(self.detail_category_model)

        if selected_before and selected_before in categories:
            self._select_category_by_name(selected_before)
        else:
            self.detail_category_row.set_selected(0)

    def _selected_category_name(self) -> str:
        if not self.detail_category_row or not self._category_names:
            return ""

        index = int(self.detail_category_row.get_selected())
        if 0 <= index < len(self._category_names):
            return self._category_names[index]
        return ""

    def _select_category_by_name(self, name: str) -> None:
        if not self.detail_category_row:
            return
        if name in self._category_names:
            self.detail_category_row.set_selected(self._category_names.index(name))

    def _on_add_category_inline_clicked(self, _button: Gtk.Button) -> None:
        dialog = Adw.MessageDialog.new(self, _("New category"), _("Enter a category name."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("create", _("Create"))
        dialog.set_default_response("create")
        dialog.set_close_response("cancel")

        entry = Gtk.Entry()
        entry.set_activates_default(True)
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        entry.set_margin_start(8)
        entry.set_margin_end(8)
        dialog.set_extra_child(entry)

        def on_response(_dlg, response: str) -> None:
            if response != "create":
                return

            name = entry.get_text().strip()
            if not name:
                return
            if self.password_service.category_exists(name):
                self._select_category_by_name(name)
                return

            self.password_service.add_category(Category(name=name))
            self.refresh_category_combo()
            self._select_category_by_name(name)
            self.load_categories()

        dialog.connect("response", on_response)
        dialog.present()

    def open_manage_categories_dialog(self) -> None:
        dialog = ManageCategoriesDialog(
            self,
            self.password_service,
            on_changed=lambda: self._on_categories_changed(),
        )

        def on_close_request(_dlg) -> bool:
            self._on_categories_changed()
            return False

        dialog.connect("close-request", on_close_request)
        dialog.present()

    def _on_categories_changed(self) -> None:
        self.refresh_category_combo()
        self.load_categories()

    def load_tags(self) -> None:
        if not self.tag_flowbox:
            return

        while (child := self.tag_flowbox.get_first_child()) is not None:
            self.tag_flowbox.remove(child)
        self._tag_by_child.clear()

        all_child = Gtk.FlowBoxChild()
        all_label = Gtk.Label(label=f"# { _('All') }")
        all_label.set_css_classes(["card-tag-pill", "filter-tag-pill"])
        all_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        all_box.set_margin_top(3)
        all_box.set_margin_bottom(3)
        all_box.set_margin_start(3)
        all_box.set_margin_end(3)
        all_box.append(all_label)
        all_child.set_child(all_box)
        self.tag_flowbox.append(all_child)
        self._tag_by_child[all_child] = "__ALL__"

        for tag in self.password_service.list_tags():
            child = Gtk.FlowBoxChild()
            label = Gtk.Label(label=f"# {tag}")
            label.set_css_classes(["card-tag-pill", "filter-tag-pill"])
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            box.set_margin_top(3)
            box.set_margin_bottom(3)
            box.set_margin_start(3)
            box.set_margin_end(3)
            box.append(label)
            child.set_child(box)
            self.tag_flowbox.append(child)
            self._tag_by_child[child] = tag

        if self.current_tag_filter is None:
            #self.tag_flowbox.select_child(all_child)
            self._suppress_filter_signals = True
            self.tag_flowbox.select_child(all_child)
            self._suppress_filter_signals = False

    def load_entries(self) -> None:
        if not self.entry_flowbox:
            return

        # Refreshing entries should always present a clean persisted state in UI.
        self._set_unsaved(False)

        self._clear_flowbox(self.entry_flowbox)
        self._entry_by_child.clear()
        self._entry_child_by_id.clear()
        self._entry_card_by_id.clear()

        all_entries = self.password_service.list_entries(
            category_filter=self.current_category_filter,
            tag_filter=self.current_tag_filter,
            search_text=self.current_search_text or None,
        )
        for entry in all_entries:
            result = self.strength_service.evaluate(entry.password)
            score_raw = result.get("score", 0)
            entry.strength_score = score_raw if isinstance(score_raw, int) else 0

        summary = self.audit_service.get_audit_summary(all_entries)
        if self.security_bar:
            self.security_bar.set_visible(len(all_entries) > 0)
            self.security_bar.update(summary)
            self.security_bar.set_active_filter(self.current_security_filter)

        filtered_entries = all_entries
        if self.current_security_filter == "weak":
            weak_ids = cast(set[int], summary.get("weak_ids", set()))
            filtered_entries = [e for e in all_entries if e.id in weak_ids]
        elif self.current_security_filter == "reused":
            reused_ids = cast(set[int], summary.get("reused_ids", set()))
            filtered_entries = [e for e in all_entries if e.id in reused_ids]
        elif self.current_security_filter == "expired":
            expired_ids = cast(set[int], summary.get("expired_ids", set()))
            filtered_entries = [e for e in all_entries if e.id in expired_ids]
        # DEBUG TEMPORAIRE
        import logging
        logging.getLogger(__name__).debug(
            "list_entries returned %d entries for search=%r cat=%r tag=%r",
            len(all_entries),
            self.current_search_text,
            self.current_category_filter,
            self.current_tag_filter,
        )

        if self.current_search_text:
            visible_entries = filtered_entries
            hidden_zero_usage = 0
        else:
            visible_entries = [entry for entry in filtered_entries if entry.usage_count > 0]
            hidden_zero_usage = len(filtered_entries) - len(visible_entries)

        entries = self._sorted_entries(visible_entries)

        unique_entries: list[PasswordEntry] = []
        seen_entry_ids: set[int] = set()
        for entry in entries:
            if entry.id is None:
                unique_entries.append(entry)
                continue
            if entry.id in seen_entry_ids:
                continue
            seen_entry_ids.add(entry.id)
            unique_entries.append(entry)
        entries = unique_entries

        self._suppress_entry_selection = True
        for entry in entries:
            child = Gtk.FlowBoxChild()
            child.add_css_class("entry-card-child")
            card = EntryCard(entry, self.strength_service)
            child.set_child(card)
            self.entry_flowbox.append(child)
            self._entry_by_child[child] = entry
            if entry.id is not None:
                self._entry_child_by_id[entry.id] = child
                self._entry_card_by_id[entry.id] = card
        self._suppress_entry_selection = False

        displayed_count = len(entries)

        if self.entry_counter_label:
            self.entry_counter_label.set_label(
                _("%(count)s entries shown") % {"count": displayed_count}
            )

        if self.empty_state_label:
            if len(entries) == 0 and hidden_zero_usage > 0:
                self.empty_state_label.set_label(
                    _("All cards are at 0 use. Run a search to find them.")
                )
            else:
                self.empty_state_label.set_label(_("No entries for current filters"))
            self.empty_state_label.set_visible(displayed_count == 0)

        if self.zero_usage_label:
            if hidden_zero_usage > 0:
                self.zero_usage_label.set_label(
                    _("Vault: %(count)s cards at 0 use, run a search to find them")
                    % {"count": hidden_zero_usage}
                )
                self.zero_usage_label.set_visible(True)
            else:
                self.zero_usage_label.set_visible(False)

        if entries:
            child = self._entry_child_by_id.get(self.current_entry_id or -1)
            if child is None:
                child = self.entry_flowbox.get_child_at_index(0)
            if child:
                self._suppress_entry_selection = True
                self.entry_flowbox.select_child(child)
                self._suppress_entry_selection = False
                entry = self._entry_by_child.get(child)
                if entry:
                    self.current_entry_id = entry.id
                    self.is_creating_new = False
                    self._populate_detail(entry)
                    self._mark_dirty(False)
        else:
            self.current_entry_id = None
            self.is_creating_new = False
            self._clear_detail()
            self._set_detail_sensitive(False)

    # ------------------------------------------------------------------
    # Filters / sorting / selection
    # ------------------------------------------------------------------
    def on_category_selected(self, _listbox, row):
        if self._suppress_filter_signals or not row:
            return
        category = self._category_by_row.get(row)
        if not category:
            return
        self.current_category_filter = category
        self.current_tag_filter = None
        self._suppress_filter_signals = True
        if self.tag_flowbox:
            all_child = self.tag_flowbox.get_child_at_index(0)
            if all_child:
                self.tag_flowbox.select_child(all_child)
        self._suppress_filter_signals = False
        self.load_entries()

    def on_tag_selected(self, _flowbox, child):
        if self._suppress_filter_signals or not child:
            return
        tag = self._tag_by_child.get(child)
        if not tag:
            return
        self.current_tag_filter = None if tag == "__ALL__" else tag
        self.current_category_filter = "All"
        self._suppress_filter_signals = True
        if self.category_listbox:
            first = self.category_listbox.get_row_at_index(0)
            if first:
                self.category_listbox.select_row(first)
        self._suppress_filter_signals = False
        self.load_entries()

    def on_search_changed(self, search_entry: Gtk.SearchEntry) -> None:
        self.current_search_text = search_entry.get_text().strip()
        self.load_entries()

    def _on_security_filter(self, _bar: SecurityDashboardBar, filter_type: object) -> None:
        self.current_security_filter = filter_type if isinstance(filter_type, str) else None
        self.load_entries()

    def _on_sort_changed(self, dropdown: Gtk.DropDown, _param: object) -> None:
        selected = dropdown.get_selected()
        if selected == 0:
            self.current_sort_mode = "usage_desc"
        elif selected == 1:
            self.current_sort_mode = "title_asc"
        else:
            self.current_sort_mode = "modified_desc"
        self.load_entries()

    def _on_entry_selection_changed(self, flowbox: Gtk.FlowBox) -> None:
        if self._suppress_entry_selection:
            return

        selected = flowbox.get_selected_children()
        if not selected:
            return
        child = selected[0]

        previous_entry_id = self.current_entry_id
        if not self._auto_save_if_dirty(reload_entries=False):
            self._restore_entry_selection(previous_entry_id)
            return

        entry = self._entry_by_child.get(child)
        if not entry:
            return

        self.is_creating_new = False
        self.current_entry_id = entry.id
        self._populate_detail(entry)
        self._mark_dirty(False)

    def _sorted_entries(self, entries: list[PasswordEntry]) -> list[PasswordEntry]:
        if self.current_sort_mode == "usage_desc":
            return sorted(
                entries,
                key=lambda item: (item.usage_count, item.modified_at or datetime.min),
                reverse=True,
            )
        if self.current_sort_mode == "modified_desc":
            return sorted(entries, key=lambda item: item.modified_at or datetime.min, reverse=True)
        return sorted(entries, key=lambda item: item.title.lower())

    # ------------------------------------------------------------------
    # Detail pane actions
    # ------------------------------------------------------------------
    def on_add_clicked(self, _button: Gtk.Button) -> None:
        self.current_entry_id = None
        self.is_creating_new = True
        self._clear_detail()
        self._set_detail_sensitive(True)
        if self.detail_delete_button:
            self.detail_delete_button.set_sensitive(False)
        if self.detail_header_title:
            self.detail_header_title.set_label(_("New entry"))
        if self.detail_meta_label:
            self.detail_meta_label.set_label("")
        self._mark_dirty(False)

    def _save_current_entry(self, *, reload_entries: bool) -> bool:
        payload = self._collect_detail_entry()
        if payload is None:
            return False

        try:
            if self.is_creating_new:
                new_id = self.password_service.create_entry(payload)
                self.current_entry_id = new_id
                self.is_creating_new = False
            else:
                self.password_service.update_entry(payload)

            self.password_service.mark_as_saved()
            self._set_unsaved(False)

            self.load_categories()
            self.load_tags()
            if reload_entries:
                self.load_entries()
            else:
                self._refresh_saved_entry_state()

            return True

        except Exception as exc:
            logger.exception("Unable to save entry")
            from src.ui.notifications import error as show_error

            show_error(self, _("Unable to save entry: %s") % str(exc))
            return False

    def _auto_save_if_dirty(self, *, reload_entries: bool | None = None) -> bool:
        if not self._detail_dirty:
            return True

        should_reload_entries = (
            self._should_reload_entries_after_save()
            if reload_entries is None
            else reload_entries
        )
        success = self._save_current_entry(reload_entries=should_reload_entries)
        if not success:
            return False

        self._mark_dirty(False)
        self._show_autosave_toast()
        return True

    def _show_autosave_toast(self) -> None:
        if not self.toast_overlay:
            return
        toast = Adw.Toast.new(_("✓ Saved"))
        toast.set_timeout(2)
        self.toast_overlay.add_toast(toast)

    def _on_revert_clicked(self, _button: Gtk.Button) -> None:
        if self.current_entry_id is None:
            self._clear_detail()
            self._mark_dirty(False)
            return

        entry = self.password_service.get_entry(self.current_entry_id)
        if not entry:
            return
        self._populate_detail(entry)
        self._mark_dirty(False)

    def _on_delete_current_clicked(self, _button: Gtk.Button) -> None:
        if self.current_entry_id is None:
            return
        self.on_delete_clicked(self.current_entry_id)

    def _on_copy_password_clicked(self, _button: Gtk.Button) -> None:
        password = ""

        if self.current_entry_id is not None:
            current_entry = self.password_service.get_entry(self.current_entry_id)
            if current_entry:
                password = current_entry.password.strip()

        if not password and self.detail_password_row:
            password = self.detail_password_row.get_text().strip()

        if password:
            self.copy_to_clipboard(password, _("Password copied"))
            if self.current_entry_id is not None:
                self.password_service.record_entry_usage(self.current_entry_id)
                if self.current_sort_mode == "usage_desc":
                    self.load_entries()
                else:
                    card = self._entry_card_by_id.get(self.current_entry_id)
                    if card:
                        card.bump_usage()
        else:
            self.show_toast(_("Password is required"))

    def _on_open_generator_clicked(self, _button: Gtk.Button) -> None:
        dialog = PasswordGeneratorDialog(self, self._on_generated_password)
        dialog.present()

    def _on_open_url_clicked(self, _btn) -> None:
        if not self.detail_url_row:
            return
        url = self.detail_url_row.get_text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        Gio.AppInfo.launch_default_for_uri(url, None)


    def _on_generated_password(self, password: str) -> None:
        if not self.detail_password_row:
            return
        self.detail_password_row.set_text(password)
        self._update_detail_strength_indicator(password)
        self._mark_dirty(True)

    # ------------------------------------------------------------------
    # Detail pane data
    # ------------------------------------------------------------------
    def _populate_detail(self, entry: PasswordEntry) -> None:
        rows = self._require_detail_rows()
        if not rows:
            return

        self._updating_detail = True
        self._set_detail_sensitive(True)

        (
            title_row,
            username_row,
            password_row,
            url_row,
            category_row,
            tags_row,
            validity_row,
            notes_view,
        ) = rows

        title_row.set_text(entry.title)
        username_row.set_text(entry.username)
        password_row.set_text(entry.password)
        url_row.set_text(entry.url)
        if entry.category:
            self._select_category_by_name(entry.category)
        elif self._category_names:
            category_row.set_selected(0)
        tags_row.set_text(", ".join(entry.tags))
        validity_row.set_value(float(entry.password_validity_days or 90))
        notes_view.get_buffer().set_text(entry.notes)
        self._update_detail_strength_indicator(entry.password)

        if self.detail_header_title:
            self.detail_header_title.set_label(entry.title)
        if self.detail_meta_label:
            modified = (
                entry.modified_at.strftime("%Y-%m-%d %H:%M")
                if entry.modified_at
                else _("Unknown")
            )
            self.detail_meta_label.set_label(_("Last modified: %s") % modified)

        self._updating_detail = False

    def _clear_detail(self) -> None:
        rows = self._require_detail_rows()
        if not rows:
            return

        self._updating_detail = True
        (
            title_row,
            username_row,
            password_row,
            url_row,
            category_row,
            tags_row,
            validity_row,
            notes_view,
        ) = rows

        title_row.set_text("")
        username_row.set_text("")
        password_row.set_text("")
        url_row.set_text("")
        if self._category_names:
            category_row.set_selected(0)
        tags_row.set_text("")
        validity_row.set_value(90)
        notes_view.get_buffer().set_text("")
        self._update_detail_strength_indicator("")

        if self.detail_header_title:
            self.detail_header_title.set_label(_("Select an entry"))
        if self.detail_meta_label:
            self.detail_meta_label.set_label("")

        self._updating_detail = False

    def _collect_detail_entry(self) -> PasswordEntry | None:
        rows = self._require_detail_rows()
        if not rows:
            return None

        (
            title_row,
            username_row,
            password_row,
            url_row,
            category_row,
            tags_row,
            validity_row,
            notes_view,
        ) = rows

        title = title_row.get_text().strip()
        password = password_row.get_text().strip()

        if not title:
            self.show_toast(_("Title is required"))
            return None
        if not password:
            self.show_toast(_("Password is required"))
            return None

        notes_buffer = notes_view.get_buffer()
        notes_text = notes_buffer.get_text(
            notes_buffer.get_start_iter(),
            notes_buffer.get_end_iter(),
            True,
        )
        tags = [item.strip() for item in tags_row.get_text().split(",") if item.strip()]
        selected_category = self._selected_category_name()
        if not selected_category and self._category_names:
            selected_category = self._category_names[0]

        return PasswordEntry(
            id=None if self.is_creating_new else self.current_entry_id,
            title=title,
            username=username_row.get_text().strip(),
            password=password,
            url=url_row.get_text().strip(),
            notes=notes_text,
            category=selected_category,
            tags=tags,
            password_validity_days=int(validity_row.get_value()),
        )

    def _connect_detail_change_signals(self) -> None:
        rows = self._require_detail_rows()
        if not rows:
            return

        (
            title_row,
            username_row,
            password_row,
            url_row,
            category_row,
            tags_row,
            validity_row,
            notes_view,
        ) = rows

        title_row.connect("changed", self._on_detail_changed)
        username_row.connect("changed", self._on_detail_changed)
        password_row.connect("changed", self._on_detail_changed)
        password_row.connect("notify::text", self._on_detail_password_text_changed)
        url_row.connect("changed", self._on_detail_changed)
        category_row.connect("notify::selected", self._on_detail_changed)
        tags_row.connect("changed", self._on_detail_changed)
        validity_row.connect("notify::value", self._on_detail_changed)
        notes_view.get_buffer().connect("changed", self._on_detail_changed)

        for widget in (
            title_row,
            username_row,
            password_row,
            url_row,
            category_row,
            tags_row,
            validity_row,
            notes_view,
        ):
            widget.connect("notify::has-focus", self._on_field_focus_changed)

    def _on_field_focus_changed(self, widget: Gtk.Widget, _param: object) -> None:
        if self._updating_detail:
            return
        if bool(widget.get_property("has-focus")):
            return
        self._auto_save_if_dirty(reload_entries=None)

    def _on_detail_changed(self, *_args) -> None:
        if self._updating_detail:
            return
        self._mark_dirty(True)

    def _on_detail_password_text_changed(
        self,
        password_row: Adw.PasswordEntryRow,
        _param: object,
    ) -> None:
        self._update_detail_strength_indicator(password_row.get_text())

    def _update_detail_strength_indicator(self, password: str) -> None:
        if not self.detail_password_row or not self.detail_password_strength_inline_label:
            return

        result = self.strength_service.evaluate(password)
        score_raw = result.get("score", 0)
        score = score_raw if isinstance(score_raw, int) else 0
        label = str(result.get("label", ""))
        crack_time = str(result.get("crack_time", ""))

        for level in range(5):
            self.detail_password_row.remove_css_class(f"password-row-strength-{level}")
            self.detail_password_strength_inline_label.remove_css_class(f"strength-{level}")

        normalized_score = max(0, min(score, 4))
        self.detail_password_row.add_css_class(f"password-row-strength-{normalized_score}")
        self.detail_password_strength_inline_label.add_css_class(f"strength-{normalized_score}")

        if password:
            self.detail_password_strength_inline_label.set_label(
                _("%(label)s · %(crack_time)s") % {"label": label, "crack_time": crack_time}
            )
        else:
            self.detail_password_strength_inline_label.set_label("")

    def _mark_dirty(self, dirty: bool) -> None:
        self._detail_dirty = dirty
        if self.unsaved_badge:
            self.unsaved_badge.set_visible(dirty)
        self._update_revert_button_visibility()

    def _update_revert_button_visibility(self) -> None:
        if self.detail_revert_button:
            self.detail_revert_button.set_visible(self._detail_dirty)
            self.detail_revert_button.set_sensitive(self._detail_dirty)

    def _set_unsaved(self, dirty: bool) -> None:
        """Compatibility wrapper for unsaved-state updates."""
        self._mark_dirty(dirty)

    def _should_reload_entries_after_save(self) -> bool:
        return bool(
            self.current_search_text
            or self.current_tag_filter is not None
            or self.current_category_filter != "All"
            or self.current_sort_mode != "usage_desc"
        )

    def _refresh_saved_entry_state(self) -> None:
        if self.current_entry_id is None:
            return

        entry = self.password_service.get_entry(self.current_entry_id)
        if not entry:
            return

        if self.detail_header_title:
            self.detail_header_title.set_label(entry.title)
        if self.detail_meta_label:
            modified = (
                entry.modified_at.strftime("%Y-%m-%d %H:%M")
                if entry.modified_at
                else _("Unknown")
            )
            self.detail_meta_label.set_label(_("Last modified: %s") % modified)

        child = self._entry_child_by_id.get(self.current_entry_id)
        if child:
            self._entry_by_child[child] = entry

        card = self._entry_card_by_id.get(self.current_entry_id)
        if card:
            card.refresh(entry)

    def _restore_entry_selection(self, entry_id: int | None) -> None:
        if not self.entry_flowbox:
            return

        self._suppress_entry_selection = True
        try:
            if entry_id is not None:
                child = self._entry_child_by_id.get(entry_id)
                if child is not None:
                    self.entry_flowbox.select_child(child)
                    return
            self.entry_flowbox.unselect_all()
        finally:
            self._suppress_entry_selection = False

    def _set_detail_sensitive(self, enabled: bool) -> None:
        widgets = [
            self.detail_title_row,
            self.detail_username_row,
            self.detail_password_row,
            self.detail_url_row,
            self.detail_password_strength_inline_label,
            self.detail_category_row,
            self.detail_tags_row,
            self.detail_validity_row,
            self.detail_notes_view,
            self.detail_delete_button,
        ]
        for widget in widgets:
            if widget is not None:
                widget.set_sensitive(enabled)

    # ------------------------------------------------------------------
    # Compatibility methods used from application.py
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_avatar_image(avatar: Adw.Avatar, avatar_path: str | None) -> None:
        if not avatar_path:
            avatar.set_custom_image(None)
            return
        try:
            texture = Gdk.Texture.new_from_filename(str(avatar_path))
            avatar.set_custom_image(texture)
        except Exception:
            avatar.set_custom_image(None)

    def refresh_account_profile(self, user_info: UserInfoUpdate) -> None:
        self.user_info.update(user_info)
        if self.user_name_label:
            self.user_name_label.set_label(self.user_info.get("username", "?"))
        if self.user_avatar:
            self.user_avatar.set_text(self.user_info.get("username", "?")[:2].upper())
            if "avatar_path" in user_info:
                self._apply_avatar_image(self.user_avatar, user_info.get("avatar_path"))

    def refresh_vault_sidebar(self) -> None:
        if not self.vault_listbox:
            return

        self._clear_listbox(self.vault_listbox)
        self._vault_by_row.clear()

        user_id = self.user_info.get("id")
        if not isinstance(user_id, int):
            return

        vaults = self.vault_service.list_vaults(user_id)
        self._suppress_vault_signals = True
        for vault in vaults:
            entry_count = self._count_vault_entries(vault)
            row = self._build_vault_row(vault, len(vaults), entry_count)
            self.vault_listbox.append(row)
            self._vault_by_row[row] = vault

            if self.current_vault and vault.id == self.current_vault.id:
                row.add_css_class("selected")
                self.vault_listbox.select_row(row)

        self._suppress_vault_signals = False

    def _build_vault_row(self, vault: Vault, vault_count: int, entry_count: int) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.add_css_class("vault-row")
        row.add_css_class("entry-list-row")

        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        accent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        accent.add_css_class("vault-accent-bar")
        accent.set_vexpand(True)
        shell.append(accent)

        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        line.set_margin_top(8)
        line.set_margin_bottom(8)
        line.set_margin_start(8)
        line.set_margin_end(8)
        line.set_hexpand(True)

        icon = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
        icon.set_pixel_size(22)
        icon.add_css_class("vault-row-icon")
        icon.set_valign(Gtk.Align.CENTER)
        line.append(icon)

        text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_lbl = Gtk.Label(label=vault.name, xalign=0)
        name_lbl.add_css_class("card-title")
        name_lbl.set_hexpand(True)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        text_col.append(name_lbl)

        count_lbl = Gtk.Label(
            label=ngettext(
                "%(count)s entry",
                "%(count)s entries",
                entry_count,
            )
            % {"count": entry_count},
            xalign=0,
        )
        count_lbl.add_css_class("card-hint")
        text_col.append(count_lbl)

        line.append(text_col)

        if vault.is_default:
            badge = Gtk.Label(label=_("default"))
            badge.add_css_class("status-role-admin")
            badge.set_valign(Gtk.Align.CENTER)
            line.append(badge)

        menu_btn = Gtk.MenuButton(icon_name="view-more-symbolic")
        menu_btn.set_css_classes(["flat"])
        menu_btn.set_tooltip_text(_("Vault actions"))
        menu_btn.set_valign(Gtk.Align.CENTER)
        menu_btn.set_popover(self._build_vault_actions_popover(vault, vault_count))
        line.append(menu_btn)

        shell.append(line)
        row.set_child(shell)
        return row

    def _count_vault_entries(self, vault: Vault) -> int:
        data_dir = getattr(self.vault_service, "data_dir", get_data_directory())
        db_path = data_dir / f"passwords_{vault.uuid}.db"
        if not db_path.exists():
            return 0

        repo = PasswordRepository(db_path)
        try:
            return repo.count_entries()
        finally:
            repo.close()

    def _build_vault_actions_popover(self, vault: Vault, vault_count: int) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        rename_btn = Gtk.Button(label=_("Rename"))
        rename_btn.set_halign(Gtk.Align.FILL)
        rename_btn.set_hexpand(True)
        rename_btn.connect("clicked", lambda _b: self._on_rename_vault_clicked(vault))
        box.append(rename_btn)

        delete_btn = Gtk.Button(label=_("Delete"))
        delete_btn.set_halign(Gtk.Align.FILL)
        delete_btn.set_hexpand(True)
        delete_btn.set_css_classes(["destructive-action"])
        delete_btn.set_sensitive(vault_count > 1)
        delete_btn.connect("clicked", lambda _b: self._on_delete_vault_clicked(vault))
        box.append(delete_btn)

        popover.set_child(box)
        return popover

    def _on_create_vault_clicked(self, _button: Gtk.Button) -> None:
        dialog = CreateVaultDialog(self)

        def on_closed(_dlg) -> bool:
            if not dialog.get_success():
                return False

            user_id = self.user_info.get("id")
            if not isinstance(user_id, int):
                return False

            try:
                new_vault = self.vault_service.create_vault(
                    user_id=user_id,
                    name=dialog.get_vault_name(),
                    master_password=dialog.get_master_password(),
                )
                self.current_vault = new_vault
                self.refresh_vault_sidebar()
                self._switch_to_vault(new_vault)
            except Exception as exc:
                logger.exception("Unable to create vault: %s", exc)
                msg = Adw.MessageDialog.new(
                    self,
                    _("Error"),
                    _("Unable to create vault: %s") % str(exc),
                )
                msg.add_response("ok", _("OK"))
                msg.present()

            return False

        dialog.connect("close-request", on_closed)
        dialog.present()

    def _on_vault_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if self._suppress_vault_signals or row is None:
            return

        vault = self._vault_by_row.get(row)
        if vault is None:
            return
        if self.current_vault and vault.id == self.current_vault.id:
            return

        self._switch_to_vault(vault)

    def _switch_to_vault(self, vault: Vault) -> None:
        on_switch = getattr(self.app, "on_vault_switched", None)
        if not callable(on_switch):
            return

        if on_switch(vault):
            self.current_vault = vault
            self.current_security_filter = None
            if self.security_bar:
                self.security_bar.set_active_filter(None)
            self.load_categories()
            self.load_tags()
            self.load_entries()
            self.refresh_vault_sidebar()
            return

        self.refresh_vault_sidebar()

    def _on_rename_vault_clicked(self, vault: Vault) -> None:
        dialog = Adw.MessageDialog.new(self, _("Rename vault"), _("Enter a new vault name."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("rename", _("Rename"))
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")

        entry = Gtk.Entry()
        entry.set_text(vault.name)
        entry.set_activates_default(True)
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        entry.set_margin_start(8)
        entry.set_margin_end(8)
        dialog.set_extra_child(entry)

        def on_response(_dlg, response: str) -> None:
            if response != "rename":
                return

            new_name = entry.get_text().strip()
            if not new_name:
                return

            if self.vault_service.rename_vault(vault.id, new_name):
                if self.current_vault and self.current_vault.id == vault.id:
                    self.current_vault.name = new_name
                self.refresh_vault_sidebar()

        dialog.connect("response", on_response)
        dialog.present()

    def _on_delete_vault_clicked(self, vault: Vault) -> None:
        dialog = Adw.MessageDialog.new(
            self,
            _("Delete vault"),
            _("Delete vault %(name)s? All entries will be lost.") % {"name": vault.name},
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dlg, response: str) -> None:
            if response != "delete":
                return

            user_id = self.user_info.get("id")
            if not isinstance(user_id, int):
                return

            deleted = self.vault_service.delete_vault(vault.id, user_id)
            if not deleted:
                msg = Adw.MessageDialog.new(
                    self,
                    _("Action not allowed"),
                    _("Unable to delete this vault."),
                )
                msg.add_response("ok", _("OK"))
                msg.present()
                return

            active = self.vault_service.get_active_vault(user_id)
            self.current_vault = active
            self.refresh_vault_sidebar()
            self._switch_to_vault(active)

        dialog.connect("response", on_response)
        dialog.present()

    def on_delete_clicked(self, entry_id: int) -> None:
        present_alert(
            self,
            _("Move to trash?"),
            _("This entry can be restored from the Trash."),
            [("cancel", _("Cancel")), ("delete", _("Move to trash"))],
            default="cancel",
            close="cancel",
            destructive="delete",
            on_response=lambda response: self._delete_confirmed(response, entry_id),
        )

    def _delete_confirmed(self, response: str, entry_id: int) -> None:
        if response != "delete":
            return
        self.password_service.delete_entry(entry_id)
        self.current_entry_id = None
        self.load_tags()
        self.load_entries()
        self.show_toast(_("Entry moved to trash"))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def copy_to_clipboard(self, text: str, message: str = _("Copied to clipboard")) -> None:
        clipboard = self.get_clipboard()
        if not clipboard:
            logger.warning("Clipboard unavailable")
            return

        try:
            bytes_value = GLib.Bytes.new(text.encode("utf-8"))
            provider = Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", bytes_value)
            clipboard.set_content(provider)
            self.show_toast(message)
            self._schedule_clipboard_clear()
        except Exception as exc:
            logger.exception("Unable to write clipboard: %s", exc)

    def _schedule_clipboard_clear(self) -> None:
        self._clipboard_token += 1
        token = self._clipboard_token
        if self._clipboard_clear_source_id:
            GLib.source_remove(self._clipboard_clear_source_id)
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
                provider = Gdk.ContentProvider.new_for_bytes(
                    "text/plain;charset=utf-8",
                    GLib.Bytes.new(b""),
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
        from src.ui.notifications import error as show_error

        safe_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
        try:
            subprocess.Popen(  # noqa: S603
                ["xdg-open", safe_url],  # noqa: S607
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.exception("Unable to open URL %s", safe_url)
            show_error(self, _("Unable to open URL:\n%s") % str(exc), heading=_("Error"))

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clear_listbox(listbox: Gtk.ListBox) -> None:
        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)

    @staticmethod
    def _clear_flowbox(flowbox: Gtk.FlowBox) -> None:
        while (child := flowbox.get_first_child()) is not None:
            flowbox.remove(child)

    @staticmethod
    def _build_category_row(label: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.set_margin_top(6)
        content.set_margin_bottom(6)
        content.set_margin_start(10)
        content.set_margin_end(10)
        icon = Gtk.Image.new_from_icon_name("folder-symbolic")
        content.append(icon)
        content.append(Gtk.Label(label=label, xalign=0))
        row.set_child(content)
        return row

    def _require_detail_rows(
        self,
    ) -> tuple[
        Adw.EntryRow,
        Adw.EntryRow,
        Adw.PasswordEntryRow,
        Adw.EntryRow,
        Adw.ComboRow,
        Adw.EntryRow,
        Adw.SpinRow,
        Gtk.TextView,
    ] | None:
        if not all(
            [
                self.detail_title_row,
                self.detail_username_row,
                self.detail_password_row,
                self.detail_url_row,
                self.detail_category_row,
                self.detail_tags_row,
                self.detail_validity_row,
                self.detail_notes_view,
            ]
        ):
            return None

        return cast(
            tuple[
                Adw.EntryRow,
                Adw.EntryRow,
                Adw.PasswordEntryRow,
                Adw.EntryRow,
                Adw.ComboRow,
                Adw.EntryRow,
                Adw.SpinRow,
                Gtk.TextView,
            ],
            (
                self.detail_title_row,
                self.detail_username_row,
                self.detail_password_row,
                self.detail_url_row,
                self.detail_category_row,
                self.detail_tags_row,
                self.detail_validity_row,
                self.detail_notes_view,
            ),
        )
