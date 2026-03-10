"""Main application window with a premium 3-column Adwaita layout."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from typing import cast

import gi  # type: ignore[import]

from src.i18n import _
from src.models.password_entry import PasswordEntry
from src.models.user_info import UserInfo, UserInfoUpdate
from src.services.password_service import PasswordService
from src.ui.dialogs.helpers import present_alert
from src.ui.dialogs.password_generator_dialog import PasswordGeneratorDialog
from src.version import __app_name__

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

logger = logging.getLogger(__name__)


def analyze_password_strength(password: str) -> tuple[int, str]:
    """Return strength score and css suffix (success/warning/error)."""
    if not password:
        return (0, "error")

    score = 0
    if len(password) >= 12:
        score += 2
    elif len(password) >= 8:
        score += 1

    has_lower = any(char.islower() for char in password)
    has_upper = any(char.isupper() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_symbol = any(not char.isalnum() for char in password)
    complexity = sum([has_lower, has_upper, has_digit, has_symbol])

    if complexity >= 3:
        score += 2
    elif complexity >= 2:
        score += 1

    if score >= 3:
        return (score, "success")
    if score == 2:
        return (score, "warning")
    return (score, "error")


class EntryCard(Gtk.Box):
    """Entry card rendered inside the center grid."""

    def __init__(self, entry: PasswordEntry):
        super().__init__()
        self.entry = entry
        self.add_css_class("entry-list-row")
        self.usage_badge: Gtk.Label | None = None

        _score, strength_css = analyze_password_strength(entry.password)

        frame = Gtk.Frame()
        frame.set_css_classes(["password-card"])
        frame.add_css_class("entry-compact-card")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        strength_bar = Gtk.Box()
        strength_bar.set_css_classes(
            ["card-strength-bar", "entry-strength-bar", f"card-strength-{strength_css}"]
        )
        row.append(strength_bar)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.set_margin_top(7)
        content.set_margin_bottom(7)
        content.set_margin_start(10)
        content.set_margin_end(10)
        content.set_hexpand(True)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        title = Gtk.Label(label=entry.title, xalign=0)
        title.set_css_classes(["card-title"])
        title.set_hexpand(True)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title_row.append(title)

        self.usage_badge = Gtk.Label()
        self.usage_badge.set_css_classes(["card-alert-badge", "card-usage-badge"])
        self._update_usage_badge()
        title_row.append(self.usage_badge)

        content.append(title_row)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        hint = Gtk.Label(label=self._build_hint(entry), xalign=0)
        hint.set_css_classes(["card-hint"])
        hint.set_hexpand(True)
        hint.set_ellipsize(Pango.EllipsizeMode.END)
        bottom.append(hint)

        if entry.tags:
            for tag in entry.tags[:2]:
                tag_lbl = Gtk.Label(label=f"# {tag}")
                tag_lbl.set_css_classes(["card-tag-pill"])
                bottom.append(tag_lbl)

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
        user_info: UserInfo,
    ):
        super().__init__(application=app, title=__app_name__)

        self.password_service = password_service
        self.user_info = user_info

        self.current_category_filter = "All"
        self.current_tag_filter: str | None = None
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
        self.vault_row: Adw.ActionRow | None = None
        self.user_avatar: Adw.Avatar | None = None
        self.user_name_label: Gtk.Label | None = None
        self.category_listbox: Gtk.ListBox | None = None
        self.tag_flowbox: Gtk.FlowBox | None = None
        self.entry_flowbox: Gtk.FlowBox | None = None
        self.entry_counter_label: Gtk.Label | None = None
        self.empty_state_label: Gtk.Label | None = None
        self.zero_usage_label: Gtk.Label | None = None

        self.detail_header_title: Gtk.Label | None = None
        self.detail_meta_label: Gtk.Label | None = None
        self.detail_save_button: Gtk.Button | None = None
        self.detail_revert_button: Gtk.Button | None = None
        self.detail_delete_button: Gtk.Button | None = None

        self.detail_title_row: Adw.EntryRow | None = None
        self.detail_username_row: Adw.EntryRow | None = None
        self.detail_password_row: Adw.PasswordEntryRow | None = None
        self.detail_url_row: Adw.EntryRow | None = None
        self.detail_category_row: Adw.EntryRow | None = None
        self.detail_tags_row: Adw.EntryRow | None = None
        self.detail_validity_row: Adw.SpinRow | None = None
        self.detail_notes_view: Gtk.TextView | None = None

        self._init_layout()
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

        self.unsaved_badge = Gtk.Label(label=_("Unsaved changes"))
        self.unsaved_badge.set_css_classes(["caption", "unsaved-indicator"])
        self.unsaved_badge.set_visible(False)
        header.pack_start(self.unsaved_badge)

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

        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_menu_model(self._build_app_menu())
        header.pack_end(menu_button)

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

        toolbar_view.set_content(outer_split)

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

        vault_group = Adw.PreferencesGroup.new()
        vault_group.set_title(_("Vaults"))
        self.vault_row = Adw.ActionRow.new()
        self.vault_row.set_title(self._vault_title())
        self.vault_row.set_subtitle(_("Single local vault (multi-vault ready)"))
        self.vault_row.add_prefix(Gtk.Image.new_from_icon_name("folder-symbolic"))
        vault_group.add(self.vault_row)
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

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_col.set_hexpand(True)

        self.detail_header_title = Gtk.Label(label=_("Select an entry"), xalign=0)
        self.detail_header_title.set_css_classes(["title-2"])
        title_col.append(self.detail_header_title)

        self.detail_meta_label = Gtk.Label(label="", xalign=0)
        self.detail_meta_label.set_css_classes(["caption", "dim-label"])
        title_col.append(self.detail_meta_label)

        top.append(title_col)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_halign(Gtk.Align.END)

        self.detail_save_button = Gtk.Button(label=_("Save"))
        self.detail_save_button.set_icon_name("document-save-symbolic")
        self.detail_save_button.set_css_classes(["suggested-action", "pill"])
        self.detail_save_button.connect("clicked", self._on_save_clicked)
        actions.append(self.detail_save_button)

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
        root.append(top)

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
        identifiers_group.add(self.detail_url_row)

        root.append(identifiers_group)

        organization_group = Adw.PreferencesGroup.new()
        organization_group.set_title(_("Organisation"))
        organization_group.set_margin_start(12)
        organization_group.set_margin_end(12)

        self.detail_category_row = Adw.EntryRow.new()
        self.detail_category_row.set_title(_("Category"))
        self.detail_category_row.add_css_class("detail-field")
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
    # Menu
    # ------------------------------------------------------------------
    def _build_app_menu(self) -> Gio.Menu:
        menu = Gio.Menu()

        account = Gio.Menu()
        account.append(_("Manage account"), "app.manage_account")
        account.append(_("Change password"), "app.change_own_password")
        account.append(_("Change email"), "app.change_own_email")
        account.append(_("Reconfigure 2FA"), "app.reconfigure_2fa")
        menu.append_section(_("Account"), account)

        data_ops = Gio.Menu()
        data_ops.append(_("Import CSV"), "app.import_csv")
        data_ops.append(_("Export CSV"), "app.export_csv")
        data_ops.append(_("Backups"), "app.manage_backups")
        data_ops.append(_("Trash"), "app.open_trash")
        menu.append_section(_("Data"), data_ops)

        admin = Gio.Menu()
        admin.append(_("Manage users"), "app.manage_users")
        menu.append_section(_("Administration"), admin)

        session = Gio.Menu()
        session.append(_("Switch user"), "app.switch_user")
        session.append(_("Logout"), "app.logout")
        session.append(_("About"), "app.about")
        menu.append_section(_("Session"), session)

        return menu

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def load_categories(self) -> None:
        if not self.category_listbox:
            return

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

        self._clear_flowbox(self.entry_flowbox)
        self._entry_by_child.clear()
        self._entry_child_by_id.clear()
        self._entry_card_by_id.clear()

        all_entries = self.password_service.list_entries(
            category_filter=self.current_category_filter,
            tag_filter=self.current_tag_filter,
            search_text=self.current_search_text or None,
        )
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
            visible_entries = all_entries
            hidden_zero_usage = 0
        else:
            visible_entries = [entry for entry in all_entries if entry.usage_count > 0]
            hidden_zero_usage = len(all_entries) - len(visible_entries)

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
            card = EntryCard(entry)
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

        if self._detail_dirty:
            self.show_toast(_("Unsaved changes were discarded"))

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
            self.detail_meta_label.set_label(_("Fill fields, then save"))
        self._mark_dirty(False)

    def _on_save_clicked(self, _button: Gtk.Button) -> None:
        payload = self._collect_detail_entry()
        if payload is None:
            return

        try:
            if self.is_creating_new:
                new_id = self.password_service.create_entry(payload)
                self.current_entry_id = new_id
                self.is_creating_new = False
                self.show_toast(_("Entry created"))
            else:
                self.password_service.update_entry(payload)
                self.show_toast(_("Entry saved"))

            self.load_categories()
            self.load_tags()
            self.load_entries()
            self._mark_dirty(False)

        except Exception as exc:
            logger.exception("Unable to save entry")
            from src.ui.notifications import error as show_error

            show_error(self, _("Unable to save entry: %s") % str(exc))

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

    def _on_generated_password(self, password: str) -> None:
        if not self.detail_password_row:
            return
        self.detail_password_row.set_text(password)
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
        category_row.set_text(entry.category)
        tags_row.set_text(", ".join(entry.tags))
        validity_row.set_value(float(entry.password_validity_days or 90))
        notes_view.get_buffer().set_text(entry.notes)

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
        category_row.set_text("")
        tags_row.set_text("")
        validity_row.set_value(90)
        notes_view.get_buffer().set_text("")

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

        return PasswordEntry(
            id=None if self.is_creating_new else self.current_entry_id,
            title=title,
            username=username_row.get_text().strip(),
            password=password,
            url=url_row.get_text().strip(),
            notes=notes_text,
            category=category_row.get_text().strip(),
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
        url_row.connect("changed", self._on_detail_changed)
        category_row.connect("changed", self._on_detail_changed)
        tags_row.connect("changed", self._on_detail_changed)
        validity_row.connect("notify::value", self._on_detail_changed)
        notes_view.get_buffer().connect("changed", self._on_detail_changed)

    def _on_detail_changed(self, *_args) -> None:
        if self._updating_detail:
            return
        self._mark_dirty(True)

    def _mark_dirty(self, dirty: bool) -> None:
        self._detail_dirty = dirty
        if self.unsaved_badge:
            self.unsaved_badge.set_visible(dirty)
        if self.detail_save_button:
            self.detail_save_button.set_sensitive(dirty)
        if self.detail_revert_button:
            self.detail_revert_button.set_sensitive(dirty)

    def _set_detail_sensitive(self, enabled: bool) -> None:
        widgets = [
            self.detail_title_row,
            self.detail_username_row,
            self.detail_password_row,
            self.detail_url_row,
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
    def refresh_account_profile(self, user_info: UserInfoUpdate) -> None:
        self.user_info.update(user_info)
        if self.vault_row:
            self.vault_row.set_title(self._vault_title())
        if self.user_name_label:
            self.user_name_label.set_label(self.user_info.get("username", "?"))
        if self.user_avatar:
            self.user_avatar.set_text(self.user_info.get("username", "?")[:2].upper())

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

    def _vault_title(self) -> str:
        username = self.user_info.get("username", "?")
        return _("%(username)s's vault") % {"username": username}

    def _require_detail_rows(
        self,
    ) -> tuple[
        Adw.EntryRow,
        Adw.EntryRow,
        Adw.PasswordEntryRow,
        Adw.EntryRow,
        Adw.EntryRow,
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
                Adw.EntryRow,
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
