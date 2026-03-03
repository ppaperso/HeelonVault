"""Service de protection contre les attaques par force brute.

Ce service gère :
- Le suivi des tentatives de connexion échouées
- Les délais progressifs après chaque échec
- Le verrouillage temporaire après trop de tentatives
- La journalisation des tentatives suspectes
- Rate limiting global pour éviter l'énumération d'emails
"""

import logging
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

# Configuration du logging
logger = logging.getLogger(__name__)


@dataclass
class LoginAttemptInfo:
    """Informations sur les tentatives de connexion pour un utilisateur."""
    failed_attempts: int = 0
    last_attempt_time: float = 0.0
    lockout_until: float | None = None


@dataclass
class GlobalAttemptTracker:
    """Suivi des tentatives globales (tous utilisateurs confondus)."""
    attempts_minute: list[float] = field(default_factory=list)
    attempts_hour: list[float] = field(default_factory=list)


class LoginAttemptTracker:
    """Gestionnaire de protection contre les attaques par force brute.

    Fonctionnalités :
    - Délai progressif : 1s, 2s, 4s, 8s, etc. après chaque échec
    - Verrouillage temporaire : 15 minutes après 5 tentatives échouées
    - Rate limiting global : 5 tentatives/minute, 30/heure (empêche énumération)
    - Journalisation des tentatives suspectes
    - Support email_hash et username (rétrocompatibilité)
    """

    # Configuration par utilisateur
    MAX_ATTEMPTS_BEFORE_LOCKOUT = 5
    LOCKOUT_DURATION_SECONDS = 900  # 15 minutes
    BASE_DELAY_SECONDS = 1  # Délai de base, doublé à chaque tentative
    MAX_DELAY_SECONDS = 32  # Délai maximum (32 secondes)

    # Configuration globale (empêche énumération d'emails)
    GLOBAL_MAX_ATTEMPTS_PER_MINUTE = 5
    GLOBAL_MAX_ATTEMPTS_PER_HOUR = 30

    def __init__(self, state_file: Path | None = None):
        """Initialise le tracker.

        Args:
            state_file: Fichier JSON de persistance des tentatives (optionnel)
        """
        self._attempts: dict[str, LoginAttemptInfo] = {}
        self._global_tracker = GlobalAttemptTracker()
        self._state_file = state_file
        self._load_state()
        logger.info("Service de protection anti-brute force initialisé (avec rate limiting global)")

    def _load_state(self):
        """Charge l'état persistant des tentatives depuis le disque."""
        if not self._state_file or not self._state_file.exists():
            return

        try:
            payload = json.loads(self._state_file.read_text(encoding="utf-8"))
            attempts: dict[str, LoginAttemptInfo] = {}

            for identifier, raw_info in payload.get("attempts", {}).items():
                attempts[identifier] = LoginAttemptInfo(
                    failed_attempts=int(raw_info.get("failed_attempts", 0)),
                    last_attempt_time=float(raw_info.get("last_attempt_time", 0.0)),
                    lockout_until=(
                        float(raw_info["lockout_until"])
                        if raw_info.get("lockout_until") is not None
                        else None
                    ),
                )

            global_data = payload.get("global", {})
            global_tracker = GlobalAttemptTracker(
                attempts_minute=[float(v) for v in global_data.get("attempts_minute", [])],
                attempts_hour=[float(v) for v in global_data.get("attempts_hour", [])],
            )

            self._attempts = attempts
            self._global_tracker = global_tracker

            now = time.time()
            self._clean_old_global_attempts(now)
            expired = [
                identifier
                for identifier, info in self._attempts.items()
                if info.lockout_until and info.lockout_until <= now
            ]
            for identifier in expired:
                del self._attempts[identifier]

        except Exception as exc:
            logger.warning("Impossible de charger l'état anti-brute force: %s", exc)

    def _save_state(self):
        """Sauvegarde l'état persistant des tentatives sur le disque."""
        if not self._state_file:
            return

        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "attempts": {
                    identifier: {
                        "failed_attempts": info.failed_attempts,
                        "last_attempt_time": info.last_attempt_time,
                        "lockout_until": info.lockout_until,
                    }
                    for identifier, info in self._attempts.items()
                },
                "global": {
                    "attempts_minute": self._global_tracker.attempts_minute,
                    "attempts_hour": self._global_tracker.attempts_hour,
                },
            }
            self._state_file.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            self._state_file.chmod(0o600)
        except Exception as exc:
            logger.warning("Impossible de sauvegarder l'état anti-brute force: %s", exc)

    def _clean_old_global_attempts(self, current_time: float):
        """Nettoie les anciennes tentatives globales.

        Args:
            current_time: Timestamp actuel
        """
        one_minute_ago = current_time - 60
        one_hour_ago = current_time - 3600

        # Nettoyer les tentatives de la dernière minute
        self._global_tracker.attempts_minute = [
            t for t in self._global_tracker.attempts_minute if t > one_minute_ago
        ]

        # Nettoyer les tentatives de la dernière heure
        self._global_tracker.attempts_hour = [
            t for t in self._global_tracker.attempts_hour if t > one_hour_ago
        ]
        self._save_state()

    def check_global_rate_limit(self) -> tuple[bool, int | None]:
        """Vérifie le rate limiting global (tous utilisateurs).

        Empêche de tester trop d'emails différents rapidement.

        Returns:
            Tuple (autorisé, secondes_restantes)
        """
        current_time = time.time()
        self._clean_old_global_attempts(current_time)

        # Vérifier la limite par minute
        if len(self._global_tracker.attempts_minute) >= self.GLOBAL_MAX_ATTEMPTS_PER_MINUTE:
            logger.warning(
                "⚠️  Rate limiting global: trop de tentatives par minute "
                "(%d/%d)",
                len(self._global_tracker.attempts_minute),
                self.GLOBAL_MAX_ATTEMPTS_PER_MINUTE,
            )
            return (False, 60)

        # Vérifier la limite par heure
        if len(self._global_tracker.attempts_hour) >= self.GLOBAL_MAX_ATTEMPTS_PER_HOUR:
            logger.warning(
                "🔒 Rate limiting global: trop de tentatives par heure (%d/%d)",
                len(self._global_tracker.attempts_hour),
                self.GLOBAL_MAX_ATTEMPTS_PER_HOUR,
            )
            return (False, 3600)

        return (True, None)

    def record_global_attempt(self):
        """Enregistre une tentative globale (avant vérification par utilisateur)."""
        current_time = time.time()
        self._global_tracker.attempts_minute.append(current_time)
        self._global_tracker.attempts_hour.append(current_time)
        self._save_state()

    def check_can_attempt(self, identifier: str) -> tuple[bool, int | None]:
        """Vérifie si une tentative de connexion est autorisée.

        Args:
            identifier: Nom d'utilisateur ou email_hash

        Returns:
            Tuple (peut_tenter, secondes_restantes):
            - peut_tenter: True si la tentative est autorisée
            - secondes_restantes: Nombre de secondes à attendre (si bloqué)
        """
        # D'abord vérifier le rate limiting global
        can_proceed, wait_time = self.check_global_rate_limit()
        if not can_proceed:
            return (False, wait_time)

        current_time = time.time()

        if identifier not in self._attempts:
            return (True, None)

        info = self._attempts[identifier]

        # Vérifier le verrouillage temporaire
        if info.lockout_until and current_time < info.lockout_until:
            remaining = int(info.lockout_until - current_time)
            logger.warning(
                "Tentative de connexion bloquée pour '%s...' (%ss restantes)",
                identifier[:16],
                remaining,
            )
            return (False, remaining)

        # Si le verrouillage est expiré, réinitialiser
        if info.lockout_until and current_time >= info.lockout_until:
            logger.info("Fin du verrouillage pour '%s...'", identifier[:16])
            self._reset_attempts(identifier)
            return (True, None)

        # Vérifier le délai progressif
        if info.failed_attempts > 0:
            delay = self._calculate_delay(info.failed_attempts)
            time_since_last = current_time - info.last_attempt_time

            if time_since_last < delay:
                remaining = int(delay - time_since_last)
                logger.debug(
                    "Délai anti-brute force actif pour '%s...' (%ss restantes)",
                    identifier[:16],
                    remaining,
                )
                return (False, remaining)

        return (True, None)

    def record_failed_attempt(self, identifier: str):
        """Enregistre une tentative de connexion échouée.

        Args:
            identifier: Nom d'utilisateur ou email_hash
        """
        current_time = time.time()

        # Enregistrer la tentative globale
        self.record_global_attempt()

        if identifier not in self._attempts:
            self._attempts[identifier] = LoginAttemptInfo()

        info = self._attempts[identifier]
        info.failed_attempts += 1
        info.last_attempt_time = current_time

        # Journalisation (masquer une partie de l'identifiant pour privacy)
        masked_id = identifier[:16] + "..." if len(identifier) > 16 else identifier
        logger.warning(
            "Tentative de connexion échouée pour '%s' (tentative %d/%d)",
            masked_id,
            info.failed_attempts,
            self.MAX_ATTEMPTS_BEFORE_LOCKOUT,
        )

        # Vérifier si verrouillage nécessaire
        if info.failed_attempts >= self.MAX_ATTEMPTS_BEFORE_LOCKOUT:
            info.lockout_until = current_time + self.LOCKOUT_DURATION_SECONDS
            logger.error(
                "🔒 VERROUILLAGE: Compte '%s' verrouillé pendant %d minutes "
                "(trop de tentatives échouées)",
                masked_id,
                self.LOCKOUT_DURATION_SECONDS // 60,
            )
        self._save_state()

    def record_successful_attempt(self, identifier: str):
        """Enregistre une tentative de connexion réussie.

        Args:
            identifier: Nom d'utilisateur ou email_hash
        """
        # Enregistrer la tentative globale
        self.record_global_attempt()

        if identifier in self._attempts:
            attempts = self._attempts[identifier].failed_attempts
            masked_id = identifier[:16] + "..." if len(identifier) > 16 else identifier
            if attempts > 0:
                logger.info(
                    "✅ Connexion réussie pour '%s' (après %d tentative(s) échouée(s))",
                    masked_id,
                    attempts,
                )
            self._reset_attempts(identifier)
        else:
            logger.info("✅ Connexion réussie")
        self._save_state()

    def _calculate_delay(self, failed_attempts: int) -> float:
        """Calcule le délai progressif en fonction du nombre d'échecs.

        Le délai double à chaque tentative : 1s, 2s, 4s, 8s, 16s, 32s

        Args:
            failed_attempts: Nombre de tentatives échouées

        Returns:
            Délai en secondes
        """
        delay = self.BASE_DELAY_SECONDS * (2 ** (failed_attempts - 1))
        return min(delay, self.MAX_DELAY_SECONDS)

    def _reset_attempts(self, identifier: str):
        """Réinitialise les tentatives pour un utilisateur.

        Args:
            identifier: Nom d'utilisateur ou email_hash
        """
        if identifier in self._attempts:
            del self._attempts[identifier]
            logger.debug("Compteur de tentatives réinitialisé")
            self._save_state()

    def get_attempt_info(self, identifier: str) -> LoginAttemptInfo | None:
        """Récupère les informations de tentatives pour un utilisateur.

        Args:
            identifier: Nom d'utilisateur ou email_hash

        Returns:
            Informations de tentatives ou None
        """
        return self._attempts.get(identifier)

    def clear_all_attempts(self):
        """Réinitialise tous les compteurs (utile pour les tests)."""
        count = len(self._attempts)
        self._attempts.clear()
        self._global_tracker = GlobalAttemptTracker()
        logger.info(
            "Tous les compteurs de tentatives réinitialisés (%d utilisateurs)",
            count,
        )
        self._save_state()

    def get_global_stats(self) -> dict[str, int]:
        """Récupère les statistiques globales.

        Returns:
            Dictionnaire avec les stats
        """
        current_time = time.time()
        self._clean_old_global_attempts(current_time)

        return {
            'attempts_last_minute': len(self._global_tracker.attempts_minute),
            'attempts_last_hour': len(self._global_tracker.attempts_hour),
            'locked_users': sum(1 for info in self._attempts.values()
                               if info.lockout_until and info.lockout_until > current_time)
        }
