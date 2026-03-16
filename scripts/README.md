# Scripts

This folder contains operational shell scripts used by the Rust repository.
Run scripts from the repository root.

## Available Scripts

- `scripts/backup-prod-before-tests.sh`: creates a production backup archive before manual tests.
- `scripts/fix-permissions.sh`: fixes permissions and ACL on `/var/lib/heelonvault-rust-shared`.

## Rust Development

For development and tests, use root-level scripts and Rust commands:

```bash
./run-dev.sh
cd rust && cargo check
cd rust && cargo test
```

Data path notes:

- Rust prod data: `/var/lib/heelonvault-rust-shared`
- Rust dev data: `data/`
- Legacy Python data: `/var/lib/heelonvault-shared` (do not modify)
