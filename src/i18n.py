"""Internationalisation (i18n) via gettext.

Objectif: permettre l'externalisation progressive des chaînes UI sans changer l'UX.
Par défaut (fallback), les chaînes restent inchangées.
"""

from __future__ import annotations

import gettext
import locale
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DOMAIN = "passwordmanager"
DEFAULT_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

_translation: gettext.NullTranslations | gettext.GNUTranslations = gettext.NullTranslations()


def _(message: str) -> str:
    return _translation.gettext(message)


def init_i18n(
    *, domain: str = DEFAULT_DOMAIN, localedir: Path | None = None
) -> Callable[[str], str]:
    """Initialise gettext.

    Ne lève pas d'exception: en cas de problème, utilise un fallback "no-op".

    Returns:
        Callable[[str], str]: la fonction de traduction `_`.
    """

    global _translation

    try:
        locale.setlocale(locale.LC_ALL, "")
    except Exception as exc:
        logger.debug("Impossible de définir la locale système: %s", exc)

    locales_dir = localedir or DEFAULT_LOCALES_DIR

    try:
        _translation = gettext.translation(domain, localedir=str(locales_dir), fallback=True)
    except Exception as exc:
        logger.debug(
            "Chargement gettext impossible (domain=%s, dir=%s): %s", domain, locales_dir, exc
        )
        _translation = gettext.NullTranslations()

    return _
