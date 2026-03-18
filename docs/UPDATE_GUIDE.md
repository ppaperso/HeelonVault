# Guide de Mise a Jour en Production (Rust)

Version documentée: `0.2.0`

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

## Changements applicatifs 0.2.0 a verifier apres update

- migration `0007_login_history.sql` appliquee;
- migration `0008_user_show_passwords_in_edit.sql` appliquee;
- vue `Profil & Sécurité` accessible depuis la sidebar;
- fermeture de la fenêtre principale ramenant au login au lieu de quitter;
- édition de secret effectuée inline dans le panneau central.

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

# migrations presentes
ls -1 /opt/heelonvault/rust/migrations
```

Vérifications fonctionnelles recommandées:

1. Se connecter puis cliquer sur la croix de la fenêtre: l'écran de login doit réapparaître.
2. Se reconnecter immédiatement: la grille des cartes doit être rechargée.
3. Ouvrir `Profil & Sécurité` et changer la préférence d'affichage du mot de passe en édition.
4. Modifier un secret de type mot de passe pour vérifier le comportement du champ selon la préférence.

## Bonnes pratiques

- Toujours lancer `update.sh` depuis le code source cible.
- Verifier l'espace disque avant mise a jour (`df -h /var/backups`).
- Ne pas modifier les donnees pendant la mise a jour.
- Conserver plusieurs backups recents avant nettoyage manuel.

## A ne pas faire

- Ne pas reutiliser d'anciennes procedures `venv`/`pip`.
- Ne pas modifier les anciens chemins Python (`/var/lib/heelonvault-shared`).
- Ne pas contourner les erreurs backup: un echec backup doit bloquer l'update.
