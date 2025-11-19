"""Tests d'intégration pour la protection anti-brute force."""

import unittest
import time
from src.services.login_attempt_tracker import LoginAttemptTracker


class TestBruteForceProtection(unittest.TestCase):
    """Tests de la protection contre les attaques par force brute."""
    
    def setUp(self):
        """Initialise un nouveau tracker pour chaque test."""
        self.tracker = LoginAttemptTracker()
    
    def test_first_attempt_allowed(self):
        """Le premier essai doit toujours être autorisé."""
        can_attempt, remaining = self.tracker.check_can_attempt("testuser")
        self.assertTrue(can_attempt)
        self.assertIsNone(remaining)
    
    def test_progressive_delay(self):
        """Teste le délai progressif après chaque échec."""
        username = "testuser"
        
        # Premier échec - pas de délai immédiat
        self.tracker.record_failed_attempt(username)
        can_attempt, _ = self.tracker.check_can_attempt(username)
        self.assertFalse(can_attempt)  # Délai de 1s activé
        
        # Attendre le délai
        time.sleep(1.1)
        can_attempt, _ = self.tracker.check_can_attempt(username)
        self.assertTrue(can_attempt)
        
        # Deuxième échec - délai de 2s
        self.tracker.record_failed_attempt(username)
        can_attempt, remaining = self.tracker.check_can_attempt(username)
        self.assertFalse(can_attempt)
        self.assertIsNotNone(remaining)
    
    def test_lockout_after_max_attempts(self):
        """Teste le verrouillage après 5 tentatives échouées."""
        username = "testuser"
        
        # 5 tentatives échouées avec délais courts
        for i in range(5):
            self.tracker.record_failed_attempt(username)
            if i < 4:  # Pas de verrouillage avant la 5ème
                time.sleep(0.1)  # Petite pause pour les tests
        
        # Vérifier le verrouillage
        can_attempt, remaining = self.tracker.check_can_attempt(username)
        self.assertFalse(can_attempt)
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 890)  # ~15 minutes
    
    def test_successful_login_resets_counter(self):
        """Un login réussi doit réinitialiser le compteur."""
        username = "testuser"
        
        # Quelques échecs
        self.tracker.record_failed_attempt(username)
        time.sleep(1.1)
        self.tracker.record_failed_attempt(username)
        
        # Vérifier qu'il y a des tentatives enregistrées
        info = self.tracker.get_attempt_info(username)
        self.assertEqual(info.failed_attempts, 2)
        
        # Login réussi
        self.tracker.record_successful_attempt(username)
        
        # Vérifier que le compteur est réinitialisé
        info = self.tracker.get_attempt_info(username)
        self.assertIsNone(info)
        
        # La prochaine tentative devrait être autorisée immédiatement
        can_attempt, _ = self.tracker.check_can_attempt(username)
        self.assertTrue(can_attempt)
    
    def test_delay_calculation(self):
        """Teste le calcul des délais progressifs."""
        # 1ère tentative : 1s
        delay1 = self.tracker._calculate_delay(1)
        self.assertEqual(delay1, 1)
        
        # 2ème tentative : 2s
        delay2 = self.tracker._calculate_delay(2)
        self.assertEqual(delay2, 2)
        
        # 3ème tentative : 4s
        delay3 = self.tracker._calculate_delay(3)
        self.assertEqual(delay3, 4)
        
        # 4ème tentative : 8s
        delay4 = self.tracker._calculate_delay(4)
        self.assertEqual(delay4, 8)
        
        # 5ème tentative : 16s
        delay5 = self.tracker._calculate_delay(5)
        self.assertEqual(delay5, 16)
        
        # 6ème tentative : 32s (maximum)
        delay6 = self.tracker._calculate_delay(6)
        self.assertEqual(delay6, 32)
        
        # 7ème+ tentative : toujours 32s (maximum)
        delay7 = self.tracker._calculate_delay(7)
        self.assertEqual(delay7, 32)
    
    def test_multiple_users_independent(self):
        """Les compteurs doivent être indépendants entre utilisateurs."""
        user1 = "alice"
        user2 = "bob"
        
        # Alice échoue plusieurs fois
        self.tracker.record_failed_attempt(user1)
        self.tracker.record_failed_attempt(user1)
        
        # Bob devrait pouvoir se connecter normalement
        can_attempt, _ = self.tracker.check_can_attempt(user2)
        self.assertTrue(can_attempt)
        
        # Vérifier les compteurs
        info1 = self.tracker.get_attempt_info(user1)
        info2 = self.tracker.get_attempt_info(user2)
        
        self.assertEqual(info1.failed_attempts, 2)
        self.assertIsNone(info2)
    
    def test_clear_all_attempts(self):
        """Teste la réinitialisation de tous les compteurs."""
        # Créer plusieurs échecs pour différents utilisateurs
        self.tracker.record_failed_attempt("alice")
        self.tracker.record_failed_attempt("bob")
        self.tracker.record_failed_attempt("charlie")
        
        # Vérifier qu'il y a des tentatives
        self.assertIsNotNone(self.tracker.get_attempt_info("alice"))
        
        # Tout réinitialiser
        self.tracker.clear_all_attempts()
        
        # Vérifier que tout est effacé
        self.assertIsNone(self.tracker.get_attempt_info("alice"))
        self.assertIsNone(self.tracker.get_attempt_info("bob"))
        self.assertIsNone(self.tracker.get_attempt_info("charlie"))


if __name__ == '__main__':
    unittest.main()
