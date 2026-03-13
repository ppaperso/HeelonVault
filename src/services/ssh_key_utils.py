"""Helpers SSH pour la Phase 2 (validation, fingerprint, payload)."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from src.i18n import _

_OPENSSH_TYPE_TO_ALGORITHM = {
    "ssh-ed25519": "ed25519",
    "ssh-rsa": "rsa",
    "ecdsa-sha2-nistp256": "ecdsa",
    "ecdsa-sha2-nistp384": "ecdsa",
    "ecdsa-sha2-nistp521": "ecdsa",
    "ssh-dss": "dsa",
}


@dataclass(slots=True)
class ParsedPublicKey:
    """Représente une clé publique OpenSSH normalisée."""

    openssh: str
    algorithm: str
    comment: str | None
    key_size: int | None
    fingerprint: str
    preview: str


class SshKeyValidationError(ValueError):
    """Erreur de validation SSH exploitable côté service/UI."""


class InvalidSSHKeyFormat(SshKeyValidationError):  # noqa: N818
    """Format de clé SSH invalide ou malformé."""


class PassphraseMismatch(SshKeyValidationError):  # noqa: N818
    """Passphrase incorrecte ou manquante pour une clé chiffrée."""


class PublicKeyMismatch(SshKeyValidationError):  # noqa: N818
    """La clé privée ne correspond pas à la clé publique."""


class UnsupportedKeyFormat(SshKeyValidationError):  # noqa: N818
    """Format ou algorithme de clé non pris en charge."""


def normalize_ssh_public_key(public_key_text: str) -> ParsedPublicKey:
    """Valide et normalise une clé publique OpenSSH."""
    clean = public_key_text.strip()
    if not clean:
        raise InvalidSSHKeyFormat(_("SSH public key is required"))

    parts = clean.split()
    if len(parts) < 2:
        raise InvalidSSHKeyFormat(_("SSH public key format is invalid"))

    key_type = parts[0]
    algorithm = _OPENSSH_TYPE_TO_ALGORITHM.get(key_type)
    if algorithm is None:
        raise UnsupportedKeyFormat(_("SSH public key algorithm is not supported"))

    try:
        key_obj = serialization.load_ssh_public_key(clean.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise InvalidSSHKeyFormat(_("SSH public key format is invalid")) from exc

    canonical = key_obj.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")

    comment = " ".join(parts[2:]).strip() or None
    key_size = getattr(key_obj, "key_size", None)
    fingerprint = compute_ssh_fingerprint(canonical)

    return ParsedPublicKey(
        openssh=canonical,
        algorithm=algorithm,
        comment=comment,
        key_size=int(key_size) if isinstance(key_size, int) else None,
        fingerprint=fingerprint,
        preview=build_public_key_preview(canonical),
    )


def validate_private_key_and_match_public(
    private_key_text: str,
    public_key: ParsedPublicKey,
    passphrase: str | None,
) -> tuple[bool, int | None]:
    """Valide la clé privée OpenSSH/PEM, retourne (has_passphrase, key_size)."""
    clean = private_key_text.strip()
    if not clean:
        raise InvalidSSHKeyFormat(_("SSH private key is required"))

    key_obj, has_passphrase = _load_private_key(clean, passphrase)

    private_public = key_obj.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")

    if private_public != public_key.openssh:
        raise PublicKeyMismatch(_("SSH private key and public key do not match"))

    key_size = getattr(key_obj, "key_size", None)
    return has_passphrase, int(key_size) if isinstance(key_size, int) else None


def build_public_key_preview(public_key_openssh: str, edge: int = 18) -> str:
    """Construit un aperçu stable 'prefix...suffix' pour l'UI."""
    clean = public_key_openssh.strip()
    if len(clean) <= (edge * 2) + 3:
        return clean
    return f"{clean[:edge]}...{clean[-edge:]}"


def compute_ssh_fingerprint(public_key_openssh: str) -> str:
    """Retourne un fingerprint compatible `ssh-keygen -E sha256`."""
    parts = public_key_openssh.strip().split()
    if len(parts) < 2:
        raise InvalidSSHKeyFormat(_("SSH public key format is invalid"))

    try:
        key_blob = base64.b64decode(parts[1].encode("ascii"), validate=True)
    except (ValueError, TypeError) as exc:
        raise InvalidSSHKeyFormat(_("SSH public key format is invalid")) from exc

    digest = hashlib.sha256(key_blob).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def build_ssh_payload(private_key: str, public_key_openssh: str) -> str:
    """Sérialise le payload SSH applicatif avant chiffrement."""
    return json.dumps(
        {
            "private_key": private_key.strip(),
            "public_key": public_key_openssh.strip(),
        }
    )


def parse_ssh_payload(payload: str) -> tuple[str, str]:
    """Désérialise le payload SSH applicatif après déchiffrement."""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SshKeyValidationError("ssh payload is malformed") from exc

    if not isinstance(parsed, dict):
        raise SshKeyValidationError("ssh payload is malformed")

    private_key = parsed.get("private_key")
    public_key = parsed.get("public_key")
    if not isinstance(private_key, str) or not isinstance(public_key, str):
        raise SshKeyValidationError("ssh payload is malformed")

    return private_key, public_key


def _load_private_key(private_key: str, passphrase: str | None) -> tuple[Any, bool]:
    if private_key.startswith("-----BEGIN OPENSSH PRIVATE KEY-----"):
        return _load_openssh_private_key(private_key, passphrase)

    if private_key.startswith(
        (
            "-----BEGIN ENCRYPTED PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----",
            "-----BEGIN DSA PRIVATE KEY-----",
        )
    ):
        return _load_pem_private_key(private_key, passphrase)

    raise UnsupportedKeyFormat(_("SSH private key format is not supported"))


def _load_openssh_private_key(private_key: str, passphrase: str | None) -> tuple[Any, bool]:
    try:
        key_obj = serialization.load_ssh_private_key(private_key.encode("utf-8"), password=None)
        return key_obj, False
    except TypeError as exc:
        if not passphrase:
            raise PassphraseMismatch(_("SSH private key requires a passphrase")) from exc
        try:
            key_obj = serialization.load_ssh_private_key(
                private_key.encode("utf-8"),
                password=passphrase.encode("utf-8"),
            )
            return key_obj, True
        except UnsupportedAlgorithm as exc:
            raise UnsupportedKeyFormat(
                _("Encrypted OpenSSH private key requires the bcrypt module")
            ) from exc
        except ValueError as exc:
            raise PassphraseMismatch(_("SSH private key passphrase is incorrect")) from exc
    except ValueError as exc:
        raise InvalidSSHKeyFormat(_("SSH private key format is invalid")) from exc


def _load_pem_private_key(private_key: str, passphrase: str | None) -> tuple[Any, bool]:
    raw = private_key.encode("utf-8")

    if passphrase:
        try:
            key_obj = serialization.load_pem_private_key(raw, password=passphrase.encode("utf-8"))
            return key_obj, True
        except ValueError as exc:
            raise PassphraseMismatch(_("SSH private key passphrase is incorrect")) from exc

    try:
        key_obj = serialization.load_pem_private_key(raw, password=None)
        return key_obj, False
    except TypeError as exc:
        raise PassphraseMismatch(_("SSH private key requires a passphrase")) from exc
    except ValueError as exc:
        raise InvalidSSHKeyFormat(_("SSH private key format is invalid")) from exc
