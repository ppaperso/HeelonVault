# Locales (i18n)

Ce dossier est utilisé par `gettext` pour charger les traductions.

- Domaine: `passwordmanager`
- Exemple de structure:

```text
locales/
  fr/
    LC_MESSAGES/
      passwordmanager.mo
  en/
    LC_MESSAGES/
      passwordmanager.mo
```

## Génération (indicatif)

1. Extraire les chaînes marquées via `_()` depuis `src/`.
2. Générer un `.po`, puis compiler en `.mo`.

Le projet n'impose pas d'outil spécifique pour le moment (Babel, gettext CLI, etc.).
