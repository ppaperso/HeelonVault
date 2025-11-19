# 👥 Guide du système multi-utilisateurs

Ce guide détaille le fonctionnement du système multi-utilisateurs avec workspaces séparés.

## 🎯 Vue d'ensemble

Le gestionnaire de mots de passe supporte maintenant plusieurs utilisateurs avec :
- **Workspaces totalement séparés** : Chaque utilisateur a sa propre base de données
- **Authentification individuelle** : Mot de passe maître unique par utilisateur
- **Gestion des rôles** : Administrateur et Utilisateur standard
- **Interface personnalisée** : Affichage "Bonjour [nom_utilisateur]"

## 🔐 Architecture de sécurité

### Séparation des données

```
~/.local/share/passwordmanager/
├── users.db                    # Base des utilisateurs (hash des mots de passe)
├── passwords_alice.db          # Workspace d'Alice (chiffré)
├── salt_alice.bin             # Salt d'Alice
├── passwords_bob.db            # Workspace de Bob (chiffré)
├── salt_bob.bin               # Salt de Bob
├── passwords_admin.db          # Workspace de l'admin (chiffré)
└── salt_admin.bin             # Salt de l'admin
```

### Niveaux de sécurité

1. **Authentification** : Hash PBKDF2 avec 600k itérations
2. **Chiffrement** : AES-256-GCM pour chaque mot de passe stocké
3. **Isolation** : Base de données SQLite séparée par utilisateur
4. **Salt individuel** : Chaque utilisateur a son propre salt cryptographique

## 👤 Types d'utilisateurs

### Utilisateur standard (User)

**Permissions :**
- ✅ Créer, modifier, supprimer ses propres mots de passe
- ✅ Organiser avec catégories et tags
- ✅ Utiliser le générateur de mots de passe
- ✅ Se déconnecter et changer de compte
- ❌ Ne peut PAS voir les données des autres utilisateurs
- ❌ Ne peut PAS gérer les comptes

**Interface :**
```
┌─────────────────────────────────────┐
│  [+]  Bonjour, alice           [≡] │
├─────────────────────────────────────┤
│  Catégories    │  Mes mots de passe │
│  📂 Toutes     │                    │
│  👤 Personnel  │  🔑 Gmail          │
│  💼 Travail    │  🔑 GitHub         │
│  💰 Finance    │  🔑 Banque         │
└─────────────────────────────────────┘
```

### Administrateur (Admin)

**Permissions supplémentaires :**
- ✅ Voir la liste de tous les utilisateurs
- ✅ Réinitialiser le mot de passe d'un utilisateur
- ✅ Supprimer un compte utilisateur
- ✅ Voir les dates de création et dernière connexion
- ❌ Ne peut toujours PAS voir les mots de passe des autres

**Interface :**
```
┌─────────────────────────────────────┐
│  [+]  Bonjour, admin  [Admin]  [≡] │
│                                  ↓  │
│       Menu:                         │
│       • Gérer les utilisateurs      │
│       • Changer de compte           │
│       • Déconnexion                 │
└─────────────────────────────────────┘
```

## 🚀 Utilisation

### Premier lancement

1. **Compte admin par défaut créé automatiquement**
   - Username: `admin`
   - Password: `admin`

2. **⚠️ SÉCURITÉ** : Changez le mot de passe admin !
   - Connectez-vous avec admin/admin
   - Créez un nouveau compte admin personnel
   - Supprimez le compte admin par défaut

### Créer un compte utilisateur

#### Interface graphique

1. **Écran de sélection** → "Créer un nouveau compte"
2. Remplissez le formulaire :
   ```
   Nom d'utilisateur: alice
   Mot de passe maître: ********** (min. 8 caractères)
   Confirmer: **********
   ```
3. Cliquez sur "Créer le compte"
4. Votre workspace est créé automatiquement

#### Validation automatique

- ✅ Nom d'utilisateur unique (min. 3 caractères)
- ✅ Mot de passe fort (min. 8 caractères)
- ✅ Confirmation identique
- ❌ Nom d'utilisateur déjà pris → Erreur

### Se connecter

1. **Sélectionnez votre compte** dans la liste
2. Entrez votre **mot de passe maître**
3. Accédez à votre workspace personnel

```
┌───────────────────────────────────┐
│  🔐 Gestionnaire de mots de passe │
│  Sélectionnez votre compte        │
│                                   │
│  ┌─────────────────────────────┐ │
│  │ 👤 alice                    │ │
│  │    Dernière connexion: ...  │ │
│  ├─────────────────────────────┤ │
│  │ 👤 bob                      │ │
│  │    Dernière connexion: ...  │ │
│  ├─────────────────────────────┤ │
│  │ 👤 admin          [Admin]   │ │
│  │    Dernière connexion: ...  │ │
│  └─────────────────────────────┘ │
│                                   │
│  [ Créer un nouveau compte ]      │
└───────────────────────────────────┘
```

### Changer de compte

1. Menu utilisateur (☰) → "Changer de compte"
2. Retour à l'écran de sélection
3. Choisissez un autre utilisateur

### Se déconnecter

1. Menu utilisateur (☰) → "Déconnexion"
2. Ferme votre session
3. Retour à l'écran de sélection

## 🛠️ Gestion admin

### Accéder à la gestion

1. Connectez-vous avec un compte **Admin**
2. Menu (☰) → "Gérer les utilisateurs"

### Interface de gestion

```
┌─────────────────────────────────────────────────────┐
│  Gestion des utilisateurs                           │
├─────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────┐ │
│  │ alice                                         │ │
│  │ Créé: 2025-11-19                             │ │
│  │         [Réinitialiser MdP]  [Supprimer]    │ │
│  ├───────────────────────────────────────────────┤ │
│  │ bob                                           │ │
│  │ Créé: 2025-11-19                             │ │
│  │         [Réinitialiser MdP]  [Supprimer]    │ │
│  ├───────────────────────────────────────────────┤ │
│  │ admin                        [Admin]          │ │
│  │ Créé: 2025-11-19                             │ │
│  │ (Vous ne pouvez pas modifier votre compte)   │ │
│  └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Réinitialiser un mot de passe oublié

**Scénario** : Alice a oublié son mot de passe maître

1. **Admin se connecte**
2. Menu → "Gérer les utilisateurs"
3. Trouve "alice" → Clic "Réinitialiser MdP"
4. Dialogue de réinitialisation :
   ```
   Réinitialiser le mot de passe de 'alice'
   
   ⚠️ L'utilisateur devra utiliser ce nouveau mot de passe
   
   Nouveau mot de passe: ****************
   Confirmer: ****************
   
   [Annuler]  [Réinitialiser]
   ```
5. **Important** : Communiquez le nouveau mot de passe à Alice de manière sécurisée
6. Alice peut maintenant se connecter avec le nouveau mot de passe

**⚠️ Limitation importante** :
- Les **données chiffrées avec l'ancien mot de passe sont perdues**
- Après réinitialisation, Alice aura un workspace vide
- C'est une limitation cryptographique : impossible de déchiffrer sans l'ancien mot de passe

### Supprimer un utilisateur

**⚠️ ACTION IRRÉVERSIBLE**

1. Menu → "Gérer les utilisateurs"
2. Clic "Supprimer" sur l'utilisateur
3. Confirmation :
   ```
   Confirmer la suppression
   
   Voulez-vous vraiment supprimer l'utilisateur 'bob' ?
   
   Toutes ses données seront perdues.
   
   [Annuler]  [Supprimer]
   ```
4. Les fichiers suivants sont supprimés :
   - `passwords_bob.db`
   - `salt_bob.bin`
   - Entrée dans `users.db`

## 🔍 Cas d'usage

### Famille avec ordinateur partagé

```
Compte admin (Parent)
├── Gestion des comptes enfants
├── Réinitialisation si mot de passe oublié
└── Ses propres mots de passe

Compte alice (Fille)
└── Ses mots de passe personnels (invisible pour les autres)

Compte bob (Fils)
└── Ses mots de passe personnels (invisible pour les autres)
```

### Petite entreprise

```
Compte admin_it (DSI)
├── Gestion des comptes employés
├── Réinitialisation en cas d'oubli
└── Mots de passe infrastructure

Compte alice (Employée Marketing)
└── Mots de passe outils marketing

Compte bob (Employé Dev)
└── Mots de passe outils développement
```

### Utilisation personnelle avancée

```
Compte admin_perso (Vous)
└── Compte principal

Compte travail (Séparation pro/perso)
└── Mots de passe professionnels

Compte finance (Isolation finance)
└── Uniquement comptes bancaires et finance
```

## 🔐 Sécurité avancée

### Ce qu'un admin PEUT faire

✅ Voir la liste des utilisateurs
✅ Voir les dates de création et dernière connexion
✅ Réinitialiser le mot de passe maître d'un utilisateur
✅ Supprimer un compte utilisateur
✅ Créer de nouveaux comptes

### Ce qu'un admin NE PEUT PAS faire

❌ Voir les mots de passe stockés par un autre utilisateur
❌ Accéder au workspace d'un autre utilisateur
❌ Déchiffrer les données sans le mot de passe maître
❌ Récupérer un mot de passe maître oublié

### Pourquoi ces limitations ?

**Chiffrement de bout en bout** :
- Chaque mot de passe est chiffré avec une clé dérivée du mot de passe maître
- Sans le mot de passe maître, les données sont **mathématiquement indéchiffrables**
- Même l'admin ne peut pas contourner le chiffrement

**C'est une fonctionnalité, pas un bug** :
- Garantit la confidentialité absolue
- Aucun backdoor administrateur
- Même sous la contrainte, impossible de révéler les données d'un utilisateur

## 📊 Fichiers et données

### Structure des fichiers

```bash
# Base des utilisateurs (hash des mots de passe)
users.db
  ├── id | username | password_hash | salt | role | created_at | last_login
  ├──  1 | admin    | [hash]        | ...  | admin| 2025-11-19 | 2025-11-19
  ├──  2 | alice    | [hash]        | ...  | user | 2025-11-19 | 2025-11-19
  └──  3 | bob      | [hash]        | ...  | user | 2025-11-19 | null

# Workspace de chaque utilisateur (données chiffrées)
passwords_alice.db
  └── [Données chiffrées avec le mot de passe maître d'Alice]

salt_alice.bin
  └── [32 bytes de salt cryptographique pour Alice]
```

### Sauvegarde

**Pour sauvegarder tous les utilisateurs** :

```bash
#!/bin/bash
# Backup complet du gestionnaire multi-utilisateurs

BACKUP_DIR=~/backups/password-manager-$(date +%Y%m%d-%H%M%S)
DATA_DIR=~/.local/share/passwordmanager

mkdir -p "$BACKUP_DIR"

# Copier tous les fichiers
cp -r "$DATA_DIR"/* "$BACKUP_DIR/"

# Créer une archive
tar czf "$BACKUP_DIR.tar.gz" -C "$BACKUP_DIR/.." "$(basename $BACKUP_DIR)"

# Nettoyer
rm -rf "$BACKUP_DIR"

echo "✅ Backup créé : $BACKUP_DIR.tar.gz"
```

**Pour restaurer** :

```bash
tar xzf backup-YYYYMMDD-HHMMSS.tar.gz -C ~/.local/share/passwordmanager/
```

## 🐛 Dépannage

### "Mot de passe incorrect"

- Vérifiez que vous utilisez le bon compte
- Le mot de passe est sensible à la casse
- CapsLock activé ?

### "Cet utilisateur existe déjà"

- Le nom d'utilisateur doit être unique
- Choisissez un autre nom

### Un utilisateur a oublié son mot de passe

1. L'admin réinitialise le mot de passe
2. ⚠️ Les anciennes données sont perdues
3. L'utilisateur repart avec un workspace vide

### Supprimer le compte admin par défaut

1. Créez d'abord un nouveau compte admin
2. Connectez-vous avec le nouveau compte
3. Menu → Gérer les utilisateurs → Supprimer "admin"

### Migration depuis l'ancienne version (mono-utilisateur)

**Anciens fichiers** :
```
passwords.db  → À renommer en passwords_admin.db
salt.bin      → À renommer en salt_admin.bin
```

**Commandes** :
```bash
cd ~/.local/share/passwordmanager/
mv passwords.db passwords_admin.db
mv salt.bin salt_admin.bin
```

Ensuite, connectez-vous avec le compte admin créé automatiquement.

## 📚 Ressources

- [README principal](README.md) - Documentation complète
- [Guide Podman](PODMAN_GUIDE.md) - Conteneurisation
- [Code source](password_manager.py) - Application

## 💡 Bonnes pratiques

1. **Changez le mot de passe admin par défaut** immédiatement
2. **Utilisez des mots de passe maîtres forts** (min. 12 caractères)
3. **Sauvegardez régulièrement** tous les fichiers du répertoire
4. **Ne partagez jamais** votre mot de passe maître
5. **Un admin = personne de confiance** : Choisissez judicieusement
6. **Testez la restauration** de vos backups régulièrement

---

**🎉 Profitez de votre gestionnaire multi-utilisateurs !**
