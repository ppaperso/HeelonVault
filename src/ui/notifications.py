"""Helpers UI pour notifications cohérentes.

Centralise:
- Toasts Adw
- MessageDialog (erreurs/informations)

But: éviter la dispersion (print(), dialogs ad-hoc) et rendre l'i18n simple.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.i18n import _

import gi  # type: ignore[import]

gi.require_version("Adw", "1")
from gi.repository import Adw  # type: ignore[attr-defined]  # noqa: E402

logger = logging.getLogger(__name__)


def toast(parent, message: str, *, timeout: int = 3) -> bool:
    """Affiche un toast si la fenêtre supporte un toast overlay."""

    try:
        overlay = getattr(parent, "toast_overlay", None)
        if overlay is None:
            return False
        toast_obj = Adw.Toast.new(message)
        try:
            toast_obj.set_timeout(timeout)
        except Exception:
            pass
        overlay.add_toast(toast_obj)
        return True
    except Exception as exc:
        logger.debug("Impossible d'afficher un toast: %s", exc)
        return False


def message_dialog(parent, *, heading: str, body: str, ok_label: Optional[str] = None) -> None:
    dialog = Adw.MessageDialog.new(parent)
    dialog.set_heading(heading)
    dialog.set_body(body)
    dialog.add_response("ok", ok_label or _("OK"))
    dialog.present()


def error(parent, body: str, *, heading: Optional[str] = None) -> None:
    """Erreur critique: affiche un dialog."""

    message_dialog(parent, heading=heading or _("Erreur"), body=body)


def info(parent, body: str, *, heading: Optional[str] = None) -> None:
    message_dialog(parent, heading=heading or _("Information"), body=body)
