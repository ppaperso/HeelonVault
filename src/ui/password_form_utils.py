"""Utilitaires partagés pour les formulaires de mot de passe."""

import gi  # type: ignore[import]

from src.i18n import _
from src.services.master_password_validator import MasterPasswordValidator

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402


def _validate_password_rules(password: str, confirm: str) -> str | None:
    if not password:
        return _("Password is required")
    if password != confirm:
        return _("Passwords do not match")
    is_valid, errors, _score = MasterPasswordValidator.validate(password)
    if not is_valid:
        if errors:
            return errors[0]
        return _("Password does not meet minimum requirements")
    return None


def _password_policy_guidance_text() -> str:
    return _(
        "Minimum requirements: 12+ characters, "
        "or 10+ with uppercase, lowercase, digit, and symbol.\n"
        "Recommended (CNIL): prefer 12 characters or more."
    )


def _password_policy_checklist_text(password: str) -> str:
    has_lower = any(char.islower() for char in password)
    has_upper = any(char.isupper() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_special = any(not char.isalnum() and not char.isspace() for char in password)

    checklist = [
        f"{'✅' if len(password) >= 10 else '•'} 10+ characters",
        f"{'✅' if has_upper else '•'} 1 uppercase",
        f"{'✅' if has_lower else '•'} 1 lowercase",
        f"{'✅' if has_digit else '•'} 1 digit",
        f"{'✅' if has_special else '•'} 1 symbol",
    ]
    return " | ".join(checklist)


def apply_new_password_feedback(
    password: str,
    strength_label: Gtk.Label,
    checklist_label: Gtk.Label,
) -> None:
    """Met à jour les widgets de feedback de robustesse et checklist."""
    if len(password) == 0:
        strength_label.set_text("")
        strength_label.set_css_classes(["caption", "dim-label"])
        checklist_label.set_text("")
        return

    _, _, score = MasterPasswordValidator.validate(password)
    strength = MasterPasswordValidator.get_strength_description(score)

    if score >= 80:
        strength_label.set_css_classes(["caption", "success"])
    elif score >= 60:
        strength_label.set_css_classes(["caption", "warning"])
    else:
        strength_label.set_css_classes(["caption", "error"])

    strength_label.set_text(f"Strength: {strength} ({score}/100)")
    checklist_label.set_text(_password_policy_checklist_text(password))
