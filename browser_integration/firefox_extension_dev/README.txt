Password Manager - Extension Firefox
====================================

Cette extension permet d'intégrer votre gestionnaire de mots de passe
avec Firefox pour :
- Auto-compléter les formulaires de connexion
- Rechercher vos identifiants
- Générer des mots de passe sécurisés
- Sauvegarder de nouveaux identifiants

Installation :
1. Ouvrir Firefox
2. Aller dans about:debugging
3. Cliquer sur "Ce Firefox" (This Firefox)
4. Cliquer sur "Charger un module temporaire"
5. Sélectionner le fichier manifest.json de cette extension

Note: L'extension doit être rechargée à chaque redémarrage de Firefox
sauf si elle est signée par Mozilla.

Pour un usage permanent, vous devez :
- Signer l'extension via https://addons.mozilla.org
- Ou utiliser Firefox Developer Edition / Nightly avec extensions.webextensions.keepUuidOnUninstall=true
