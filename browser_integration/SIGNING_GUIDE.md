# 🔏 Guide de Signature pour Extension Permanente

## 🎯 Objectif
Transformer votre extension temporaire en extension permanente installable dans Firefox.

## ✅ Package créé
Le fichier `packages/password-manager-0.1.0.zip` est prêt à être signé.

---

## 🚀 Méthode Recommandée : Signature avec web-ext

### Étape 1 : Créer un compte Mozilla
1. Aller sur https://addons.mozilla.org
2. Cliquer sur "Register" ou "Sign In"
3. Créer votre compte (gratuit)

### Étape 2 : Générer les clés API
1. Aller sur https://addons.mozilla.org/developers/addon/api/key/
2. Cliquer sur "Generate new credentials"
3. Donner un nom (ex: "Password Manager Extension")
4. **Copier et sauvegarder** :
   - `JWT issuer` (ressemble à : user:12345678:123)
   - `JWT secret` (longue chaîne aléatoire)
   
   ⚠️ **Important** : Gardez ces clés secrètes et en sécurité !

### Étape 3 : Installer web-ext
```bash
# Si vous avez npm installé
npm install -g web-ext

# Ou avec npx (pas besoin d'installer)
# Les commandes suivantes utiliseront npx
```

### Étape 4 : Signer l'extension
```bash
cd /home/ppaadmin/Vscode/Gestionnaire_mot_passe/browser_integration/firefox_extension

# Remplacer YOUR_JWT_ISSUER et YOUR_JWT_SECRET par vos vraies clés
npx web-ext sign \
  --api-key=YOUR_JWT_ISSUER \
  --api-secret=YOUR_JWT_SECRET \
  --channel=unlisted
```

**Note** : `--channel=unlisted` signifie que l'extension sera signée mais non listée sur addons.mozilla.org (pour usage personnel).

### Étape 5 : Récupérer l'extension signée
Après quelques minutes, un fichier `.xpi` sera créé dans :
```
firefox_extension/web-ext-artifacts/password_manager_integration-0.1.0.xpi
```

### Étape 6 : Installer l'extension signée
**Option A - Double-clic :**
```bash
firefox web-ext-artifacts/password_manager_integration-0.1.0.xpi
```

**Option B - Glisser-déposer :**
1. Ouvrir Firefox
2. Glisser le fichier `.xpi` dans la fenêtre Firefox
3. Cliquer sur "Add" / "Ajouter"

**✅ L'extension est maintenant permanente !**

---

## 🌐 Méthode Alternative : Signature Manuelle (Interface Web)

### Étape 1 : Se connecter
1. Aller sur https://addons.mozilla.org/developers/addons
2. Se connecter avec votre compte

### Étape 2 : Soumettre l'extension
1. Cliquer sur **"Submit a New Add-on"**
2. Choisir **"On this site"** (auto-distribution)
3. Accepter les conditions

### Étape 3 : Upload
1. Cliquer sur **"Select a file..."**
2. Sélectionner : `packages/password-manager-0.1.0.zip`
3. Cliquer sur **"Continue"**

### Étape 4 : Validation automatique
Mozilla va analyser l'extension (1-5 minutes) :
- ✅ Vérification du code
- ✅ Détection de malware
- ✅ Conformité aux règles

### Étape 5 : Télécharger le .xpi signé
1. Une fois validée, cliquer sur **"Download Signed File"**
2. Sauvegarder le fichier `.xpi`

### Étape 6 : Installer
- Double-cliquer sur le `.xpi`, OU
- Le glisser dans Firefox, OU
- `Outils > Add-ons > Installer depuis un fichier`

---

## 🔧 Méthode Développeur : Firefox Developer Edition

**Pour qui ?** Développeurs qui veulent garder le contrôle total.

### Étape 1 : Installer Firefox Developer Edition
```bash
# Fedora
sudo dnf install firefox-developer-edition

# Ou télécharger depuis
# https://www.mozilla.org/firefox/developer/
```

### Étape 2 : Désactiver la vérification de signature
1. Ouvrir Firefox Developer Edition
2. Taper dans la barre d'adresse : `about:config`
3. Accepter le risque
4. Rechercher : `xpinstall.signatures.required`
5. Double-cliquer pour passer à `false`

### Étape 3 : Installer l'extension non signée
1. Renommer le `.zip` en `.xpi` :
   ```bash
   cp packages/password-manager-0.1.0.zip packages/password-manager-0.1.0.xpi
   ```
2. Glisser le `.xpi` dans Firefox Developer

**⚠️ Limitations :**
- Fonctionne uniquement avec Firefox Developer ou Nightly
- Ne fonctionne PAS avec Firefox standard
- À utiliser uniquement pour le développement

---

## 🔄 Mises à jour de l'extension

### Quand vous modifiez l'extension :

1. **Incrémenter la version** dans `manifest.json` :
   ```json
   "version": "0.2.0"
   ```

2. **Re-packager** :
   ```bash
   ./package_for_signing.sh
   ```

3. **Re-signer** avec web-ext ou l'interface web

4. Firefox détectera automatiquement la mise à jour

---

## ❓ Dépannage

### "Extension is not properly signed"
→ Vous devez utiliser Firefox Developer Edition avec `xpinstall.signatures.required=false`

### "Could not sign add-on: Validation error"
→ Vérifier les erreurs dans la sortie de `web-ext sign`
→ Assurez-vous que le `manifest.json` est valide

### "API credentials are invalid"
→ Revérifier vos clés JWT_ISSUER et JWT_SECRET
→ Elles doivent être copiées exactement depuis addons.mozilla.org

### L'extension disparaît après redémarrage
→ Elle n'est pas signée. Utiliser une des méthodes ci-dessus.

### "This add-on is not compatible with your version of Firefox"
→ Vérifier `strict_min_version` dans manifest.json
→ Mettre à jour Firefox si nécessaire

---

## 📊 Comparaison des méthodes

| Méthode | Permanent ? | Firefox Standard ? | Difficulté | Temps |
|---------|-------------|-------------------|------------|-------|
| **web-ext** | ✅ Oui | ✅ Oui | ⭐⭐ Moyen | 10-15 min |
| **Interface Web** | ✅ Oui | ✅ Oui | ⭐ Facile | 5-10 min |
| **Developer Edition** | ✅ Oui | ❌ Non | ⭐ Facile | 2 min |

**🎯 Recommandation :**
- **Usage personnel** → Interface Web (Méthode 2)
- **Développement continu** → web-ext (Méthode 1)
- **Tests rapides** → Developer Edition (Méthode 3)

---

## 🎓 Ressources

- [Guide officiel de signature](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)
- [Documentation web-ext](https://extensionworkshop.com/documentation/develop/web-ext-command-reference/)
- [Portail développeurs Mozilla](https://addons.mozilla.org/developers/)
- [FAQ signature d'extensions](https://wiki.mozilla.org/Add-ons/Extension_Signing)

---

## ✨ Après la signature

Une fois votre extension signée et installée :

1. **L'icône 🔐 reste** dans la barre d'outils
2. **Fonctionne après redémarrage** de Firefox
3. **Pas besoin de la recharger** manuellement
4. **Mises à jour possibles** en re-signant les nouvelles versions

🎉 **Votre extension est maintenant professionnelle et permanente !**
