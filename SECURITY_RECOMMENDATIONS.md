# 🔒 Recommandations de Sécurité

## Date d'analyse : 18 février 2026

## Résumé Exécutif

✅ **POSITIF** : Le gestionnaire utilise des standards cryptographiques modernes (AES-256-GCM, PBKDF2 600k itérations, module `secrets`)

⚠️ **AMÉLIORATION NÉCESSAIRE** : L'entropie des passphrases est insuffisante (32 bits au lieu de 77+ bits recommandés)

---

## 🔴 CRITIQUE - Entropie insuffisante des passphrases

### Problème actuel

- Liste de seulement **42 mots français**
- Entropie totale : ~32 bits (4 mots)
- **RISQUE** : Attaque par dictionnaire ciblé possible

### Solution recommandée

Utiliser une liste de **7776 mots** (EFF Diceware ou équivalent français)

**Entropie améliorée** :

- 4 mots parmi 7776 : log₂(7776⁴) ≈ 51.7 bits
- 5 mots parmi 7776 : log₂(7776⁵) ≈ 64.6 bits  
- 6 mots parmi 7776 : log₂(7776⁶) ≈ 77.5 bits ✅ (recommandé)

### Implémentation

#### Option 1 : Liste EFF Diceware (anglais)

```python
# Télécharger : https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt
DICEWARE_WORDS = [...]  # 7776 mots
```

#### Option 2 : Liste française étendue

Créer une liste de ~8000 mots français courants à partir de :

- Liste de fréquence Lexique 3.83
- Mots de 4-8 lettres uniquement
- Sans caractères spéciaux ni accents (pour compatibilité)

#### Option 3 : Compromis (court terme)

Augmenter immédiatement à **500+ mots** et passer à 5-6 mots minimum :

```python
FRENCH_WORDS = [
    # Ajouter 458+ mots supplémentaires...
    "maison", "soleil", "jardin", "montagne", ...,
    "fenetre", "ordinateur", "telephone", "voiture", ...
]
```

Avec 500 mots et 5 mots par phrase : log₂(500⁵) ≈ 44.8 bits (acceptable minimum)

---

## 🟡 MOYEN - Longueur par défaut des mots de passe

### Recommandation

Augmenter la longueur par défaut de **16 à 20 caractères**

**Justification** :

- Les GPUs modernes peuvent tester des milliards de hash/sec
- AES-256 mérite une clé d'entropie équivalente
- 20 caractères ≈ 130 bits d'entropie (avec jeu complet)

### Modification

```python
# src/services/password_generator.py
def generate(
    length: int = 20,  # CHANGÉ de 16 à 20
    ...
)
```

---

## 🟡 MOYEN - Validation du mot de passe maître

### Problème

Aucune validation de la force du mot de passe maître lors de la création.

### Recommandation-

Implémenter des exigences minimales :

```python
def validate_master_password(password: str) -> tuple[bool, str]:
    """Valide la force du mot de passe maître.
    
    Returns:
        (is_valid, error_message)
    """
    if len(password) < 12:
        return False, "Minimum 12 caractères requis"
    
    if not any(c.isupper() for c in password):
        return False, "Au moins une majuscule requise"
    
    if not any(c.islower() for c in password):
        return False, "Au moins une minuscule requise"
    
    if not any(c.isdigit() for c in password):
        return False, "Au moins un chiffre requis"
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Au moins un symbole requis"
    
    # Vérifier contre les mots de passe communs
    common_passwords = ["password", "Password123!", "admin123", ...]
    if password.lower() in common_passwords:
        return False, "Mot de passe trop commun"
    
    return True, ""
```

---

## 🟢 AMÉLIORATIONS SUGGÉRÉES (non critiques)

### 1. Protection Have I Been Pwned (HIBP)

Vérifier si le mot de passe a été compromis ailleurs :

```python
import hashlib
import requests

def check_password_pwned(password: str) -> tuple[bool, int]:
    """Vérifie si le mot de passe est dans HIBP.
    
    Returns:
        (is_pwned, occurrence_count)
    """
    sha1_hash = hashlib.sha1(password.encode()).hexdigest().upper()
    prefix = sha1_hash[:5]
    suffix = sha1_hash[5:]
    
    # API k-anonymity : on n'envoie que les 5 premiers caractères
    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    response = requests.get(url, timeout=5)
    
    if response.status_code != 200:
        return False, 0
    
    for line in response.text.splitlines():
        hash_suffix, count = line.split(':')
        if hash_suffix == suffix:
            return True, int(count)
    
    return False, 0
```

### 2. Indicateur de force visuel

Ajouter une barre de progression dans le générateur :

```text
[████████████░░░░] Fort (87/100)
Entropie : 65.5 bits
Temps estimé de crack : 2.3 milliards d'années
```

### 3. Timeout de session

Verrouiller automatiquement après X minutes d'inactivité :

```python
IDLE_TIMEOUT_MINUTES = 15
```

### 4. Double authentification (2FA)

Ajouter TOTP (Google Authenticator) pour les admins :

- Utiliser `pyotp` library
- QR code lors de l'activation
- Code de secours

### 5. Export chiffré

Permettre l'export avec chiffrement GPG ou mot de passe séparé

### 6. Avertissement d'âge de mot de passe

Notifier si un mot de passe n'a pas été changé depuis 90+ jours (déjà partiellement implémenté avec `password_age`)

### 7. Détection de doublons

Avertir si le même mot de passe est utilisé plusieurs fois (déjà partiellement implémenté)

---

## 🔧 Correctif du fichier add_test_data.py

**Problème** : Utilise 100 000 itérations au lieu de 600 000

```python
# add_test_data.py ligne ~18
kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=salt,
    iterations=600000,  # CHANGÉ de 100000 à 600000
)
```

---

## 📊 Priorités d'implémentation

### Priorité 1 (CRITIQUE - à faire immédiatement)

1. ✅ Augmenter la liste de mots pour passphrases (500+ minimum, 7776 idéal)
2. ✅ Corriger add_test_data.py (600k itérations)

### Priorité 2 (MOYEN - dans le mois)

1. Validation du mot de passe maître
2. Augmenter longueur par défaut à 20 caractères
3. Indicateur de force visuel

### Priorité 3 (BONUS - quand possible)

1. Check HIBP
2. Timeout de session
3. 2FA pour admins
4. Export chiffré

---

## ✅ Ce qui est déjà excellent

1. ✅ Chiffrement AES-256-GCM (meilleur algorithme actuel)
2. ✅ PBKDF2 600 000 itérations (conforme aux standards 2023+)
3. ✅ Module `secrets` pour génération aléatoire
4. ✅ Protection anti-brute force implémentée
5. ✅ Salt unique par utilisateur
6. ✅ Nonce unique par entrée
7. ✅ Permissions fichiers strictes (600)
8. ✅ Séparation des données par utilisateur
9. ✅ Journalisation de sécurité
10. ✅ Mode dev séparé

---

## 📚 Références

- OWASP Password Storage Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>
- NIST SP 800-63B Digital Identity Guidelines: <https://pages.nist.gov/800-63-3/sp800-63b.html>
- EFF Diceware Wordlist: <https://www.eff.org/deeplinks/2016/07/new-wordlists-random-passphrases>
- Have I Been Pwned API: <https://haveibeenpwned.com/API/v3>

---

## 🎯 Conclusion

**Note générale : 7.5/10** :

Le gestionnaire utilise d'excellentes pratiques cryptographiques modernes. Les deux principaux points à adresser sont :

1. **L'entropie des passphrases** (facilement corrigeable en ajoutant des mots)
2. **La validation du mot de passe maître** (protection de l'utilisateur contre lui-même)

Une fois ces deux points adressés, le niveau de sécurité sera excellent (9/10).
