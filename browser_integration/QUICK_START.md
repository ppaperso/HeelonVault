# 🚀 Guide de Démarrage Rapide - Extension Firefox

## Installation en 3 étapes

### 1️⃣ Installer le Native Host
```bash
cd browser_integration
./install_native_host.sh
```

### 2️⃣ Charger l'extension dans Firefox
1. Ouvrir Firefox
2. Taper dans la barre d'adresse : `about:debugging#/runtime/this-firefox`
3. Cliquer sur **"Charger un module complémentaire temporaire..."**
4. Naviguer vers : `browser_integration/firefox_extension/`
5. Sélectionner le fichier **`manifest.json`**

### 3️⃣ Vérifier que ça fonctionne
1. Une icône 🔐 apparaît dans la barre d'outils Firefox
2. Cliquez dessus → le popup s'ouvre
3. Le statut doit afficher **"Connecté"** avec un point vert 🟢

## 🎯 Utilisation

### Auto-remplissage de formulaires
1. Visitez un site avec un formulaire de login (ex: github.com)
2. Un bouton **🔑** apparaît près du champ mot de passe
3. Cliquez dessus pour sélectionner un identifiant
4. Le formulaire est rempli automatiquement !

### Générer un mot de passe
1. Cliquez sur l'icône 🔐 dans la barre d'outils
2. Cliquez sur **"🎲 Générer"**
3. Un mot de passe sécurisé de 20 caractères apparaît
4. Cliquez sur 📋 pour copier

### Rechercher un identifiant
1. Ouvrez le popup (icône 🔐)
2. Tapez dans la barre de recherche
3. Cliquez sur **"🔑 Remplir"** ou **"📋"** (copier)

### Sauvegarder un nouveau compte
1. Connectez-vous normalement sur un nouveau site
2. Après soumission, un popup propose de sauvegarder
3. Cliquez sur **"Sauvegarder"**
4. L'identifiant sera disponible pour les prochaines visites

## ⚠️ Important

- **L'extension est temporaire** : elle disparaît au redémarrage de Firefox
- Pour la garder de façon permanente, vous devez la signer sur [addons.mozilla.org](https://addons.mozilla.org)
- Le Native Host doit être installé et l'application Password Manager lancée

## 🐛 Problèmes courants

**Statut "Déconnecté" ?**
→ Vérifier que le native host est installé : `./test_native_host.sh`

**Le bouton 🔑 n'apparaît pas ?**
→ Recharger la page (Ctrl+R)

**Extension disparue au redémarrage ?**
→ Normal en mode développement, la recharger via `about:debugging`

## 📚 Documentation complète
→ Voir `browser_integration/README.md`
