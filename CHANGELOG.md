# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

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
