# 📋 Résumé des Versions

## 🎉 Version 0.4.0-beta - Intégration Firefox

### 🚀 Release du 3 décembre 2025

**Intégration complète avec Firefox** via extension navigateur et Native Messaging Host.

#### Nouveautés principales

- 🦊 **Extension Firefox** (DEV & PROD) avec popup interactif
- 🔌 **Native Messaging Host** : Communication bidirectionnelle sécurisée
- 🎯 **Filtrage intelligent par URL** : Affichage contextuel des identifiants
- 🛠️ **15+ scripts** d'installation et de test
- 📚 **10+ documents** de configuration et debugging
- 🧪 **9 tests validés** : Communication + filtrage URL

#### Fichiers clés

- `browser_integration/firefox_extension_dev/` - Extension DEV avec badge "DEV"
- `browser_integration/firefox_extension/` - Extension PROD
- `browser_integration/native_host.py` - Host de communication
- `docs/VERSION_0.4.0-beta.md` - Documentation complète

#### Limitations

- ⏳ Récupération des mots de passe (décryption à implémenter)
- ⏳ Auto-fill automatique des formulaires
- ⏳ Sauvegarde de nouveaux identifiants

---

## 🎉 Version 0.3.0-beta - Sauvegardes Automatiques

### 🚀 Release du 21 novembre 2025

**Gestion complète des sauvegardes** avec rotation automatique et interface dédiée.

---

## 🎉 Version 0.2.0-beta - Système de Logs

### 🚀 Release du 20 novembre 2025

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
