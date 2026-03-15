use secrecy::{ExposeSecret, SecretBox};
use uuid::Uuid;

use crate::errors::AppError;
use crate::models::{BlobStorage, SecretItem, SecretType};
use crate::repositories::secret_repository::SecretRepository;
use crate::services::crypto_service::{CryptoService, EncryptedPayload, NONCE_LEN};

#[derive(Debug)]
pub struct DecryptedSecret {
    pub id: Uuid,
    pub vault_id: Uuid,
    pub secret_type: SecretType,
    pub blob_storage: BlobStorage,
    pub secret_value: SecretBox<Vec<u8>>,
}

#[allow(async_fn_in_trait)]
pub trait SecretService {
    async fn create_secret(
        &self,
        vault_id: Uuid,
        secret_type: SecretType,
        plaintext_secret: SecretBox<Vec<u8>>,
        vault_key: SecretBox<Vec<u8>>,
    ) -> Result<SecretItem, AppError>;
    async fn get_secret(
        &self,
        secret_id: Uuid,
        vault_key: SecretBox<Vec<u8>>,
    ) -> Result<DecryptedSecret, AppError>;
    async fn list_by_vault(&self, vault_id: Uuid) -> Result<Vec<SecretItem>, AppError>;
    async fn soft_delete(&self, secret_id: Uuid) -> Result<(), AppError>;
}

pub struct SecretServiceImpl<TRepo, TCrypto>
where
    TRepo: SecretRepository + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    secret_repo: TRepo,
    crypto_service: TCrypto,
}

impl<TRepo, TCrypto> SecretServiceImpl<TRepo, TCrypto>
where
    TRepo: SecretRepository + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    pub fn new(secret_repo: TRepo, crypto_service: TCrypto) -> Self {
        Self {
            secret_repo,
            crypto_service,
        }
    }

    fn blob_storage_for_type(secret_type: SecretType) -> BlobStorage {
        match secret_type {
            SecretType::Password | SecretType::ApiToken | SecretType::SshKey => {
                BlobStorage::Inline
            }
            SecretType::SecureDocument => BlobStorage::File,
        }
    }

    fn serialize_payload(payload: &EncryptedPayload) -> SecretBox<Vec<u8>> {
        let mut bytes = Vec::with_capacity(NONCE_LEN + payload.ciphertext.expose_secret().len());
        bytes.extend_from_slice(&payload.nonce);
        bytes.extend_from_slice(payload.ciphertext.expose_secret().as_slice());
        SecretBox::new(Box::new(bytes))
    }

    fn deserialize_payload(bytes: &SecretBox<Vec<u8>>) -> Result<EncryptedPayload, AppError> {
        if bytes.expose_secret().len() < NONCE_LEN {
            return Err(AppError::Storage("secret blob envelope is invalid".to_string()));
        }

        let mut nonce = [0_u8; NONCE_LEN];
        nonce.copy_from_slice(&bytes.expose_secret()[0..NONCE_LEN]);
        let ciphertext = bytes.expose_secret()[NONCE_LEN..].to_vec();

        Ok(EncryptedPayload {
            nonce,
            ciphertext: SecretBox::new(Box::new(ciphertext)),
        })
    }

    fn validate_plaintext_secret(plaintext_secret: &SecretBox<Vec<u8>>) -> Result<(), AppError> {
        if plaintext_secret.expose_secret().is_empty() {
            return Err(AppError::Validation(
                "secret value must not be empty".to_string(),
            ));
        }

        Ok(())
    }
}

impl<TRepo, TCrypto> SecretService for SecretServiceImpl<TRepo, TCrypto>
where
    TRepo: SecretRepository + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    async fn create_secret(
        &self,
        vault_id: Uuid,
        secret_type: SecretType,
        plaintext_secret: SecretBox<Vec<u8>>,
        vault_key: SecretBox<Vec<u8>>,
    ) -> Result<SecretItem, AppError> {
        Self::validate_plaintext_secret(&plaintext_secret)?;

        let blob_storage = Self::blob_storage_for_type(secret_type);
        let encrypted_payload = self
            .crypto_service
            .encrypt(&plaintext_secret, &vault_key)
            .await?;
        let serialized_payload = Self::serialize_payload(&encrypted_payload);
        let stored_blob = SecretBox::new(Box::new(serialized_payload.expose_secret().clone()));

        let item = SecretItem {
            id: Uuid::new_v4(),
            vault_id,
            secret_type,
            blob_storage,
            secret_blob: stored_blob,
        };

        self.secret_repo
            .insert_secret_blob(&item, serialized_payload)
            .await?;

        Ok(item)
    }

    async fn get_secret(
        &self,
        secret_id: Uuid,
        vault_key: SecretBox<Vec<u8>>,
    ) -> Result<DecryptedSecret, AppError> {
        let item = self
            .secret_repo
            .get_by_id(secret_id)
            .await?
            .ok_or_else(|| AppError::NotFound("secret not found".to_string()))?;

        let payload = Self::deserialize_payload(&item.secret_blob)?;
        let secret_value = self.crypto_service.decrypt(&payload, &vault_key).await?;

        Ok(DecryptedSecret {
            id: item.id,
            vault_id: item.vault_id,
            secret_type: item.secret_type,
            blob_storage: item.blob_storage,
            secret_value,
        })
    }

    async fn list_by_vault(&self, vault_id: Uuid) -> Result<Vec<SecretItem>, AppError> {
        self.secret_repo.list_by_vault_id(vault_id).await
    }

    async fn soft_delete(&self, secret_id: Uuid) -> Result<(), AppError> {
        self.secret_repo.soft_delete(secret_id).await
    }
}

#[cfg(test)]
mod tests {
    use super::{DecryptedSecret, SecretService, SecretServiceImpl};
    use crate::errors::AppError;
    use crate::models::{BlobStorage, SecretItem, SecretType};
    use crate::repositories::secret_repository::SecretRepository;
    use crate::services::crypto_service::{CryptoService, EncryptedPayload, NONCE_LEN};
    use secrecy::{ExposeSecret, SecretBox, SecretString};
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex};
    use uuid::Uuid;

    struct StoredSecretRecord {
        id: Uuid,
        vault_id: Uuid,
        secret_type: SecretType,
        blob_storage: BlobStorage,
        blob: Vec<u8>,
        deleted: bool,
    }

    #[derive(Default, Clone)]
    struct StubSecretRepository {
        items: Arc<Mutex<HashMap<Uuid, StoredSecretRecord>>>,
    }

    impl StubSecretRepository {
        fn lock_items(
            &self,
        ) -> Result<std::sync::MutexGuard<'_, HashMap<Uuid, StoredSecretRecord>>, AppError> {
            self.items
                .lock()
                .map_err(|_| AppError::Storage("secret repository lock poisoned".to_string()))
        }
    }

    impl SecretRepository for StubSecretRepository {
        async fn get_by_id(&self, secret_id: Uuid) -> Result<Option<SecretItem>, AppError> {
            let items = self.lock_items()?;
            let item_opt = items.get(&secret_id);

            match item_opt {
                Some(item) if !item.deleted => Ok(Some(SecretItem {
                    id: item.id,
                    vault_id: item.vault_id,
                    secret_type: item.secret_type,
                    blob_storage: item.blob_storage,
                    secret_blob: SecretBox::new(Box::new(item.blob.clone())),
                })),
                Some(_) => Ok(None),
                None => Ok(None),
            }
        }

        async fn list_by_vault_id(&self, vault_id: Uuid) -> Result<Vec<SecretItem>, AppError> {
            let items = self.lock_items()?;
            let listed = items
                .values()
                .filter(|item| item.vault_id == vault_id && !item.deleted)
                .map(|item| SecretItem {
                    id: item.id,
                    vault_id: item.vault_id,
                    secret_type: item.secret_type,
                    blob_storage: item.blob_storage,
                    secret_blob: SecretBox::new(Box::new(item.blob.clone())),
                })
                .collect();

            Ok(listed)
        }

        async fn insert_secret_blob(
            &self,
            item: &SecretItem,
            encrypted_secret_blob: SecretBox<Vec<u8>>,
        ) -> Result<(), AppError> {
            let mut items = self.lock_items()?;
            items.insert(
                item.id,
                StoredSecretRecord {
                    id: item.id,
                    vault_id: item.vault_id,
                    secret_type: item.secret_type,
                    blob_storage: item.blob_storage,
                    blob: encrypted_secret_blob.expose_secret().clone(),
                    deleted: false,
                },
            );
            Ok(())
        }

        async fn update_secret_blob(
            &self,
            secret_id: Uuid,
            encrypted_secret_blob: SecretBox<Vec<u8>>,
        ) -> Result<(), AppError> {
            let mut items = self.lock_items()?;
            let item = items
                .get_mut(&secret_id)
                .ok_or_else(|| AppError::Storage("secret not found for update".to_string()))?;
            item.blob = encrypted_secret_blob.expose_secret().clone();
            Ok(())
        }

        async fn soft_delete(&self, secret_id: Uuid) -> Result<(), AppError> {
            let mut items = self.lock_items()?;
            let item = items
                .get_mut(&secret_id)
                .ok_or_else(|| AppError::Storage("secret not found for delete".to_string()))?;
            item.deleted = true;
            Ok(())
        }
    }

    #[derive(Default, Clone)]
    struct StubCryptoService;

    impl CryptoService for StubCryptoService {
        async fn generate_kdf_salt(&self) -> Result<SecretBox<Vec<u8>>, AppError> {
            Ok(SecretBox::new(Box::new(vec![1_u8; 32])))
        }

        async fn derive_key(
            &self,
            _password: &SecretString,
            _salt: &SecretBox<Vec<u8>>,
        ) -> Result<SecretBox<Vec<u8>>, AppError> {
            Ok(SecretBox::new(Box::new(vec![2_u8; 32])))
        }

        async fn encrypt(
            &self,
            plaintext: &SecretBox<Vec<u8>>,
            _key: &SecretBox<Vec<u8>>,
        ) -> Result<EncryptedPayload, AppError> {
            let mut nonce = [0_u8; NONCE_LEN];
            nonce[0] = 17;

            let mut ciphertext = plaintext.expose_secret().clone();
            ciphertext.reverse();

            Ok(EncryptedPayload {
                nonce,
                ciphertext: SecretBox::new(Box::new(ciphertext)),
            })
        }

        async fn decrypt(
            &self,
            payload: &EncryptedPayload,
            _key: &SecretBox<Vec<u8>>,
        ) -> Result<SecretBox<Vec<u8>>, AppError> {
            let mut plaintext = payload.ciphertext.expose_secret().clone();
            plaintext.reverse();
            Ok(SecretBox::new(Box::new(plaintext)))
        }
    }

    async fn assert_secret_roundtrip(
        secret_type: SecretType,
        plaintext: &[u8],
    ) -> Result<DecryptedSecret, AppError> {
        let repo = StubSecretRepository::default();
        let service = SecretServiceImpl::new(repo.clone(), StubCryptoService);
        let vault_id = Uuid::new_v4();
        let vault_key = SecretBox::new(Box::new(vec![7_u8; 32]));

        let created = service
            .create_secret(
                vault_id,
                secret_type,
                SecretBox::new(Box::new(plaintext.to_vec())),
                SecretBox::new(Box::new(vault_key.expose_secret().clone())),
            )
            .await?;

        match secret_type {
            SecretType::Password | SecretType::ApiToken | SecretType::SshKey => {
                if !matches!(created.blob_storage, BlobStorage::Inline) {
                    return Err(AppError::Internal);
                }
            }
            SecretType::SecureDocument => {
                if !matches!(created.blob_storage, BlobStorage::File) {
                    return Err(AppError::Internal);
                }
            }
        }

        if created.secret_blob.expose_secret().len() <= NONCE_LEN {
            return Err(AppError::Internal);
        }

        service.get_secret(created.id, vault_key).await
    }

    #[tokio::test]
    async fn create_and_get_password_secret() {
        let result = assert_secret_roundtrip(SecretType::Password, b"super-secret-password").await;
        assert!(result.is_ok(), "password roundtrip should succeed");
        let decrypted = match result {
            Ok(value) => value,
            Err(_) => return,
        };

        assert!(matches!(decrypted.secret_type, SecretType::Password));
        assert!(matches!(decrypted.blob_storage, BlobStorage::Inline));
        assert_eq!(
            decrypted.secret_value.expose_secret().as_slice(),
            b"super-secret-password"
        );
    }

    #[tokio::test]
    async fn create_and_get_api_token_secret() {
        let result = assert_secret_roundtrip(SecretType::ApiToken, b"token-abc-123").await;
        assert!(result.is_ok(), "api token roundtrip should succeed");
        let decrypted = match result {
            Ok(value) => value,
            Err(_) => return,
        };

        assert!(matches!(decrypted.secret_type, SecretType::ApiToken));
        assert!(matches!(decrypted.blob_storage, BlobStorage::Inline));
        assert_eq!(decrypted.secret_value.expose_secret().as_slice(), b"token-abc-123");
    }

    #[tokio::test]
    async fn create_and_get_ssh_key_secret() {
        let result = assert_secret_roundtrip(
            SecretType::SshKey,
            b"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEexample",
        )
        .await;
        assert!(result.is_ok(), "ssh key roundtrip should succeed");
        let decrypted = match result {
            Ok(value) => value,
            Err(_) => return,
        };

        assert!(matches!(decrypted.secret_type, SecretType::SshKey));
        assert!(matches!(decrypted.blob_storage, BlobStorage::Inline));
        assert_eq!(
            decrypted.secret_value.expose_secret().as_slice(),
            b"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEexample"
        );
    }

    #[tokio::test]
    async fn list_by_vault_and_soft_delete_excludes_deleted_secret() {
        let repo = StubSecretRepository::default();
        let service = SecretServiceImpl::new(repo, StubCryptoService);
        let vault_id = Uuid::new_v4();
        let other_vault_id = Uuid::new_v4();
        let vault_key = SecretBox::new(Box::new(vec![8_u8; 32]));

        let first_result = service
            .create_secret(
                vault_id,
                SecretType::Password,
                SecretBox::new(Box::new(b"first-secret".to_vec())),
                SecretBox::new(Box::new(vault_key.expose_secret().clone())),
            )
            .await;
        let second_result = service
            .create_secret(
                vault_id,
                SecretType::ApiToken,
                SecretBox::new(Box::new(b"second-secret".to_vec())),
                SecretBox::new(Box::new(vault_key.expose_secret().clone())),
            )
            .await;
        let third_result = service
            .create_secret(
                other_vault_id,
                SecretType::SshKey,
                SecretBox::new(Box::new(b"third-secret".to_vec())),
                vault_key,
            )
            .await;

        assert!(first_result.is_ok(), "first create should succeed");
        assert!(second_result.is_ok(), "second create should succeed");
        assert!(third_result.is_ok(), "third create should succeed");
        if first_result.is_err() || second_result.is_err() || third_result.is_err() {
            return;
        }

        let first = match first_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let listed_before_result = service.list_by_vault(vault_id).await;
        assert!(listed_before_result.is_ok(), "list before delete should succeed");
        let listed_before = match listed_before_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(listed_before.len(), 2);

        let delete_result = service.soft_delete(first.id).await;
        assert!(delete_result.is_ok(), "soft delete should succeed");
        if delete_result.is_err() {
            return;
        }

        let listed_after_result = service.list_by_vault(vault_id).await;
        assert!(listed_after_result.is_ok(), "list after delete should succeed");
        let listed_after = match listed_after_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(listed_after.len(), 1);
        assert_ne!(listed_after[0].id, first.id);
    }
}
