"""Tests unitaires du dashboard securite premium."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.models.password_entry import PasswordEntry
from src.services.password_strength_service import PasswordStrengthService
from src.services.security_audit_service import SecurityAuditService
from src.ui.windows.security_dashboard_window import (
    SecurityDashboardWindow,
    compute_top_risk_entries,
    load_score_history,
    record_security_score,
)


def _entry(entry_id: int, password: str, *, score: int = -1) -> PasswordEntry:
    return PasswordEntry(
        id=entry_id,
        title=f"Entry {entry_id}",
        username="user",
        password=password,
        strength_score=score,
        modified_at=datetime.now() - timedelta(days=5),
        password_validity_days=90,
    )


def test_compute_top_risk_score_composite() -> None:
    strength = PasswordStrengthService()
    entries = [
        _entry(1, "password", score=0),
        _entry(2, "sharedStrong1!", score=3),
        _entry(3, "sharedStrong1!", score=3),
        _entry(4, "medium", score=2),
    ]

    top = compute_top_risk_entries(
        entries,
        reused_ids={2, 3},
        expired_ids={1, 4},
        strength_service=strength,
    )

    assert len(top) >= 1
    assert top[0].entry.id == 1


def test_security_score_history_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "users.db"
    record_security_score(db_path, user_id=1, vault_uuid="vault-1", score=72)
    record_security_score(db_path, user_id=1, vault_uuid="vault-1", score=80)

    points = load_score_history(db_path, user_id=1, vault_uuid="vault-1", limit=30)
    assert len(points) == 2
    assert points[0][1] == 72
    assert points[1][1] == 80


def test_security_dashboard_window_instantiation_no_crash(tmp_path: Path) -> None:
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    if not Gtk.init_check():
        pytest.skip("GTK display not available in test environment")

    strength = PasswordStrengthService()
    audit = SecurityAuditService(password_service=None, strength_service=strength)  # type: ignore[arg-type]

    parent = Gtk.Window()
    entries = [_entry(1, "password", score=0), _entry(2, "Strong#2026", score=4)]
    summary = audit.get_audit_summary(entries)

    win = SecurityDashboardWindow(
        parent=parent,
        entries=entries,
        audit_summary=summary,
        strength_service=strength,
        audit_service=audit,
        vault=None,
        user_info={"id": 1, "role": "admin"},
        users_db_path=tmp_path / "users.db",
        log_file=None,
    )
    win.close()
    parent.close()


def test_render_web_template_embeds_payload_inline(tmp_path: Path) -> None:
    strength = PasswordStrengthService()
    audit = SecurityAuditService(password_service=None, strength_service=strength)  # type: ignore[arg-type]

    obj = SecurityDashboardWindow.__new__(SecurityDashboardWindow)
    entries = [_entry(1, "password", score=0), _entry(2, "Strong#2026", score=4)]
    summary = audit.get_audit_summary(entries)

    obj.entries = entries
    obj.audit_summary = summary
    obj.strength_service = strength
    obj.audit_service = audit
    obj.vault = None
    obj.user_info = {"id": 1, "role": "admin"}
    obj.users_db_path = tmp_path / "users.db"
    obj.log_file = None
    obj.score_counts = obj._compute_score_counts(entries)
    obj.strong_count = sum(obj.score_counts[level] for level in (3, 4))
    obj.category_scores = obj._compute_category_scores(entries)
    obj.expiration_rows = obj._compute_expiration_rows(entries)
    obj.global_score = obj._as_int(summary.get("global_score", 100), 100)
    obj.weak_count = obj._as_int(summary.get("weak_count", 0), 0)
    obj.reused_count = obj._as_int(summary.get("reused_count", 0), 0)
    obj.expired_count = obj._as_int(summary.get("expired_count", 0), 0)
    obj.history_points = []
    obj.top_risk = []

    payload = obj._build_web_payload()
    html = obj._render_web_template(payload)

    assert "const data = " in html
    assert '"global_score": 50' in html
    assert "fetch('data.json')" not in html
    assert "__PAYLOAD__" not in html
