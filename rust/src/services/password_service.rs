use crate::services::ServiceError;

pub trait PasswordService {
    fn validate_password_policy(&self) -> Result<(), ServiceError>;
}

pub struct PasswordServiceImpl;
