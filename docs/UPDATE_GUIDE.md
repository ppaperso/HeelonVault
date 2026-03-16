# Guide de Mise a Jour en Production (Rust)

Ce guide decrit la mise a jour de HeelonVault dans son architecture Rust-only.

## Portee

- Application: `/opt/heelonvault`
- Donnees Rust: `/var/lib/heelonvault-rust-shared`
- Backups: `/var/backups/heelonvault`
- Legacy Python a ne jamais modifier: `/var/lib/heelonvault-shared`

## Prerequis

1. L'application est deja installee via `install.sh`.
2. Vous avez les droits `sudo`.
3. Le toolchain Rust est disponible (`cargo`).
4. Vous etes dans le dossier source qui contient `update.sh`.

## Procedure de mise a jour

```bash
cd /chemin/vers/HeelonVault
sudo bash update.sh
```

Le script effectue:

1. Verification des preconditions (`sudo`, `cargo`, dossier d'installation).
2. Backup complet de `/opt/heelonvault` et `/var/lib/heelonvault-rust-shared`.
3. Verification d'integrite de l'archive backup.
4. Synchronisation des fichiers source vers `/opt/heelonvault` via `rsync`.
5. Build release Rust (`cargo build --release`).
6. Ajustement des permissions du dossier de donnees Rust.

## Restauration (rollback)

Si une mise a jour doit etre annulee:

```bash
# 1. Identifier le backup cible
ls -lth /var/backups/heelonvault/

# 2. Restaurer installation + donnees Rust
sudo tar -xzf /var/backups/heelonvault/heelonvault_YYYYMMDD_HHMMSS.tar.gz -C /

# 3. Relancer
/opt/heelonvault/run.sh
```

## Verification post-update

```bash
# binaire release present
test -x /opt/heelonvault/rust/target/release/heelonvault-rust && echo OK

# variable de chemin DB attendue par le launcher
sed -n '1,80p' /opt/heelonvault/run.sh

# build local de controle (optionnel)
cd /opt/heelonvault/rust && cargo check
```

## Bonnes pratiques

- Toujours lancer `update.sh` depuis le code source cible.
- Verifier l'espace disque avant mise a jour (`df -h /var/backups`).
- Ne pas modifier les donnees pendant la mise a jour.
- Conserver plusieurs backups recents avant nettoyage manuel.

## A ne pas faire

- Ne pas reutiliser d'anciennes procedures `venv`/`pip`.
- Ne pas modifier les anciens chemins Python (`/var/lib/heelonvault-shared`).
- Ne pas contourner les erreurs backup: un echec backup doit bloquer l'update.
