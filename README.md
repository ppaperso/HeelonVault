# HeelonVault 0.2.0

HeelonVault est un gestionnaire de secrets desktop en Rust, construit avec GTK4/libadwaita et SQLite.

La version 0.2.0 stabilise le runtime Rust-only et introduit une passe UI/UX importante:

- vue principale dimensionnée dynamiquement au lancement;
- navigation inline `Profil & Sécurité` dans la page principale;
- création/édition de secrets en vue inline au lieu d'une fenêtre modale;
- historique des 5 dernières connexions dans le badge profil;
- déconnexion propre au clic sur la croix de la fenêtre et lors de l'auto-verrouillage;
- recherche multi-champs avancée (titre, login, email, URL, notes, catégorie, tags, type) avec normalisation accents/casse;
- préférence utilisateur pour afficher le mot de passe courant en édition de secret.

## Fonctionnalités principales

- chiffrement des secrets côté application;
- gestion multi-utilisateur;
- coffre SQLite versionné par migrations `sqlx`;
- import CSV et export `.hvb`;
- corbeille avec restauration et purge définitive;
- politique d'auto-verrouillage configurable (`1`, `5`, `15`, `30` minutes ou `jamais`).

## Structure du dépôt

```text
HeelonVault/
├── src/                   # Runtime principal Rust
├── migrations/            # Migrations SQL
├── resources/             # Ressources GTK/libadwaita
├── tests/                 # Tests d'integration Rust
├── docs/                  # Documentation fonctionnelle et technique
├── data/                  # Base de données dev locale
├── logs/                  # Logs runtime
├── Cargo.toml             # Manifest Cargo racine
├── run-dev.sh             # Lancement développement
├── run.sh                 # Lancement production
├── install.sh             # Installation
└── update.sh              # Mise à jour + backup
```

## Lancement rapide

### Développement

```bash
./run-dev.sh
```

Base dev utilisée:

- `data/heelonvault-rust-dev.db`

### Vérification build

```bash
cargo check
```

### Tests

```bash
cargo test
```

## Documentation utile

- `QUICKSTART.md`
- `docs/ARCHITECTURE.md`
- `docs/UPDATE_GUIDE.md`
- `SECURITY.md`
- `docs/PLAN_ADD_UPDATE_TRASH_SECRET.md`

## Notes de version 0.2.0

### UI / UX

- stack principal avec vues inline pour le profil et l'édition des secrets;
- hints visuels améliorés sur l'édition des mots de passe;
- tooltips explicites dans la zone Sécurité du profil;
- badge profil transformé en popover informatif avec historique de connexions.

### Sécurité / session

- auto-verrouillage avec retour garanti à l'écran de login;
- fermeture de la fenêtre principale convertie en déconnexion propre;
- journalisation des connexions réussies (`login_history`);
- préférence utilisateur persistée `show_passwords_in_edit`.

### Données

- migration `0007_login_history.sql`;
- migration `0008_user_show_passwords_in_edit.sql`.
