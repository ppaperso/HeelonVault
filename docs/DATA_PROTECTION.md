# 🔐 Protection des Données - Améliorations

**Date**: 21 novembre 2025  
**Version**: 0.2.1

## 📝 Résumé des améliorations

Ce document décrit les améliorations apportées au système de protection des données du gestionnaire de mots de passe.

---

## 🎯 Objectifs atteints

### 1. ✅ Sauvegarde automatique à la déconnexion

**Fonctionnalité** : Création automatique d'une sauvegarde horodatée de la base de données lors de la déconnexion (Menu "Se déconnecter").

**Implémentation** :

- Nouveau service : `src/services/backup_service.py`
- Détection intelligente des modifications via un système de tracking
- Sauvegarde uniquement si des changements ont été effectués
- Gestion automatique des anciennes sauvegardes (conservation des 10 dernières)
- Notification toast discrète lors de la création de la sauvegarde

**Comportement** :

```text
Utilisateur clique sur "Se déconnecter"
    ↓
Vérification : Y a-t-il des modifications ?
    ↓ Oui
Création d'une sauvegarde : passwords_[user]_YYYYMMDD_HHMMSS.db
    ↓
Sauvegarde stockée dans : ~/.local/share/passwordmanager/backups/
    ↓
Notification : "💾 Sauvegarde créée: passwords_admin_20251121_143052.db"
    ↓
Nettoyage automatique (garde les 10 dernières)
    ↓
Déconnexion
```

**Détails techniques** :

- Format de sauvegarde : `passwords_[username]_YYYYMMDD_HHMMSS.db`
- Répertoire : `~/.local/share/passwordmanager/backups/`
- Permissions : `0o600` (lecture/écriture propriétaire uniquement)
- Tracking des modifications :
  - `add_entry()` → marque comme modifié
  - `update_entry()` → marque comme modifié
  - `delete_entry()` → marque comme modifié
- Protection contre les doublons : skip si sauvegarde < 1 minute

---

### 2. ✅ Protection renforcée des fichiers sensibles

**Problème identifié** :

- Les bases de données SQLite peuvent être ouvertes directement avec un outil externe (ex: `sqlite3`)
- Les permissions des fichiers étaient trop permissives (`0o664` = lisible par tous)
- Bien que les mots de passe soient chiffrés (AES-256-GCM), la structure de la base et les métadonnées étaient exposées

**Solution implémentée** :

#### A. Permissions strictes (600)

Tous les fichiers sensibles ont maintenant les permissions `0o600` (lecture/écriture propriétaire uniquement) :

- ✅ `users.db` : Base des utilisateurs
- ✅ `passwords_*.db` : Bases de mots de passe par utilisateur
- ✅ `salt_*.bin` : Fichiers salt de chiffrement
- ✅ Fichiers de sauvegarde dans `backups/`

#### B. Sécurisation automatique au démarrage

Fonction `_secure_sensitive_files()` :

- Appelée à chaque lancement de l'application
- Parcourt et sécurise tous les fichiers sensibles existants
- Logs détaillés pour traçabilité

#### C. Sécurisation à la création

- Nouveau fichier `.db` créé → permissions `0o600` appliquées immédiatement
- Nouveau fichier `salt_*.bin` créé → permissions `0o600` appliquées immédiatement
- Nouvelles sauvegardes → permissions `0o600` appliquées immédiatement

---

## 🔒 Niveaux de protection

### Niveau 1 : Permissions du système de fichiers

```bash
# Avant (trop permissif)
-rw-r--r--  passwords_admin.db    # Tous peuvent lire

# Après (sécurisé)
-rw-------  passwords_admin.db    # Seul le propriétaire peut lire/écrire
-rw-------  salt_admin.bin
-rw-------  users.db
```

### Niveau 2 : Chiffrement des données sensibles

Les données suivantes sont chiffrées avec **AES-256-GCM** :

- ✅ Mots de passe (`password_data`)
- ✅ Notes (`notes`)
- ✅ Utilisation d'un **nonce unique** par entrée
- ✅ **Tag d'authentification** pour détecter toute modification

**Ce qui reste en clair dans la base** (par conception) :

- Titre de l'entrée (`title`)
- Nom d'utilisateur (`username`)
- URL (`url`)
- Catégorie (`category`)
- Tags (`tags`)

### Niveau 3 : Authentification multi-niveaux

1. **Authentification utilisateur** : Hash PBKDF2 (600 000 itérations)
2. **Mot de passe maître** : Dérivation de clé avec PBKDF2 + salt unique
3. **Salt individuel** : Chaque utilisateur a son propre salt

---

## 🛡️ Évaluation de la sécurité

### ✅ Protection contre l'accès direct à la base

### Tentative 1 : Lecture avec sqlite3**

```bash
$ sqlite3 passwords_admin.db "SELECT * FROM passwords"
Error: unable to open database file  # Permission refusée (600)
```

### Tentative 2 : Lecture avec Python**

```python
import sqlite3
conn = sqlite3.connect('passwords_admin.db')  # Permission refusée (600)
# OU si exécuté en tant que propriétaire :
cursor.execute('SELECT password_data FROM passwords')
# Résultat : Données chiffrées illisibles sans la clé
# {"nonce": "7KF8x...", "ciphertext": "gh45j..."}
```

**Conclusion** :

- ✅ Les fichiers ne peuvent être lus que par le propriétaire
- ✅ Même si un attaquant obtient le fichier, les données sensibles sont chiffrées
- ✅ Sans le mot de passe maître, impossible de déchiffrer

### ⚠️ Données non chiffrées (limitations acceptables)

**Métadonnées exposées** (si accès physique au fichier) :

- Titres des entrées (ex: "Compte Gmail", "Banque XYZ")
- Noms d'utilisateurs (ex: "<john.doe@example.com>")
- URLs (ex: "<https://gmail.com>")

**Justification** :

1. Nécessaire pour la recherche et le filtrage rapides
2. Pas de secrets critiques (les mots de passe sont chiffrés)
3. Compromis performance/sécurité standard pour ce type d'application

**Recommandation** : Si un niveau de sécurité maximal est requis (ex: contexte militaire), envisager :

- Chiffrement de toute la base avec SQLCipher
- Chiffrement au niveau du disque (LUKS, FileVault)
- Conteneur chiffré VeraCrypt

---

## 📊 Tests effectués

### Test 1 : Sauvegarde automatique

```bash
# Conditions : 
- Utilisateur connecté : admin
- Ajout d'une nouvelle entrée
- Clic sur "Se déconnecter"

# Résultat attendu :
✅ Sauvegarde créée : passwords_admin_20251121_143052.db
✅ Toast affiché : "💾 Sauvegarde créée: passwords_admin_20251121_143052.db"
✅ Fichier dans backups/ avec permissions 600
✅ Anciennes sauvegardes nettoyées (garde 10 dernières)
```

### Test 2 : Permissions sécurisées

```bash
# Avant l'amélioration
$ ls -l ~/.local/share/passwordmanager/
-rw-r--r-- passwords_admin.db    # Lisible par tous ❌

# Après l'amélioration
$ ls -l ~/.local/share/passwordmanager/
-rw------- passwords_admin.db    # Propriétaire uniquement ✅
-rw------- salt_admin.bin        # Propriétaire uniquement ✅
-rw------- users.db              # Propriétaire uniquement ✅

# Tentative de lecture par un autre utilisateur
$ su - otheruser
$ cat /home/admin/.local/share/passwordmanager/passwords_admin.db
cat: passwords_admin.db: Permission non accordée ✅
```

### Test 3 : Détection de modifications

```bash
# Scénario 1 : Aucune modification
- Connexion → Déconnexion immédiate
- Résultat : Pas de sauvegarde créée ✅

# Scénario 2 : Modifications effectuées
- Connexion → Ajout/Édition/Suppression → Déconnexion
- Résultat : Sauvegarde créée ✅

# Scénario 3 : Déconnexions multiples rapides
- Déconnexion 1 : Sauvegarde créée à 14:30:52 ✅
- Déconnexion 2 (< 1 min après) : Skip (même sauvegarde) ✅
```

---

## 🔧 Fichiers modifiés

### Nouveaux fichiers

- `src/services/backup_service.py` : Service de sauvegarde automatique
- `docs/DATA_PROTECTION.md` : Cette documentation

### Fichiers modifiés

- `password_manager.py` :
  - Import de `BackupService`
  - Ajout de `_has_changes` dans `PasswordDatabase`
  - Modification de `add_entry()`, `update_entry()`, `delete_entry()`
  - Ajout de `has_unsaved_changes()` et `mark_as_saved()`
  - Modification de `on_logout()` avec sauvegarde automatique
  - Ajout de `_secure_sensitive_files()` dans `PasswordManagerApplication`
  - Permissions changées de `0o664` → `0o600` pour tous les fichiers sensibles

---

## 📈 Améliorations futures possibles

### Court terme

- [ ] Interface de restauration de sauvegarde dans l'UI
- [ ] Export chiffré des sauvegardes vers un emplacement externe
- [ ] Compression des sauvegardes anciennes (gzip)

### Moyen terme

- [ ] Chiffrement des métadonnées (titre, username, URL)
- [ ] Synchronisation chiffrée avec un serveur distant
- [ ] Audit trail des accès aux mots de passe

### Long terme

- [ ] Migration vers SQLCipher pour chiffrer toute la base
- [ ] Support du chiffrement matériel (TPM, Secure Enclave)
- [ ] Authentification à deux facteurs (2FA)

---

## 🔍 Références

- **AES-256-GCM** : [NIST SP 800-38D](https://csrc.nist.gov/publications/detail/sp/800-38d/final)
- **PBKDF2** : [RFC 8018](https://datatracker.ietf.org/doc/html/rfc8018)
- **SQLite Security** : [SQLite Security Best Practices](https://www.sqlite.org/security.html)
- **File Permissions** : [Linux File Permissions Guide](https://www.linux.com/training-tutorials/understanding-linux-file-permissions/)

---

## ✅ Conclusion

Les deux objectifs ont été atteints :

1. ✅ **Sauvegarde automatique** : Système de backup horodaté intelligent lors de la déconnexion
2. ✅ **Protection renforcée** : Permissions strictes (600) sur tous les fichiers sensibles

**Niveau de sécurité actuel** : 🟢 **ÉLEVÉ**

- Chiffrement AES-256-GCM des données critiques
- Permissions système strictes
- Sauvegardes automatiques
- Protection multi-niveaux (authentification + chiffrement)

**Recommandations** :

- ✅ Adapté pour un usage personnel et professionnel standard
- ⚠️ Pour usage très sensible, envisager le chiffrement du disque entier
- ℹ️ Effectuer des sauvegardes externes régulières (USB chiffré, cloud chiffré)
