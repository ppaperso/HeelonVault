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
from typing import Final, TypedDict

logger = logging.getLogger(__name__)

DEFAULT_DOMAIN = "heelonvault"
DEFAULT_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

_translation: gettext.NullTranslations | gettext.GNUTranslations = gettext.NullTranslations()


class LanguageMeta(TypedDict):
    """Metadata used to render language selectors in UI."""

    code: str
    emoji: str
    native_name: str


SUPPORTED_LANGUAGES: Final[dict[str, LanguageMeta]] = {
    "en": {"code": "en", "emoji": "🇬🇧", "native_name": "English"},
    "fr": {"code": "fr", "emoji": "🇫🇷", "native_name": "Français"},
    "de": {"code": "de", "emoji": "🇩🇪", "native_name": "Deutsch"},
    "it": {"code": "it", "emoji": "🇮🇹", "native_name": "Italiano"},
}

DEFAULT_LANGUAGE: Final[str] = "en"
_active_language: str = DEFAULT_LANGUAGE


def _(message: str) -> str:
    return _translation.gettext(message)


def normalize_language(language: str | None) -> str:
    """Normalize an input language code to one of the supported languages."""
    if not language:
        return DEFAULT_LANGUAGE

    normalized = language.strip().lower().split("_")[0].split("-")[0]
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def get_supported_languages() -> list[LanguageMeta]:
    """Return supported languages in UI display order."""
    return [
        SUPPORTED_LANGUAGES["en"],
        SUPPORTED_LANGUAGES["fr"],
        SUPPORTED_LANGUAGES["de"],
        SUPPORTED_LANGUAGES["it"],
    ]


def get_active_language() -> str:
    """Return the currently active language code."""
    return _active_language


def init_i18n(
    *,
    domain: str = DEFAULT_DOMAIN,
    localedir: Path | None = None,
    language: str | None = None,
) -> Callable[[str], str]:
    """Initialise gettext.

    Ne lève pas d'exception: en cas de problème, utilise un fallback "no-op".

    Returns:
        Callable[[str], str]: la fonction de traduction `_`.
    """

    global _translation, _active_language

    try:
        locale.setlocale(locale.LC_ALL, "")
    except Exception as exc:
        logger.debug("Unable to set system locale: %s", exc)

    locales_dir = localedir or DEFAULT_LOCALES_DIR
    resolved_language = normalize_language(language)

    try:
        _translation = gettext.translation(
            domain,
            localedir=str(locales_dir),
            languages=[resolved_language],
            fallback=True,
        )
        _active_language = resolved_language
    except Exception as exc:
        logger.debug(
            "Unable to load gettext catalog (domain=%s, dir=%s, language=%s): %s",
            domain,
            locales_dir,
            resolved_language,
            exc,
        )
        _translation = gettext.NullTranslations()
        _active_language = DEFAULT_LANGUAGE

    return _


def set_language(
    language: str,
    *,
    domain: str = DEFAULT_DOMAIN,
    localedir: Path | None = None,
) -> str:
    """Switch active language and return the normalized language code."""
    resolved_language = normalize_language(language)
    init_i18n(domain=domain, localedir=localedir, language=resolved_language)
    return resolved_language
