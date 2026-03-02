"""Service de gestion de l'authentification à double facteur (2FA) via TOTP.

Ce module gère :
- Génération et chiffrement de secrets TOTP
- Génération de QR codes pour applications d'authentification
- Vérification des codes TOTP
- Génération et vérification de codes de secours
- Chiffrement basé sur l'identifiant unique de la machine
"""

import hashlib
import hmac
import json
import logging
import secrets
from io import BytesIO
from pathlib import Path

import pyotp
import qrcode
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class TOTPService:
    """Service de gestion de l'authentification à double facteur (TOTP).
    Utilise :
    - pyotp pour la génération et vérification TOTP (RFC 6238)
    - machine-id pour lier le chiffrement au matériel
    - AESGCM pour chiffrer les secrets TOTP
    - HMAC-SHA256 pour hasher les codes de secours
    """

    TOTP_ISSUER = "HeelonVault"
    TOTP_INTERVAL = 30  # Secondes
    TOTP_DIGITS = 6
    BACKUP_CODES_COUNT = 10
    BACKUP_CODE_LENGTH = 10

    def __init__(self, data_dir: Path):
        """Initialise le service TOTP.

        Args:
            data_dir: Répertoire de données pour stocker la clé système
        """
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._system_key = self._get_or_create_system_key()
        logger.info("TOTPService initialisé avec clé système")

    def _get_machine_id(self) -> str:
        """Récupère l'identifiant unique de la machine.

        Essaie plusieurs sources (Linux, fallback pour dev).

        Returns:
            Identifiant unique de la machine
        """
        # Essayer /etc/machine-id (Linux systemd)
        machine_id_paths = [
            Path("/etc/machine-id"),
            Path("/var/lib/dbus/machine-id"),
        ]

        for path in machine_id_paths:
            if path.exists():
                try:
                    machine_id = path.read_text().strip()
                    if machine_id:
                        logger.debug(f"Machine ID trouvé dans {path}")
                        return machine_id
                except Exception as e:
                    logger.warning(f"Erreur lecture {path}: {e}")

        # Fallback pour développement : utiliser un ID persistant local
        fallback_path = self.data_dir / ".machine_id_fallback"
        if fallback_path.exists():
            machine_id = fallback_path.read_text().strip()
            logger.warning("Utilisation machine-id fallback (développement)")
            return machine_id
        else:
            # Générer un ID unique et le persister
            machine_id = secrets.token_hex(16)
            fallback_path.write_text(machine_id)
            logger.warning(f"Machine-id fallback généré : {machine_id}")
            return machine_id

    def _get_or_create_system_key(self) -> bytes:
        """Récupère ou crée la clé système pour chiffrement TOTP.

        La clé est dérivée de machine-id + pepper stocké localement.

        Returns:
            Clé AES de 256 bits
        """
        app_key_path = self.data_dir / ".app_key"

        # Récupérer le machine-id
        machine_id = self._get_machine_id()

        # Si .app_key existe, le charger
        if app_key_path.exists():
            try:
                pepper = app_key_path.read_bytes()
                logger.debug(".app_key trouvé, dérivation de la clé système")
            except Exception as e:
                logger.error(f"Erreur lecture .app_key : {e}")
                raise
        else:
            # Générer un nouveau pepper
            pepper = secrets.token_bytes(32)
            try:
                # Permissions restreintes (600)
                app_key_path.write_bytes(pepper)
                app_key_path.chmod(0o600)
                logger.info(".app_key créé avec permissions 600")
            except Exception as e:
                logger.error(f"Erreur création .app_key : {e}")
                raise

        # Dériver la clé système avec PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits pour AES-256
            salt=machine_id.encode(),
            iterations=100_000,
            backend=default_backend()
        )
        system_key = kdf.derive(pepper)
        logger.debug("Clé système dérivée avec succès")
        return system_key

    def generate_secret(self) -> str:
        """Génère un nouveau secret TOTP aléatoire.

        Returns:
            Secret en base32 (compatible Google Authenticator)
        """
        secret = pyotp.random_base32()
        logger.info("Secret TOTP généré")
        return secret

    def encrypt_secret(self, secret: str) -> str:
        """Chiffre un secret TOTP avec la clé système.

        Args:
            secret: Secret TOTP en base32

        Returns:
            Secret chiffré encodé en JSON (nonce + ciphertext en hex)
        """
        try:
            aesgcm = AESGCM(self._system_key)
            nonce = secrets.token_bytes(12)  # 96 bits pour GCM
            ciphertext = aesgcm.encrypt(nonce, secret.encode(), None)

            encrypted_data = {
                "nonce": nonce.hex(),
                "ciphertext": ciphertext.hex()
            }
            result = json.dumps(encrypted_data)
            logger.debug("Secret TOTP chiffré")
            return result
        except Exception as e:
            logger.error(f"Erreur chiffrement secret TOTP : {e}")
            raise

    def decrypt_secret(self, encrypted_secret: str) -> str:
        """Déchiffre un secret TOTP.

        Args:
            encrypted_secret: Secret chiffré (JSON)

        Returns:
            Secret TOTP en base32

        Raises:
            ValueError: Si le déchiffrement échoue
        """
        try:
            encrypted_data = json.loads(encrypted_secret)
            nonce = bytes.fromhex(encrypted_data["nonce"])
            ciphertext = bytes.fromhex(encrypted_data["ciphertext"])

            aesgcm = AESGCM(self._system_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            secret = plaintext.decode()
            logger.debug("Secret TOTP déchiffré")
            return secret
        except Exception as e:
            logger.error(f"Erreur déchiffrement secret TOTP : {e}")
            raise ValueError("Impossible de déchiffrer le secret TOTP") from e

    def generate_qr_code(self, secret: str, email: str) -> bytes:
        """Génère un QR code pour le secret TOTP.

        Args:
            secret: Secret TOTP en base32
            email: Email de l'utilisateur (pour le label)

        Returns:
            Image QR code en PNG (bytes)
        """
        try:
            totp = pyotp.TOTP(secret)
            uri = totp.provisioning_uri(
                name=email,
                issuer_name=self.TOTP_ISSUER
            )

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(uri)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_bytes = buffer.getvalue()
            logger.info(f"QR code généré pour {email}")
            return qr_bytes
        except Exception as e:
            logger.error(f"Erreur génération QR code : {e}")
            raise

    def verify_totp(self, secret: str, code: str, window: int = 1) -> bool:
        """Vérifie un code TOTP.

        Args:
            secret: Secret TOTP en base32
            code: Code à 6 chiffres saisi par l'utilisateur
            window: Fenêtre de tolérance (±30s par défaut)

        Returns:
            True si le code est valide
        """
        try:
            totp = pyotp.TOTP(secret)
            is_valid = totp.verify(code, valid_window=window)
            logger.debug(f"Vérification TOTP : {'✅ valide' if is_valid else '❌ invalide'}")
            return is_valid
        except Exception as e:
            logger.error(f"Erreur vérification TOTP : {e}")
            return False

    def generate_backup_codes(self) -> list[str]:
        """Génère des codes de secours pour la récupération.

        Returns:
            Liste de 10 codes de secours (format: XXXX-XXXX-XX)
        """
        codes = []
        for _ in range(self.BACKUP_CODES_COUNT):
            # Générer un code aléatoire
            code_part1 = secrets.token_hex(2).upper()  # 4 chars
            code_part2 = secrets.token_hex(2).upper()  # 4 chars
            code_part3 = secrets.token_hex(1).upper()  # 2 chars
            code = f"{code_part1}-{code_part2}-{code_part3}"
            codes.append(code)

        logger.info(f"{self.BACKUP_CODES_COUNT} codes de secours générés")
        return codes

    def hash_backup_code(self, code: str) -> str:
        """Hash un code de secours avec HMAC-SHA256.

        Args:
            code: Code de secours en clair

        Returns:
            Hash HMAC-SHA256 en hexadécimal
        """
        # Utiliser la clé système comme clé HMAC
        code_hash = hmac.new(
            self._system_key,
            code.encode(),
            hashlib.sha256
        ).hexdigest()
        return code_hash

    def verify_backup_code(self, code: str, hashed_codes: list[str]) -> tuple[bool, str | None]:
        """Vérifie un code de secours.

        Args:
            code: Code saisi par l'utilisateur
            hashed_codes: Liste des codes hashés stockés

        Returns:
            Tuple (is_valid, matched_hash)
            - is_valid: True si le code est valide
            - matched_hash: Hash du code correspondant (pour le marquer comme utilisé)
        """
        code_hash = self.hash_backup_code(code)

        if code_hash in hashed_codes:
            logger.info("✅ Code de secours valide")
            return (True, code_hash)

        logger.warning("❌ Code de secours invalide")
        return (False, None)

    def encrypt_backup_codes(self, codes: list[str]) -> str:
        """Chiffre et hash les codes de secours pour stockage.

        Args:
            codes: Liste des codes en clair

        Returns:
            JSON contenant les codes hashés
        """
        hashed_codes = [self.hash_backup_code(code) for code in codes]
        result = json.dumps(hashed_codes)
        logger.debug(f"{len(hashed_codes)} codes de secours hashés")
        return result

    def decrypt_backup_codes(self, encrypted_codes: str) -> list[str]:
        """Déchiffre les codes de secours stockés.

        Args:
            encrypted_codes: JSON contenant les codes hashés

        Returns:
            Liste des hashes (pas les codes en clair, c'est impossible)
        """
        try:
            hashed_codes = json.loads(encrypted_codes)
            logger.debug(f"{len(hashed_codes)} codes de secours chargés")
            return hashed_codes
        except Exception as e:
            logger.error(f"Erreur déchiffrement codes de secours : {e}")
            return []

    def mark_backup_code_used(self, encrypted_codes: str, used_hash: str) -> str:
        """Marque un code de secours comme utilisé.

        Args:
            encrypted_codes: JSON actuel des codes
            used_hash: Hash du code à retirer

        Returns:
            JSON mis à jour sans le code utilisé
        """
        try:
            hashed_codes = json.loads(encrypted_codes)
            if used_hash in hashed_codes:
                hashed_codes.remove(used_hash)
                logger.info(f"Code de secours marqué comme utilisé (reste {len(hashed_codes)})")
            return json.dumps(hashed_codes)
        except Exception as e:
            logger.error(f"Erreur marquage code utilisé : {e}")
            return encrypted_codes

    def get_current_totp(self, secret: str) -> str:
        """Génère le code TOTP actuel (pour tests).

        Args:
            secret: Secret TOTP en base32

        Returns:
            Code TOTP actuel à 6 chiffres
        """
        totp = pyotp.TOTP(secret)
        return totp.now()
