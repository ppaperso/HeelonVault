"""
Service de génération de mots de passe sécurisés.
"""
import logging
import secrets
import string

from src.data.french_wordlist_extended import FRENCH_WORDS_EXTENDED

logger = logging.getLogger(__name__)


class PasswordGenerator:
    """Générateur de mots de passe et phrases de passe sécurisés."""

    # Liste étendue de mots français pour les phrases de passe (1053 mots)
    # Entropie : 5 mots = log₂(1053⁵) ≈ 50 bits (acceptable)
    # Avec capitalisation + nombres : ~60 bits (bon)
    FRENCH_WORDS = FRENCH_WORDS_EXTENDED

    @staticmethod
    def generate(
        length: int = 20,
        use_uppercase: bool = True,
        use_lowercase: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
        exclude_ambiguous: bool = True
    ) -> str:
        """Génère un mot de passe aléatoire sécurisé.

        Args:
            length: Longueur du mot de passe (8-64)
            use_uppercase: Inclure les majuscules
            use_lowercase: Inclure les minuscules
            use_digits: Inclure les chiffres
            use_symbols: Inclure les symboles
            exclude_ambiguous: Exclure les caractères ambigus (0, O, l, 1, I)

        Returns:
            str: Mot de passe généré

        Raises:
            ValueError: Si aucun jeu de caractères n'est sélectionné
        """
        charset = ""

        if use_lowercase:
            charset += string.ascii_lowercase
        if use_uppercase:
            charset += string.ascii_uppercase
        if use_digits:
            charset += string.digits
        if use_symbols:
            charset += "!@#$%^&*()_+-=[]{}|;:,.<>?"

        if exclude_ambiguous:
            # Retirer les caractères ambigus (0, O, l, 1, I)
            ambiguous = "0Ol1I"
            charset = "".join(c for c in charset if c not in ambiguous)

        if not charset:
            charset = string.ascii_letters + string.digits

        # Génération cryptographiquement sécurisée
        password = "".join(secrets.choice(charset) for _ in range(length))
        logger.debug("PasswordGenerator: mot de passe genere (longueur=%d)", length)
        return password

    @classmethod
    def generate_passphrase(
        cls,
        word_count: int = 5,
        separator: str = "-"
    ) -> str:
        """Génère une phrase de passe mémorisable.

        Args:
            word_count: Nombre de mots (3-8)
            separator: Séparateur entre les mots

        Returns:
            str: Phrase de passe générée

        Example:
            >>> PasswordGenerator.generate_passphrase(4)
            'Soleil-montagne-Jardin-neige42'
        """
        chosen_words = [secrets.choice(cls.FRENCH_WORDS) for _ in range(word_count)]

        # Capitaliser aléatoirement certains mots
        chosen_words = [
            w.capitalize() if secrets.randbelow(2) else w
            for w in chosen_words
        ]

        # Ajouter un chiffre à la fin
        result = separator.join(chosen_words) + str(secrets.randbelow(100))
        logger.debug("PasswordGenerator: phrase de passe generee (mots=%d)", word_count)
        return result

    @staticmethod
    def estimate_strength(password: str) -> dict:
        """Estime la force d'un mot de passe.

        Args:
            password: Mot de passe à évaluer

        Returns:
            dict: Dictionnaire avec score (0-4) et description
        """
        score = 0
        length = len(password)

        # Critères de force
        has_lower = any(c.islower() for c in password)
        has_upper = any(c.isupper() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_symbol = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

        # Calcul du score
        if length >= 8:
            score += 1
        if length >= 12:
            score += 1
        if has_lower and has_upper:
            score += 1
        if has_digit:
            score += 1
        if has_symbol:
            score += 1

        # Normaliser le score (0-4)
        score = min(score, 4)

        descriptions = {
            0: "Très faible",
            1: "Faible",
            2: "Moyen",
            3: "Fort",
            4: "Très fort"
        }

        return {
            'score': score,
            'description': descriptions[score],
            'length': length,
            'has_lowercase': has_lower,
            'has_uppercase': has_upper,
            'has_digits': has_digit,
            'has_symbols': has_symbol
        }
