"""Service d'authentification et gestion des utilisateurs.

Ce module gère :
- L'authentification des utilisateurs par email (avec hash HMAC-SHA256)
- Le hachage sécurisé des mots de passe (PBKDF2HMAC)
- La création et suppression d'utilisateurs
- Le changement et la réinitialisation de mots de passe
- La gestion du 2FA (TOTP) obligatoire
- Protection contre le brute force avec délai artificiel
"""

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
import time
from pathlib import Path

import validators
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class AuthService:
    """Service d'authentification et gestion des utilisateurs.

    Utilise PBKDF2HMAC avec 600 000 itérations pour le hachage des mots de passe.
    Utilise HMAC-SHA256 avec pepper pour le hachage des emails (privacy).
    Intègre un délai artificiel de 1.5s sur les échecs d'authentification (anti-brute-force).
    """

    ITERATIONS = 600_000
    KEY_LENGTH = 32
    AUTH_FAILURE_DELAY = 1.5  # Secondes

    def __init__(self, users_db_path: Path, totp_service=None):
        """Initialise le service d'authentification.

        Args:
            users_db_path: Chemin vers la base de données SQLite des utilisateurs
            totp_service: Service TOTP (optionnel, pour tests)
        """
        self.db_path = users_db_path
        self.data_dir = users_db_path.parent
        self.conn = sqlite3.connect(str(users_db_path))
        self.totp_service = totp_service

        # Charger ou créer le pepper pour HMAC des emails
        self._email_pepper = self._get_or_create_email_pepper()

        self._init_db()

    def _get_or_create_email_pepper(self) -> bytes:
        """Récupère ou crée le pepper pour le hachage HMAC des emails.

        Returns:
            Pepper de 32 bytes
        """
        pepper_file = self.data_dir / ".email_pepper"

        if pepper_file.exists():
            pepper = pepper_file.read_bytes()
            logger.debug("Pepper email existant chargé")
        else:
            pepper = secrets.token_bytes(32)
            pepper_file.write_bytes(pepper)
            pepper_file.chmod(0o600)
            logger.info("Pepper email créé avec permissions 600")

        return pepper

    def hash_email(self, email: str) -> str:
        """Hash un email avec HMAC-SHA256 et pepper.

        Protection contre les attaques par dictionnaire sur users.db.

        Args:
            email: Email en clair

        Returns:
            Hash HMAC-SHA256 en hexadécimal
        """
        email_hash = hmac.new(
            self._email_pepper,
            email.lower().encode(),
            hashlib.sha256
        ).hexdigest()
        return email_hash

    def _init_db(self):
        """Initialise la base de données des utilisateurs."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        self.conn.commit()

        # Créer un utilisateur admin par défaut si aucun utilisateur n'existe
        cursor.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] == 0:
            self.create_user('admin', 'admin', role='admin')
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        logger.info("AuthService: %d comptes utilisateurs disponibles", total_users)

    def _hash_password(self, password: str, salt: bytes = None) -> tuple:
        """Hache un mot de passe avec PBKDF2HMAC.

        Args:
            password: Mot de passe en clair
            salt: Salt à utiliser (généré automatiquement si None)

        Returns:
            Tuple (password_hash_b64, salt_b64)
        """
        if salt is None:
            salt = secrets.token_bytes(32)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=salt,
            iterations=self.ITERATIONS,
            backend=default_backend()
        )
        password_hash = kdf.derive(password.encode())
        return base64.b64encode(password_hash).decode(), base64.b64encode(salt).decode()

    def create_user(self, username: str, password: str, role: str = 'user') -> bool:
        """Crée un nouvel utilisateur.

        Args:
            username: Nom d'utilisateur unique
            password: Mot de passe maître de l'utilisateur
            role: 'admin' ou 'user'

        Returns:
            True si création réussie, False si l'utilisateur existe déjà
        """
        try:
            password_hash, salt = self._hash_password(password)
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, password_hash, salt, role)
                VALUES (?, ?, ?, ?)
            ''', (username, password_hash, salt, role))
            self.conn.commit()
            logger.info("AuthService: utilisateur cree %s (role=%s)", username, role)
            return True
        except sqlite3.IntegrityError:
            logger.warning("AuthService: utilisateur deja existant %s", username)
            return False

    def authenticate(self, username: str, password: str) -> dict | None:
        """Authentifie un utilisateur.

        Args:
            username: Nom d'utilisateur
            password: Mot de passe maître

        Returns:
            Dictionnaire avec les infos utilisateur si succès, None sinon
            {'id', 'username', 'role', 'salt'}
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, salt, role
            FROM users WHERE username = ?
        ''', (username,))
        row = cursor.fetchone()

        if not row:
            logger.warning(
                "AuthService: authentification echouee, utilisateur inconnu %s", username
            )
            return None

        user_id, username, stored_hash, salt_b64, role = row
        salt = base64.b64decode(salt_b64)
        password_hash, _ = self._hash_password(password, salt)

        if password_hash == stored_hash:
            # Mettre à jour la date de dernière connexion
            cursor.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))
            self.conn.commit()
            logger.info("AuthService: authentification reussie %s (role=%s)", username, role)

            return {
                'id': user_id,
                'username': username,
                'role': role,
                'salt': salt
            }
        logger.warning(
            "AuthService: authentification echouee, mauvais mot de passe pour %s", username
        )
        return None

    def verify_user(self, username: str, password: str) -> bool:
        """Vérifie le mot de passe d'un utilisateur sans authentifier.

        Args:
            username: Nom d'utilisateur
            password: Mot de passe à vérifier

        Returns:
            True si le mot de passe est correct
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT password_hash, salt
            FROM users WHERE username = ?
        ''', (username,))
        row = cursor.fetchone()

        if not row:
            logger.debug("AuthService: verification echouee, utilisateur inconnu %s", username)
            return False

        stored_hash, salt_b64 = row
        salt = base64.b64decode(salt_b64)
        password_hash, _ = self._hash_password(password, salt)
        result = password_hash == stored_hash
        logger.debug("AuthService: verification %s -> %s", username, result)
        return result

    def change_user_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Change le mot de passe d'un utilisateur après vérification de l'ancien.

        Args:
            username: Nom de l'utilisateur
            old_password: Ancien mot de passe (pour vérification)
            new_password: Nouveau mot de passe

        Returns:
            True si succès
        """
        # Vérifier l'ancien mot de passe
        if not self.verify_user(username, old_password):
            logger.warning("AuthService: ancien mot de passe incorrect pour %s", username)
            return False

        try:
            # Générer un nouveau sel et hasher le nouveau mot de passe
            password_hash, salt = self._hash_password(new_password)
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE username = ?
            ''', (password_hash, salt, username))
            self.conn.commit()
            success = cursor.rowcount > 0
            logger.info("AuthService: mot de passe change pour %s", username)
            return success
        except Exception:
            logger.exception(
                "AuthService: erreur lors du changement de mot de passe pour %s", username
            )
            return False

    def reset_user_password(self, username: str, new_password: str) -> bool:
        """Réinitialise le mot de passe d'un utilisateur (admin uniquement).

        Args:
            username: Nom de l'utilisateur à réinitialiser
            new_password: Nouveau mot de passe

        Returns:
            True si succès
        """
        try:
            password_hash, salt = self._hash_password(new_password)
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE username = ?
            ''', (password_hash, salt, username))
            self.conn.commit()
            success = cursor.rowcount > 0
            logger.info("AuthService: mot de passe reinitialise pour %s", username)
            return success
        except Exception:
            logger.exception("AuthService: erreur lors de la reinitialisation pour %s", username)
            return False

    def delete_user(self, username: str) -> bool:
        """Supprime un utilisateur (admin uniquement).

        Args:
            username: Nom de l'utilisateur à supprimer

        Returns:
            True si succès
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM users WHERE username = ?', (username,))
            self.conn.commit()
            success = cursor.rowcount > 0
            logger.info("AuthService: utilisateur supprime %s", username)
            return success
        except Exception:
            logger.exception("AuthService: erreur lors de la suppression de %s", username)
            return False

    def get_all_users(self) -> list:
        """Récupère tous les utilisateurs (pour l'admin).

        Returns:
            Liste de tuples (username, role, created_at, last_login)
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT username, role, created_at, last_login
            FROM users
            ORDER BY username
        ''')
        users = cursor.fetchall()
        logger.debug("AuthService: %d utilisateurs recus", len(users))
        return users

    def user_exists(self, username: str) -> bool:
        """Vérifie si un utilisateur existe.

        Args:
            username: Nom d'utilisateur à vérifier

        Returns:
            True si l'utilisateur existe
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', (username,))
        exists = cursor.fetchone()[0] > 0
        logger.debug("AuthService: utilisateur %s existe=%s", username, exists)
        return exists

    # ========== NOUVELLES MÉTHODES POUR EMAIL + TOTP ==========

    def is_migration_email(self, email: str) -> bool:
        """Détecte si c'est un email temporaire de migration.

        Args:
            email: Email à vérifier

        Returns:
            True si c'est un email de migration (*.@migration.local)
        """
        return email.endswith('@migration.local')

    def email_exists(self, email: str) -> bool:
        """Vérifie si un email existe déjà.

        Args:
            email: Email à vérifier

        Returns:
            True si l'email existe
        """
        email_hash = self.hash_email(email)
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE email_hash = ?', (email_hash,))
        exists = cursor.fetchone()[0] > 0
        logger.debug("AuthService: email existe=%s", exists)
        return exists

    def get_user_by_email(self, email: str) -> dict | None:
        """Récupère les informations d'un utilisateur par email.

        Args:
            email: Email de l'utilisateur

        Returns:
            Dictionnaire avec les infos utilisateur ou None
        """
        email_hash = self.hash_email(email)
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, username, email, role, workspace_uuid, totp_enabled, totp_confirmed,
                   created_at, last_login
            FROM users
            WHERE email_hash = ?
        ''', (email_hash,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'role': row[3],
            'workspace_uuid': row[4],
            'totp_enabled': bool(row[5]),
            'totp_confirmed': bool(row[6]),
            'created_at': row[7],
            'last_login': row[8]
        }

    def authenticate_by_email(
        self, email: str, password: str, enforce_delay: bool = True
    ) -> dict | None:
        """Authentifie un utilisateur par email (première étape avant TOTP).

        Args:
            email: Email de l'utilisateur
            password: Mot de passe maître
            enforce_delay: Si True, applique un délai sur échec (anti-brute-force)

        Returns:
            Dictionnaire avec les infos utilisateur si succès, None sinon
            {'id', 'username', 'email', 'role', 'workspace_uuid', 'totp_enabled', 'salt'}
        """
        email_hash = self.hash_email(email)
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, username, email, password_hash, salt, role, workspace_uuid,
                   totp_enabled, totp_confirmed
            FROM users
            WHERE email_hash = ?
        ''', (email_hash,))
        row = cursor.fetchone()

        if not row:
            logger.warning("AuthService: authentification echouee, email inconnu")
            if enforce_delay:
                time.sleep(self.AUTH_FAILURE_DELAY)
            return None

        (
            user_id, username, email_stored, stored_hash, salt_b64, role,
            workspace_uuid, totp_enabled, totp_confirmed
        ) = row
        salt = base64.b64decode(salt_b64)
        password_hash, _ = self._hash_password(password, salt)

        if password_hash == stored_hash:
            # Mettre à jour la date de dernière connexion
            cursor.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))
            self.conn.commit()
            logger.info("AuthService: authentification reussie pour %s (role=%s)", email, role)

            return {
                'id': user_id,
                'username': username,
                'email': email_stored,
                'role': role,
                'workspace_uuid': workspace_uuid,
                'totp_enabled': bool(totp_enabled),
                'totp_confirmed': bool(totp_confirmed),
                'salt': salt
            }

        logger.warning("AuthService: authentification echouee, mauvais mot de passe pour %s", email)
        if enforce_delay:
            time.sleep(self.AUTH_FAILURE_DELAY)
        return None

    def update_user_email(self, user_id: int, new_email: str) -> bool:
        """Met à jour l'email d'un utilisateur (post-migration).

        Args:
            user_id: ID de l'utilisateur
            new_email: Nouvel email

        Returns:
            True si succès
        """
        # Valider l'email
        if not validators.email(new_email):
            logger.warning("AuthService: email invalide : %s", new_email)
            return False

        # Hasher le nouvel email
        new_email_hash = self.hash_email(new_email)

        # Vérifier que l'email n'est pas déjà pris
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE email_hash = ? AND id != ?',
                      (new_email_hash, user_id))
        if cursor.fetchone()[0] > 0:
            logger.warning("AuthService: email deja utilise : %s", new_email)
            return False

        # Mettre à jour
        try:
            cursor.execute('''
                UPDATE users
                SET email = ?, email_hash = ?
                WHERE id = ?
            ''', (new_email, new_email_hash, user_id))
            self.conn.commit()
            logger.info("AuthService: email mis a jour pour user_id=%d", user_id)
            return True
        except Exception:
            logger.exception("AuthService: erreur lors de la mise a jour email")
            return False

    def setup_2fa(self, user_id: int, secret_encrypted: str, backup_codes_encrypted: str) -> bool:
        """Configure le 2FA pour un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            secret_encrypted: Secret TOTP chiffré (JSON)
            backup_codes_encrypted: Codes de secours chiffrés (JSON)

        Returns:
            True si succès
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE users
                SET secret_2fa = ?,
                    backup_codes = ?,
                    totp_enabled = 1,
                    totp_confirmed = 0
                WHERE id = ?
            ''', (secret_encrypted, backup_codes_encrypted, user_id))
            self.conn.commit()
            logger.info("AuthService: 2FA configure pour user_id=%d", user_id)
            return True
        except Exception:
            logger.exception("AuthService: erreur lors de la configuration 2FA")
            return False

    def confirm_2fa(self, user_id: int) -> bool:
        """Confirme que le 2FA est actif et fonctionnel.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            True si succès
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE users
                SET totp_confirmed = 1
                WHERE id = ?
            ''', (user_id,))
            self.conn.commit()
            logger.info("AuthService: 2FA confirme pour user_id=%d", user_id)
            return True
        except Exception:
            logger.exception("AuthService: erreur lors de la confirmation 2FA")
            return False

    def get_2fa_secret(self, user_id: int) -> str | None:
        """Récupère le secret TOTP chiffré d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            Secret chiffré (JSON) ou None
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT secret_2fa FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()

        if row and row[0]:
            return row[0]
        return None

    def get_backup_codes(self, user_id: int) -> str | None:
        """Récupère les codes de secours chiffrés d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            Codes chiffrés (JSON) ou None
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT backup_codes FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()

        if row and row[0]:
            return row[0]
        return None

    def update_backup_codes(self, user_id: int, backup_codes_encrypted: str) -> bool:
        """Met à jour les codes de secours (après utilisation).

        Args:
            user_id: ID de l'utilisateur
            backup_codes_encrypted: Codes mis à jour (JSON)

        Returns:
            True si succès
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE users
                SET backup_codes = ?
                WHERE id = ?
            ''', (backup_codes_encrypted, user_id))
            self.conn.commit()
            logger.info("AuthService: codes de secours mis a jour pour user_id=%d", user_id)
            return True
        except Exception:
            logger.exception("AuthService: erreur lors de la mise a jour des codes de secours")
            return False

    def create_user_with_email(self, email: str, password: str, username: str = None,
                                role: str = 'user') -> int | None:
        """Crée un nouvel utilisateur avec email (nouveau système).

        Args:
            email: Email de l'utilisateur
            password: Mot de passe maître
            username: Nom d'utilisateur (optionnel, généré si None)
            role: 'admin' ou 'user'

        Returns:
            ID de l'utilisateur créé ou None en cas d'erreur
        """
        import uuid as uuid_module

        # Valider l'email
        if not validators.email(email):
            logger.warning("AuthService: email invalide : %s", email)
            return None

        # Vérifier que l'email n'existe pas déjà
        if self.email_exists(email):
            logger.warning("AuthService: email deja existant : %s", email)
            return None

        # Générer un username si non fourni
        if username is None:
            username = email.split('@')[0]
            # S'assurer de l'unicité
            base_username = username
            counter = 1
            while self.user_exists(username):
                username = f"{base_username}{counter}"
                counter += 1

        # Générer un UUID pour le workspace
        workspace_uuid = str(uuid_module.uuid4())

        # Hasher l'email et le mot de passe
        email_hash = self.hash_email(email)
        password_hash, salt = self._hash_password(password)

        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, email, email_hash, password_hash, salt,
                                   role, workspace_uuid, totp_enabled, totp_confirmed)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''', (username, email, email_hash, password_hash, salt, role, workspace_uuid))
            self.conn.commit()
            user_id = cursor.lastrowid
            logger.info("AuthService: utilisateur cree %s (%s) - role=%s", username, email, role)
            return user_id
        except sqlite3.IntegrityError:
            logger.warning("AuthService: erreur creation utilisateur (contrainte unique)")
            return None
        except Exception:
            logger.exception("AuthService: erreur creation utilisateur")
            return None

    def close(self):
        """Ferme la connexion à la base de données."""
        self.conn.close()
        logger.debug("AuthService: connexion aux utilisateurs fermee")
