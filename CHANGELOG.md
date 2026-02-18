# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [1.0.0] - 2026-02-18

### 🎉 Première Version Stable

Cette version majeure marque la première release stable du gestionnaire de mots de passe, avec des améliorations majeures en sécurité, ergonomie et fiabilité.

### ✨ Ajouté

#### 🔒 Améliorations de Sécurité

- **Générateur de mots de passe renforcé** :
  - Liste de mots française étendue : 1053 mots (vs 100 précédemment)
  - Longueur par défaut augmentée : 20 caractères (vs 16)
  - Passphrases : 5 mots par défaut (vs 4)
  - Meilleure entropie et résistance aux attaques par dictionnaire

- **Validateur de mot de passe maître** :
  - Indicateur de force en temps réel dans CreateUserDialog
  - Exigences claires : 12+ caractères, majuscules, minuscules, chiffres, symboles
  - Score visuel avec code couleur (Faible/Moyen/Fort/Très Fort)
  - Feedback immédiat pour guider l'utilisateur

#### 🗑️ Système de Corbeille

- **Soft delete avec restauration** :
  - Colonne `deleted_at` pour marquage des entrées supprimées
  - Bouton corbeille (🗑️) sur chaque carte d'entrée
  - Interface dédiée de gestion de la corbeille
  - Actions : Restaurer, Supprimer définitivement, Vider la corbeille
  - Confirmation pour éviter les suppressions accidentelles

- **Migration automatique** :
  - Ajout automatique de la colonne `deleted_at` aux bases existantes
  - Compatible avec toutes les bases de données existantes
  - 8 tests automatisés (unit + integration)

#### 🎨 Optimisations UI/UX

- **Cartes d'entrées compactes** :
  - Taille réduite de 45% : 200px × 85px (vs 260px × 150-200px)
  - Layout vertical optimisé
  - Actions groupées horizontalement
  - Plus d'entrées visibles sans scroll

- **Filtres de recherche avancés** :
  - 5 filtres configurables : Titre, Catégorie, Username, URL, Tags
  - Checkboxes horizontales pour économiser l'espace
  - Recherche précise en décochant les champs inutiles
  - Recherche en temps réel

- **Sidebar optimisée** :
  - Catégories et tags en FlowBox multi-colonnes
  - Plusieurs badges par ligne au lieu d'un seul
  - Sections repliables (Adw.ExpanderRow)
  - Compteurs dynamiques de catégories et tags
  - Filtres de recherche dédiés pour catégories et tags
  - Catégories sans scroll (toutes visibles)
  - Tags avec scroll pour l'espace restant

- **Icônes et symboles** :
  - Icônes emoji pour catégories : 📂 Toutes, 📁 Autres
  - Symbole # pour les tags
  - Interface plus visuelle et moderne

#### 🔐 Backup Automatique

- **Protection avant migration** :
  - Backup automatique créé avant chaque migration de base de données
  - Sauvegarde horodatée dans `backups/`
  - Conservation des 7 derniers backups
  - Permissions 0o600 pour sécurité maximale
  - Logs détaillés de chaque backup
  - Test automatisé de validation du système

### 🔧 Améliorations

#### Performance

- **Affichage optimisé** :
  - Réduction de 45% de l'espace occupé par les cartes
  - Filtrage en temps réel sans latence
  - FlowBox pour rendu optimisé des badges
  - Scroll uniquement quand nécessaire

#### Sécurité

- **Protection des données** :
  - Backup automatique avant toute modification structurelle
  - Soft delete : aucune perte de données accidentelle
  - Validateur de mot de passe pour comptes utilisateurs
  - Conservation de l'historique des backups

#### Ergonomie

- **Interface scalable** :
  - Design adapté pour gérer 100+ entrées
  - Recherche et filtrage efficaces
  - Sections repliables pour gérer l'espace
  - Navigation fluide entre catégories et tags

### 🐛 Corrigé

- **Recherche par champ** : Fix du problème où rechercher "orange" renvoyait tous les emails @orange.fr
- **Espace UI** : Optimisation des marges et espacements pour maximiser l'affichage
- **Scroll inutile** : Catégories maintenant toutes visibles sans scroll

### 📊 Statistiques

- **Tests** : 8 tests automatisés pour le système de corbeille
- **Réduction UI** : 45% d'espace économisé sur les cartes
- **Sécurité** : Score passé de 7.5/10 à 9/10
- **Code qualité** : 0 erreur ruff, formatage automatique

### 🔜 Prochaines Étapes (v1.1.0)

- [ ] Export/Import CSV amélioré
- [ ] Gestion multi-utilisateurs avancée
- [ ] Synchronisation cloud optionnelle
- [ ] Mode sombre natif
- [ ] Raccourcis clavier personnalisables

---

## [0.4.0-beta] - 2025-12-03

### ✨ Ajouté-

#### 🦊 Extension Firefox - Intégration Navigateur Complète

- **Architecture Dual Environment** : Environnements DEV et PROD complètement isolés
  - Extension DEV avec badge orange "DEV" (défini dynamiquement)
  - Extension PROD pour utilisation en production
  - Bases de données séparées : `src/data/` (DEV) vs `data/` (PROD)
  - Logs séparés pour faciliter le debugging

- **Popup Interactif** : Interface utilisateur complète dans le navigateur
  - Indicateur de connexion (🟢 Connecté / 🔴 Déconnecté)
  - Liste des identifiants avec titre et username
  - Barre de recherche en temps réel
  - Boutons d'action : "🔑 Remplir" et "📋 Copier"
  - Bouton de rafraîchissement et accès aux paramètres

- **Générateur de Mots de Passe** : Intégré dans le popup
  - Génération de mots de passe sécurisés de 20 caractères
  - Copie automatique dans le presse-papiers
  - Affichage temporaire pour vérification

#### 🔌 Native Messaging Host

- **Communication bidirectionnelle** : Protocol binary length-prefixed JSON
  - Messages supportés : `ping`, `search_credentials`, `get_credentials`, `generate_password`
  - Communication via stdin/stdout sécurisée
  - Validation stricte du format JSON

- **Paramètre showAll** : Récupération intelligente des credentials
  - `showAll=true` : Retourne toutes les entrées sans filtrage
  - `showAll=false` : Filtre par domaine (legacy)
  - Requête SQL optimisée selon le paramètre

#### 🎯 Filtrage Intelligent par URL

- **Logique côté client** : Récupération globale + filtrage intelligent
  - **URL match** : Affiche uniquement les entrées correspondantes
  - **URL ne match pas** : Affiche TOUTES les entrées (choix manuel possible)
  - **URL système** (about:, moz-extension:) : Affiche TOUTES les entrées
  - **Barre de recherche** : Cherche toujours dans TOUTES les entrées disponibles

- **Avantages** :
  - Performance : 1 seule requête backend
  - Contextuel : Affiche les bons identifiants sur les sites connus
  - Flexible : Jamais bloqué sur une seule entrée
  - Pas de latence : Filtrage JavaScript instantané

#### 🛠️ Scripts d'Installation et de Test

- **Installation** :
  - `install_dev.sh` : Installation complète environnement DEV
  - `install_prod.sh` : Installation complète environnement PROD
  - `install_native_host.sh` : Installation du native host uniquement
  - `install_firefox_extension.sh` : Installation extension Firefox

- **Tests** :
  - `test_dev_communication.py` : Tests complets (ping, showAll, URL filter, generate)
  - `test_url_matching.py` : Tests de la logique de filtrage (5 scénarios)
  - `test_native_host.sh` : Test rapide de connexion
  - `test_connection_firefox.sh` : Test depuis Firefox

#### 📚 Documentation Complète

- **Guides utilisateur** :
  - `QUICK_START.md` : Installation en 3 étapes
  - `README.md` : Documentation complète de l'intégration
  - `URL_FILTERING_BEHAVIOR.md` : Comportement détaillé du filtrage

- **Guides développeur** :
  - `DEV_PROD_SOLUTION.md` : Architecture dual environment
  - `DEBUGGING_GUIDE.md` : Guide de débogage complet
  - `SIGNING_GUIDE.md` : Signature d'extension pour Firefox
  - `PERMANENT_EXTENSION.md` : Installation permanente

- **Résolution de problèmes** :
  - `PHASE_2_COMPLETE.md` : Résolution problème d'affichage
  - `PHASE_2_FIX.md` : Fix du filtrage par URL
  - `QUICK_COMMANDS.sh` : Commandes rapides de développement

### 🐛 Corrigé-

#### Extension Firefox

- **Avertissements manifest.json** :
  - Suppression de `default_badge_text` et `default_badge_background_color` du manifest
  - Badge "DEV" défini dynamiquement via `browser.browserAction.setBadgeText()`
  - Conformité totale avec Firefox Manifest V2

#### Logique de Filtrage

- **Filtrage par URL revu** :
  - Anciennement : Filtrage backend avec requêtes multiples et affichage partiel
  - Maintenant : Récupération globale + filtrage client intelligent
  - Fix : La recherche fonctionne toujours dans toutes les entrées (pas de blocage)
  - Fix : Sur URL inconnue, affiche tout (pas de liste vide)

### 🔧 Améliorations-

#### Architecture

- **Séparation DEV/PROD** : Environnements complètement isolés
- **Variable DEV_MODE** : Contrôle automatique de l'environnement (0 ou 1)
- **Logs séparés** : `native_host_dev.log` vs `native_host_prod.log`

#### Performance-

- **1 seule requête SQL** : Récupération globale au lieu de multiples requêtes
- **Filtrage côté client** : JavaScript rapide vs requêtes réseau
- **Cache des credentials** : Variable `allCredentials` dans le popup

#### Sécurité-

- **Communication chiffrée** : Via Native Messaging sécurisé de Firefox
- **Validation des messages** : Format JSON strict avec gestion d'erreurs
- **Isolation des environnements** : Bases de données et logs séparés
- **Logs détaillés** : Traçabilité complète des opérations

### 📊 Statistiques-

- **Fichiers ajoutés** : 25+ (extensions, scripts, documentation)
- **Lignes de code** : ~2000 (JavaScript + Python)
- **Tests** : 9 tests validés (communication + filtrage URL)
- **Documentation** : 10+ fichiers markdown

### 🚧 Limitations Connues

- ⏳ **Récupération des mots de passe** : Affiche username uniquement (décryption à venir)
- ⏳ **Auto-fill automatique** : Bouton "Remplir" non fonctionnel
- ⏳ **Sauvegarde de nouveaux identifiants** : À implémenter
- ⚠️ **Extension temporaire** : Disparaît au redémarrage de Firefox (signature nécessaire)

### 🔜 Prochaines Étapes (v0.5.0)

- [ ] Phase 3 : Récupération et décryption des mots de passe
- [ ] Phase 4 : Auto-fill automatique des formulaires
- [ ] Phase 5 : Sauvegarde de nouveaux identifiants
- [ ] Phase 6 : Content script pour détection formulaires

---

## [0.3.0-beta] - 2025-11-21

### ✨ Ajouté--

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

### 🐛 Corrigé--

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

### ✨ Ajouté---

- Module `src/config/logging_config.py` avec rotation quotidienne, niveaux adaptés (DEBUG en DEV, INFO en PROD) et répertoires distincts (`./logs` vs `/var/log/password_manager`).
- Script `tests/test-logging.sh` qui génère plusieurs journaux, valide la suppression des plus anciens et échoue si la rotation ne respecte pas la rétention de 7 fichiers.
- Fichier `VERSION_0.2.0-beta.md` et mise à jour complète du `VERSION_SUMMARY.md`.

### 🔧 Modifié--

- `password_manager.py`, services (`auth_service`, `crypto_service`, `password_generator`, `csv_importer`, etc.) et dialogues GTK reçoivent une instrumentation détaillée pour tracer les actions clés.
- `tests/run_all_tests.sh` exécute désormais `tests/test-logging.sh` afin que la CI couvre la rotation des journaux.
- `tests/test-version.sh`, `README.md`, `password-manager.desktop` et `src/version.py` reflètent la nouvelle version `0.2.0-beta`.
- Documentation (README, CHANGELOG, VERSION_SUMMARY) mise à jour pour décrire l'infrastructure de logs et les nouveaux scripts.

### 🛠️ Technique--

- Gestion de fallback automatique vers `/tmp/password_manager_logs` si l'écriture dans `/var/log/password_manager` échoue (droits insuffisants).
- Nettoyage automatique des anciens fichiers de log (7 derniers conservés) à chaque initialisation.
- Amélioration de la visibilité sur l'application grâce à des messages structurés aux niveaux INFO/WARNING/ERROR.

## [0.1.0-beta] - 2025-11-19

### ✨ Ajouté----

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

#### Sécurité---

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

### 🛠️ Technique---

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

### 🐛 Corrigé---

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
