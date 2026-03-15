use crate::services::ServiceError;

pub trait VaultService {
    fn open_vault(&self) -> Result<(), ServiceError>;
}

pub struct VaultServiceImpl;
