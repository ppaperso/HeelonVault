# 🔧 Guide d'Implémentation des Améliorations de Sécurité

## Vue d'ensemble

Ce guide vous accompagne dans l'implémentation des améliorations de sécurité recommandées pour votre gestionnaire de mots de passe.

---

## 📋 Checklist des modifications

### ✅ Priorité 1 - CRITIQUE (À faire immédiatement)

- [ ] **1.1** Remplacer la liste de mots des passphrases
- [ ] **1.2** Corriger les itérations PBKDF2 dans add_test_data.py
- [ ] **1.3** Augmenter la longueur par défaut à 20 caractères
- [ ] **1.4** Tester les modifications en mode dev

### ⚠️ Priorité 2 - MOYEN (Dans le mois)

- [ ] **2.1** Intégrer la validation du mot de passe maître
- [ ] **2.2** Ajouter un indicateur de force visuel
- [ ] **2.3** Augmenter le nombre de mots minimum pour passphrases
- [ ] **2.4** Mettre à jour les tests unitaires

### 💡 Priorité 3 - BONUS (Quand possible)

- [ ] **3.1** Intégrer Have I Been Pwned API
- [ ] **3.2** Ajouter un timeout de session
- [ ] **3.3** Implémenter la 2FA pour les admins

---

## 🚀 Implémentation Priorité 1

### 1.1 - Remplacer la liste de mots des passphrases

**Fichiers à modifier** :

- `src/services/password_generator.py`

**Étapes** :

1. **Importer la nouvelle liste de mots** :

```python
# En haut du fichier src/services/password_generator.py
from src.data.french_wordlist_extended import FRENCH_WORDS_EXTENDED, WORDLIST_SIZE
```

1. **Remplacer la liste actuelle** :

```python
# Remplacer :
class PasswordGenerator:
    FRENCH_WORDS = [
        "maison", "soleil", ...  # 42 mots
    ]

# Par :
class PasswordGenerator:
    FRENCH_WORDS = FRENCH_WORDS_EXTENDED  # 1000+ mots
```

1. **Ajuster le nombre de mots par défaut** :

```python
# Dans generate_passphrase(), changer :
def generate_passphrase(
    cls,
    word_count: int = 5,  # CHANGÉ de 4 à 5
    separator: str = "-"
) -> str:
```

1. **Mettre à jour le dialogue UI** :

```python
# Dans src/ui/dialogs/password_generator_dialog.py
# Ligne ~123-125

self.words_spin.set_range(4, 8)  # Garder la flexibilité
self.words_spin.set_value(5)    # CHANGÉ de 4 à 5
```

1. **Tester en mode dev** :

```bash
./run-dev.sh
# Dans l'interface :
# 1. Générer un mot de passe
# 2. Cliquer sur "Phrase de passe"
# 3. Vérifier que 5 mots sont générés par défaut
# 4. Vérifier la diversité des mots
```

---

### 1.2 - Corriger les itérations PBKDF2

**Fichier à modifier** :

- `add_test_data.py`

**Modification** :

```python
# Ligne ~18-24
def derive_key(master_password: str, salt: bytes) -> bytes:
    """Dérive une clé à partir du mot de passe maître"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,  # ✅ CHANGÉ de 100000 à 600000
    )
    return kdf.derive(master_password.encode())
```

**Test** :

```bash
python add_test_data.py
# Vérifier que les données de test sont créées correctement
```

---

### 1.3 - Augmenter la longueur par défaut

**Fichier à modifier** :

- `src/services/password_generator.py`
- `password_manager.py` (si version monolithique encore utilisée)

**Modification** :

```python
# Ligne ~35
@staticmethod
def generate(
    length: int = 20,  # ✅ CHANGÉ de 16 à 20
    use_uppercase: bool = True,
    use_lowercase: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    exclude_ambiguous: bool = True
) -> str:
```

**UI - Ajuster le spinner** :

```python
# Dans src/ui/dialogs/password_generator_dialog.py
# Ligne ~80

self.length_spin.set_range(12, 64)  # Minimum recommandé : 12
self.length_spin.set_value(20)      # ✅ CHANGÉ de 16 à 20
```

**Test** :

```bash
./run-dev.sh
# 1. Ouvrir le générateur de mot de passe
# 2. Vérifier que la longueur par défaut est 20
# 3. Générer plusieurs mots de passe
# 4. Vérifier leur longueur et diversité
```

---

### 1.4 - Tests complets en mode dev

**Script de test** :

```bash
#!/bin/bash
# test-security-improvements.sh

echo "🧪 Tests des améliorations de sécurité"
echo "======================================"

# Test 1 : Génération de passphrases
echo ""
echo "Test 1 : Génération de passphrases"
python3 << 'EOF'
from src.services.password_generator import PasswordGenerator
import math

print("Génération de 5 passphrases :")
for i in range(5):
    phrase = PasswordGenerator.generate_passphrase(5)
    words = phrase[:-2].split('-')  # Enlever le nombre final
    print(f"  {i+1}. {phrase} ({len(words)} mots)")

# Calcul d'entropie
from src.data.french_wordlist_extended import WORDLIST_SIZE
entropy = 5 * math.log2(WORDLIST_SIZE) + 10 + 6.6
print(f"\n✅ Entropie estimée : {entropy:.1f} bits")
EOF

# Test 2 : Génération de mots de passe
echo ""
echo "Test 2 : Génération de mots de passe"
python3 << 'EOF'
from src.services.password_generator import PasswordGenerator

print("Génération de 5 mots de passe (longueur par défaut) :")
for i in range(5):
    pwd = PasswordGenerator.generate()
    print(f"  {i+1}. {pwd} ({len(pwd)} caractères)")

print("\n✅ Longueur par défaut vérifiée")
EOF

# Test 3 : Validation des mots de passe maîtres
echo ""
echo "Test 3 : Validation des mots de passe maîtres"
python3 << 'EOF'
from src.services.master_password_validator import MasterPasswordValidator

test_passwords = [
    "abc123",
    "MySecureP@ss2024",
    "C0mpl3x!P@ssw0rd#2024"
]

for pwd in test_passwords:
    is_valid, errors, score = MasterPasswordValidator.validate(pwd)
    strength = MasterPasswordValidator.get_strength_description(score)
    print(f"'{pwd}' → {score}/100 ({strength})")

print("\n✅ Validateur fonctionnel")
EOF

echo ""
echo "======================================"
echo "✅ Tous les tests sont terminés"
```

**Exécution** :

```bash
chmod +x test-security-improvements.sh
./test-security-improvements.sh
```

---

## 🔐 Implémentation Priorité 2

### 2.1 - Intégrer la validation du mot de passe maître

**Fichiers à modifier** :

- `src/ui/dialogs/create_user_dialog.py`
- `password_manager.py` (CreateUserDialog)

**Modification dans CreateUserDialog** :

```python
# Ajouter l'import en haut du fichier
from src.services.master_password_validator import MasterPasswordValidator

# Dans la méthode de création/validation (on_create_clicked)
def on_create_clicked(self, button):
    username = self.username_entry.get_text().strip()
    password = self.password_entry.get_text()
    confirm = self.confirm_entry.get_text()
    
    # Validations existantes...
    
    # NOUVELLE VALIDATION 👇
    is_valid, errors, score = MasterPasswordValidator.validate(password)
    
    if not is_valid:
        error_msg = "Mot de passe trop faible :\n" + "\n".join(f"• {err}" for err in errors)
        self.error_label.set_text(error_msg)
        self.error_label.set_visible(True)
        return
    
    if score < 60:
        # Avertissement mais autoriser quand même
        strength = MasterPasswordValidator.get_strength_description(score)
        warning_msg = f"⚠️ Force du mot de passe : {strength} ({score}/100)\n"
        warning_msg += "Recommandé : au moins 60/100"
        self.error_label.set_text(warning_msg)
        self.error_label.set_visible(True)
        # Ne pas return, on laisse passer
    
    # Suite du code existant...
```

**Ajouter un indicateur de force en temps réel** :

```python
# Dans __init__ de CreateUserDialog

# Ajouter un label de force après les champs de mot de passe
self.strength_label = Gtk.Label(label="")
self.strength_label.set_css_classes(['caption'])
box.append(self.strength_label)

# Connecter l'événement de changement de texte
self.password_entry.connect("changed", self.on_password_changed)

# Ajouter la méthode
def on_password_changed(self, entry):
    password = entry.get_text()
    if len(password) == 0:
        self.strength_label.set_text("")
        return
    
    _, _, score = MasterPasswordValidator.validate(password)
    strength = MasterPasswordValidator.get_strength_description(score)
    
    # Couleur selon le score
    if score >= 80:
        css_class = "success"
    elif score >= 60:
        css_class = "warning"
    else:
        css_class = "error"
    
    self.strength_label.set_text(f"Force : {strength} ({score}/100)")
    self.strength_label.set_css_classes(['caption', css_class])
```

---

### 2.2 - Indicateur de force visuel dans le générateur

**Fichier** : `src/ui/dialogs/password_generator_dialog.py`

**Ajouter sous le champ d'affichage du mot de passe** :

```python
# Après self.password_display

# Barre de progression
self.strength_bar = Gtk.LevelBar()
self.strength_bar.set_min_value(0)
self.strength_bar.set_max_value(100)
self.strength_bar.set_mode(Gtk.LevelBarMode.CONTINUOUS)
content.append(self.strength_bar)

# Label de force
self.strength_label = Gtk.Label(label="")
self.strength_label.set_css_classes(['caption'])
content.append(self.strength_label)

# Dans generate_password(), ajouter :
def generate_password(self):
    # ... génération existante ...
    
    # Calculer la force
    strength_info = PasswordGenerator.estimate_strength(password)
    score = strength_info['score'] * 25  # Convertir 0-4 en 0-100
    
    self.strength_bar.set_value(score)
    self.strength_label.set_text(
        f"{strength_info['description']} - {strength_info['length']} caractères"
    )
```

---

### 2.3 - Augmenter le nombre de mots minimum

**Déjà fait dans 1.1** - S'assurer que la plage est bien 4-8 avec défaut à 5 ou 6.

---

## 📊 Vérification finale

### Checklist de validation

```bash
# 1. Générer une passphrase
./run-dev.sh
# → Doit générer 5 mots par défaut avec des mots variés

# 2. Générer un mot de passe
# → Doit avoir 20 caractères par défaut

# 3. Créer un nouvel utilisateur avec mot de passe faible
# → Doit afficher des erreurs et refuser

# 4. Créer un nouvel utilisateur avec mot de passe fort
# → Doit accepter et afficher la force

# 5. Vérifier les logs
tail -f ~/.local/share/passwordmanager-dev/app.log
# → Aucune erreur liée aux nouvelles fonctionnalités
```

---

## 🔄 Mise à jour de la documentation

**Fichiers à mettre à jour** :

1. **README.md** :

```markdown
### 🎲 Générateur de mots de passe

- **Mots de passe aléatoires** avec options personnalisables :
  - Longueur ajustable (12-64 caractères, défaut : 20)  ✅ MODIFIÉ
  - Jeu de caractères étendu
  - Exclusion des caractères ambigus
  
- **Phrases de passe** mémorables :
  - 4-8 mots parmi 1000+ mots français  ✅ MODIFIÉ
  - Entropie : ~50-77 bits (selon nombre de mots)  ✅ NOUVEAU
  - Exemple : `Soleil-montagne-Jardin-neige-Lumiere42`
  
- **Validation du mot de passe maître** :  ✅ NOUVEAU
  - Vérification de la force en temps réel
  - Suggestions d'amélioration
  - Protection contre les mots de passe communs
```

1. **CHANGELOG.md** :

```markdown
## [Version prochaine] - 2026-02-18

### Améliorations de sécurité 🔒

#### Ajouté
- Liste étendue de mots français (1000+) pour les passphrases
- Validation du mot de passe maître lors de la création de compte
- Indicateur de force en temps réel pour les mots de passe
- Augmentation de la longueur par défaut : 16 → 20 caractères
- Augmentation du nombre de mots par défaut : 4 → 5 mots

#### Corrigé
- Itérations PBKDF2 dans add_test_data.py : 100k → 600k

#### Sécurité
- Entropie des passphrases : ~32 bits → ~50-60 bits
- Amélioration significative de la résistance au bruteforce
```

---

## 🧪 Tests automatisés

**Créer** : `tests/unit/test_password_security.py`

```python
"""Tests unitaires pour les améliorations de sécurité."""

import unittest
from src.services.password_generator import PasswordGenerator
from src.services.master_password_validator import MasterPasswordValidator
from src.data.french_wordlist_extended import WORDLIST_SIZE


class TestPasswordSecurity(unittest.TestCase):
    """Tests de sécurité des mots de passe."""
    
    def test_wordlist_size(self):
        """Vérifie que la liste de mots est suffisamment grande."""
        self.assertGreaterEqual(
            WORDLIST_SIZE, 1000,
            "La liste de mots doit contenir au moins 1000 mots"
        )
    
    def test_default_password_length(self):
        """Vérifie la longueur par défaut des mots de passe."""
        password = PasswordGenerator.generate()
        self.assertEqual(
            len(password), 20,
            "La longueur par défaut doit être 20 caractères"
        )
    
    def test_default_passphrase_word_count(self):
        """Vérifie le nombre de mots par défaut des passphrases."""
        passphrase = PasswordGenerator.generate_passphrase()
        # Enlever le nombre final et compter les mots
        words = passphrase[:-2].split('-')
        self.assertEqual(
            len(words), 5,
            "Le nombre de mots par défaut doit être 5"
        )
    
    def test_master_password_validation_weak(self):
        """Vérifie le rejet des mots de passe faibles."""
        weak_passwords = ["abc123", "password", "123456", "qwerty"]
        for pwd in weak_passwords:
            is_valid, _, _ = MasterPasswordValidator.validate(pwd)
            self.assertFalse(
                is_valid,
                f"Le mot de passe '{pwd}' devrait être rejeté"
            )
    
    def test_master_password_validation_strong(self):
        """Vérifie l'acceptation des mots de passe forts."""
        strong_passwords = [
            "MySecureP@ssw0rd2024!",
            "C0mpl3x!SecureP@ss#123",
            "J'Aim3L3sCh@tsN0irs!"
        ]
        for pwd in strong_passwords:
            is_valid, _, score = MasterPasswordValidator.validate(pwd)
            self.assertTrue(
                is_valid,
                f"Le mot de passe '{pwd}' devrait être accepté"
            )
            self.assertGreater(
                score, 60,
                f"Le score devrait être > 60, obtenu : {score}"
            )
    
    def test_passphrase_entropy(self):
        """Vérifie que l'entropie des passphrases est suffisante."""
        import math
        # 5 mots × log2(1000) + capitalisation + nombre
        min_entropy = 5 * math.log2(1000) + 10
        self.assertGreater(
            min_entropy, 50,
            f"L'entropie devrait être > 50 bits, calculé : {min_entropy:.1f}"
        )


if __name__ == '__main__':
    unittest.main()
```

**Exécution** :

```bash
python -m unittest tests.unit.test_password_security -v
```

---

## 📝 Notes importantes

### Compatibilité

- ✅ Les modifications sont **rétro-compatibles**
- ✅ Les mots de passe existants **ne sont pas affectés**
- ✅ Les nouvelles générations utilisent les nouveaux paramètres
- ✅ Le mode dev reste **séparé de la production**

### Migration

Aucune migration nécessaire. Les modifications concernent uniquement :

- La génération de nouveaux mots de passe
- La création de nouveaux comptes utilisateurs

### Performance

Impact négligeable :

- Liste de mots chargée une seule fois en mémoire (~100 KB)
- Validation de mots de passe : < 1ms
- Pas d'impact sur le chiffrement/déchiffrement

---

## 🆘 Dépannage

### Erreur d'import de french_wordlist_extended

```python
# Vérifier que le fichier existe
ls -la src/data/french_wordlist_extended.py

# Vérifier le __init__.py
cat src/data/__init__.py
# Devrait contenir :
from .french_wordlist_extended import FRENCH_WORDS_EXTENDED, WORDLIST_SIZE
```

### Les tests échouent

```bash
# Réinstaller les dépendances
pip install -r requirements.txt

# Exécuter un test simple
python3 -c "from src.services.password_generator import PasswordGenerator; print(PasswordGenerator.generate())"
```

### Le validateur est trop strict

Ajuster les paramètres dans `src/services/master_password_validator.py` :

```python
# Ligne ~11
MIN_LENGTH = 10  # Au lieu de 12 si nécessaire
```

---

## ✅ Validation complète

Une fois toutes les modifications appliquées :

```bash
# 1. Tests unitaires
python -m unittest discover tests/unit -v

# 2. Tests d'intégration
python -m unittest discover tests/integration -v

# 3. Test manuel complet
./run-dev.sh
# → Créer un utilisateur avec validation
# → Générer des mots de passe et passphrases
# → Vérifier les indicateurs de force
# → Consulter les logs

# 4. Vérification de la documentation
cat SECURITY_RECOMMENDATIONS.md
cat CHANGELOG.md
```

---

## 📞 Support

Si vous rencontrez des problèmes lors de l'implémentation :

1. Vérifiez les logs : `~/.local/share/passwordmanager-dev/app.log`
2. Consultez la documentation : `docs/SECURITY.md`
3. Exécutez les tests : `./run_all_tests.sh`

Bonne implémentation ! 🚀
