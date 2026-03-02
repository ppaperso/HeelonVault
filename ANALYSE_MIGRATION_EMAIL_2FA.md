# 🔍 Analyse de Faisabilité - Migration vers Email + 2FA

**Date** : 2 mars 2026  
**Analysé par** : AI Assistant  
**Version actuelle** : 0.4.0-beta  
**Type** : Analyse pré-implémentation (sans modification de code)

---

## 📋 Résumé Exécutif

Cette analyse évalue la faisabilité technique d'une migration majeure du système d'authentification :

- **Objectif 1** : Remplacer username par email comme identifiant unique
- **Objectif 2** : Ajouter 2FA obligatoire (TOTP)
- **Objectif 3** : Maintenir le niveau de sécurité actuel (voire l'améliorer)

**Verdict préliminaire** : ✅ **FAISABLE** avec des précautions importantes

**Complexité estimée** : 🟠 **MOYENNE-HAUTE** (15-20h de développement)

**Risques identifiés** : 🟡 **MODÉRÉS** (régression sécurité possible si mal implémenté)

---

## 🏗️ Architecture Actuelle

### Schéma de stockage

```text
~/.local/share/password-manager/
├── users.db                        # Table users
│   ├── username (UNIQUE, TEXT)     # ← Identifiant actuel
│   ├── password_hash (TEXT)        # PBKDF2(password, salt, 600k)
│   ├── salt (TEXT, base64)         # Salt individuel
│   ├── role (TEXT)                 # 'admin' ou 'user'
│   ├── created_at (TIMESTAMP)
│   └── last_login (TIMESTAMP)
│
├── passwords_[username].db         # Une DB par utilisateur
│   └── [Données chiffrées AES-256-GCM]
│
└── salt_[username].bin             # Salt pour dérivation clé crypto
    └── [32 bytes binaires]         # Utilisé par CryptoService
```

### Flow d'authentification actuel

```text
1. UserSelectionDialog
   └── Liste tous les users de users.db
   └── SELECT username, role, created_at, last_login

2. LoginDialog(username)
   ├── Vérifie LoginAttemptTracker(username)
   ├── User saisit password
   └── AuthService.authenticate(username, password)
       ├── SELECT password_hash, salt FROM users WHERE username = ?
       ├── PBKDF2(password, salt, 600k) → derived_hash
       ├── Compare derived_hash == stored_hash
       └── Si OK → Retourne {id, username, role, salt}

3. on_user_authenticated(user_info, master_password)
   ├── Charge salt_{username}.bin
   ├── CryptoService(master_password, salt) → Dérive clé crypto
   ├── Ouvre passwords_{username}.db
   └── PasswordService prêt à chiffrer/déchiffrer
```

### Points critiques

| Aspect | État actuel | Dépendance au username |
| -------- | ------------- | ------------------------ |
| **Identifiant unique** | `username` | ✅ Clé primaire |
| **Nom de fichier DB** | `passwords_{username}.db` | ✅ Direct |
| **Nom de fichier salt** | `salt_{username}.bin` | ✅ Direct |
| **Rate limiting** | LoginAttemptTracker par username | ✅ Dict[username] |
| **Logs** | Logger avec username | ✅ Traçabilité |

---

## 1️⃣ Migration vers Email comme Identifiant

### A. Analyse d'impact sur users.db

#### ✅ Modifications de schéma proposées

```sql
-- AVANT (actuel)
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,          -- ← Identifiant actuel
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- APRÈS (proposé)
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,             -- ← Nouvel identifiant
    email_hash TEXT UNIQUE NOT NULL,        -- ← SHA-256(email) pour privacy
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    secret_2fa TEXT,                        -- ← Secret TOTP chiffré (voir section 2)
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    last_password_change TIMESTAMP,
    
    -- Nouvelles colonnes de sécurité
    failed_login_attempts INTEGER DEFAULT 0,
    last_failed_attempt TIMESTAMP,
    account_locked_until TIMESTAMP
);

-- Migration des données existantes
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN email_hash TEXT;
UPDATE users SET email = username || '@local.migration',
                 email_hash = hex(sha256(email))
WHERE email IS NULL;
```

#### 🤔 Faut-il hasher l'email ?

**Ma recommandation** : ✅ **OUI, absolument**

**Justification** :

1. **Protection en cas de vol de users.db** :

   ```text
   Sans hash :
   - Attaquant vole users.db
   - Voit TOUS les emails en clair
   - Peut faire du phishing ciblé
   - Peut croiser avec d'autres fuites
   
   Avec hash :
   - Attaquant voit uniquement SHA-256(email)
   - Ne peut pas lire les emails
   - Ne peut pas envoyer de phishing
   - Doit bruteforcer chaque hash (coûteux)
   ```

2. **Conformité RGPD** : Email = donnée personnelle identifiable
3. **Defense in depth** : Même si permissions 600, meilleure protection

**Implémentation recommandée** :

```python
# auth_service.py

import hashlib

def _hash_email(self, email: str) -> str:
    """Hash an email for storage (privacy protection).
    
    Uses SHA-256 (not PBKDF2) because:
    - Email is used for lookup, not password verification
    - Fast computation needed for search
    - Email entropy is lower than passwords, but acceptable
    
    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(email.lower().encode()).hexdigest()

def create_user(self, email: str, password: str, role: str = 'user') -> bool:
    email = email.lower().strip()  # Normalisation
    email_hash = self._hash_email(email)
    password_hash, salt = self._hash_password(password)
    
    cursor = self.conn.cursor()
    cursor.execute('''
        INSERT INTO users (email, email_hash, password_hash, salt, role)
        VALUES (?, ?, ?, ?, ?)
    ''', (email, email_hash, password_hash, salt, role))
    # Note: On stocke email ET email_hash
    # - email_hash : pour lookup rapide (indexé)
    # - email : pour affichage (optionnel, peut être chiffré)
```

**Alternative (plus sécurisée)** : Ne stocker QUE le hash

```python
# Ne pas stocker l'email en clair du tout
cursor.execute('''
    INSERT INTO users (email_hash, password_hash, salt, role)
    VALUES (?, ?, ?, ?)
''', (email_hash, password_hash, salt, role))

# Problème : Comment afficher l'utilisateur dans les logs/UI ?
# Solution : Stocker un "display_name" choisi par l'utilisateur
```

**Ma recommandation finale** :

```python
# Compromis optimal : Email chiffré + Hash pour lookup
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash TEXT UNIQUE NOT NULL,        -- SHA-256(email) pour lookup
    email_encrypted TEXT NOT NULL,          -- AES-GCM(email) pour affichage
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    ...
);
```

Mais cela ajoute de la complexité (clé de chiffrement pour les emails). Pour une première version, **stocker email + email_hash** est acceptable.

### B. Lien avec le Workspace (fichiers DB)

#### ❌ Problème : Nommage des fichiers

```text
Actuellement :
passwords_alice.db
passwords_bob.db

Après migration vers email :
passwords_alice@example.com.db  ← INVALIDE (@ dans nom de fichier)
passwords_bob123@gmail.com.db   ← INVALIDE
```

#### ✅ Solutions possibles

**Option 1 : UUID comme nom de fichier** (RECOMMANDÉ)

```python
# users.db
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_uuid TEXT UNIQUE NOT NULL,    -- ← UUID v4
    email TEXT UNIQUE NOT NULL,
    email_hash TEXT UNIQUE NOT NULL,
    ...
);

# Fichiers
passwords_a7f4c8e1-3d9b-4f2a-8e6d-1c5b9f7e2a4d.db
salt_a7f4c8e1-3d9b-4f2a-8e6d-1c5b9f7e2a4d.bin

# Code
import uuid

def create_user(self, email: str, password: str, role: str = 'user') -> bool:
    workspace_uuid = str(uuid.uuid4())
    # ...
    cursor.execute('''
        INSERT INTO users (workspace_uuid, email, email_hash, ...)
        VALUES (?, ?, ?, ...)
    ''', (workspace_uuid, email, email_hash, ...))
```

**Avantages** :

- ✅ Pas de caractères spéciaux
- ✅ Impossible de deviner l'email depuis le nom de fichier
- ✅ Immuable (même si l'user change d'email)
- ✅ Privacy : Pas de corrélation fichier ↔ email

**Inconvénients** :

- ⚠️ Migration nécessaire pour les fichiers existants
- ⚠️ Logs moins lisibles (UUID au lieu de username)

## Option 2 : Hash de l'email comme nom de fichier

```python
# Fichiers
passwords_3a7bd3e2cd8c60604dbd3f00b0d7a7f3.db  # SHA-256(email)[:32]
salt_3a7bd3e2cd8c60604dbd3f00b0d7a7f3.bin

# Code
def _get_workspace_id(self, email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:32]

def on_user_authenticated(self, user_info: dict, master_password: str):
    workspace_id = self._get_workspace_id(user_info['email'])
    db_path = DATA_DIR / f"passwords_{workspace_id}.db"
    salt_path = DATA_DIR / f"salt_{workspace_id}.bin"
```

**Avantages** :

- ✅ Déterministe (même email → même fichier)
- ✅ Pas de colonne workspace_uuid nécessaire
- ✅ Privacy

**Inconvénients** :

- ⚠️ Si 2 utilisateurs ont le même email sur 2 machines → conflit si on fusionne
- ⚠️ Un peu moins flexible qu'UUID

## Option 3 : ID de base de données

```python
# Utiliser l'ID auto-incrémenté
passwords_1.db
passwords_2.db
```

**Avantages** :

- ✅ Simple

**Inconvénients** :

- ❌ Fuite d'information : Facile de savoir combien d'utilisateurs
- ❌ ID peut changer lors de migrations/réimports

### 🎯 Ma recommandation : **Option 1 (UUID)**

```python
# Migration des fichiers existants

def migrate_workspace_files(self):
    """Migrer les fichiers username vers UUID."""
    cursor = self.conn.cursor()
    cursor.execute('SELECT id, username FROM users')
    
    for user_id, username in cursor.fetchall():
        # Générer UUID
        workspace_uuid = str(uuid.uuid4())
        
        # Mettre à jour la DB
        cursor.execute(
            'UPDATE users SET workspace_uuid = ? WHERE id = ?',
            (workspace_uuid, user_id)
        )
        
        # Renommer les fichiers
        old_db = DATA_DIR / f"passwords_{username}.db"
        new_db = DATA_DIR / f"passwords_{workspace_uuid}.db"
        if old_db.exists():
            old_db.rename(new_db)
        
        old_salt = DATA_DIR / f"salt_{username}.bin"
        new_salt = DATA_DIR / f"salt_{workspace_uuid}.bin"
        if old_salt.exists():
            old_salt.rename(new_salt)
    
    self.conn.commit()
    logger.info("Migration des workspaces terminée")
```

---

## 2️⃣ Implémentation 2FA (TOTP)

### A. Choix de stockage du secret TOTP

**Question** : Où stocker `secret_2fa` ?

#### Option 1 : Dans users.db (RECOMMANDÉ)

```sql
CREATE TABLE users (
    ...
    secret_2fa TEXT,  -- Base32-encoded secret TOTP, CHIFFRÉ
    totp_enabled BOOLEAN DEFAULT 0,
    totp_confirmed BOOLEAN DEFAULT 0,
    backup_codes TEXT,  -- JSON array de codes de secours, CHIFFRÉS
    ...
);
```

**Avantages** :

- ✅ Centralisé avec les autres infos d'auth
- ✅ Accessible même avant d'ouvrir le workspace utilisateur
- ✅ Peut être vérifié tôt dans le flow de login

**Inconvénients** :

- ⚠️ Doit être chiffré avec une clé séparée (pas le master password)

#### Option 2 : Dans passwords_{uuid}.db (workspace)

```sql
-- Dans la DB de chaque utilisateur
CREATE TABLE user_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT INTO user_metadata VALUES ('secret_2fa', '...');
```

**Avantages** :

- ✅ Peut être chiffré avec la clé dérivée du master password

**Inconvénients** :

- ❌ Nécessite de dériver la clé AVANT de vérifier le TOTP
- ❌ Chicken-and-egg problem : Comment ouvrir le workspace avant le 2FA ?
- ❌ Complexité : Doit ouvrir temporairement la DB juste pour le 2FA

#### 🎯 Ma recommandation : **Option 1 (users.db)**

**Mais** : Le secret TOTP doit être chiffré

**Problème** : Avec quelle clé le chiffrer ?

### B. Chiffrement du secret TOTP

#### Approche 1 : Clé dérivée du master password (❌ NON RECOMMANDÉ)

```python
# Problème : On n'a pas encore le master password au moment de vérifier le TOTP
secret_2fa = AES_GCM.decrypt(stored_secret, key=derive(master_password))
```

**Faille** : On doit vérifier le TOTP APRÈS avoir validé le password, donc aucune protection 2FA réelle.

#### Approche 2 : Clé système (Application Master Key)

```python
# Générer UNE SEULE clé pour toute l'application
# Stockée dans ~/.local/share/password-manager/.app_key
# Ou dérivée d'un secret fixe

APP_MASTER_KEY = load_or_generate_app_key()

def encrypt_totp_secret(secret):
    return AES_GCM(APP_MASTER_KEY).encrypt(secret)
```

**Avantages** :

- ✅ Peut déchiffrer le secret TOTP sans le master password
- ✅ Permet la vérification 2FA indépendante

**Inconvénients** :

- ⚠️ Si APP_MASTER_KEY est compromise → tous les TOTP sont lisibles
- ⚠️ Moins sécurisé que chiffrement par master password

#### Approche 3 : TOTP secret stocké en clair (❌ DANGEREUX)

```python
# Ne JAMAIS faire ça
secret_2fa = "JBSWY3DPEHPK3PXP"  # En clair dans users.db
```

**Faille** : Si attaquant vole users.db → Peut générer des codes TOTP valides

#### 🎯 Ma recommandation : **Approche 2 (Clé système)**

**Justification** :

- Le secret TOTP est moins critique que le master password
- Le vol de users.db seul ne suffit PAS (besoin de .app_key)
- C'est l'approche utilisée par la plupart des gestionnaires (1Password, Bitwarden)

**Implémentation** :

```python
# src/services/totp_service.py

import pyotp
import secrets
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pathlib import Path

class TOTPService:
    """Gestion TOTP (2FA)."""
    
    def __init__(self, app_key_path: Path):
        """Initialise le service TOTP.
        
        Args:
            app_key_path: Chemin vers la clé applicative (32 bytes)
        """
        if not app_key_path.exists():
            # Générer une clé unique à la première utilisation
            app_key = secrets.token_bytes(32)
            app_key_path.write_bytes(app_key)
            app_key_path.chmod(0o600)
            logger.info("Clé applicative TOTP générée")
        else:
            app_key = app_key_path.read_bytes()
        
        self.cipher = AESGCM(app_key)
    
    def generate_secret(self) -> str:
        """Génère un nouveau secret TOTP.
        
        Returns:
            Secret base32 (ex: "JBSWY3DPEHPK3PXP")
        """
        return pyotp.random_base32()
    
    def encrypt_secret(self, secret: str) -> dict:
        """Chiffre un secret TOTP pour stockage.
        
        Returns:
            dict: {'nonce': '...', 'ciphertext': '...'}
        """
        nonce = secrets.token_bytes(12)
        ciphertext = self.cipher.encrypt(nonce, secret.encode(), None)
        return {
            'nonce': base64.b64encode(nonce).decode(),
            'ciphertext': base64.b64encode(ciphertext).decode()
        }
    
    def decrypt_secret(self, encrypted: dict) -> str:
        """Déchiffre un secret TOTP."""
        nonce = base64.b64decode(encrypted['nonce'])
        ciphertext = base64.b64decode(encrypted['ciphertext'])
        plaintext = self.cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode()
    
    def verify_code(self, secret: str, code: str) -> bool:
        """Vérifie un code TOTP.
        
        Args:
            secret: Secret TOTP (déchiffré)
            code: Code à 6 chiffres saisi par l'utilisateur
            
        Returns:
            True si le code est valide
        """
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)  # ±30 secondes
    
    def get_provisioning_uri(self, secret: str, email: str, issuer: str = "PasswordManager") -> str:
        """Génère l'URI pour QR code.
        
        Args:
            secret: Secret TOTP
            email: Email de l'utilisateur
            issuer: Nom de l'application
            
        Returns:
            URI otpauth://totp/...
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)
    
    def generate_backup_codes(self, count: int = 10) -> list:
        """Génère des codes de secours.
        
        Returns:
            Liste de codes (ex: ["A1B2-C3D4-E5F6", ...])
        """
        codes = []
        for _ in range(count):
            code = secrets.token_hex(6).upper()
            formatted = f"{code[:4]}-{code[4:8]}-{code[8:12]}"
            codes.append(formatted)
        return codes
```

### C. Logique de Login avec 2FA

#### Flow proposé

```text
1. EmailLoginDialog
   ├── User saisit email + password
   ├── AuthService.verify_password(email, password)
   │   ├── Lookup par email_hash
   │   ├── PBKDF2(password, salt, 600k)
   │   └── Compare hash
   │
   ├── Si password INCORRECT :
   │   └── LoginAttemptTracker.record_failed(email_hash)
   │
   └── Si password CORRECT :
       ├── Récupérer user_info (incluant totp_enabled)
       │
       ├── Si totp_enabled == False :
       │   └── on_user_authenticated() directement
       │
       └── Si totp_enabled == True :
           └── TOTP2FADialog(email, master_password)

2. TOTP2FADialog
   ├── User saisit code 6 chiffres
   ├── Récupérer secret_2fa_encrypted de users.db
   ├── TOTPService.decrypt_secret(secret_2fa_encrypted)
   ├── TOTPService.verify_code(secret, code)
   │
   ├── Si code INCORRECT :
   │   ├── Incrémenter compteur tentatives 2FA
   │   └── Si trop de tentatives → Verrouiller compte
   │
   └── Si code CORRECT :
       └── on_user_authenticated(user_info, master_password)

3. on_user_authenticated(user_info, master_password)
   ├── Charger salt_{workspace_uuid}.bin
   ├── CryptoService(master_password, salt)  ← Dérivation clé ICI
   ├── Ouvrir passwords_{workspace_uuid}.db
   └── PasswordService prêt
```

#### ⚠️ CRITIQUE : Ordre des opérations

**Question** : Quand dériver la clé de chiffrement ?

**Réponse** : **SEULEMENT après validation 2FA complète**

**Justification** :

```python
# ❌ MAUVAIS (faille de sécurité)
def on_password_verified(email, master_password):
    # Dériver la clé AVANT le 2FA
    crypto_service = CryptoService(master_password, salt)  # ❌ TROP TÔT
    # Demander le code TOTP
    show_totp_dialog()

# ✅ BON (sécurisé)
def on_password_verified(email, master_password):
    # Stocker temporairement le master_password (en RAM uniquement)
    self.pending_auth = {
        'email': email,
        'master_password': master_password,  # Temporaire
        'timestamp': time.time()
    }
    # Demander le code TOTP
    show_totp_dialog()

def on_totp_verified(code):
    # Récupérer les infos temporaires
    auth = self.pending_auth
    
    # Vérifier timeout (max 2 minutes)
    if time.time() - auth['timestamp'] > 120:
        raise Exception("Session expirée")
    
    # MAINTENANT dériver la clé
    crypto_service = CryptoService(auth['master_password'], salt)
    
    # Effacer le master_password de la RAM
    self.pending_auth = None
    del auth['master_password']
    
    # Continuer l'authentification
    on_user_authenticated(...)
```

**Principe** : Ne JAMAIS accéder aux données avant validation 2FA complète

---

## 3️⃣ Sécurité et Cryptographie

### A. Impact du changement d'email sur le Salt

**Question** : Si l'utilisateur change son email (identifiant), quel impact sur la clé maître ?

**État actuel** :

```python
# Le salt est stocké à 2 endroits :
# 1. users.db → salt (pour vérifier le password)
# 2. salt_{username}.bin → salt (pour dériver la clé de chiffrement)

# Ces 2 salts sont DIFFÉRENTS !
```

**Analyse** :

```python
# Salt 1 : Pour le password hash (dans users.db)
password_hash = PBKDF2(master_password, salt_auth, 600k)
# Objectif : Vérifier que l'utilisateur connait le bon password

# Salt 2 : Pour la clé de chiffrement (dans salt_{username}.bin)
crypto_key = PBKDF2(master_password, salt_crypto, 600k)
# Objectif : Dériver la clé qui chiffre/déchiffre les mots de passe
```

**Impact du changement d'email** :

```text
1. Si on change email → Aucun impact sur les salts
   - salt_auth reste le même dans users.db
   - salt_crypto reste le même dans salt_{workspace_uuid}.bin
   - Les données restent déchiffrables

2. Si on change le master_password → Les 2 salts doivent changer
   - Nouveau salt_auth → Nouveau password_hash
   - Nouveau salt_crypto → Nouvelle clé de chiffrement
   - Nécessite re-chiffrement de TOUTES les données (lourd !)
```

**Conclusion** : ✅ **Pas d'impact** du changement d'email sur la cryptographie

**Problème potentiel** : Si un utilisateur veut changer son master password

```python
def change_master_password(self, email: str, old_password: str, new_password: str):
    """Change le master password ET re-chiffre toutes les données."""
    
    # 1. Vérifier l'ancien password
    if not self.verify_password(email, old_password):
        return False
    
    # 2. Charger TOUTES les données avec l'ancienne clé
    old_crypto = CryptoService(old_password, old_salt)
    entries = load_all_entries()
    decrypted_entries = [old_crypto.decrypt(e) for e in entries]
    
    # 3. Générer un nouveau salt pour la clé crypto
    new_salt_crypto = secrets.token_bytes(32)
    
    # 4. Créer la nouvelle clé de chiffrement
    new_crypto = CryptoService(new_password, new_salt_crypto)
    
    # 5. Re-chiffrer TOUTES les données
    re_encrypted = [new_crypto.encrypt(e) for e in decrypted_entries]
    save_all_entries(re_encrypted)
    
    # 6. Mettre à jour le password hash dans users.db
    new_salt_auth = secrets.token_bytes(32)
    new_password_hash = PBKDF2(new_password, new_salt_auth, 600k)
    UPDATE users SET password_hash = ?, salt = ? WHERE email_hash = ?
    
    # 7. Sauvegarder le nouveau salt_crypto
    salt_{workspace_uuid}.bin.write(new_salt_crypto)
```

**Recommandation** : Documenter clairement que le changement de master password est une opération lourde.

### B. Protection contre Brute Force sans liste d'utilisateurs

**Problème actuel** : LoginAttemptTracker utilise un dictionnaire `Dict[username, LoginAttemptInfo]`

```python
# Actuellement
_attempts: Dict[str, LoginAttemptInfo] = {}
tracker.check_can_attempt("alice")
tracker.record_failed("alice")
```

**Problème après migration** :

```text
Attaquant peut tester des milliers d'emails aléatoires :
- test1@fake.com
- test2@fake.com  
- test3@fake.com
...

Chaque email créerait une nouvelle entrée dans le tracker
→ Pas de verrouillage car jamais 5 échecs pour le MÊME email
```

### Solution 1 : Rate limiting global par IP (RECOMMANDÉ pour app desktop)**

```python
class LoginAttemptTracker:
    """Protection brute force avec rate limiting global."""
    
    def __init__(self):
        self._attempts_by_email: Dict[str, LoginAttemptInfo] = {}
        self._global_attempts: List[float] = []  # Timestamps
        self.GLOBAL_MAX_ATTEMPTS_PER_HOUR = 20
    
    def check_can_attempt_global(self) -> tuple[bool, Optional[int]]:
        """Vérifie le rate limiting global (tous utilisateurs confondus).
        
        Empêche de tester trop d'emails différents en peu de temps.
        """
        current_time = time.time()
        one_hour_ago = current_time - 3600
        
        # Nettoyer les anciennes tentatives
        self._global_attempts = [
            t for t in self._global_attempts if t > one_hour_ago
        ]
        
        if len(self._global_attempts) >= self.GLOBAL_MAX_ATTEMPTS_PER_HOUR:
            return (False, 3600)  # Bloqué pendant 1h
        
        return (True, None)
    
    def record_attempt(self):
        """Enregistre une tentative globale."""
        self._global_attempts.append(time.time())
```

**Usage** :

```python
def on_login_clicked(self):
    email = self.email_entry.get_text()
    
    # Vérifier rate limiting global
    can_attempt, wait_time = tracker.check_can_attempt_global()
    if not can_attempt:
        self.show_error(f"Trop de tentatives. Attendez {wait_time//60} minutes")
        return
    
    # Vérifier rate limiting par email
    can_attempt, wait_time = tracker.check_can_attempt(email_hash)
    if not can_attempt:
        self.show_error(f"Compte temporairement verrouillé ({wait_time}s)")
        return
    
    # Tenter l'authentification
    tracker.record_attempt()  # Global
    if not auth_service.verify_password(email, password):
        tracker.record_failed(email_hash)  # Par email
```

## Solution 2 : Captcha après X échecs** (pour app web, pas pertinent ici)

## Solution 3 : Délai exponentiel global**

```python
# Après 5 échecs globaux → délai de 1 minute
# Après 10 échecs globaux → délai de 5 minutes
# Après 20 échecs globaux → délai de 30 minutes
```

## Solution 4 : Stockage de rate limiting dans users.db**

```sql
-- Ajouter une table de rate limiting
CREATE TABLE login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    email_hash TEXT,
    success BOOLEAN
);

-- Requête pour vérifier
SELECT COUNT(*) FROM login_attempts 
WHERE timestamp > datetime('now', '-1 hour');
```

**Avantages** :

- ✅ Persiste entre redémarrages
- ✅ Peut être analysé pour détecter des attaques

**Inconvénients** :

- ⚠️ Plus lent (requête DB à chaque tentative)

### 🎯 Ma recommandation : **Solution 1 (Rate limiting global en RAM)**

**Justification** :

- C'est une application desktop (pas d'IP, pas de réseau)
- L'attaquant doit avoir accès physique à la machine
- Si accès physique → d'autres vecteurs d'attaque existent déjà
- Keep it simple

**Implémentation** :

```python
class LoginAttemptTracker:
    """Protection brute force améliorée pour email-based auth."""
    
    # Nouvelle config
    GLOBAL_MAX_ATTEMPTS_PER_MINUTE = 5
    GLOBAL_MAX_ATTEMPTS_PER_HOUR = 30
    
    def __init__(self):
        self._attempts_by_email_hash: Dict[str, LoginAttemptInfo] = {}
        self._global_attempts_minute: List[float] = []
        self._global_attempts_hour: List[float] = []
    
    def check_can_attempt(self, email_hash: str) -> tuple[bool, Optional[int]]:
        """Vérification combinée : global + par email."""
        
        # 1. Rate limiting global (minute)
        current_time = time.time()
        self._clean_old_attempts(current_time)
        
        if len(self._global_attempts_minute) >= self.GLOBAL_MAX_ATTEMPTS_PER_MINUTE:
            return (False, 60)
        
        # 2. Rate limiting global (heure)
        if len(self._global_attempts_hour) >= self.GLOBAL_MAX_ATTEMPTS_PER_HOUR:
            return (False, 3600)
        
        # 3. Rate limiting par email (existant)
        can_attempt, wait = self._check_email_attempts(email_hash)
        if not can_attempt:
            return (False, wait)
        
        return (True, None)
    
    def record_attempt(self, email_hash: str, success: bool):
        """Enregistre une tentative."""
        current_time = time.time()
        
        # Global
        self._global_attempts_minute.append(current_time)
        self._global_attempts_hour.append(current_time)
        
        # Par email
        if not success:
            self.record_failed_attempt(email_hash)
        else:
            self.record_successful_attempt(email_hash)
```

---

## 4️⃣ UX & GTK4

### A. Affichage du QR Code

**Contexte** : Lors de l'activation du 2FA, l'utilisateur doit scanner un QR code avec son app d'authentification.

#### Implémentation proposée

```python
# src/ui/dialogs/setup_2fa_dialog.py

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GdkPixbuf

import qrcode
import io

class Setup2FADialog(Adw.Window):
    """Dialogue de configuration du 2FA."""
    
    def __init__(self, parent, totp_service, email: str):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(500, 700)
        self.set_title("Configuration de l'authentification à deux facteurs")
        
        self.totp_service = totp_service
        self.email = email
        self.secret = totp_service.generate_secret()
        
        self._build_ui()
    
    def _build_ui(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        
        # Titre
        title = Gtk.Label(label="🔐 Sécurisez votre compte avec 2FA")
        title.set_css_classes(['title-2'])
        box.append(title)
        
        # Instructions
        instructions = Gtk.Label(
            label="Scannez ce QR code avec votre application d'authentification\\n"
                  "(Google Authenticator, Authy, etc.)",
            wrap=True,
            justify=Gtk.Justification.CENTER
        )
        instructions.set_css_classes(['body'])
        box.append(instructions)
        
        # QR Code
        qr_image = self._generate_qr_code()
        box.append(qr_image)
        
        # Secret en clair (pour saisie manuelle)
        secret_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        secret_label = Gtk.Label(label="Ou saisissez manuellement ce code :", xalign=0)
        secret_label.set_css_classes(['caption'])
        secret_box.append(secret_label)
        
        secret_entry = Gtk.Entry()
        secret_entry.set_text(self.secret)
        secret_entry.set_editable(False)
        secret_box.append(secret_entry)
        
        copy_btn = Gtk.Button(label="📋 Copier")
        copy_btn.connect("clicked", lambda b: self._copy_secret())
        secret_box.append(copy_btn)
        
        box.append(secret_box)
        
        # Vérification
        verify_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        verify_label = Gtk.Label(label="Entrez le code à 6 chiffres affiché :", xalign=0)
        verify_box.append(verify_label)
        
        self.code_entry = Gtk.Entry()
        self.code_entry.set_placeholder_text("000 000")
        self.code_entry.set_max_length(6)
        self.code_entry.connect("activate", lambda e: self.on_verify())
        verify_box.append(self.code_entry)
        
        box.append(verify_box)
        
        # Message d'erreur
        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        box.append(self.error_label)
        
        # Boutons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        
        cancel_btn = Gtk.Button(label="Annuler")
        cancel_btn.connect("clicked", lambda b: self.close())
        button_box.append(cancel_btn)
        
        verify_btn = Gtk.Button(label="✓ Activer le 2FA")
        verify_btn.set_css_classes(['suggested-action'])
        verify_btn.connect("clicked", lambda b: self.on_verify())
        button_box.append(verify_btn)
        
        box.append(button_box)
        
        self.set_content(box)
    
    def _generate_qr_code(self) -> Gtk.Image:
        """Génère le QR code pour le TOTP."""
        uri = self.totp_service.get_provisioning_uri(self.secret, self.email)
        
        # Générer QR code avec qrcode library
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convertir en GdkPixbuf
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        loader = GdkPixbuf.PixbufLoader.new()
        loader.write(buffer.read())
        loader.close()
        pixbuf = loader.get_pixbuf()
        
        gtk_image = Gtk.Image.new_from_pixbuf(pixbuf)
        return gtk_image
    
    def _copy_secret(self):
        """Copie le secret dans le presse-papiers."""
        clipboard = self.get_clipboard()
        clipboard.set(self.secret)
        
        toast = Adw.Toast.new("✓ Secret copié dans le presse-papiers")
        toast.set_timeout(2)
        # (afficher toast si overlay disponible)
    
    def on_verify(self):
        """Vérifie le code saisi."""
        code = self.code_entry.get_text().replace(" ", "")
        
        if len(code) != 6:
            self.show_error("Le code doit contenir 6 chiffres")
            return
        
        if self.totp_service.verify_code(self.secret, code):
            # Code valide ! Enregistrer le 2FA
            self.on_2fa_confirmed(self.secret)
            self.close()
        else:
            self.show_error("❌ Code incorrect. Vérifiez l'heure de votre appareil.")
    
    def show_error(self, message: str):
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
    
    def on_2fa_confirmed(self, secret: str):
        """Callback quand le 2FA est confirmé."""
        # À implémenter : Sauvegarder secret dans users.db
        pass
```

**Sécurité du QR code** :

1. ✅ Le QR code est affiché **uniquement pendant la configuration initiale**
2. ✅ Le dialogue est **modal** (bloque l'accès au reste de l'app)
3. ✅ Le secret **n'est jamais loggé**
4. ✅ Le QR disparaît après fermeture du dialogue
5. ⚠️ **ATTENTION** : Ne pas faire de screenshot automatique lors des tests

**Dépendances à ajouter** :

```text
# requirements.txt
pyotp>=2.8.0
qrcode[pil]>=7.4.0
```

### B. Nouveau flow de login avec email

```python
# src/ui/dialogs/email_login_dialog.py

class EmailLoginDialog(Adw.Window):
    """Dialogue de connexion par email (remplace UserSelectionDialog + LoginDialog)."""
    
    def _build_ui(self):
        # ...
        
        # Email
        self.email_entry = Gtk.Entry()
        self.email_entry.set_placeholder_text("votre.email@example.com")
        self.email_entry.set_input_purpose(Gtk.InputPurpose.EMAIL)
        
        # Password
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        
        # Remember me (optionnel)
        self.remember_check = Gtk.CheckButton(label="Se souvenir de mon email")
        
        # Bouton login
        login_btn = Gtk.Button(label="Se connecter")
        login_btn.set_css_classes(['suggested-action'])
        login_btn.connect("clicked", self.on_login)
    
    def on_login(self, button):
        email = self.email_entry.get_text().strip()
        password = self.password_entry.get_text()
        
        # Validation basique
        if not email or '@' not in email:
            self.show_error("Email invalide")
            return
        
        if not password:
            self.show_error("Mot de passe requis")
            return
        
        # Rate limiting
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        can_attempt, wait = tracker.check_can_attempt(email_hash)
        if not can_attempt:
            self.show_error(f"Trop de tentatives. Attendez {wait}s")
            return
        
        # Authentification
        user_info = self.auth_service.authenticate(email, password)
        
        if not user_info:
            # Échec
            tracker.record_attempt(email_hash, success=False)
            self.show_error("Email ou mot de passe incorrect")
            return
        
        tracker.record_attempt(email_hash, success=True)
        
        # Vérifier 2FA
        if user_info.get('totp_enabled'):
            # Ouvrir dialogue 2FA
            TOTP2FADialog(self, user_info, password, self.callback).present()
            self.close()
        else:
            # Connexion directe
            self.callback(user_info, password)
            self.close()
```

---

## 📊 Évaluation des Risques de Régression

### Matrice des risques

| Aspect | Risque Avant | Risque Après | Mitigation |
| -------- | -------------- | -------------- | ------------ |
| **Vol de users.db** | 🟢 Faible (usernames exposés) | 🟢 Faible (emails hashés) | ✅ Hash SHA-256 |
| **Brute force** | 🟢 Faible (rate limit par user) | 🟡 Moyen (email énumération) | ✅ Rate limit global |
| **Bypass 2FA** | N/A | 🔴 ÉLEVÉ si mal implémenté | ✅ Vérif avant clé crypto |
| **Perte de TOTP** | N/A | 🟡 Moyen (lockout permanent) | ✅ Backup codes |
| **Migration données** | N/A | 🟡 Moyen (rename fichiers) | ✅ Script de migration testé |
| **Complexité code** | 🟢 Faible | 🟡 Moyenne (+2000 LOC) | ✅ Tests unitaires complets |

### Points critiques de sécurité

#### 🔴 CRITIQUE : Ordre d'authentification

```python
# ❌ FAILLE : Dériver la clé avant 2FA
def on_password_ok(user, password):
    crypto = CryptoService(password, salt)  # ← TROP TÔT
    verify_totp()

# ✅ CORRECT : 2FA d'abord, clé ensuite
def on_password_ok(user, password):
    self.pending_auth = (user, password)
    verify_totp()

def on_totp_ok():
    user, password = self.pending_auth
    crypto = CryptoService(password, salt)  # ← BON MOMENT
```

#### 🟡 MOYEN : Stockage du secret TOTP

```python
# ✅ CORRECT : Secret TOTP chiffré
secret_encrypted = TOTPService.encrypt_secret(secret)
INSERT INTO users (..., secret_2fa) VALUES (..., json.dumps(secret_encrypted))

# ❌ FAILLE : Secret en clair
INSERT INTO users (..., secret_2fa) VALUES (..., secret)  # ← DANGEREUX
```

#### 🟡 MOYEN : Gestion des codes de secours

```python
# Les backup codes doivent être :
# 1. Hashés (pas en clair)
# 2. Usage unique (marqués comme utilisés)
# 3. Affichés UNE SEULE FOIS lors de la config

backup_codes = totp_service.generate_backup_codes()
backup_codes_hashed = [hashlib.sha256(c.encode()).hexdigest() for c in backup_codes]

# Afficher à l'utilisateur UNE FOIS
show_backup_codes_dialog(backup_codes)  # Clair

# Stocker hashés
INSERT INTO users (..., backup_codes) VALUES (..., json.dumps(backup_codes_hashed))
```

---

## 🎯 Recommandations Finales

### ✅ Faisabilité globale : OUI

La migration est techniquement faisable et peut **améliorer significativement la sécurité** si bien implémentée.

### 📋 Checklist d'implémentation

#### Phase 1 : Préparation (2h)

- [ ] Ajouter dépendances : `pyotp`, `qrcode`
- [ ] Créer `totp_service.py`
- [ ] Créer migration SQL pour users.db
- [ ] Implémenter `workspace_uuid` et migration de fichiers
- [ ] Tests unitaires pour TOTPService

#### Phase 2 : Backend (6h)

- [ ] Modifier `AuthService` :
  - [ ] `email` + `email_hash` au lieu de `username`
  - [ ] Méthodes `authenticate_by_email()`
  - [ ] Gestion `secret_2fa` chiffré
- [ ] Modifier `LoginAttemptTracker` :
  - [ ] Rate limiting global
  - [ ] Utiliser `email_hash` au lieu de `username`
- [ ] Implémenter `change_email()`
- [ ] Tests d'intégration complets

#### Phase 3 : UI (4h)

- [ ] Créer `EmailLoginDialog` (remplace UserSelectionDialog)
- [ ] Créer `Setup2FADialog` avec QR code
- [ ] Créer `TOTP2FADialog` pour vérification
- [ ] Modifier `CreateUserDialog` pour saisie email
- [ ] Backup codes dialog

#### Phase 4 : Migration (2h)

- [ ] Script de migration users.db (username → email)
- [ ] Conversion des fichiers (passwords_username → passwords_uuid)
- [ ] Tests de migration avec données réelles
- [ ] Backup avant migration

#### Phase 5 : Tests et doc (3h)

- [ ] Tests unitaires (>90% couverture)
- [ ] Tests d'intégration end-to-end
- [ ] Tests de sécurité (tentatives brute force, bypass 2FA)
- [ ] Documentation utilisateur
- [ ] Guide de migration

### ⚠️ Risques à surveiller

1. **Migration de données** : ✅ Prévoir un backup automatique
2. **Ordre d'authentification** : ✅ Tests rigoureux pour éviter bypass 2FA
3. **Gestion des erreurs** : ✅ Que se passe-t-il si le user perd son TOTP ?
4. **Backward compatibility** : ❌ Non, nécessite migration complète

### 🚀 Prochaines étapes suggérées

1. **Créer une branche git dédiée** : `feature/email-auth-2fa`
2. **Commencer par les tests** : TDD pour le TOTPService
3. **Implémenter le backend d'abord** : AuthService + Migration
4. **Puis l'UI** : Dialogs et intégration
5. **Tests de sécurité** : Simulations d'attaques

### 📧 Questions ouvertes

1. **Doit-on permettre de désactiver le 2FA** ? (recommandation : OUI, mais avec confirmation par email)
2. **Email de récupération** ? (pour reset password/2FA)
3. **Historique des connexions** ? (logs avec IP/timestamp)
4. **Notification par email** lors de nouvelles connexions ?

---

## 📚 Références Techniques

### Librairies nécessaires

```python
# pyproject.toml
dependencies = [
    "PyGObject>=3.42.0",
    "cryptography>=41.0.0",
    "validators>=0.20.0",
    "pyotp>=2.8.0",        # ← Nouveau
    "qrcode[pil]>=7.4.0",  # ← Nouveau
]
```

### Standards appliqués

- **TOTP** : RFC 6238 (Time-Based One-Time Password)
- **Email hashing** : SHA-256 (rapide, suffisant pour lookup)
- **Secret TOTP** : 160 bits (base32) = standard Google Authenticator
- **Rate limiting** : OWASP recommandations (max 5/min, 30/heure)

### Exemples de code

Voir fichiers proposés :

- `src/services/totp_service.py` (complet ci-dessus)
- `src/ui/dialogs/setup_2fa_dialog.py` (complet ci-dessus)
- `src/ui/dialogs/email_login_dialog.py` (esquisse ci-dessus)

---

## ✅ Conclusion

**Verdict final** : Cette migration est **techniquement solide et recommandée**.

**Avantages** :

- ✅ Meilleure sécurité (2FA obligatoire)
- ✅ Plus standard (email au lieu de username)
- ✅ Privacy améliorée (hash d'email, UUID pour fichiers)
- ✅ Prépare pour des features futures (reset password par email, etc.)

**Points d'attention** :

- ⚠️ Complexité accrue (+25% de code)
- ⚠️ Migration nécessaire (breaking change)
- ⚠️ Support utilisateur (perte TOTP = problème majeur)
- ⚠️ Tests exhaustifs requis (sécurité critique)

**Estimation finale** :

- **Temps de développement** : 15-20 heures
- **Temps de tests** : 5-8 heures
- **Complexité** : Moyenne-Haute
- **ROI sécurité** : ✅ Excellent

**Go / No-Go** : ✅ **GO** avec implémentation progressive et tests rigoureux.

---

**Document généré le** : 2 mars 2026  
**Prêt pour revue et implémentation**
