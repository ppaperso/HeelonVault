# Guide de Contribution

Merci de votre intérêt pour contribuer au projet Password Manager ! 🎉

Ce document explique comment contribuer efficacement au projet.

---

## 📋 Table des Matières

1. [Code de Conduite](#code-de-conduite)
2. [Comment contribuer](#comment-contribuer)
3. [Configuration de l'environnement de développement](#configuration-de-lenvironnement-de-développement)
4. [Standards de code](#standards-de-code)
5. [Tests](#tests)
6. [Documentation](#documentation)
7. [Soumettre une Pull Request](#soumettre-une-pull-request)
8. [Signaler un bug](#signaler-un-bug)
9. [Proposer une fonctionnalité](#proposer-une-fonctionnalité)
10. [Questions de sécurité](#questions-de-sécurité)

---

## Code de Conduite

Ce projet adhère au [Code de Conduite](CODE_OF_CONDUCT.md). En participant, vous vous engagez à respecter ses termes.

---

## Comment contribuer

Il existe plusieurs façons de contribuer :

- 🐛 **Signaler des bugs** via les [Issues](https://github.com/[USERNAME]/password-manager/issues)
- ✨ **Proposer de nouvelles fonctionnalités** via les [Issues](https://github.com/[USERNAME]/password-manager/issues)
- 📝 **Améliorer la documentation** (README, guides, commentaires)
- 🌍 **Traduire l'application** (voir `locales/`)
- 💻 **Contribuer du code** (corrections de bugs, nouvelles fonctionnalités)
- 🔍 **Auditer la sécurité** (voir [SECURITY.md](SECURITY.md))

---

## Configuration de l'environnement de développement

### Prérequis

**Système d'exploitation** : Linux (testé sur Ubuntu 22.04+)

**Dépendances système** :

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    python3.10 \
    python3-pip \
    python3-venv \
    libgirepository1.0-dev \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    gcc \
    libcairo2-dev \
    pkg-config
```

### Installation

1. **Fork et clone** le dépôt :

```bash
git clone https://github.com/[VOTRE-USERNAME]/password-manager.git
cd password-manager
```

1. **Créer l'environnement virtuel** :

```bash
python3 -m venv venv-dev
source venv-dev/bin/activate
```

1. **Installer les dépendances** :

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"  # Installe les dépendances de développement
```

1. **Vérifier l'installation** :

```bash
python -m pytest tests/ -v
./test-app.sh
```

### Mode développement

**Lancer l'application en mode dev** :

```bash
./run-dev.sh
```

Cela utilise un répertoire de données isolé : `./src/data/` (ne touche pas aux données de production).

---

## Standards de code

### Style de code

Nous utilisons [Ruff](https://github.com/astral-sh/ruff) pour le formatage et le linting :

```bash
# Formater automatiquement le code
ruff format .

# Vérifier les problèmes
ruff check .

# Corriger automatiquement (quand possible)
ruff check --fix .
```

**Règles principales** :

- **Longueur de ligne** : 100 caractères maximum
- **Imports** : triés automatiquement (isort)
- **Naming** : PEP 8 (snake_case pour fonctions/variables, PascalCase pour classes)
- **Type hints** : obligatoires pour les nouvelles fonctions publiques

### Exemple de fonction bien documentée

```python
def encrypt_password(password: str, key: bytes) -> str:
    """Chiffre un mot de passe avec AES-256-GCM.
    
    Args:
        password: Le mot de passe en clair à chiffrer
        key: La clé de chiffrement (256 bits, dérivée du mot de passe maître)
    
    Returns:
        str: Le mot de passe chiffré encodé en base64 (nonce || ciphertext || tag)
    
    Raises:
        ValueError: Si la clé n'a pas la bonne longueur (32 bytes)
        cryptography.exceptions.InvalidTag: Si le chiffrement échoue
    
    Example:
        >>> key = PBKDF2HMAC(...).derive(b"master_password")
        >>> encrypted = encrypt_password("MyP@ssw0rd", key)
        >>> print(len(encrypted))  # Base64 encoded
        64
    """
    if len(key) != 32:
        raise ValueError("Key must be 32 bytes")
    
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, password.encode(), None)
    
    encrypted = nonce + ciphertext
    return base64.b64encode(encrypted).decode()
```

### Conventions de nommage

| Type | Convention | Exemple |
| ------ | ------------ | --------- |
| Fichiers | `snake_case.py` | `password_generator.py` |
| Classes | `PascalCase` | `PasswordGenerator` |
| Fonctions | `snake_case()` | `generate_password()` |
| Variables | `snake_case` | `master_password` |
| Constantes | `UPPER_SNAKE_CASE` | `MAX_ATTEMPTS` |
| Privé | `_prefixe` | `_internal_method()` |

---

## Tests

### Exécuter les tests

```bash
# Tous les tests
python -m pytest tests/ -v

# Tests avec couverture
python -m pytest tests/ -v --cov=src --cov-report=html

# Tests de sécurité spécifiques
./run-security-tests.sh

# Test d'un module spécifique
python -m pytest tests/test_password_generator.py -v
```

### Écrire des tests

Chaque nouvelle fonctionnalité doit avoir des tests correspondants.

**Exemple de test** :

```python
# tests/test_password_generator.py
import pytest
from src.services.password_generator import PasswordGenerator


def test_generate_password_default():
    """Test la génération avec paramètres par défaut."""
    password = PasswordGenerator.generate()
    
    assert len(password) == 20
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)
    assert any(c.isdigit() for c in password)


def test_generate_password_custom_length():
    """Test la génération avec longueur personnalisée."""
    password = PasswordGenerator.generate(length=30)
    
    assert len(password) == 30


def test_generate_passphrase():
    """Test la génération de passphrase."""
    passphrase = PasswordGenerator.generate_passphrase(word_count=5)
    
    words = passphrase[:-2].split('-')  # Retirer les 2 chiffres finaux
    assert len(words) == 5
    assert all(word.isalpha() for word in words)


@pytest.mark.parametrize("length", [8, 16, 20, 32, 64])
def test_generate_password_various_lengths(length):
    """Test avec différentes longueurs."""
    password = PasswordGenerator.generate(length=length)
    assert len(password) == length
```

### Couverture de tests

Objectif : **>70%** de couverture globale.

Les zones critiques (cryptographie, validation) doivent avoir **>90%** de couverture.

---

## Documentation

### Documentation du code

- **Docstrings** : obligatoires pour toutes les fonctions/classes publiques (format Google ou NumPy)
- **Commentaires** : expliquer le "pourquoi", pas le "quoi"
- **Type hints** : utiliser pour une meilleure autocomplétion

### Documentation utilisateur

- **README.md** : guide de démarrage rapide
- **docs/** : documentation détaillée (architecture, sécurité, guides)
- **CHANGELOG.md** : historique des versions

### Mettre à jour la documentation

Quand vous ajoutez une fonctionnalité :

1. ✅ Ajouter une docstring complète
2. ✅ Mettre à jour le README si nécessaire
3. ✅ Créer/mettre à jour un guide dans `docs/` si pertinent
4. ✅ Ajouter une entrée dans CHANGELOG.md (section "Unreleased")

---

## Soumettre une Pull Request

### Processus

1. **Fork** le projet
2. **Créez une branche** descriptive :

   ```bash
   git checkout -b feature/ma-super-fonctionnalite
   # ou
   git checkout -b fix/correction-bug-xyz
   ```

3. **Committez** vos changements :

   ```bash
   git commit -m "feat: ajout de la génération de passphrases

   - Ajout de la méthode generate_passphrase()
   - Wordlist de 1053 mots français
   - Tests unitaires complets
   
   Closes #42"
   ```

4. **Pushez** vers votre fork :

   ```bash
   git push origin feature/ma-super-fonctionnalite
   ```

5. **Ouvrez une Pull Request** sur GitHub avec :
   - **Titre clair** : `feat: ajout génération passphrases` ou `fix: correction validation email`
   - **Description détaillée** : quoi, pourquoi, comment
   - **Références** : `Fixes #123`, `Closes #456`
   - **Screenshots** (si UI modifiée)
   - **Tests** : confirmation que tous les tests passent

### Format des commits

Nous suivons [Conventional Commits](https://www.conventionalcommits.org/) :

- `feat:` - Nouvelle fonctionnalité
- `fix:` - Correction de bug
- `docs:` - Documentation uniquement
- `style:` - Formatage (pas de changement de code)
- `refactor:` - Refactorisation (pas de nouvelle fonctionnalité ni correction)
- `perf:` - Amélioration de performance
- `test:` - Ajout/correction de tests
- `chore:` - Maintenance (build, CI, dépendances)
- `security:` - Correctif de sécurité

**Exemples** :

```text
feat: ajout de l'export CSV
fix: correction du crash au démarrage sur Python 3.10
docs: mise à jour du guide d'installation
security: correction de la validation des entrées utilisateur
```

### Checklist avant la PR

- [ ] ✅ Le code compile sans erreur
- [ ] ✅ Tous les tests passent (`pytest tests/ -v`)
- [ ] ✅ Ruff ne signale aucun problème (`ruff check .`)
- [ ] ✅ La couverture de tests n'a pas diminué
- [ ] ✅ La documentation est à jour
- [ ] ✅ CHANGELOG.md est mis à jour
- [ ] ✅ Pas de secrets/credentials dans le code
- [ ] ✅ Les commits suivent le format Conventional Commits

---

## Signaler un bug

### Où signaler

Ouvrez une [Issue](https://github.com/[USERNAME]/password-manager/issues) avec le label `bug`.

### Informations à inclure

```markdown
**Description du bug**
Description claire et concise du problème.

**Reproduction**
Étapes pour reproduire le comportement :
1. Aller à '...'
2. Cliquer sur '...'
3. Défiler jusqu'à '...'
4. Voir l'erreur

**Comportement attendu**
Ce qui devrait se passer normalement.

**Comportement actuel**
Ce qui se passe actuellement.

**Screenshots**
Si possible, ajouter des captures d'écran.

**Environnement**
- OS: [ex: Ubuntu 22.04]
- Version Python: [ex: 3.10.12]
- Version de l'app: [ex: 0.4.0-beta]
- Installation: [source / package]

**Logs**
```

Coller les logs pertinents ici

```text

**Contexte additionnel**
Toute autre information utile.
```

---

## Proposer une fonctionnalité

### Avant de proposer

1. **Cherchez** dans les [Issues](https://github.com/[USERNAME]/password-manager/issues) existantes
2. **Discutez** dans [Discussions](https://github.com/[USERNAME]/password-manager/discussions) si pertinent
3. **Considérez** si cela s'aligne avec les objectifs du projet

### Format de proposition

Ouvrez une [Issue](https://github.com/[USERNAME]/password-manager/issues) avec le label `enhancement`.

```markdown
**Problème à résoudre**
Quel problème utilisateur cette fonctionnalité résout-elle ?

**Solution proposée**
Description claire de ce que vous voulez ajouter.

**Alternatives considérées**
Autres solutions envisagées.

**Impact sur la sécurité**
Y a-t-il des implications de sécurité ?

**Mockups / Exemples**
Si UI, ajouter des mockups ou screenshots.

**Priorité suggérée**
Faible / Moyenne / Haute

**Volontaire pour implémenter**
Oui / Non / Besoin d'aide
```

---

## Questions de sécurité

### ⚠️ NE CRÉEZ PAS D'ISSUE PUBLIQUE POUR LES VULNÉRABILITÉS

Pour les problèmes de sécurité, suivez la [Politique de Sécurité](SECURITY.md) :

📧 **Email** : <security@heelonys.fr>

Nous répondrons sous 48h et travaillerons avec vous sur une divulgation responsable.

---

## 🎨 Contribution UI/UX

### Design

Nous suivons les [GNOME Human Interface Guidelines](https://developer.gnome.org/hig/).

- **Toolkit** : GTK4 + Libadwaita
- **Icônes** : Icon theme système (Adwaita)
- **Spacing** : Multiples de 6px
- **Palette** : Utiliser les couleurs système Adwaita

### Fichiers UI

Les interfaces sont définies dans :

- `src/ui/dialogs/` - Dialogues
- `src/ui/widgets/` - Widgets personnalisés

Utiliser Glade ou code Python pour construire l'UI.

---

## 🌍 Traductions

### Ajouter une langue

1. Créer le dossier : `locales/[CODE_LANGUE]/LC_MESSAGES/`
2. Copier `locales/messages.pot` vers `[CODE_LANGUE]/LC_MESSAGES/password-manager.po`
3. Traduire les chaînes dans le fichier `.po`
4. Compiler : `msgfmt password-manager.po -o password-manager.mo`

### Mettre à jour les traductions

```bash
# Extraire les nouvelles chaînes
xgettext -o locales/messages.pot src/**/*.py

# Mettre à jour les fichiers .po existants
msgmerge --update locales/fr/LC_MESSAGES/password-manager.po locales/messages.pot
```

---

## 📞 Obtenir de l'aide

- **Questions générales** : [GitHub Discussions](https://github.com/[USERNAME]/password-manager/discussions)
- **Chat** : [À CONFIGURER - Discord/Matrix/IRC]
- **Documentation** : [docs/](docs/)

---

## 🏆 Remerciements

Merci à tous les contributeurs qui font vivre ce projet ! 🎉

Votre contribution sera listée dans :

- [CHANGELOG.md](CHANGELOG.md)
- [GitHub Contributors](https://github.com/[USERNAME]/password-manager/graphs/contributors)
- [CONTRIBUTORS.md](CONTRIBUTORS.md) (si créé)

---

## 📄 Licence

En contribuant, vous acceptez que vos contributions soient licenciées sous la [Licence MIT](LICENSE).

---

**Merci de contribuer !** 💙

Si vous avez des questions sur ce guide, n'hésitez pas à ouvrir une issue ou discussion.
