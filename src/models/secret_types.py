"""Types et constantes pour les nouveaux secrets."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

SECRET_TYPE_PASSWORD = "password"  # noqa: S105
SECRET_TYPE_API_TOKEN = "api_token"  # noqa: S105
SECRET_TYPE_SSH_KEY = "ssh_key"  # noqa: S105
SECRET_TYPE_SECURE_DOCUMENT = "secure_document"  # noqa: S105

ALL_NEW_SECRET_TYPES = frozenset(
    {
        SECRET_TYPE_API_TOKEN,
        SECRET_TYPE_SSH_KEY,
        SECRET_TYPE_SECURE_DOCUMENT,
    }
)


class ApiTokenMetadata(TypedDict):
    """Métadonnées normalisées pour un token API."""

    provider: str
    environment: Literal["dev", "staging", "prod", "other"]
    scopes: list[str]
    token_hint: str
    expiration_warning_days: NotRequired[int]


class SshKeyMetadata(TypedDict):
    """Métadonnées normalisées pour une clé SSH."""

    algorithm: Literal["ed25519", "rsa", "ecdsa", "dsa"]
    fingerprint: str
    public_key_preview: str
    has_passphrase: bool
    comment: NotRequired[str]
    key_size: NotRequired[int]


class SecureDocumentMetadata(TypedDict):
    """Métadonnées normalisées pour un document sécurisé."""

    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    blob_path: str
