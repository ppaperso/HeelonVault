# Changelog - Protection des données

## [0.2.1] - 2025-11-21

### 🔐 Ajouté - Sécurité et Protection des données

#### Sauvegarde automatique
- **Nouveau service** : `BackupService` pour gérer les sauvegardes automatiques
- **Sauvegarde à la déconnexion** : Création automatique d'une sauvegarde horodatée lors de la déconnexion
- **Détection intelligente** : Sauvegarde uniquement si des modifications ont été effectuées
- **Gestion automatique** : Conservation des 10 dernières sauvegardes, suppression automatique des anciennes
- **Notification** : Toast discret lors de la création d'une sauvegarde
- **Format** : `passwords_[username]_YYYYMMDD_HHMMSS.db`
- **Emplacement** : `~/.local/share/passwordmanager/backups/` (production) ou `src/data/backups/` (dev)

#### Permissions sécurisées
- **Fichiers sensibles protégés** : Permissions `0o600` (lecture/écriture propriétaire uniquement)
  - `users.db` : Base des utilisateurs
  - `passwords_*.db` : Bases de mots de passe
  - `salt_*.bin` : Fichiers salt de chiffrement
  - Fichiers de sauvegarde
- **Sécurisation au démarrage** : Vérification et correction automatique des permissions au lancement
- **Sécurisation à la création** : Permissions strictes appliquées dès la création des fichiers

### 🔧 Modifié

#### PasswordDatabase
- Ajout du tracker `_has_changes` pour détecter les modifications
- Méthodes `add_entry()`, `update_entry()`, `delete_entry()` marquent maintenant la base comme modifiée
- Nouvelles méthodes :
  - `has_unsaved_changes()` : Vérifie si des modifications sont en attente
  - `mark_as_saved()` : Marque la base comme sauvegardée
- Permissions des fichiers DB changées de `0o664` → `0o600`

#### PasswordManagerApplication
- Intégration du `BackupService`
- Méthode `on_logout()` améliorée avec sauvegarde automatique avant déconnexion
- Nouvelle méthode `_secure_sensitive_files()` : Sécurise tous les fichiers sensibles au démarrage
- Permissions des fichiers salt changées de `0o640` → `0o600`

### 🧪 Tests

#### Nouveaux tests unitaires
- `tests/unit/test_backup_service.py` : 11 tests couvrant toutes les fonctionnalités du BackupService
  - Création de sauvegarde
  - Listage et tri des sauvegardes
  - Nettoyage des anciennes sauvegardes
  - Restauration de sauvegarde
  - Détection de sauvegarde récente (skip si < 1 minute)
  - Vérification des permissions
  - Format des noms de fichiers

### 📚 Documentation

#### Nouveaux documents
- `docs/DATA_PROTECTION.md` : Guide complet sur les améliorations de protection des données
  - Description détaillée des fonctionnalités
  - Évaluation de la sécurité
  - Tests effectués
  - Limitations et recommandations
  - Améliorations futures possibles

### 🔍 Détails techniques

#### Flux de sauvegarde automatique
```
1. Utilisateur clique "Se déconnecter"
2. Vérification : db.has_unsaved_changes()
3. Si modifications → backup_service.create_user_db_backup(username)
4. Sauvegarde créée avec timestamp
5. Notification toast affichée
6. Nettoyage automatique (garde 10 dernières)
7. Déconnexion normale
```

#### Sécurisation des fichiers
```
Démarrage application
  ↓
_secure_sensitive_files()
  ↓
Pour chaque fichier sensible:
  - users.db
  - passwords_*.db
  - salt_*.bin
  ↓
chmod 0o600 (rw-------)
  ↓
Logs de confirmation
```

### ⚠️ Breaking Changes
Aucun - Rétrocompatible avec les versions précédentes

### 🐛 Corrections
Aucune

### 🚀 Performance
- Sauvegarde intelligente : skip si aucune modification
- Skip si sauvegarde récente (< 1 minute)
- Opérations de fichiers optimisées

### 📊 Statistiques
- **Fichiers ajoutés** : 3
  - `src/services/backup_service.py` (204 lignes)
  - `tests/unit/test_backup_service.py` (183 lignes)
  - `docs/DATA_PROTECTION.md` (422 lignes)
- **Fichiers modifiés** : 1
  - `password_manager.py` (6 sections modifiées)
- **Total lignes ajoutées** : ~850 lignes
- **Tests unitaires** : 11 nouveaux tests, 100% de réussite

### 🎯 Objectifs atteints
- ✅ Sauvegarde automatique lors de la déconnexion
- ✅ Protection renforcée contre l'accès direct aux fichiers
- ✅ Tests unitaires complets
- ✅ Documentation détaillée
