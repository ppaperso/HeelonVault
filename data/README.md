# Development Data Directory (Rust)

This folder is used only for local Rust development data.

## Paths

- Dev database: `data/heelonvault-rust-dev.db`
- Prod database: `/var/lib/heelonvault-rust-shared/heelonvault.db`

## Legacy Data Protection

Do not modify or delete `/var/lib/heelonvault-shared`.
This path belongs to legacy Python data and must remain untouched.

## Reset Local Dev Data

```bash
rm -f data/heelonvault-rust-dev.db
```

The dev database will be recreated on next `./run-dev.sh` launch.
