# HeelonVault 0.9.2-beta

Language: EN | [FR](README.md)

HeelonVault is a local-first desktop secrets manager built in Rust with GTK4/libadwaita and SQLite.

> **⚠️ License - Source-Available (not open source)**
> The source code is published for audit and compliance verification purposes only.
> Copying, modification, and redistribution are prohibited unless explicitly authorized in writing by HEELONYS.
> See [LICENSE](LICENSE) and [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Core Features

| Area | Details |
| ---- | ------- |
| **Encryption** | AES-256-GCM at application level; secrets never leave the machine in plaintext |
| **Authentication** | Argon2id password hashing + TOTP 2FA (RFC 6238) |
| **Multi-user** | Isolated accounts and vaults per user |
| **Persistence** | Local SQLite with versioned `sqlx` migrations |
| **Import / Export** | CSV import, `.hvb` export |
| **Trash** | Soft-delete with restore and permanent purge |
| **Auto-lock** | Configurable policy: 1 / 5 / 15 / 30 minutes or never |
| **Dashboard** | Dedicated security dashboard with global vault score |
| **Strength Meter** | Real-time `zxcvbn` evaluation for each password |
| **Advanced Search** | Multi-field search with Unicode normalization |
| **Structured Logs** | Rotating JSON logs in `~/.local/state/heelonvault/logs` |

---

## Audit and Compliance

HeelonVault follows a security-first approach for GDPR-oriented data protection.

### License and transparency

- **Source-Available**: code is readable for security and GDPR verification, but protected against copying and commercial reuse (see [LICENSE](LICENSE)).
- **Dependency inventory**: complete third-party component list and licenses are documented in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
- **LGPL runtime linking**: GTK4/libadwaita are dynamically linked by the operating system.

### Cryptographic primitives

- **AES-256-GCM** for authenticated encryption (`aes-gcm` crate).
- **Argon2id** for password hashing.
- **HMAC-SHA1 / SHA256** for TOTP generation (`totp-rs`).
- **CSPRNG** via `getrandom`.

### Error-handling policy

`clippy.toml` forbids panic-prone `unwrap()` / `expect()` calls on sensitive paths to reduce crash-leak risks.

### Vulnerability reporting

See [SECURITY.md](SECURITY.md).

---

## Repository Structure

```text
HeelonVault/
├── src/                   # Main Rust runtime
│   ├── services/          # Business logic (crypto, auth, TOTP, backup...)
│   ├── repositories/      # SQLite access layer
│   ├── models/            # Domain types
│   └── ui/                # GTK4 / libadwaita UI
├── migrations/            # SQL migrations
├── resources/             # GTK resources (CSS, icons, GResource)
├── tests/                 # Rust integration tests
├── docs/                  # Technical documentation
├── data/                  # Local dev database
├── logs/                  # Runtime logs
├── LICENSE                # Source-Available license
├── THIRD_PARTY_LICENSES.md# Third-party dependency licenses
└── install.sh             # Linux installer
```

---

## Quick Start

### Development

```bash
./run-dev.sh
```

Dev database: `data/heelonvault-rust-dev.db`

### Build and lint

```bash
cargo check
cargo clippy -- -D warnings
```

### Packaged Linux installation

```bash
tar -xzf heelonvault-linux-x86_64.tar.gz
cd heelonvault-linux-x86_64
sudo ./install.sh
```

See [QUICKSTART.md](QUICKSTART.md) and [QUICKSTART.fr.md](QUICKSTART.fr.md).

### Tests

```bash
cargo test
```

---

## Bilingual Documentation Index

Central index: [docs/README.md](docs/README.md)

| Document | English | French |
| -------- | ------- | ------ |
| Overview | [README.en.md](README.en.md) | [README.md](README.md) |
| Quickstart | [QUICKSTART.md](QUICKSTART.md) | [QUICKSTART.fr.md](QUICKSTART.fr.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) | [CONTRIBUTING.fr.md](CONTRIBUTING.fr.md) |
| Security | [SECURITY.md](SECURITY.md) | [SECURITY.fr.md](SECURITY.fr.md) |
| Code of Conduct | [CODE_OF_CONDUCT.en.md](CODE_OF_CONDUCT.en.md) | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |
| Architecture | [docs/ARCHITECTURE.en.md](docs/ARCHITECTURE.en.md) | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Update Guide | [docs/UPDATE_GUIDE.en.md](docs/UPDATE_GUIDE.en.md) | [docs/UPDATE_GUIDE.md](docs/UPDATE_GUIDE.md) |
| Data folder | [data/README.md](data/README.md) | [data/README.fr.md](data/README.fr.md) |
| Scripts | [scripts/README.md](scripts/README.md) | [scripts/README.fr.md](scripts/README.fr.md) |
| Tests | [tests/README.en.md](tests/README.en.md) | [tests/README.md](tests/README.md) |
| Third-party licenses | [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | [THIRD_PARTY_LICENSES.fr.md](THIRD_PARTY_LICENSES.fr.md) |

---

## Release Notes 0.9.2-beta

### Internationalization and UX

- login language selector replaced with FR/EN flags;
- fixed a UI freeze during language switching on the login screen;
- harmonized live i18n refresh across main-window global areas (sidebar, tooltips, placeholders, stack titles);
- user language preference now persists and applies live from `Profile & Security`.

### Installer, CI/CD, and release reliability

- installer hardened with explicit validation of critical artifacts (`run.sh`, desktop entries);
- dual desktop-entry installation (`com.heelonvault.rust.desktop` and `heelonvault.desktop`) for environment compatibility;
- installer smoke test added to the release workflow;
- dedicated CI pipeline added (`.github/workflows/ci.yml`) with formatting, lint, build, test compilation, desktop validation, and installer smoke test.

### Bilingual documentation

- FR/EN coverage across operational Markdown documentation;
- central bilingual documentation index in `docs/README.md`;
- synchronized documented versions and runtime paths with the current project state.

### Team sharing, RBAC, and admin UX (March 2026)

- fixed team vault sharing flow by deriving member keys from `password_envelope` when explicit keys are not provided by the UI;
- added fail-fast protection to prevent false success when no member receives a vault key (`granted = 0`);
- added an explicit vault picker in the team sharing dialog to remove target-vault ambiguity;
- added an ADMIN badge in the header next to the connected identity;
- added owner-side shared-state visibility for owned vaults (shared icon kept, text badge removed to avoid duplicate signal);
- normalized FR badge labels to uppercase for visual consistency (for example: ADMIN, DOUBLON, ACTIVEE);
- i18n cleanup: removed obsolete `main-vault-shared-badge` key in FR/EN.
