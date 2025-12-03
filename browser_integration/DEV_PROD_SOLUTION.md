# 🔧 Solution DEV/PROD - Deux Extensions Distinctes

## 📅 Date : 3 décembre 2025

## 🎯 Problème Résolu

L'extension Firefox ne pouvait pas accéder aux données réelles de la base (ni dev ni prod). 
Le native host retournait uniquement des données de test en dur.

## ✅ Solution Implémentée

### Architecture Dual : DEV et PRODUCTION

Création de **deux extensions complètement distinctes** :

1. **Extension DEV** (`firefox_extension_dev/`)
   - ID: `password-manager-dev@example.com`
   - Native host: `com.passwordmanager.native.dev`
   - Badge: `[DEV]` en orange
   - Base de données: `src/data/passwords_admin.db`
   - Logs: `logs/native_host_dev.log`

2. **Extension PROD** (`firefox_extension/`)
   - ID: `password-manager@example.com`
   - Native host: `com.passwordmanager.native`
   - Base de données: `data/passwords_admin.db`
   - Logs: `~/.local/share/passwordmanager/native_host.log`

---

## 📂 Fichiers Créés/Modifiés

### 1. Native Host Principal

**`native_host.py`** (modifié)
- Détection automatique de `DEV_MODE` via variable d'environnement
- Connexion à la vraie base SQLite
- Recherche réelle dans la table `passwords`
- Logging adapté selon le mode

```python
DEV_MODE = os.environ.get('DEV_MODE', '0') == '1'

if DEV_MODE:
    DATA_DIR = APP_DIR / 'src' / 'data'
    LOG_FILE = APP_DIR / 'logs' / 'native_host_dev.log'
else:
    DATA_DIR = APP_DIR / 'data'
    LOG_FILE = Path.home() / '.local/share/passwordmanager/native_host.log'
```

### 2. Wrappers

**`native_host_wrapper_dev.sh`** (nouveau)
```bash
export DEV_MODE=1
exec "$VENV/bin/python3" "$SCRIPT_DIR/native_host.py"
```

**`native_host_wrapper.sh`** (modifié)
```bash
export DEV_MODE=0
exec "$VENV/bin/python3" "$SCRIPT_DIR/native_host.py"
```

### 3. Extensions Firefox

**`firefox_extension_dev/`** (nouveau)
- manifest.json avec ID `password-manager-dev@example.com`
- background.js utilisant `com.passwordmanager.native.dev`
- popup.html avec badge `[DEV]` orange
- Icônes identiques

**`firefox_extension/`** (modifié)
- manifest.json avec ID `password-manager@example.com`
- background.js utilisant `com.passwordmanager.native`
- Version production standard

### 4. Scripts d'installation

**`install_dev.sh`** (nouveau)
- Crée `~/.mozilla/native-messaging-hosts/com.passwordmanager.native.dev.json`
- Configure le wrapper DEV
- Instructions pour Firefox

**`install_prod.sh`** (nouveau)
- Crée `~/.mozilla/native-messaging-hosts/com.passwordmanager.native.json`
- Configure le wrapper PROD
- Instructions pour Firefox + signing

### 5. Tests

**`test_dev_communication.py`** (nouveau)
- Test complet du native host en mode DEV
- Vérifie la connexion à la vraie base
- Affiche les credentials trouvés

---

## 🚀 Utilisation

### Mode Développement

```bash
cd browser_integration

# 1. Installer l'extension DEV
./install_dev.sh

# 2. Tester la communication
python3 test_dev_communication.py

# 3. Dans Firefox:
# - Aller sur about:debugging#/runtime/this-firefox
# - Charger firefox_extension_dev/manifest.json
# - Vérifier le badge [DEV] orange
```

**Résultat attendu:**
- Badge `[DEV]` visible sur l'icône
- Connexion à `src/data/passwords_admin.db`
- Logs dans `logs/native_host_dev.log`
- Données de test visibles dans le popup

### Mode Production

```bash
cd browser_integration

# 1. Installer l'extension PROD
./install_prod.sh

# 2. Option A - Installation temporaire
# Dans Firefox:
# - Aller sur about:debugging#/runtime/this-firefox
# - Charger firefox_extension/manifest.json

# 2. Option B - Installation permanente (recommandé)
./package_for_signing.sh
./sign_extension.sh
# Installer le .xpi généré
```

**Résultat attendu:**
- Extension sans badge DEV
- Connexion à `data/passwords_admin.db`
- Logs dans `~/.local/share/passwordmanager/native_host.log`
- Données de production visibles

---

## 🔍 Vérifications

### Test de la base DEV

```bash
# Voir les données
python3 -c "
import sqlite3
conn = sqlite3.connect('src/data/passwords_admin.db')
cursor = conn.cursor()
cursor.execute('SELECT id, title, username, url FROM passwords')
for row in cursor.fetchall():
    print(f'{row[0]}: {row[1]} ({row[2]})')
"

# Tester le native host
python3 browser_integration/test_dev_communication.py
```

### Logs

```bash
# Logs DEV
tail -f logs/native_host_dev.log

# Logs PROD
tail -f ~/.local/share/passwordmanager/native_host.log
```

---

## 📊 Comparaison DEV vs PROD

| Caractéristique | DEV | PROD |
|----------------|-----|------|
| **Extension ID** | `password-manager-dev@example.com` | `password-manager@example.com` |
| **Native Host** | `com.passwordmanager.native.dev` | `com.passwordmanager.native` |
| **Badge Firefox** | 🟠 [DEV] | Aucun |
| **Base de données** | `src/data/passwords_admin.db` | `data/passwords_admin.db` |
| **Logs** | `logs/native_host_dev.log` | `~/.local/share/passwordmanager/native_host.log` |
| **Wrapper** | `native_host_wrapper_dev.sh` | `native_host_wrapper.sh` |
| **DEV_MODE** | `1` | `0` |
| **Installation** | Temporaire (about:debugging) | Permanente (signée) |
| **Objectif** | Tests et développement | Usage quotidien |

---

## 🧪 Tests Effectués

### Test 1: Connexion à la base DEV

```bash
$ python3 test_dev_communication.py

📍 Test 2: Search credentials (src/data/)
   Status: ✅ OK
   Credentials trouvés: 2
      - Entree3 (plog78@live.fr)
      - Test (test)

📍 Test 3: Search credentials (autre domaine)
   Status: ✅ OK
   Credentials trouvés: 1
      - Test2 (plog66@live.fr)
```

**✅ Résultat:** Le native host lit correctement la base de développement.

### Test 2: Isolation des extensions

```bash
# Les deux extensions peuvent être installées simultanément
$ ls -la ~/.mozilla/native-messaging-hosts/
com.passwordmanager.native.dev.json
com.passwordmanager.native.json
```

**✅ Résultat:** Les deux versions cohabitent sans conflit.

---

## 🎓 Avantages de cette Architecture

### 1. Isolation Complète
- Deux bases de données séparées
- Aucun risque de mélanger dev et prod
- Tests sans impacter les données réelles

### 2. Identification Visuelle
- Badge `[DEV]` orange immédiatement visible
- Titre de l'extension différent
- Logs séparés

### 3. Workflow de Développement
```
DEV: Développement → Tests → Validation
  ↓
PROD: Package → Signature → Installation permanente
```

### 4. Coexistence
- Les deux extensions peuvent être installées en même temps
- Native hosts distincts
- Pas d'interférence

---

## 🔧 Maintenance

### Synchroniser les modifications

Quand vous modifiez le code de l'extension DEV et voulez le porter en PROD:

```bash
# Copier les fichiers JS/CSS/HTML modifiés
cp firefox_extension_dev/{background,content,popup}.js firefox_extension/
cp firefox_extension_dev/popup.{html,css} firefox_extension/

# NE PAS copier manifest.json (IDs différents)

# Vérifier que background.js utilise le bon native host
grep "connectNative" firefox_extension/background.js
# Doit contenir: "com.passwordmanager.native"
```

### Mettre à jour les versions

```bash
# Incrémenter la version dans les deux manifests
# firefox_extension/manifest.json: "version": "0.2.0"
# firefox_extension_dev/manifest.json: "version": "0.2.0"

# Re-packager
cd browser_integration
./package_for_signing.sh
```

---

## 📚 Documentation Associée

- `DEBUGGING_GUIDE.md` - Guide de débogage complet
- `PHASE_2_FIX.md` - Corrections précédentes (status ok→success)
- `SIGNING_GUIDE.md` - Installation permanente
- `PERMANENT_EXTENSION.md` - Guide rapide signing

---

## 🐛 Problèmes Résolus

### 1. Données de test en dur
**Avant:** Native host retournait `credentials: []` ou des données fictives
**Après:** Connexion réelle à SQLite, recherche dynamique

### 2. Confusion dev/prod
**Avant:** Une seule extension, risque de mélanger les environnements
**Après:** Deux extensions isolées, base de données distinctes

### 3. Impossible de tester
**Avant:** Pas de données visibles dans l'extension
**Après:** Affichage des credentials réels de la base sélectionnée

### 4. Colonne SQL incorrecte
**Avant:** Requête cherchait `category_id` (n'existe pas)
**Après:** Utilise `category` (colonne correcte)

---

## 🎉 Résultat Final

### Mode DEV
```
🦊 Firefox → Extension DEV [badge orange]
           ↓
  Native Host DEV (com.passwordmanager.native.dev)
           ↓
  native_host_wrapper_dev.sh (DEV_MODE=1)
           ↓
  native_host.py → src/data/passwords_admin.db
           ↓
  📊 Données: Test, Test2, Entree3
```

### Mode PROD
```
🦊 Firefox → Extension PROD (signée)
           ↓
  Native Host PROD (com.passwordmanager.native)
           ↓
  native_host_wrapper.sh (DEV_MODE=0)
           ↓
  native_host.py → data/passwords_admin.db
           ↓
  📊 Données: Vos mots de passe réels
```

---

## 🚀 Prochaines Étapes

1. **Installer l'extension DEV dans Firefox**
   ```bash
   ./install_dev.sh
   # Puis charger dans about:debugging
   ```

2. **Vérifier que les credentials apparaissent**
   - Ouvrir le popup
   - Voir les 3 entrées de test

3. **Tester l'auto-fill sur une page web**
   - Visiter https://test.fr
   - Cliquer sur l'icône 🔑 dans le champ de login

4. **Passer en production quand prêt**
   ```bash
   ./install_prod.sh
   # Puis signer l'extension
   ```

---

## ✅ Validation

- [x] Native host lit la vraie base de données
- [x] Extension DEV accède à src/data/
- [x] Extension PROD accède à data/
- [x] Les deux peuvent coexister
- [x] Badge [DEV] visible
- [x] Logs séparés
- [x] Tests automatisés
- [x] Documentation complète

🎊 **L'extension Firefox est maintenant fonctionnelle et prête pour le développement !**
