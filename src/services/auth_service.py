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
import uuid
from datetime import datetime
from pathlib import Path
from typing import cast

import validators
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.models.user_info import UserInfo

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
    DEFAULT_ADMIN_EMAIL = "admin@local.heelonvault"

    _USER_COLUMNS: dict[str, str] = {
        "email": "TEXT",
        "email_hash": "TEXT",
        "workspace_uuid": "TEXT",
        "secret_2fa": "TEXT",
        "totp_enabled": "INTEGER DEFAULT 0",
        "totp_confirmed": "INTEGER DEFAULT 0",
        "backup_codes": "TEXT",
        "last_password_change": "TIMESTAMP",
        "failed_login_attempts": "INTEGER DEFAULT 0",
        "last_failed_attempt": "TIMESTAMP",
        "account_locked_until": "TIMESTAMP",
        "avatar_path": "TEXT",
    }

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
            logger.debug("Existing email pepper loaded")
        else:
            pepper = secrets.token_bytes(32)
            pepper_file.write_bytes(pepper)
            pepper_file.chmod(0o600)
            logger.info("Email pepper created with 600 permissions")

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
                email TEXT,
                email_hash TEXT,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                workspace_uuid TEXT,
                secret_2fa TEXT,
                totp_enabled INTEGER DEFAULT 0,
                totp_confirmed INTEGER DEFAULT 0,
                backup_codes TEXT,
                last_password_change TIMESTAMP,
                failed_login_attempts INTEGER DEFAULT 0,
                last_failed_attempt TIMESTAMP,
                account_locked_until TIMESTAMP,
                avatar_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')

        self._ensure_user_profile_columns(cursor)

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_hash ON users(email_hash)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_workspace_uuid ON users(workspace_uuid)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        self.conn.commit()

        self._backfill_legacy_users(cursor)
        self.conn.commit()

        # Créer un utilisateur admin par défaut si aucun utilisateur n'existe
        cursor.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] == 0:
            self.create_user_with_email(
                self.DEFAULT_ADMIN_EMAIL,
                'admin',
                username='admin',
                role='admin',
            )
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        logger.info("AuthService: %d user accounts available", total_users)

    def _ensure_user_profile_columns(self, cursor) -> None:
        """Ajoute les colonnes de profil manquantes sur les bases existantes."""
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        for column_name, column_type in self._USER_COLUMNS.items():
            if column_name not in existing_columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")

        self.conn.commit()

    def _backfill_legacy_users(self, cursor) -> None:
        """Complète email/email_hash/workspace_uuid pour les comptes legacy."""
        cursor.execute(
            '''
            SELECT id, username, email, email_hash, workspace_uuid
            FROM users
            '''
        )
        rows = cursor.fetchall()

        for user_id, username, email, email_hash, workspace_uuid in rows:
            update_values: dict[str, str] = {}

            resolved_email = (email or "").strip()
            if not resolved_email:
                resolved_email = f"{username}@migration.local"
                update_values["email"] = resolved_email

            if not email_hash:
                update_values["email_hash"] = self.hash_email(resolved_email)

            if not workspace_uuid:
                update_values["workspace_uuid"] = str(uuid.uuid4())

            if not update_values:
                continue

            if "email" in update_values:
                cursor.execute(
                    "UPDATE users SET email = ? WHERE id = ?",
                    (update_values["email"], user_id),
                )
            if "email_hash" in update_values:
                cursor.execute(
                    "UPDATE users SET email_hash = ? WHERE id = ?",
                    (update_values["email_hash"], user_id),
                )
            if "workspace_uuid" in update_values:
                cursor.execute(
                    "UPDATE users SET workspace_uuid = ? WHERE id = ?",
                    (update_values["workspace_uuid"], user_id),
                )
            logger.info(
                "AuthService: profile migration applied for %s (id=%d)",
                username,
                user_id,
            )

    def _hash_password(self, password: str, salt: bytes | None=None) -> tuple:
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
            migration_email = f"{username}@migration.local"
            if self.email_exists(migration_email):
                logger.warning(
                    "AuthService: migration email already exists for %s",
                    username,
                )
                return False

            workspace_uuid = str(uuid.uuid4())
            email_hash = self.hash_email(migration_email)
            password_hash, salt = self._hash_password(password)
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO users (
                    username, email, email_hash, password_hash, salt,
                    role, workspace_uuid, totp_enabled, totp_confirmed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''', (username, migration_email, email_hash, password_hash, salt, role, workspace_uuid))
            self.conn.commit()
            logger.info("AuthService: user created %s (role=%s)", username, role)
            return True
        except sqlite3.IntegrityError:
            logger.warning("AuthService: user already exists %s", username)
            return False

    def authenticate(self, username: str, password: str) -> UserInfo | None:
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
            SELECT id, username, password_hash, salt, role, last_login
            FROM users WHERE username = ?
        ''', (username,))
        row = cursor.fetchone()

        if not row:
            logger.warning(
                "AuthService: authentication failed, unknown user %s", username
            )
            return None

        user_id, username, stored_hash, salt_b64, role, previous_last_login = row
        salt = base64.b64decode(salt_b64)
        password_hash, _ = self._hash_password(password, salt)

        if password_hash == stored_hash:
            # Mettre à jour la date de dernière connexion
            cursor.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))
            cursor.execute(
                "INSERT INTO login_events (user_id) VALUES (?)",
                (user_id,),
            )
            self.conn.commit()
            logger.info("AuthService: authentication succeeded %s (role=%s)", username, role)

            return cast(UserInfo, {
                'id': user_id,
                'username': username,
                'role': role,
                'salt': salt,
                'last_login_previous': previous_last_login,
                'login_count_today': self._get_login_count_today(user_id),
            })
        logger.warning(
            "AuthService: authentication failed, invalid password for %s",
            username,
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
            logger.debug("AuthService: verification failed, unknown user %s", username)
            return False

        stored_hash, salt_b64 = row
        salt = base64.b64decode(salt_b64)
        password_hash, _ = self._hash_password(password, salt)
        result = password_hash == stored_hash
        logger.debug("AuthService: verification result %s -> %s", username, result)
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
            logger.warning("AuthService: invalid current password for %s", username)
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
            logger.info("AuthService: password changed for %s", username)
            return success
        except sqlite3.Error:
            logger.exception(
                "AuthService: error while changing password for %s",
                username,
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
            logger.info("AuthService: password reset for %s", username)
            return success
        except sqlite3.Error:
            logger.exception("AuthService: error while resetting password for %s", username)
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
            logger.info("AuthService: user deleted %s", username)
            return success
        except sqlite3.Error:
            logger.exception("AuthService: error while deleting %s", username)
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
        logger.debug("AuthService: %d users fetched", len(users))
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
        logger.debug("AuthService: user %s exists=%s", username, exists)
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
        logger.debug("AuthService: email exists=%s", exists)
        return exists

    def get_user_by_email(self, email: str) -> UserInfo | None:
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
                   created_at, last_login, avatar_path
            FROM users
            WHERE email_hash = ?
        ''', (email_hash,))
        row = cursor.fetchone()

        if not row:
            return None

        return cast(UserInfo, {
            'id': row[0],
            'username': row[1],
            'email': row[2],
            'role': row[3],
            'workspace_uuid': row[4],
            'totp_enabled': bool(row[5]),
            'totp_confirmed': bool(row[6]),
            'created_at': row[7],
            'last_login': row[8],
            'avatar_path': row[9],
        })

    def authenticate_by_email(
        self, email: str, password: str, enforce_delay: bool = True
    ) -> UserInfo | None:
        """Authentifie un utilisateur par email (première étape avant TOTP).

        Args:
            email: Email de l'utilisateur
            password: Mot de passe maître
            enforce_delay: Si True, applique un délai sur échec (anti-brute-force)

        Returns:
            Dictionnaire avec les infos utilisateur si succès, None sinon
            {'id', 'username', 'email', 'role', 'workspace_uuid', 'totp_enabled', 'salt'}
        """
        normalized_input = email.strip().lower()
        email_hash = self.hash_email(normalized_input)
        cursor = self.conn.cursor()
        cursor.execute('''
             SELECT id, username, email, password_hash, salt, role, workspace_uuid,
                 totp_enabled, totp_confirmed, last_login, avatar_path
            FROM users
            WHERE email_hash = ?
        ''', (email_hash,))
        row = cursor.fetchone()

        # Rétrocompatibilité : autoriser aussi la connexion par username
        if not row and '@' not in normalized_input:
            cursor.execute(
                '''
                SELECT id, username, email, password_hash, salt, role, workspace_uuid,
                       totp_enabled, totp_confirmed, last_login, avatar_path
                FROM users
                WHERE lower(username) = ?
                ''',
                (normalized_input,),
            )
            row = cursor.fetchone()

        if not row:
            logger.warning("AuthService: authentication failed, unknown email")
            if enforce_delay:
                time.sleep(self.AUTH_FAILURE_DELAY)
            return None

        (
            user_id,
            username,
            email_stored,
            stored_hash,
            salt_b64,
            role,
            workspace_uuid,
            totp_enabled,
            totp_confirmed,
            previous_last_login,
            avatar_path,
        ) = row
        salt = base64.b64decode(salt_b64)
        password_hash, _ = self._hash_password(password, salt)

        if password_hash == stored_hash:
            # Mettre à jour la date de dernière connexion
            cursor.execute('''
                UPDATE users SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))
            cursor.execute(
                "INSERT INTO login_events (user_id) VALUES (?)",
                (user_id,),
            )
            self.conn.commit()
            logger.info(
                "AuthService: authentication succeeded for %s (role=%s)",
                normalized_input,
                role,
            )

            return cast( UserInfo, {
                'id': user_id,
                'username': username,
                'email': email_stored,
                'role': role,
                'workspace_uuid': workspace_uuid,
                'totp_enabled': bool(totp_enabled),
                'totp_confirmed': bool(totp_confirmed),
                'salt': salt,
                'last_login_previous': previous_last_login,
                'last_login': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'login_count_today': self._get_login_count_today(user_id),
                'avatar_path': avatar_path,
            })

        logger.warning(
            "AuthService: authentication failed, invalid password for %s",
            normalized_input,
        )
        if enforce_delay:
            time.sleep(self.AUTH_FAILURE_DELAY)
        return None

    def _get_login_count_today(self, user_id: int) -> int:
        """Retourne le nombre de connexions réussies de l'utilisateur aujourd'hui."""
        cursor = self.conn.cursor()
        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM login_events
            WHERE user_id = ?
              AND date(login_at, 'localtime') = date('now', 'localtime')
            ''',
            (user_id,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

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
            logger.warning("AuthService: invalid email: %s", new_email)
            return False

        # Hasher le nouvel email
        new_email_hash = self.hash_email(new_email)

        # Vérifier que l'email n'est pas déjà pris
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE email_hash = ? AND id != ?',
                      (new_email_hash, user_id))
        if cursor.fetchone()[0] > 0:
            logger.warning("AuthService: email already used: %s", new_email)
            return False

        # Mettre à jour
        try:
            cursor.execute('''
                UPDATE users
                SET email = ?, email_hash = ?
                WHERE id = ?
            ''', (new_email, new_email_hash, user_id))
            self.conn.commit()
            logger.info("AuthService: email updated for user_id=%d", user_id)
            return True
        except sqlite3.Error:
            logger.exception("AuthService: error while updating email")
            return False

    def update_username(self, user_id: int, new_username: str) -> bool:
        """Met à jour le nom affiché/utilisateur d'un compte."""
        cleaned = new_username.strip()
        if len(cleaned) < 3:
            logger.warning("AuthService: username too short")
            return False

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE username = ? AND id != ?",
            (cleaned, user_id),
        )
        if cursor.fetchone()[0] > 0:
            logger.warning("AuthService: username already used: %s", cleaned)
            return False

        try:
            cursor.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (cleaned, user_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error:
            logger.exception("AuthService: error while updating username")
            return False

    def update_avatar_path(self, user_id: int, avatar_path: str | None) -> bool:
        """Met à jour le chemin d'avatar d'un utilisateur."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET avatar_path = ? WHERE id = ?",
                (avatar_path, user_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error:
            logger.exception("AuthService: error while updating avatar")
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
            logger.info("AuthService: 2FA configured for user_id=%d", user_id)
            return True
        except sqlite3.Error:
            logger.exception("AuthService: error while configuring 2FA")
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
            logger.info("AuthService: 2FA confirmed for user_id=%d", user_id)
            return True
        except sqlite3.Error:
            logger.exception("AuthService: error while confirming 2FA")
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
            logger.info("AuthService: backup codes updated for user_id=%d", user_id)
            return True
        except sqlite3.Error:
            logger.exception("AuthService: error while updating backup codes")
            return False

    def create_user_with_email(self, email: str, password: str, username: str | None=None,
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
            logger.warning("AuthService: invalid email: %s", email)
            return None

        # Vérifier que l'email n'existe pas déjà
        if self.email_exists(email):
            logger.warning("AuthService: email already exists: %s", email)
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
            logger.info(
                "AuthService: user created %s (%s) - role=%s",
                username,
                email,
                role,
            )
            return user_id
        except sqlite3.IntegrityError:
            logger.warning("AuthService: user creation error (unique constraint)")
            return None
        except sqlite3.Error:
            logger.exception("AuthService: user creation error")
            return None

    def close(self):
        """Ferme la connexion à la base de données."""
        self.conn.close()
        logger.debug("AuthService: user database connection closed")
