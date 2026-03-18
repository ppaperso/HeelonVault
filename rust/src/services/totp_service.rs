use qrcode::render::unicode;
use qrcode::QrCode;
use secrecy::{ExposeSecret, SecretBox};
use sqlx::{Row, SqlitePool};
use totp_rs::{Algorithm, Secret, TOTP};
use uuid::Uuid;

use crate::errors::AppError;
use crate::services::auth_service::AuthService;
use crate::services::crypto_service::{CryptoService, EncryptedPayload, NONCE_LEN};

const TOTP_DIGITS: usize = 6;
const TOTP_STEP: u64 = 30;
const TOTP_SKEW: u8 = 1;

#[derive(Debug, Clone)]
pub struct TotpSetupPayload {
    pub base32_secret: String,
    pub otpauth_url: String,
    pub qr_ascii: String,
}

#[allow(async_fn_in_trait)]
pub trait TotpService {
    async fn is_totp_enabled_for_user_id(&self, user_id: Uuid) -> Result<bool, AppError>;
    async fn is_totp_enabled_for_username(&self, username: &str) -> Result<bool, AppError>;
    fn create_setup_payload(&self, account_name: &str) -> Result<TotpSetupPayload, AppError>;
    fn verify_setup_code(
        &self,
        account_name: &str,
        base32_secret: &str,
        code: &str,
    ) -> Result<bool, AppError>;
    async fn enable_totp(
        &self,
        user_id: Uuid,
        username: &str,
        password: SecretBox<Vec<u8>>,
        base32_secret: &str,
    ) -> Result<(), AppError>;
    async fn disable_totp(&self, user_id: Uuid) -> Result<(), AppError>;
    async fn verify_login_totp(
        &self,
        username: &str,
        password: SecretBox<Vec<u8>>,
        code: &str,
    ) -> Result<bool, AppError>;
}

pub struct SqliteTotpService<TAuth, TCrypto>
where
    TAuth: AuthService + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    pool: SqlitePool,
    auth_service: std::sync::Arc<TAuth>,
    crypto_service: TCrypto,
    issuer: String,
}

impl<TAuth, TCrypto> SqliteTotpService<TAuth, TCrypto>
where
    TAuth: AuthService + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    pub fn new(
        pool: SqlitePool,
        auth_service: std::sync::Arc<TAuth>,
        crypto_service: TCrypto,
        issuer: impl Into<String>,
    ) -> Self {
        Self {
            pool,
            auth_service,
            crypto_service,
            issuer: issuer.into(),
        }
    }

    fn map_storage_err(context: &str, error: impl ToString) -> AppError {
        AppError::Storage(format!("{context}: {}", error.to_string()))
    }

    fn build_totp(&self, account_name: &str, base32_secret: &str) -> Result<TOTP, AppError> {
        let secret_bytes = Secret::Encoded(base32_secret.to_string())
            .to_bytes()
            .map_err(|error| AppError::Validation(format!("invalid TOTP secret: {error}")))?;

        TOTP::new(
            Algorithm::SHA1,
            TOTP_DIGITS,
            TOTP_SKEW,
            TOTP_STEP,
            secret_bytes,
            Some(self.issuer.clone()),
            account_name.to_string(),
        )
        .map_err(|error| AppError::Validation(format!("invalid TOTP setup: {error}")))
    }

    fn is_valid_totp_code(code: &str) -> bool {
        code.len() == TOTP_DIGITS && code.chars().all(|character| character.is_ascii_digit())
    }

    fn serialize_envelope(payload: &EncryptedPayload) -> SecretBox<Vec<u8>> {
        let mut bytes = Vec::with_capacity(NONCE_LEN + payload.ciphertext.expose_secret().len());
        bytes.extend_from_slice(&payload.nonce);
        bytes.extend_from_slice(payload.ciphertext.expose_secret().as_slice());
        SecretBox::new(Box::new(bytes))
    }

    fn deserialize_envelope(bytes: &SecretBox<Vec<u8>>) -> Result<EncryptedPayload, AppError> {
        if bytes.expose_secret().len() <= NONCE_LEN {
            return Err(AppError::Storage("invalid totp_secret payload".to_string()));
        }

        let mut nonce = [0_u8; NONCE_LEN];
        nonce.copy_from_slice(&bytes.expose_secret()[0..NONCE_LEN]);

        Ok(EncryptedPayload {
            nonce,
            ciphertext: SecretBox::new(Box::new(bytes.expose_secret()[NONCE_LEN..].to_vec())),
        })
    }

    async fn load_totp_secret_by_username(
        &self,
        username: &str,
    ) -> Result<Option<SecretBox<Vec<u8>>>, AppError> {
        let row_opt = sqlx::query("SELECT totp_secret FROM users WHERE username = ?1")
            .bind(username)
            .fetch_optional(&self.pool)
            .await
            .map_err(|error| Self::map_storage_err("get totp secret by username", error))?;

        match row_opt {
            Some(row) => {
                let bytes: Option<Vec<u8>> = row
                    .try_get("totp_secret")
                    .map_err(|error| Self::map_storage_err("read totp_secret", error))?;
                Ok(bytes.map(|value| SecretBox::new(Box::new(value))))
            }
            None => Ok(None),
        }
    }

    async fn load_totp_secret_by_user_id(
        &self,
        user_id: Uuid,
    ) -> Result<Option<SecretBox<Vec<u8>>>, AppError> {
        let row_opt = sqlx::query("SELECT totp_secret FROM users WHERE id = ?1")
            .bind(user_id.to_string())
            .fetch_optional(&self.pool)
            .await
            .map_err(|error| Self::map_storage_err("get totp secret by user id", error))?;

        match row_opt {
            Some(row) => {
                let bytes: Option<Vec<u8>> = row
                    .try_get("totp_secret")
                    .map_err(|error| Self::map_storage_err("read totp_secret", error))?;
                Ok(bytes.map(|value| SecretBox::new(Box::new(value))))
            }
            None => Ok(None),
        }
    }
}

impl<TAuth, TCrypto> TotpService for SqliteTotpService<TAuth, TCrypto>
where
    TAuth: AuthService + Send + Sync,
    TCrypto: CryptoService + Send + Sync,
{
    async fn is_totp_enabled_for_user_id(&self, user_id: Uuid) -> Result<bool, AppError> {
        Ok(self.load_totp_secret_by_user_id(user_id).await?.is_some())
    }

    async fn is_totp_enabled_for_username(&self, username: &str) -> Result<bool, AppError> {
        Ok(self.load_totp_secret_by_username(username).await?.is_some())
    }

    fn create_setup_payload(&self, account_name: &str) -> Result<TotpSetupPayload, AppError> {
        if account_name.trim().is_empty() {
            return Err(AppError::Validation(
                "account name is required for TOTP setup".to_string(),
            ));
        }

        let secret = Secret::generate_secret();
        let base32_secret = match secret.to_encoded() {
            Secret::Encoded(value) => value,
            Secret::Raw(_) => {
                return Err(AppError::Validation(
                    "failed to encode TOTP secret".to_string(),
                ));
            }
        };
        let totp = self.build_totp(account_name, base32_secret.as_str())?;
        let otpauth_url = totp.get_url();

        let qr_code = QrCode::new(otpauth_url.as_bytes())
            .map_err(|error| AppError::Validation(format!("failed to generate QR: {error}")))?;
        let qr_ascii = qr_code
            .render::<unicode::Dense1x2>()
            .quiet_zone(true)
            .build();

        Ok(TotpSetupPayload {
            base32_secret,
            otpauth_url,
            qr_ascii,
        })
    }

    fn verify_setup_code(
        &self,
        account_name: &str,
        base32_secret: &str,
        code: &str,
    ) -> Result<bool, AppError> {
        if !Self::is_valid_totp_code(code) {
            return Ok(false);
        }

        let totp = self.build_totp(account_name, base32_secret)?;
        totp.check_current(code)
            .map_err(|error| AppError::Validation(format!("failed to verify TOTP code: {error}")))
    }

    async fn enable_totp(
        &self,
        user_id: Uuid,
        username: &str,
        password: SecretBox<Vec<u8>>,
        base32_secret: &str,
    ) -> Result<(), AppError> {
        if username.trim().is_empty() {
            return Err(AppError::Validation("username must not be empty".to_string()));
        }

        let key_opt = self
            .auth_service
            .derive_key_if_valid(username, password)
            .await?;
        let key = key_opt.ok_or_else(|| AppError::Authorization("invalid credentials".to_string()))?;

        let encrypted = self
            .crypto_service
            .encrypt(
                &SecretBox::new(Box::new(base32_secret.as_bytes().to_vec())),
                &key,
            )
            .await?;
        let envelope = Self::serialize_envelope(&encrypted);

        let result = sqlx::query("UPDATE users SET totp_secret = ?1 WHERE id = ?2")
            .bind(envelope.expose_secret().as_slice())
            .bind(user_id.to_string())
            .execute(&self.pool)
            .await
            .map_err(|error| Self::map_storage_err("enable totp", error))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage("user not found for TOTP activation".to_string()));
        }

        Ok(())
    }

    async fn disable_totp(&self, user_id: Uuid) -> Result<(), AppError> {
        let result = sqlx::query("UPDATE users SET totp_secret = NULL WHERE id = ?1")
            .bind(user_id.to_string())
            .execute(&self.pool)
            .await
            .map_err(|error| Self::map_storage_err("disable totp", error))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage("user not found for TOTP deactivation".to_string()));
        }

        Ok(())
    }

    async fn verify_login_totp(
        &self,
        username: &str,
        password: SecretBox<Vec<u8>>,
        code: &str,
    ) -> Result<bool, AppError> {
        if !Self::is_valid_totp_code(code) {
            return Ok(false);
        }

        let encrypted_secret_opt = self.load_totp_secret_by_username(username).await?;
        let Some(encrypted_secret) = encrypted_secret_opt else {
            return Ok(true);
        };

        let key_opt = self
            .auth_service
            .derive_key_if_valid(username, password)
            .await?;
        let Some(key) = key_opt else {
            return Ok(false);
        };

        let payload = Self::deserialize_envelope(&encrypted_secret)?;
        let decrypted = self.crypto_service.decrypt(&payload, &key).await?;
        let base32_secret = String::from_utf8(decrypted.expose_secret().clone())
            .map_err(|_| AppError::Validation("invalid decrypted TOTP secret".to_string()))?;

        let totp = self.build_totp(username, base32_secret.as_str())?;
        totp.check_current(code)
            .map_err(|error| AppError::Validation(format!("failed to verify login TOTP code: {error}")))
    }
}
