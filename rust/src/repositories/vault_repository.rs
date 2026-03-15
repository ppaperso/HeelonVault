use crate::errors::AppError;
use crate::models::Vault;
use secrecy::SecretBox;
use uuid::Uuid;

#[allow(async_fn_in_trait)]
pub trait VaultRepository {
    async fn get_by_id(&self, vault_id: Uuid) -> Result<Option<Vault>, AppError>;
    async fn list_by_user_id(&self, user_id: Uuid) -> Result<Vec<Vault>, AppError>;
    async fn create_vault(&self, vault: &Vault) -> Result<(), AppError>;
    async fn update_vault_key_envelope(
        &self,
        vault_id: Uuid,
        encrypted_vault_key_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
}
