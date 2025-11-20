#!/usr/bin/env python3
"""
Gestionnaire de mots de passe sécurisé pour Linux
Architecture: GTK4 + Python + Chiffrement AES-256
Fonctionnalités: Générateur de mots de passe, Catégories/Tags
"""

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio

import sqlite3
import json
import secrets
import string
import hashlib
import logging
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64
from datetime import datetime

# Imports pour l'import CSV
from src.services.csv_importer import CSVImporter
from src.ui.dialogs.import_dialog import ImportCSVDialog
from src.ui.dialogs.helpers import present_alert
from src.ui.dialogs.entry_details_dialog import EntryDetailsDialog
from src.ui.dialogs.add_edit_dialog import AddEditDialog
from src.ui.dialogs.password_generator_dialog import PasswordGeneratorDialog

# Imports pour la version et À propos
from src.version import get_version, get_version_info
from src.ui.dialogs.about_dialog import show_about_dialog
from src.config.environment import get_data_directory, is_dev_mode
from src.config.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

DATA_DIR = get_data_directory()

class UserManager:
    """Gestion des utilisateurs et authentification"""
    
    def __init__(self, users_db_path: Path):
        self.db_path = users_db_path
        self.conn = sqlite3.connect(str(users_db_path))
        self._init_db()
        logger.debug("UserManager initialise avec DB %s", users_db_path)
    
    def _init_db(self):
        """Initialise la base de données des utilisateurs"""
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
        logger.debug("Structure de la base initialisee pour %s", self.db_path)
        
        # Créer un utilisateur admin par défaut si aucun utilisateur n'existe
        cursor.execute('SELECT COUNT(*) FROM users')
        current_users = cursor.fetchone()[0]
        if current_users == 0:
            self.create_user('admin', 'admin', role='admin')
            cursor.execute('SELECT COUNT(*) FROM users')
            current_users = cursor.fetchone()[0]
        logger.info("Base utilisateurs initialisee (%d comptes)", current_users)
    
    def _hash_password(self, password: str, salt: bytes = None) -> tuple:
        """Hash un mot de passe avec PBKDF2"""
        if salt is None:
            salt = secrets.token_bytes(32)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,
            backend=default_backend()
        )
        password_hash = kdf.derive(password.encode())
        return base64.b64encode(password_hash).decode(), base64.b64encode(salt).decode()
    
    def create_user(self, username: str, password: str, role: str = 'user') -> bool:
        """Crée un nouvel utilisateur
        
        Args:
            username: Nom d'utilisateur unique
            password: Mot de passe maître de l'utilisateur
            role: 'admin' ou 'user'
            
        Returns:
            bool: True si création réussie, False si l'utilisateur existe déjà
        """
        try:
            password_hash, salt = self._hash_password(password)
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, password_hash, salt, role)
                VALUES (?, ?, ?, ?)
            ''', (username, password_hash, salt, role))
            self.conn.commit()
            logger.info("Utilisateur cree: %s (role=%s)", username, role)
            return True
        except sqlite3.IntegrityError:
            logger.warning("Utilisateur deja existant: %s", username)
            return False
    
    def authenticate(self, username: str, password: str) -> dict:
        """Authentifie un utilisateur
        
        Args:
            username: Nom d'utilisateur
            password: Mot de passe maître
            
        Returns:
            dict: Informations utilisateur si succès, None sinon
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, salt, role 
            FROM users WHERE username = ?
        ''', (username,))
        row = cursor.fetchone()
        
        if not row:
            logger.warning("Authentification echouee: utilisateur inconnu %s", username)
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
            logger.info("Authentification reussie: %s", username)
            return {
                'id': user_id,
                'username': username,
                'role': role,
                'salt': salt
            }
        logger.warning("Authentification echouee: mauvais mot de passe pour %s", username)
        return None
    
    def get_all_users(self) -> list:
        """Récupère tous les utilisateurs (pour l'admin)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT username, role, created_at, last_login 
            FROM users 
            ORDER BY username
        ''')
        users = cursor.fetchall()
        logger.debug("Recuperation de %d utilisateurs", len(users))
        return users
    
    def verify_user(self, username: str, password: str) -> bool:
        """Vérifie le mot de passe d'un utilisateur sans authentifier
        
        Args:
            username: Nom d'utilisateur
            password: Mot de passe à vérifier
            
        Returns:
            bool: True si le mot de passe est correct
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT password_hash, salt 
            FROM users WHERE username = ?
        ''', (username,))
        row = cursor.fetchone()
        
        if not row:
            logger.debug("Verification echouee: utilisateur inconnu %s", username)
            return False
        
        stored_hash, salt_b64 = row
        salt = base64.b64decode(salt_b64)
        password_hash, _ = self._hash_password(password, salt)
        result = password_hash == stored_hash
        logger.debug("Verification utilisateur %s: %s", username, result)
        return result
    
    def change_user_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Change le mot de passe d'un utilisateur après vérification de l'ancien
        
        Args:
            username: Nom de l'utilisateur
            old_password: Ancien mot de passe (pour vérification)
            new_password: Nouveau mot de passe
            
        Returns:
            bool: True si succès
        """
        # Vérifier l'ancien mot de passe
        if not self.verify_user(username, old_password):
            logger.warning(
                "Changement de mot de passe bloque: ancien mot de passe incorrect pour %s",
                username
            )
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
            if success:
                logger.info("Mot de passe change pour %s", username)
            else:
                logger.warning("Aucune ligne mise a jour pour %s", username)
            return success
        except Exception as e:
            logger.exception("Erreur lors du changement de mot de passe pour %s", username)
            return False
    
    def reset_user_password(self, username: str, new_password: str) -> bool:
        """Réinitialise le mot de passe d'un utilisateur (admin uniquement)
        
        Args:
            username: Nom de l'utilisateur à réinitialiser
            new_password: Nouveau mot de passe
            
        Returns:
            bool: True si succès
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
            if success:
                logger.info("Mot de passe reinitialise pour %s", username)
            else:
                logger.warning("Aucune ligne modifiee pour la reinitialisation de %s", username)
            return success
        except Exception as e:
            logger.exception("Erreur lors de la reinitialisation du mot de passe pour %s", username)
            return False
    
    def delete_user(self, username: str) -> bool:
        """Supprime un utilisateur (admin uniquement)"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM users WHERE username = ?', (username,))
            self.conn.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info("Utilisateur supprime: %s", username)
            else:
                logger.warning("Aucune ligne supprimee pour %s", username)
            return success
        except Exception as e:
            logger.exception("Erreur lors de la suppression de %s", username)
            return False
    
    def user_exists(self, username: str) -> bool:
        """Vérifie si un utilisateur existe"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', (username,))
        exists = cursor.fetchone()[0] > 0
        logger.debug("Utilisateur %s existe: %s", username, exists)
        return exists
    
    def close(self):
        self.conn.close()
        logger.debug("Connexion a la base %s fermee", self.db_path)


class PasswordGenerator:
    """Générateur de mots de passe sécurisés"""
    
    @staticmethod
    def generate(length=16, use_uppercase=True, use_lowercase=True, 
                 use_digits=True, use_symbols=True, exclude_ambiguous=True):
        """Génère un mot de passe aléatoire sécurisé"""
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
        return password
    
    @staticmethod
    def generate_passphrase(word_count=4, separator="-"):
        """Génère une phrase de passe mémorisable"""
        # Liste de mots courants en français
        words = [
            "maison", "soleil", "jardin", "montagne", "riviere", "foret",
            "ocean", "nuage", "etoile", "lumiere", "ombre", "chemin",
            "arbre", "fleur", "pierre", "vent", "pluie", "neige",
            "feu", "eau", "terre", "ciel", "lune", "jour", "nuit",
            "libre", "joie", "paix", "force", "sage", "beau",
            "grand", "petit", "nouveau", "ancien", "rapide", "lent",
            "rouge", "bleu", "vert", "jaune", "noir", "blanc"
        ]
        
        chosen_words = [secrets.choice(words) for _ in range(word_count)]
        # Capitaliser aléatoirement certains mots
        chosen_words = [w.capitalize() if secrets.randbelow(2) else w for w in chosen_words]
        # Ajouter un chiffre à la fin
        return separator.join(chosen_words) + str(secrets.randbelow(100))

class PasswordCrypto:
    """Gestion du chiffrement/déchiffrement"""
    
    def __init__(self, master_password: str, salt: bytes = None):
        if salt is None:
            salt = secrets.token_bytes(32)
        self.salt = salt
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,
            backend=default_backend()
        )
        self.key = kdf.derive(master_password.encode())
        self.cipher = AESGCM(self.key)
    
    def encrypt(self, plaintext: str) -> dict:
        """Chiffre un texte avec AES-256-GCM"""
        nonce = secrets.token_bytes(12)
        ciphertext = self.cipher.encrypt(nonce, plaintext.encode(), None)
        return {
            'nonce': base64.b64encode(nonce).decode(),
            'ciphertext': base64.b64encode(ciphertext).decode()
        }
    
    def decrypt(self, encrypted_data: dict) -> str:
        """Déchiffre un texte"""
        nonce = base64.b64decode(encrypted_data['nonce'])
        ciphertext = base64.b64decode(encrypted_data['ciphertext'])
        plaintext = self.cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

class PasswordDatabase:
    """Gestion de la base de données SQLite chiffrée"""
    
    def __init__(self, db_path: Path, crypto: PasswordCrypto):
        self.db_path = db_path
        self.crypto = crypto
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()
        logger.debug("Initialisation de la base de donnees %s", db_path)
    
    def _init_db(self):
        """Initialise la structure de la base"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                username TEXT,
                password_data TEXT NOT NULL,
                url TEXT,
                notes TEXT,
                category TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT,
                icon TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Catégories par défaut
        default_categories = [
            ("Personnel", "#3584e4", "user-home-symbolic"),
            ("Travail", "#f66151", "briefcase-symbolic"),
            ("Finance", "#33d17a", "credit-card-symbolic"),
            ("Social", "#9141ac", "user-available-symbolic"),
            ("Autres", "#986a44", "folder-symbolic")
        ]
        
        for cat_name, color, icon in default_categories:
            cursor.execute('''
                INSERT OR IGNORE INTO categories (name, color, icon)
                VALUES (?, ?, ?)
            ''', (cat_name, color, icon))
        
        self.conn.commit()
    
    def add_entry(self, title: str, username: str, password: str, url: str = "", 
                  notes: str = "", category: str = "", tags: list = None):
        """Ajoute une entrée chiffrée"""
        encrypted_pass = self.crypto.encrypt(password)
        encrypted_notes = self.crypto.encrypt(notes) if notes else ""
        tags_str = json.dumps(tags if tags else [])
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO passwords (title, username, password_data, url, notes, category, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, username, json.dumps(encrypted_pass), url, 
              json.dumps(encrypted_notes) if notes else "", category, tags_str))
        self.conn.commit()
        logger.info("Entree ajoutee: %s (categorie=%s)", title, category or "Aucune")
        return cursor.lastrowid
    
    def get_all_entries(self, category_filter=None, tag_filter=None, search_text=None):
        """Récupère toutes les entrées avec filtres optionnels
        
        Args:
            category_filter: Nom de la catégorie pour filtrer (None pour toutes)
            tag_filter: Tag pour filtrer les entrées
            search_text: Texte de recherche dans titre, username ou URL
            
        Returns:
            List[Tuple]: Liste des entrées correspondantes
        """
        cursor = self.conn.cursor()
        query = 'SELECT id, title, username, url, category, tags FROM passwords WHERE 1=1'
        params = []
        
        if category_filter and category_filter != "Toutes":
            query += ' AND category = ?'
            params.append(category_filter)
        
        if search_text:
            query += ' AND (title LIKE ? OR username LIKE ? OR url LIKE ?)'
            search_pattern = f'%{search_text}%'
            params.extend([search_pattern, search_pattern, search_pattern])
        
        query += ' ORDER BY title COLLATE NOCASE'
        cursor.execute(query, params)
        entries = cursor.fetchall()
        logger.debug(
            "Chargement de %d entrees (categorie=%s, tag=%s)",
            len(entries),
            category_filter or "Toutes",
            tag_filter or "Aucun"
        )
        
        # Filtre par tag si nécessaire (optimisé avec compréhension de liste)
        if tag_filter:
            return [
                entry for entry in entries 
                if tag_filter in (json.loads(entry[5]) if entry[5] else [])
            ]
        
        return entries
    
    def get_entry(self, entry_id: int):
        """Récupère et déchiffre une entrée complète
        
        Args:
            entry_id: ID de l'entrée à récupérer
            
        Returns:
            dict: Dictionnaire avec toutes les données déchiffrées ou None si non trouvée
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM passwords WHERE id = ?', (entry_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        try:
            encrypted_pass = json.loads(row[3])
            password = self.crypto.decrypt(encrypted_pass)
            
            notes = ""
            if row[5]:
                encrypted_notes = json.loads(row[5])
                notes = self.crypto.decrypt(encrypted_notes)
            
            tags = json.loads(row[7]) if row[7] else []
            
            entry_data = {
                'id': row[0],
                'title': row[1],
                'username': row[2],
                'password': password,
                'url': row[4],
                'notes': notes,
                'category': row[6] or "",
                'tags': tags
            }
            logger.debug("Entree %s decryptee et retournee", entry_id)
            return entry_data
        except Exception as e:
            logger.exception("Erreur lors du dechiffrement de l'entree %s", entry_id)
            return None
    
    def delete_entry(self, entry_id: int):
        """Supprime une entrée"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM passwords WHERE id = ?', (entry_id,))
        self.conn.commit()
        logger.info("Entree supprimee: %s", entry_id)
    
    def update_entry(self, entry_id: int, title: str, username: str, password: str, 
                     url: str = "", notes: str = "", category: str = "", tags: list = None):
        """Met à jour une entrée"""
        encrypted_pass = self.crypto.encrypt(password)
        encrypted_notes = self.crypto.encrypt(notes) if notes else ""
        tags_str = json.dumps(tags if tags else [])
        
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE passwords 
            SET title=?, username=?, password_data=?, url=?, notes=?, 
                category=?, tags=?, modified_at=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (title, username, json.dumps(encrypted_pass), url, 
              json.dumps(encrypted_notes) if notes else "", category, tags_str, entry_id))
        self.conn.commit()
        logger.info("Entree %s mise a jour (titre=%s)", entry_id, title)
    
    def get_all_categories(self):
        """Récupère toutes les catégories"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT name, color, icon FROM categories ORDER BY name')
        return cursor.fetchall()
    
    def get_all_tags(self):
        """Récupère tous les tags utilisés"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT tags FROM passwords WHERE tags IS NOT NULL AND tags != ""')
        all_tags = set()
        for row in cursor.fetchall():
            tags = json.loads(row[0])
            all_tags.update(tags)
        return sorted(list(all_tags))
    
    def add_category(self, name: str, color: str = "#999999", icon: str = "folder-symbolic"):
        """Ajoute une nouvelle catégorie"""
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO categories (name, color, icon) VALUES (?, ?, ?)',
                      (name, color, icon))
        self.conn.commit()
        logger.debug("Categorie ajoutee: %s", name)
    
    def close(self):
        self.conn.close()

class PasswordEntryRow(Gtk.ListBoxRow):
    """Widget pour afficher une entrée de mot de passe (legacy - pour compatibilité)"""
    
    def __init__(self, entry_id, title, username, url, category, tags):
        super().__init__()
        self.entry_id = entry_id
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        
        # Titre avec catégorie
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        title_label = Gtk.Label(label=title, xalign=0)
        title_label.set_css_classes(['title-4'])
        title_label.set_hexpand(True)
        header_box.append(title_label)
        
        if category:
            category_label = Gtk.Label(label=category)
            category_label.set_css_classes(['caption', 'dim-label'])
            header_box.append(category_label)
        
        box.append(header_box)
        
        if username:
            username_label = Gtk.Label(label=username, xalign=0)
            username_label.set_css_classes(['dim-label'])
            box.append(username_label)
        
        # Tags
        if tags and len(tags) > 0:
            tags_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            tags_box.set_margin_top(4)
            for tag in tags[:3]:  # Limiter à 3 tags affichés
                tag_label = Gtk.Label(label=f"#{tag}")
                tag_label.set_css_classes(['caption', 'accent'])
                tags_box.append(tag_label)
            box.append(tags_box)
        
        self.set_child(box)


class PasswordCard(Gtk.FlowBoxChild):
    """Card moderne pour afficher une entrée de mot de passe dans un FlowBox"""
    
    def __init__(self, entry_id, title, username, url, category, tags):
        super().__init__()
        self.entry_id = entry_id
        self.title = title
        self.username = username
        self.url = url
        self.category = category
        self.tags = tags
        
        # Container principal avec style card
        frame = Gtk.Frame()
        frame.set_css_classes(['card'])
        
        card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card_box.set_margin_start(16)
        card_box.set_margin_end(16)
        card_box.set_margin_top(16)
        card_box.set_margin_bottom(16)
        card_box.set_size_request(200, -1)  # Largeur fixe pour consistance
        
        # Header avec icône
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # Icône basée sur la catégorie ou l'URL
        icon_name = self._get_icon_for_entry(category, url)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(32)
        header_box.append(icon)
        
        # Titre
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        
        title_label = Gtk.Label(label=title, xalign=0)
        title_label.set_css_classes(['title-4'])
        title_label.set_ellipsize(3)  # ELLIPSIZE_END
        title_label.set_max_width_chars(20)
        title_box.append(title_label)
        
        # Catégorie
        if category:
            cat_label = Gtk.Label(label=f"📁 {category}", xalign=0)
            cat_label.set_css_classes(['caption', 'dim-label'])
            cat_label.set_ellipsize(3)
            cat_label.set_max_width_chars(20)
            title_box.append(cat_label)
        
        header_box.append(title_box)
        card_box.append(header_box)
        
        # Séparateur
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        card_box.append(separator)
        
        # Username
        if username:
            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            user_icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            user_icon.set_pixel_size(16)
            user_box.append(user_icon)
            
            user_label = Gtk.Label(label=username, xalign=0)
            user_label.set_css_classes(['body'])
            user_label.set_ellipsize(3)
            user_label.set_max_width_chars(20)
            user_label.set_hexpand(True)
            user_box.append(user_label)
            
            card_box.append(user_box)
        
        # Tags
        if tags and len(tags) > 0:
            tags_flow = Gtk.FlowBox()
            tags_flow.set_selection_mode(Gtk.SelectionMode.NONE)
            tags_flow.set_max_children_per_line(2)
            tags_flow.set_margin_top(4)
            
            for tag in tags[:2]:  # Limiter à 2 tags
                tag_label = Gtk.Label(label=f"#{tag}")
                tag_label.set_css_classes(['caption', 'accent'])
                tag_child = Gtk.FlowBoxChild()
                tag_child.set_child(tag_label)
                tags_flow.append(tag_child)
            
            if len(tags) > 2:
                more_label = Gtk.Label(label=f"+{len(tags)-2}")
                more_label.set_css_classes(['caption', 'dim-label'])
                more_child = Gtk.FlowBoxChild()
                more_child.set_child(more_label)
                tags_flow.append(more_child)
            
            card_box.append(tags_flow)
        
        frame.set_child(card_box)
        self.set_child(frame)
    
    def _get_icon_for_entry(self, category, url):
        """Retourne une icône appropriée selon la catégorie ou l'URL"""
        if url:
            domain = url.lower()
            if 'google' in domain:
                return 'web-browser-symbolic'
            elif 'github' in domain:
                return 'software-update-available-symbolic'
            elif 'facebook' in domain or 'twitter' in domain or 'instagram' in domain:
                return 'user-available-symbolic'
            elif 'mail' in domain or 'gmail' in domain:
                return 'mail-send-symbolic'
            else:
                return 'network-server-symbolic'
        
        if category:
            cat_lower = category.lower()
            if 'social' in cat_lower:
                return 'user-available-symbolic'
            elif 'mail' in cat_lower or 'email' in cat_lower:
                return 'mail-send-symbolic'
            elif 'bank' in cat_lower or 'finance' in cat_lower:
                return 'security-high-symbolic'
            elif 'work' in cat_lower or 'travail' in cat_lower:
                return 'briefcase-symbolic'
            elif 'shopping' in cat_lower or 'achat' in cat_lower:
                return 'shopping-cart-symbolic'
        
        return 'dialog-password-symbolic'  # Icône par défaut


class PasswordManagerApp(Adw.ApplicationWindow):
    """Fenêtre principale de l'application"""
    
    def __init__(self, app, db: PasswordDatabase, user_info: dict, user_manager: UserManager):
        super().__init__(application=app, title="Gestionnaire de mots de passe")
        self.set_default_size(1000, 650)
        self.db = db
        self.user_info = user_info
        self.user_manager = user_manager
        self.current_category_filter = "Toutes"
        self.current_tag_filter = None
        
        # Layout principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Header Bar
        header = Adw.HeaderBar()
        
        # Bouton ajouter
        add_button = Gtk.Button(icon_name="list-add-symbolic")
        add_button.connect("clicked", self.on_add_clicked)
        header.pack_start(add_button)
        
        # Label de bienvenue avec le nom d'utilisateur
        welcome_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        user_icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        welcome_box.append(user_icon)
        
        welcome_label = Gtk.Label(label=f"Bonjour, {user_info['username']}")
        welcome_label.set_css_classes(['title-4'])
        welcome_box.append(welcome_label)
        
        if user_info['role'] == 'admin':
            admin_badge = Gtk.Label(label="Admin")
            admin_badge.set_css_classes(['caption', 'accent'])
            welcome_box.append(admin_badge)

        if is_dev_mode():
            dev_badge = Gtk.Label(label="🔧 MODE DÉVELOPPEMENT")
            dev_badge.set_css_classes(['caption', 'warning'])
            welcome_box.append(dev_badge)
        
        header.set_title_widget(welcome_box)
        
        # Menu utilisateur
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        
        menu = Gio.Menu()
        
        menu.append("Importer depuis CSV", "app.import_csv")
        menu.append("Changer mon mot de passe", "app.change_own_password")
        
        if user_info['role'] == 'admin':
            menu.append("Gérer les utilisateurs", "app.manage_users")
        
        menu.append("Changer de compte", "app.switch_user")
        menu.append("Déconnexion", "app.logout")
        
        # Séparateur
        menu_section = Gio.Menu()
        menu_section.append("À propos", "app.about")
        menu.append_section(None, menu_section)
        
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)
        
        main_box.append(header)
        
        # Vue divisée
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        
        # Panneau gauche (catégories + liste) - Utilisation d'un Paned vertical
        left_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        left_paned.set_size_request(320, -1)
        left_paned.set_shrink_start_child(False)
        left_paned.set_shrink_end_child(False)
        
        # Panneau supérieur (catégories et tags)
        filters_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Filtres par catégorie
        cat_label = Gtk.Label(label="Catégories")
        cat_label.set_css_classes(['title-4'])
        cat_label.set_margin_start(12)
        cat_label.set_margin_top(10)
        cat_label.set_margin_bottom(5)
        cat_label.set_xalign(0)
        filters_box.append(cat_label)
        
        cat_scroll = Gtk.ScrolledWindow()
        cat_scroll.set_vexpand(True)
        cat_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.category_listbox = Gtk.ListBox()
        self.category_listbox.set_css_classes(['navigation-sidebar'])
        self.category_listbox.connect("row-selected", self.on_category_selected)
        cat_scroll.set_child(self.category_listbox)
        filters_box.append(cat_scroll)
        
        # Filtres par tags
        tag_label = Gtk.Label(label="Tags")
        tag_label.set_css_classes(['title-4'])
        tag_label.set_margin_start(12)
        tag_label.set_margin_top(10)
        tag_label.set_margin_bottom(5)
        tag_label.set_xalign(0)
        filters_box.append(tag_label)
        
        tag_scroll = Gtk.ScrolledWindow()
        tag_scroll.set_min_content_height(80)
        tag_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.tag_flowbox = Gtk.FlowBox()
        self.tag_flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.tag_flowbox.set_margin_start(12)
        self.tag_flowbox.set_margin_end(12)
        self.tag_flowbox.connect("child-activated", self.on_tag_selected)
        tag_scroll.set_child(self.tag_flowbox)
        filters_box.append(tag_scroll)
        
        left_paned.set_start_child(filters_box)
        
        left_paned.set_start_child(filters_box)
        
        # Sidebar compacte (remplace le panneau gauche complexe)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(250, -1)
        sidebar.set_css_classes(['background'])
        
        # Recherche en haut
        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        search_box.set_margin_start(12)
        search_box.set_margin_end(12)
        search_box.set_margin_top(12)
        search_box.set_margin_bottom(6)
        
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Rechercher...")
        search_entry.connect("search-changed", self.on_search_changed)
        search_box.append(search_entry)
        sidebar.append(search_box)
        
        # Séparateur
        sep1 = Gtk.Separator()
        sidebar.append(sep1)
        
        # Catégories
        cat_label = Gtk.Label(label="Catégories")
        cat_label.set_css_classes(['title-4'])
        cat_label.set_margin_start(12)
        cat_label.set_margin_top(12)
        cat_label.set_margin_bottom(6)
        cat_label.set_xalign(0)
        sidebar.append(cat_label)
        
        cat_scroll = Gtk.ScrolledWindow()
        cat_scroll.set_vexpand(True)
        cat_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cat_scroll.set_min_content_height(150)
        
        self.category_listbox = Gtk.ListBox()
        self.category_listbox.set_css_classes(['navigation-sidebar'])
        self.category_listbox.connect("row-selected", self.on_category_selected)
        cat_scroll.set_child(self.category_listbox)
        sidebar.append(cat_scroll)
        
        # Séparateur
        sep2 = Gtk.Separator()
        sidebar.append(sep2)
        
        # Tags
        tag_label = Gtk.Label(label="Tags")
        tag_label.set_css_classes(['title-4'])
        tag_label.set_margin_start(12)
        tag_label.set_margin_top(8)
        tag_label.set_margin_bottom(6)
        tag_label.set_xalign(0)
        sidebar.append(tag_label)
        
        tag_scroll = Gtk.ScrolledWindow()
        tag_scroll.set_vexpand(True)
        tag_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        tag_scroll.set_min_content_height(100)
        tag_scroll.set_margin_bottom(12)
        
        self.tag_flowbox = Gtk.FlowBox()
        self.tag_flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.tag_flowbox.set_margin_start(12)
        self.tag_flowbox.set_margin_end(12)
        self.tag_flowbox.set_max_children_per_line(1)
        self.tag_flowbox.connect("child-activated", self.on_tag_selected)
        tag_scroll.set_child(self.tag_flowbox)
        sidebar.append(tag_scroll)
        
        paned.set_start_child(sidebar)
        
        # Zone principale avec FlowBox des cards
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_content.set_hexpand(True)
        main_content.set_vexpand(True)
        
        # Message de bienvenue ou vide
        self.empty_state = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.empty_state.set_valign(Gtk.Align.CENTER)
        self.empty_state.set_halign(Gtk.Align.CENTER)
        
        empty_icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.set_css_classes(['dim-label'])
        self.empty_state.append(empty_icon)
        
        empty_label = Gtk.Label(label="Aucune entrée")
        empty_label.set_css_classes(['title-2', 'dim-label'])
        self.empty_state.append(empty_label)
        
        empty_hint = Gtk.Label(label="Cliquez sur + pour ajouter votre première entrée")
        empty_hint.set_css_classes(['body', 'dim-label'])
        self.empty_state.append(empty_hint)
        
        # ScrolledWindow pour les cards
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        
        # FlowBox pour les cards
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(30)  # Auto-adapt selon largeur
        self.flowbox.set_min_children_per_line(1)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_margin_start(20)
        self.flowbox.set_margin_end(20)
        self.flowbox.set_margin_top(20)
        self.flowbox.set_margin_bottom(20)
        self.flowbox.set_row_spacing(16)
        self.flowbox.set_column_spacing(16)
        self.flowbox.connect("child-activated", self.on_card_activated)
        
        scrolled.set_child(self.flowbox)
        main_content.append(self.empty_state)
        main_content.append(scrolled)
        
        paned.set_end_child(main_content)
        
        main_box.append(paned)
        self.set_content(main_box)
        
        self.load_categories()
        self.load_tags()
        self.load_entries()
        logger.info(
            "Fenetre principale prete pour %s (role=%s)",
            user_info['username'],
            user_info['role']
        )
    
    def load_categories(self):
        """Charge les catégories"""
        # Suppression optimisée
        self.category_listbox.remove_all()
        
        # Ajouter "Toutes"
        all_row = Gtk.ListBoxRow()
        all_label = Gtk.Label(label="📂 Toutes")
        all_label.set_xalign(0)
        all_label.set_margin_start(12)
        all_label.set_margin_end(12)
        all_label.set_margin_top(6)
        all_label.set_margin_bottom(6)
        all_row.set_child(all_label)
        all_row.category_name = "Toutes"
        self.category_listbox.append(all_row)
        
        # Ajouter les catégories depuis la base
        categories = self.db.get_all_categories()
        for cat_name, color, icon in categories:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=f"  {cat_name}")
            label.set_xalign(0)
            label.set_margin_start(12)
            label.set_margin_end(12)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            row.set_child(label)
            row.category_name = cat_name
            self.category_listbox.append(row)
        logger.debug("Categories chargees: %d", len(categories))
    
    def load_tags(self):
        """Charge les tags dans un format compact"""
        while True:
            child = self.tag_flowbox.get_first_child()
            if child is None:
                break
            self.tag_flowbox.remove(child)
        
        tags = self.db.get_all_tags()
        for tag in tags:
            # Créer une box pour le tag avec style
            tag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            tag_box.set_css_classes(['card'])
            
            label = Gtk.Label(label=f"#{tag}")
            label.set_css_classes(['caption'])
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            tag_box.append(label)
            
            # Wrapper FlowBoxChild
            child = Gtk.FlowBoxChild()
            child.set_child(tag_box)
            child.tag_name = tag
            
            self.tag_flowbox.append(child)
        logger.debug("Tags charges: %d", len(tags))
    
    def load_entries(self):
        """Charge toutes les entrées dans le FlowBox"""
        # Suppression optimisée de toutes les cards
        while True:
            child = self.flowbox.get_first_child()
            if child is None:
                break
            self.flowbox.remove(child)
        
        entries = self.db.get_all_entries(
            category_filter=self.current_category_filter,
            tag_filter=self.current_tag_filter
        )
        logger.debug(
            "Affichage de %d entrees (categorie=%s, tag=%s)",
            len(entries),
            self.current_category_filter,
            self.current_tag_filter or "Aucun"
        )
        
        # Afficher/masquer l'état vide
        if len(entries) == 0:
            self.empty_state.set_visible(True)
            self.flowbox.set_visible(False)
        else:
            self.empty_state.set_visible(False)
            self.flowbox.set_visible(True)
            
            # Ajout optimisé des cards
            for entry in entries:
                tags = json.loads(entry[5]) if entry[5] else []
                card = PasswordCard(entry[0], entry[1], entry[2], entry[3], entry[4], tags)
                self.flowbox.append(card)
    
    def on_category_selected(self, listbox, row):
        """Filtre par catégorie"""
        if row:
            self.current_category_filter = row.category_name
            self.current_tag_filter = None
            self.tag_flowbox.unselect_all()
            self.load_entries()
    
    def on_tag_selected(self, flowbox, child):
        """Filtre par tag"""
        if child and hasattr(child, 'tag_name'):
            self.current_tag_filter = child.tag_name
            self.current_category_filter = "Toutes"
            self.category_listbox.select_row(self.category_listbox.get_row_at_index(0))
            self.load_entries()
    
    def on_search_changed(self, search_entry):
        """Recherche dans les entrées"""
        text = search_entry.get_text().lower()
        
        def filter_func(child):
            """Filtre les cards selon le texte de recherche"""
            if not hasattr(child, 'title'):
                return True
            
            # Recherche dans titre, username, catégorie et tags
            searchable = [
                child.title.lower(),
                child.username.lower() if child.username else "",
                child.category.lower() if child.category else "",
            ]
            
            # Ajouter les tags
            if child.tags:
                searchable.extend([tag.lower() for tag in child.tags])
            
            return any(text in item for item in searchable)
        
        self.flowbox.set_filter_func(filter_func if text else None)
    
    def on_card_activated(self, flowbox, child):
        """Ouvre le dialogue de détails quand une card est cliquée"""
        if child and hasattr(child, 'entry_id'):
            logger.info("Card selectionnee pour l'entree %s", child.entry_id)
            entry = self.db.get_entry(child.entry_id)
            if entry:
                dialog = EntryDetailsDialog(self, self.db, entry, self.on_edit_clicked, self.on_delete_clicked)
                dialog.present()
    
    def on_row_selected(self, listbox, row):
        """Affiche les détails d'une entrée sélectionnée (legacy - pour compatibilité)"""
        if row is None:
            return
        
        entry = self.db.get_entry(row.entry_id)
        if not entry:
            return
        
        # Nettoyer la vue détails
        while True:
            child = self.detail_box.get_first_child()
            if child is None:
                break
            self.detail_box.remove(child)
        
        # Afficher les détails
        title_label = Gtk.Label(label=entry['title'], xalign=0)
        title_label.set_css_classes(['title-1'])
        title_label.set_margin_bottom(10)
        self.detail_box.append(title_label)
        
        # Catégorie et tags
        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        meta_box.set_margin_bottom(20)
        
        if entry['category']:
            cat_label = Gtk.Label(label=f"📁 {entry['category']}")
            cat_label.set_css_classes(['caption'])
            meta_box.append(cat_label)
        
        for tag in entry['tags']:
            tag_label = Gtk.Label(label=f"#{tag}")
            tag_label.set_css_classes(['caption', 'accent'])
            meta_box.append(tag_label)
        
        self.detail_box.append(meta_box)
        
        # Nom d'utilisateur
        if entry['username']:
            username_box = self.create_field_box("Nom d'utilisateur", entry['username'], True)
            self.detail_box.append(username_box)
        
        # Mot de passe
        password_box = self.create_field_box("Mot de passe", entry['password'], True, is_password=True)
        self.detail_box.append(password_box)
        
        # URL
        if entry['url']:
            url_box = self.create_field_box("URL", entry['url'], copyable=True, is_url=True)
            self.detail_box.append(url_box)
        
        # Notes
        if entry['notes']:
            notes_label = Gtk.Label(label="Notes", xalign=0)
            notes_label.set_css_classes(['title-4'])
            notes_label.set_margin_top(10)
            self.detail_box.append(notes_label)
            
            notes_text = Gtk.Label(label=entry['notes'], xalign=0, wrap=True)
            notes_text.set_margin_top(5)
            self.detail_box.append(notes_text)
        
        # Boutons d'action
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_margin_top(20)
        
        edit_btn = Gtk.Button(label="Modifier")
        edit_btn.connect("clicked", lambda x: self.on_edit_clicked(entry['id']))
        action_box.append(edit_btn)
        
        delete_btn = Gtk.Button(label="Supprimer")
        delete_btn.set_css_classes(['destructive-action'])
        delete_btn.connect("clicked", lambda x: self.on_delete_clicked(entry['id']))
        action_box.append(delete_btn)
        
        self.detail_box.append(action_box)
    
    def create_field_box(self, label_text, value, copyable=False, is_password=False, is_url=False):
        """Crée un champ avec label et valeur copiable
        
        Args:
            label_text: Texte du label
            value: Valeur à afficher
            copyable: Ajouter un bouton copier
            is_password: Masquer la valeur avec option de révélation
            is_url: Ajouter un bouton pour ouvrir l'URL dans le navigateur
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.set_margin_bottom(15)
        
        label = Gtk.Label(label=label_text, xalign=0)
        label.set_css_classes(['title-4'])
        box.append(label)
        
        value_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        value_entry = Gtk.Entry()
        value_entry.set_text(value)
        value_entry.set_editable(False)
        value_entry.set_hexpand(True)
        if is_password:
            value_entry.set_visibility(False)
        value_box.append(value_entry)
        
        if copyable:
            copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
            copy_btn.set_tooltip_text("Copier dans le presse-papiers")
            copy_btn.connect("clicked", lambda x: self.copy_to_clipboard(value))
            value_box.append(copy_btn)
        
        if is_url and value:
            open_btn = Gtk.Button(icon_name="web-browser-symbolic")
            open_btn.set_tooltip_text("Ouvrir dans le navigateur")
            open_btn.connect("clicked", lambda x: self.open_url(value))
            value_box.append(open_btn)
        
        if is_password:
            show_btn = Gtk.Button(icon_name="view-reveal-symbolic")
            show_btn.set_tooltip_text("Afficher/masquer")
            show_btn.connect("clicked", lambda x: value_entry.set_visibility(not value_entry.get_visibility()))
            value_box.append(show_btn)
        
        box.append(value_box)
        return box
    
    def copy_to_clipboard(self, text):
        """Copie du texte dans le presse-papiers"""
        clipboard = self.get_clipboard()
        clipboard.set(text)
        logger.debug("Texte copie dans le presse-papiers (%d caracteres)", len(text))
    
    def open_url(self, url):
        """Ouvre une URL dans le navigateur par défaut
        
        Args:
            url: URL à ouvrir
        """
        import subprocess
        import shlex
        
        # Ajouter https:// si aucun protocole n'est spécifié
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        logger.info("Ouverture d'une URL: %s", url)
        try:
            # Utiliser xdg-open sur Linux pour ouvrir avec le navigateur par défaut
            subprocess.Popen(['xdg-open', url], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.exception("Erreur lors de l'ouverture de l'URL %s", url)
            # En cas d'erreur, afficher un message
            dialog = Adw.MessageDialog.new(self)
            dialog.set_heading("❌ Erreur")
            dialog.set_body(f"Impossible d'ouvrir l'URL :\n{str(e)}")
            dialog.add_response("ok", "OK")
            dialog.present()
    
    def on_add_clicked(self, button):
        """Ouvre le dialogue d'ajout"""
        logger.info("Dialogue d'ajout d'entree lance")
        dialog = AddEditDialog(self, self.db)
        dialog.present()
    
    def on_edit_clicked(self, entry_id):
        """Ouvre le dialogue d'édition"""
        logger.info("Ouverture du dialogue d'edition pour l'entree %s", entry_id)
        entry = self.db.get_entry(entry_id)
        dialog = AddEditDialog(self, self.db, entry)
        dialog.present()
    
    def on_delete_clicked(self, entry_id):
        """Supprime une entrée après confirmation"""
        logger.warning("Demande de suppression pour l'entree %s", entry_id)
        present_alert(
            self,
            "Confirmer la suppression",
            "Êtes-vous sûr de vouloir supprimer cette entrée ?",
            [("cancel", "Annuler"), ("delete", "Supprimer")],
            default="cancel",
            close="cancel",
            destructive="delete",
            on_response=lambda response: self.delete_confirmed(response, entry_id),
        )
    
    def delete_confirmed(self, response, entry_id):
        """Callback de confirmation de suppression"""
        if response == "delete":
            logger.info("Suppression confirmee pour l'entree %s", entry_id)
            self.db.delete_entry(entry_id)
            self.load_entries()
            self.load_tags()
            
            # Nettoyer la vue détails
            while True:
                child = self.detail_box.get_first_child()
                if child is None:
                    break
                self.detail_box.remove(child)

class UserSelectionDialog(Adw.ApplicationWindow):
    """Dialogue de sélection d'utilisateur"""
    
    def __init__(self, app, user_manager: UserManager, callback):
        super().__init__(application=app)
        self.set_default_size(450, 500)
        self.set_title("Sélection d'utilisateur")
        self.user_manager = user_manager
        self.callback = callback
        self.app_ref = app
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Header
        header = Adw.HeaderBar()
        box.append(header)
        
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_top(20)
        content.set_margin_bottom(40)
        
        title = Gtk.Label(label="🔐 Gestionnaire de mots de passe")
        title.set_css_classes(['title-1'])
        content.append(title)
        
        # Version
        version_label = Gtk.Label(label=f"Version {get_version()}")
        version_label.set_css_classes(['caption', 'dim-label'])
        content.append(version_label)
        
        subtitle = Gtk.Label(label="Sélectionnez votre compte")
        subtitle.set_css_classes(['title-4'])
        content.append(subtitle)
        
        # Liste des utilisateurs
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(['boxed-list'])
        self.users_listbox.connect("row-activated", self.on_user_selected)
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)
        
        # Charger les utilisateurs
        self.load_users()
        
        box.append(content)
        self.set_content(box)
    
    def load_users(self):
        """Charge la liste des utilisateurs"""
        self.users_listbox.remove_all()
        
        users = self.user_manager.get_all_users()
        for username, role, created_at, last_login in users:
            row = Gtk.ListBoxRow()
            row.username = username
            
            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            user_box.set_margin_start(12)
            user_box.set_margin_end(12)
            user_box.set_margin_top(12)
            user_box.set_margin_bottom(12)
            
            # Icône
            icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            icon.set_pixel_size(32)
            user_box.append(icon)
            
            # Infos utilisateur
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_hexpand(True)
            
            name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name_label = Gtk.Label(label=username, xalign=0)
            name_label.set_css_classes(['title-4'])
            name_box.append(name_label)
            
            if role == 'admin':
                admin_label = Gtk.Label(label="Admin")
                admin_label.set_css_classes(['caption', 'accent'])
                name_box.append(admin_label)
            
            info_box.append(name_box)
            
            if last_login:
                last_login_label = Gtk.Label(label=f"Dernière connexion: {last_login[:16]}", xalign=0)
                last_login_label.set_css_classes(['caption', 'dim-label'])
                info_box.append(last_login_label)
            
            user_box.append(info_box)
            
            # Flèche
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            user_box.append(arrow)
            
            row.set_child(user_box)
            self.users_listbox.append(row)
        logger.debug("Gestion des utilisateurs: %d comptes charges", len(users))
        logger.debug("%d utilisateurs affiches dans la selection", len(users))
    
    def on_user_selected(self, listbox, row):
        """Utilisateur sélectionné, demander le mot de passe"""
        username = row.username
        logger.info("Utilisateur choisi pour connexion: %s", username)
        LoginDialog(self, self.user_manager, username, self.callback).present()


class LoginDialog(Adw.Window):
    """Dialogue de connexion pour un utilisateur spécifique"""
    
    def __init__(self, parent, user_manager: UserManager, username: str, callback):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 250)
        self.set_title("Connexion")
        self.user_manager = user_manager
        self.username = username
        self.callback = callback
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)
        box.set_valign(Gtk.Align.CENTER)
        
        # Icône utilisateur
        icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        icon.set_pixel_size(64)
        box.append(icon)
        
        title = Gtk.Label(label=f"Bonjour, {username}")
        title.set_css_classes(['title-2'])
        box.append(title)
        
        subtitle = Gtk.Label(label="Entrez votre mot de passe maître")
        box.append(subtitle)
        
        # Version en petit en bas
        version_label = Gtk.Label(label=f"v{get_version()}")
        version_label.set_css_classes(['caption', 'dim-label'])
        version_label.set_margin_top(10)
        
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.connect("activate", lambda x: self.on_login())
        box.append(self.password_entry)
        
        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        box.append(self.error_label)
        
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        
        cancel_btn = Gtk.Button(label="Retour")
        cancel_btn.connect("clicked", lambda x: self.close())
        button_box.append(cancel_btn)
        
        login_btn = Gtk.Button(label="Se connecter")
        login_btn.set_css_classes(['suggested-action'])
        login_btn.connect("clicked", lambda x: self.on_login())
        button_box.append(login_btn)
        
        box.append(button_box)
        
        box.append(version_label)
        
        self.set_content(box)
        
        # Focus sur le champ mot de passe
        self.password_entry.grab_focus()
    
    def on_login(self):
        """Tente de se connecter"""
        password = self.password_entry.get_text()
        logger.debug("Tentative de connexion pour %s", self.username)
        if not password:
            logger.warning("Mot de passe vide pour %s", self.username)
            self.show_error("Veuillez entrer votre mot de passe")
            return
        
        user_info = self.user_manager.authenticate(self.username, password)
        if user_info:
            logger.info("Connexion reussie pour %s", self.username)
            self.callback(user_info, password)
            self.get_transient_for().close()  # Fermer la fenêtre de sélection
            self.close()
        else:
            logger.warning("Connexion echouee pour %s", self.username)
            self.show_error("Mot de passe incorrect")
            self.password_entry.set_text("")
            self.password_entry.grab_focus()
    
    def show_error(self, message: str):
        """Affiche un message d'erreur"""
        self.error_label.set_text(message)
        self.error_label.set_visible(True)


class CreateUserDialog(Adw.Window):
    """Dialogue de création d'utilisateur (admin uniquement)"""
    
    def __init__(self, parent, user_manager: UserManager, on_success_callback):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(450, 420)
        self.set_title("Créer un compte")
        self.user_manager = user_manager
        self.on_success_callback = on_success_callback
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        header = Adw.HeaderBar()
        box.append(header)
        
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_top(20)
        content.set_margin_bottom(40)
        
        title = Gtk.Label(label="Créer un nouveau compte")
        title.set_css_classes(['title-2'])
        content.append(title)
        
        # Nom d'utilisateur
        username_label = Gtk.Label(label="Nom d'utilisateur", xalign=0)
        content.append(username_label)
        
        self.username_entry = Gtk.Entry()
        self.username_entry.set_placeholder_text("Votre nom d'utilisateur")
        content.append(self.username_entry)
        
        # Mot de passe
        password_label = Gtk.Label(label="Mot de passe maître", xalign=0)
        content.append(password_label)
        
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        content.append(self.password_entry)
        
        # Confirmation
        confirm_label = Gtk.Label(label="Confirmer le mot de passe", xalign=0)
        content.append(confirm_label)
        
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        content.append(self.confirm_entry)
        
        # Rôle de l'utilisateur
        role_label = Gtk.Label(label="Rôle", xalign=0)
        content.append(role_label)
        
        role_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        role_box.set_margin_bottom(10)
        
        self.role_user = Gtk.CheckButton(label="Utilisateur")
        self.role_user.set_active(True)
        role_box.append(self.role_user)
        
        self.role_admin = Gtk.CheckButton(label="Administrateur")
        self.role_admin.set_group(self.role_user)
        role_box.append(self.role_admin)
        
        content.append(role_box)
        
        # Message d'erreur
        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        content.append(self.error_label)
        
        # Boutons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(10)
        
        cancel_btn = Gtk.Button(label="Annuler")
        cancel_btn.connect("clicked", lambda x: self.close())
        button_box.append(cancel_btn)
        
        create_btn = Gtk.Button(label="Créer le compte")
        create_btn.set_css_classes(['suggested-action'])
        create_btn.connect("clicked", self.on_create_clicked)
        button_box.append(create_btn)
        
        content.append(button_box)
        
        box.append(content)
        self.set_content(box)
    
    def on_create_clicked(self, button):
        """Créer le compte"""
        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()
        
        # Validations
        if not username:
            logger.warning("Creation utilisateur: nom vide")
            self.show_error("Le nom d'utilisateur est requis")
            return
        
        if len(username) < 3:
            logger.warning("Creation utilisateur: nom trop court (%s)", username)
            self.show_error("Le nom d'utilisateur doit contenir au moins 3 caractères")
            return
        
        if not password:
            logger.warning("Creation utilisateur: mot de passe vide pour %s", username)
            self.show_error("Le mot de passe est requis")
            return
        
        if len(password) < 8:
            logger.warning("Creation utilisateur: mot de passe trop court pour %s", username)
            self.show_error("Le mot de passe doit contenir au moins 8 caractères")
            return
        
        if password != confirm:
            logger.warning("Creation utilisateur: mots de passe differents pour %s", username)
            self.show_error("Les mots de passe ne correspondent pas")
            return
        
        # Déterminer le rôle
        role = 'admin' if self.role_admin.get_active() else 'user'
        
        # Créer l'utilisateur
        if self.user_manager.create_user(username, password, role):
            self.on_success_callback()
            logger.info("Utilisateur cree via l'interface: %s (role=%s)", username, role)
            self.close()
        else:
            logger.warning("Creation utilisateur echouee (existe deja): %s", username)
            self.show_error("Ce nom d'utilisateur existe déjà")
    
    def show_error(self, message: str):
        """Affiche un message d'erreur"""
        self.error_label.set_text(message)
        self.error_label.set_visible(True)


class ManageUsersDialog(Adw.Window):
    """Dialogue de gestion des utilisateurs (admin uniquement)"""
    
    def __init__(self, parent, user_manager: UserManager, current_username: str):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 500)
        self.set_title("Gestion des utilisateurs")
        self.user_manager = user_manager
        self.current_username = current_username
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        header = Adw.HeaderBar()
        box.append(header)
        
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        
        title = Gtk.Label(label="Gestion des utilisateurs")
        title.set_css_classes(['title-2'])
        content.append(title)
        
        # Liste des utilisateurs
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(['boxed-list'])
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)
        
        self.load_users()
        
        # Bouton pour créer un nouvel utilisateur
        create_user_btn = Gtk.Button(label="➕ Créer un nouvel utilisateur")
        create_user_btn.set_css_classes(['suggested-action', 'pill'])
        create_user_btn.connect("clicked", self.on_create_user)
        content.append(create_user_btn)
        
        box.append(content)
        self.set_content(box)
    
    def load_users(self):
        """Charge la liste des utilisateurs"""
        self.users_listbox.remove_all()
        
        users = self.user_manager.get_all_users()
        for username, role, created_at, last_login in users:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            
            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            user_box.set_margin_start(12)
            user_box.set_margin_end(12)
            user_box.set_margin_top(12)
            user_box.set_margin_bottom(12)
            
            # Infos
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_hexpand(True)
            
            name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name_label = Gtk.Label(label=username, xalign=0)
            name_label.set_css_classes(['title-4'])
            name_box.append(name_label)
            
            if role == 'admin':
                admin_label = Gtk.Label(label="Admin")
                admin_label.set_css_classes(['caption', 'accent'])
                name_box.append(admin_label)
            
            info_box.append(name_box)
            
            created_label = Gtk.Label(label=f"Créé: {created_at[:10]}", xalign=0)
            created_label.set_css_classes(['caption', 'dim-label'])
            info_box.append(created_label)
            
            user_box.append(info_box)
            
            # Actions (sauf pour soi-même)
            if username != self.current_username:
                action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                
                reset_btn = Gtk.Button(label="Réinitialiser MdP")
                reset_btn.connect("clicked", lambda b, u=username: self.on_reset_password(u))
                action_box.append(reset_btn)
                
                delete_btn = Gtk.Button(label="Supprimer")
                delete_btn.set_css_classes(['destructive-action'])
                delete_btn.connect("clicked", lambda b, u=username: self.on_delete_user(u))
                action_box.append(delete_btn)
                
                user_box.append(action_box)
            
            row.set_child(user_box)
            self.users_listbox.append(row)
    
    def on_create_user(self, button):
        """Créer un nouvel utilisateur"""
        CreateUserDialog(self, self.user_manager, lambda: self.load_users()).present()
    
    def on_reset_password(self, username: str):
        """Réinitialiser le mot de passe d'un utilisateur"""
        ResetPasswordDialog(self, self.user_manager, username).present()
    
    def on_delete_user(self, username: str):
        """Supprimer un utilisateur"""
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading("Confirmer la suppression")
        dialog.set_body(f"Voulez-vous vraiment supprimer l'utilisateur '{username}' ?\n\nToutes ses données seront perdues.")
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("delete", "Supprimer")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda d, r: self.delete_confirmed(r, username))
        dialog.present()
    
    def delete_confirmed(self, response: str, username: str):
        """Confirmation de suppression"""
        if response == "delete":
            if self.user_manager.delete_user(username):
                # Supprimer aussi le workspace de l'utilisateur
                user_db = DATA_DIR / f"passwords_{username}.db"
                user_salt = DATA_DIR / f"salt_{username}.bin"
                
                if user_db.exists():
                    user_db.unlink()
                if user_salt.exists():
                    user_salt.unlink()
                
                self.load_users()


class ChangeOwnPasswordDialog(Adw.Window):
    """Dialogue pour changer son propre mot de passe"""
    
    def __init__(self, parent, user_manager: UserManager, username: str):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(450, 400)
        self.set_title("Changer mon mot de passe")
        self.user_manager = user_manager
        self.username = username
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)
        
        title = Gtk.Label(label="Changer votre mot de passe maître")
        title.set_css_classes(['title-3'])
        title.set_wrap(True)
        box.append(title)
        
        info = Gtk.Label(label="Pour des raisons de sécurité, vous devez d'abord saisir votre mot de passe actuel.")
        info.set_css_classes(['caption', 'dim-label'])
        info.set_wrap(True)
        box.append(info)
        
        # Mot de passe actuel
        current_label = Gtk.Label(label="Mot de passe actuel", xalign=0)
        current_label.set_css_classes(['title-4'])
        box.append(current_label)
        
        self.current_entry = Gtk.PasswordEntry()
        self.current_entry.set_show_peek_icon(True)
        box.append(self.current_entry)
        
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(10)
        separator.set_margin_bottom(10)
        box.append(separator)
        
        # Nouveau mot de passe
        new_label = Gtk.Label(label="Nouveau mot de passe", xalign=0)
        new_label.set_css_classes(['title-4'])
        box.append(new_label)
        
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        box.append(self.password_entry)
        
        # Confirmation
        confirm_label = Gtk.Label(label="Confirmer le nouveau mot de passe", xalign=0)
        box.append(confirm_label)
        
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        box.append(self.confirm_entry)
        
        # Message d'erreur
        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        box.append(self.error_label)
        
        # Boutons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        
        cancel_btn = Gtk.Button(label="Annuler")
        cancel_btn.connect("clicked", lambda x: self.close())
        button_box.append(cancel_btn)
        
        change_btn = Gtk.Button(label="Changer le mot de passe")
        change_btn.set_css_classes(['suggested-action'])
        change_btn.connect("clicked", self.on_change_clicked)
        button_box.append(change_btn)
        
        box.append(button_box)
        
        self.set_content(box)
    
    def on_change_clicked(self, button):
        """Changer le mot de passe"""
        logger.info("Demande de changement de mot de passe pour %s", self.username)
        current = self.current_entry.get_text()
        new_password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()
        
        # Vérifier le mot de passe actuel
        if not current:
            logger.warning("Changement mot de passe: ancien mot de passe vide pour %s", self.username)
            self.show_error("Veuillez saisir votre mot de passe actuel")
            return
        
        if not self.user_manager.verify_user(self.username, current):
            logger.warning("Changement mot de passe: mauvais mot de passe actuel pour %s", self.username)
            self.show_error("❌ Mot de passe actuel incorrect")
            self.current_entry.set_text("")
            self.current_entry.grab_focus()
            return
        
        # Vérifier le nouveau mot de passe
        if not new_password:
            logger.warning("Changement mot de passe: nouveau mot de passe vide pour %s", self.username)
            self.show_error("Le nouveau mot de passe est requis")
            return
        
        if len(new_password) < 8:
            logger.warning("Changement mot de passe: nouveau mot de passe trop court pour %s", self.username)
            self.show_error("Le mot de passe doit contenir au moins 8 caractères")
            return
        
        if new_password == current:
            logger.warning("Changement mot de passe: nouveau mot de passe identique pour %s", self.username)
            self.show_error("Le nouveau mot de passe doit être différent de l'ancien")
            return
        
        if new_password != confirm:
            logger.warning("Changement mot de passe: confirmation differente pour %s", self.username)
            self.show_error("Les mots de passe ne correspondent pas")
            return
        
        # Changer le mot de passe
        if self.user_manager.change_user_password(self.username, current, new_password):
            logger.info("Mot de passe mis a jour pour %s", self.username)
            success_dialog = Adw.MessageDialog.new(self)
            success_dialog.set_heading("✅ Succès")
            success_dialog.set_body("Votre mot de passe maître a été changé avec succès.\n\nVous devrez utiliser ce nouveau mot de passe lors de votre prochaine connexion.")
            success_dialog.add_response("ok", "OK")
            success_dialog.connect("response", lambda d, r: self.close())
            success_dialog.present()
        else:
            self.show_error("❌ Erreur lors du changement de mot de passe")
    
    def show_error(self, message: str):
        """Affiche un message d'erreur"""
        self.error_label.set_text(message)
        self.error_label.set_visible(True)


class ResetPasswordDialog(Adw.Window):
    """Dialogue de réinitialisation de mot de passe (admin uniquement)"""
    
    def __init__(self, parent, user_manager: UserManager, username: str):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 300)
        self.set_title("Réinitialiser le mot de passe")
        self.user_manager = user_manager
        self.username = username
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)
        
        title = Gtk.Label(label=f"Réinitialiser le mot de passe de '{username}'")
        title.set_css_classes(['title-3'])
        title.set_wrap(True)
        box.append(title)
        
        warning = Gtk.Label(label="⚠️ L'utilisateur devra utiliser ce nouveau mot de passe")
        warning.set_css_classes(['caption'])
        warning.set_wrap(True)
        box.append(warning)
        
        password_label = Gtk.Label(label="Nouveau mot de passe", xalign=0)
        box.append(password_label)
        
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        box.append(self.password_entry)
        
        confirm_label = Gtk.Label(label="Confirmer le mot de passe", xalign=0)
        box.append(confirm_label)
        
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        box.append(self.confirm_entry)
        
        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        box.append(self.error_label)
        
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        
        cancel_btn = Gtk.Button(label="Annuler")
        cancel_btn.connect("clicked", lambda x: self.close())
        button_box.append(cancel_btn)
        
        reset_btn = Gtk.Button(label="Réinitialiser")
        reset_btn.set_css_classes(['destructive-action'])
        reset_btn.connect("clicked", self.on_reset_clicked)
        button_box.append(reset_btn)
        
        box.append(button_box)
        
        self.set_content(box)
    
    def on_reset_clicked(self, button):
        """Réinitialiser le mot de passe"""
        logger.info("Demande de reinitialisation pour %s", self.username)
        password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()
        
        if not password:
            logger.warning("Reinitialisation: mot de passe vide pour %s", self.username)
            self.show_error("Le mot de passe est requis")
            return
        
        if len(password) < 8:
            logger.warning("Reinitialisation: mot de passe trop court pour %s", self.username)
            self.show_error("Le mot de passe doit contenir au moins 8 caractères")
            return
        
        if password != confirm:
            logger.warning("Reinitialisation: confirmations differents pour %s", self.username)
            self.show_error("Les mots de passe ne correspondent pas")
            return
        
        if self.user_manager.reset_user_password(self.username, password):
            logger.info("Mot de passe reinitialise pour %s", self.username)
            success_dialog = Adw.MessageDialog.new(self)
            success_dialog.set_heading("Succès")
            success_dialog.set_body(f"Le mot de passe de '{self.username}' a été réinitialisé.")
            success_dialog.add_response("ok", "OK")
            success_dialog.connect("response", lambda d, r: self.close())
            success_dialog.present()
        else:
            self.show_error("Erreur lors de la réinitialisation")
    
    def show_error(self, message: str):
        """Affiche un message d'erreur"""
        self.error_label.set_text(message)
        self.error_label.set_visible(True)

class PasswordManagerApplication(Adw.Application):
    """Application principale avec gestion multi-utilisateurs"""
    
    def __init__(self):
        super().__init__(application_id='org.example.passwordmanager',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.db = None
        self.window = None
        self.user_manager = None
        self.current_user = None
        self.selection_dialog = None  # Garder une référence à la fenêtre de sélection
        
        # Actions
        logout_action = Gio.SimpleAction.new("logout", None)
        logout_action.connect("activate", self.on_logout)
        self.add_action(logout_action)
        
        switch_user_action = Gio.SimpleAction.new("switch_user", None)
        switch_user_action.connect("activate", self.on_switch_user)
        self.add_action(switch_user_action)
        
        manage_users_action = Gio.SimpleAction.new("manage_users", None)
        manage_users_action.connect("activate", self.on_manage_users)
        self.add_action(manage_users_action)
        
        change_own_password_action = Gio.SimpleAction.new("change_own_password", None)
        change_own_password_action.connect("activate", self.on_change_own_password)
        self.add_action(change_own_password_action)
        
        import_csv_action = Gio.SimpleAction.new("import_csv", None)
        import_csv_action.connect("activate", self.on_import_csv)
        self.add_action(import_csv_action)
        
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)
        logger.info("Application initialisee (mode %s)", "DEV" if is_dev_mode() else "PROD")
    
    def do_activate(self):
        """Lance l'application"""
        logger.info("Activation de l'application")
        # Initialiser le gestionnaire d'utilisateurs
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        users_db_path = DATA_DIR / "users.db"
        self.user_manager = UserManager(users_db_path)
        
        # Afficher l'écran de sélection utilisateur
        self.show_user_selection()
    
    def show_user_selection(self):
        """Affiche l'écran de sélection d'utilisateur"""
        logger.debug("Affichage du dialogue de selection utilisateur")
        self.selection_dialog = UserSelectionDialog(self, self.user_manager, self.on_user_authenticated)
        self.selection_dialog.set_application(self)  # Important: lier à l'application
        self.selection_dialog.present()
    
    def on_user_authenticated(self, user_info: dict, master_password: str):
        """Callback après authentification réussie
        
        Args:
            user_info: Informations de l'utilisateur (id, username, role, salt)
            master_password: Mot de passe maître pour dériver la clé de chiffrement
        """
        try:
            self.current_user = user_info
            username = user_info['username']
            logger.info("Utilisateur authentifie: %s (role=%s)", username, user_info['role'])
            db_path = DATA_DIR / f"passwords_{username}.db"
            salt_path = DATA_DIR / f"salt_{username}.bin"
            
            # Charger ou créer le salt spécifique à l'utilisateur
            if salt_path.exists():
                with open(salt_path, 'rb') as f:
                    salt = f.read()
            else:
                salt = user_info['salt']
                with open(salt_path, 'wb') as f:
                    f.write(salt)
                # Sécuriser les permissions du fichier salt
                salt_path.chmod(0o600)
            
            crypto = PasswordCrypto(master_password, salt)
            self.db = PasswordDatabase(db_path, crypto)
            
            # Fermer la fenêtre de sélection si elle existe
            if self.selection_dialog:
                self.selection_dialog.close()
                self.selection_dialog = None
            
            if not self.window:
                self.window = PasswordManagerApp(self, self.db, user_info, self.user_manager)
            else:
                # Fermer l'ancienne fenêtre et en créer une nouvelle
                self.window.close()
                self.window = PasswordManagerApp(self, self.db, user_info, self.user_manager)
            
            self.window.present()
            logger.debug("Fenetre principale affichee pour %s", username)
        except Exception as e:
            logger.exception("Erreur lors de l'initialisation de l'application pour %s", user_info.get('username'))
            dialog = Adw.MessageDialog.new(None)
            dialog.set_heading("Erreur")
            dialog.set_body(f"Impossible d'initialiser l'application: {e}")
            dialog.add_response("ok", "OK")
            dialog.present()
    
    def on_logout(self, action, param):
        """Déconnexion"""
        logger.info("Demande de deconnexion")
        if self.window:
            self.window.close()
            self.window = None
        if self.db:
            self.db.close()
            self.db = None
        self.current_user = None
        self.show_user_selection()
    
    def on_switch_user(self, action, param):
        """Changer d'utilisateur"""
        logger.info("Changement d'utilisateur demande")
        self.on_logout(action, param)
    
    def on_manage_users(self, action, param):
        """Gérer les utilisateurs (admin uniquement)"""
        if self.current_user and self.current_user['role'] == 'admin' and self.window:
            logger.info("Ouverture du dialogue de gestion des utilisateurs")
            ManageUsersDialog(self.window, self.user_manager, self.current_user['username']).present()
    
    def on_change_own_password(self, action, param):
        """Changer son propre mot de passe"""
        if self.current_user and self.window:
            logger.info("Dialogue de changement de mot de passe lance pour %s", self.current_user['username'])
            ChangeOwnPasswordDialog(self.window, self.user_manager, self.current_user['username']).present()
    
    def on_import_csv(self, action, param):
        """Importer des mots de passe depuis un fichier CSV"""
        if self.window and self.db:
            logger.info("Import CSV lance")
            csv_importer = CSVImporter()
            ImportCSVDialog(self.window, self.db, csv_importer).present()
    
    def on_about(self, action, param):
        """Afficher le dialogue À propos"""
        if self.window:
            logger.info("Affichage du dialogue A propos")
            show_about_dialog(self.window)

def main():
    import sys
    app = PasswordManagerApplication()
    return app.run(sys.argv)

if __name__ == '__main__':
    import sys
    sys.exit(main())
