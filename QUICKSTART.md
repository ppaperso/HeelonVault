# Quickstart (Rust)

## 1. Build Check

```bash
cd rust
cargo check
```

## 2. Run in Development

From repository root:

```bash
./run-dev.sh
```

Development database path:

- `data/heelonvault-rust-dev.db`

## 3. Run Tests

```bash
cd rust
cargo test secret_repository:: -- --nocapture
cargo test secret_service:: -- --nocapture
```

## 4. Production Build

```bash
cd rust
cargo build --release
```

The production launcher expects:

- Binary path: `/opt/heelonvault/rust/target/release/heelonvault-rust`
- Launcher: `/opt/heelonvault/run.sh`
- Production database path: `/var/lib/heelonvault-rust-shared/heelonvault.db`

Legacy path protection:

- Do not modify or delete `/var/lib/heelonvault-shared` (legacy Python data).
