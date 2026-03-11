"""Tests unitaires du service de score de force des mots de passe."""

from __future__ import annotations

from src.services.password_strength_service import (
    PasswordStrengthService,
    STRENGTH_COLORS,
    STRENGTH_LABELS,
)


def test_empty_password_score_zero() -> None:
    service = PasswordStrengthService()
    result = service.evaluate("")
    assert result["score"] == 0


def test_common_password_forced_to_zero() -> None:
    service = PasswordStrengthService()
    result = service.evaluate("password")
    assert result["score"] == 0


def test_correct_horse_battery_staple_score_four() -> None:
    service = PasswordStrengthService()
    result = service.evaluate("correct-horse-battery-staple")
    assert result["score"] == 4


def test_score_mapping_is_consistent() -> None:
    service = PasswordStrengthService()
    probes = [
        "a",
        "P@ssw0rd!",
        "correct-horse-battery-staple",
        "Z7v!kL2q$N9m@R1t",
    ]

    for probe in probes:
        result = service.evaluate(probe)
        score = int(result["score"])
        assert result["color"] == STRENGTH_COLORS[score]
        assert result["label"] == STRENGTH_LABELS[score]
