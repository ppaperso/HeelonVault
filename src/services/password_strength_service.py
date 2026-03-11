"""Service d'evaluation de robustesse des mots de passe."""

from __future__ import annotations

import math
from pathlib import Path

from src.i18n import N_, _

try:
    from zxcvbn import zxcvbn
except ImportError:  # pragma: no cover - handled by graceful fallback
    zxcvbn = None

STRENGTH_COLORS = {
    0: "#E53935",  # rouge - tres faible
    1: "#FB8C00",  # orange - faible
    2: "#FDD835",  # jaune - moyen
    3: "#43A047",  # vert - fort
    4: "#13A1A1",  # teal - tres fort (charte HeelonVault)
}

STRENGTH_LABELS = {
    0: N_("Very weak"),
    1: N_("Weak"),
    2: N_("Fair"),
    3: N_("Strong"),
    4: N_("Very strong"),
}


class PasswordStrengthService:
    """Centralise l'evaluation de la force de mot de passe pour l'UI."""

    def __init__(self, common_passwords_path: Path | None = None) -> None:
        data_file = common_passwords_path or (
            Path(__file__).resolve().parents[1] / "data" / "common_passwords.txt"
        )
        self._common_passwords = self._load_common_passwords(data_file)

    def evaluate(self, password: str) -> dict[str, object]:
        """Retourne score/couleur/libelle/entropie/feedback/crack_time."""
        if not password:
            return self._build_result(
                score=0,
                entropy=0.0,
                feedback=[],
                crack_time=_("instantly"),
            )

        lowered = password.lower()
        if lowered in self._common_passwords:
            return self._build_result(
                score=0,
                entropy=0.0,
                feedback=[_("This password is in the most common passwords list")],
                crack_time=_("instantly"),
            )

        if zxcvbn is None:
            # Fallback minimal if dependency is unavailable at runtime.
            return self._build_result(
                score=0,
                entropy=0.0,
                feedback=[_("Password strength engine unavailable")],
                crack_time=_("unknown"),
            )

        analysis = zxcvbn(password)
        score = int(analysis.get("score", 0))

        guesses = float(analysis.get("guesses", 0.0) or 0.0)
        entropy = math.log2(max(1.0, guesses))

        feedback: list[str] = []
        feedback_data = analysis.get("feedback", {})
        if isinstance(feedback_data, dict):
            warning = feedback_data.get("warning")
            if isinstance(warning, str) and warning.strip():
                feedback.append(warning.strip())
            suggestions = feedback_data.get("suggestions", [])
            if isinstance(suggestions, list):
                feedback.extend(
                    suggestion.strip()
                    for suggestion in suggestions
                    if isinstance(suggestion, str) and suggestion.strip()
                )

        crack_times = analysis.get("crack_times_display", {})
        crack_time = _("unknown")
        if isinstance(crack_times, dict):
            crack_time = str(
                crack_times.get("offline_slow_hashing_1e4_per_second")
                or crack_times.get("offline_fast_hashing_1e10_per_second")
                or crack_times.get("online_no_throttling_10_per_second")
                or crack_times.get("online_throttling_100_per_hour")
                or _("unknown")
            )

        return self._build_result(
            score=max(0, min(score, 4)),
            entropy=entropy,
            feedback=feedback,
            crack_time=crack_time,
        )

    @staticmethod
    def _load_common_passwords(path: Path) -> set[str]:
        if not path.exists():
            return set()
        with path.open("r", encoding="utf-8") as handle:
            return {
                line.strip().lower()
                for line in handle
                if line.strip() and not line.startswith("#")
            }

    def _build_result(
        self,
        *,
        score: int,
        entropy: float,
        feedback: list[str],
        crack_time: str,
    ) -> dict[str, object]:
        normalized_score = max(0, min(score, 4))
        return {
            "score": normalized_score,
            "color": STRENGTH_COLORS[normalized_score],
            "label": _(STRENGTH_LABELS[normalized_score]),
            "entropy": entropy,
            "feedback": feedback,
            "crack_time": crack_time,
        }
