# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [0.3.0-beta] - 2025-11-21

### ✨ Ajouté

#### Sauvegarde Automatique
- **BackupService** : Service complet de gestion des sauvegardes
  - Sauvegarde automatique au logout si modifications détectées
  - Sauvegarde système complète (users.db + passwords_*.db + salt_*.bin)
  - Rotation intelligente : conservation des 7 sauvegardes les plus récentes
  - Format structuré : dossiers `system_backup_YYYYMMDD_HHMMSS/` avec MANIFEST.txt
  - Permissions sécurisées 0o700 pour tous les backups

#### Interface de Gestion des Sauvegardes
- **Menu admin** : "Gérer les sauvegardes" (accessible uniquement aux administrateurs)
- **BackupManagerDialog** : Interface complète de gestion
  - Liste des sauvegardes avec date, taille et nombre de fichiers
  - Bouton de sauvegarde manuelle
  - Vue détaillée du contenu de chaque backup
  - Instructions de restauration en 6 étapes
  - Bouton d'ouverture du dossier de sauvegardes

#### Sécurité Renforcée
- **Permissions strictes** : Tous les fichiers sensibles en mode 0o600 (au lieu de 0o664)
  - users.db, passwords_*.db, salt_*.bin
  - Application automatique au démarrage
- **Détection des modifications** : Tracking des changements pour optimiser les sauvegardes
- **Sécurisation des tests** : Tous les scripts de test forcent `DEV_MODE=1`
  - Bannière de sécurité visible dans tous les scripts
  - Protection contre l'accès accidentel aux données de production
  - Documentation complète : `tests/SECURITY_TESTING.md`

#### Tests
- **test_backup_service.py** : 14 tests unitaires pour le service de sauvegarde
- **test_backup_rotation.py** : 5 tests de rotation (7, 9, 10, 15 sauvegardes)
- **test-data-protection.sh** : Tests des permissions et de la protection
- **Amélioration de test-app.sh** : Ajout des tests de sauvegarde et rotation

### 🐛 Corrigé
- **Champ Notes** : Zone de texte maintenant accessible dans les dialogues d'ajout/édition
  - TextView correctement enveloppé dans un ScrolledWindow
  - Hauteur minimale de 150px pour une meilleure utilisation
  - Wrap automatique et marges de 10px

### 🔧 Modifié
- **Organisation de la documentation** : Déplacement de 7 fichiers .md vers `docs/`
  - RESUME_PROTECTION_DONNEES.md
  - CHANGELOG_DATA_PROTECTION.md
  - VERSION_0.1.0-beta.md, VERSION_0.2.0-beta.md
  - VERSION_SUMMARY.md
  - CHANGELOG_CSV_IMPORT.md
  - MULTI_USER_GUIDE.md
- **PasswordDatabase** : Ajout du tracking des modifications
  - Méthodes `has_unsaved_changes()` et `mark_as_saved()`
  - Flag `_has_changes` pour optimiser les sauvegardes
- **test-app.sh** : Amélioration avec tests de protection et rotation

### 📚 Documentation
- **docs/VERSION_0.3.0-beta.md** : Documentation complète de la version
- **tests/SECURITY_TESTING.md** : Guide de sécurité pour les tests
- **tests/CHANGELOG_SECURITY_FIX.md** : Résumé des corrections de sécurité
- Mise à jour de tous les fichiers .md avec les nouvelles fonctionnalités

### 🛠️ Technique
- 250+ lignes : `src/services/backup_service.py`
- 350+ lignes : `src/ui/dialogs/backup_manager_dialog.py`
- 19 nouveaux tests unitaires (tous passent ✅)
- 7 scripts de test sécurisés avec bannière `DEV_MODE=1`

## [0.2.0-beta] - 2025-11-20

### ✨ Ajouté
- Module `src/config/logging_config.py` avec rotation quotidienne, niveaux adaptés (DEBUG en DEV, INFO en PROD) et répertoires distincts (`./logs` vs `/var/log/password_manager`).
- Script `tests/test-logging.sh` qui génère plusieurs journaux, valide la suppression des plus anciens et échoue si la rotation ne respecte pas la rétention de 7 fichiers.
- Fichier `VERSION_0.2.0-beta.md` et mise à jour complète du `VERSION_SUMMARY.md`.

### 🔧 Modifié
- `password_manager.py`, services (`auth_service`, `crypto_service`, `password_generator`, `csv_importer`, etc.) et dialogues GTK reçoivent une instrumentation détaillée pour tracer les actions clés.
- `tests/run_all_tests.sh` exécute désormais `tests/test-logging.sh` afin que la CI couvre la rotation des journaux.
- `tests/test-version.sh`, `README.md`, `password-manager.desktop` et `src/version.py` reflètent la nouvelle version `0.2.0-beta`.
- Documentation (README, CHANGELOG, VERSION_SUMMARY) mise à jour pour décrire l'infrastructure de logs et les nouveaux scripts.

### 🛠️ Technique
- Gestion de fallback automatique vers `/tmp/password_manager_logs` si l'écriture dans `/var/log/password_manager` échoue (droits insuffisants).
- Nettoyage automatique des anciens fichiers de log (7 derniers conservés) à chaque initialisation.
- Amélioration de la visibilité sur l'application grâce à des messages structurés aux niveaux INFO/WARNING/ERROR.

## [0.1.0-beta] - 2025-11-19

### ✨ Ajouté

#### Import/Export
- **Import CSV** : Importation de mots de passe depuis LastPass, 1Password, Bitwarden
  - Support de multiples formats (délimiteur `;` ou `,`)
  - Détection automatique du format
  - Gestion des en-têtes
  - Aperçu avant import
  - Résumé détaillé avec erreurs et avertissements
  - Fichiers de test inclus

#### Interface utilisateur
- **Système de versioning** : Version 0.1.0-beta
  - Affichage sur l'écran de sélection d'utilisateur
  - Affichage sur l'écran de connexion
  - Dialogue "À propos" accessible depuis le menu principal
  - Informations complètes (version, description, technologies, licence)

#### Sécurité
- **Protection contre les attaques par force brute**
  - Délai progressif après chaque échec (2s, 5s, 10s, 30s)
  - Verrouillage après 5 tentatives pendant 15 minutes
  - Compteurs indépendants par utilisateur
  - Logs de sécurité

#### Gestion multi-utilisateurs
- Workspaces isolés par utilisateur
- Rôles : Admin et Utilisateur standard
- Gestion des utilisateurs par les admins
- Changement de mot de passe personnel
- Réinitialisation de mot de passe (admin)

#### Fonctionnalités de base
- **Chiffrement AES-256-GCM** pour tous les mots de passe
- **PBKDF2** (600 000 itérations) pour la dérivation de clé
- Organisation par catégories et tags
- Recherche rapide dans toutes les entrées
- Générateur de mots de passe sécurisés
  - Mots de passe aléatoires (8-64 caractères)
  - Phrases de passe mémorables
  - Options personnalisables
- Stockage sécurisé avec SQLite3

### 📝 Documentation
- Guide complet d'importation CSV
- Guide rapide LastPass
- Documentation de l'architecture
- Guide de sécurité
- Guide multi-utilisateurs
- Documentation des tests

### 🧪 Tests
- 10 tests unitaires pour l'import CSV
- 7 tests d'intégration pour la protection brute force
- Scripts de test automatisés
- Taux de réussite : 100%

### 🛠️ Technique
- Python 3.8+ avec type hints
- GTK4 + Libadwaita pour l'interface
- Structure modulaire (src/, tests/, docs/)
- Logging complet des opérations
- Gestion robuste des erreurs

### 📦 Fichiers de configuration
- `src/version.py` : Gestion du versioning
- `test-version.sh` : Script de test du versioning
- `test-import-csv.sh` : Script de test de l'import CSV
- Exemples CSV pour LastPass

### 🚀 Déploiement
- Support Podman/Docker
- Script de build et run conteneurisé
- Mode développement avec `run-dev.sh`
- Documentation d'installation complète

---

## [Non publié]

### ✨ Modifié
- Centralisation de la création des boîtes de dialogue via `present_alert()` pour harmoniser l'interface et réduire la duplication.
- Gestion améliorée du focus initial avec `GLib.idle_add` afin d'éviter les warnings GTK lors de l'ouverture des fenêtres.

### 🐛 Corrigé
- Correction des boîtes de dialogue de confirmation qui provoquaient une exception (`Task.get_string`).
- Prévention des warnings `gdk_frame_clock_get_frame_time` en retardant la création d'un parent temporaire avant d'afficher un dialogue sans fenêtre active.

### 🔮 Prévu pour les futures versions
- Export vers CSV
- Import/Export JSON
- Support de plus de formats (KeePass, Dashlane)
- Détection et gestion des doublons lors de l'import
- Sauvegarde et restauration complète
- Synchronisation cloud (optionnelle)
- Application mobile
- Thèmes personnalisés
- Raccourcis clavier personnalisables
- Plugin navigateur
- Authentification à deux facteurs (2FA)
- Partage sécurisé de mots de passe entre utilisateurs
- Historique des modifications
- Audit de sécurité des mots de passe

---

## Types de changements
- **Ajouté** pour les nouvelles fonctionnalités
- **Modifié** pour les changements aux fonctionnalités existantes
- **Déprécié** pour les fonctionnalités qui seront supprimées
- **Supprimé** pour les fonctionnalités supprimées
- **Corrigé** pour les corrections de bugs
- **Sécurité** pour les vulnérabilités corrigées
