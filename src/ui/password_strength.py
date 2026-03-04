"""Utilitaires UI pour évaluer et afficher la robustesse d'un mot de passe."""

from __future__ import annotations

from src.i18n import _


def evaluate_password_strength(password: str) -> tuple[int, str, str]:
    """Retourne (score, libellé, classe CSS) pour un mot de passe.

    score: 0..4
    classe CSS: success | warning | error
    """
    if not password:
        return (0, _("None"), "error")

    score = 0
    length = len(password)

    if length >= 12:
        score += 2
    elif length >= 8:
        score += 1

    has_lower = any(char.islower() for char in password)
    has_upper = any(char.isupper() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_special = any(not char.isalnum() for char in password)

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
