use crate::services::ServiceError;

pub trait SecretService {
    fn store_secret(&self) -> Result<(), ServiceError>;
}

pub struct SecretServiceImpl;
