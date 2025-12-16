"""Service de protection contre les attaques par force brute.

Ce service gère :
- Le suivi des tentatives de connexion échouées
- Les délais progressifs après chaque échec
- Le verrouillage temporaire après trop de tentatives
- La journalisation des tentatives suspectes
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass

# Configuration du logging
logger = logging.getLogger(__name__)


@dataclass
class LoginAttemptInfo:
    """Informations sur les tentatives de connexion pour un utilisateur."""
    failed_attempts: int = 0
    last_attempt_time: float = 0.0
    lockout_until: Optional[float] = None


class LoginAttemptTracker:
    """Gestionnaire de protection contre les attaques par force brute.
    
    Fonctionnalités :
    - Délai progressif : 1s, 2s, 4s, 8s, etc. après chaque échec
    - Verrouillage temporaire : 15 minutes après 5 tentatives échouées
    - Journalisation des tentatives suspectes
    """
    
    # Configuration
    MAX_ATTEMPTS_BEFORE_LOCKOUT = 5
    LOCKOUT_DURATION_SECONDS = 900  # 15 minutes
    BASE_DELAY_SECONDS = 1  # Délai de base, doublé à chaque tentative
    MAX_DELAY_SECONDS = 32  # Délai maximum (32 secondes)
    
    def __init__(self):
        """Initialise le tracker."""
        self._attempts: Dict[str, LoginAttemptInfo] = {}
        logger.info("Service de protection anti-brute force initialisé")
    
    def check_can_attempt(self, username: str) -> tuple[bool, Optional[int]]:
        """Vérifie si une tentative de connexion est autorisée.
        
        Args:
            username: Nom de l'utilisateur
            
        Returns:
            Tuple (peut_tenter, secondes_restantes):
            - peut_tenter: True si la tentative est autorisée
            - secondes_restantes: Nombre de secondes à attendre (si bloqué)
        """
        current_time = time.time()
        
        if username not in self._attempts:
            return (True, None)
        
        info = self._attempts[username]
        
        # Vérifier le verrouillage temporaire
        if info.lockout_until and current_time < info.lockout_until:
            remaining = int(info.lockout_until - current_time)
            logger.warning(
                f"Tentative de connexion bloquée pour '{username}' "
                f"({remaining}s restantes)"
            )
            return (False, remaining)
        
        # Si le verrouillage est expiré, réinitialiser
        if info.lockout_until and current_time >= info.lockout_until:
            logger.info(f"Fin du verrouillage pour '{username}'")
            self._reset_attempts(username)
            return (True, None)
        
        # Vérifier le délai progressif
        if info.failed_attempts > 0:
            delay = self._calculate_delay(info.failed_attempts)
            time_since_last = current_time - info.last_attempt_time
            
            if time_since_last < delay:
                remaining = int(delay - time_since_last)
                logger.debug(
                    f"Délai anti-brute force actif pour '{username}' "
                    f"({remaining}s restantes)"
                )
                return (False, remaining)
        
        return (True, None)
    
    def record_failed_attempt(self, username: str):
        """Enregistre une tentative de connexion échouée.
        
        Args:
            username: Nom de l'utilisateur
        """
        current_time = time.time()
        
        if username not in self._attempts:
            self._attempts[username] = LoginAttemptInfo()
        
        info = self._attempts[username]
        info.failed_attempts += 1
        info.last_attempt_time = current_time
        
        # Journalisation
        logger.warning(
            f"Tentative de connexion échouée pour '{username}' "
            f"(tentative {info.failed_attempts}/{self.MAX_ATTEMPTS_BEFORE_LOCKOUT})"
        )
        
        # Vérifier si verrouillage nécessaire
        if info.failed_attempts >= self.MAX_ATTEMPTS_BEFORE_LOCKOUT:
            info.lockout_until = current_time + self.LOCKOUT_DURATION_SECONDS
            logger.error(
                f"🔒 VERROUILLAGE: Compte '{username}' verrouillé pendant "
                f"{self.LOCKOUT_DURATION_SECONDS // 60} minutes "
                f"(trop de tentatives échouées)"
            )
    
    def record_successful_attempt(self, username: str):
        """Enregistre une tentative de connexion réussie.
        
        Args:
            username: Nom de l'utilisateur
        """
        if username in self._attempts:
            attempts = self._attempts[username].failed_attempts
            if attempts > 0:
                logger.info(
                    f"✅ Connexion réussie pour '{username}' "
                    f"(après {attempts} tentative(s) échouée(s))"
                )
            self._reset_attempts(username)
        else:
            logger.info(f"✅ Connexion réussie pour '{username}'")
    
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
    
    def _reset_attempts(self, username: str):
        """Réinitialise les tentatives pour un utilisateur.
        
        Args:
            username: Nom de l'utilisateur
        """
        if username in self._attempts:
            del self._attempts[username]
            logger.debug(f"Compteur de tentatives réinitialisé pour '{username}'")
    
    def get_attempt_info(self, username: str) -> Optional[LoginAttemptInfo]:
        """Récupère les informations de tentatives pour un utilisateur.
        
        Args:
            username: Nom de l'utilisateur
            
        Returns:
            Informations de tentatives ou None
        """
        return self._attempts.get(username)
    
    def clear_all_attempts(self):
        """Réinitialise tous les compteurs (utile pour les tests)."""
        count = len(self._attempts)
        self._attempts.clear()
        logger.info(f"Tous les compteurs de tentatives réinitialisés ({count} utilisateurs)")
