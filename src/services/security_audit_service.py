"""Service d'audit securite pour les entrees de mots de passe."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from src.models.password_entry import PasswordEntry
from src.services.password_service import PasswordService
from src.services.password_strength_service import PasswordStrengthService


class SecurityAuditService:
    """Calcule des indicateurs de securite sur un jeu d'entrees."""

    def __init__(
        self,
        password_service: PasswordService,
        strength_service: PasswordStrengthService,
    ) -> None:
        self.password_service = password_service
        self.strength_service = strength_service

    def get_audit_summary(self, entries: list[PasswordEntry]) -> dict[str, object]:
        """Retourne un resume securite exploitable par l'UI."""
        weak_ids: set[int] = set()
        reused_ids: set[int] = set()
        expired_ids: set[int] = set()

        if not entries:
            return {
                "weak_count": 0,
                "reused_count": 0,
                "expired_count": 0,
                "global_score": 100,
                "weak_ids": weak_ids,
                "reused_ids": reused_ids,
                "expired_ids": expired_ids,
            }

        password_groups: dict[str, list[int]] = {}
        strong_count = 0
        now = datetime.now()
        soon_threshold = now + timedelta(days=7)

        for entry in entries:
            entry_id = entry.id
            if isinstance(entry_id, int):
                password_hash = hashlib.sha256(entry.password.encode("utf-8")).hexdigest()
                password_groups.setdefault(password_hash, []).append(entry_id)

            score = entry.strength_score
            if score < 0:
                result = self.strength_service.evaluate(entry.password)
                score_raw = result.get("score", 0)
                score = score_raw if isinstance(score_raw, int) else 0

            if score <= 1 and isinstance(entry_id, int):
                weak_ids.add(entry_id)
            if score >= 3:
                strong_count += 1

            if not isinstance(entry_id, int):
                continue
            validity_days = entry.password_validity_days
            if not validity_days or validity_days <= 0:
                continue

            base_date = entry.modified_at or entry.created_at
            if not base_date:
                continue

            expires_at = base_date + timedelta(days=validity_days)
            if expires_at <= soon_threshold:
                expired_ids.add(entry_id)

        for group_ids in password_groups.values():
            if len(group_ids) > 1:
                reused_ids.update(group_ids)

        global_score = round((strong_count / len(entries)) * 100) if entries else 100

        return {
            "weak_count": len(weak_ids),
            "reused_count": len(reused_ids),
            "expired_count": len(expired_ids),
            "global_score": global_score,
            "weak_ids": weak_ids,
            "reused_ids": reused_ids,
            "expired_ids": expired_ids,
        }
