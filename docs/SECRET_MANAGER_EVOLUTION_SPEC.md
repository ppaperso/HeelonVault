# Secret Manager Evolution Spec

## 1. Objective

Transform HeelonVault from a password manager into a personal secret manager that supports:

- SSH key management
- API token storage
- Sensitive document storage

This spec is implementation-oriented for the next development session.

## 2. Scope

### In scope (Phase 1-3)

- New secret types in data model and UI
- Secure storage and retrieval for each type
- Migration from existing password-only schema
- Type-aware list/detail experience
- Security controls aligned with existing encryption model

### Out of scope (for now)

- Cloud sync
- Team sharing and RBAC beyond current local user roles
- HSM integration
- Hardware-backed key storage APIs

## 3. Product Model

Introduce a unified `SecretItem` abstraction with typed payloads.

### Secret types

- `password`
- `ssh_key`
- `api_token`
- `secure_document`

### Principles

- One vault can contain all secret types
- Metadata remains queryable/indexable
- Sensitive payloads are always encrypted at rest
- UI behavior is type-specific but stored under one domain model

## 4. Data Model

## 4.1 Existing constraints

- Current app stores password entries in per-vault sqlite databases.
- Encryption is already handled by `CryptoService` + `PasswordService`.

## 4.2 Proposed schema additions

### Option retained for continuity

Keep existing password table, then add a new generic table for non-password secrets in Phase 1.

### Target table: `secret_items`

```sql
CREATE TABLE IF NOT EXISTS secret_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 secret_type TEXT NOT NULL CHECK (secret_type IN ('ssh_key', 'api_token', 'secure_document')),
 title TEXT NOT NULL,
 metadata_json TEXT,
 secret_blob BLOB NOT NULL,
 tags TEXT DEFAULT '',
 expires_at TEXT,
 created_at TEXT NOT NULL,
 modified_at TEXT NOT NULL,
 usage_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_secret_items_type ON secret_items(secret_type);
CREATE INDEX IF NOT EXISTS idx_secret_items_title ON secret_items(title);
CREATE INDEX IF NOT EXISTS idx_secret_items_expires ON secret_items(expires_at);
```

### Metadata JSON per type

- `ssh_key`:
  - `algorithm` (`ed25519`, `rsa`, ...)
  - `fingerprint`
  - `public_key_preview`
  - `has_passphrase` (bool)
- `api_token`:
  - `provider`
  - `environment` (`dev`, `staging`, `prod`)
  - `scopes` (array string)
  - `token_hint` (last chars masked)
- `secure_document`:
  - `filename`
  - `mime_type`
  - `size_bytes`
  - `sha256`
  - `blob_path` (encrypted file path)

## 4.3 Document blob storage

Store encrypted document binaries in:

```text
src/data/blobs/<vault_uuid>/<item_id_or_uuid>.bin
```

`secret_blob` in DB stores encrypted metadata envelope and reference, not full file body for large documents.

## 5. Migration Strategy

## 5.1 Versioning

- Add schema version marker (if absent) in DB metadata table.
- Increment version when `secret_items` is introduced.

## 5.2 Migration steps

1. Detect DB without `secret_items`.
2. Create new table and indexes.
3. Leave existing password entries unchanged.
4. Mark schema version upgraded.
5. Log migration success/failure (without sensitive payloads).

## 5.3 Rollback

- Preserve backup before migration using existing backup service.
- On migration failure: abort startup for that vault with user-friendly error.

## 6. Service Layer Changes

## 6.1 New domain models

- `src/models/secret_item.py`
- `src/models/secret_types.py`

### Suggested dataclass

```python
@dataclass
class SecretItem:
  id: int | None
  secret_type: str
  title: str
  metadata: dict[str, Any]
  payload: str | bytes
  tags: list[str]
  expires_at: datetime | None
  created_at: datetime | None
  modified_at: datetime | None
  usage_count: int = 0
```

## 6.2 Repository

New repository:

- `src/repositories/secret_repository.py`

Core methods:

- `list_items(secret_type=None, search_text=None, tag_filter=None)`
- `get_item(item_id)`
- `create_item(item)`
- `update_item(item)`
- `delete_item(item_id)`
- `record_usage(item_id, amount=1)`

## 6.3 Service

New service:

- `src/services/secret_service.py`

Responsibilities:

- Validate type-specific payload structure
- Encrypt/decrypt item payload using existing `CryptoService`
- Normalize metadata fields
- Apply security policies for export/reveal/copy

## 7. UI/UX Evolution

## 7.1 Navigation

Extend left navigation with a `Secrets` filter group:

- All
- Passwords
- SSH Keys
- API Tokens
- Documents

Default remains `All`.

## 7.2 Entry list rendering

Use card variants by `secret_type`:

- Password card: current behavior
- SSH card: algorithm + fingerprint + passphrase badge
- API token card: provider + env + expiration badge
- Document card: filename + size + mime

## 7.3 Detail panel variants

Switch right panel form by selected type.

### SSH Key form fields

- Title
- Algorithm
- Private key (masked/reveal)
- Public key
- Comment
- Passphrase present

### API Token form fields

- Title
- Provider
- Token value (masked/reveal)
- Scopes
- Environment
- Expiration

### Secure Document form fields

- Title
- File picker/import
- Metadata summary
- Export/Reveal actions

## 7.4 Premium interactions

- Copy with auto-clear timer for tokens/keys
- Sensitive reveal with timed remask
- Uniform panic behavior across all secret types
- Visual badges for expiration and risk level

## 8. Security Requirements

## 8.1 Data-at-rest

- All secret payloads encrypted using existing master-key flow.
- No raw token/key/document content in logs.
- Document blobs encrypted before disk write.

## 8.2 Memory hygiene (best effort)

- Reuse panic purge path for new secret payload holders.
- Clear UI text buffers when switching items/types.
- Keep clipboard cleanup behavior consistent across types.

## 8.3 Operational controls

- Soft Lock: logout and return to auth screen
- Panic Lock: best-effort in-memory purge + application quit

## 9. API and File Contracts

## 9.1 Internal service contracts

- `SecretService.create_api_token(...)`
- `SecretService.create_ssh_key(...)`
- `SecretService.import_document(...)`
- `SecretService.export_document(...)`

## 9.2 Filesystem contract for documents

- Blob path derived from active vault UUID.
- Atomic write pattern for encrypted document files.
- SHA-256 integrity check on read.

## 10. Implementation Plan

## Phase 1: API Tokens (quick value)

1. Add `secret_items` table and migration
2. Add repository + service skeleton
3. Add API token type in list and detail panel
4. Add i18n strings and tests

## Phase 2: SSH Keys

1. Add SSH key model metadata and forms
2. Add key import and secure export
3. Add fingerprint and validation helpers

## Phase 3: Secure Documents

1. Add encrypted blob storage path + integrity hash
2. Add import/export flows and metadata display
3. Add large file handling safeguards

## 11. Testing Strategy

## 11.1 Unit tests

- `test_secret_repository.py`
- `test_secret_service.py`
- `test_document_encryption.py`
- `test_ssh_metadata_parsing.py`

## 11.2 Integration tests

- Migration test from password-only DB to mixed-secrets DB
- CRUD flows for each new type
- Panic/Soft lock behavior while secrets are loaded

## 11.3 Security regression tests

- Ensure no plaintext secrets in logs
- Ensure clipboard auto-clear for token/key copy
- Ensure encrypted document file does not contain plaintext patterns

## 12. Acceptance Criteria

- User can create/read/update/delete API tokens.
- User can create/import/store SSH keys with encrypted private key.
- User can import and export encrypted secure documents.
- Panic and Soft lock work consistently across all secret types.
- Existing password workflows remain fully functional.
- fr/de/it/en strings are available for new UI elements.

## 13. Open Decisions for Kickoff

- Whether to keep passwords in legacy table long-term or converge into one universal table in v2.
- Maximum document size for initial release.
- Whether SSH key generation is in-app in Phase 2 or import-only first.

## 14. Proposed Day-1 Task Breakdown (tomorrow)

1. Create migration + repository skeleton for `secret_items`.
2. Introduce `SecretItem` model and `SecretService` minimal API.
3. Add type filter UI and API token detail form.
4. Add tests for migration + API token CRUD.
5. Add i18n entries and run compile for all locales.
