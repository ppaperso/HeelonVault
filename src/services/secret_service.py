"""Service applicatif pour la gestion des nouveaux secrets (Phase 1+)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from src.models.secret_item import SecretItem
from src.models.secret_types import SECRET_TYPE_API_TOKEN
from src.repositories.secret_repository import SecretRepository
from src.services.crypto_service import CryptoService

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
