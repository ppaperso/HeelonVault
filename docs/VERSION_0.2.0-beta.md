# Version 0.2.0-beta

## 🗓️ Date de sortie
20 novembre 2025

## ✨ Points forts
- **Nouveau système de logs** avec configuration centralisée, rotation automatique (7 jours) et séparation DEV/PROD
- **Instrumentation exhaustive** sur l'ensemble des services, dialogues et actions utilisateur pour faciliter le support
- **Script de validation `tests/test-logging.sh`** simulant plusieurs rotations et vérifiant le ménage automatique
- **Intégration CI** : `tests/run_all_tests.sh` exécute désormais le test de logging en plus des tests d'intégration
- **Rafraîchissement documentation** : changelog, badge README, fichier desktop, scripts de test et sommaire des versions

## 🔍 Détails techniques
### Logging
- Module `src/config/logging_config.py`
- Format unique : `password_manager_YYYYMMDD_HHMMSS.log`
- Niveaux adaptés (DEBUG en DEV, INFO en PROD)
- Gestion de repli `/tmp/password_manager_logs` si `/var/log` inaccessible

### Instrumentation
- `password_manager.py` trace chaque étape (démarrage, authentification, CRUD, dialogues)
- Services (`auth_service`, `crypto_service`, `password_generator`, `csv_importer`, `login_attempt_tracker`) publient des messages orientés diagnostic
- UI/Dialogs (import CSV, gestion utilisateurs, badges DEV, etc.) annoncent les actions clés

### Tests
- `tests/test-logging.sh` génère 9 journaux successifs, vérifie qu'il n'en reste que 7 et échoue si la rotation ne supprime pas les plus anciens
- `tests/run_all_tests.sh` appelle automatiquement ce script pour garantir la couverture
- `tests/test-version.sh` vérifie la nouvelle valeur `0.2.0-beta`

## 📦 Fichiers impactés
- `src/config/logging_config.py` (nouveau)
- `src/config/environment.py`, `password_manager.py` et services : instrumentation
- `README.md`, `CHANGELOG.md`, `password-manager.desktop`, `tests/test-version.sh`
- `VERSION_SUMMARY.md` + **ce fichier**

## ✅ Résumé
Cette version se concentre sur l'observabilité :
- Les journaux sont fiables, exploitables et nettoyés automatiquement
- Les diagnostics sont plus rapides grâce à des traces contextualisées
- Le comportement est vérifié automatiquement via le nouveau test dédié

**Bon débogage avec la version 0.2.0-beta ! 🔐**
