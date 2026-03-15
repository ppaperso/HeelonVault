# Guide d'importation CSV

## Vue d'ensemble

Le gestionnaire de mots de passe permet d'importer vos mots de passe depuis d'autres applications via des fichiers CSV. Cette fonctionnalité facilite la migration depuis LastPass, 1Password, Bitwarden et autres gestionnaires.

## Formats supportés

### LastPass (recommandé)

- **Délimiteur** : Point-virgule (`;`)
- **Ordre des colonnes** : `url;username;password;name`
- **Exemple** :

  ```text
  https://github.com;john.doe@email.com;MySecretPass123!;GitHub Account
  https://gmail.com;jane.smith@gmail.com;Gmail2024Secure;Gmail Personnel
  ```

### Format CSV générique (virgule)

- **Délimiteur** : Virgule (`,`)
- **Ordre des colonnes** : `url,username,password,name`
- **Exemple** :

  ```text
  https://example.com,user1,pass123,My Account
  ```

### Format CSV générique (point-virgule)

- **Délimiteur** : Point-virgule (`;`)
- **Ordre des colonnes** : `url;username;password;name`

## Comment importer vos mots de passe

### Étape 1 : Exporter depuis votre gestionnaire actuel

#### LastPass

1. Connectez-vous à votre compte LastPass
2. Allez dans **Compte** → **Options avancées** → **Exporter**
3. Entrez votre mot de passe maître
4. Sauvegardez le fichier CSV

#### 1Password

1. Ouvrez 1Password
2. Allez dans **Fichier** → **Exporter** → **Tous les éléments**
3. Choisissez le format CSV
4. Sauvegardez le fichier

#### Bitwarden

1. Connectez-vous à Bitwarden
2. Allez dans **Outils** → **Exporter le coffre**
3. Sélectionnez le format `.csv`
4. Sauvegardez le fichier

### Étape 2 : Préparer le fichier CSV

Assurez-vous que votre fichier CSV respecte le format attendu :

```csv
url;username;password;name
```

**Important** :

- Le délimiteur doit être cohérent (`;` ou `,`)
- L'ordre des colonnes doit être respecté
- Les champs peuvent être vides mais les point-virgules doivent rester

**Exemple avec champs vides** :

```csv
https://example.com;;mypassword;Site sans username
;user@email.com;pass123;Entrée sans URL
```

### Étape 3 : Importer dans le gestionnaire

1. **Lancez l'application** et connectez-vous
2. **Ouvrez le menu** (icône trois points en haut à droite)
3. **Sélectionnez "Importer depuis CSV"**
4. **Choisissez votre fichier** CSV
5. **Sélectionnez le format** :
   - LastPass (pour les exports LastPass)
   - Format générique CSV (virgule)
   - Format générique CSV (point-virgule)
6. **Activez "Première ligne = en-tête"** si votre fichier contient une ligne d'en-tête
7. **Cliquez sur "Importer"**

### Étape 4 : Vérifier l'importation

Après l'import :

- Un résumé s'affiche avec le nombre d'entrées importées
- Les avertissements éventuels sont listés
- Les entrées importées sont marquées avec la catégorie "Importé" et le tag "import"
- Vous pouvez les retrouver facilement dans votre liste

## Résolution des problèmes

### Format non reconnu

**Problème** : Le format du fichier n'est pas reconnu automatiquement

**Solution** :

1. Ouvrez le fichier CSV dans un éditeur de texte
2. Vérifiez le délimiteur utilisé (`;` ou `,`)
3. Sélectionnez manuellement le format dans le dialogue d'import

### Erreurs d'encodage

**Problème** : Les caractères spéciaux (accents, emojis) ne s'affichent pas correctement

**Solution** :

1. Ouvrez le fichier CSV dans un éditeur de texte
2. Sauvegardez-le en UTF-8
3. Réessayez l'import

### Mots de passe manquants

**Problème** : Certaines entrées n'ont pas de mot de passe

**Solution** :

- L'import continuera mais vous recevrez un avertissement
- Complétez manuellement les mots de passe manquants après l'import

### Entrées dupliquées

**Problème** : Certaines entrées existent déjà

**Solution** :

- L'import créera des doublons
- Supprimez manuellement les doublons après vérification

## Sécurité

### Bonnes pratiques

1. **Supprimez le fichier CSV après l'import**

   ```bash
   shred -u -z -v -n 3 export.csv
   ```

2. **Vérifiez les permissions**
   - Le fichier CSV ne doit être lisible que par vous
   - Utilisez `chmod 600 export.csv` avant l'import

3. **N'envoyez jamais de CSV par email**
   - Les emails ne sont pas chiffrés
   - Les fichiers CSV contiennent vos mots de passe en clair

4. **Vérifiez vos mots de passe importés**
   - Assurez-vous qu'ils fonctionnent
   - Changez les mots de passe critiques après migration

### Que se passe-t-il avec vos données ?

- Les mots de passe sont **immédiatement chiffrés** avec votre clé maître lors de l'import
- Le fichier CSV n'est **jamais copié** ni stocké par l'application
- Les données sont **uniquement lues** depuis le fichier que vous sélectionnez
- Après l'import, tout est **chiffré dans la base de données**

## Format détaillé des colonnes

### url

- URL complète du site web
- Peut être vide
- Exemple : `https://github.com`

### username

- Identifiant, nom d'utilisateur ou email
- Peut être vide
- Exemple : `john.doe@email.com`

### password

- Mot de passe en clair (sera chiffré lors de l'import)
- **Obligatoire** (un avertissement sera émis si vide)
- Exemple : `MySecretPass123!`

### name

- Nom descriptif de l'entrée
- Si vide, un nom par défaut sera généré
- Exemple : `Mon compte GitHub`

## Fichiers d'exemple

Deux fichiers d'exemple sont fournis :

1. **`test_import_lastpass.csv`** - Sans ligne d'en-tête
2. **`test_import_lastpass_with_header.csv`** - Avec ligne d'en-tête

Vous pouvez les utiliser pour tester la fonctionnalité d'import.

## Support

Pour toute question ou problème :

1. Vérifiez les logs dans `~/.local/share/passwordmanager/security.log`
2. Consultez la documentation complète dans `docs/`
3. Ouvrez une issue sur le dépôt du projet
