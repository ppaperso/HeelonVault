use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("validation error: {0}")]
    Validation(String),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("conflict: {0}")]
    Conflict(String),
    #[error("storage error: {0}")]
    Storage(String),
    #[error("crypto error: {0}")]
    Crypto(String),
    #[error("authorization error: {0}")]
    Authorization(String),
    #[error("shutdown in progress")]
    ShutdownInProgress,
    #[error("internal error")]
    Internal,
}