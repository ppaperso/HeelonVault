# 🚀 Guide de Migration - Email + TOTP + UUID

**Version** : 1.0  
**Date** : 2 mars 2026  
**Migration** : `email_totp_uuid_v1`

---

## 📋 Vue d'ensemble

Cette migration transforme le système d'authentification :

| Avant | Après |
| ------- | -------- |
| Username comme identifiant | **Email** comme identifiant |
| Pas de 2FA | **TOTP obligatoire** (Google Authenticator, etc.) |
| Fichiers `passwords_{username}.db` | Fichiers `passwords_{uuid}.db` |
| Email hash simple | **HMAC-SHA256 avec pepper** (privacy) |
| Rate limiting basique | **Rate limiting global** (5/min, 30/h) |

---

## ⚙️ Prérequis

### 1. Environnement de développement

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Installer les nouvelles dépendances
pip install -r requirements.txt

# Vérifier l'installation
python3 -c "import pyotp, qrcode, validators; print('✅ Dépendances OK')"
```

### 2. Backup avant tout

**🔴 CRITIQUE : Ne jamais tester sur les données de production !**

```bash
# Copier les données de production vers data/ pour les tests
mkdir -p data
cp /var/lib/heelonvault-shared/users.db data/
cp /var/lib/heelonvault-shared/passwords_*.db data/ 2>/dev/null || true
cp /var/lib/heelonvault-shared/salt_*.bin data/ 2>/dev/null || true
```

---

## 🧪 Phase 1 : Tests en environnement de développement

### Étape 1.1 : Exécuter la migration

```bash
# Dans le .venv
./scripts/migrate_to_email_2fa.py --data-dir ./data

# Sortie attendue :
# ======================================================================
# DÉBUT DE LA MIGRATION : Email + TOTP + UUID
# ======================================================================
# ✅ Backup créé : ./data/backup_pre_migration_20260302_HHMMSS
# Migration de 3 utilisateur(s)...
#   ✅ admin → UUID: 1234abcd... | Email: admin@migration.local
#   ✅ alice → UUID: 5678efgh... | Email: alice@migration.local
#   ✅ bob → UUID: 9012ijkl... | Email: bob@migration.local
# ✅ Fichiers renommés avec succès
# ✅ MIGRATION TERMINÉE AVEC SUCCÈS
```

### Étape 1.2 : Vérifier la base de données

```bash
sqlite3 data/users.db

# Vérifier les nouvelles colonnes
.schema users

# Lister les utilisateurs migrés
SELECT username, email, workspace_uuid, totp_enabled FROM users;

# Vérifier le statut de migration
SELECT * FROM migration_status;

.quit
```

### Étape 1.3 : Vérifier les fichiers renommés

```bash
# Lister les fichiers
ls -lh data/

# Vérifier que les fichiers UUID existent
# ✅ passwords_<UUID>.db
# ✅ salt_<UUID>.bin
# ✅ .app_key (clé système pour TOTP)
# ✅ .email_pepper (pepper pour hash email)
```

### Étape 1.4 : Tester l'application

```bash
# Lancer en mode développement
./run-dev.sh

# OU directement
python3 password_manager.py
```

#### Tests à effectuer

1. **✅ Login avec email temporaire**
   - Saisir : `admin@migration.local`
   - Mot de passe : `admin` (ou celui configuré)
   - **Attendu** : Dialog "Mise à jour de l'email"

2. **✅ Mise à jour de l'email**
   - Saisir un email valide : `admin@example.com`
   - **Attendu** : Email mis à jour, passage au setup 2FA

3. **✅ Configuration 2FA obligatoire**
   - Scanner le QR code avec Google Authenticator
   - Entrer le code à 6 chiffres
   - **Attendu** : Codes de secours affichés (10 codes)

4. **✅ Confirmation des codes de secours**
   - Cocher "J'ai sauvegardé ces codes"
   - Cliquer "Terminer"
   - **Attendu** : Accès au workspace

5. **✅ Déconnexion et reconnexion**
   - Se déconnecter
   - Saisir : `admin@example.com` + mot de passe
   - **Attendu** : Dialog de vérification TOTP
   - Entrer le code à 6 chiffres
   - **Attendu** : Accès au workspace

6. **✅ Test du code de secours**
   - Se déconnecter
   - Se connecter avec email + mot de passe
   - Cliquer "Utiliser un code de secours"
   - Entrer un des 10 codes sauvegardés
   - **Attendu** : Accès au workspace, code marqué comme utilisé

7. **✅ Test du rate limiting**
   - Se déconnecter
   - Essayer 6 fois avec un mauvais mot de passe
   - **Attendu** : Message "Trop de tentatives, attendez X minutes"

8. **✅ Accès aux mots de passe**
   - Vérifier que tous les mots de passe sont accessibles
   - Ajouter un nouveau mot de passe
   - Modifier un mot de passe existant
   - **Attendu** : Tout fonctionne normalement

---

## 🔄 Phase 2 : Rollback (en cas de problème)

### Option A : Rollback manuel

```bash
# Restaurer depuis le backup
./scripts/rollback_migration.py \
    --data-dir ./data \
    --backup ./data/backup_pre_migration_TIMESTAMP

# Ou depuis le .tar.gz
./scripts/rollback_migration.py \
    --data-dir ./data \
    --backup ./data/backup_pre_migration_TIMESTAMP.tar.gz
```

### Option B : Restauration manuelle

```bash
# 1. Supprimer users.db actuel
rm data/users.db

# 2. Restaurer depuis le backup
cp data/backup_pre_migration_TIMESTAMP/users.db data/

# 3. Restaurer les fichiers de workspace
cp data/backup_pre_migration_TIMESTAMP/passwords_*.db data/
cp data/backup_pre_migration_TIMESTAMP/salt_*.bin data/

# 4. Supprimer les fichiers UUID créés
rm data/passwords_*-*-*-*.db  # UUID format
rm data/salt_*-*-*-*.bin
```

---

## 🚀 Phase 3 : Déploiement en production

**⚠️  SEULEMENT APRÈS VALIDATION COMPLÈTE EN DEV !**

### Étape 3.1 : Communication aux utilisateurs

**📧 Email aux utilisateurs (à envoyer AVANT la migration) :**

```text
Objet : Mise à jour de sécurité - Action requise

Chers utilisateurs,

Une mise à jour majeure de sécurité sera déployée le [DATE].

Changements :
✅ Connexion par email (plus besoin de retenir un username)
✅ Double authentification obligatoire (2FA)
✅ Sécurité renforcée

Actions requises à la première connexion :
1. Fournir votre adresse email
2. Installer une app d'authentification (Google Authenticator, Authy, etc.)
3. Scanner le QR code affiché
4. Sauvegarder vos 10 codes de secours

Durée estimée : 5 minutes

Merci de votre coopération.
```

### Étape 3.2 : Planification

```text
Fenêtre de maintenance : [DATE] de [HEURE DÉBUT] à [HEURE FIN]
Durée estimée : 30 minutes
Plan de rollback : Prêt (backup automatique)
```

### Étape 3.3 : Exécution

```bash
# 1. Arrêter l'application (si elle tourne)
sudo systemctl stop heelonvault  # Si service systemd
# OU
pkill -f heelonvault.py

# 2. Backup complet manuel (sécurité supplémentaire)
sudo cp -r /var/lib/heelonvault-shared /var/backups/manual_backup_$(date +%Y%m%d)

# 3. Exécuter la migration
cd /opt/heelonvault
source venv/bin/activate
./scripts/migrate_to_email_2fa.py --data-dir /var/lib/heelonvault-shared

# 4. Vérifier le succès
# ✅ Backup créé automatiquement
# ✅ Migration terminée avec succès
# ✅ Tous les tests de validation passés

# 5. Relancer l'application
sudo systemctl start heelonvault
# OU
./run.sh
```

### Étape 3.4 : Vérification post-migration

```bash
# Vérifier les logs
tail -f /var/log/password-manager/app.log

# Vérifier la base de données
sqlite3 /var/lib/password-manager-shared/users.db \
    "SELECT COUNT(*) FROM users WHERE email_hash IS NOT NULL;"
# Doit retourner le nombre total d'utilisateurs

# Vérifier les fichiers
ls -lh /var/lib/password-manager-shared/
# Doit contenir passwords_<UUID>.db au lieu de passwords_<username>.db
```

---

## 🐛 Troubleshooting

### Problème 1 : "Migration already applied"

**Symptôme** : Le script dit que la migration est déjà appliquée

**Solution** :

```bash
sqlite3 data/users.db "SELECT * FROM migration_status;"
# Si status='in_progress' → Migration interrompue, restaurer depuis backup
# Si status='completed' → Migration déjà faite, pas besoin de relancer
```

### Problème 2 : "Fichier UUID manquant"

**Symptôme** : Erreur lors de l'accès aux mots de passe

**Cause** : Fichier `passwords_{uuid}.db` introuvable

**Solution** :

```bash
# Vérifier les correspondances
sqlite3 data/users.db \
    "SELECT username, workspace_uuid FROM users;"

# Vérifier que les fichiers existent
ls -lh data/passwords_*.db
```

### Problème 3 : "Secret TOTP introuvable"

**Symptôme** : Erreur lors de la vérification 2FA

**Cause** : Fichier `.app_key` manquant ou corrompu

**Solution** :

```bash
# Vérifier la présence de .app_key
ls -la data/.app_key

# Si manquant, le TOTPService le regénérera
# MAIS les secrets TOTP existants seront invalides
# → Nécessite re-configuration 2FA pour tous les utilisateurs
```

### Problème 4 : "Trop de tentatives"

**Symptôme** : Utilisateur bloqué après 5 échecs

**Solution** :

```python
# En développement, réinitialiser le tracker
python3
>>> from src.services.login_attempt_tracker import LoginAttemptTracker
>>> tracker = LoginAttemptTracker()
>>> tracker.clear_all_attempts()
>>> print("✅ Compteurs réinitialisés")
```

### Problème 5 : QR code ne s'affiche pas

**Symptôme** : Dialog 2FA sans QR code

**Cause** : Dépendance `qrcode[pil]` manquante

**Solution** :

```bash
pip install --upgrade qrcode[pil] Pillow
```

---

## 📊 Métriques de succès

### Avant migration

- [ ] Backup complet créé
- [ ] Tests en dev réussis (100%)
- [ ] Utilisateurs informés

### Pendant migration

- [ ] Migration complétée sans erreur
- [ ] Tous les fichiers renommés
- [ ] Base de données validée

### Après migration

- [ ] Tous les utilisateurs peuvent se connecter
- [ ] 2FA fonctionne pour tous
- [ ] Accès aux mots de passe OK
- [ ] Aucune perte de données

---

## 🔒 Sécurité post-migration

### Nouveaux fichiers sensibles

| Fichier | Description | Permissions |
| --------- | ------------- | ------------- |
| `.app_key` | Clé système pour chiffrement TOTP | `600` |
| `.email_pepper` | Pepper pour hash HMAC des emails | `600` |
| `.machine_id_fallback` | ID machine (si /etc/machine-id absent) | `600` |

**⚠️  NE JAMAIS supprimer ces fichiers ! Perte d'accès aux secrets TOTP.**

### Recommandations

1. **Backup réguliers** : Inclure `.app_key` et `.email_pepper` dans les backups
2. **Surveillance** : Logger les tentatives de connexion échouées
3. **Support utilisateur** : Prévoir un process pour reset 2FA (admin uniquement)
4. **Documentation** : Mettre à jour les procédures internes

---

## 📝 Checklist finale

### Pré-migration

- [ ] Dépendances installées (`pyotp`, `qrcode`, `validators`)
- [ ] Tests en dev réussis (100%)
- [ ] Backup manuel créé
- [ ] Utilisateurs informés
- [ ] Fenêtre de maintenance planifiée
- [ ] Plan de rollback vérifié

### Migration

- [ ] Application arrêtée
- [ ] Script de migration exécuté
- [ ] Logs vérifiés (pas d'erreur)
- [ ] Base de données validée
- [ ] Fichiers renommés vérifiés

### Post-migration

- [ ] Application redémarrée
- [ ] Test de connexion admin OK
- [ ] Test 2FA OK
- [ ] Test code de secours OK
- [ ] Tous les utilisateurs notifiés
- [ ] Documentation mise à jour

---

## 🆘 Support

En cas de problème critique lors de la migration en production :

1. **Arrêter la migration immédiatement**
2. **Exécuter le rollback** : `./scripts/rollback_migration.py`
3. **Restaurer le service** : `systemctl start heelonvault`
4. **Analyser les logs** : `/var/log/heelonvault/app.log`
5. **Contacter l'équipe technique**

---

## 📚 Références

- RFC 6238 : TOTP (Time-Based One-Time Password)
- OWASP : Protection contre le brute force
- NIST : Recommandations 2FA

---

Bonne migration ! 🚀
