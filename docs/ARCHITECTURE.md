# 🏗️ Architecture du projet - Gestionnaire de Mots de Passe

## 📋 Table des matières

- [Vue d'ensemble](#-vue-densemble)
- [Structure du projet](#-structure-du-projet-refactorisé)
- [Architecture en couches](#️-architecture-en-couches)
- [Guide de refactoring](#-guide-de-refactoring-étape-par-étape)
- [Patterns utilisés](#-patterns-utilisés)

## 🎯 Vue d'ensemble

Ce projet suit une **architecture en couches** (Layered Architecture) pour séparer les responsabilités :

```text
┌─────────────────────────────────────┐
│     UI Layer (GTK4/Adwaita)        │  Fenêtres, dialogues, widgets
├─────────────────────────────────────┤
│     Service Layer                   │  Logique métier
├─────────────────────────────────────┤
│     Repository Layer                │  Accès aux données
├─────────────────────────────────────┤
│     Models Layer                    │  Modèles de données
└─────────────────────────────────────┘
```

## 📁 Structure du projet refactorisé

```text
Gestionnaire_mot_passe/
├── src/                              # Code source principal
│   ├── __init__.py
│   ├── main.py                       # Point d'entrée de l'application
│   ├── app.py                        # Classe principale de l'application
│   │
│   ├── models/                       # 📦 Modèles de données (Data Classes)
│   │   ├── __init__.py
│   │   ├── user.py                   # User, UserCredentials
│   │   ├── password_entry.py         # PasswordEntry, EncryptedPasswordEntry
│   │   └── category.py               # Category, DEFAULT_CATEGORIES
│   │
│   ├── services/                     # 🔧 Logique métier
│   │   ├── __init__.py
│   │   ├── password_generator.py     # Génération de mots de passe
│   │   ├── crypto_service.py         # Chiffrement AES-256-GCM
│   │   ├── auth_service.py           # Authentification utilisateurs
│   │   └── password_service.py       # Gestion des mots de passe
│   │
│   ├── repositories/                 # 💾 Accès aux données (Data Access)
│   │   ├── __init__.py
│   │   ├── base_repository.py        # Repository abstrait
│   │   ├── user_repository.py        # CRUD utilisateurs
│   │   ├── password_repository.py    # CRUD mots de passe
│   │   └── category_repository.py    # CRUD catégories
│   │
│   ├── ui/                           # 🎨 Interface utilisateur GTK4
│   │   ├── __init__.py
│   │   ├── windows/                  # Fenêtres principales
│   │   │   ├── __init__.py
│   │   │   ├── main_window.py        # Fenêtre principale
│   │   │   └── user_selection_window.py  # Sélection utilisateur
│   │   │
│   │   ├── dialogs/                  # Dialogues
│   │   │   ├── __init__.py
│   │   │   ├── login_dialog.py       # Connexion
│   │   │   ├── create_user_dialog.py # Création utilisateur
│   │   │   ├── password_dialog.py    # Ajout/édition mot de passe
│   │   │   ├── generator_dialog.py   # Générateur de mots de passe
│   │   │   ├── manage_users_dialog.py # Gestion utilisateurs (admin)
│   │   │   └── reset_password_dialog.py # Réinitialisation MdP
│   │   │
│   │   └── widgets/                  # Widgets réutilisables
│   │       ├── __init__.py
│   │       ├── password_entry_row.py # Ligne d'entrée de mot de passe
│   │       ├── category_button.py    # Bouton de catégorie
│   │       └── tag_widget.py         # Widget de tag
│   │
│   ├── config/                       # ⚙️ Configuration
│   │   ├── __init__.py
│   │   ├── settings.py               # Paramètres de l'application
│   │   └── constants.py              # Constantes globales
│   │
│   └── utils/                        # 🛠️ Utilitaires
│       ├── __init__.py
│       ├── logger.py                 # Configuration du logging
│       └── validators.py             # Validateurs de données
│
├── tests/                            # 🧪 Tests
│   ├── __init__.py
│   ├── unit/                         # Tests unitaires
│   │   ├── test_password_generator.py
│   │   ├── test_crypto_service.py
│   │   ├── test_auth_service.py
│   │   ├── test_user_repository.py
│   │   └── test_password_repository.py
│   │
│   ├── integration/                  # Tests d'intégration
│   │   ├── test_user_workflow.py
│   │   └── test_password_workflow.py
│   │
│   └── fixtures/                     # Données de test
│       └── test_data.py
│
├── docs/                             # 📚 Documentation
│   ├── ARCHITECTURE.md               # Ce fichier
│   ├── API.md                        # Documentation API interne
│   ├── DEPLOYMENT.md                 # Guide de déploiement
│   └── DEVELOPMENT.md                # Guide développeur
│
├── scripts/                          # 📜 Scripts utilitaires
│   ├── test-app.sh                   # Tests complets
│   ├── run-dev.sh                    # Lancement développement
│   ├── build-container.sh            # Build Podman
│   └── run-container.sh              # Run Podman
│
├── docker/                           # 🐋 Configuration Docker/Podman
│   ├── Dockerfile                    # Image principale
│   ├── Dockerfile.dev                # Image de développement
│   └── .containerignore
│
├── password_manager.py               # ⚠️ ANCIEN fichier monolithique (à supprimer)
├── requirements.txt                  # Dépendances Python
├── requirements-dev.txt              # Dépendances de développement
├── setup.py                          # Configuration du package
├── pytest.ini                        # Configuration pytest
├── .gitignore
├── README.md                         # Documentation principale
├── MULTI_USER_GUIDE.md               # Guide multi-utilisateurs
└── PODMAN_GUIDE.md                   # Guide conteneurisation
```

## 🏛️ Architecture en couches

### 1. Models Layer (Modèles de données)

**Responsabilité** : Définir les structures de données

**Fichiers** :

- `src/models/user.py` : User, UserCredentials
- `src/models/password_entry.py` : PasswordEntry, EncryptedPasswordEntry
- `src/models/category.py` : Category, DEFAULT_CATEGORIES

**Principes** :

- Utiliser des `@dataclass` pour les modèles simples
- Pas de logique métier, seulement des données
- Méthodes utilitaires simples (is_admin(), matches_search())

**Exemple** :

```python
from dataclasses import dataclass

@dataclass
class User:
    id: int
    username: str
    role: str = 'user'
    
    def is_admin(self) -> bool:
        return self.role == 'admin'
```

### 2. Repository Layer (Accès aux données)

**Responsabilité** : Gérer la persistance des données (SQLite)

**Fichiers** :

- `src/repositories/base_repository.py` : BaseRepository (abstrait)
- `src/repositories/user_repository.py` : UserRepository
- `src/repositories/password_repository.py` : PasswordRepository
- `src/repositories/category_repository.py` : CategoryRepository

**Principes** :

- Pattern Repository pour abstraire l'accès aux données
- Toutes les requêtes SQL sont ici
- Retourne des objets du Models Layer
- Gère les transactions

**Exemple** :

```python
class UserRepository(BaseRepository):
    def find_by_username(self, username: str) -> Optional[User]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return User(*row) if row else None
```

### 3. Service Layer (Logique métier)

**Responsabilité** : Implémenter la logique métier

**Fichiers** :

- `src/services/password_generator.py` : Génération de mots de passe
- `src/services/crypto_service.py` : Chiffrement/déchiffrement
- `src/services/auth_service.py` : Authentification
- `src/services/password_service.py` : Gestion des mots de passe

**Principes** :

- Orchestre les repositories
- Contient la logique métier complexe
- Validation des données
- Gestion des erreurs métier

**Exemple** :

```python
class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
    
    def authenticate(self, username: str, password: str) -> Optional[User]:
        user = self.user_repo.find_by_username(username)
        if user and self._verify_password(user, password):
            return user
        return None
```

### 4. UI Layer (Interface utilisateur)

**Responsabilité** : Affichage et interactions utilisateur

**Fichiers** :

- `src/ui/windows/` : Fenêtres principales
- `src/ui/dialogs/` : Dialogues modaux
- `src/ui/widgets/` : Composants réutilisables

**Principes** :

- Pas de logique métier dans l'UI
- Appelle les services pour les actions
- Gère uniquement l'affichage et les événements GTK
- Utilise le pattern MVC/MVP

**Exemple** :

```python
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, password_service, user):
        super().__init__(application=app)
        self.password_service = password_service
        self.user = user
        self._build_ui()
    
    def on_add_password_clicked(self, button):
        dialog = PasswordDialog(self, self.password_service)
        dialog.present()
```

## 🔄 Guide de refactoring étape par étape

### Étape 1 : Extraire les modèles ✅

**Fait** :

- ✅ `src/models/user.py`
- ✅ `src/models/password_entry.py`
- ✅ `src/models/category.py`

### Étape 2 : Extraire les services

**À faire** :

1. Copier `PasswordGenerator` → `src/services/password_generator.py`
2. Copier `PasswordCrypto` → `src/services/crypto_service.py`
3. Extraire logique auth de `UserManager` → `src/services/auth_service.py`
4. Créer `src/services/password_service.py` pour orchestrer

### Étape 3 : Extraire les repositories

**À faire** :

1. Créer `BaseRepository` avec connexion SQLite
2. Extraire SQL de `UserManager` → `UserRepository`
3. Extraire SQL de `PasswordDatabase` → `PasswordRepository`
4. Créer `CategoryRepository`

### Étape 4 : Refactorer l'UI

**À faire** :

1. Séparer chaque classe de dialogue dans son propre fichier
2. Créer des widgets réutilisables
3. Utiliser l'injection de dépendances pour les services

### Étape 5 : Créer le point d'entrée

**À faire** :

1. `src/main.py` : Point d'entrée simple
2. `src/app.py` : Classe PasswordManagerApplication refactorisée

### Étape 6 : Tests

**À faire** :

1. Tests unitaires pour chaque service
2. Tests d'intégration pour les workflows
3. Utiliser pytest et fixtures

## 🎨 Patterns utilisés

### Repository Pattern

Abstrait l'accès aux données, permet de changer facilement de backend (SQLite → PostgreSQL).

### Service Layer Pattern

Sépare la logique métier de l'infrastructure (UI, DB).

### Dependency Injection

Les services reçoivent leurs dépendances en constructeur.

### Factory Pattern

Pour créer les objets complexes (UserFactory, PasswordEntryFactory).

### Observer Pattern (GTK Signals)

GTK utilise des signals/callbacks pour la communication UI.

## 🔐 Principes SOLID appliqués

- **S**ingle Responsibility : Chaque classe a une responsabilité unique
- **O**pen/Closed : Extensible via interfaces/héritages
- **L**iskov Substitution : Les repositories implémentent une interface commune
- **I**nterface Segregation : Interfaces spécifiques et petites
- **D**ependency Inversion : Dépend d'abstractions, pas de concrétions

## 📊 Diagramme de dépendances

```text
main.py
  └── app.py
      ├── UI Layer
      │   ├── MainWindow
      │   ├── Dialogs
      │   └── Widgets
      │       └── → Services
      │
      └── Service Layer
          ├── AuthService
          ├── PasswordService
          ├── CryptoService
          └── PasswordGenerator
              └── → Repositories
                  ├── UserRepository
                  ├── PasswordRepository
                  └── CategoryRepository
                      └── → Models
                          ├── User
                          ├── PasswordEntry
                          └── Category
```

## 🧪 Tests

### Structure des tests

```python
# tests/unit/test_password_generator.py
import pytest
from src.services.password_generator import PasswordGenerator

def test_generate_password_default():
    password = PasswordGenerator.generate()
    assert len(password) == 16
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)

def test_generate_passphrase():
    phrase = PasswordGenerator.generate_passphrase(4)
    words = phrase[:-2].split('-')  # Enlever le nombre à la fin
    assert len(words) == 4
```

### Lancer les tests

```bash
# Tous les tests
pytest

# Tests unitaires seulement
pytest tests/unit/

# Avec couverture
pytest --cov=src --cov-report=html
```

## 🚀 Migration progressive

### Phase 1 : Coexistence (ACTUEL)

- Garder `password_manager.py` fonctionnel
- Créer la nouvelle structure en parallèle
- Tests pour valider la parité

### Phase 2 : Migration

- Migrer module par module
- Adapter les imports progressivement
- Tests à chaque étape

### Phase 3 : Finalisation

- Supprimer `password_manager.py`
- Mettre à jour tous les scripts
- Documentation finale

## 📚 Ressources

- [Python Architecture Patterns](https://www.cosmicpython.com/)
- [GTK4 Python Documentation](https://docs.gtk.org/gtk4/)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)

---

**Prochaine étape** : Voir `docs/DEVELOPMENT.md` pour le guide de développement complet.
