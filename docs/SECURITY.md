# 🔒 Sécurité et Contrôle d'Accès

## 📋 Restrictions implémentées

### ✅ Création de comptes (19 novembre 2025)

**Problème initial** : N'importe qui pouvait créer un compte depuis l'écran de login.

**Solution implémentée** :
- ❌ **Supprimé** : Bouton "Créer un nouveau compte" de l'écran de sélection utilisateur
- ✅ **Ajouté** : Note informative "Pour créer un nouveau compte, connectez-vous en tant qu'administrateur"
- ✅ **Ajouté** : Bouton "➕ Créer un nouvel utilisateur" dans le dialogue "Gestion des utilisateurs" (admin uniquement)
- ✅ **Modifié** : CreateUserDialog permet maintenant de choisir le rôle (Utilisateur/Administrateur)

**Fichiers modifiés** :
- `password_manager.py` (lignes 1350-1610)
  - `UserSelectionDialog` : Suppression de `on_new_user_clicked()`
  - `CreateUserDialog` : Ajout du champ de sélection de rôle
  - `ManageUsersDialog` : Ajout du bouton de création

**Nouveau comportement** :
```
Écran de login
└─> Liste des utilisateurs existants
    └─> Clic sur utilisateur → Demande mot de passe
    
Menu admin (une fois connecté)
└─> Gérer les utilisateurs
    └─> ➕ Créer un nouvel utilisateur
        └─> Formulaire avec :
            • Nom d'utilisateur
            • Mot de passe
            • Confirmation
            • Rôle (User/Admin) ← NOUVEAU
```

## 🔐 Fonctionnalités de sécurité

### Changement de mot de passe personnel

**Accessible depuis** : Menu utilisateur (☰) → "Changer mon mot de passe"

**Flux** :
1. Saisir le mot de passe actuel (vérification obligatoire)
2. Saisir le nouveau mot de passe (min. 8 caractères)
3. Confirmer le nouveau mot de passe
4. Le mot de passe est changé avec un nouveau salt

**Implémentation** :
- `ChangeOwnPasswordDialog` (password_manager.py, ligne ~1755)
- `UserManager.verify_user()` : Vérifie le mot de passe actuel
- `UserManager.change_user_password()` : Change avec vérification

### Réinitialisation de mot de passe (admin uniquement)

**Accessible depuis** : Gestion des utilisateurs → "Réinitialiser MdP"

**Flux** :
1. Admin sélectionne un utilisateur (pas soi-même)
2. Saisit un nouveau mot de passe
3. Le mot de passe est réinitialisé sans vérifier l'ancien

**Implémentation** :
- `ResetPasswordDialog` (password_manager.py, ligne ~1920)
- `UserManager.reset_user_password()` : Réinitialise sans vérification

## 👥 Rôles et permissions

### Rôle : `user` (Utilisateur standard)
**Peut** :
- ✅ Se connecter avec son compte
- ✅ Gérer ses propres mots de passe (CRUD)
- ✅ Changer son propre mot de passe maître
- ✅ Générer des mots de passe
- ✅ Se déconnecter / Changer de compte

**Ne peut pas** :
- ❌ Créer de nouveaux utilisateurs
- ❌ Voir les autres utilisateurs
- ❌ Réinitialiser les mots de passe d'autres utilisateurs
- ❌ Supprimer des comptes

### Rôle : `admin` (Administrateur)
**Peut** (en plus des droits utilisateur) :
- ✅ Créer de nouveaux utilisateurs (avec choix du rôle)
- ✅ Voir tous les utilisateurs
- ✅ Réinitialiser les mots de passe des autres utilisateurs
- ✅ Supprimer des comptes utilisateurs (pas le sien)
- ✅ Accéder au menu "Gérer les utilisateurs"

## 🔨 Architecture de sécurité

### Hachage des mots de passe
```python
Algorithm: PBKDF2HMAC
Hash: SHA256
Salt: 32 bytes (random per user)
Iterations: 600 000
Key length: 32 bytes
Encoding: Base64
```

### Séparation des données
```
~/.local/share/passwordmanager/
├── users.db              # Base centralisée des utilisateurs
├── passwords_admin.db    # Workspace de 'admin'
├── passwords_alice.db    # Workspace de 'alice'
├── passwords_bob.db      # Workspace de 'bob'
├── salt_admin.bin        # Salt de chiffrement de 'admin'
├── salt_alice.bin        # Salt de chiffrement de 'alice'
└── salt_bob.bin          # Salt de chiffrement de 'bob'
```

### Chiffrement des mots de passe stockés
```python
Algorithm: AES-256-GCM
Key derivation: PBKDF2HMAC du mot de passe maître
Nonce: 12 bytes (random per entry)
Tag: 16 bytes (authentication)
```

## 📚 Modules de sécurité

### Nouveaux modules (src/)
```
src/
├── services/
│   ├── auth_service.py          # Service d'authentification
│   │   ├── create_user()        # Création avec hachage
│   │   ├── authenticate()       # Vérification credentials
│   │   ├── verify_user()        # Vérification mot de passe
│   │   ├── change_user_password()  # Changement sécurisé
│   │   └── reset_user_password()   # Réinit admin
│   │
│   ├── crypto_service.py        # Chiffrement AES-256-GCM
│   └── password_generator.py    # Génération sécurisée
│
└── ui/
    └── dialogs/
        ├── user_selection_dialog.py  # Sélection utilisateur
        └── login_dialog.py            # Authentification
```

### Classes principales (password_manager.py)
```python
UserManager                    # Gestion utilisateurs + auth
├── _hash_password()          # PBKDF2HMAC hashing
├── create_user()             # Création avec validation
├── authenticate()            # Login avec MàJ last_login
├── verify_user()             # Vérif sans auth
├── change_user_password()    # Changement sécurisé
├── reset_user_password()     # Réinit admin
├── delete_user()             # Suppression
└── get_all_users()           # Liste (admin)

ChangeOwnPasswordDialog       # UI changement mot de passe
ResetPasswordDialog           # UI réinit admin
CreateUserDialog              # UI création (admin)
ManageUsersDialog             # UI gestion (admin)
```

## 🧪 Tests de sécurité

### Tests manuels recommandés

#### 1. Restriction de création de compte
```bash
./run-dev.sh

# Vérifier :
# - Pas de bouton "Créer un nouveau compte" sur l'écran de login
# - Message informatif présent
# - Bouton visible uniquement dans Gestion des utilisateurs (admin)
```

#### 2. Changement de mot de passe
```bash
# Test utilisateur standard
1. Se connecter (non-admin)
2. Menu → Changer mon mot de passe
3. Tester avec mauvais mot de passe actuel (doit échouer)
4. Tester avec bon mot de passe actuel (doit réussir)
5. Se déconnecter et se reconnecter avec nouveau mot de passe
```

#### 3. Gestion admin
```bash
# Test admin
1. Se connecter avec admin/admin
2. Menu → Changer mon mot de passe → Changer en "AdminSecure123!"
3. Menu → Gérer les utilisateurs
4. Créer un utilisateur standard
5. Créer un utilisateur admin
6. Réinitialiser le mot de passe d'un utilisateur
7. Tenter de se supprimer soi-même (doit échouer)
8. Supprimer un autre utilisateur
```

#### 4. Isolation des workspaces
```bash
# Test isolation
1. Se connecter comme user1, créer des mots de passe
2. Se déconnecter
3. Se connecter comme user2
4. Vérifier que les mots de passe de user1 ne sont pas visibles
```

## 📝 Bonnes pratiques

### Pour les développeurs

1. **Toujours vérifier les permissions** avant les opérations sensibles
   ```python
   if user['role'] != 'admin':
       return False, "Permission refusée"
   ```

2. **Ne jamais stocker de mots de passe en clair**
   ```python
   # ❌ Mauvais
   db.store(username, password)
   
   # ✅ Bon
   password_hash, salt = self._hash_password(password)
   db.store(username, password_hash, salt)
   ```

3. **Toujours utiliser des salts uniques**
   ```python
   salt = secrets.token_bytes(32)  # Un salt par utilisateur
   ```

4. **Vérifier l'ancien mot de passe lors d'un changement**
   ```python
   if not self.verify_user(username, old_password):
       return False
   ```

### Pour les utilisateurs

1. **Changer le mot de passe admin par défaut** dès la première connexion
2. **Utiliser des mots de passe forts** (min. 8 caractères, varié)
3. **Ne pas partager son mot de passe maître**
4. **Les admins** : Créer des comptes utilisateur plutôt que donner le rôle admin

## 🔄 Prochaines améliorations de sécurité

- [ ] Authentification à deux facteurs (2FA)
- [ ] Historique des connexions
- [ ] Verrouillage après X tentatives échouées
- [ ] Expiration des sessions
- [ ] Audit log des actions admin
- [ ] Sauvegarde chiffrée automatique
- [ ] Import/Export chiffré

---

**Dernière mise à jour** : 19 novembre 2025
**Version** : 2.0 (Multi-utilisateurs avec restrictions)
