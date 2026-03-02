# ⚡ Quick Start - Migration Email + TOTP + UUID

## 🚀 Installation des dépendances

```bash
source venv-dev/bin/activate
pip install -r requirements.txt
```

## 🧪 Test de la migration (DEV)

```bash
# 1. Copier les données de prod vers data/ (ou utiliser données de test)
mkdir -p data
cp /path/to/users.db data/

# 2. Exécuter la migration
./scripts/migrate_to_email_2fa.py --data-dir ./data

# 3. Vérifier
sqlite3 data/users.db "SELECT username, email, workspace_uuid FROM users;"

# 4. Tester l'application
./run-dev.sh
```

## 🔄 Rollback en cas de problème

```bash
./scripts/rollback_migration.py \
    --data-dir ./data \
    --backup ./data/backup_pre_migration_TIMESTAMP
```

## ✅ Checklist avant intégration

- [ ] Dépendances installées
- [ ] Migration testée en dev
- [ ] Dialogs UI fonctionnels
- [ ] **application.py modifié** (voir IMPLEMENTATION_STATUS.md)
- [ ] Tests complets réussis
- [ ] Documentation lue (MIGRATION_GUIDE.md)

## 📚 Documentation complète

- **MIGRATION_GUIDE.md** - Guide complet de migration et tests
- **IMPLEMENTATION_STATUS.md** - État détaillé de l'implémentation
- **ANALYSE_MIGRATION_EMAIL_2FA.md** - Analyse technique initiale

## ⚠️ Important

**NE PAS tester sur données de production !**  
Toujours utiliser `run-dev.sh` et le répertoire `./data/`

---

**Prochaine étape** : Modifier `application.py` selon les instructions dans `IMPLEMENTATION_STATUS.md` section "Ce qui reste à faire".
