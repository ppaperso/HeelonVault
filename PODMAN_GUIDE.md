# 🐋 Guide de déploiement avec Podman

Ce guide détaille la conteneurisation de l'application avec Podman sur Fedora.

## 🎯 Pourquoi Podman + RHEL UBI ?

### Avantages de Podman
- **Sans daemon** : Plus sécurisé, pas de processus root permanent
- **Rootless** : Exécution en tant qu'utilisateur non-privilégié
- **Compatible Docker** : Commandes similaires à Docker
- **Natif Fedora/RHEL** : Support officiel Red Hat
- **SELinux** : Intégration native avec les politiques de sécurité

### Avantages RHEL 9 UBI
- **Images officielles Red Hat** : Maintenues et sécurisées
- **Python 3.12** : Version récente et performante
- **Enterprise-ready** : Stabilité et support long terme
- **Gratuit** : Pas besoin d'abonnement Red Hat
- **Compatibilité Fedora** : Même écosystème RPM

## 📋 Fichiers créés

### `Dockerfile`
Image basée sur RHEL 9 UBI avec Python 3.12. Installe toutes les dépendances GTK4 et libadwaita nécessaires.

**Caractéristiques :**
- Multi-stage pour optimisation
- Utilisateur non-root (UID 1001)
- Volume pour données persistantes
- Variables d'environnement configurées

### `build-container.sh`
Script automatisé pour construire l'image avec Podman.

**Fonctionnalités :**
- Build avec layers pour cache
- Format Docker pour compatibilité
- Affichage des informations post-build

### `run-container.sh`
Script de lancement avec toutes les options nécessaires.

**Configure :**
- Partage X11/Wayland pour l'affichage
- Volume persistant pour la base de données
- Accélération GPU avec `/dev/dri`
- Networking host pour accès complet
- Labels SELinux appropriés

### `.containerignore`
Fichiers exclus du build pour optimiser la taille de l'image.

### `requirements.txt`
Dépendances Python minimales nécessaires.

## 🚀 Utilisation rapide

### Première utilisation

```bash
# 1. Autoriser X11
xhost +local:

# 2. Construire l'image (une seule fois)
./build-container.sh

# 3. Lancer l'application
./run-container.sh
```

### Utilisation quotidienne

```bash
# Lancer l'application
./run-container.sh
```

C'est tout ! Les données sont automatiquement sauvegardées dans `~/.local/share/passwordmanager-container/`

## 🔐 Sécurité

### Isolation
- ✅ L'application tourne dans un container isolé
- ✅ Pas d'accès au système de fichiers hôte (sauf données)
- ✅ Utilisateur non-root dans le container
- ✅ SELinux actif avec labels appropriés

### Données
- ✅ Stockées dans `~/.local/share/passwordmanager-container/`
- ✅ Chiffrées avec AES-256-GCM
- ✅ Séparées des données d'installation locale
- ✅ Faciles à sauvegarder

### Réseau
- ⚠️ `--network host` : Nécessaire pour certaines applications GTK
- Alternative : Créer un réseau dédié si isolation requise

## 🎨 X11 vs Wayland

L'application supporte les deux :

### X11 (par défaut)
```bash
# Déjà configuré dans run-container.sh
-e DISPLAY="${DISPLAY}"
-v /tmp/.X11-unix:/tmp/.X11-unix:rw
```

### Wayland
```bash
# Également configuré (fallback automatique)
-e WAYLAND_DISPLAY="${WAYLAND_DISPLAY}"
-v "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}:..."
```

## 📊 Performances

### Taille de l'image
- **Base RHEL 9 UBI** : ~200 MB
- **Avec dépendances GTK4** : ~400-500 MB
- **Image finale** : ~500 MB

### Temps de build
- **Premier build** : 3-5 minutes (téléchargement packages)
- **Rebuilds** : 30 secondes (avec cache layers)

### Runtime
- **Démarrage** : 1-2 secondes
- **Performance** : Native (pas de virtualisation)
- **Mémoire** : ~100-150 MB

## 🛠️ Personnalisation

### Modifier l'image

```dockerfile
# Dans Dockerfile, ajouter des packages :
RUN dnf install -y mon-package && dnf clean all

# Changer le port ou autre config :
ENV MA_VARIABLE=valeur
```

### Build avec options

```bash
# Build sans cache
podman build --no-cache -t password-manager:latest .

# Build avec autre tag
podman build -t password-manager:dev .

# Build verbeux
podman build --log-level=debug -t password-manager:latest .
```

### Lancement personnalisé

```bash
# Avec autre volume
podman run -it --rm \
    -e DISPLAY="${DISPLAY}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v /mon/chemin:/data:Z \
    password-manager:latest

# Mode debug (shell interactif)
podman run -it --rm \
    --entrypoint /bin/bash \
    password-manager:latest
```

## 🔄 Mises à jour

### Mettre à jour l'image

```bash
# 1. Reconstruire l'image
./build-container.sh

# 2. Relancer le container
./run-container.sh
```

Les données sont préservées car stockées dans un volume externe.

### Mettre à jour le code uniquement

```bash
# Sans rebuild complet
podman run -it --rm \
    -e DISPLAY="${DISPLAY}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v $(pwd):/opt/app-root/src/password-manager:ro \
    -v ~/.local/share/passwordmanager-container:/data:Z \
    password-manager:latest
```

## 🐛 Résolution de problèmes

### L'application ne s'affiche pas

```bash
# 1. Vérifier X11
echo $DISPLAY
xhost +local:

# 2. Tester une app simple
podman run -it --rm \
    -e DISPLAY="${DISPLAY}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    fedora:latest \
    bash -c "dnf install -y xeyes && xeyes"
```

### Erreur SELinux

```bash
# Vérifier les logs SELinux
sudo ausearch -m avc -ts recent

# Mode permissif temporaire
sudo setenforce 0

# Après test, réactiver
sudo setenforce 1
```

### Permissions volume

```bash
# Vérifier les permissions
ls -laZ ~/.local/share/passwordmanager-container/

# Recréer si nécessaire
rm -rf ~/.local/share/passwordmanager-container/
mkdir -p ~/.local/share/passwordmanager-container/
```

### Container ne démarre pas

```bash
# Voir les logs
podman logs password-manager-app

# Mode verbose
podman run -it --rm \
    --name password-manager-debug \
    -e DISPLAY="${DISPLAY}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    password-manager:latest 2>&1 | tee debug.log
```

## 📦 Distribution

### Exporter l'image

```bash
# Sauvegarder l'image
podman save -o password-manager.tar password-manager:latest

# Compresser
gzip password-manager.tar
```

### Importer sur une autre machine

```bash
# Copier le fichier .tar.gz sur la machine cible
scp password-manager.tar.gz user@machine:/tmp/

# Sur la machine cible
podman load -i /tmp/password-manager.tar.gz
```

### Publier sur un registre

```bash
# Tag pour un registre
podman tag password-manager:latest registry.example.com/password-manager:latest

# Push
podman push registry.example.com/password-manager:latest
```

## 🎓 Ressources

- [Documentation Podman](https://docs.podman.io/)
- [RHEL UBI Images](https://catalog.redhat.com/software/containers/ubi9/python-312/)
- [GTK4 Documentation](https://docs.gtk.org/gtk4/)
- [SELinux et Containers](https://www.redhat.com/sysadmin/podman-selinux-container-separation)

## 💡 Astuces

### Alias utiles

```bash
# Ajouter dans ~/.bashrc
alias pwdm-build='cd ~/Vscode/Gestionnaire_mot_passe && ./build-container.sh'
alias pwdm-run='cd ~/Vscode/Gestionnaire_mot_passe && ./run-container.sh'
alias pwdm='pwdm-run'

# Utilisation
pwdm  # Lance directement l'application
```

### Backup automatique

```bash
# Script de backup quotidien
cat > ~/bin/backup-pwdm.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=~/backups/password-manager
mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).tar.gz" \
    ~/.local/share/passwordmanager-container/
# Garder seulement les 30 derniers backups
ls -t "$BACKUP_DIR"/backup-*.tar.gz | tail -n +31 | xargs rm -f
EOF

chmod +x ~/bin/backup-pwdm.sh

# Ajouter à crontab (tous les jours à 2h)
(crontab -l 2>/dev/null; echo "0 2 * * * ~/bin/backup-pwdm.sh") | crontab -
```

### Monitoring

```bash
# Voir l'utilisation ressources
podman stats password-manager-app

# Inspection détaillée
podman inspect password-manager-app
```

---

**🎉 Profitez de votre gestionnaire de mots de passe conteneurisé !**
