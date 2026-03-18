# HeelonVault Rust Runtime

Ce dossier contient le runtime actif de HeelonVault en Rust.

## État actuel

- version applicative: `0.2.0`;
- UI GTK4/libadwaita opérationnelle;
- base SQLite avec migrations automatiques au démarrage;
- services métier et tests d'intégration actifs;
- launchers racine `run-dev.sh` et `run.sh` utilisés comme point d'entrée.

## Capacités livrées

- authentification multi-utilisateur;
- coffre de secrets avec création, édition inline et corbeille;
- profil et sécurité dans une vue inline dédiée;
- export `.hvb` et import CSV;
- historique de connexions récentes;
- recherche avancée multi-champs;
- déconnexion propre au close window et à l'auto-lock.

## Commandes utiles

```bash
cd rust
cargo check
cargo test
```

## Notes techniques

- `tokio` est utilisé pour isoler DB/crypto hors thread GTK;
- `sqlx::migrate!()` applique les migrations au lancement;
- `secrecy` et `zeroize` encadrent les données sensibles;
- les préférences utilisateur incluent désormais `show_passwords_in_edit`.

## Migrations récentes

- `0007_login_history.sql`: journalisation des connexions réussies;
- `0008_user_show_passwords_in_edit.sql`: préférence d'affichage du mot de passe en édition.
