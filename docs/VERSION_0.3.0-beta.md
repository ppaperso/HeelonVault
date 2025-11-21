# Version 0.3.0-beta - Sauvegarde Automatique et Sécurisation

**Date de release** : 21 novembre 2025

## 🎯 Objectifs de cette version

Cette version majeure apporte un **système complet de sauvegarde automatique** avec rotation intelligente, une **sécurisation renforcée des données** avec permissions strictes, et une **interface de gestion des sauvegardes** pour les administrateurs.

## ✨ Nouvelles Fonctionnalités

### 🔐 Sauvegarde Automatique

#### Service de Sauvegarde (`BackupService`)
- **Sauvegarde automatique au logout** : Détection des modifications et sauvegarde automatique lors de la déconnexion
- **Sauvegarde système complète** : Backup de tous les utilisateurs (users.db + passwords_*.db + salt_*.bin)
- **Rotation intelligente** : Conservation des 7 sauvegardes les plus récentes
- **Format structuré** : Dossiers horodatés `system_backup_YYYYMMDD_HHMMSS/` avec fichier MANIFEST.txt
- **Permissions sécurisées** : Tous les backups en 0o700 (lecture/écriture/exécution propriétaire uniquement)

#### Interface de Gestion des Sauvegardes
- **Menu admin exclusif** : "Gérer les sauvegardes" dans le menu hamburger (accessible uniquement aux administrateurs)
- **Liste des sauvegardes** : Affichage avec date/heure, nombre de fichiers et taille
- **Sauvegarde manuelle** : Bouton pour créer une sauvegarde complète à la demande
- **Détails de sauvegarde** : Vue détaillée du contenu de chaque backup
- **Instructions de restauration** : Guide en 6 étapes pour restaurer les données
- **Ouverture du dossier** : Accès direct au répertoire des sauvegardes

### 🛡️ Sécurisation Renforcée

#### Protection des Données
- **Permissions strictes** : Tous les fichiers sensibles en mode 0o600 (lecture/écriture propriétaire uniquement)
  - users.db
  - passwords_*.db
  - salt_*.bin
  - Tous les fichiers de sauvegarde
- **Vérification au démarrage** : Application automatique des permissions sécurisées
- **Isolation dev/prod** : Séparation stricte des environnements de développement et production

#### Détection des Modifications
- **Tracking des changements** : Suivi des opérations d'ajout, modification et suppression
- **Optimisation** : Sauvegarde uniquement si des modifications ont été détectées
- **Flag de modification** : Système de `has_unsaved_changes()` pour éviter les sauvegardes inutiles

### 🧪 Sécurisation des Tests

#### Protection de l'Environnement de Production
- **Bannière de sécurité** : Tous les scripts de test affichent clairement qu'ils utilisent l'environnement de développement
- **Variable DEV_MODE forcée** : `export DEV_MODE=1` dans tous les scripts de test
- **7 scripts sécurisés** :
  - test-app.sh
  - tests/test-data-protection.sh
  - tests/run_all_tests.sh
  - tests/test-import-csv.sh
  - tests/test-version.sh
  - tests/test_no_deprecation.sh
  - tests/test-logging.sh

#### Tests de Rotation
- **Nouveau test unitaire** : `tests/unit/test_backup_rotation.py` avec 5 scénarios de test
- **Validation complète** : Test de la rotation avec 7, 9, 10 et 15 sauvegardes
- **Test de tri par mtime** : Vérification que la rotation se base sur la date de modification, pas le nom

### 🐛 Corrections

#### Interface Utilisateur
- **Champ Notes accessible** : Le TextView des notes est maintenant correctement enveloppé dans un ScrolledWindow
- **Hauteur optimale** : Zone de texte avec hauteur minimale de 150px
- **Wrap automatique** : Le texte passe à la ligne automatiquement
- **Marges améliorées** : Meilleur confort visuel avec marges de 10px

## 📊 Statistiques

### Code
- **Fichiers modifiés** : 15+
- **Nouveaux fichiers** : 5
  - src/services/backup_service.py (250+ lignes)
  - src/ui/dialogs/backup_manager_dialog.py (350+ lignes)
  - tests/unit/test_backup_service.py (250+ lignes)
  - tests/unit/test_backup_rotation.py (200+ lignes)
  - tests/SECURITY_TESTING.md

### Tests
- **Tests unitaires** : +19 tests (14 pour backup_service, 5 pour rotation)
- **Couverture** : Tous les tests passent ✅
- **Sécurité** : 100% des scripts de test sécurisés

### Documentation
- **Fichiers déplacés** : 7 fichiers .md vers docs/
- **Nouveaux guides** : 
  - tests/SECURITY_TESTING.md
  - tests/CHANGELOG_SECURITY_FIX.md

## 🔧 Changements Techniques

### Architecture
```
src/services/
  └── backup_service.py          # Nouveau service de sauvegarde
src/ui/dialogs/
  └── backup_manager_dialog.py   # Nouvelle interface de gestion
tests/unit/
  ├── test_backup_service.py     # Tests du service
  └── test_backup_rotation.py    # Tests de rotation
tests/
  ├── SECURITY_TESTING.md        # Guide de sécurité
  └── CHANGELOG_SECURITY_FIX.md  # Log des corrections
```

### Permissions
```
Avant : 0o664 (rw-rw-r--)
Après : 0o600 (rw-------)
```

### Format de Sauvegarde
```
backups/
└── system_backup_20251121_143000/
    ├── MANIFEST.txt
    ├── users.db
    ├── passwords_admin.db
    ├── passwords_user1.db
    ├── salt_admin.bin
    └── salt_user1.bin
```

## 🚀 Migration depuis 0.2.0-beta

### Automatique
- Les permissions seront automatiquement corrigées au premier lancement
- Le système de sauvegarde se configure automatiquement
- Aucune intervention manuelle requise

### Optionnel
- Les administrateurs peuvent créer une sauvegarde manuelle via le menu
- Vérifier que le dossier `backups/` est créé et accessible

## 📝 Notes de Mise à Jour

### Pour les Développeurs
- **IMPORTANT** : Tous les scripts de test DOIVENT définir `export DEV_MODE=1`
- Utiliser `venv-dev/` pour les tests, jamais `venv/`
- Les données de test sont dans `src/data/`, jamais dans `/var/lib/password-manager-shared/`
- Consulter `tests/SECURITY_TESTING.md` pour les guidelines

### Pour les Administrateurs
- Nouveau menu "Gérer les sauvegardes" accessible uniquement aux admins
- Les sauvegardes sont créées automatiquement à la déconnexion (si modifications)
- Maximum 7 sauvegardes conservées (rotation automatique)
- Consulter les instructions de restauration dans le dialogue de gestion

### Pour les Utilisateurs
- La déconnexion peut prendre 1-2 secondes supplémentaires (création de sauvegarde)
- Vos données sont maintenant automatiquement sauvegardées
- Aucune action requise de votre part

## 🔗 Liens Utiles

- [Guide de Sécurité des Tests](tests/SECURITY_TESTING.md)
- [Corrections de Sécurité](tests/CHANGELOG_SECURITY_FIX.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Sécurité](docs/SECURITY.md)

## 👥 Contributeurs

- Développement : ppaperso
- Tests : ppaperso
- Documentation : ppaperso

## 📅 Prochaine Version (0.4.0)

Fonctionnalités prévues :
- Import/Export de sauvegardes
- Compression des sauvegardes
- Sauvegarde planifiée automatique
- Notifications de sauvegarde
- Dashboard de statistiques

---

**Version complète** : 0.3.0-beta  
**Date** : 21 novembre 2025  
**Statut** : ✅ Stable pour environnement de test
