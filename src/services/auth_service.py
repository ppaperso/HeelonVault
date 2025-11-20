"""Service d'authentification et gestion des utilisateurs.

Ce module gère :
- L'authentification des utilisateurs
- Le hachage sécurisé des mots de passe (PBKDF2HMAC)
- La création et suppression d'utilisateurs
- Le changement et la réinitialisation de mots de passe
"""

import sqlite3
import secrets
import base64
import logging
from pathlib import Path
from typing import Optional, Dict
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class AuthService:
    """Service d'authentification et gestion des utilisateurs.
    
    Utilise PBKDF2HMAC avec 600 000 itérations pour le hachage des mots de passe.
    """
    
    ITERATIONS = 600_000
    KEY_LENGTH = 32
    
    def __init__(self, users_db_path: Path):
        """Initialise le service d'authentification.
        
        Args:
            users_db_path: Chemin vers la base de données SQLite des utilisateurs
        """
        self.db_path = users_db_path
        self.conn = sqlite3.connect(str(users_db_path))
        self._init_db()
    
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
    
    def authenticate(self, username: str, password: str) -> Optional[Dict]:
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
            logger.warning("AuthService: authentification echouee, utilisateur inconnu %s", username)
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
        logger.warning("AuthService: authentification echouee, mauvais mot de passe pour %s", username)
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
        except Exception as e:
            logger.exception("AuthService: erreur lors du changement de mot de passe pour %s", username)
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
        except Exception as e:
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
        except Exception as e:
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
    
    def close(self):
        """Ferme la connexion à la base de données."""
        self.conn.close()
        logger.debug("AuthService: connexion aux utilisateurs fermee")
