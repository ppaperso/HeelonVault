# Guide de Mise à Jour en Production

## 🔄 Mise à Jour Sécurisée avec update.sh

Le script `update.sh` est conçu pour mettre à jour l'application en production de manière **sécurisée** avec **backup automatique complet en tar.gz**.

### ✨ Fonctionnalités

- ✅ **Backup tar.gz complet** (application + données)
- ✅ **Détection automatique de la source** (workspace local)
- ✅ **Analyse des fichiers modifiés** avec rsync
- ✅ **Détection de version** automatique
- ✅ **Liste des changements** avant validation
- ✅ **Validation en 2 étapes** (aperçu puis confirmation)
- ✅ **Arrêt propre** de l'application en cours
- ✅ **Mise à jour de l'environnement virtuel**
- ✅ **Mise à jour des permissions** (compatibilité 0.3.0-beta)
- ✅ **Instructions de rollback** en cas de problème
- ✅ **Rotation des backups** (conservation des 10 plus récents)

### 📋 Prérequis

1. L'application doit être déjà installée via `install.sh`
2. Vous devez avoir les droits sudo
3. Le code source de la nouvelle version (workspace local)

### 🚀 Procédure de Mise à Jour

#### 1. Se Placer dans le Dossier Source

```bash
cd /chemin/vers/Gestionnaire_mot_passe
# Par exemple: cd ~/Vscode/Gestionnaire_mot_passe
```

**Important** : Le script détecte automatiquement le dossier source où il se trouve. Pas besoin de git clone si vous développez en local.

#### 2. Lancer le Script de Mise à Jour

```bash
sudo bash update.sh
```

#### 3. Suivre les Étapes Interactives

Le script va procéder en **12 étapes** avec validation utilisateur :

##### Étape 1-2 : Vérifications et Détection de Versions

```text
🔍 Vérifications préliminaires
✅ Droits administrateur vérifiés
✅ Application installée détectée
✅ Répertoire de données présent
✅ Dossier source valide

📊 Détection des versions
Version actuelle: 0.2.0-beta
Nouvelle version: 0.3.0-beta
```

##### Étape 3 : Analyse des Fichiers Modifiés

```text
🔍 Analyse des fichiers à mettre à jour
📊 Analyse des différences entre:
   Source: /home/user/Vscode/Gestionnaire_mot_passe
   Cible:  /opt/password-manager

📋 Résumé des changements:
   • Fichiers à mettre à jour: 12
   • Fichiers à supprimer: 1
   • Nouveaux répertoires: 2

📝 Détails des modifications:
Fichiers modifiés/nouveaux:
   ✏️  password_manager.py
   ✏️  src/services/backup_service.py
   ✏️  src/ui/dialogs/backup_manager_dialog.py
   ...

Fichiers à supprimer:
   🗑️  old_file.py
```

##### Étape 4 : Première Validation

```text
⚠️  ATTENTION: Une mise à jour va être effectuée

   1. Un backup complet sera créé en tar.gz
   2. Les fichiers listés ci-dessus seront mis à jour
   3. L'environnement virtuel Python sera recréé
   4. Les permissions seront mises à jour

Voulez-vous effectuer la mise à jour? [o/N]
```

##### Étape 5 : Création du Backup

```text
💾 Création du backup complet
💾 Création du backup complet en tar.gz...
   📦 Fichier: password-manager_0.2.0-beta_20251121_150000.tar.gz
   📊 Taille du dossier d'installation: 45M
   🔄 Compression en cours...
   ✅ Backup créé avec succès
   📦 Taille du backup: 12M
   📂 Emplacement: /var/backups/password-manager/password-manager_0.2.0-beta_20251121_150000.tar.gz
   🔍 Vérification de l'intégrité...
   ✅ Intégrité vérifiée

✅ Backup créé avec succès!

Continuer avec la mise à jour? [o/N]
```

##### Étapes 6-11 : Mise à Jour Automatique

```text
⏹️  Arrêt de l'application
   ✅ Processus arrêté via pkill

🔄 Application de la mise à jour
   📂 Copie des fichiers...
   ✅ Fichiers copiés avec succès

🐍 Environnement virtuel Python
   🗑️  Suppression de l'ancien venv...
   🔧 Création du nouveau venv...
   📦 Installation des dépendances...
   ✅ Dépendances installées

🔐 Permissions
   ✅ Permissions mises à jour

🗑️  Nettoyage
   🗑️  Nettoyage des anciens backups (conservation des 10 plus récents)...
   ✅ Nettoyage effectué

✅ Vérification finale
   ✅ Version correctement installée: 0.3.0-beta
   ✅ Fichiers de données présents: 42
```

##### Étape 12 : Résumé Final

```text
╔══════════════════════════════════════════════════════════════╗
║             ✅ MISE À JOUR RÉUSSIE !                         ║
╚══════════════════════════════════════════════════════════════╝

📊 Résumé de la mise à jour:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Version précédente    : 0.2.0-beta
  Version installée     : 0.3.0-beta
  Backup créé           : password-manager_0.2.0-beta_20251121_150000.tar.gz
  Emplacement           : /var/backups/password-manager/password-manager_0.2.0-beta_20251121_150000.tar.gz
  Logs                  : /tmp/update-password-manager.log

🎯 L'application peut maintenant être relancée:
   • Via le menu Applications
   • Ou avec: /opt/password-manager/run.sh

💾 En cas de problème, restaurez le backup:
   sudo pkill -f password_manager.py
   sudo rm -rf /opt/password-manager
   sudo mkdir -p /opt/password-manager
   sudo tar -xzf /var/backups/password-manager/password-manager_0.2.0-beta_20251121_150000.tar.gz -C /
```

## 🔒 Sécurité des Données

### Protection Maximale

Le script `update.sh` garantit la sécurité de vos données :

1. **Backup COMPLET en tar.gz** avant toute modification
   - Application complète (`/opt/password-manager`)
   - Toutes les données (`/var/lib/password-manager-shared`)
   - Bases de données (`.db`)
   - Sels de chiffrement (`salt_*.bin`)
   - Sauvegardes existantes
   - Format compressé (gain d'espace ~70%)

2. **Vérification d'intégrité**
   - Test de l'archive tar.gz après création
   - Vérification du nombre de fichiers de données avant/après
   - Contrôle de la version installée
   - Arrêt immédiat si anomalie détectée

3. **Analyse intelligente des changements**
   - Utilise `rsync` en mode dry-run
   - Liste précise des fichiers modifiés/ajoutés/supprimés
   - Exclusion automatique des fichiers temporaires
   - Validation utilisateur avant application

4. **Exclusions automatiques**
   - `venv/` et `venv-dev/` (environnements virtuels)
   - `__pycache__/` et `*.pyc` (fichiers compilés)
   - `.git/` (historique git)
   - `tests/` et `export-csv/` (développement)
   - Fichiers de logs

### Format du Backup

```text
/var/backups/password-manager/
├── password-manager_0.2.0-beta_20251121_150000.tar.gz  (12M)
├── password-manager_0.2.0-beta_20251120_143000.tar.gz  (11M)
├── password-manager_0.1.0-beta_20251115_090000.tar.gz  (9M)
└── ... (jusqu'à 10 backups conservés)
```

**Contenu de l'archive tar.gz** :

```text
password-manager_0.2.0-beta_20251121_150000.tar.gz
├── opt/password-manager/           # Application complète
│   ├── password_manager.py
│   ├── src/
│   ├── requirements.txt
│   └── ... (sans venv/)
└── var/lib/password-manager-shared/  # Données complètes
    ├── users.db
    ├── passwords_admin.db
    ├── passwords_user1.db
    ├── salt_admin.bin
    ├── salt_user1.bin
    └── backups/
```

## 🔄 Restauration en Cas de Problème

### Restauration Complète depuis tar.gz

Si la mise à jour pose problème, la restauration est **ultra simple** :

```bash
# 1. Arrêter l'application
sudo pkill -f password_manager.py

# 2. Supprimer l'installation corrompue
sudo rm -rf /opt/password-manager

# 3. Recréer le dossier
sudo mkdir -p /opt/password-manager

# 4. Extraire le backup (restaure TOUT en une commande)
sudo tar -xzf /var/backups/password-manager/password-manager_VERSION_TIMESTAMP.tar.gz -C /

# 5. Recréer le venv
cd /opt/password-manager
sudo python3 -m venv --system-site-packages venv
sudo venv/bin/pip install -r requirements.txt

# 6. Relancer l'application
/opt/password-manager/run.sh
```

### Lister les Backups Disponibles

```bash
ls -lth /var/backups/password-manager/
```

**Exemple de sortie** :

```text
-rw-r--r-- 1 root root  12M nov. 21 15:00 password-manager_0.2.0-beta_20251121_150000.tar.gz
-rw-r--r-- 1 root root  11M nov. 20 14:30 password-manager_0.2.0-beta_20251120_143000.tar.gz
-rw-r--r-- 1 root root  9.5M nov. 15 09:00 password-manager_0.1.0-beta_20251115_090000.tar.gz
```

### Vérifier le Contenu d'un Backup

```bash
# Lister le contenu sans extraire
tar -tzf /var/backups/password-manager/password-manager_VERSION_TIMESTAMP.tar.gz | head -20

# Vérifier l'intégrité
tar -tzf /var/backups/password-manager/password-manager_VERSION_TIMESTAMP.tar.gz > /dev/null && echo "✅ Archive intègre"
```

## 📝 Logs et Diagnostic

### Fichiers de Log

- **Log d'installation** : `/tmp/update-password-manager.log`
- Contient toutes les opérations effectuées
- Conservé après la mise à jour
- Consulter en cas d'erreur

### Commandes de Diagnostic

```bash
# Vérifier la version installée
python3 -c "import sys; sys.path.insert(0, '/opt/password-manager'); from src.version import __version__; print(__version__)"

# Lister les backups disponibles
ls -lth /var/backups/password-manager/

# Compter les fichiers de données
find /var/lib/password-manager-shared -type f | wc -l

# Vérifier l'espace disque
df -h /var/backups

# Tester l'intégrité d'un backup
tar -tzf /var/backups/password-manager/password-manager_*.tar.gz > /dev/null && echo "✅ OK"
```

## 🚫 Ce Qu'il NE FAUT PAS Faire

### ❌ N'utilisez PAS install.sh pour une mise à jour

Le script `install.sh` va **écraser** l'installation sans backup automatique !

```bash
# ❌ MAUVAIS - Pas de backup automatique
cd /nouvelle/version
sudo bash install.sh

# ✅ BON - Backup automatique en tar.gz
cd /nouvelle/version
sudo bash update.sh
```

### ❌ Ne lancez pas update.sh depuis n'importe où

Le script doit être lancé **depuis le dossier source** de la nouvelle version :

```bash
# ❌ MAUVAIS
cd /tmp
sudo bash /opt/password-manager/update.sh

# ✅ BON
cd ~/Vscode/Gestionnaire_mot_passe  # ou le chemin vers votre code
sudo bash update.sh
```

### ❌ Ne modifiez pas les données pendant la mise à jour

- Fermez l'application avant la mise à jour
- N'accédez pas à `/var/lib/password-manager-shared/` pendant le processus
- Attendez la fin complète du script

### ❌ Ne supprimez pas les backups manuellement

- Le script gère automatiquement la rotation (10 backups max)
- Les backups tar.gz sont précieux pour le rollback
- Ils prennent peu de place grâce à la compression

## 🔧 Différences install.sh vs update.sh

| Aspect | install.sh | update.sh |
| ------ | ---------- | --------- |
| **Usage** | Installation initiale | Mise à jour existante |
| **Source** | Clone git + copie | Copie locale directe |
| **Backup automatique** | ❌ Non | ✅ Oui (tar.gz complet) |
| **Analyse des changements** | ❌ Non | ✅ Oui (rsync diff) |
| **Validation utilisateur** | Basique | 2 étapes (aperçu + confirmation) |
| **Détection de version** | ❌ Non | ✅ Oui (comparaison) |
| **Préservation des données** | ⚠️ Risque écrasement | ✅ Garantie (backup) |
| **Rollback** | Manuel complexe | Simple (tar -xzf) |
| **Vérification post-update** | Basique | Complète (version + fichiers) |
| **Rotation des backups** | ❌ N/A | ✅ 10 backups max |
| **Logs détaillés** | Oui | Oui + rsync diff |

## 💡 Bonnes Pratiques

### Avant la Mise à Jour

1. **Vérifier l'espace disque** disponible pour les backups

   ```bash
   df -h /var/backups
   # Au minimum : 2x la taille de /opt/password-manager
   ```

2. **Noter la version actuelle**

   ```bash
   python3 -c "import sys; sys.path.insert(0, '/opt/password-manager'); from src.version import __version__; print(__version__)"
   ```

3. **Se placer dans le bon dossier**

   ```bash
   cd ~/Vscode/Gestionnaire_mot_passe  # Dossier source avec la nouvelle version
   pwd  # Vérifier le chemin
   ```

4. **Tester en environnement de dev d'abord**
   - Créer une VM de test
   - Installer l'ancienne version
   - Tester le script update.sh

### Pendant la Mise à Jour

1. **Lire attentivement** l'analyse des fichiers modifiés
2. **Vérifier** que les changements correspondent à ce qui est attendu
3. **Confirmer** le backup tar.gz créé avant de continuer
4. **Ne pas interrompre** le processus (pas de Ctrl+C)
5. **Attendre** la fin complète des 12 étapes

### Après la Mise à Jour

1. **Tester l'application immédiatement**

   ```bash
   /opt/password-manager/run.sh
   ```

2. **Vérifier les logs**

   ```bash
   tail -50 /tmp/update-password-manager.log
   ```

3. **Tester les fonctionnalités critiques**
   - Connexion utilisateur
   - Déchiffrement des mots de passe
   - Ajout/modification d'entrée
   - Export CSV
   - Backup manuel

4. **Vérifier le backup créé**

   ```bash
   ls -lh /var/backups/password-manager/*.tar.gz | head -1
   tar -tzf /var/backups/password-manager/password-manager_*.tar.gz | wc -l
   ```

5. **Conserver le backup** quelques jours avant nettoyage manuel (si besoin)

## 📞 Support

En cas de problème :

1. Consulter `/tmp/update-password-manager.log`
2. Vérifier le MANIFEST du backup
3. Tester la restauration sur une copie
4. Contacter le support avec les logs

## 🔄 Rotation des Backups

Le script conserve automatiquement les **10 backups les plus récents**.

Pour modifier ce nombre, éditez `update.sh` :

```bash
# Ligne à modifier (vers la fin du script)
ls -t | tail -n +11 | xargs -r rm -rf  # 11 = garder 10 backups
```

## ✅ Checklist de Mise à Jour

### Préparation

- [ ] Espace disque vérifié (`df -h /var/backups`)
- [ ] Version actuelle notée
- [ ] Code source de la nouvelle version téléchargé
- [ ] Se placer dans le dossier source (`cd ~/Vscode/Gestionnaire_mot_passe`)
- [ ] Version testée en dev (recommandé)

### Exécution

- [ ] Lancer `sudo bash update.sh`
- [ ] Vérifier l'analyse des fichiers modifiés
- [ ] Confirmer la première validation
- [ ] Vérifier le backup tar.gz créé
- [ ] Confirmer la deuxième validation
- [ ] Attendre la fin des 12 étapes

### Vérification

- [ ] Application relancée avec succès
- [ ] Version correcte installée
- [ ] Connexion utilisateur fonctionnelle
- [ ] Déchiffrement des mots de passe OK
- [ ] Ajout/modification d'entrée OK
- [ ] Backup manuel dans l'interface OK
- [ ] Logs vérifiés (`/tmp/update-password-manager.log`)
- [ ] Backup tar.gz présent et intègre

### En Cas de Problème

- [ ] Consulter `/tmp/update-password-manager.log`
- [ ] Identifier le backup à restaurer
- [ ] Suivre la procédure de rollback
- [ ] Vérifier l'intégrité après restauration

---

## 📚 Résumé des Commandes Clés

```bash
# Mise à jour complète (depuis le dossier source)
cd ~/Vscode/Gestionnaire_mot_passe
sudo bash update.sh

# Lister les backups
ls -lth /var/backups/password-manager/

# Vérifier un backup
tar -tzf /var/backups/password-manager/password-manager_*.tar.gz > /dev/null && echo "✅ OK"

# Restaurer un backup
sudo pkill -f password_manager.py
sudo rm -rf /opt/password-manager
sudo mkdir -p /opt/password-manager
sudo tar -xzf /var/backups/password-manager/password-manager_VERSION_TIMESTAMP.tar.gz -C /
cd /opt/password-manager
sudo python3 -m venv --system-site-packages venv
sudo venv/bin/pip install -r requirements.txt

# Vérifier la version installée
python3 -c "import sys; sys.path.insert(0, '/opt/password-manager'); from src.version import __version__; print(__version__)"

# Consulter les logs
tail -100 /tmp/update-password-manager.log
```

---

**Version du guide** : 0.3.0-beta  
**Dernière mise à jour** : 21 novembre 2025  
**Compatibilité** : update.sh v2.0 (backup tar.gz)
