# Scripts

Ce dossier contient les scripts utilitaires opérationnels du projet. Ils doivent être lancés depuis la **racine du projet**.

## Scripts de migration

| Script | Description |
|---|---|
| `migrate_to_email_2fa.py` | Migration vers Email + TOTP + UUID (exécuté automatiquement par `update.sh`) |
| `rollback_migration.py` | Rollback de la migration depuis un backup |

### Usage

```bash
# Migration (depuis la racine)
./scripts/migrate_to_email_2fa.py --data-dir ./data

# Rollback
./scripts/rollback_migration.py \
    --data-dir ./data \
    --backup ./data/backup_pre_migration_TIMESTAMP
```

## Scripts de développement / test

| Script | Description |
|---|---|
| `test-app.sh` | Tests complets de l'application (syntaxe, imports, unitaires) |
| `run-security-tests.sh` | Tests de sécurité (mode DEV obligatoire) |
| `backup-prod-before-tests.sh` | Backup de sécurité des données de production avant tests |

### Usage

```bash
# Tests complets
./scripts/test-app.sh

# Lancer l'application directement (raccourci)
./scripts/test-app.sh run

# Tests de sécurité
./scripts/run-security-tests.sh

# Backup prod avant tests
sudo ./scripts/backup-prod-before-tests.sh
```

## Scripts d'administration

| Script | Description |
|---|---|
| `fix-permissions.sh` | Répare les permissions et ACL de `/var/lib/heelonvault-shared` |

### Usage

```bash
sudo ./scripts/fix-permissions.sh
```
