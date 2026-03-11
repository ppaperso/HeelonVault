"""Tests unitaires du service d'audit securite."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.models.password_entry import PasswordEntry
from src.services.security_audit_service import SecurityAuditService


class _StubStrengthService:
    def evaluate(self, password: str) -> dict[str, object]:
        score_map = {
            "weak": 0,
            "strong": 4,
            "shared": 3,
            "expired": 3,
        }
        return {"score": score_map.get(password, 2)}


def _service() -> SecurityAuditService:
    return SecurityAuditService(password_service=None, strength_service=_StubStrengthService())  # type: ignore[arg-type]


def test_empty_vault_summary_defaults() -> None:
    summary = _service().get_audit_summary([])
    assert summary["weak_count"] == 0
    assert summary["reused_count"] == 0
    assert summary["expired_count"] == 0
    assert summary["global_score"] == 100


def test_reused_passwords_count_two() -> None:
    entries = [
        PasswordEntry(id=1, title="A", username="u", password="shared"),
        PasswordEntry(id=2, title="B", username="u", password="shared"),
    ]
    summary = _service().get_audit_summary(entries)
    assert summary["reused_count"] == 2


def test_expired_entry_count_one() -> None:
    entries = [
        PasswordEntry(
            id=1,
            title="A",
            username="u",
            password="strong",
            password_validity_days=30,
            modified_at=datetime.now() - timedelta(days=31),
        )
    ]
    summary = _service().get_audit_summary(entries)
    assert summary["expired_count"] == 1


def test_weak_entry_count_one() -> None:
    entries = [
        PasswordEntry(id=1, title="A", username="u", password="weak"),
    ]
    summary = _service().get_audit_summary(entries)
    assert summary["weak_count"] == 1


def test_global_score_calculation() -> None:
    entries = [
        PasswordEntry(id=1, title="A", username="u", password="strong"),
        PasswordEntry(id=2, title="B", username="u", password="strong"),
        PasswordEntry(id=3, title="C", username="u", password="weak"),
        PasswordEntry(id=4, title="D", username="u", password="weak"),
    ]
    summary = _service().get_audit_summary(entries)
    assert summary["global_score"] == 50
