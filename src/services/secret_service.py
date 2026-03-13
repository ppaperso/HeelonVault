"""Service applicatif pour la gestion des nouveaux secrets (Phase 1+)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.i18n import _
from src.models.secret_item import SecretItem
from src.models.secret_types import SECRET_TYPE_API_TOKEN, SECRET_TYPE_SSH_KEY
from src.repositories.secret_repository import SecretRepository
from src.services.crypto_service import CryptoService
from src.services.ssh_key_utils import (
    InvalidSSHKeyFormat,
    build_ssh_payload,
    normalize_ssh_public_key,
    parse_ssh_payload,
    validate_private_key_and_match_public,
)

logger = logging.getLogger(__name__)

_API_TOKEN_ENV_ALIASES: dict[str, str] = {
    "dev": "dev",
    "development": "dev",
    "staging": "staging",
    "stage": "staging",
    "preprod": "staging",
    "pre-prod": "staging",
    "prod": "prod",
    "production": "prod",
    "other": "other",
    "autre": "other",
    "altro": "other",
    "sonstige": "other",
}


class SecretService:
    """Expose des opérations haut niveau pour les secrets non-password."""

    def __init__(self, repository: SecretRepository, crypto: CryptoService) -> None:
        self.repository = repository
        self.crypto = crypto

    def create_api_token(
        self,
        title: str,
        token: str,
        metadata: dict[str, Any],
    ) -> SecretItem:
        """Crée un secret de type API token (payload chiffré)."""
        clean_title = title.strip()
        clean_token = token.strip()
        if not clean_title:
            raise ValueError("title is required")
        if not clean_token:
            raise ValueError("token is required")

        normalized_metadata = self._normalize_api_token_metadata(metadata, clean_token)
        scopes = [str(scope) for scope in normalized_metadata.get("scopes", [])]

        item = SecretItem(
            secret_type=SECRET_TYPE_API_TOKEN,
            title=clean_title,
            metadata=normalized_metadata,
            payload=self._encrypt_payload(clean_token),
            tags=scopes,
        )
        created = self.repository.create_item(item)

        # Le service ne doit pas propager le payload chiffré vers la couche UI.
        created.clear_payload()
        logger.info("SecretService: API token created (%s)", created.id)
        return created

    def update_api_token(
        self,
        item_id: int,
        title: str,
        token: str | None,
        metadata: dict[str, Any],
    ) -> SecretItem:
        """Met à jour un token API existant sans changer son UUID stable."""
        current = self.repository.get_item(item_id)
        if current is None:
            raise ValueError(f"Secret item {item_id} not found")
        if current.secret_type != SECRET_TYPE_API_TOKEN:
            raise ValueError("Secret item is not an API token")

        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title is required")

        clean_token = (token or "").strip()
        if clean_token:
            normalized_metadata = self._normalize_api_token_metadata(
                metadata,
                clean_token,
                existing_token_hint=None,
            )
            current.payload = self._encrypt_payload(clean_token)
        else:
            normalized_metadata = self._normalize_api_token_metadata(
                metadata,
                token=None,
                existing_token_hint=current.metadata.get("token_hint"),
            )

        scopes = [str(scope) for scope in normalized_metadata.get("scopes", [])]

        current.title = clean_title
        current.metadata = normalized_metadata
        current.tags = scopes

        updated = self.repository.update_item(current)
        updated.clear_payload()
        logger.info("SecretService: API token updated (%s)", item_id)
        return updated

    def create_ssh_key(
        self,
        title: str,
        private_key: str,
        public_key: str,
        metadata: dict[str, Any] | None = None,
        passphrase: str | None = None,
    ) -> SecretItem:
        """Crée un secret SSH à partir d'une paire privée/publique OpenSSH."""
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title is required")

        parsed_public = normalize_ssh_public_key(public_key)
        has_passphrase, private_key_size = validate_private_key_and_match_public(
            private_key,
            parsed_public,
            passphrase,
        )

        normalized_metadata = self._normalize_ssh_metadata(
            metadata or {},
            parsed_public.algorithm,
            parsed_public.fingerprint,
            parsed_public.preview,
            has_passphrase,
            parsed_public.comment,
            private_key_size,
        )

        item = SecretItem(
            secret_type=SECRET_TYPE_SSH_KEY,
            title=clean_title,
            metadata=normalized_metadata,
            payload=self._encrypt_payload(build_ssh_payload(private_key, parsed_public.openssh)),
            tags=[str(tag) for tag in metadata.get("tags", [])] if metadata else [],
        )
        created = self.repository.create_item(item)
        created.clear_payload()
        logger.info("SecretService: SSH key created (%s)", created.id)
        return created

    def reveal_ssh_private_key(self, item_id: int) -> str:
        """Déchiffre et retourne la clé privée SSH."""
        item = self.repository.get_item(item_id)
        if item is None:
            raise ValueError(f"Secret item {item_id} not found")
        if item.secret_type != SECRET_TYPE_SSH_KEY:
            raise ValueError("Secret item is not an SSH key")

        payload_text = self._decrypt_payload(item.payload)
        private_key, _public_key = parse_ssh_payload(payload_text)
        self.repository.record_usage(item_id, amount=1)
        return private_key

    def update_ssh_key(
        self,
        item_id: int,
        title: str,
        metadata: dict[str, Any],
    ) -> SecretItem:
        """Met à jour uniquement le titre + métadonnées SSH (payload immuable)."""
        current = self.repository.get_item(item_id)
        if current is None:
            raise ValueError(f"Secret item {item_id} not found")
        if current.secret_type != SECRET_TYPE_SSH_KEY:
            raise ValueError("Secret item is not an SSH key")

        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title is required")

        normalized_metadata = self._normalize_ssh_metadata(
            metadata,
            algorithm=str(current.metadata.get("algorithm", "")).strip(),
            fingerprint=str(current.metadata.get("fingerprint", "")).strip(),
            public_key_preview=str(current.metadata.get("public_key_preview", "")).strip(),
            has_passphrase=bool(current.metadata.get("has_passphrase", False)),
            default_comment=current.metadata.get("comment"),
            default_key_size=current.metadata.get("key_size"),
        )

        current.title = clean_title
        current.metadata = normalized_metadata
        current.tags = [str(tag) for tag in metadata.get("tags", []) if str(tag).strip()]

        updated = self.repository.update_item(current)
        updated.clear_payload()
        logger.info("SecretService: SSH key metadata updated (%s)", item_id)
        return updated

    def import_ssh_key_from_file(
        self,
        path: Path,
        title: str | None = None,
        passphrase: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecretItem:
        """Importe une clé SSH depuis le système de fichiers (paire privée + .pub)."""
        if not path.exists():
            raise FileNotFoundError(
                _("SSH private key file not found: %(path)s") % {"path": str(path)}
            )

        pub_path = path.parent / (path.name + ".pub")
        if not pub_path.exists():
            raise InvalidSSHKeyFormat(
                _("SSH public key file not found: %(path)s") % {"path": str(pub_path)}
            )

        private_key_text = path.read_text(encoding="utf-8")
        public_key_text = pub_path.read_text(encoding="utf-8")
        clean_title = (title or path.stem).strip() or path.name

        result = self.create_ssh_key(
            title=clean_title,
            private_key=private_key_text,
            public_key=public_key_text,
            metadata=metadata,
            passphrase=passphrase,
        )
        logger.info("SecretService: SSH key imported from file (%s)", clean_title)
        return result

    def export_ssh_key(
        self,
        item_id: int,
        dest_path: Path,
        overwrite: bool = False,
    ) -> None:
        """Exporte la clé privée SSH vers le système de fichiers (0o600, atomique)."""
        if dest_path.exists() and not overwrite:
            raise FileExistsError(
                _("SSH key export refused: destination file already exists: %(path)s")
                % {"path": str(dest_path)}
            )

        private_key = self.reveal_ssh_private_key(item_id)

        dest_dir = dest_path.parent
        fd, tmp_str = tempfile.mkstemp(dir=dest_dir, prefix=".ssh_export_")
        tmp_path = Path(tmp_str)
        success = False
        try:
            try:
                os.write(fd, private_key.encode("utf-8"))
            finally:
                os.close(fd)
            os.chmod(tmp_path, 0o600)
            tmp_path.rename(dest_path)
            success = True
        finally:
            if not success:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        logger.info("SecretService: SSH key exported (%s)", item_id)

    def reveal_api_token(self, item_id: int) -> str:
        """Déchiffre et retourne la valeur d'un token API."""
        item = self.repository.get_item(item_id)
        if item is None:
            raise ValueError(f"Secret item {item_id} not found")
        if item.secret_type != SECRET_TYPE_API_TOKEN:
            raise ValueError("Secret item is not an API token")

        token = self._decrypt_payload(item.payload)
        self.repository.record_usage(item_id, amount=1)
        return token

    def get_item(self, item_id: int) -> SecretItem | None:
        """Retourne un item sans exposer son payload chiffré."""
        item = self.repository.get_item(item_id)
        if item is None:
            return None
        item.clear_payload()
        return item

    def get_item_by_uuid(self, item_uuid: str) -> SecretItem | None:
        """Retourne un item par UUID stable sans exposer son payload."""
        item = self.repository.get_item_by_uuid(item_uuid)
        if item is None:
            return None
        item.clear_payload()
        return item

    def list_items(
        self,
        secret_type: str | None = None,
        search_text: str | None = None,
    ) -> list[SecretItem]:
        """Liste les items sans payload pour limiter les fuites accidentelles."""
        items = self.repository.list_items(secret_type=secret_type, search_text=search_text)
        for item in items:
            item.clear_payload()
        return items

    def delete_secret(self, item_id: int) -> None:
        """Supprime définitivement un secret."""
        deleted = self.repository.delete_item(item_id)
        if not deleted:
            raise ValueError(f"Secret item {item_id} not found")

    def get_expiring_soon(self, days: int = 30) -> list[SecretItem]:
        """Retourne les secrets expirant dans la fenêtre demandée."""
        deadline = datetime.now() + timedelta(days=days)
        expiring: list[SecretItem] = []

        for item in self.repository.list_items():
            if item.expires_at is None:
                continue
            if item.expires_at <= deadline:
                item.clear_payload()
                expiring.append(item)
        return expiring

    def close(self) -> None:
        self.repository.close()

    def _normalize_api_token_metadata(
        self,
        metadata: dict[str, Any],
        token: str | None,
        existing_token_hint: Any | None = None,
    ) -> dict[str, Any]:
        provider = str(metadata.get("provider", "")).strip()
        environment = self._normalize_api_environment(metadata.get("environment"))
        scopes = metadata.get("scopes", [])

        if not provider:
            raise ValueError("metadata.provider is required")
        if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
            raise ValueError("metadata.scopes must be a list[str]")

        raw_hint = metadata.get("token_hint")
        if raw_hint:
            token_hint = str(raw_hint)
        elif token:
            token_hint = self._mask_token(token)
        elif existing_token_hint:
            token_hint = str(existing_token_hint)
        else:
            token_hint = "****"  # noqa: S105 - masked fallback, not a real secret

        normalized: dict[str, Any] = {
            "provider": provider,
            "environment": environment,
            "scopes": scopes,
            "token_hint": token_hint,
        }

        warning_days = metadata.get("expiration_warning_days")
        if warning_days is not None:
            normalized["expiration_warning_days"] = int(warning_days)

        notes = metadata.get("notes")
        if notes is not None:
            normalized["notes"] = str(notes)

        return normalized

    @staticmethod
    def _normalize_ssh_metadata(
        metadata: dict[str, Any],
        algorithm: str,
        fingerprint: str,
        public_key_preview: str,
        has_passphrase: bool,
        default_comment: Any | None,
        default_key_size: Any | None,
    ) -> dict[str, Any]:
        if algorithm not in {"ed25519", "rsa", "ecdsa", "dsa"}:
            raise ValueError("metadata.algorithm is invalid")
        if not fingerprint.startswith("SHA256:"):
            raise ValueError("metadata.fingerprint is invalid")
        if not public_key_preview.strip():
            raise ValueError("metadata.public_key_preview is invalid")

        normalized: dict[str, Any] = {
            "algorithm": algorithm,
            "fingerprint": fingerprint,
            "public_key_preview": public_key_preview,
            "has_passphrase": bool(has_passphrase),
        }

        raw_comment = metadata.get("comment")
        if raw_comment is None:
            raw_comment = default_comment
        if raw_comment is not None and str(raw_comment).strip():
            normalized["comment"] = str(raw_comment).strip()

        key_size = default_key_size
        if key_size is None:
            key_size = metadata.get("key_size")
        if key_size is not None:
            normalized["key_size"] = int(key_size)

        return normalized

    @staticmethod
    def _normalize_api_environment(raw_environment: Any) -> str:
        raw_value = str(raw_environment or "").strip().lower()
        if not raw_value:
            return "other"

        normalized = _API_TOKEN_ENV_ALIASES.get(raw_value)
        if normalized is None:
            raise ValueError("metadata.environment is invalid")
        return normalized

    def _encrypt_payload(self, plaintext: str) -> bytes:
        encrypted_data = self.crypto.encrypt(plaintext)
        return json.dumps(encrypted_data).encode("utf-8")

    def _decrypt_payload(self, payload: str | bytes) -> str:
        try:
            payload_text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            encrypted_data = json.loads(payload_text)
            if not isinstance(encrypted_data, dict):
                raise ValueError("malformed encrypted payload")
            return self.crypto.decrypt(encrypted_data)
        except Exception as exc:
            raise ValueError("Unable to decrypt secret payload") from exc

    @staticmethod
    def _mask_token(token: str) -> str:
        suffix = token[-4:] if len(token) >= 4 else token
        return f"****{suffix}"
