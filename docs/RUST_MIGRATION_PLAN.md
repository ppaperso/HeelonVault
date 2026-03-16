# Plan De Migration Rust

Date de mise à jour : 16 mars 2026

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
- Les migrations SQL devaient être écrites avant l’UI car les repositories en dépendent au runtime. Cette étape est désormais réalisée.- Le bootstrap runtime (`main.rs`) est en place : ouverture de la base SQLite fichier, application des migrations au démarrage via `sqlx::migrate!`, composition complète des services, cycle de vie GTK4/libadwaita.
- L'UI démarre sur la base migrée réelle. Le contrat async est respecté : zéro accès DB/crypto sur le thread UI.
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

### Runtime Et Wiring

- Bootstrap complet dans `main.rs` : tokio multi-thread, ouverture SQLite fichier, application des migrations (`sqlx::migrate!`) au démarrage, gestion d'erreur sur base corrompue.
- Composition applicative câblée : `CryptoServiceImpl`, `AuthServiceImpl`, `VaultServiceImpl`, `SecretServiceImpl`, `PasswordServiceImpl`, `BackupServiceImpl` instanciés et injectés.
- `SqlxVaultEnvelopeRepository` implémenté inline dans `main.rs` pour le wiring de `VaultService`.
- Ressources GTK4 compilées via `build.rs` et registrées au démarrage (`gio::resources_register_include!`).
- Thème d'icônes, CSS applicatif et `APP_ID` en place.

### UI Rust Partiellement Implémentée

- `MainWindow` (~550 lignes) : fenêtre principale, liste des secrets, barre de recherche, sélecteur de vault, actions (ajout, édition, suppression soft, copie), intégration `SecretService` et `VaultService`.
- `LoginDialog` (~500 lignes) : dialogue d'authentification branché sur `AuthService`, gestion des callbacks succès/annulation, fermeture propre.
- `AddEditDialog` (~730 lignes) : création et édition de secret, sélecteur de type, générateur de mot de passe intégré, branché sur `SecretService` et `PasswordService`.

## Ce Qui Reste À Faire

### UI Rust — Stubs À Implémenter

Les composants suivants sont déclarés mais non implémentés (stub 1 ligne) :

- `SecurityDashboardWindow` : fenêtre tableau de bord sécurité — statistiques santé des secrets (expiration, force, réutilisation), état des vaults, accès backup. **Priorité haute.**
- `SecurityDashboardBar` : widget barre de statut sécurité pour la `MainWindow`.
- `PasswordStrengthBar` : widget visuel de force de mot de passe pour `AddEditDialog` et `LoginDialog`.
- `ManageUsersDialog` : dialogue de gestion des utilisateurs (création, suppression, changement de mot de passe) branché sur `AuthService`.

### Tests Et Validation Complémentaires

- Ajouter des tests d'intégration dans `tests/` qui utilisent les vraies migrations SQL au lieu de recréer les tables à la main dans chaque test.
- Ajouter des tests de non-régression autour de la cohérence du schéma et des contraintes SQL.
- Ajouter des tests bout-en-bout backend sur une base SQLite fichier (flux complet : migration → auth → vault → secret).
- Ajouter les benchmarks prévus sur KDF, chiffrement et opérations courantes.

### Points D'Attention

- `app.rs` contient uniquement `pub struct HeelonVaultApplication;` — ce stub n'est pas utilisé par le runtime actuel. À conserver ou supprimer selon l'évolution du cycle de vie applicatif.
- Le schéma SQL contient plus de colonnes que certains repositories n'utilisent encore. Faire converger progressivement modèles, repositories et services.
- `PasswordStrengthBar` et `SecurityDashboardBar` doivent être implémentés avant ou en parallèle de leurs fenêtres parentes pour éviter des écrans vides.

## Prochaine Étape Recommandée

Implémenter `SecurityDashboardWindow` et les widgets associés :

1. `PasswordStrengthBar` en widget autonome réutilisable (utilisé dans `AddEditDialog`).
2. `SecurityDashboardWindow` branchée sur `SecretService`, `VaultService`, `BackupService` et `PasswordService` pour afficher les métriques de santé.
3. `SecurityDashboardBar` comme widget résumé embeddable dans la `MainWindow`.
4. `ManageUsersDialog` en dernier car c'est un flux admin moins critique pour valider l'architecture principale.
