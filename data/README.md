# 📂 Répertoire de données de développement

Ce répertoire contient les données de **développement et de test uniquement**.

## 🔐 Isolation Dev/Prod

L'application utilise deux répertoires distincts selon le mode :

| Mode | Variable | Emplacement | Usage |
|------|----------|-------------|-------|
| **DEV** | `DEV_MODE=1` | `./data/` | Développement et tests |
| **PROD** | (par défaut) | `/var/lib/password-manager-shared/` | Production |

## 🛡️ Sécurité

- ✅ Ce dossier est **ignoré par Git** (`.gitignore`)
- ✅ Les données de dev **ne polluent jamais la prod**
- ✅ Les données de prod **ne sont jamais modifiées en dev**
- ✅ Vous pouvez **supprimer `./data/`** sans risque

## 📦 Contenu

```
data/
├── users.db              # Comptes utilisateurs de test
├── passwords_*.db        # Mots de passe de test chiffrés
├── salt_*.bin           # Clés de chiffrement de test
└── security.log         # Logs de test
```

## 🚀 Utilisation

### Mode développement
```bash
./run-dev.sh              # Lance avec DEV_MODE=1 automatiquement
# OU
DEV_MODE=1 python3 password_manager.py
```

### Mode production
```bash
python3 password_manager.py    # Utilise /var/lib/password-manager-shared/
# OU via l'icône du menu Applications
```

## 🗑️ Réinitialiser les données de test

```bash
rm -rf data/
# Le dossier sera recréé au prochain lancement en mode dev
```

---

**⚠️ IMPORTANT** : Ne commitez JAMAIS ce dossier dans Git !
