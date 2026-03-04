"""Dialogue 'À propos' de l'application."""

import os
from pathlib import Path

import gi  # type: ignore[import]

from src.i18n import _
from src.version import __app_name__, get_version_info

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


def show_about_dialog(parent):
    """Affiche le dialogue À propos avec branding premium."""
    version_info = get_version_info()

    window = Adw.Window()
    window.set_transient_for(parent)
    window.set_modal(True)
    window.set_default_size(560, 360)
    window.set_resizable(False)
    window.set_title(_("About"))

    version_text = version_info["version"]
    if os.environ.get("DEV_MODE", "").lower() in ("1", "true", "yes"):
        version_text += _(" (Development mode)")

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    root.set_margin_start(20)
    root.set_margin_end(20)
    root.set_margin_top(20)
    root.set_margin_bottom(20)

    branding = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    branding.set_css_classes(["card", "sidebar-branding"])
    branding.set_margin_start(4)
    branding.set_margin_end(4)
    branding.set_margin_top(4)
    branding.set_margin_bottom(4)

    ui_dir = Path(__file__).resolve().parents[1]
    logo_path = ui_dir / "assets" / "images" / "Logo_Heelonys_transparent.png"
    if not logo_path.exists():
        root_dir = Path(__file__).resolve().parents[3]
        logo_path = root_dir / "assets" / "images" / "Logo_Heelonys_transparent.png"

    if logo_path.exists():
        logo = Gtk.Picture.new_for_filename(str(logo_path))
        logo.set_content_fit(Gtk.ContentFit.CONTAIN)
        logo.set_size_request(40, 40)
        logo.set_can_shrink(True)
        logo.set_css_classes(["sidebar-brand-logo"])
    else:
        logo = Gtk.Image.new_from_icon_name("security-high-symbolic")
        logo.set_pixel_size(32)
        logo.set_css_classes(["sidebar-brand-logo"])
    branding.append(logo)

    title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    title_box.set_hexpand(True)

    app_name = Gtk.Label(label=__app_name__, xalign=0)
    app_name.set_css_classes(["sidebar-brand-title"])
    title_box.append(app_name)

    version_label = Gtk.Label(label=_("Version %s") % version_text, xalign=0)
    version_label.set_css_classes(["caption", "dim-label"])
    title_box.append(version_label)

    branding.append(title_box)
    root.append(branding)

    description_enrichie = _(
        """Secure password manager for Linux

🔒 AES-256-GCM encryption • Multi-user management
📥 CSV import/export • 🎲 Secure generator
🏷️ Organization by categories and tags"""
    )

    description = Gtk.Label(label=description_enrichie, xalign=0)
    description.set_wrap(True)
    description.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    description.set_css_classes(["body"])
    root.append(description)

    details = Gtk.Label(
        label=_("Developed by %(author)s\n%(copyright)s\nMIT License")
        % {
            "author": version_info["author"],
            "copyright": version_info["copyright"],
        },
        xalign=0,
    )
    details.set_wrap(True)
    details.set_css_classes(["caption", "dim-label"])
    root.append(details)

    close_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    close_row.set_halign(Gtk.Align.END)
    close_button = Gtk.Button(label=_("Close"))
    close_button.set_css_classes(["suggested-action"])
    close_button.connect("clicked", lambda _btn: window.close())
    close_row.append(close_button)
    root.append(close_row)

    window.set_content(root)
    window.present()
