# HeelonVault 0.9.4-beta

Langue: FR | [EN](README.en.md)

HeelonVault est un gestionnaire de secrets desktop **local-first**, écrit en Rust et construit
avec GTK4 / libadwaita et SQLite.

> Distribué sous licence **Apache 2.0** — utilisation, modification et redistribution libres sous conditions Apache.
> Consulter [LICENSE](LICENSE) et [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Fonctionnalités principales

| Domaine | Détail |
| ------- | ------ |
| **Chiffrement** | AES-256-GCM côté application — les secrets ne quittent jamais la machine en clair |
| **Authentification** | Hachage Argon2id (résistant aux GPU) + TOTP 2FA (RFC 6238) |
| **Multi-utilisateur** | Comptes séparés avec coffres isolés par utilisateur |
| **Bootstrap** | Assistant d'initialisation guidé en 3 étapes pour la création du premier compte administrateur |
| **Clé de récupération** | Phrase mnémotechnique 24 mots (style BIP39) générée à l'initialisation ; exportable depuis le profil ; copie avec effacement presse-papier automatique (60 s) |
| **Persistance** | SQLite local, versionné par migrations `sqlx` (14 migrations, sans interruption de service) |
| **Import / Export** | Import CSV, export `.hvb` avec contrôle d'accès RBAC |
| **Journal d'audit** | Traçabilité des actions sensibles (création/modification/suppression de secrets, partages) |
| **Corbeille** | Suppression logique avec restauration et purge définitive |
| **Auto-verrouillage** | Politique configurable : 1 / 5 / 15 / 30 minutes ou jamais |
| **Tableau de bord** | Fenêtre de sécurité dédiée avec score global du coffre |
| **Indicateur de force** | Évaluation `zxcvbn` en temps réel sur chaque mot de passe |
| **Recherche avancée** | Multi-champs (titre, login, email, URL, notes, catégorie, tags, type) avec normalisation Unicode |
| **Licence** | Vérification Ed25519 de la licence signée ; badge visible avant et après login ; fallback Community automatique |
| **Logs structurés** | Tracing JSON rotatif dans `~/.local/state/heelonvault/logs` |

---

## 🛡️ Audit & Conformité

Ce projet est conçu avec une architecture **security-first** pour garantir la conformité RGPD
et la protection des données utilisateurs.

### Licence et transparence

- **Apache 2.0** : utilisation, modification et redistribution libres ; le copyright et la marque HeelonVault restent la propriété d'HEELONYS (voir [LICENSE](LICENSE)).
- **Inventaire des dépendances** : la totalité des bibliothèques tierces (Rust + système)
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
├── LICENSE                # Licence Apache 2.0
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
| [CHANGELOG.md](CHANGELOG.md) | Journal des modifications (FR) |
| [CHANGELOG.en.md](CHANGELOG.en.md) | Changelog (EN) |
| [QUICKSTART.md](QUICKSTART.md) | Installation et premiers pas |
| [QUICKSTART.fr.md](QUICKSTART.fr.md) | Guide de démarrage rapide (FR) |
| [docs/README.md](docs/README.md) | Index central de la documentation bilingue |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture technique détaillée |
| [docs/ARCHITECTURE.en.md](docs/ARCHITECTURE.en.md) | Technical architecture (EN) |
| [docs/UPDATE_GUIDE.md](docs/UPDATE_GUIDE.md) | Procédure de mise à jour |
| [docs/UPDATE_GUIDE.en.md](docs/UPDATE_GUIDE.en.md) | Production update guide (EN) |
| [SECURITY.md](SECURITY.md) | Politique de sécurité et divulgation |
| [SECURITY.fr.md](SECURITY.fr.md) | Politique de sécurité (FR) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guide (EN) |
| [CONTRIBUTING.fr.md](CONTRIBUTING.fr.md) | Guide de contribution (FR) |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Code de conduite (FR) |
| [CODE_OF_CONDUCT.en.md](CODE_OF_CONDUCT.en.md) | Code of Conduct (EN) |
| [LICENSE](LICENSE) | Licence Apache 2.0 |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | Inventaire complet des dépendances tierces |
| [THIRD_PARTY_LICENSES.fr.md](THIRD_PARTY_LICENSES.fr.md) | Guide FR des licences tierces |

---

> Les notes de version détaillées sont dans [CHANGELOG.md](CHANGELOG.md).
