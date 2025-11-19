# 🔧 Guide de Refactoring - Migration Progressive

## 📋 Vue d'ensemble

Ce guide vous accompagne dans la migration du fichier monolithique `password_manager.py` (1950 lignes) vers une architecture modulaire.

## ✅ Progression

### Phase 1 : Modèles ✅ (TERMINÉ)
- ✅ `src/models/user.py`
- ✅ `src/models/password_entry.py`
- ✅ `src/models/category.py`

### Phase 2 : Services (EN COURS)
- ✅ `src/services/password_generator.py`
- ✅ `src/services/crypto_service.py`
- ⏳ `src/services/auth_service.py`
- ⏳ `src/services/password_service.py`

### Phase 3 : Repositories (À FAIRE)
- ⏳ `src/repositories/base_repository.py`
- ⏳ `src/repositories/user_repository.py`
- ⏳ `src/repositories/password_repository.py`

### Phase 4 : UI (À FAIRE)
- ⏳ Séparer les dialogues
- ⏳ Séparer les fenêtres
- ⏳ Créer des widgets réutilisables

### Phase 5 : Finalisation (À FAIRE)
- ⏳ Créer `main.py` et `app.py`
- ⏳ Tests complets
- ⏳ Mise à jour des scripts

---

## 🔨 Phase 2 : Services (Suite)

### Étape 2.3 : Créer AuthService

**Fichier** : `src/services/auth_service.py`

**Code à extraire de `password_manager.py`** :
- Lignes ~150-250 : Classe `UserManager`
- Logique de hachage des mots de passe
- Vérification des credentials

**Nouveau code** :

```python
"""Service d'authentification et gestion des utilisateurs."""

import os
import hashlib
from typing import Optional, Tuple
from pathlib import Path
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

from ..models.user import User, UserCredentials
from ..repositories.user_repository import UserRepository


class AuthService:
    """Service d'authentification des utilisateurs.
    
    Gère le hachage des mots de passe avec PBKDF2HMAC (600 000 itérations)
    et l'authentification des utilisateurs.
    """
    
    ITERATIONS = 600_000
    KEY_LENGTH = 64
    
    def __init__(self, user_repository: UserRepository, data_dir: Path):
        """Initialise le service d'authentification.
        
        Args:
            user_repository: Repository pour accéder aux utilisateurs
            data_dir: Répertoire de données pour stocker les salts
        """
        self.user_repo = user_repository
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_salt_path(self, username: str) -> Path:
        """Retourne le chemin du fichier salt pour un utilisateur."""
        return self.data_dir / f'salt_{username}.bin'
    
    def _generate_salt(self) -> bytes:
        """Génère un salt cryptographiquement sûr."""
        return os.urandom(32)
    
    def _hash_password(self, password: str, salt: bytes) -> bytes:
        """Hache un mot de passe avec PBKDF2HMAC.
        
        Args:
            password: Mot de passe en clair
            salt: Salt unique pour l'utilisateur
            
        Returns:
            Hash du mot de passe (64 octets)
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=salt,
            iterations=self.ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
    
    def _save_salt(self, username: str, salt: bytes) -> None:
        """Sauvegarde le salt d'un utilisateur."""
        salt_path = self._get_salt_path(username)
        with open(salt_path, 'wb') as f:
            f.write(salt)
    
    def _load_salt(self, username: str) -> Optional[bytes]:
        """Charge le salt d'un utilisateur.
        
        Returns:
            Le salt ou None si le fichier n'existe pas
        """
        salt_path = self._get_salt_path(username)
        if not salt_path.exists():
            return None
        with open(salt_path, 'rb') as f:
            return f.read()
    
    def create_user(self, username: str, password: str, role: str = 'user') -> Tuple[bool, str]:
        """Crée un nouveau utilisateur.
        
        Args:
            username: Nom d'utilisateur (unique)
            password: Mot de passe en clair
            role: Rôle ('user' ou 'admin')
            
        Returns:
            Tuple (succès, message)
        """
        # Vérifier si l'utilisateur existe déjà
        if self.user_repo.find_by_username(username):
            return False, f"L'utilisateur '{username}' existe déjà"
        
        # Générer et sauvegarder le salt
        salt = self._generate_salt()
        self._save_salt(username, salt)
        
        # Hacher le mot de passe
        password_hash = self._hash_password(password, salt)
        
        # Créer les credentials
        credentials = UserCredentials(
            username=username,
            password_hash=password_hash,
            salt=salt
        )
        
        # Sauvegarder dans la base
        user_id = self.user_repo.create(username, password_hash.hex(), role)
        
        if user_id:
            return True, f"Utilisateur '{username}' créé avec succès"
        return False, "Erreur lors de la création de l'utilisateur"
    
    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authentifie un utilisateur.
        
        Args:
            username: Nom d'utilisateur
            password: Mot de passe en clair
            
        Returns:
            L'utilisateur si authentifié, None sinon
        """
        # Charger l'utilisateur
        user = self.user_repo.find_by_username(username)
        if not user:
            return None
        
        # Charger le salt
        salt = self._load_salt(username)
        if not salt:
            return None
        
        # Vérifier le mot de passe
        password_hash = self._hash_password(password, salt)
        stored_hash = bytes.fromhex(user.password_hash)
        
        if password_hash == stored_hash:
            # Mettre à jour la dernière connexion
            self.user_repo.update_last_login(user.id)
            return user
        
        return None
    
    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """Change le mot de passe d'un utilisateur.
        
        Args:
            username: Nom d'utilisateur
            old_password: Ancien mot de passe
            new_password: Nouveau mot de passe
            
        Returns:
            Tuple (succès, message)
        """
        # Vérifier l'ancien mot de passe
        user = self.authenticate(username, old_password)
        if not user:
            return False, "Mot de passe actuel incorrect"
        
        # Charger le salt existant
        salt = self._load_salt(username)
        if not salt:
            return False, "Erreur: salt introuvable"
        
        # Hacher le nouveau mot de passe
        new_hash = self._hash_password(new_password, salt)
        
        # Mettre à jour dans la base
        if self.user_repo.update_password(user.id, new_hash.hex()):
            return True, "Mot de passe changé avec succès"
        return False, "Erreur lors du changement de mot de passe"
    
    def reset_password(self, username: str, new_password: str, admin_user: User) -> Tuple[bool, str]:
        """Réinitialise le mot de passe d'un utilisateur (admin uniquement).
        
        Args:
            username: Nom de l'utilisateur cible
            new_password: Nouveau mot de passe
            admin_user: Utilisateur administrateur effectuant l'action
            
        Returns:
            Tuple (succès, message)
        """
        # Vérifier les permissions
        if not admin_user.is_admin():
            return False, "Permission refusée: vous devez être administrateur"
        
        # Charger l'utilisateur cible
        user = self.user_repo.find_by_username(username)
        if not user:
            return False, f"Utilisateur '{username}' introuvable"
        
        # Charger le salt
        salt = self._load_salt(username)
        if not salt:
            return False, "Erreur: salt introuvable"
        
        # Hacher le nouveau mot de passe
        new_hash = self._hash_password(new_password, salt)
        
        # Mettre à jour dans la base
        if self.user_repo.update_password(user.id, new_hash.hex()):
            return True, f"Mot de passe de '{username}' réinitialisé"
        return False, "Erreur lors de la réinitialisation"
    
    def delete_user(self, username: str, admin_user: User) -> Tuple[bool, str]:
        """Supprime un utilisateur (admin uniquement).
        
        Args:
            username: Nom de l'utilisateur à supprimer
            admin_user: Utilisateur administrateur effectuant l'action
            
        Returns:
            Tuple (succès, message)
        """
        # Vérifier les permissions
        if not admin_user.is_admin():
            return False, "Permission refusée"
        
        # Empêcher l'auto-suppression
        if username == admin_user.username:
            return False, "Impossible de supprimer votre propre compte"
        
        # Supprimer l'utilisateur
        user = self.user_repo.find_by_username(username)
        if not user:
            return False, f"Utilisateur '{username}' introuvable"
        
        if self.user_repo.delete(user.id):
            # Supprimer le fichier salt
            salt_path = self._get_salt_path(username)
            if salt_path.exists():
                salt_path.unlink()
            return True, f"Utilisateur '{username}' supprimé"
        return False, "Erreur lors de la suppression"
    
    def list_all_users(self) -> list[User]:
        """Liste tous les utilisateurs.
        
        Returns:
            Liste des utilisateurs
        """
        return self.user_repo.find_all()
    
    def count_admins(self) -> int:
        """Compte le nombre d'administrateurs.
        
        Returns:
            Nombre d'administrateurs
        """
        return self.user_repo.count_by_role('admin')
```

**Comment l'utiliser** :

```python
from pathlib import Path
from src.services.auth_service import AuthService
from src.repositories.user_repository import UserRepository

# Configuration
data_dir = Path.home() / '.local' / 'share' / 'passwordmanager'
user_repo = UserRepository(data_dir / 'users.db')
auth_service = AuthService(user_repo, data_dir)

# Créer un utilisateur
success, msg = auth_service.create_user('alice', 'MySecret123!', 'admin')
print(msg)

# Authentifier
user = auth_service.authenticate('alice', 'MySecret123!')
if user:
    print(f"Bienvenue {user.username}!")
```

---

## 🗄️ Phase 3 : Repositories

### Étape 3.1 : BaseRepository

**Fichier** : `src/repositories/base_repository.py`

```python
"""Repository de base pour la gestion SQLite."""

import sqlite3
from pathlib import Path
from typing import Optional


class BaseRepository:
    """Repository de base avec gestion de connexion SQLite.
    
    Toutes les repositories héritent de cette classe pour bénéficier
    de la gestion automatique de la connexion.
    """
    
    def __init__(self, db_path: Path):
        """Initialise le repository.
        
        Args:
            db_path: Chemin vers le fichier SQLite
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
    
    def _connect(self) -> None:
        """Établit la connexion à la base de données."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys = ON')
    
    def close(self) -> None:
        """Ferme la connexion."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        """Support du context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support du context manager."""
        self.close()
```

### Étape 3.2 : UserRepository

**Fichier** : `src/repositories/user_repository.py`

```python
"""Repository pour la gestion des utilisateurs."""

from typing import Optional
from pathlib import Path
from datetime import datetime

from .base_repository import BaseRepository
from ..models.user import User


class UserRepository(BaseRepository):
    """Repository pour les opérations CRUD sur les utilisateurs."""
    
    def __init__(self, db_path: Path):
        """Initialise le repository utilisateurs.
        
        Args:
            db_path: Chemin vers users.db
        """
        super().__init__(db_path)
        self._create_tables()
    
    def _create_tables(self) -> None:
        """Crée les tables si elles n'existent pas."""
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT
            )
        ''')
        self.conn.commit()
    
    def create(self, username: str, password_hash: str, role: str = 'user') -> Optional[int]:
        """Crée un nouvel utilisateur.
        
        Args:
            username: Nom d'utilisateur unique
            password_hash: Hash du mot de passe (hex)
            role: Rôle ('user' ou 'admin')
            
        Returns:
            ID du nouvel utilisateur ou None en cas d'erreur
        """
        try:
            cursor = self.conn.execute(
                'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                (username, password_hash, role)
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None
    
    def find_by_id(self, user_id: int) -> Optional[User]:
        """Trouve un utilisateur par son ID.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            L'utilisateur ou None
        """
        cursor = self.conn.execute(
            'SELECT * FROM users WHERE id = ?',
            (user_id,)
        )
        row = cursor.fetchone()
        return self._row_to_user(row) if row else None
    
    def find_by_username(self, username: str) -> Optional[User]:
        """Trouve un utilisateur par son nom.
        
        Args:
            username: Nom d'utilisateur (insensible à la casse)
            
        Returns:
            L'utilisateur ou None
        """
        cursor = self.conn.execute(
            'SELECT * FROM users WHERE username = ? COLLATE NOCASE',
            (username,)
        )
        row = cursor.fetchone()
        return self._row_to_user(row) if row else None
    
    def find_all(self) -> list[User]:
        """Liste tous les utilisateurs.
        
        Returns:
            Liste des utilisateurs
        """
        cursor = self.conn.execute('SELECT * FROM users ORDER BY username')
        return [self._row_to_user(row) for row in cursor.fetchall()]
    
    def count_by_role(self, role: str) -> int:
        """Compte les utilisateurs par rôle.
        
        Args:
            role: Rôle à compter ('user' ou 'admin')
            
        Returns:
            Nombre d'utilisateurs
        """
        cursor = self.conn.execute(
            'SELECT COUNT(*) FROM users WHERE role = ?',
            (role,)
        )
        return cursor.fetchone()[0]
    
    def update_password(self, user_id: int, new_password_hash: str) -> bool:
        """Met à jour le mot de passe d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            new_password_hash: Nouveau hash (hex)
            
        Returns:
            True si réussi
        """
        cursor = self.conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (new_password_hash, user_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    def update_last_login(self, user_id: int) -> bool:
        """Met à jour la date de dernière connexion.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            True si réussi
        """
        cursor = self.conn.execute(
            'UPDATE users SET last_login = ? WHERE id = ?',
            (datetime.now().isoformat(), user_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    def delete(self, user_id: int) -> bool:
        """Supprime un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            
        Returns:
            True si réussi
        """
        cursor = self.conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def _row_to_user(self, row) -> User:
        """Convertit une ligne SQLite en objet User.
        
        Args:
            row: Ligne de résultat SQLite
            
        Returns:
            Objet User
        """
        return User(
            id=row['id'],
            username=row['username'],
            password_hash=row['password_hash'],
            role=row['role'],
            created_at=row['created_at'],
            last_login=row['last_login']
        )
```

---

## 🚀 Script de migration automatique

**Fichier** : `scripts/migrate.py`

```python
#!/usr/bin/env python3
"""Script de migration automatique."""

import sys
from pathlib import Path

# Ajouter src au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

print("🔧 Migration du projet...")
print("=" * 50)

# TODO: Implémenter la migration automatique
# 1. Copier les données existantes
# 2. Vérifier l'intégrité
# 3. Basculer vers la nouvelle architecture

print("\n✅ Migration terminée!")
```

---

## 📝 Checklist de migration

### Avant de commencer
- [ ] Sauvegarder `password_manager.py`
- [ ] Commit Git du code actuel
- [ ] Vérifier que tous les tests passent

### Pendant la migration
- [ ] Créer chaque nouveau module
- [ ] Écrire les tests unitaires
- [ ] Vérifier la parité fonctionnelle
- [ ] Documenter les changements

### Après la migration
- [ ] Mettre à jour les imports
- [ ] Mettre à jour les scripts (run-dev.sh, etc.)
- [ ] Mettre à jour le Dockerfile
- [ ] Mettre à jour README.md
- [ ] Supprimer l'ancien `password_manager.py`

---

## 🐛 Résolution de problèmes

### Import Error
**Problème** : `ModuleNotFoundError: No module named 'src'`

**Solution** :
```bash
# Installer le package en mode développement
pip install -e .
```

### Tests ne passent pas
**Problème** : Tests unitaires échouent

**Solution** :
```bash
# Installer les dépendances de test
pip install -r requirements-dev.txt

# Lancer les tests avec verbose
pytest -v
```

---

## 📚 Ressources utiles

- [ARCHITECTURE.md](ARCHITECTURE.md) - Architecture détaillée
- [README.md](../README.md) - Documentation principale
- [Python Packaging Guide](https://packaging.python.org/)

---

**Next Step** : Continuer avec `src/services/password_service.py` et les repositories.
