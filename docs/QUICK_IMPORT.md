# Guide rapide d'importation CSV

## 📦 Import depuis LastPass

### 1. Exporter depuis LastPass

1. Connectez-vous à [LastPass](https://www.lastpass.com)
2. Allez dans **Compte** → **Options avancées** → **Exporter**
3. Entrez votre mot de passe maître
4. Copiez les données ou sauvegardez le fichier CSV

### 2. Importer dans le gestionnaire

1. **Lancez l'application** et connectez-vous avec votre compte
2. **Cliquez sur le menu** (☰ en haut à droite)
3. **Sélectionnez "Importer depuis CSV"**
4. **Choisissez votre fichier** d'export LastPass
5. **Sélectionnez "LastPass"** comme format
6. **Activez "Première ligne = en-tête"** si nécessaire
7. **Cliquez sur "Importer"**

### 3. Vérifier et nettoyer

- Vérifiez que vos mots de passe sont bien importés
- Les entrées importées sont dans la catégorie "Importé" avec le tag "import"
- **Supprimez le fichier CSV** après l'import :

  ```bash
  shred -u -z -v -n 3 lastpass_export.csv
  ```

## 🔐 Format du fichier CSV

Le format LastPass attendu est :

```text
url;username;password;name
```

**Exemple** :

```csv
https://github.com;john@email.com;MyPass123;GitHub
https://gmail.com;jane@email.com;GmailPass;Gmail
```

## ⚠️ Sécurité

- ❌ **Ne partagez JAMAIS** votre fichier d'export CSV
- ❌ **Ne l'envoyez JAMAIS** par email
- ✅ **Supprimez-le immédiatement** après l'import
- ✅ **Vérifiez les permissions** du fichier avant l'import

## 🆘 Problèmes courants

**Le format n'est pas reconnu** → Ouvrez le fichier dans un éditeur et vérifiez que le délimiteur est bien `;`

**Caractères bizarres** → Sauvegardez le fichier en UTF-8

**Mots de passe manquants** → Vous recevrez un avertissement, complétez-les manuellement après l'import

## 📖 Documentation complète

Pour plus de détails, consultez [CSV_IMPORT_GUIDE.md](CSV_IMPORT_GUIDE.md)
