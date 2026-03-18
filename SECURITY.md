# Security Guide (Rust Runtime)

Last update: 18 March 2026
Scope: active runtime in rust/

This document replaces legacy Python-era notes and reflects the current Rust codebase.

## 1. Security Scope and Threat Model

HeelonVault is a local-first desktop password manager.

Security goals:

- protect vault secrets at rest;
- protect authentication material (master password derivatives, not plaintext);
- limit brute-force attempts on login;
- reduce accidental leaks in UI and logs;
- preserve session safety (auto-lock and explicit logout).

Main assumptions:

- if the OS account is fully compromised while the app is unlocked, attacker impact remains high;
- the project focuses on local storage security, not cloud account security.

## 2. Cryptography in Rust

Current primitives used in rust/src/services/crypto_service.rs:

- KDF: Argon2id (v=19)
- default KDF params: memory 64 MiB, time cost 3, parallelism 1
- derived key size: 32 bytes
- random salt size: 32 bytes
- encryption: AES-256-GCM
- nonce size: 12 bytes (fresh random nonce per encryption)
- RNG: getrandom (OS CSPRNG)
- sensitive buffers: secrecy + zeroize/Zeroizing patterns

Implementation notes:

- decryption/authentication failures return generic crypto errors;
- salts and keys are never stored as plaintext passwords;
- key derivation and encryption are isolated in dedicated services.

## 3. Authentication and Password Material

Current auth model in rust/src/services/auth_service.rs:

- plaintext passwords are converted to secret strings in memory only;
- password verification uses constant-time byte comparison;
- credentials are stored as a versioned envelope:
  - envelope version byte
  - salt length + hash length
  - Argon2id salt and derived hash bytes
- persisted value in database: users.password_envelope (binary)

Important:

- no plaintext password is persisted;
- changing password rotates salt and hash;
- auth service supports shutdown signaling to block operations during controlled shutdown.

## 4. Login Identifier UX and Security

Login now accepts a single identifier field with resolution order:

1. username (exact logical match, case-insensitive after trim)
2. email (if present)
3. display_name (if present)

Security behavior:

- lock policy is applied on the resolved canonical username;
- failed attempts increment the policy counter for that account;
- unknown identifier is treated as invalid credentials.

## 5. Brute-force and Session Controls

Current lock controls in rust/src/services/auth_policy_service.rs:

- threshold: 5 failed attempts
- lock window: 5 minutes
- counters are persisted in auth_policy table
- successful login resets failed_attempts and last_attempt_at

Current session controls:

- auto-lock delay per user: allowed values 0, 1, 5, 10, 15, 30 minutes
- default auto-lock delay: 5 minutes
- app returns to login screen on logout/auto-lock
- close-window path triggers secure logout behavior

## 6. Password Policy and ANSSI Positioning

This project follows an internal baseline inspired by ANSSI guidance (long unique passphrases, no reuse, context-based hardening).

Current technical rules in Rust:

- password service policy (generator/validator):
  - min length 16, max 128
  - at least one lowercase, uppercase, digit, symbol
  - no whitespace
- generated passwords default to length 24

Current master password change rule in user flow:

- minimum length check currently set to 10 before update.

Security recommendation for operations:

- for admin and sensitive environments, use passphrases >= 16 chars;
- target roadmap is to align all entry points to a unified >= 16 policy.

## 7. Data Protection Boundaries

Data encrypted with AES-256-GCM:

- secret payloads in vault items (passwords and sensitive blobs)
- key envelopes used by vault service
- persisted password envelopes for authentication material

Data that may remain in clear text for UX/indexing reasons:

- some metadata fields such as labels/titles/tags/URLs.

Operational recommendation:

- do not place highly sensitive values in metadata fields intended for search/display.

## 8. 2FA Status

2FA/TOTP capabilities exist in model and storage layers, but full end-to-end login enforcement in the Rust UI flow is not yet finalized.

Practical interpretation:

- 2FA is currently considered in-progress for the runtime login pipeline;
- do not claim full MFA enforcement in audits until login flow migration is complete.

## 9. Logging and Security Events

Current event coverage includes:

- successful login history (table login_history);
- auth failure threshold events (critical counters);
- policy reset/update traces.

Logging rules:

- never log plaintext secrets;
- keep technical details sufficient for incident triage without sensitive payload leakage.

## 10. Security Testing

Minimum test routine before release:

1. cargo check
2. cargo test
3. targeted security suites:
   - rust/tests/security_auth.rs
   - rust/tests/security_crypto.rs

Recommended manual checks:

1. verify login lock behavior after repeated failures
2. verify auto-lock behavior and forced return to login
3. verify password change rotates auth envelope and old password no longer works
4. verify login via username, display name, and email

## 11. Vulnerability Disclosure

Do not open public issues for security vulnerabilities.

Contact channel:

  <security@heelonys.fr>

Please include:

- impacted version
- environment
- reproduction steps
- expected vs actual behavior
- impact assessment
- proof of concept if available

Target response process:

1. acknowledgment within 48h
2. initial triage within 7 days
3. coordinated remediation and disclosure by severity

## 12. Compliance and Hardening Roadmap

Near-term priorities:

- unify master password policy to >= 16 across all flows
- finalize full MFA enforcement in login pipeline
- add stronger audit trails for admin-sensitive operations
- document hardening profiles (standard, admin, high assurance)

Reference standards:

- ANSSI password and authentication recommendations
- OWASP Password Storage Cheat Sheet
- NIST SP 800-63B
