from __future__ import annotations

from typing import Callable, Iterable, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

ResponseList = Iterable[Tuple[str, str]]


def present_alert(
    parent: Gtk.Widget,
    title: str,
    body: str,
    responses: ResponseList,
    *,
    default: Optional[str] = None,
    destructive: Optional[str] = None,
    close: Optional[str] = None,
    on_response: Optional[Callable[[str], None]] = None,
) -> Adw.AlertDialog:
    """Create and present an Adw.AlertDialog with consistent defaults."""
    dialog = Adw.AlertDialog.new(title, body)

    for response_id, label in responses:
        dialog.add_response(response_id, label)

    if default:
        dialog.set_default_response(default)
    if close:
        dialog.set_close_response(close)
    if destructive:
        dialog.set_response_appearance(destructive, Adw.ResponseAppearance.DESTRUCTIVE)

    if on_response:
        dialog.connect("response", lambda _dialog, response: on_response(response))

    dialog.present(parent)
    return dialog
