# 🌐 Intégration Navigateur - Phase 1 & 2

Extension Firefox complète avec Native Messaging Host pour intégrer votre gestionnaire de mots de passe directement dans le navigateur.

## 📋 Architecture

```
┌─────────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  Extension Firefox  │ ←───→ │  Native Host     │ ←───→ │  Application    │
│  (JavaScript)       │       │  (Python stdio)  │       │  GTK4 (Python)  │
│  - Popup UI         │       │  - Message relay │       │  - Database     │
│  - Content Scripts  │       │  - Validation    │       │  - Encryption   │
│  - Form Detection   │       │  - Logging       │       │  - User Auth    │
└─────────────────────┘       └──────────────────┘       └─────────────────┘
```

## ✨ Fonctionnalités

### ✅ Phase 1 - Native Messaging Host (TERMINÉE)
- ✅ Communication stdin/stdout avec protocole binaire
- ✅ 6 actions implémentées (ping, status, search, get, save, generate)
- ✅ Logging sécurisé
- ✅ Détection automatique venv-dev/venv
- ✅ Installation automatisée pour Firefox et Chrome

### ✅ Phase 2 - Extension Firefox (TERMINÉE)
- ✅ **Détection automatique** des formulaires de connexion
- ✅ **Bouton auto-fill** (🔑) sur les champs de mot de passe
- ✅ **Popup de recherche** avec liste des identifiants
- ✅ **Génération de mots de passe** sécurisés
- ✅ **Copie rapide** dans le presse-papiers
- ✅ **Proposition de sauvegarde** après connexion
- ✅ Interface moderne avec statut de connexion
- ✅ Support des SPAs (Single Page Applications)

### 🚧 Phase 3 - À venir
- ⏳ Port vers Chrome/Chromium (Manifest V3)
- ⏳ Communication bidirectionnelle app ↔ native host
- ⏳ Notifications desktop
- ⏳ Import/export depuis le navigateur

## 🚀 Installation

### 1. Installer le Native Messaging Host

```bash
cd browser_integration
./install_native_host.sh
```

Cela va :
- **Détecter automatiquement l'environnement** (`venv-dev` pour développement, `venv` pour production)
- Créer un **wrapper shell** qui utilise le bon environnement virtuel Python
- Créer les manifestes pour Firefox et Chrome/Chromium
- Configurer les permissions
- Créer les répertoires nécessaires

**📌 Note importante:** Le script utilise en priorité `venv-dev` s'il existe (tests), sinon `venv` (production).

### 2. Tester le Native Host

```bash
./test_native_host.sh
```

Vous devriez voir des réponses JSON pour chaque test.

### 3. Installer l'extension Firefox

#### Option A - Installation temporaire (tests)
```bash
./install_firefox_extension.sh
```

Puis suivez les instructions pour charger l'extension temporaire :
1. Ouvrir Firefox
2. Aller dans `about:debugging#/runtime/this-firefox`
3. Cliquer sur "Charger un module complémentaire temporaire..."
4. Sélectionner : `firefox_extension/manifest.json`

⚠️ **L'extension temporaire disparaît au redémarrage de Firefox**

#### Option B - Installation permanente (recommandée)

**Étape 1 : Packager l'extension**
```bash
./package_for_signing.sh
```

**Étape 2 : Signer l'extension**
```bash
./sign_extension.sh
```

Suivez les instructions pour obtenir vos clés API Mozilla et signer l'extension.

**Étape 3 : Installer le .xpi signé**
Le fichier `.xpi` signé sera dans `firefox_extension/web-ext-artifacts/`

Double-cliquez dessus ou glissez-le dans Firefox.

✅ **L'extension reste installée après redémarrage !**

📚 **Guide détaillé** : Voir [SIGNING_GUIDE.md](SIGNING_GUIDE.md)

## 🔧 Fonctionnalités Implémentées

### Actions disponibles

| Action | Description | Paramètres | Réponse |
|--------|-------------|------------|---------|
| `ping` | Test de connexion | - | `pong` avec version |
| `check_status` | Statut de l'application | - | État app + utilisateur |
| `search_credentials` | Rechercher identifiants | `url`, `username?` | Liste d'entrées |
| `get_credentials` | Récupérer identifiants | `entry_id` | Username + password |
| `save_credentials` | Sauvegarder identifiants | `url`, `username`, `password` | Confirmation |
| `generate_password` | Générer mot de passe | `length?` | Mot de passe |

### Format des messages

**Requête :**
```json
{
  "action": "search_credentials",
  "url": "https://github.com"
}
```

**Réponse :**
```json
{
  "action": "search_response",
  "status": "ok",
  "url": "https://github.com",
  "credentials": [
    {
      "id": 1,
      "title": "GitHub Account",
      "username": "user@example.com"
    }
  ]
}
```

## 🎯 Utilisation de l'extension Firefox

### 1️⃣ Auto-fill sur les formulaires

Lorsque vous visitez un site avec un formulaire de connexion :
1. Un **bouton 🔑** apparaît près du champ mot de passe
2. Cliquez dessus pour voir vos identifiants disponibles
3. Sélectionnez un identifiant pour remplir automatiquement le formulaire

### 2️⃣ Popup de gestion

Cliquez sur l'**icône 🔐** dans la barre d'outils Firefox :
- **🟢 Statut de connexion** au native host
- **🔍 Recherche** d'identifiants par nom de site ou username
- **🎲 Génération** de mots de passe sécurisés
- **📋 Copie rapide** des mots de passe
- **🔑 Remplissage** direct depuis le popup

### 3️⃣ Sauvegarde automatique

Après une connexion réussie sur un nouveau site :
1. Un popup apparaît proposant de sauvegarder les identifiants
2. Cliquez sur "Sauvegarder" pour ajouter à votre base
3. L'identifiant sera disponible pour les prochaines visites

### 4️⃣ Génération de mots de passe

Dans le popup :
1. Cliquez sur **"🎲 Générer"**
2. Un mot de passe de 20 caractères est créé
3. Cliquez sur **"📋"** pour copier dans le presse-papiers

## 🔐 Sécurité

- ✅ **Native Messaging** : Communication sécurisée via protocole binaire
- ✅ **Validation stricte** des messages et actions autorisées
- ✅ **Session token** unique par instance
- ✅ **Encryption AES-256-GCM** pour le stockage (app principale)
- ✅ **Logs sécurisés** sans mots de passe en clair
- ✅ **Permissions Firefox** : uniquement nativeMessaging, activeTab, storage
- ✅ **Isolated world** : Content scripts isolés du contexte de la page

## 🔀 Environnements Dev vs Production

Le système détecte automatiquement l'environnement à utiliser :

### Développement (`venv-dev`)
- **Utilisé pour** : Tests et développement
- **Détection** : Si `venv-dev/` existe, il est utilisé en priorité
- **Base de données** : `src/data/` (isolée de la production)
- **Activation** : `./run-dev.sh` ou tests unitaires

### Production (`venv`)
- **Utilisé pour** : Application déployée
- **Détection** : Utilisé seulement si `venv-dev/` n'existe pas
- **Base de données** : Dossier de production (configuré par `update.sh`)
- **Activation** : `./run.sh` ou déploiement avec `update.sh`

### Wrapper automatique
Le fichier `native_host_wrapper.sh` :
1. Détecte automatiquement quel venv utiliser (`venv-dev` > `venv`)
2. Active le bon environnement Python
3. Lance `native_host.py` avec les bonnes dépendances

**💡 Avantage** : Un seul manifeste Firefox/Chrome fonctionne pour les deux environnements !

## 📝 Logs

Les logs sont stockés dans :
```
~/.local/share/passwordmanager/native_host.log
```

Pour suivre en temps réel :
```bash
tail -f ~/.local/share/passwordmanager/native_host.log
```

## 📁 Structure des fichiers

```
browser_integration/
├── native_host.py              # Native Messaging Host (Python)
├── native_host_wrapper.sh      # Wrapper détection venv
├── install_native_host.sh      # Installation manifestes
├── install_firefox_extension.sh # Installation extension
├── test_native_host.sh         # Tests automatisés
├── README.md                   # Cette documentation
└── firefox_extension/
    ├── manifest.json           # Configuration extension
    ├── background.js           # Service worker / background script
    ├── content.js              # Script injecté dans les pages
    ├── popup.html              # Interface popup
    ├── popup.js                # Logique popup
    ├── popup.css               # Styles
    ├── README.txt              # Instructions utilisateur
    └── icons/
        ├── icon-48.png         # Icône 48x48
        ├── icon-96.png         # Icône 96x96
        └── icon.svg            # Source SVG
```

## 🧪 Tests

### Test du Native Host
```bash
./test_native_host.sh
```

### Test de l'extension
1. Charger l'extension dans Firefox (voir instructions ci-dessus)
2. Ouvrir la console du navigateur (F12)
3. Ouvrir le popup de l'extension
4. Vérifier le statut : doit afficher "Connecté" avec un point vert
5. Tester la génération de mot de passe
6. Visiter un site avec formulaire de login (ex: github.com)
7. Vérifier que le bouton 🔑 apparaît

## 🔄 Prochaines Étapes (Phase 2)

- [ ] Extension Firefox avec UI
- [ ] Content scripts pour détection formulaires
- [ ] Communication bidirectionnelle
- [ ] Auto-remplissage
- [ ] Capture de nouveaux mots de passe

## 🐛 Troubleshooting

### Le native host ne répond pas

1. Vérifier que l'environnement virtuel existe :
   ```bash
   ls -la ../venv-dev/bin/python3  # Pour le développement
   ls -la ../venv/bin/python3      # Pour la production
   ```

2. Vérifier les permissions du wrapper :
   ```bash
   ls -la native_host_wrapper.sh
   # Doit être exécutable (-rwxr-xr-x)
   ```

3. Vérifier les logs en temps réel :
   ```bash
   tail -f ~/.local/share/passwordmanager/native_host.log
   ```

4. Tester manuellement avec le wrapper :
   ```bash
   echo '{"action":"ping"}' | ./native_host_wrapper.sh
   # Ou utiliser le script de test complet
   ./test_native_host.sh
   ```

5. Vérifier quel environnement est utilisé :
   ```bash
   # Le wrapper détecte automatiquement le bon venv
   # Pour forcer production, supprimez temporairement venv-dev
   mv ../venv-dev ../venv-dev.backup
   ./install_native_host.sh  # Utilisera venv
   mv ../venv-dev.backup ../venv-dev
   ```

### L'extension ne se connecte pas

1. **Vérifier le manifeste Native Messaging :**
   ```bash
   cat ~/.mozilla/native-messaging-hosts/com.passwordmanager.native.json
   # Le "path" doit pointer vers native_host_wrapper.sh
   ```

2. **Vérifier les logs du native host :**
   ```bash
   tail -f ~/.local/share/passwordmanager/native_host.log
   ```

3. **Vérifier la console de l'extension :**
   - Ouvrir `about:debugging#/runtime/this-firefox`
   - Cliquer sur "Inspecter" sous l'extension
   - Regarder les erreurs dans la console

### Le bouton 🔑 n'apparaît pas

1. Vérifier que le content script est bien injecté (console navigateur)
2. Essayer de recharger la page (Ctrl+R)
3. Vérifier que le site a bien un formulaire avec `<input type="password">`
4. Certains sites bloquent les content scripts (CSP)

### Erreurs courantes

**"Error: No such native application com.passwordmanager.native"**
→ Le manifeste n'est pas installé ou mal configuré. Relancer `./install_native_host.sh`

**"Status: Déconnecté" dans le popup**
→ Le native host ne démarre pas. Vérifier les logs et le wrapper.

**L'extension se recharge toute seule**
→ Normal en mode développement. Pour un usage permanent, signer l'extension sur addons.mozilla.org

# Chromium
ls -la ~/.config/chromium/NativeMessagingHosts/
```

## 📚 Ressources

- [Native Messaging - MDN](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging)
- [Chrome Native Messaging](https://developer.chrome.com/docs/apps/nativeMessaging/)
- [WebExtensions API](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions)

## 📄 Licence

MIT - Voir LICENSE dans le répertoire racine
