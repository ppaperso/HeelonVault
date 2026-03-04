"""Dialogue d'exportation des mots de passe vers CSV."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import gi  # type: ignore[import]

from src.i18n import _
from src.services.csv_exporter import CSVExporter
from src.services.master_password_validator import MasterPasswordValidator
from src.services.password_service import PasswordService
from src.ui.notifications import toast as show_toast

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


def _password_policy_guidance_text() -> str:
    return _(
           "Minimum requirements: 12+ characters, "
           "or 10+ with uppercase, lowercase, digit, and symbol.\n"
           "Recommended (CNIL): prefer 12 characters or more."
    )


def _password_policy_checklist_text(password: str) -> str:
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(not c.isalnum() and not c.isspace() for c in password)
    checklist = [
           f"{'✅' if len(password) >= 10 else '•'} 10+ characters",
           f"{'✅' if has_upper else '•'} 1 uppercase",
           f"{'✅' if has_lower else '•'} 1 lowercase",
           f"{'✅' if has_digit else '•'} 1 digit",
           f"{'✅' if has_special else '•'} 1 symbol",
    ]
    return " | ".join(checklist)


class ExportCSVDialog(Adw.Window):
    """Dialogue permettant d'exporter le coffre vers un ZIP chiffré."""

    def __init__(
        self,
        parent,
        password_service: PasswordService,
        csv_exporter: CSVExporter,
        on_export_done=None,
    ):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title(_("Export to encrypted ZIP"))
        self.set_default_size(640, 660)

        self.parent_window = parent
        self.password_service = password_service
        self.csv_exporter = csv_exporter
        self.on_export_done = on_export_done
        self.selected_file: Path | None = None
        self._is_exporting = False

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        main_box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)

        title_label = Gtk.Label(label=_("Export passwords"))
        title_label.set_css_classes(["title-2"])
        title_label.set_xalign(0)
        content.append(title_label)

        desc_label = Gtk.Label(
            label=_(
                "Exports all entries from the current vault into a password-protected "
                "encrypted ZIP file (the ZIP contains a CSV)."
            )
        )
        desc_label.set_wrap(True)
        desc_label.set_xalign(0)
        desc_label.set_css_classes(["dim-label"])
        content.append(desc_label)

        file_group = Adw.PreferencesGroup()
        file_group.set_title(_("Destination file"))

        file_row = Adw.ActionRow()
        file_row.set_title(_("Destination"))
        file_row.set_subtitle(_("Choose where to save the ZIP archive"))

        select_button = Gtk.Button(label=_("Choose location"))
        select_button.set_valign(Gtk.Align.CENTER)
        select_button.connect("clicked", self.on_select_file_clicked)
        self.select_button = select_button
        file_row.add_suffix(select_button)

        self.file_label = Gtk.Label(label=_("No file selected"))
        self.file_label.set_css_classes(["caption", "dim-label"])
        self.file_label.set_xalign(0)
        self.file_label.set_margin_top(5)

        file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        file_box.append(file_row)
        file_box.append(self.file_label)
        file_group.add(file_box)
        content.append(file_group)

        security_group = Adw.PreferencesGroup()
        security_group.set_title(_("Security"))

        password_row = Adw.ActionRow()
        password_row.set_title(_("ZIP archive password"))
        password_row.set_subtitle(_("Required to open the exported ZIP archive"))
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.set_tooltip_text(
            _("Enter the ZIP archive password")
        )
        self.password_entry.connect("changed", self._on_security_input_changed)
        password_row.add_suffix(self.password_entry)
        security_group.add(password_row)

        confirm_row = Adw.ActionRow()
        confirm_row.set_title(_("Confirm ZIP archive password"))
        self.password_confirm_entry = Gtk.PasswordEntry()
        self.password_confirm_entry.set_show_peek_icon(True)
        self.password_confirm_entry.set_tooltip_text(
            _("Confirm the ZIP archive password")
        )
        self.password_confirm_entry.connect("changed", self._on_security_input_changed)
        confirm_row.add_suffix(self.password_confirm_entry)
        security_group.add(confirm_row)

        self.password_rules_label = Gtk.Label(
            label=_password_policy_guidance_text(),
            xalign=0,
        )
        self.password_rules_label.set_wrap(True)
        self.password_rules_label.set_css_classes(["caption", "dim-label"])
        security_group.add(self.password_rules_label)

        self.password_hint_label = Gtk.Label(label="", xalign=0)
        self.password_hint_label.set_css_classes(["caption", "dim-label"])
        security_group.add(self.password_hint_label)

        self.password_strength_label = Gtk.Label(label="", xalign=0)
        self.password_strength_label.set_css_classes(["caption", "dim-label"])
        security_group.add(self.password_strength_label)

        self.password_checklist_label = Gtk.Label(label="", xalign=0)
        self.password_checklist_label.set_wrap(True)
        self.password_checklist_label.set_css_classes(["caption", "dim-label"])
        security_group.add(self.password_checklist_label)

        content.append(security_group)

        options_group = Adw.PreferencesGroup()
        options_group.set_title(_("Options"))

        self.include_header_switch = Adw.SwitchRow()
        self.include_header_switch.set_title(_("Include header row"))
        self.include_header_switch.set_active(True)
        options_group.add(self.include_header_switch)

        delimiter_row = Adw.ComboRow()
        delimiter_row.set_title(_("Delimiter"))
        delimiter_model = Gtk.StringList()
        delimiter_model.append(_("Comma (,)"))
        delimiter_model.append(_("Semicolon (;)"))
        delimiter_row.set_model(delimiter_model)
        delimiter_row.set_selected(0)
        self.delimiter_row = delimiter_row
        options_group.add(delimiter_row)

        content.append(options_group)

        status_group = Adw.PreferencesGroup()
        status_group.set_title(_("Export status"))
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        status_box.set_margin_start(8)
        status_box.set_margin_end(8)
        status_box.set_margin_top(4)
        status_box.set_margin_bottom(4)

        status_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_spinner = Gtk.Spinner()
        self.status_spinner.set_visible(False)
        status_top.append(self.status_spinner)

        self.status_title_label = Gtk.Label(label="", xalign=0)
        self.status_title_label.set_css_classes(["heading"])
        status_top.append(self.status_title_label)
        status_box.append(status_top)

        self.status_detail_label = Gtk.Label(label="", xalign=0)
        self.status_detail_label.set_wrap(True)
        self.status_detail_label.set_css_classes(["caption", "dim-label"])
        status_box.append(self.status_detail_label)
        status_group.add(status_box)
        content.append(status_group)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)

        cancel_button = Gtk.Button(label=_("Cancel"))
        cancel_button.connect("clicked", lambda _b: self.close())
        self.cancel_button = cancel_button
        button_box.append(cancel_button)

        self.export_button = Gtk.Button(label=_("Export"))
        self.export_button.set_css_classes(["suggested-action"])
        self.export_button.set_sensitive(False)
        self.export_button.connect("clicked", self.on_export_clicked)
        button_box.append(self.export_button)

        content.append(button_box)
        main_box.append(content)
        self.set_content(main_box)
        self._set_status(
            "info",
            _("Waiting"),
            _("Configure export settings, then click Export."),
        )

    def _set_status(self, status_type: str, title: str, detail: str, *, busy: bool = False):
        self.status_title_label.set_text(title)
        self.status_detail_label.set_text(detail)

        self.status_title_label.remove_css_class("success")
        self.status_title_label.remove_css_class("warning")
        self.status_title_label.remove_css_class("error")
        self.status_detail_label.remove_css_class("success")
        self.status_detail_label.remove_css_class("warning")
        self.status_detail_label.remove_css_class("error")
        self.status_detail_label.add_css_class("dim-label")

        if status_type in ("success", "warning", "error"):
            self.status_title_label.add_css_class(status_type)
            self.status_detail_label.add_css_class(status_type)

        self.status_spinner.set_visible(busy)
        if busy:
            self.status_spinner.start()
        else:
            self.status_spinner.stop()

    def _set_exporting(self, exporting: bool):
        self._is_exporting = exporting
        self.select_button.set_sensitive(not exporting)
        self.password_entry.set_sensitive(not exporting)
        self.password_confirm_entry.set_sensitive(not exporting)
        self.include_header_switch.set_sensitive(not exporting)
        self.delimiter_row.set_sensitive(not exporting)
        self.cancel_button.set_sensitive(not exporting)
        if exporting:
            self.export_button.set_sensitive(False)
            self.export_button.set_label(_("Exporting..."))
        else:
            self.export_button.set_label(_("Export"))
            self._update_export_button_state()

    def on_select_file_clicked(self, _button):
        """Ouvre un sélecteur pour choisir le fichier de sortie."""
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title(_("Export to encrypted ZIP archive"))

        zip_filter = Gtk.FileFilter()
        zip_filter.set_name(_("ZIP archives"))
        zip_filter.add_pattern("*.zip")

        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All files"))
        all_filter.add_pattern("*")

        filter_list = Gio.ListStore.new(Gtk.FileFilter)
        filter_list.append(zip_filter)
        filter_list.append(all_filter)

        file_dialog.set_filters(filter_list)
        file_dialog.set_default_filter(zip_filter)

        suggested_name = f"heelonvault_export_{datetime.now().strftime('%Y%m%d')}.zip"
        file_dialog.set_initial_name(suggested_name)
        file_dialog.save(self, None, self.on_file_selected)

    def on_file_selected(self, dialog, result):
        """Callback après sélection du chemin de destination."""
        try:
            file = dialog.save_finish(result)
            if file and file.get_path():
                selected = Path(file.get_path())
                if selected.suffix.lower() != ".zip":
                    selected = selected.with_suffix(".zip")
                self.selected_file = selected
                self.file_label.set_label(str(selected))
                self._update_export_button_state()
                self._set_status(
                    "info",
                    _("Ready"),
                    _("Destination selected. You can now start secure export."),
                )
        except (OSError, ValueError, TypeError) as exc:
            logger.error("Export file selection error: %s", exc)
            self._set_status("error", _("Error"), str(exc))

    def _on_security_input_changed(self, _entry):
        if self._is_exporting:
            return
        self._update_export_button_state()

    def _update_export_button_state(self):
        password = self.password_entry.get_text()
        password_confirm = self.password_confirm_entry.get_text()

        if len(password) == 0:
            self.password_strength_label.set_text("")
            self.password_strength_label.set_css_classes(["caption", "dim-label"])
            self.password_checklist_label.set_text("")
            self.password_hint_label.set_label(_("ZIP archive password is required"))
            self.export_button.set_sensitive(False)
            return

        score = MasterPasswordValidator.validate(password)[2]
        strength = MasterPasswordValidator.get_strength_description(score)
        if score >= 80:
            self.password_strength_label.set_css_classes(["caption", "success"])
        elif score >= 60:
            self.password_strength_label.set_css_classes(["caption", "warning"])
        else:
            self.password_strength_label.set_css_classes(["caption", "error"])
        self.password_strength_label.set_text(f"Strength: {strength} ({score}/100)")
        self.password_checklist_label.set_text(_password_policy_checklist_text(password))

        if password != password_confirm:
            self.password_hint_label.set_label(
                _("ZIP archive passwords do not match")
            )
            self.export_button.set_sensitive(False)
            return

        is_valid, errors, _score_unused = MasterPasswordValidator.validate(password)
        if not is_valid:
            self.password_hint_label.set_label(
                errors[0]
                if errors
                else _("Password does not meet minimum requirements")
            )
            self.export_button.set_sensitive(False)
            return

        self.password_hint_label.set_label(
            _("Minimum requirements met • ZIP archive protected with password (AES)")
        )
        self.export_button.set_sensitive(self.selected_file is not None)

    def on_export_clicked(self, _button):
        """Exécute l'export ZIP chiffré."""
        if not self.selected_file:
            self._set_status(
                "warning",
                _("Action required"),
                _("Choose a destination file."),
            )
            return

        password = self.password_entry.get_text()
        password_confirm = self.password_confirm_entry.get_text()
        if password != password_confirm:
            self._update_export_button_state()
            self._set_status(
                "warning",
                _("Verification required"),
                _("ZIP archive passwords do not match."),
            )
            return

        is_valid, errors, _score_unused = MasterPasswordValidator.validate(password)
        if not is_valid:
            self._update_export_button_state()
            detail = (
                errors[0]
                if errors
                else _("Password does not meet minimum requirements")
            )
            self._set_status("warning", _("Verification required"), detail)
            return

        entries = self.password_service.list_entries()
        if not entries:
            self._set_status(
                "warning",
                _("Export unavailable"),
                _("No entries to export in the current vault."),
            )
            return

        self._set_exporting(True)
        self._set_status(
            "info",
            _("Export in progress"),
            _("Encrypting archive and writing file..."),
            busy=True,
        )

        from gi.repository import GLib

        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

        include_header = self.include_header_switch.get_active()
        delimiter = ";" if self.delimiter_row.get_selected() == 1 else ","

        result = self.csv_exporter.export_to_encrypted_zip(
            self.selected_file,
            entries,
            password=password,
            delimiter=delimiter,
            include_header=include_header,
        )

        self._set_exporting(False)

        if result.get("success"):
            raw_count = result.get("exported_count", 0)
            exported_count = int(raw_count) if raw_count is not None else 0
            exported_path = str(result.get("file_path", self.selected_file))
            self._set_status(
                "success",
                _("Export successful"),
                _("%(count)s entries successfully exported to:\n%(path)s")
                % {"count": exported_count, "path": exported_path},
            )
            show_toast(
                self.parent_window,
                _("✅ Secure export completed (%(count)s entries)") % {"count": exported_count},
            )
            if callable(self.on_export_done):
                self.on_export_done()
            return

        error_text = str(result.get("error", "unknown"))
        self._set_status(
            "error",
            _("Export failed"),
            _("Unable to export encrypted archive:\n%(error)s") % {"error": error_text},
        )
        show_toast(self.parent_window, _("❌ Secure export failed"))
