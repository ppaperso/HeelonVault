# 🔐 Gestionnaire de Mots de Passe

Un gestionnaire de mots de passe sécurisé et moderne pour Linux, développé avec GTK4 et Python.

![Version](https://img.shields.io/badge/version-0.1.0--beta-blue)
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![GTK Version](https://img.shields.io/badge/GTK-4.0-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## ✨ Fonctionnalités

### 🔒 Sécurité
- **Chiffrement AES-256-GCM** : Protection maximale de vos données
- **PBKDF2** avec 600 000 itérations pour la dérivation de clé
- **Mot de passe maître individuel** : Chaque utilisateur a son propre mot de passe
- **Générateur cryptographiquement sécurisé** utilisant `secrets`
- **Workspaces isolés** : Séparation complète des données entre utilisateurs

### 👥 Gestion multi-utilisateurs
- **Comptes utilisateurs séparés** : Chaque utilisateur a son propre espace
- **Workspaces isolés** : Les données d'un utilisateur sont invisibles aux autres
- **Rôles utilisateur** : Admin et Utilisateur standard
- **Interface personnalisée** : "Bonjour [nom_utilisateur]" avec badge de rôle
- **Gestion admin** : Réinitialisation des mots de passe oubliés
- **Écran de sélection** : Choix du compte au démarrage

### 📝 Gestion des mots de passe
- Ajout, modification et suppression d'entrées
- Organisation par **catégories** (Personnel, Travail, Finance, Social, etc.)
- Système de **tags** flexible pour une classification avancée
- **Recherche rapide** dans toutes les entrées
- Stockage de : titre, identifiant, mot de passe, URL, notes
- **Import CSV** : Migration depuis LastPass, 1Password, Bitwarden et autres

### 🎲 Générateur de mots de passe
- **Mots de passe aléatoires** avec options personnalisables :
  - Longueur ajustable (8-64 caractères)
  - Majuscules, minuscules, chiffres, symboles
  - Exclusion des caractères ambigus (0, O, l, 1, I)
- **Phrases de passe** mémorables (ex: `Soleil-montagne-Jardin-neige42`)
- Copie rapide dans le presse-papiers

### 🎨 Interface moderne
- Interface **GTK4 + libadwaita** native pour Linux
- Design épuré et intuitif
- Thème sombre/clair automatique
- Affichage/masquage des mots de passe
- Copie en un clic

## 📋 Prérequis

### Système d'exploitation
- Linux (Ubuntu, Fedora, Arch, Debian, etc.)

### Dépendances
```bash
# Python 3.8 ou supérieur
python3 --version

# GTK4 et libadwaita
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1  # Debian/Ubuntu
sudo dnf install python3-gobject gtk4 libadwaita                          # Fedora
sudo pacman -S python-gobject gtk4 libadwaita                             # Arch Linux
```

### Bibliothèques Python
```bash
pip install cryptography
```

## 🚀 Installation

### Installation automatique

Un script d'installation automatique configure l'application et ses dépendances :

```bash
# Cloner le dépôt
git clone https://github.com/ppaperso/Gestionnaire_mot_passe.git
cd Gestionnaire_mot_passe

# Lancer l'installation
./install.sh
```

Le script :
- ✅ Vérifie les prérequis système (Python, GTK4, libadwaita)
- ✅ Crée l'environnement virtuel Python
- ✅ Installe les dépendances Python
- ✅ Crée le répertoire de données partagé `/var/lib/passwordmanager-shared`
- ✅ Configure les permissions multi-utilisateurs
- ✅ Installe le lanceur dans le menu Applications

### Architecture multi-utilisateurs

L'application utilise une **base de données partagée** pour tous les utilisateurs du système :

- 📂 **Emplacement** : `/var/lib/passwordmanager-shared/`
- 🔐 **Séparation** : Chaque utilisateur a ses propres fichiers de base de données
- 🔑 **Sécurité** : Chaque utilisateur chiffre ses données avec son propre mot de passe maître
- 👥 **Partage** : Tous les utilisateurs du système peuvent utiliser l'application
- 🛡️ **Isolation** : Un utilisateur ne peut pas accéder aux données d'un autre

**Note** : Vous devez être membre du groupe `users` pour accéder au répertoire partagé. Le script d'installation le fait automatiquement.

### Installation manuelle

Si vous préférez installer manuellement :

#### 1. Installer les dépendances système
```bash
# Fedora/RHEL
sudo dnf install python3-gobject gtk4 libadwaita

# Debian/Ubuntu
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1

# Arch Linux
sudo pacman -S python-gobject gtk4 libadwaita
```

#### 2. Créer l'environnement virtuel
```bash
python3 -m venv venvpwdmanager
source venvpwdmanager/bin/activate
pip install -r requirements.txt
```

#### 3. Créer le répertoire de données partagé
```bash
sudo mkdir -p /var/lib/passwordmanager-shared
sudo chown root:users /var/lib/passwordmanager-shared
sudo chmod 775 /var/lib/passwordmanager-shared
sudo usermod -a -G users $USER
# Vous devez vous déconnecter/reconnecter après cette étape
```

#### 4. Tester l'installation
```bash
./test-app.sh
```

Ce script vérifie automatiquement :
- ✅ Présence du venv
- ✅ Version Python
- ✅ Dépendances système (GTK4, libadwaita)
- ✅ Dépendances Python
- ✅ Syntaxe du code
- ✅ Tests unitaires des composants

## 📖 Utilisation

### Lancement de l'application

#### Depuis le menu Applications
Après installation, l'application apparaît dans : **Menu → Utilitaires → Gestionnaire de mots de passe**

#### En ligne de commande
```bash
# Mode développement (avec venv)
./run-dev.sh

# Ou directement
source venvpwdmanager/bin/activate
python3 password_manager.py
```

### Première utilisation

#### Compte administrateur par défaut
Au premier lancement, un compte **admin** est créé avec :
- **Nom d'utilisateur** : `admin`
- **Mot de passe** : `admin`

**⚠️ IMPORTANT** : Changez immédiatement ce mot de passe après la première connexion !

#### Créer votre compte
1. **Sélectionnez un utilisateur** ou cliquez sur "Créer un nouveau compte"
2. Entrez vos informations :
   - Nom d'utilisateur (min. 3 caractères)
   - Mot de passe maître (min. 8 caractères)
   - Confirmation du mot de passe
3. Votre workspace personnel est créé automatiquement

#### Connexion
1. Sélectionnez votre compte dans la liste
2. Entrez votre mot de passe maître
3. Accédez à votre espace personnel avec "Bonjour [votre_nom]"

**⚠️ SÉCURITÉ** : 
- Chaque utilisateur a son propre mot de passe maître
- Les mots de passe ne sont **jamais** stockés en clair
- Un administrateur peut réinitialiser un mot de passe oublié

### Gestion des utilisateurs

#### Pour les utilisateurs standards
- **Voir ses propres mots de passe** uniquement
- **Créer/Modifier/Supprimer** ses entrées
- **Changer de compte** via le menu utilisateur
- **Se déconnecter** pour revenir à l'écran de sélection

#### Pour les administrateurs
En plus des fonctionnalités utilisateur standard :
- **Gérer les utilisateurs** : Menu "Gérer les utilisateurs"
- **Voir tous les comptes** avec dates de création et dernière connexion
- **Réinitialiser un mot de passe** : Pour un utilisateur qui l'a oublié
- **Supprimer un compte** : Supprime l'utilisateur et toutes ses données
- **Badge "Admin"** visible dans l'interface

#### Réinitialiser un mot de passe oublié (Admin)
1. Connectez-vous avec un compte administrateur
2. Menu → "Gérer les utilisateurs"
3. Cliquez sur "Réinitialiser MdP" pour l'utilisateur concerné
4. Entrez et confirmez le nouveau mot de passe
5. Communiquez le nouveau mot de passe à l'utilisateur

### Gestion des entrées

#### Ajouter une entrée
1. Cliquez sur le bouton **+** dans la barre d'outils
2. Remplissez les informations :
   - **Titre** (obligatoire)
   - **Catégorie**
   - **Tags** (séparés par des virgules)
   - **Nom d'utilisateur**
   - **Mot de passe** (obligatoire) - utilisez le bouton "Générer"
   - **URL**
   - **Notes**
3. Cliquez sur **Enregistrer**

#### Modifier une entrée
1. Sélectionnez l'entrée dans la liste
2. Cliquez sur **Modifier** dans le panneau de détails
3. Modifiez les champs souhaités
4. Enregistrez les modifications

#### Supprimer une entrée
1. Sélectionnez l'entrée
2. Cliquez sur **Supprimer**
3. Confirmez la suppression

### Filtrage et recherche
- **Par catégorie** : Cliquez sur une catégorie dans le panneau gauche
- **Par tag** : Cliquez sur un tag dans la section Tags
- **Recherche** : Utilisez la barre de recherche pour filtrer par titre, utilisateur ou URL

### Générateur de mots de passe
1. Lors de l'ajout/modification, cliquez sur **Générer**
2. Choisissez le type :
   - **Aléatoire** : Personnalisez longueur et caractères
   - **Phrase de passe** : Choisissez le nombre de mots
3. Cliquez sur **Utiliser ce mot de passe** ou **Copier**

## 🏗️ Architecture

### Structure du projet
```
gestionnaire-mot-passe/
├── password_manager.py      # Application principale (72 KB)
├── README.md               # Documentation principale (17 KB)
├── MULTI_USER_GUIDE.md     # Guide multi-utilisateurs (14 KB)
├── PODMAN_GUIDE.md         # Guide conteneurisation (7.7 KB)
├── requirements.txt        # Dépendances Python
├── Dockerfile              # Image container RHEL 9 UBI + Python 3.12
├── .containerignore        # Fichiers exclus du build
├── Scripts de développement:
│   ├── test-app.sh         # Script de test complet avec venv
│   └── run-dev.sh          # Lancement en mode développement
├── Scripts de production:
│   ├── build-container.sh  # Construction image Podman
│   └── run-container.sh    # Lancement conteneurisé
├── venvpwdmanager/         # Environnement virtuel Python
└── Données (selon installation):
    ├── ~/.local/share/passwordmanager/           # Installation locale
    │   ├── users.db                              # Base des utilisateurs
    │   ├── passwords_[username].db               # Base de chaque utilisateur
    │   └── salt_[username].bin                   # Salt par utilisateur
    └── ~/.local/share/passwordmanager-container/ # Installation conteneurisée
        ├── users.db
        ├── passwords_[username].db
        └── salt_[username].bin
```

### Composants principaux

#### `UserManager`
Gestion des utilisateurs et authentification :
- **Création de comptes** avec validation
- **Authentification** avec hash PBKDF2
- **Gestion des rôles** (admin/user)
- **Réinitialisation de mot de passe** par admin
- **Base dédiée** : `users.db`

#### `PasswordGenerator`
Génère des mots de passe aléatoires ou des phrases de passe sécurisées.

#### `PasswordCrypto`
Gère le chiffrement/déchiffrement avec :
- **AES-256-GCM** : Chiffrement authentifié
- **PBKDF2** : Dérivation de clé à partir du mot de passe maître
- **Nonce unique** pour chaque opération de chiffrement
- **Salt individuel** par utilisateur

#### `PasswordDatabase`
Interface avec la base de données SQLite :
- **Workspace séparé** par utilisateur : `passwords_[username].db`
- Stockage des mots de passe chiffrés
- Gestion des catégories et tags
- Recherche et filtrage

#### Interface GTK4
- `UserSelectionDialog` : Sélection du compte utilisateur
- `LoginDialog` : Authentification avec mot de passe maître
- `CreateUserDialog` : Création de nouveau compte
- `ManageUsersDialog` : Gestion des utilisateurs (admin)
- `ResetPasswordDialog` : Réinitialisation de mot de passe (admin)
- `PasswordManagerApp` : Fenêtre principale avec badge utilisateur
- `AddEditDialog` : Dialogue d'ajout/édition
- `PasswordGeneratorDialog` : Générateur de mots de passe

### Sécurité

#### Architecture multi-utilisateurs
```
Utilisateur → Authentification → Workspace dédié
   ↓              ↓                     ↓
Username    Password hash          passwords_[user].db
            (PBKDF2)               salt_[user].bin
```

#### Chiffrement
```
Mot de passe maître → PBKDF2 (600k itérations) → Clé AES-256
                      ↓
            Salt individuel (32 bytes)
```

Chaque mot de passe est chiffré avec un **nonce unique** de 12 bytes, garantissant qu'un même mot de passe chiffré deux fois produit des résultats différents.

#### Isolation des données
- **Base utilisateurs** : `users.db` (hash des mots de passe, pas de données sensibles)
- **Base par utilisateur** : `passwords_[username].db` (données chiffrées)
- **Salt par utilisateur** : `salt_[username].bin` (permissions 600)
- **Séparation complète** : Un utilisateur ne peut **jamais** accéder aux données d'un autre
- Les mots de passe ne sont **jamais** stockés en clair

#### Rôles et permissions
- **User** : Accès à son workspace uniquement
- **Admin** : 
  - Accès à son propre workspace
  - Réinitialisation des mots de passe oubliés
  - Gestion des comptes utilisateurs
  - **Ne peut PAS** voir les mots de passe des autres utilisateurs

## 🛠️ Optimisations réalisées

### Performance
- ✅ Utilisation de `remove_all()` au lieu de boucles while pour vider les listes
- ✅ Compréhension de liste pour le filtrage par tags
- ✅ Tri insensible à la casse avec `COLLATE NOCASE`
- ✅ Early return pour améliorer la lisibilité

### Robustesse
- ✅ Gestion d'erreurs pour le déchiffrement
- ✅ Sécurisation des permissions du fichier salt (chmod 600)
- ✅ Validation des champs obligatoires
- ✅ Messages d'erreur informatifs

### Documentation
- ✅ Docstrings détaillées avec types et descriptions
- ✅ Commentaires explicatifs
- ✅ Structure claire et lisible

Pour plus d'informations, consultez les guides dans le dossier `docs/` :
- 📁 [CSV_IMPORT_GUIDE.md](docs/CSV_IMPORT_GUIDE.md) - Guide d'importation CSV depuis LastPass, 1Password, etc.
- 📁 [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Architecture du projet
- 📁 [SECURITY.md](docs/SECURITY.md) - Détails sur la sécurité
- 📁 [BRUTE_FORCE_PROTECTION.md](docs/BRUTE_FORCE_PROTECTION.md) - Protection contre les attaques
- 📁 [MULTI_USER_GUIDE.md](MULTI_USER_GUIDE.md) - Gestion multi-utilisateurs

## 🐋 Gestion des containers Podman

### Commandes utiles

#### Build et gestion d'image
```bash
# Construire l'image
./build-container.sh

# Lister les images
podman images

# Supprimer l'image
podman rmi password-manager:latest

# Rebuild sans cache
podman build --no-cache -t password-manager:latest .
```

#### Gestion du container
```bash
# Lancer l'application
./run-container.sh

# Voir les containers en cours
podman ps

# Voir tous les containers (y compris arrêtés)
podman ps -a

# Arrêter le container
podman stop password-manager-app

# Supprimer le container
podman rm password-manager-app

# Logs du container
podman logs password-manager-app
```

#### Données persistantes
```bash
# Localisation des données
ls -la ~/.local/share/passwordmanager-container/

# Backup des données
tar czf password-manager-backup-$(date +%Y%m%d).tar.gz \
    ~/.local/share/passwordmanager-container/

# Restauration
tar xzf password-manager-backup-YYYYMMDD.tar.gz -C ~/
```

### Troubleshooting

#### Problème d'affichage X11
```bash
# Autoriser les connexions X11 locales
xhost +local:

# Vérifier la variable DISPLAY
echo $DISPLAY

# Si sous Wayland
echo $WAYLAND_DISPLAY
```

#### Problème de permissions SELinux
```bash
# Désactiver temporairement SELinux (si nécessaire)
sudo setenforce 0

# Mode permissif permanent (déconseillé)
sudo sed -i 's/SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config
```

#### Le container ne démarre pas
```bash
# Vérifier les logs
podman logs password-manager-app

# Démarrer en mode debug
podman run -it --rm \
    --name password-manager-debug \
    -e DISPLAY="${DISPLAY}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    password-manager:latest /bin/bash
```

## 🔧 Développement

### Workflow de développement

#### 1. Configuration de l'environnement
```bash
# Cloner le projet
git clone https://github.com/votre-utilisateur/gestionnaire-mot-passe.git
cd gestionnaire-mot-passe

# Installer les dépendances système
sudo dnf install python3-gobject gtk4 libadwaita

# Créer le venv
python3 -m venv venvpwdmanager
source venvpwdmanager/bin/activate

# Installer les dépendances Python
pip install -r requirements.txt
```

#### 2. Tests et validation
```bash
# Lancer les tests complets
./test-app.sh

# Tester l'application
./run-dev.sh

# Vérifier la syntaxe
python3 -m py_compile password_manager.py

# Linter (optionnel)
pip install pylint
pylint password_manager.py
```

#### 3. Développement itératif
```bash
# 1. Modifier le code
vim password_manager.py

# 2. Tester
./test-app.sh

# 3. Lancer l'application
./run-dev.sh

# 4. Déboguer si nécessaire
# Les données de test sont dans: ~/.local/share/passwordmanager/
```

#### 4. Conteneurisation
```bash
# Une fois les modifications validées, construire l'image
./build-container.sh

# Tester la version conteneurisée
./run-container.sh
```

### Scripts disponibles

| Script | Description | Usage |
|--------|-------------|-------|
| `test-app.sh` | Tests complets (syntaxe, imports, unitaires) | `./test-app.sh` |
| `run-dev.sh` | Lancement en mode développement avec venv | `./run-dev.sh` |
| `build-container.sh` | Construction de l'image Podman | `./build-container.sh` |
| `run-container.sh` | Lancement de l'application conteneurisée | `./run-container.sh` |

### Contribuer
Les contributions sont les bienvenues ! Pour contribuer :
1. Forkez le projet
2. Créez une branche (`git checkout -b feature/amelioration`)
3. Committez vos changements (`git commit -am 'Ajout fonctionnalité'`)
4. Pushez vers la branche (`git push origin feature/amelioration`)
5. Ouvrez une Pull Request

### Tests
```bash
# Tester le générateur de mots de passe
python3 -c "from password_manager import PasswordGenerator; print(PasswordGenerator.generate())"

# Tester le chiffrement
python3 -c "from password_manager import PasswordCrypto; c = PasswordCrypto('test'); enc = c.encrypt('secret'); print(c.decrypt(enc))"
```

## ⚠️ Avertissements

1. **Mot de passe maître** : 
   - Chaque utilisateur a son propre mot de passe maître
   - Un admin peut le réinitialiser, mais **toutes les données seront inaccessibles** avec l'ancien mot de passe
   - Choisissez un mot de passe fort et mémorisable
   
2. **Compte admin par défaut** :
   - Login: `admin` / Password: `admin`
   - **Changez-le immédiatement** après le premier lancement !
   
3. **Sauvegardes** : 
   - Sauvegardez régulièrement `~/.local/share/passwordmanager/`
   - Incluez `users.db` et tous les fichiers `passwords_*.db` et `salt_*.bin`
   
4. **Sécurité du système** : 
   - Assurez-vous que votre système est sécurisé (pas de keyloggers, malware, etc.)
   - Les permissions des fichiers salt sont automatiquement sécurisées (600)
   
5. **Confidentialité** : 
   - Ne partagez jamais votre mot de passe maître
   - Les administrateurs peuvent réinitialiser les mots de passe mais **ne peuvent pas** voir vos données

## 🐛 Problèmes connus

- L'application nécessite GTK4 et libadwaita (non disponible sur les vieux systèmes)
- Le presse-papiers n'est pas automatiquement vidé après copie

## 📝 TODO / Améliorations futures

- [x] Gestion multi-utilisateurs avec workspaces séparés
- [x] Rôles admin/user
- [x] Réinitialisation de mot de passe par admin
- [x] Interface personnalisée par utilisateur
- [ ] Auto-vidage du presse-papiers après 30 secondes
- [ ] Export/Import des données (chiffré) par utilisateur
- [ ] Analyse de la force des mots de passe
- [ ] Détection des mots de passe dupliqués
- [ ] Notifications de renouvellement des mots de passe
- [ ] Support du dark mode forcé
- [ ] Intégration avec les navigateurs
- [ ] Version en ligne de commande (CLI)
- [ ] Historique des connexions par utilisateur
- [ ] Logs d'audit pour les actions admin

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 🙏 Remerciements

- [GTK](https://www.gtk.org/) pour le framework d'interface
- [libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/) pour les widgets modernes
- [cryptography](https://cryptography.io/) pour les primitives cryptographiques

## 📧 Contact

Pour toute question ou suggestion, n'hésitez pas à ouvrir une issue sur GitHub.

---

**⚡ Fait avec ❤️ pour la communauté Linux**
