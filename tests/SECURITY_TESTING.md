# Sécurité des Tests - Guide de Développement

## ⚠️ RÈGLE CRITIQUE DE SÉCURITÉ

**TOUS les scripts de test DOIVENT définir `export DEV_MODE=1` au début.**

Cette règle garantit que les tests n'accèdent JAMAIS aux données de production.

## Séparation des Environnements

### Environnement de Développement
- **Variable**: `DEV_MODE=1`
- **Répertoire de données**: `src/data/`
- **Venv**: `venv-dev/`
- **Usage**: Tests, développement, expérimentation

### Environnement de Production
- **Variable**: `DEV_MODE=0` ou non définie
- **Répertoire de données**: `/var/lib/password-manager-shared/`
- **Venv**: `venv/`
- **Usage**: Application en production

## Scripts de Test Sécurisés

Tous les scripts de test ont été sécurisés avec la bannière suivante :

```bash
#!/bin/bash

# ⚠️ SÉCURITÉ: Forcer le mode développement pour les tests
export DEV_MODE=1

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS SUR ENVIRONNEMENT DE DÉVELOPPEMENT    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔒 Mode DEV activé: DEV_MODE=$DEV_MODE"
echo "📂 Données de test: src/data/"
echo "⚠️  Les données de production ne seront PAS touchées"
echo ""
```

### Scripts Sécurisés

1. **test-app.sh** - Script principal de test
2. **tests/test-data-protection.sh** - Tests de protection des données
3. **tests/run_all_tests.sh** - Tous les tests d'intégration
4. **tests/test-import-csv.sh** - Tests d'import CSV
5. **tests/test-version.sh** - Tests de versioning
6. **tests/test_no_deprecation.sh** - Tests de dépréciation
7. **tests/test-logging.sh** - Tests de logging

## Tests Unitaires Python

Les tests unitaires Python sont automatiquement sûrs car ils utilisent :
- `tempfile.mkdtemp()` pour créer des répertoires temporaires
- Des bases de données en mémoire ou temporaires
- Pas d'accès au système de fichiers de production

### Exemples de Tests Sûrs

```python
import tempfile
from pathlib import Path

class TestBackupService(unittest.TestCase):
    def setUp(self):
        # Utilise un répertoire temporaire
        self.test_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.test_dir) / "data"
        self.data_dir.mkdir()
```

## Vérification de l'Environnement

### Vérifier le Mode Actif

```bash
echo "Mode: $DEV_MODE"
python3 -c "from src.config.environment import is_dev_mode, get_data_directory; print(f'Dev mode: {is_dev_mode()}, Data dir: {get_data_directory()}')"
```

### Sortie Attendue en Mode DEV

```
Dev mode: True, Data dir: /path/to/project/src/data
```

### Sortie en Mode Production

```
Dev mode: False, Data dir: /var/lib/password-manager-shared
```

## Checklist pour Nouveaux Tests

Avant d'ajouter un nouveau script de test :

- [ ] Ajouter `export DEV_MODE=1` au début du script
- [ ] Ajouter la bannière de sécurité
- [ ] Vérifier que le script utilise `venv-dev/` et non `venv/`
- [ ] Tester que les données sont écrites dans `src/data/`
- [ ] Vérifier qu'aucun fichier de production n'est touché

## Que Faire en Cas d'Erreur

Si un test accède accidentellement aux données de production :

1. **ARRÊTER immédiatement le test**
2. Vérifier l'intégrité des données de production
3. Ajouter `export DEV_MODE=1` au script
4. Restaurer les sauvegardes si nécessaire
5. Re-tester en mode DEV

## Responsabilités

### Développeurs
- Toujours définir `DEV_MODE=1` dans les scripts de test
- Ne jamais tester directement sur les données de production
- Vérifier l'environnement avant de lancer les tests

### Reviewers
- Vérifier la présence de `export DEV_MODE=1`
- Vérifier l'utilisation de `venv-dev/`
- S'assurer que les tests n'accèdent pas à `/var/lib/password-manager-shared/`

## Résumé

**Règle d'Or** : Si vous voyez `/var/lib/password-manager-shared/` dans un test, c'est une erreur critique !

**Toujours utiliser** : `src/data/` pour les tests.
