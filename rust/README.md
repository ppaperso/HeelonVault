# HeelonVault Rust Skeleton

Ce dossier contient le socle Rust de migration pour HeelonVault, sans logique fonctionnelle.

## Objectifs
- Poser une architecture propre et testable (`models`, `repositories`, `services`, `ui`, `config`).
- Intégrer dès le départ les exigences sécurité non négociables.
- Préparer une migration incrémentale sans impacter le code Python existant.

## Choix techniques
- `gtk4` + `libadwaita`: future UI desktop native GNOME.
- `sqlx` (SQLite, macros): requêtes validées à la compilation.
- `tokio`: runtime async pour isoler I/O et DB hors thread UI GTK.
- `argon2`: KDF Argon2id (remplacement PBKDF2).
- `aes-gcm`: chiffrement AES-256-GCM.
- `secrecy` + `zeroize`: hygiène mémoire pour données sensibles.
- `totp-rs`: fondation 2FA TOTP.
- `uuid`: identifiants stables (vaults/items/users).
- `thiserror`: erreurs typées sans `unwrap()` sur chemins sensibles.

## Notes d'architecture
- UI GTK reste sur son event loop principal.
- Les opérations DB/crypto sont destinées à s'exécuter hors thread UI.
- Le schéma SQLite sera versionné via `db_metadata(schema_version)` (migrations à implémenter plus tard).

## Périmètre actuel
- Structures de modules et types/traits vides.
- Fichiers de migration SQL versionnés et volontairement vides.
- Aucun comportement métier implémenté.
