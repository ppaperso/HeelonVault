"""Tests unitaires des helpers SSH (parsing + fingerprint + passphrase)."""

from __future__ import annotations

import pytest

from src.services.ssh_key_utils import (
    SshKeyValidationError,
    build_ssh_payload,
    compute_ssh_fingerprint,
    normalize_ssh_public_key,
    parse_ssh_payload,
    validate_private_key_and_match_public,
)
from tests.fixtures.ssh_fixture_data import (
    ED25519_FINGERPRINT_SHA256,
    ED25519_PRIVATE_PATH,
    ED25519_PUBLIC_PATH,
    RSA_4096_FINGERPRINT_SHA256,
    RSA_4096_PASSPHRASE,
    RSA_4096_PRIVATE_PATH,
    RSA_4096_PUBLIC_PATH,
    read_text,
)


def test_normalize_ed25519_public_key() -> None:
    public_key = read_text(ED25519_PUBLIC_PATH)

    parsed = normalize_ssh_public_key(public_key)

    assert parsed.algorithm == "ed25519"
    assert parsed.comment == "fixture-ed25519@heelonvault"
    assert parsed.fingerprint == ED25519_FINGERPRINT_SHA256
    assert parsed.preview


def test_compute_fingerprint_matches_expected_values() -> None:
    ed_pub = read_text(ED25519_PUBLIC_PATH)
    rsa_pub = read_text(RSA_4096_PUBLIC_PATH)

    assert compute_ssh_fingerprint(ed_pub) == ED25519_FINGERPRINT_SHA256
    assert compute_ssh_fingerprint(rsa_pub) == RSA_4096_FINGERPRINT_SHA256


def test_validate_private_key_no_passphrase() -> None:
    private_key = read_text(ED25519_PRIVATE_PATH)
    public_key = normalize_ssh_public_key(read_text(ED25519_PUBLIC_PATH))

    has_passphrase, key_size = validate_private_key_and_match_public(
        private_key,
        public_key,
        passphrase=None,
    )

    assert has_passphrase is False
    assert key_size is None


def test_validate_private_key_with_passphrase() -> None:
    private_key = read_text(RSA_4096_PRIVATE_PATH)
    public_key = normalize_ssh_public_key(read_text(RSA_4096_PUBLIC_PATH))

    has_passphrase, key_size = validate_private_key_and_match_public(
        private_key,
        public_key,
        passphrase=RSA_4096_PASSPHRASE,
    )

    assert has_passphrase is True
    assert key_size == 4096


def test_validate_private_key_rejects_missing_passphrase() -> None:
    private_key = read_text(RSA_4096_PRIVATE_PATH)
    public_key = normalize_ssh_public_key(read_text(RSA_4096_PUBLIC_PATH))

    with pytest.raises(SshKeyValidationError, match="requires a passphrase"):
        validate_private_key_and_match_public(
            private_key,
            public_key,
            passphrase=None,
        )


def test_validate_private_key_rejects_wrong_passphrase() -> None:
    private_key = read_text(RSA_4096_PRIVATE_PATH)
    public_key = normalize_ssh_public_key(read_text(RSA_4096_PUBLIC_PATH))

    with pytest.raises(SshKeyValidationError, match="passphrase"):
        validate_private_key_and_match_public(
            private_key,
            public_key,
            passphrase="wrong-passphrase",
        )


def test_validate_private_key_rejects_mismatched_pair() -> None:
    private_key = read_text(ED25519_PRIVATE_PATH)
    rsa_public_key = normalize_ssh_public_key(read_text(RSA_4096_PUBLIC_PATH))

    with pytest.raises(SshKeyValidationError, match="do not match"):
        validate_private_key_and_match_public(
            private_key,
            rsa_public_key,
            passphrase=None,
        )


def test_payload_roundtrip() -> None:
    private_key = read_text(ED25519_PRIVATE_PATH)
    public_key = read_text(ED25519_PUBLIC_PATH)

    payload = build_ssh_payload(private_key, public_key)
    private_roundtrip, public_roundtrip = parse_ssh_payload(payload)

    assert private_roundtrip.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert public_roundtrip.startswith("ssh-ed25519 ")
