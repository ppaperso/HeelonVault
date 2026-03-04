"""Validation équilibrée des mots de passe maîtres.

Politique orientée usage humain, alignée avec les bonnes pratiques CNIL/NIST:
- recommandé: 12+ caractères (phrase de passe)
- minimum accepté: 10 caractères avec 4 classes (maj/min/chiffre/symbole)
"""

import re

from src.i18n import _


class MasterPasswordValidator:
    """Validateur de mot de passe maître avec règles pragmatiques."""

    # Configuration
    MIN_LENGTH = 10
    RECOMMENDED_LENGTH = 12
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
    def validate(cls, password: str) -> tuple[bool, list[str], int]:
        """Valide un mot de passe maître.

        Args:
            password: Le mot de passe à valider

        Returns:
            Tuple[bool, List[str], int]: (is_valid, error_messages, strength_score)
                - is_valid: True si le mot de passe est acceptable
                - error_messages: Liste des problèmes détectés
                - strength_score: Score de 0 à 100
        """
        errors: list[str] = []
        score = 0
        length = len(password)

        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() and not c.isspace() for c in password)
        complexity = sum([has_lower, has_upper, has_digit, has_special])

        # 1) Score longueur
        if length >= cls.MIN_LENGTH_STRONG:
            score += 35
        elif length >= cls.RECOMMENDED_LENGTH:
            score += 30
        elif length >= cls.MIN_LENGTH:
            score += 20
        elif length >= 8:
            score += 10

        # 2) Score diversité
        score += complexity * 10

        # 3) Politique d'acceptation minimale
        meets_length_only = length >= cls.RECOMMENDED_LENGTH
        meets_len10_complex = (
            length >= cls.MIN_LENGTH
            and has_lower
            and has_upper
            and has_digit
            and has_special
        )
        if not (meets_length_only or meets_len10_complex):
            errors.append(
                _(
                    "Minimum requirement: 12+ characters, or 10+ with at least "
                    "1 uppercase, 1 lowercase, 1 digit, and 1 symbol"
                )
            )

        # 4) Vérification contre mots de passe trop communs
        if cls._is_too_common(password):
            errors.append(_("This password is too common and easy to guess"))
            score = max(0, score - 40)

        # 5) Détection de patterns simples (impacte surtout le score)
        if cls._has_simple_patterns(password):
            score = max(0, score - 10)

        # 6) Détection de répétitions (impacte le score)
        if cls._has_repetitions(password):
            score = max(0, score - 10)

        # 7) Bonus diversité
        unique_chars = len(set(password))
        if length > 0 and unique_chars >= length * 0.7:
            score += 10

        # 8) Bonus longueur + complexité
        if length >= cls.MIN_LENGTH_STRONG and complexity >= 3:
            score += 10

        # Score final normalisé
        score = min(100, score)

        # Valide si aucune erreur bloquante
        is_valid = len(errors) == 0

        return is_valid, errors, score

    @classmethod
    def _is_too_common(cls, password: str) -> bool:
        """Vérifie si le mot de passe correspond à un secret très courant.

        On compare en égalité (pas en sous-chaîne) pour éviter les faux positifs
        sur des mots de passe longs contenant, par exemple, "test".
        """
        normalized = "".join(ch.lower() for ch in password if ch.isalnum())
        if not normalized:
            return True
        common_normalized = {
            "".join(ch.lower() for ch in common if ch.isalnum())
            for common in cls.COMMON_PASSWORDS
        }
        return normalized in common_normalized

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
        return bool(re.search(r"(.)\1{3,}", password))

    @classmethod
    def get_strength_description(cls, score: int) -> str:
        """Retourne une description textuelle de la force.

        Args:
            score: Score de 0 à 100

        Returns:
            str: Description de la force
        """
        if score >= 80:
            return _("Very strong 💪")
        elif score >= 60:
            return _("Strong 👍")
        elif score >= 40:
            return _("Medium ⚠️")
        elif score >= 20:
            return _("Weak 😟")
        else:
            return _("Very weak ❌")

    @classmethod
    def suggest_improvements(cls, password: str) -> list[str]:
        """Suggère des améliorations pour un mot de passe.

        Args:
            password: Le mot de passe à analyser

        Returns:
            List[str]: Liste de suggestions
        """
        suggestions = []

        if len(password) < cls.RECOMMENDED_LENGTH:
            suggestions.append(
                _("Aim for at least %(count)s characters (recommended)")
                % {"count": cls.RECOMMENDED_LENGTH}
            )

        if len(password) < cls.MIN_LENGTH_STRONG:
            suggestions.append(
                _("Increase length to at least %(count)s characters")
                % {"count": cls.MIN_LENGTH_STRONG}
            )

        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            suggestions.append(_("Add special symbols (!@#$%...)"))

        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)

        if not (has_lower and has_upper and has_digit):
            suggestions.append(_("Mix uppercase, lowercase, and digits"))

        if cls._has_simple_patterns(password):
            suggestions.append(_("Avoid simple sequences (123, abc, etc.)"))

        if cls._has_repetitions(password):
            suggestions.append(_("Avoid repeated characters"))

        if cls._is_too_common(password):
            suggestions.append(_("Choose a less common password"))

        if not suggestions:
            suggestions.append(_("Your password is solid! ✅"))

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

    for password, _expected_level in test_cases:
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
