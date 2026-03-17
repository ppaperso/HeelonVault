# Architecture du projet (Rust)

## Vue d'ensemble

HeelonVault est un projet Rust-first.

- Runtime applicatif: `rust/`
- UI desktop: GTK4 + libadwaita
- Base de donnees: SQLite
- Migrations SQL: `sqlx::migrate!` au demarrage
- Launchers racine: `run.sh` (prod), `run-dev.sh` (dev)

## Couches logiques

```text
UI (gtk4/libadwaita)
  -> Services metier
    -> Repositories (SQLx)
      -> SQLite + migrations
```

## Structure active

```text
HeelonVault/
├── rust/
│   ├── src/
│   │   ├── main.rs                 # Bootstrap runtime + UI
│   │   ├── ui/                     # Fenetres + dialogues GTK/adw
│   │   ├── services/               # Regles metier
│   │   ├── repositories/           # Acces DB (SQLx)
│   │   ├── models/                 # Types metier
│   │   ├── config/                 # Constantes/config runtime
│   │   └── errors/                 # Erreurs applicatives
│   ├── migrations/                 # Migrations SQL appliquees au demarrage
│   ├── tests/                      # Tests integration/securite
│   └── Cargo.toml
├── run.sh                          # Launcher production
├── run-dev.sh                      # Launcher developpement
├── install.sh                      # Installation Rust-only
├── update.sh                       # Mise a jour Rust-only + backup
└── docs/
```

## Flux de demarrage

1. `main.rs` initialise le runtime tokio.
2. Ouverture de la base SQLite via `HEELONVAULT_DB_PATH`.
3. Application des migrations SQL.
4. Construction des repositories/services.
5. Initialisation UI, authentification, puis fenetre principale.

## Chemins de donnees

- Dev: `data/heelonvault-rust-dev.db`
- Prod: `/var/lib/heelonvault-rust-shared/heelonvault.db`
- Legacy Python a ne pas toucher: `/var/lib/heelonvault-shared`

## Logs (runtime)

- Rotation journaliere active via `tracing-appender` (un fichier par jour).
- Dossier des logs configurable via `HEELONVAULT_LOG_DIR`.
- Niveau global configurable via `RUST_LOG` (prioritaire) puis `HEELONVAULT_LOG_LEVEL`.
- Defauts launchers:
  - Dev (`run-dev.sh`): `HEELONVAULT_LOG_LEVEL=debug`, `HEELONVAULT_LOG_DIR=./logs`
  - Prod (`run.sh`): `HEELONVAULT_LOG_LEVEL=info`, `HEELONVAULT_LOG_DIR=/var/lib/heelonvault-rust-shared/logs`
- Fichiers de rotation: `heelonvault.log.YYYY-MM-DD` dans le dossier configure.

Exemples:

```bash
# Compat standard Rust (prioritaire)
RUST_LOG=info,heelonvault_rust::ui=debug ./run-dev.sh

# Ou via variable applicative
HEELONVAULT_LOG_LEVEL=warn ./run.sh
```

## Tests et validation

Depuis `rust/`:

```bash
cargo check
cargo test
```

## Notes migration

- Le code legacy Python a ete retire du repository actif.
- Les docs et scripts operationnels doivent rester alignes sur le flux Rust-only.
