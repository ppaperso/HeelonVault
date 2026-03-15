use crate::errors::AppError;
use crate::models::User;
use secrecy::SecretBox;
use uuid::Uuid;

#[allow(async_fn_in_trait)]
pub trait UserRepository {
    async fn get_by_id(&self, user_id: Uuid) -> Result<Option<User>, AppError>;
    async fn get_by_username(&self, username: &str) -> Result<Option<User>, AppError>;
    async fn update_password_envelope(
        &self,
        user_id: Uuid,
        encrypted_password_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
    async fn update_totp_secret_envelope(
        &self,
        user_id: Uuid,
        encrypted_totp_secret_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
}
