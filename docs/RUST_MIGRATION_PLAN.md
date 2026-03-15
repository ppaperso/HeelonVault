# Plan De Migration Rust

Date de mise à jour : 15 mars 2026

## Objectif

Créer un socle Rust sécurisé, testable et performant dans `rust/`, sans casser l’existant Python, avec une séparation nette entre modèles, repositories, services, migrations et future UI GTK4/libadwaita.

## Décisions D’Architecture Actées

- Le projet Rust vit dans `rust/` et reste autonome par rapport au runtime Python existant.
- Le schéma Rust démarre sur une base SQLite vierge. Il n’y a pas de migration des anciennes bases Python.
- Les dossiers Python de production `/var/lib/heelonvault-shared` et `/home/ppaadmin/.local/share/heelonvault` sont hors périmètre et ne doivent jamais être touchés.
- La pile backend retenue est `tokio` + `sqlx` + SQLite, avec travail hors thread UI pour DB et crypto.
- Le socle sécurité repose sur Argon2id, AES-256-GCM, `secrecy`, `zeroize`, `thiserror` et l’interdiction de `unwrap()` / `expect()` sur les chemins sensibles.
- `SecretService` est le service unique pour le stockage chiffré des secrets, y compris les secrets de type `password`.
- `PasswordService` est requalifié en service auxiliaire spécialisé uniquement pour la politique de mot de passe : validation, scoring, génération, détection de réutilisation. Il ne fait ni CRUD, ni chiffrement, ni accès repository.
- Les migrations SQL devaient être écrites avant l’UI car les repositories en dépendent au runtime. Cette étape est désormais réalisée.

## Plan Global

1. Cadrer l’architecture cible Rust et les frontières de couches.
2. Poser les règles de sécurité non négociables.
3. Définir les modèles de données Rust.
4. Définir la persistance SQLite versionnée.
5. Implémenter les repositories.
6. Implémenter les services backend.
7. Écrire les migrations SQL réelles.
8. Brancher ensuite l’UI Rust sur les services et repositories.
9. Renforcer les tests d’intégration et de validation runtime.

## Ce Qui Est Fait

### Structure Et Hardening

- Squelette complet du projet `rust/` créé.
- `Cargo.toml`, `README.md`, `src/`, `migrations/`, `tests/` en place.
- Hardening ajouté avec `clippy.toml` et `.cargo/config.toml`.
- Règles strictes de compilation et discipline sécurité posées.

### Contrats Et Erreurs

- `AppError` centralisé en place.
- Contrats async des repositories figés avec `Result<_, AppError>`.
- Usage normalisé de `SecretBox<Vec<u8>>` pour les données sensibles binaires.

### Services Implémentés

- `CryptoService`
  - dérivation Argon2id
  - chiffrement/déchiffrement AES-256-GCM
  - nonces aléatoires
- `AuthService`
  - création d’utilisateur
  - dérivation et vérification de mot de passe
  - gestion du shutdown
- `VaultService`
  - création de vault
  - génération et chiffrement de clé de vault
  - ouverture de vault
  - listing des vaults utilisateur
- `SecretService`
  - création de secret chiffré
  - récupération avec déchiffrement
  - listing par vault
  - soft delete
  - support des types `password`, `api_token`, `ssh_key`, `secure_document`
- `PasswordService`
  - validation de politique de mot de passe
  - scoring de robustesse
  - génération sécurisée
- `BackupService`
  - export chiffré de fichier SQLite
  - import depuis backup
  - vérification d’intégrité SHA-256 avant et après restauration

### Repositories Implémentés

- `UserRepository` avec SQLite `sqlx`
- `VaultRepository` avec SQLite `sqlx`
- `SecretRepository` avec SQLite `sqlx`

### Tests Déjà En Place

- Tests sécurité pour la crypto
- Tests sécurité pour l’auth
- Tests unitaires ou d’intégration sur les repositories
- Tests unitaires à base de stubs pour `VaultService`
- Tests unitaires pour `SecretService`
- Tests unitaires pour `PasswordService`
- Tests unitaires avec fichiers temporaires pour `BackupService`

### Migrations SQL Implémentées

- `0001_init_schema.sql`
  - tables `users` et `vaults`
  - index de recherche principaux
- `0002_db_metadata_schema_version.sql`
  - table `db_metadata`
  - insertion idempotente de `schema_version = '1'`
- `0003_secret_item_extensions.sql`
  - table `secret_items`
  - contraintes `secret_type` / `blob_storage`
  - index de recherche fréquente

## Ce Qui Reste À Faire

### Runtime Et Wiring

- Ajouter le point d’entrée runtime qui ouvre la base SQLite Rust et applique les migrations au démarrage.
- Vérifier que le cycle complet migration -> ouverture DB -> repositories fonctionne sur une vraie base fichier, pas seulement en mémoire.
- Connecter proprement les services entre eux dans une composition applicative claire.

### UI Rust

- Construire le squelette UI GTK4/libadwaita réel côté fenêtres, dialogues et widgets.
- Définir les flux UI vers `AuthService`, `VaultService`, `SecretService`, `PasswordService` et `BackupService`.
- Respecter le contrat UI async : pas de DB/crypto sur le thread UI, remontée d’état propre, fermeture contrôlée.

### Tests Et Validation Complémentaires

- Ajouter des tests d’intégration qui utilisent les vraies migrations SQL au lieu de recréer les tables à la main dans chaque test.
- Ajouter des tests de non-régression autour de la cohérence du schéma et des contraintes SQL.
- Ajouter des tests bout-en-bout backend sur une base SQLite fichier.
- Ajouter les benchmarks prévus sur KDF, chiffrement et opérations courantes.

### Points D’Attention

- Les repositories implémentés supposent désormais un schéma réel. Toute exécution runtime doit passer par les migrations.
- Le schéma SQL contient plus de colonnes que certains repositories n’utilisent encore. C’est acceptable, mais il faudra faire converger progressivement modèles, repositories et services.
- L’UI ne doit commencer qu’en s’appuyant sur la base migrée réelle, pas sur des hypothèses implicites de schéma.

## Reprise Recommandée Demain

1. Vérifier l’exécution réelle des migrations sur une base SQLite fichier.
2. Ajouter le bootstrap runtime de la base et des services.
3. Démarrer ensuite le squelette UI Rust et ses premiers écrans branchés sur les services.
