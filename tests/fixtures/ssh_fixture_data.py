"""Données de fixtures SSH stables pour la Phase 2."""

from __future__ import annotations

from pathlib import Path

SSH_FIXTURES_DIR = Path(__file__).with_name("ssh_keys")

ED25519_PRIVATE_PATH = SSH_FIXTURES_DIR / "ed25519_no_passphrase"
ED25519_PUBLIC_PATH = SSH_FIXTURES_DIR / "ed25519_no_passphrase.pub"

RSA_4096_PRIVATE_PATH = SSH_FIXTURES_DIR / "rsa_4096_with_passphrase"
RSA_4096_PUBLIC_PATH = SSH_FIXTURES_DIR / "rsa_4096_with_passphrase.pub"
RSA_4096_PASSPHRASE = "Phase2FixturePass!"  # noqa: S105

ED25519_FINGERPRINT_SHA256 = "SHA256:dhHZy/yyLiZ12IpTqpsGO9cUyT+w30rsN44Rnqw/wG4"
RSA_4096_FINGERPRINT_SHA256 = "SHA256:A+0l3TYWGr50Tcv9kBzb5wkAXlPefmIUDLxVsXecieM"


def read_text(path: Path) -> str:
    """Lit une fixture texte UTF-8."""
    return path.read_text(encoding="utf-8")
