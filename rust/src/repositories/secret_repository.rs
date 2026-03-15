use crate::errors::AppError;
use crate::models::SecretItem;
use secrecy::SecretBox;
use uuid::Uuid;

#[allow(async_fn_in_trait)]
pub trait SecretRepository {
    async fn get_by_id(&self, secret_id: Uuid) -> Result<Option<SecretItem>, AppError>;
    async fn list_by_vault_id(&self, vault_id: Uuid) -> Result<Vec<SecretItem>, AppError>;
    async fn insert_secret_blob(
        &self,
        item: &SecretItem,
        encrypted_secret_blob: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
    async fn update_secret_blob(
        &self,
        secret_id: Uuid,
        encrypted_secret_blob: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
    async fn soft_delete(&self, secret_id: Uuid) -> Result<(), AppError>;
}
