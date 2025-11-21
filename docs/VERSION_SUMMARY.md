# 🎉 Version 0.2.0-beta - Récapitulatif

## 🚀 Release du 20 novembre 2025

Cette version consolide toute l'infrastructure de logs et facilite le support en production :

- ✅ Nouveau module `src/config/logging_config.py`
- ✅ Rotation automatique (7 jours) + répertoires dédiés DEV/PROD
- ✅ Instrumentation détaillée dans les services, dialogues et UI
- ✅ Script automatisé `tests/test-logging.sh`
- ✅ Intégration du test de rotation dans `tests/run_all_tests.sh`

## 🆕 Ce qui change pour 0.2.0-beta

### 1. Journaux robustes
- Initialisation unique via `configure_logging()` (stdout + fichier horodaté)
- Répertoires séparés : `./logs/` en DEV, `/var/log/password_manager/` en PROD
- Gestion de repli vers `/tmp/password_manager_logs` en cas de permission refusée

### 2. Visibilité accrue
- Ajout de logs structurés dans :
  - `password_manager.py` (cycle de vie complet)
  - Services (`auth_service`, `crypto_service`, `login_attempt_tracker`, `password_generator`, `csv_importer`…)
  - Dialogues GTK (import CSV, gestion utilisateurs, etc.)
- Messages adaptés aux niveaux INFO/DEBUG/WARNING/ERROR

### 3. Tests dédiés
- `tests/test-logging.sh` génère 9 journaux et vérifie la rotation
- `tests/run_all_tests.sh` exécute désormais ce script après la suite d'intégration
- `tests/test-version.sh` attend la nouvelle version `0.2.0-beta`

### 4. Documentation & métadonnées
- `README.md` : badge mis à jour
- `CHANGELOG.md` : nouvelle section 0.2.0-beta
- `VERSION_0.2.0-beta.md` : notes de version détaillées
- `password-manager.desktop` : champ `Version` synchronisé

## 🧪 Tests

```bash
tests/run_all_tests.sh
# ▶️ ...
# ✅ logging rotation
# 🎉 Tous les tests ont réussi !
```

## 📁 Fichiers notables

- `src/version.py` → `__version__ = "0.2.0-beta"`
- `src/config/logging_config.py` (nouveau)
- `tests/test-logging.sh` (nouveau)
- `tests/run_all_tests.sh` (mise à jour)
- `README.md`, `CHANGELOG.md`, `password-manager.desktop`, `tests/test-version.sh`
- `VERSION_0.2.0-beta.md` (nouveau) + `VERSION_SUMMARY.md` (ce fichier)

## 🗺️ Rappel utilisation

```bash
python3 -c "from src.version import get_version; print(get_version())"
# 0.2.0-beta

./run-dev.sh
# Les premières lignes de logs confirment le mode + répertoire utilisés
```

## 🔭 Roadmap preview (0.3.0)

- Export CSV
- Détection de doublons à l'import
- Synchronisation optionnelle
- Support d'autres gestionnaires (KeePass, Dashlane)

---

**Profitez de la tranquillité d'esprit avec la version 0.2.0-beta ! 🔐**
