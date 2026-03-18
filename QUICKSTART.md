# Quickstart (Rust)

Version rapide documentée: `0.2.0`

## 1. Build Check

```bash
cd rust
cargo check
```

## 2. Run in Development

From repository root:

```bash
./run-dev.sh
```

Development database path:

- `data/heelonvault-rust-dev.db`

## 3. Run Tests

```bash
cd rust
cargo test secret_repository:: -- --nocapture
cargo test secret_service:: -- --nocapture
cargo test --test login_history_integration
```

## 3bis. Vérifications UI recommandées

1. Ouvrir `Profil & Sécurité` depuis la sidebar.
2. Fermer la fenêtre principale avec la croix: le login doit réapparaître.
3. Se reconnecter immédiatement: les cartes de secrets doivent être visibles.
4. Activer l'affichage du mot de passe en édition, puis modifier un secret de type mot de passe.

## 4. Production Build

```bash
cd rust
cargo build --release
```

The production launcher expects:

- Binary path: `/opt/heelonvault/rust/target/release/heelonvault-rust`
- Launcher: `/opt/heelonvault/run.sh`
- Production database path: `/var/lib/heelonvault-rust-shared/heelonvault.db`

Legacy path protection:

- Do not modify or delete `/var/lib/heelonvault-shared` (legacy Python data).
