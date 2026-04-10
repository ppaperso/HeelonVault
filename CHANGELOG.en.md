# Changelog — HeelonVault

Language: EN | [FR](CHANGELOG.md)

All notable changes are documented here, in descending version order.
Format inspired by [Keep a Changelog](https://keepachangelog.com/).

---

## [1.0.3] — 2026-04-10

### UI refactoring

- Finalized the split of large Rust screens into dedicated modules for `login_dialog`, `main_window`, `profile_view`, and related flows.
- Kept the maintainability constraint satisfied: no active UI Rust file above 800 lines.
- Extracted sizing helpers and UI subcomponents to reduce local coupling and clarify responsibilities.

### Technical cleanup

- Removed unreferenced intermediate split files left behind during the refactor.
- Verified that `resources/images/user-guide` images remain documentation-only assets and are not unintentionally bundled at runtime.

### Validation

- Validated the release state with `cargo check`, `cargo clippy`, `cargo test`, and `cargo fmt --all -- --check`.

### Version

- Bumped application and documentation version to **1.0.3**.

## [1.0.1] — 2026-04-06

### Product documentation

- Added a **bilingual user guide** (`docs/USER_GUIDE.md` and `docs/USER_GUIDE.en.md`) with an end-user manual tone.
- Integrated real UI screenshots across screen-by-screen sections (bootstrap, login, dashboard, secret creation forms, profile/security, import/export, user/team administration, trash).
- Structured the guide with a table of contents and formal screen/capture numbering.

### CI/CD and Linux packaging

- Added a shared smoke test (`tests/smoke-test.sh`) with `--install/--remove`, permissions checks, and desktop-entry validation.
- Hardened CI/Release workflows: Rust cache, Fedora container job, external `.sha256` checksum asset, build provenance attestation, and core script inclusion in `dist/`.

### Version1

- Bumped application and documentation version to **1.0.1**.

## [1.0.0] — 2026-04-02

### Stable release

- Official move to **1.0.0** (stable release), removing the beta suffix from the application version and reference documentation.

### PDF audit report

- Simplified premium visual header: removed the gold framed panel.
- New black primary title: **REGISTRE DE TRAÇABILITÉ DES ACCÈS**.
- Signed audit log exported as an actionable table (date, action, actor, target, detail).

### Traceability and readability

- Actor identity resolution now prefers display name / username in exports.
- Audit targets enriched with vault names and secret titles when available.
- `secret.created` event now includes secret title in audit detail payload.

## [0.9.4-beta] — 2026-04-01

### License

- Switched from proprietary Source-Available license to **Apache 2.0**: free to use, modify, and redistribute; HEELONYS copyright and brand retained.

### Application license system (LicenseService)

- Ed25519 signature verification for signed license files (`~/.config/heelonvault/license.hvl` in dev, `/etc/heelonvault/license.hvl` in prod).
- JSON format with `payload` field (JSON object or serialized string) and `signature` (128-char hex or base64).
- Automatic fallback to **Community** license when no file is present or verification fails.
- Automatic tolerance of whitespace and `0x` prefix in hex values (`sanitize_hex_input`).
- Audit log entries `LicenseCheckSuccess` / `LicenseCheckFailure` at application startup.

### License badges in the UI

- **"Licence free"** / **"Licence pro — CLIENT"** badge in the login hero section, visible before authentication.
- License badge in the main-window header bar (next to the BETA badge).
- High-visibility CSS style `.login-license-badge` (teal gradient).
- i18n keys `license-status-community`, `license-status-professional`, `license-status-invalid` added in FR and EN.

---

## [0.9.3-beta] — 2026-03-31

### Security dashboard

- Security dashboard window rendered via WebKitGTK (WebView-first, no GTK fallback blocks).
- Global vault score computed in real time with `zxcvbn` evaluation.
- Dedicated FR and EN translations for all dashboard labels and states.

### Login history

- Each successful login is recorded in the `login_history` table (migration 0007).
- History displayed in the `Profile & Security` view.

### TOTP 2FA activation

- Guided TOTP activation via QR code in `Profile & Security`.
- Mandatory first-code verification before activation is confirmed.
- TOTP secret stored encrypted in the database (migration 0009).

### Fixes and robustness

- Secret restore from trash: atomic transaction with automatic parent vault restore when needed (avoids "invisible secret" state).
- Vault resolution fixed in the multi-vault secret edit dialog.
- Password envelope persistence corrected on reload.

---

## [0.9.2-beta] — 2026-03-27

### Internationalization and UX

- Login language selector replaced with FR/EN flags.
- Fixed a UI freeze during language switching on the login screen.
- Harmonized live i18n refresh across main-window global areas (sidebar, tooltips, placeholders, stack titles).
- User language preference now persists and applies live from `Profile & Security`.

### Installer, CI/CD, and release reliability

- Installer hardened with explicit validation of critical artifacts (`run.sh`, desktop entries).
- Dual desktop-entry installation (`com.heelonvault.rust.desktop` and `heelonvault.desktop`) for environment compatibility.
- Installer smoke test added to the release workflow.
- Dedicated CI pipeline (`.github/workflows/ci.yml`): formatting, lint, build, test compilation, desktop validation, smoke test.

### Bootstrap wizard, recovery key, and secure backup

- 3-step first-admin setup wizard in the login dialog: identity → oath (24-word phrase) → pending.
- 24-word BIP39-style mnemonic phrase generated at bootstrap via `BackupService::generate_recovery_key()`.
- Mandatory spot-check of 2 randomly drawn words before confirmation.
- Clipboard copy with automatic wipe after 60 seconds.
- Recovery key re-export available from `Profile & Security` for any admin.
- `BackupApplicationService`: RBAC access control on `.hvb` export and import operations.
- Audit log introduced (table `audit_log`, migration 0013).

### Team sharing, RBAC, and admin UX

- Fixed team vault sharing: member key now derived from `password_envelope` when no explicit key is provided.
- Fail-fast protection: explicit failure when no member receives a vault key.
- Explicit vault picker added to the team sharing dialog.
- ADMIN badge in the header next to the connected identity.
- Owner-side shared-state visibility for owned vaults.
- FR badge labels normalized to uppercase.
- i18n cleanup: removed obsolete `main-vault-shared-badge` key.

### Bilingual documentation

- FR/EN coverage across all operational Markdown documentation.
- Central bilingual documentation index in `docs/README.md`.

---

## [0.9.1-beta] — 2026-03-01

### Initial Rust architecture

- Full migration from Python to Rust (GTK4 + libadwaita).
- Service/repository/model layer in Rust with `sqlx` and 9 initial migrations.
- Argon2id authentication, AES-256-GCM encryption, TOTP RFC 6238.
- Multi-user with isolated vaults per user.
- Multi-field search with Unicode normalization.
- Rotating structured JSON logs via `tracing`.
- Security Clippy policy (`clippy.toml`) forbidding `unwrap()`/`expect()` on sensitive paths.
