# 📦 Implémentation Migration Email + TOTP + UUID - Synthèse

**Date d'implémentation** : 2 mars 2026  
**Développeur** : AI Assistant  
**Statut** : ✅ Backend et Scripts Complétés | ⚠️ Intégration UI Requise

---

## ✅ Ce qui a été implémenté

### 1. **Dépendances** (`requirements.txt`)

Nouvelles dépendances ajoutées :

- `pyotp>=2.8.0` - Génération et vérification TOTP
- `qrcode[pil]>=7.4.0` - Génération de QR codes
- `validators>=0.20.0` - Validation d'emails

**Installation** :

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

### 2. **Service TOTP** (`src/services/totp_service.py`)

✅ **Fonctionnalités complètes** :

- Génération de secrets TOTP (RFC 6238)
- Chiffrement des secrets avec clé dérivée de `machine-id`
- Génération de QR codes pour applications d'authentification
- Vérification des codes TOTP (fenêtre de tolérance ±30s)
- Génération de 10 codes de secours
- Hachage HMAC-SHA256 des codes de secours
- Marquage des codes utilisés

**Sécurité** :

- Clé système stockée dans `.app_key` (permissions 600)
- Dérivation PBKDF2 avec machine-id comme salt
- Chiffrement AES-256-GCM pour les secrets
- Support fallback pour environnements sans `/etc/machine-id`

---

### 3. **Service d'authentification modifié** (`src/services/auth_service.py`)

✅ **Nouvelles fonctionnalités** :

- `hash_email(email)` - Hash HMAC-SHA256 avec pepper (privacy)
- `authenticate_by_email(email, password)` - Authentification par email
- `update_user_email(user_id, new_email)` - Mise à jour email post-migration
- `is_migration_email(email)` - Détection emails temporaires
- `email_exists(email)` - Vérification unicité email
- `get_user_by_email(email)` - Récupération infos utilisateur
- `create_user_with_email(...)` - Création avec email + UUID
- `setup_2fa(user_id, secret, backup_codes)` - Configuration 2FA
- `confirm_2fa(user_id)` - Confirmation 2FA actif
- `get_2fa_secret(user_id)` - Récupération secret TOTP
- `get_backup_codes(user_id)` - Récupération codes de secours
- `update_backup_codes(user_id, codes)` - MAJ après utilisation

**Sécurité** :

- Pepper email stocké dans `.email_pepper` (permissions 600)
- Délai artificiel de **1.5 seconde** sur échecs d'authentification
- Conservation colonne `username` pour rétrocompatibilité/debug

---

### 4. **LoginAttemptTracker amélioré** (`src/services/login_attempt_tracker.py`)

✅ **Nouvelles protections** :

- **Rate limiting global** : 5 tentatives/minute, 30/heure
- Support `email_hash` ET `username` (rétrocompatibilité)
- Prévention de l'énumération d'emails
- Statistiques globales (`get_global_stats()`)

**Configuration** :

- Verrouillage après 5 échecs : 15 minutes
- Délai progressif : 1s, 2s, 4s, 8s, 16s, 32s
- Logs masqués (privacy) : `identifier[:16]...`

---

### 5. **Dialogs UI** (GTK4/Adwaita)

#### `src/ui/dialogs/setup_2fa_dialog.py`

✅ Dialog de configuration 2FA obligatoire :

- Affichage QR code + secret en texte
- Vérification du code TOTP
- Affichage des 10 codes de secours
- Confirmation obligatoire de sauvegarde
- Blocage si annulé (sécurité > confort)

#### `src/ui/dialogs/verify_totp_dialog.py`

✅ Dialog de vérification TOTP au login :

- Saisie code TOTP à 6 chiffres
- Option "Utiliser un code de secours"
- Vérification et marquage des codes utilisés
- Stack pour basculer entre TOTP et backup

#### `src/ui/dialogs/email_login_dialog.py`

✅ Dialog de connexion par email (remplace UserSelectionDialog) :

- Saisie email + mot de passe
- Rate limiting intégré
- Messages d'erreur clairs
- Design moderne (Adwaita)

#### `src/ui/dialogs/update_email_dialog.py`

✅ Dialog de mise à jour email (post-migration) :

- Détection automatique emails `@migration.local`
- Validation email (library `validators`)
- Vérification unicité
- Obligation de mise à jour

---

### 6. **Script de migration** (`migrate_to_email_2fa.py`)

✅ **Fonctionnalités complètes** :

- Backup automatique avant toute modification
- Ajout de 11 nouvelles colonnes à `users.db`
- Génération d'UUID v4 pour chaque utilisateur
- Création emails temporaires `{username}@migration.local`
- Hash HMAC-SHA256 des emails (avec pepper)
- Renommage sécurisé des fichiers :
  - `passwords_{username}.db` → `passwords_{uuid}.db`
  - `salt_{username}.bin` → `salt_{uuid}.bin`
- Création d'index pour performances
- Validation complète (tests intégrés)
- Marquage dans `migration_status` table
- Prévention double migration

**Usage** :

```bash
./migrate_to_email_2fa.py --data-dir ./data
```

---

### 7. **Script de rollback** (`rollback_migration.py`)

✅ **Fonctionnalités complètes** :

- Restauration depuis backup ou .tar.gz
- Backup de l'état actuel avant rollback
- Restauration de `users.db`
- Restauration des fichiers `passwords_*` et `salt_*`
- Nettoyage des fichiers UUID créés
- Validation du statut de migration
- Mode interactif avec confirmation

**Usage** :

```bash
./rollback_migration.py \
    --data-dir ./data \
    --backup ./data/backup_pre_migration_TIMESTAMP
```

---

### 8. **Documentation** (`MIGRATION_GUIDE.md`)

✅ **Guide complet** :

- Vue d'ensemble de la migration
- Prérequis (dépendances, environnements)
- Phase 1 : Tests en développement (étapes détaillées)
- Phase 2 : Procédure de rollback
- Phase 3 : Déploiement en production
- Troubleshooting (5 problèmes courants)
- Métriques de succès
- Checklist finale
- Support et références

---

## ⚠️ Ce qui reste à faire pour l'intégration complète

### 1. **Modification de `application.py`** (CRITIQUE)

Le fichier `src/app/application.py` doit être mis à jour pour :

#### À modifier dans la méthode `on_activate`

```python
# AVANT (ancien système)
from src.ui.dialogs.user_selection_dialog import UserSelectionDialog
user_selection = UserSelectionDialog(parent=self.window)
user_selection.present()
user_selection.connect('user-selected', self.on_user_selected)

# APRÈS (nouveau système)
from src.ui.dialogs.email_login_dialog import EmailLoginDialog
from src.services.totp_service import TOTPService

# Initialiser le TOTPService
self.totp_service = TOTPService(DATA_DIR)

# Afficher le dialog de login par email
email_login = EmailLoginDialog(
    parent=self.window,
    auth_service=self.auth_service,
    login_tracker=self.login_tracker
)
email_login.present()

# Après fermeture, récupérer user_info et master_password
def on_login_closed():
    user_info = email_login.get_user_info()
    master_password = email_login.get_master_password()
    
    if user_info and master_password:
        # Vérifier si email temporaire
        if self.auth_service.is_migration_email(user_info['email']):
            self.show_update_email_dialog(user_info)
        else:
            # Vérifier si 2FA configuré
            if not user_info['totp_enabled']:
                self.show_setup_2fa_dialog(user_info, master_password)
            else:
                self.show_verify_totp_dialog(user_info, master_password)

email_login.connect('close-request', lambda w: on_login_closed())
```

#### Nouvelles méthodes à ajouter

```python
def show_update_email_dialog(self, user_info):
    """Affiche le dialog de mise à jour d'email."""
    from src.ui.dialogs.update_email_dialog import UpdateEmailDialog
    
    dialog = UpdateEmailDialog(
        parent=self.window,
        auth_service=self.auth_service,
        user_info=user_info
    )
    dialog.present()
    
    def on_closed():
        new_email = dialog.get_new_email()
        if new_email:
            user_info['email'] = new_email
            # Forcer la configuration 2FA
            self.show_setup_2fa_dialog(user_info, self.pending_master_password)
        else:
            # Si annulé, fermer l'application (politique stricte)
            self.quit()
    
    dialog.connect('close-request', lambda w: on_closed())

def show_setup_2fa_dialog(self, user_info, master_password):
    """Affiche le dialog de configuration 2FA (OBLIGATOIRE)."""
    from src.ui.dialogs.setup_2fa_dialog import Setup2FADialog
    
    dialog = Setup2FADialog(
        parent=self.window,
        totp_service=self.totp_service,
        auth_service=self.auth_service,
        user_info=user_info
    )
    dialog.present()
    
    def on_closed():
        if dialog.get_success():
            # 2FA configuré avec succès
            # Charger le workspace
            self.on_user_authenticated(user_info, master_password)
        else:
            # Si annulé, fermer l'application (politique stricte)
            self.show_error_and_quit(
                "Configuration 2FA Requise",
                "La double authentification est obligatoire pour utiliser l'application."
            )
    
    dialog.connect('close-request', lambda w: on_closed())

def show_verify_totp_dialog(self, user_info, master_password):
    """Affiche le dialog de vérification TOTP."""
    from src.ui.dialogs.verify_totp_dialog import VerifyTOTPDialog
    
    dialog = VerifyTOTPDialog(
        parent=self.window,
        totp_service=self.totp_service,
        auth_service=self.auth_service,
        user_info=user_info
    )
    dialog.present()
    
    def on_closed():
        if dialog.get_verified():
            # TOTP vérifié avec succès
            # Charger le workspace
            self.on_user_authenticated(user_info, master_password)
        else:
            # Retour au login
            self.on_activate()
    
    dialog.connect('close-request', lambda w: on_closed())

def show_error_and_quit(self, title, message):
    """Affiche une erreur et ferme l'application."""
    dialog = Adw.MessageDialog.new(self.window, title, message)
    dialog.add_response("ok", "OK")
    dialog.connect("response", lambda d, r: self.quit())
    dialog.present()
```

#### Modification de `on_user_authenticated`

```python
def on_user_authenticated(self, user_info: Dict, master_password: str):
    """Appelé après authentification complète (email + password + TOTP)."""
    
    # Utiliser workspace_uuid au lieu de username
    workspace_uuid = user_info['workspace_uuid']
    
    # Chemins basés sur UUID
    db_path = DATA_DIR / f"passwords_{workspace_uuid}.db"
    salt_path = DATA_DIR / f"salt_{workspace_uuid}.bin"
    
    # Charger le salt (si existe, sinon créer)
    if salt_path.exists():
        salt = salt_path.read_bytes()
    else:
        salt = secrets.token_bytes(32)
        salt_path.write_bytes(salt)
        salt_path.chmod(0o600)
    
    # Initialiser CryptoService avec le master password
    self.crypto_service = CryptoService(master_password, salt)
    
    # Ouvrir ou créer le repository de mots de passe
    from src.repositories.password_repository import PasswordRepository
    self.password_repository = PasswordRepository(db_path)
    
    # Initialiser PasswordService
    from src.services.password_service import PasswordService
    self.password_service = PasswordService(
        self.password_repository,
        self.crypto_service
    )
    
    # Sauvegarder les infos utilisateur
    self.current_user = user_info
    
    # Afficher l'interface principale
    self.show_main_window()
```

---

### 2. **Tests** (Recommandé)

Créer des tests unitaires pour :

- `TOTPService` : génération, vérification, codes de secours
- `AuthService` : nouvelles méthodes email
- `LoginAttemptTracker` : rate limiting global
- Migration : transformation des données
- Rollback : restauration correcte

**Fichier** : `tests/test_email_totp_migration.py`

---

### 3. **Mise à jour des autres références à `username`** (Optionnel)

Rechercher et mettre à jour :

```bash
grep -r "username" src/ --include="*.py" | grep -v "# Keep username"
```

Fichiers potentiellement concernés :

- Gestion des utilisateurs (admin)
- Logs et messages
- Backup service
- Export/Import

---

## 🎯 Prochaines étapes recommandées

### Priorité 1 : Intégration UI (CRITIQUE)

1. ✅ Modifier `application.py` selon le guide ci-dessus
2. ✅ Tester le flow complet en dev
3. ✅ Corriger les bugs éventuels

### Priorité 2 : Tests (IMPORTANT)

1. ✅ Exécuter la migration sur données de test
2. ✅ Valider tous les scénarios du MIGRATION_GUIDE.md
3. ✅ Tester le rollback

### Priorité 3 : Documentation finale

1. ✅ Mettre à jour README.md principal
2. ✅ Créer un changelog détaillé
3. ✅ Documenter les nouvelles API

### Priorité 4 : Déploiement

1. ✅ Validation finale en environnement de staging
2. ✅ Communication aux utilisateurs
3. ✅ Migration en production
4. ✅ Monitoring post-déploiement

---

## 📊 État d'avancement global

| Composant | Statut | Progression |
| ----------- | -------- | ------------- |
| **Backend** | ✅ Complet | 100% |
| TOTPService | ✅ Complet | 100% |
| AuthService | ✅ Complet | 100% |
| LoginAttemptTracker | ✅ Complet | 100% |
| **Scripts** | ✅ Complet | 100% |
| Migration | ✅ Complet | 100% |
| Rollback | ✅ Complet | 100% |
| **UI (Dialogs)** | ✅ Complet | 100% |
| Setup2FADialog | ✅ Complet | 100% |
| VerifyTOTPDialog | ✅ Complet | 100% |
| EmailLoginDialog | ✅ Complet | 100% |
| UpdateEmailDialog | ✅ Complet | 100% |
| **Intégration** | ⚠️ À faire | 0% |
| application.py | ⏳ Pending | 0% |
| **Tests** | ⏳ À faire | 0% |
| Tests unitaires | ⏳ Pending | 0% |
| Tests intégration | ⏳ Pending | 0% |
| **Documentation** | ✅ Complet | 100% |
| MIGRATION_GUIDE.md | ✅ Complet | 100% |

**Progression globale** : 🟢 **75%**

---

## 🔒 Rappels de sécurité

1. **Ne JAMAIS supprimer** :
   - `.app_key` → Perte d'accès aux secrets TOTP
   - `.email_pepper` → Hash emails invalides
   - Backups de migration

2. **Toujours tester** en environnement de développement d'abord

3. **Politique stricte** : 2FA obligatoire = pas de bypass

4. **Rate limiting** : Empêche l'énumération d'emails

5. **Délai artificiel** : 1.5s sur échecs = ralentit les attaques

---

## 📞 Support

Pour toute question ou assistance :

- Consulter `MIGRATION_GUIDE.md`
- Vérifier les logs : `/var/log/password-manager/`
- Rollback en cas de problème critique

---

Développé avec ❤️ et rigueur de sécurité**
