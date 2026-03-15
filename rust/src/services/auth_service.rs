use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use secrecy::{ExposeSecret, SecretBox, SecretString};

use crate::errors::AppError;
use crate::services::crypto_service::CryptoService;

struct UserCredentialRecord {
    password_salt: SecretBox<Vec<u8>>,
    password_hash: SecretBox<Vec<u8>>,
}

#[allow(async_fn_in_trait)]
pub trait AuthService {
    async fn create_user(
        &self,
        username: &str,
        password: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
    async fn verify_password(
        &self,
        username: &str,
        password: SecretBox<Vec<u8>>,
    ) -> Result<bool, AppError>;
    fn signal_shutdown(&self);
}

pub struct AuthServiceImpl<TCrypto>
where
    TCrypto: CryptoService + Send + Sync,
{
    crypto_service: TCrypto,
    shutdown_in_progress: AtomicBool,
    credentials: Mutex<HashMap<String, UserCredentialRecord>>,
}

impl<TCrypto> AuthServiceImpl<TCrypto>
where
    TCrypto: CryptoService + Send + Sync,
{
    pub fn new(crypto_service: TCrypto) -> Self {
        Self {
            crypto_service,
            shutdown_in_progress: AtomicBool::new(false),
            credentials: Mutex::new(HashMap::new()),
        }
    }

    fn ensure_not_shutting_down(&self) -> Result<(), AppError> {
        if self.shutdown_in_progress.load(Ordering::SeqCst) {
            return Err(AppError::ShutdownInProgress);
        }
        Ok(())
    }

    fn password_to_secret_string(
        password: &SecretBox<Vec<u8>>,
    ) -> Result<SecretString, AppError> {
        let password_text = std::str::from_utf8(password.expose_secret().as_slice())
            .map_err(|_| AppError::Validation("password must be valid utf-8".to_string()))?;
        Ok(SecretString::new(password_text.to_owned().into_boxed_str()))
    }

    fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
        if left.len() != right.len() {
            return false;
        }

        let mut diff = 0_u8;
        let mut index = 0_usize;
        while index < left.len() {
            diff |= left[index] ^ right[index];
            index += 1;
        }

        diff == 0
    }
}

impl<TCrypto> AuthService for AuthServiceImpl<TCrypto>
where
    TCrypto: CryptoService + Send + Sync,
{
    async fn create_user(
        &self,
        username: &str,
        password: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError> {
        self.ensure_not_shutting_down()?;

        if username.trim().is_empty() {
            return Err(AppError::Validation("username must not be empty".to_string()));
        }

        {
            let credentials = self
                .credentials
                .lock()
                .map_err(|_| AppError::Internal)?;
            if credentials.contains_key(username) {
                return Err(AppError::Conflict("username already exists".to_string()));
            }
        }

        let secret_password = Self::password_to_secret_string(&password)?;
        let password_salt = self.crypto_service.generate_kdf_salt().await?;
        let password_hash = self
            .crypto_service
            .derive_key(&secret_password, &password_salt)
            .await?;

        let mut credentials = self
            .credentials
            .lock()
            .map_err(|_| AppError::Internal)?;
        credentials.insert(
            username.to_string(),
            UserCredentialRecord {
                password_salt,
                password_hash,
            },
        );

        Ok(())
    }

    async fn verify_password(
        &self,
        username: &str,
        password: SecretBox<Vec<u8>>,
    ) -> Result<bool, AppError> {
        self.ensure_not_shutting_down()?;

        let secret_password = Self::password_to_secret_string(&password)?;

        let (password_salt, expected_password_hash) = {
            let credentials = self
                .credentials
                .lock()
                .map_err(|_| AppError::Internal)?;
            let record = credentials
                .get(username)
                .ok_or_else(|| AppError::Authorization("invalid credentials".to_string()))?;
            (
                SecretBox::new(Box::new(record.password_salt.expose_secret().clone())),
                record.password_hash.expose_secret().clone(),
            )
        };

        let derived_hash = self
            .crypto_service
            .derive_key(&secret_password, &password_salt)
            .await?;

        Ok(Self::constant_time_eq(
            derived_hash.expose_secret().as_slice(),
            expected_password_hash.as_slice(),
        ))
    }

    fn signal_shutdown(&self) {
        self.shutdown_in_progress.store(true, Ordering::SeqCst);
    }
}
