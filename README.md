# HeelonVault 0.9.1-beta

HeelonVault est un gestionnaire de secrets desktop **local-first**, écrit en Rust et construit
avec GTK4 / libadwaita et SQLite.

> **⚠️ Licence — Source-Available (non open source)**
> Le code source est publié **à des fins d'audit et de vérification de conformité uniquement**.
> Toute copie, modification ou redistribution est interdite sauf autorisation écrite d'HEELONYS.
> Consulter [LICENSE](LICENSE) et [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Fonctionnalités principales

| Domaine | Détail |
| ------- | ------ |
| **Chiffrement** | AES-256-GCM côté application — les secrets ne quittent jamais la machine en clair |
| **Authentification** | Hachage Argon2id (résistant aux GPU) + TOTP 2FA (RFC 6238) |
| **Multi-utilisateur** | Comptes séparés avec coffres isolés par utilisateur |
| **Persistance** | SQLite local, versionné par migrations `sqlx` (9 migrations, sans interruption de service) |
| **Import / Export** | Import CSV, export `.hvb` |
| **Corbeille** | Suppression logique avec restauration et purge définitive |
| **Auto-verrouillage** | Politique configurable : 1 / 5 / 15 / 30 minutes ou jamais |
| **Tableau de bord** | Fenêtre de sécurité dédiée avec score global du coffre |
| **Indicateur de force** | Évaluation `zxcvbn` en temps réel sur chaque mot de passe |
| **Recherche avancée** | Multi-champs (titre, login, email, URL, notes, catégorie, tags, type) avec normalisation Unicode |
| **Logs structurés** | Tracing JSON rotatif dans `~/.local/state/heelonvault/logs` |

---

## 🛡️ Audit & Conformité

Ce projet est conçu avec une architecture **security-first** pour garantir la conformité RGPD
et la protection des données utilisateurs.

### Licence et transparence

- **Source-Available** : le code est consultable pour audit de sécurité et vérification RGPD,
  mais protégé contre la copie et toute exploitation commerciale (voir [LICENSE](LICENSE)).
- **Inventaire des dépendances** : la totalité des 440 bibliothèques tierces (Rust + système)
  et leurs licences exactes sont documentées dans [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
- **Aucune dépendance copyleft** compilée statiquement dans le binaire — les seules bibliothèques
  LGPL (GTK4, libadwaita) sont liées dynamiquement par le système d'exploitation.

### Primitives cryptographiques

- **AES-256-GCM** (authentifié) — chiffrement des secrets via crate `aes-gcm` (RustCrypto).
- **Argon2id** — hachage des mots de passe utilisateur (résistant aux attaques par GPU/ASIC).
- **HMAC-SHA1 / SHA256** — génération des codes TOTP (RFC 6238) via crate `totp-rs`.
- **CSPRNG** — génération des sel/IV via `getrandom` (appel direct aux RNG du noyau).

### Politique de code

Un fichier [`clippy.toml`](clippy.toml) applique globalement l'interdiction des appels
`unwrap()` / `expect()` sur toutes les valeurs `Result` et `Option` :

```toml
# extrait de clippy.toml
disallowed-methods = [
  { path = "std::result::Result::unwrap",  reason = "Use typed errors (thiserror) on sensitive paths" },
  { path = "std::result::Result::expect",  reason = "Avoid panics and secret-leaking failure messages" },
  { path = "std::option::Option::unwrap",  reason = "Handle missing values explicitly" },
  { path = "std::option::Option::expect",  reason = "Handle missing values explicitly" }
]
```

Ceci garantit qu'aucune panique imprévue ne peut exposer de données sensibles en production.

### Signalement de vulnérabilités

Consulter [SECURITY.md](SECURITY.md) pour la politique de divulgation responsable.

---

## Structure du dépôt

```text
HeelonVault/
├── src/                   # Runtime principal Rust
│   ├── services/          # Logique métier (crypto, auth, TOTP, backup…)
│   ├── repositories/      # Couche d'accès SQLite
│   ├── models/            # Types de domaine
│   └── ui/                # Widgets GTK4 / libadwaita
├── migrations/            # 9 migrations SQL (sqlx)
├── resources/             # Ressources GTK (CSS, icônes, GResource)
├── tests/                 # Tests d'intégration Rust
├── docs/                  # Documentation technique et architecture
├── data/                  # Base de données dev locale
├── logs/                  # Logs runtime
├── Cargo.toml             # Manifest Cargo
├── clippy.toml            # Politique Clippy sécurité
├── LICENSE                # Licence source-available HEELONYS
├── THIRD_PARTY_LICENSES.md# Inventaire des bibliothèques tierces
├── SECURITY.md            # Politique de divulgation
├── run-dev.sh             # Lancement développement
├── run.sh                 # Lancement production (généré par install.sh)
└── install.sh             # Installateur Linux packagé
```

---

## Lancement rapide

### Développement

```bash
./run-dev.sh
```

Base de données dev : `data/heelonvault-rust-dev.db`

### Vérification build et lint

```bash
cargo check
cargo clippy -- -D warnings
```

### Installation Linux packagée

Le tarball de release (`heelonvault-linux-x86_64.tar.gz`) installe :

- le binaire dans `/opt/heelonvault/`;
- un lanceur GNOME `com.heelonvault.rust.desktop` (App ID GTK correspondant);
- les icônes dans le thème hicolor système;
- la base SQLite **par utilisateur** dans `~/.local/share/heelonvault/heelonvault-rust.db`;
- les logs **par utilisateur** dans `~/.local/state/heelonvault/logs`.

```bash
tar -xzf heelonvault-linux-x86_64.tar.gz
cd heelonvault-linux-x86_64
sudo ./install.sh
```

Consulter [QUICKSTART.md](QUICKSTART.md) pour les détails post-installation.

### Tests

```bash
cargo test
```

---

## Documentation

| Fichier | Contenu |
| ------- | ------- |
| [QUICKSTART.md](QUICKSTART.md) | Installation et premiers pas |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture technique détaillée |
| [docs/UPDATE_GUIDE.md](docs/UPDATE_GUIDE.md) | Procédure de mise à jour |
| [SECURITY.md](SECURITY.md) | Politique de sécurité et divulgation |
| [LICENSE](LICENSE) | Licence source-available HEELONYS |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | Inventaire complet des dépendances tierces |

---

## Notes de version 0.9.1-beta

### Authentification deux facteurs (TOTP)

- activation/désactivation du TOTP par l'utilisateur depuis le profil;
- génération et affichage du QR code de provisionnement;
- validation du code à 6 chiffres à la connexion;
- secret TOTP chiffré en base (migration `0009_user_totp_secret.sql`).

### UI / UX (hérité 0.9.0)

- stack principal avec vues inline pour le profil et l'édition des secrets;
- recherche multi-champs avec normalisation Unicode accents/casse;
- badge profil transformé en popover avec historique des 5 dernières connexions;
- préférence utilisateur `show_passwords_in_edit` persistée.

### Sécurité / session (hérité 0.9.0)

- auto-verrouillage avec retour garanti à l'écran de login;
- fermeture de fenêtre convertie en déconnexion propre;
- journalisation des connexions réussies (`login_history`).

### Données

- migration `0009_user_totp_secret.sql`;
- migration `0007_login_history.sql`;
- migration `0008_user_show_passwords_in_edit.sql`.
