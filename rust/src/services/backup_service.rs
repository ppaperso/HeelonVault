use crate::services::ServiceError;

pub trait BackupService {
    fn create_backup(&self) -> Result<(), ServiceError>;
}

pub struct BackupServiceImpl;
