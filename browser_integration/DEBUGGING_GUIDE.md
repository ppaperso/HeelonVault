# 🐛 Guide de Débogage - Extension Firefox

## Problème : "Erreur lors du chargement" dans le popup

### ✅ Corrections appliquées

1. **Synchronisation des statuts** : Le native host retourne maintenant `"status": "success"` au lieu de `"status": "ok"`
2. **Gestion des promesses** : Amélioration du système de matching des réponses dans `background.js`
3. **Données de test** : Ajout d'un compte de test pour vérifier que l'affichage fonctionne

### 🧪 Tests à effectuer

#### 1. Recharger l'extension dans Firefox

```bash
# Dans Firefox:
1. Ouvrir about:debugging#/runtime/this-firefox
2. Trouver "Password Manager"
3. Cliquer sur "Recharger"
```

#### 2. Vérifier les logs du navigateur

```bash
# Dans Firefox:
1. Cliquer sur l'icône de l'extension
2. Faire Ctrl+Shift+J pour ouvrir la console
3. Chercher les messages:
   - "Connecté au native host"
   - "Message reçu:"
   - "Réponse du native host:"
```

#### 3. Vérifier le native host

```bash
# Terminal:
cd browser_integration
./test_direct_communication.py

# Doit afficher:
# ✅ OK pour tous les tests
# "status": "success"
# "credentials": [...]
```

#### 4. Vérifier les logs du native host

```bash
tail -f ~/.local/share/passwordmanager/native_host.log

# Doit montrer:
# - "Message reçu: search_credentials"
# - "Message envoyé: search_response"
# Pas d'erreurs JSON
```

### 🔍 Debugging Console Firefox

Ouvrez la console du background script:
```
about:debugging#/runtime/this-firefox
→ Cliquer "Inspecter" sur Password Manager
```

Vérifiez:
- `isConnected` devrait être `true`
- `nativePort` ne devrait pas être `null`
- Les messages "Envoi au native host:" et "Réponse du native host:" doivent apparaître

### 📊 Structure attendue des réponses

**Ping:**
```json
{
  "action": "pong",
  "status": "success",
  "version": "0.3.0-beta"
}
```

**Search credentials:**
```json
{
  "action": "search_response",
  "status": "success",
  "url": "https://example.com",
  "credentials": [
    {
      "id": 1,
      "title": "Compte de test",
      "username": "utilisateur@example.com",
      "url": "https://example.com"
    }
  ]
}
```

### 🚨 Erreurs possibles

#### "Not connected to native host"
**Cause:** Le native host n'est pas démarré ou le manifest n'est pas correctement installé.

**Solution:**
```bash
# Vérifier l'installation
cd browser_integration
./install_firefox_extension.sh
```

#### "Timeout waiting for response"
**Cause:** Le native host ne répond pas assez vite.

**Solution:**
1. Vérifier que le wrapper fonctionne: `./native_host_wrapper.sh`
2. Vérifier les logs: `tail ~/.local/share/passwordmanager/native_host.log`
3. Tester directement: `./test_direct_communication.py`

#### "Erreur décodage JSON"
**Cause:** Le format des messages n'est pas correct.

**Solution:**
1. Vérifier que le venv est activé dans le wrapper
2. Tester la communication: `./test_direct_communication.py`

### 🎯 Données de test

Le native host retourne maintenant un compte de test pour vérifier l'affichage:

- **Titre:** Compte de test
- **Username:** utilisateur@example.com
- **Password:** MotDePasseTest123!
- **ID:** 1

Vous devriez voir ce compte apparaître dans la liste du popup.

### 🔧 Commandes utiles

```bash
# Réinstaller l'extension
cd browser_integration
./install_firefox_extension.sh

# Tester la communication
./test_direct_communication.py

# Voir les logs en temps réel
tail -f ~/.local/share/passwordmanager/native_host.log

# Nettoyer les logs
> ~/.local/share/passwordmanager/native_host.log

# Tester le manifest
firefox --new-tab about:debugging#/runtime/this-firefox
```

### 📝 Checklist

- [ ] Extension rechargée dans Firefox
- [ ] Console du background script ouverte
- [ ] Logs du native host suivis en temps réel
- [ ] Test de communication réussi
- [ ] Popup ouvert et console vérifiée
- [ ] Données de test visibles dans le popup

### ✨ Résultat attendu

Après ces corrections, vous devriez voir dans le popup:

```
🟢 Connecté

┌─────────────────────────────┐
│ 🔑 Compte de test          │
│ utilisateur@example.com     │
│ [Remplir] [Copier]          │
└─────────────────────────────┘
```

### 📚 Ressources

- [Native Messaging API](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging)
- [Debugging Extensions](https://extensionworkshop.com/documentation/develop/debugging/)
- [Console API](https://developer.mozilla.org/en-US/docs/Web/API/Console)
