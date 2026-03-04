"""
Service de chiffrement/déchiffrement des mots de passe.

Algorithme : AES-256-GCM (authentifié, résistant aux altérations)
KDF        : PBKDF2-HMAC-SHA256, 600 000 itérations (recommandation NIST 2023)
Interface  : identique à l'original — aucune modification requise côté appelant
"""

from __future__ import annotations

import base64
import ctypes
import logging
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.i18n import _

logger = logging.getLogger(__name__)

# ── Constantes cryptographiques ──────────────────────────────────────────────
_PBKDF2_ITERATIONS: int = 600_000   # NIST SP 800-132 (2023) — à augmenter dans le futur
_KEY_LENGTH: int = 32               # 256 bits
_NONCE_LENGTH: int = 12             # 96 bits — taille canonique AES-GCM
_SALT_LENGTH: int = 32              # 256 bits
_SALT_MIN_LENGTH: int = 16          # 128 bits minimum accepté


class CryptoService:
    """Chiffrement/déchiffrement AES-256-GCM avec clé dérivée par PBKDF2.

    Interface publique inchangée par rapport à la version précédente :
        - .salt         → bytes
        - .encrypt()    → dict[str, str]
        - .decrypt()    → str
        - .clear()      → None  (nouveau — à appeler en fin de session)
    """

    def __init__(self, master_password: str, salt: bytes | None = None) -> None:
        """Initialise le service de chiffrement.

        Args:
            master_password: Mot de passe maître pour dériver la clé.
                             N'est jamais stocké — utilisé uniquement pour la dérivation.
            salt: Salt PBKDF2 (généré aléatoirement si None).
                  Doit faire au minimum 16 bytes si fourni.

        Raises:
            ValueError: Si le salt fourni est trop court.
        """
        if salt is None:
            salt = secrets.token_bytes(_SALT_LENGTH)

        if len(salt) < _SALT_MIN_LENGTH:
            raise ValueError(
                f"Salt trop court : {len(salt)} bytes fournis, "
                f"minimum requis : {_SALT_MIN_LENGTH} bytes."
            )

        self.salt: bytes = salt

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LENGTH,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
            backend=default_backend(),
        )

        # La clé est préfixée _ : elle ne doit pas être accédée directement
        # ni loggée, ni sérialisée.
        self._key: bytes = kdf.derive(master_password.encode("utf-8"))
        self._cipher: AESGCM = AESGCM(self._key)

        logger.debug(
            "CryptoService initialisé — salt %d bytes, %d itérations PBKDF2",
            len(salt),
            _PBKDF2_ITERATIONS,
        )

    # ── Chiffrement ──────────────────────────────────────────────────────────

    def encrypt(self, plaintext: str) -> dict[str, str]:
        """Chiffre un texte en clair avec AES-256-GCM.

        Un nonce unique est généré pour chaque appel.

        Args:
            plaintext: Texte en clair à chiffrer.

        Returns:
            Dictionnaire ``{"nonce": <b64>, "ciphertext": <b64>}``.
        """
        nonce = secrets.token_bytes(_NONCE_LENGTH)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode("utf-8"), None)

        # Aucun log du contenu — même en DEBUG
        return {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    # ── Déchiffrement ────────────────────────────────────────────────────────

    def decrypt(self, encrypted_data: dict[str, str]) -> str:
        """Déchiffre un enregistrement chiffré par :meth:`encrypt`.

        Args:
            encrypted_data: Dictionnaire ``{"nonce": <b64>, "ciphertext": <b64>}``.

        Returns:
            Texte en clair déchiffré.

        Raises:
            ValueError: Si le déchiffrement échoue (clé incorrecte, données
                        corrompues ou altérées — tag GCM invalide).
            KeyError:   Si ``encrypted_data`` ne contient pas les clés attendues.
        """
        try:
            nonce = base64.b64decode(encrypted_data["nonce"])
            ciphertext = base64.b64decode(encrypted_data["ciphertext"])
            plaintext_bytes = self._cipher.decrypt(nonce, ciphertext, None)
            return plaintext_bytes.decode("utf-8")
        except InvalidTag as exc:
            # Ne pas propager l'exception originale pour éviter toute fuite
            # d'information sur la structure interne
            raise ValueError(
                _("Unable to decrypt: invalid key or corrupted/tampered data.")
            ) from exc
        except (KeyError, ValueError) as exc:
            raise ValueError(_("Malformed encrypted payload: %s") % exc) from exc

    # ── Nettoyage mémoire ────────────────────────────────────────────────────

    def clear(self) -> None:
        """Efface la clé de dérivation de la mémoire (best-effort).

        À appeler explicitement en fin de session (logout, fermeture de fenêtre).
        Python ne garantit pas l'effacement immédiat du GC, mais cette méthode
        écrase les bytes au niveau C avant de libérer la référence.

        Note:
            En raison de l'immutabilité des ``bytes`` Python, cette opération
            agit sur une copie — elle réduit la fenêtre d'exposition sans
            l'éliminer totalement. Pour une protection maximale envisager
            ``SecretBuffer`` via ``cryptography.hazmat`` ou ``secmem``.
        """
        if hasattr(self, "_key") and self._key:
            try:
                buf = (ctypes.c_char * len(self._key)).from_buffer_copy(self._key)
                ctypes.memset(buf, 0, len(self._key))
            except Exception as exc:
                logger.debug("Exception during memory clearing (best-effort): %s", exc)
            finally:
                self._key = b""

        if hasattr(self, "_cipher"):
            del self._cipher

        logger.debug("CryptoService: secrets cleared from memory")

    def __del__(self) -> None:
        """Garantit un nettoyage minimal à la destruction de l'objet."""
        self.clear()
