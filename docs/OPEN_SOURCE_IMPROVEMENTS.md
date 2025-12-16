# Pistes d'amélioration pour l'ouverture du projet

Ce document regroupe les principales recommandations identifiées pour faire évoluer le gestionnaire de mots de passe vers une application open source pérenne.

## Architecture et modularisation --> Done
- **Scinder `password_manager.py`** : isoler UI, services (gestion utilisateurs, crypto, sauvegardes), couche d'accès base et dialogues pour réduire le fichier monolithique et faciliter les contributions ciblées.
- **Introduire des `@dataclass`** pour représenter les entités clés (utilisateur, entrée, sauvegarde). Cela remplace les dictionnaires dynamiques et renforce l'autocomplétion/type checking.
- **Ajouter un layer de repository** (ou adopter SQLModel/SQLAlchemy) afin de centraliser les requêtes SQLite, préparer d'éventuelles migrations et permettre un mode headless/CLI.

## UX / UI --> Done
- **Internationalisation** : externaliser les chaînes transposables (gettext, fichiers `.ui`, etc.) pour permettre à la communauté de traduire rapidement l'application.
- **Notifications cohérentes** : remplacer les `print()` restants par des logs + `Adw.Toast`/`Adw.MessageDialog` en cas d'erreur critique (copie presse-papiers, ouverture URL...).

## Sécurité et bonnes pratiques --> A faire
- **Onboarding sécurisé** : supprimer l'utilisateur `admin/admin` en production et proposer un assistant imposant la définition d'un mot de passe fort au premier lancement.
- **Chiffrement étendu** : documenter les champs non chiffrés (username/category/tags) ou offrir un mode « full encryption » (SQLCipher) pour un stockage entièrement chiffré.
- **Mode CLI / headless** : exposer des commandes (`python -m password_manager --export ...`) pour intégrer l'outil dans des scripts et faciliter l'audit des fonctionnalités core sans interface graphique.

## Industrialisation open source
- **Fichiers de projet** : fournir un `pyproject.toml`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` et une licence explicite.
- **CI/CD** : ajouter un workflow GitHub Actions qui exécute `ruff`, les tests unitaires/integration et éventuellement un packaging flatpak/appimage.
- **Documentation** : prolonger les guides dans `docs/` (architecture, contributions, sécurité) et publier un README multilingue avec captures d'écran et instructions d'installation.

## Observations diverses
- Standardiser l'usage du logger sur l'ensemble du code (y compris `browser_integration/`).
- Uniformiser la gestion des erreurs (exceptions explicites, messages utilisateur traduisibles).
- Prévoir un format d'export JSON documenté pour favoriser l'interopérabilité (extensions navigateur, API REST potentielle).

Ces actions permettront de rendre le projet plus accueillant pour les contributeurs, plus auditable sur le plan sécurité, et plus simple à maintenir dans la durée. 