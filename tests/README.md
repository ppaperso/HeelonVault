# 🧪 Tests du Gestionnaire de Mots de Passe

## 📋 Structure des tests

```
tests/
├── __init__.py
├── README.md                          # Ce fichier
├── unit/                              # Tests unitaires
│   ├── __init__.py
│   ├── test_password_generator.py     # À créer
│   ├── test_crypto_service.py         # À créer
│   ├── test_auth_service.py           # À créer
│   └── test_models.py                 # À créer
│
├── integration/                       # Tests d'intégration
│   ├── __init__.py
│   ├── test_change_password.py        # Test changement mot de passe
│   ├── test_restrictions.py           # Test restrictions création compte
│   ├── test_url_field.py              # Test champ URL
│   ├── test_url_improvements.py       # Test améliorations URL
│   └── test_ui_improvements.py        # Test améliorations UI
│
└── fixtures/                          # Données de test
    └── test_data.py                   # À créer
```

## 🎯 Types de tests

### Tests unitaires (`unit/`)
Tests des composants individuels en isolation.

**À créer** :
- `test_password_generator.py` : Tests du générateur de mots de passe
- `test_crypto_service.py` : Tests du chiffrement AES-256-GCM
- `test_auth_service.py` : Tests d'authentification et hachage
- `test_models.py` : Tests des modèles de données

**Exemple** :
```python
# tests/unit/test_password_generator.py
import pytest
from src.services.password_generator import PasswordGenerator

def test_generate_password_default():
    password = PasswordGenerator.generate()
    assert len(password) == 16
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)
    assert any(c.isdigit() for c in password)

def test_generate_passphrase():
    phrase = PasswordGenerator.generate_passphrase(4)
    words = phrase[:-2].split('-')
    assert len(words) == 4
```

### Tests d'intégration (`integration/`)
Tests des workflows complets et des interactions entre composants.

**Existants** :
- `test_change_password.py` : Vérifie le changement de mot de passe personnel
- `test_restrictions.py` : Vérifie les restrictions de création de compte
- `test_url_field.py` : Vérifie la fonctionnalité du champ URL
- `test_url_improvements.py` : Vérifie les améliorations du champ URL
- `test_ui_improvements.py` : Vérifie les améliorations UI (Paned, username)

**Exemple** :
```python
# tests/integration/test_user_workflow.py
def test_complete_user_workflow():
    """Test du workflow complet d'un utilisateur."""
    # 1. Créer un utilisateur
    # 2. Se connecter
    # 3. Ajouter des mots de passe
    # 4. Changer le mot de passe maître
    # 5. Se reconnecter
    pass
```

## 🚀 Lancer les tests

### Tous les tests
```bash
pytest tests/
```

### Tests unitaires uniquement
```bash
pytest tests/unit/
```

### Tests d'intégration uniquement
```bash
pytest tests/integration/
```

### Un test spécifique
```bash
pytest tests/integration/test_change_password.py
```

### Avec couverture de code
```bash
pytest --cov=src --cov-report=html tests/
```

### Avec verbose
```bash
pytest -v tests/
```

## 📝 Tests d'intégration actuels

### test_change_password.py
**Objectif** : Vérifier la fonctionnalité de changement de mot de passe

**Tests** :
- ✅ Authentification avec mot de passe actuel
- ✅ Méthode `verify_user()` fonctionne
- ✅ Rejet du mauvais mot de passe actuel
- ✅ Méthode `change_user_password()` existe

**Usage** :
```bash
./venvpwdmanager/bin/python tests/integration/test_change_password.py
```

### test_restrictions.py
**Objectif** : Vérifier les restrictions de création de compte

**Tests** :
- ✅ Bouton "Créer un compte" supprimé de l'écran de login
- ✅ Note informative présente
- ✅ Bouton création dans "Gestion des utilisateurs" (admin)
- ✅ Sélection du rôle dans CreateUserDialog
- ✅ Architecture modulaire (src/services/auth_service.py)

**Usage** :
```bash
./venvpwdmanager/bin/python tests/integration/test_restrictions.py
```

### test_url_field.py
**Objectif** : Vérifier la présence et le fonctionnement du champ URL

**Tests** :
- ✅ Colonne `url TEXT` dans la base de données
- ✅ Champ de saisie dans AddEditDialog
- ✅ Affichage dans la vue détaillée
- ✅ Copie dans le presse-papiers
- ✅ Recherche par URL
- ✅ Champ optionnel

**Usage** :
```bash
./venvpwdmanager/bin/python tests/integration/test_url_field.py
```

### test_url_improvements.py
**Objectif** : Vérifier les améliorations du champ URL

**Tests** :
- ✅ Icône 🌐 dans le formulaire
- ✅ Placeholder et texte d'aide
- ✅ Bouton "Ouvrir dans le navigateur"
- ✅ Ajout automatique de https://
- ✅ Tooltips informatifs

**Usage** :
```bash
./venvpwdmanager/bin/python tests/integration/test_url_improvements.py
```

### test_ui_improvements.py
**Objectif** : Vérifier les améliorations de l'interface utilisateur

**Tests** :
- ✅ Paned vertical pour zone catégories
- ✅ Zone redimensionnable
- ✅ Champ username amélioré avec icône
- ✅ Placeholder et aide contextuelle

**Usage** :
```bash
./venvpwdmanager/bin/python tests/integration/test_ui_improvements.py
```

## 🔧 Configuration pytest

Créez un fichier `pytest.ini` à la racine du projet :

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
markers =
    unit: Tests unitaires
    integration: Tests d'intégration
    slow: Tests lents
```

## 📦 Dépendances de test

Ajoutez à `requirements-dev.txt` :

```txt
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
pytest-asyncio>=0.21.0
```

Installation :
```bash
./venvpwdmanager/bin/pip install -r requirements-dev.txt
```

## 📊 Couverture de code

Pour générer un rapport de couverture HTML :

```bash
pytest --cov=src --cov-report=html tests/
# Ouvrir htmlcov/index.html dans un navigateur
```

Objectif : **>80% de couverture**

## 🎯 Bonnes pratiques

### Nommage
- Fichiers : `test_*.py`
- Classes : `Test*`
- Fonctions : `test_*`

### Organisation
```python
def test_feature_scenario():
    """Description claire du test."""
    # Given (Arrange) - Préparation
    user = create_test_user()
    
    # When (Act) - Action
    result = user.authenticate('password')
    
    # Then (Assert) - Vérification
    assert result is not None
    assert result['username'] == 'test_user'
```

### Fixtures
```python
import pytest

@pytest.fixture
def test_user():
    """Créer un utilisateur de test."""
    return User(username='test', role='user')

def test_with_fixture(test_user):
    assert test_user.username == 'test'
```

## 🚀 Prochaines étapes

1. ✅ Déplacer les tests d'intégration existants (fait)
2. ⏳ Créer les tests unitaires pour les services
3. ⏳ Créer les tests unitaires pour les modèles
4. ⏳ Ajouter pytest et pytest-cov aux dépendances
5. ⏳ Configurer pytest.ini
6. ⏳ Atteindre >80% de couverture de code

## 📚 Ressources

- [Pytest Documentation](https://docs.pytest.org/)
- [Python Testing Best Practices](https://realpython.com/pytest-python-testing/)
- [Test-Driven Development (TDD)](https://testdriven.io/)

---

**Dernière mise à jour** : 19 novembre 2025  
**Tests existants** : 5 tests d'intégration  
**Tests à créer** : Tests unitaires
