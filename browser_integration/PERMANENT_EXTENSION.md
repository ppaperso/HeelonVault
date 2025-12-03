# 🎯 Extension Permanente - Mode d'emploi Rapide

## ✅ Votre extension est packagée !

Le fichier `packages/password-manager-0.1.0.zip` (23 Ko) est prêt à être signé.

---

## 🚀 Installation Permanente en 3 étapes

### Méthode Automatique (Recommandée)

```bash
# Étape 1 : Packager (Déjà fait ✅)
./package_for_signing.sh

# Étape 2 : Signer avec vos clés API Mozilla
./sign_extension.sh

# Étape 3 : Installer le .xpi créé
# Le script vous proposera de l'installer automatiquement
```

### Méthode Manuelle (Interface Web)

1. **Créer un compte** sur https://addons.mozilla.org *(2 minutes)*

2. **Soumettre l'extension** :
   - Aller sur https://addons.mozilla.org/developers/addons
   - Cliquer sur "Submit a New Add-on"
   - Choisir "On this site" (self-distribution)
   - Uploader `packages/password-manager-0.1.0.zip`

3. **Télécharger le .xpi signé** après validation *(5-10 minutes)*

4. **Installer** en double-cliquant sur le `.xpi`

---

## 🔑 Obtenir les clés API (une seule fois)

Pour `./sign_extension.sh`, vous aurez besoin de clés API :

1. Aller sur https://addons.mozilla.org/developers/addon/api/key/
2. Cliquer sur **"Generate new credentials"**
3. Copier :
   - **JWT issuer** (ex: `user:12345:678`)
   - **JWT secret** (longue chaîne)
4. Les coller quand `./sign_extension.sh` les demande

Le script peut **sauvegarder** ces clés pour les prochaines fois.

---

## ⏱️ Comparaison des temps

| Méthode | Première fois | Fois suivantes |
|---------|---------------|----------------|
| **Script automatique** | 10-15 min | 2-3 min |
| **Interface Web** | 5-10 min | 5 min |
| **Firefox Developer** | 2 min | 2 min |

---

## ✨ Avantages de l'extension permanente

✅ **Reste installée** après redémarrage de Firefox
✅ **Icône toujours visible** dans la barre d'outils
✅ **Pas besoin** de la recharger manuellement
✅ **Fonctionne** sur tous les profils Firefox
✅ **Mises à jour** faciles (re-signer les nouvelles versions)

---

## 📚 Besoin d'aide ?

- **Guide complet** : `SIGNING_GUIDE.md`
- **Problèmes** : Voir section "Dépannage" dans SIGNING_GUIDE.md
- **Questions API** : https://extensionworkshop.com/documentation/publish/

---

## 🎓 Ce qui se passe lors de la signature

1. Mozilla **analyse** le code de l'extension
2. **Vérifie** qu'il n'y a pas de malware
3. **Certifie** que l'extension est sûre
4. **Crée** un fichier `.xpi` signé avec certificat
5. **Retourne** le fichier prêt à installer

**Temps de traitement** : 2-5 minutes généralement

---

## 🔄 Pour les mises à jour

Quand vous modifiez l'extension :

1. **Modifier** le code dans `firefox_extension/`
2. **Incrémenter** la version dans `manifest.json` :
   ```json
   "version": "0.2.0"
   ```
3. **Re-packager** : `./package_for_signing.sh`
4. **Re-signer** : `./sign_extension.sh` (clés déjà sauvegardées ✅)
5. **Installer** la nouvelle version

Firefox **remplacera** automatiquement l'ancienne version.

---

## 💡 Conseil Pro

Créez un alias pour simplifier :

```bash
# Ajouter à votre ~/.bashrc
alias sign-extension='cd /chemin/vers/browser_integration && ./sign_extension.sh'
```

Ensuite, tapez juste `sign-extension` de n'importe où !

---

## ⚡ Résumé Ultra-Rapide

```bash
# Première fois (une seule fois)
1. Créer compte sur addons.mozilla.org
2. Générer clés API
3. ./sign_extension.sh
4. Coller les clés
5. Attendre 2-5 minutes
6. Double-clic sur le .xpi créé

# Mises à jour (à chaque changement)
1. Modifier manifest.json (version)
2. ./package_for_signing.sh
3. ./sign_extension.sh (clés auto)
4. Double-clic sur le .xpi
```

🎉 **C'est tout !**
