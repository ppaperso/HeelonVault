"""
Utilitaire de validation de la force des mots de passe maîtres.

Implémente les recommandations NIST SP 800-63B et OWASP.
"""

import re
from typing import Tuple, List


class MasterPasswordValidator:
    """Validateur de mot de passe maître avec règles de sécurité strictes."""

    # Configuration
    MIN_LENGTH = 12
    MIN_LENGTH_STRONG = 16

    # Liste des 100 mots de passe les plus communs (à étendre)
    COMMON_PASSWORDS = [
        "password",
        "password123",
        "password1",
        "12345678",
        "123456789",
        "qwerty",
        "abc123",
        "monkey",
        "1234567",
        "letmein",
        "trustno1",
        "dragon",
        "baseball",
        "iloveyou",
        "master",
        "sunshine",
        "ashley",
        "bailey",
        "passw0rd",
        "shadow",
        "superman",
        "qazwsx",
        "michael",
        "football",
        "welcome",
        "jesus",
        "ninja",
        "mustang",
        "password1234",
        "admin",
        "admin123",
        "root",
        "toor",
        "changeme",
        "test",
        "test123",
        "azerty",
        "123123",
        "654321",
        "111111",
        "000000",
        "1q2w3e4r",
        "qwertyuiop",
        "123qwe",
        "default",
        "guest",
        "user",
        "administrator",
        "princess",
        "starwars",
        "whatever",
        "freedom",
        "batman",
        "samsung",
        "chocolate",
        "AdminSecure123",
        "Admin123!",
        "Azerty123",
        "Qwerty123",
    ]

    @classmethod
    def validate(cls, password: str) -> Tuple[bool, List[str], int]:
        """Valide un mot de passe maître.

        Args:
            password: Le mot de passe à valider

        Returns:
            Tuple[bool, List[str], int]: (is_valid, error_messages, strength_score)
                - is_valid: True si le mot de passe est acceptable
                - error_messages: Liste des problèmes détectés
                - strength_score: Score de 0 à 100
        """
        errors = []
        score = 0

        # 1. Vérification de la longueur
        if len(password) < cls.MIN_LENGTH:
            errors.append(
                f"Minimum {cls.MIN_LENGTH} caractères requis (actuel : {len(password)})"
            )
        else:
            score += 20
            if len(password) >= cls.MIN_LENGTH_STRONG:
                score += 10
            if len(password) >= 20:
                score += 10

        # 2. Présence de majuscules
        if not any(c.isupper() for c in password):
            errors.append("Au moins une majuscule (A-Z) requise")
        else:
            score += 10

        # 3. Présence de minuscules
        if not any(c.islower() for c in password):
            errors.append("Au moins une minuscule (a-z) requise")
        else:
            score += 10

        # 4. Présence de chiffres
        if not any(c.isdigit() for c in password):
            errors.append("Au moins un chiffre (0-9) requis")
        else:
            score += 10

        # 5. Présence de symboles
        symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in symbols for c in password):
            errors.append("Au moins un symbole (!@#$%...) requis")
        else:
            score += 10

        # 6. Vérification contre les mots de passe communs
        password_lower = password.lower()
        for common in cls.COMMON_PASSWORDS:
            if common.lower() in password_lower or password_lower in common.lower():
                errors.append(
                    "Ce mot de passe (ou une variante) est trop commun et facile à deviner"
                )
                score = max(0, score - 30)
                break

        # 7. Détection de patterns simples
        if cls._has_simple_patterns(password):
            errors.append("Évitez les patterns simples (123, abc, qwerty, etc.)")
            score = max(0, score - 20)

        # 8. Détection de répétitions
        if cls._has_repetitions(password):
            errors.append("Évitez les répétitions excessives (aaa, 111, etc.)")
            score = max(0, score - 10)

        # 9. Bonus pour diversité de caractères
        unique_chars = len(set(password))
        if unique_chars >= len(password) * 0.7:  # 70% de caractères uniques
            score += 10

        # 10. Bonus pour complexité
        if len(password) >= 16 and score >= 60:
            score += 10

        # Score final normalisé
        score = min(100, score)

        # Le mot de passe est valide s'il n'y a aucune erreur critique
        is_valid = len(errors) == 0

        return is_valid, errors, score

    @staticmethod
    def _has_simple_patterns(password: str) -> bool:
        """Détecte les patterns simples dans le mot de passe."""
        password_lower = password.lower()

        # Patterns numériques
        numeric_patterns = [
            "123",
            "234",
            "345",
            "456",
            "567",
            "678",
            "789",
            "987",
            "876",
            "765",
            "654",
            "543",
            "432",
            "321",
            "012",
            "210",
            "111",
            "222",
            "333",
            "000",
        ]

        # Patterns alphabétiques
        alpha_patterns = [
            "abc",
            "bcd",
            "cde",
            "def",
            "efg",
            "fgh",
            "ghi",
            "qwerty",
            "azerty",
            "asdf",
            "zxcv",
            "qwe",
            "asd",
        ]

        for pattern in numeric_patterns + alpha_patterns:
            if pattern in password_lower:
                return True

        return False

    @staticmethod
    def _has_repetitions(password: str) -> bool:
        """Détecte les répétitions excessives de caractères."""
        # Cherche 3 caractères identiques consécutifs ou plus
        if re.search(r"(.)\1{2,}", password):
            return True

        # Cherche des répétitions de séquences (aba, 121, etc.)
        if re.search(r"(..).*\1", password):
            # Vérifie si c'est une répétition courte
            matches = re.findall(r"(..).*\1", password)
            if len(matches) >= 2:
                return True

        return False

    @classmethod
    def get_strength_description(cls, score: int) -> str:
        """Retourne une description textuelle de la force.

        Args:
            score: Score de 0 à 100

        Returns:
            str: Description de la force
        """
        if score >= 80:
            return "Très fort 💪"
        elif score >= 60:
            return "Fort 👍"
        elif score >= 40:
            return "Moyen ⚠️"
        elif score >= 20:
            return "Faible 😟"
        else:
            return "Très faible ❌"

    @classmethod
    def suggest_improvements(cls, password: str) -> List[str]:
        """Suggère des améliorations pour un mot de passe.

        Args:
            password: Le mot de passe à analyser

        Returns:
            List[str]: Liste de suggestions
        """
        suggestions = []

        if len(password) < cls.MIN_LENGTH_STRONG:
            suggestions.append(
                f"Augmentez la longueur à au moins {cls.MIN_LENGTH_STRONG} caractères"
            )

        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            suggestions.append("Ajoutez des symboles spéciaux (!@#$%...)")

        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)

        if not (has_lower and has_upper and has_digit):
            suggestions.append("Mélangez majuscules, minuscules et chiffres")

        if cls._has_simple_patterns(password):
            suggestions.append("Évitez les séquences simples (123, abc, etc.)")

        if cls._has_repetitions(password):
            suggestions.append("Évitez les répétitions de caractères")

        if not suggestions:
            suggestions.append("Votre mot de passe est solide ! ✅")

        return suggestions


def test_validator():
    """Fonction de test pour le validateur."""
    test_cases = [
        ("abc123", "Très faible (trop court et simple)"),
        ("password123", "Faible (mot commun)"),
        ("MySecureP@ss2024", "Fort"),
        ("C0mpl3x!P@ssw0rd#2024", "Très fort"),
        ("aaaaaa", "Très faible (répétitions)"),
        ("qwerty123456", "Faible (pattern clavier)"),
        ("J'Aim3L3sCh@tsN0irs!", "Très fort"),
    ]

    print("🧪 Tests de validation des mots de passe\n")
    print("=" * 70)

    for password, expected_level in test_cases:
        is_valid, errors, score = MasterPasswordValidator.validate(password)
        strength = MasterPasswordValidator.get_strength_description(score)

        print(f"\nMot de passe : {password}")
        print(f"Valide      : {'✅ Oui' if is_valid else '❌ Non'}")
        print(f"Score       : {score}/100")
        print(f"Force       : {strength}")

        if errors:
            print("Erreurs     :")
            for error in errors:
                print(f"  - {error}")

        suggestions = MasterPasswordValidator.suggest_improvements(password)
        if suggestions and not is_valid:
            print("Suggestions :")
            for suggestion in suggestions:
                print(f"  💡 {suggestion}")

        print("-" * 70)


if __name__ == "__main__":
    test_validator()
