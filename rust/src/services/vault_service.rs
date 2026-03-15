use secrecy::{ExposeSecret, SecretBox};
use uuid::Uuid;

use crate::errors::AppError;
use crate::models::Vault;
use crate::repositories::vault_repository::VaultRepository;
use crate::services::crypto_service::{CryptoService, EncryptedPayload, NONCE_LEN};

pub const VAULT_KEY_LEN: usize = 32;

#[allow(async_fn_in_trait)]
pub trait VaultKeyEnvelopeRepository {
    async fn get_vault_key_envelope(&self, vault_id: Uuid) -> Result<Option<SecretBox<Vec<u8>>>, AppError>;
}

#[allow(async_fn_in_trait)]
pub trait VaultService {
    async fn create_vault(
        &self,
        owner_user_id: Uuid,
        name: &str,
        master_key: SecretBox<Vec<u8>>,
    ) -> Result<Vault, AppError>;
    async fn open_vault(
        &self,
        vault_id: Uuid,
        master_key: SecretBox<Vec<u8>>,
    ) -> Result<SecretBox<Vec<u8>>, AppError>;
    async fn list_user_vaults(&self, user_id: Uuid) -> Result<Vec<Vault>, AppError>;
}

pub struct VaultServiceImpl<TVaultRepo, TEnvelopeRepo, TCrypto>
where
    TVaultRepo: VaultRepository + Send + Sync,
    TEnvelopeRepo: VaultKeyEnvelopeRepository + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    vault_repo: TVaultRepo,
    envelope_repo: TEnvelopeRepo,
    crypto_service: TCrypto,
}

impl<TVaultRepo, TEnvelopeRepo, TCrypto> VaultServiceImpl<TVaultRepo, TEnvelopeRepo, TCrypto>
where
    TVaultRepo: VaultRepository + Send + Sync,
    TEnvelopeRepo: VaultKeyEnvelopeRepository + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    pub fn new(vault_repo: TVaultRepo, envelope_repo: TEnvelopeRepo, crypto_service: TCrypto) -> Self {
        Self {
            vault_repo,
            envelope_repo,
            crypto_service,
        }
    }

    fn serialize_envelope(payload: &EncryptedPayload) -> SecretBox<Vec<u8>> {
        let mut bytes =
            Vec::with_capacity(NONCE_LEN + payload.ciphertext.expose_secret().len());
        bytes.extend_from_slice(&payload.nonce);
        bytes.extend_from_slice(payload.ciphertext.expose_secret().as_slice());
        SecretBox::new(Box::new(bytes))
    }

    fn deserialize_envelope(bytes: &SecretBox<Vec<u8>>) -> Result<EncryptedPayload, AppError> {
        if bytes.expose_secret().len() < NONCE_LEN {
            return Err(AppError::Storage("vault key envelope is invalid".to_string()));
        }

        let mut nonce = [0_u8; NONCE_LEN];
        nonce.copy_from_slice(&bytes.expose_secret()[0..NONCE_LEN]);
        let ciphertext = bytes.expose_secret()[NONCE_LEN..].to_vec();

        Ok(EncryptedPayload {
            nonce,
            ciphertext: SecretBox::new(Box::new(ciphertext)),
        })
    }

    fn generate_vault_key() -> Result<SecretBox<Vec<u8>>, AppError> {
        let mut key = vec![0_u8; VAULT_KEY_LEN];
        getrandom::fill(key.as_mut_slice())
            .map_err(|err| AppError::Crypto(format!("vault key generation failed: {err}")))?;
        Ok(SecretBox::new(Box::new(key)))
    }
}

impl<TVaultRepo, TEnvelopeRepo, TCrypto> VaultService for VaultServiceImpl<TVaultRepo, TEnvelopeRepo, TCrypto>
where
    TVaultRepo: VaultRepository + Send + Sync,
    TEnvelopeRepo: VaultKeyEnvelopeRepository + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    async fn create_vault(
        &self,
        owner_user_id: Uuid,
        name: &str,
        master_key: SecretBox<Vec<u8>>,
    ) -> Result<Vault, AppError> {
        if name.trim().is_empty() {
            return Err(AppError::Validation("vault name must not be empty".to_string()));
        }

        let vault = Vault {
            id: Uuid::new_v4(),
            owner_user_id,
            name: name.to_string(),
        };

        let vault_key = Self::generate_vault_key()?;
        let encrypted_payload = self.crypto_service.encrypt(&vault_key, &master_key).await?;
        let serialized = Self::serialize_envelope(&encrypted_payload);

        self.vault_repo.create_vault(&vault).await?;
        self.vault_repo
            .update_vault_key_envelope(vault.id, serialized)
            .await?;

        Ok(vault)
    }

    async fn open_vault(
        &self,
        vault_id: Uuid,
        master_key: SecretBox<Vec<u8>>,
    ) -> Result<SecretBox<Vec<u8>>, AppError> {
        let vault_opt = self.vault_repo.get_by_id(vault_id).await?;
        if vault_opt.is_none() {
            return Err(AppError::NotFound("vault not found".to_string()));
        }

        let envelope_opt = self.envelope_repo.get_vault_key_envelope(vault_id).await?;
        let envelope = envelope_opt
            .ok_or_else(|| AppError::Storage("missing vault key envelope".to_string()))?;

        let payload = Self::deserialize_envelope(&envelope)?;
        self.crypto_service.decrypt(&payload, &master_key).await
    }

    async fn list_user_vaults(&self, user_id: Uuid) -> Result<Vec<Vault>, AppError> {
        self.vault_repo.list_by_user_id(user_id).await
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::sync::{Arc, Mutex};

    use secrecy::{ExposeSecret, SecretBox};
    use uuid::Uuid;

    use crate::errors::AppError;
    use crate::models::Vault;
    use crate::repositories::vault_repository::VaultRepository;
    use crate::services::crypto_service::{CryptoService, EncryptedPayload, NONCE_LEN};

    use super::{VaultKeyEnvelopeRepository, VaultService, VaultServiceImpl, VAULT_KEY_LEN};

    #[derive(Default, Clone)]
    struct StubVaultRepository {
        vaults: Arc<Mutex<HashMap<Uuid, Vault>>>,
        envelopes: Arc<Mutex<HashMap<Uuid, SecretBox<Vec<u8>>>>>,
    }

    impl StubVaultRepository {
        fn lock_vaults(&self) -> Result<std::sync::MutexGuard<'_, HashMap<Uuid, Vault>>, AppError> {
            self.vaults
                .lock()
                .map_err(|_| AppError::Storage("vault lock poisoned".to_string()))
        }

        fn lock_envelopes(
            &self,
        ) -> Result<std::sync::MutexGuard<'_, HashMap<Uuid, SecretBox<Vec<u8>>>>, AppError> {
            self.envelopes
                .lock()
                .map_err(|_| AppError::Storage("envelope lock poisoned".to_string()))
        }
    }

    impl VaultRepository for StubVaultRepository {
        async fn get_by_id(&self, vault_id: Uuid) -> Result<Option<Vault>, AppError> {
            let guard = self.lock_vaults()?;
            Ok(guard.get(&vault_id).cloned())
        }

        async fn list_by_user_id(&self, user_id: Uuid) -> Result<Vec<Vault>, AppError> {
            let guard = self.lock_vaults()?;
            Ok(guard
                .values()
                .filter(|vault| vault.owner_user_id == user_id)
                .cloned()
                .collect())
        }

        async fn create_vault(&self, vault: &Vault) -> Result<(), AppError> {
            let mut guard = self.lock_vaults()?;
            guard.insert(vault.id, vault.clone());
            Ok(())
        }

        async fn update_vault_key_envelope(
            &self,
            vault_id: Uuid,
            encrypted_vault_key_envelope: SecretBox<Vec<u8>>,
        ) -> Result<(), AppError> {
            let mut guard = self.lock_envelopes()?;
            guard.insert(vault_id, encrypted_vault_key_envelope);
            Ok(())
        }
    }

    impl VaultKeyEnvelopeRepository for StubVaultRepository {
        async fn get_vault_key_envelope(
            &self,
            vault_id: Uuid,
        ) -> Result<Option<SecretBox<Vec<u8>>>, AppError> {
            let guard = self.lock_envelopes()?;
            Ok(guard
                .get(&vault_id)
                .map(|bytes| SecretBox::new(Box::new(bytes.expose_secret().clone()))))
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
            _password: &secrecy::SecretString,
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
            nonce[0] = 42;

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

    #[tokio::test]
    async fn create_vault_persists_envelope_and_lists() {
        let repo = StubVaultRepository::default();
        let service = VaultServiceImpl::new(repo.clone(), repo.clone(), StubCryptoService);
        let owner_user_id = Uuid::new_v4();
        let master_key = SecretBox::new(Box::new(vec![8_u8; 32]));

        let vault_result = service
            .create_vault(owner_user_id, "Work", master_key)
            .await;
        assert!(vault_result.is_ok(), "create_vault should succeed");
        let vault = match vault_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let listed_result = service.list_user_vaults(owner_user_id).await;
        assert!(listed_result.is_ok(), "list should succeed");
        let listed = match listed_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].id, vault.id);

        let envelope_result = repo.get_vault_key_envelope(vault.id).await;
        assert!(envelope_result.is_ok(), "envelope load should succeed");
        let envelope_opt = match envelope_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(envelope_opt.is_some(), "envelope should be stored");
        let envelope = match envelope_opt {
            Some(value) => value,
            None => return,
        };
        assert!(envelope.expose_secret().len() > NONCE_LEN);
    }

    #[tokio::test]
    async fn open_vault_decrypts_key() {
        let repo = StubVaultRepository::default();
        let service = VaultServiceImpl::new(repo.clone(), repo.clone(), StubCryptoService);
        let owner_user_id = Uuid::new_v4();
        let master_key = SecretBox::new(Box::new(vec![9_u8; 32]));

        let created_result = service
            .create_vault(owner_user_id, "Personal", SecretBox::new(Box::new(vec![9_u8; 32])))
            .await;
        assert!(created_result.is_ok(), "create should succeed");
        let created = match created_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let opened_result = service.open_vault(created.id, master_key).await;
        assert!(opened_result.is_ok(), "open should succeed");
        let opened_key = match opened_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(opened_key.expose_secret().len(), VAULT_KEY_LEN);
    }

    #[tokio::test]
    async fn open_vault_returns_not_found() {
        let repo = StubVaultRepository::default();
        let service = VaultServiceImpl::new(repo.clone(), repo, StubCryptoService);

        let result = service
            .open_vault(Uuid::new_v4(), SecretBox::new(Box::new(vec![1_u8; 32])))
            .await;
        assert!(matches!(result, Err(AppError::NotFound(_))));
    }

    #[tokio::test]
    async fn open_vault_rejects_invalid_envelope() {
        let repo = StubVaultRepository::default();
        let service = VaultServiceImpl::new(repo.clone(), repo.clone(), StubCryptoService);

        let vault = Vault {
            id: Uuid::new_v4(),
            owner_user_id: Uuid::new_v4(),
            name: "Broken".to_string(),
        };

        let create_result = repo.create_vault(&vault).await;
        assert!(create_result.is_ok(), "seed vault should succeed");
        if create_result.is_err() {
            return;
        }

        let envelope_result = repo
            .update_vault_key_envelope(vault.id, SecretBox::new(Box::new(vec![1_u8, 2_u8, 3_u8])))
            .await;
        assert!(envelope_result.is_ok(), "seed envelope should succeed");
        if envelope_result.is_err() {
            return;
        }

        let opened_result = service
            .open_vault(vault.id, SecretBox::new(Box::new(vec![7_u8; 32])))
            .await;
        assert!(matches!(opened_result, Err(AppError::Storage(_))));
    }
}
