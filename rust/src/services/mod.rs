pub mod auth_service;
pub mod backup_service;
pub mod crypto_service;
pub mod password_service;
pub mod secret_service;
pub mod vault_service;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ServiceError {
    #[error("service error placeholder")]
    Placeholder,
}
