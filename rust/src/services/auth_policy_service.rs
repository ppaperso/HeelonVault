use chrono::Utc;
use sqlx::{Row, SqlitePool};
use tracing::{error, info};

use crate::errors::AppError;

const MAX_FAILED_ATTEMPTS: i64 = 5;
const LOCK_WINDOW_SECS: i64 = 5 * 60;
const DEFAULT_AUTO_LOCK_DELAY_MINS: i64 = 5;

#[derive(Debug, Clone, Copy)]
pub struct AuthPolicyState {
    pub failed_attempts: i64,
    pub remaining_lock_secs: i64,
}

impl AuthPolicyState {
    pub fn is_locked(&self) -> bool {
        self.failed_attempts >= MAX_FAILED_ATTEMPTS && self.remaining_lock_secs > 0
    }
}

#[allow(async_fn_in_trait)]
pub trait AuthPolicyService {
    async fn get_state(&self, username: &str) -> Result<AuthPolicyState, AppError>;
    async fn record_failed_attempt(&self, username: &str) -> Result<AuthPolicyState, AppError>;
    async fn reset_failed_attempts(&self, username: &str) -> Result<(), AppError>;
    async fn get_auto_lock_delay(&self, username: &str) -> Result<i64, AppError>;
    async fn update_auto_lock_delay(&self, username: &str, mins: i64) -> Result<(), AppError>;
}

pub struct SqlxAuthPolicyService {
    pool: SqlitePool,
}

impl SqlxAuthPolicyService {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    fn map_storage_err(context: &str, error: impl ToString) -> AppError {
        AppError::Storage(format!("{context}: {}", error.to_string()))
    }

    async fn ensure_row_exists(&self, username: &str) -> Result<(), AppError> {
        sqlx::query(
            "INSERT INTO auth_policy (username, failed_attempts, last_attempt_at)
             VALUES (?1, 0, NULL)
             ON CONFLICT(username) DO NOTHING",
        )
        .bind(username)
        .execute(&self.pool)
        .await
        .map_err(|error| Self::map_storage_err("ensure auth_policy row", error))?;

        Ok(())
    }

    fn remaining_lock_secs(failed_attempts: i64, last_attempt_at: Option<i64>, now_ts: i64) -> i64 {
        if failed_attempts < MAX_FAILED_ATTEMPTS {
            return 0;
        }

        let Some(last_ts) = last_attempt_at else {
            return 0;
        };

        let elapsed = now_ts.saturating_sub(last_ts);
        if elapsed >= LOCK_WINDOW_SECS {
            0
        } else {
            LOCK_WINDOW_SECS - elapsed
        }
    }

    fn is_allowed_auto_lock_delay(mins: i64) -> bool {
        matches!(mins, 1 | 5 | 10 | 30)
    }
}

impl AuthPolicyService for SqlxAuthPolicyService {
    async fn get_state(&self, username: &str) -> Result<AuthPolicyState, AppError> {
        if username.trim().is_empty() {
            return Ok(AuthPolicyState {
                failed_attempts: 0,
                remaining_lock_secs: 0,
            });
        }

        self.ensure_row_exists(username).await?;

        let row = sqlx::query(
            "SELECT failed_attempts, last_attempt_at
             FROM auth_policy
             WHERE username = ?1",
        )
        .bind(username)
        .fetch_one(&self.pool)
        .await
        .map_err(|error| Self::map_storage_err("get auth_policy state", error))?;

        let failed_attempts: i64 = row
            .try_get("failed_attempts")
            .map_err(|error| Self::map_storage_err("read failed_attempts", error))?;
        let last_attempt_at: Option<i64> = row
            .try_get("last_attempt_at")
            .map_err(|error| Self::map_storage_err("read last_attempt_at", error))?;

        let now_ts = Utc::now().timestamp();
        Ok(AuthPolicyState {
            failed_attempts,
            remaining_lock_secs: Self::remaining_lock_secs(failed_attempts, last_attempt_at, now_ts),
        })
    }

    async fn record_failed_attempt(&self, username: &str) -> Result<AuthPolicyState, AppError> {
        if username.trim().is_empty() {
            return Ok(AuthPolicyState {
                failed_attempts: 1,
                remaining_lock_secs: 0,
            });
        }

        self.ensure_row_exists(username).await?;
        let now_ts = Utc::now().timestamp();

        sqlx::query(
            "UPDATE auth_policy
             SET failed_attempts = failed_attempts + 1,
                 last_attempt_at = ?2
             WHERE username = ?1",
        )
        .bind(username)
        .bind(now_ts)
        .execute(&self.pool)
        .await
        .map_err(|error| Self::map_storage_err("record failed auth attempt", error))?;

        let state = self.get_state(username).await?;
        if state.failed_attempts == 3 || state.failed_attempts == 5 {
            error!(
                username = %username,
                failed_attempts = state.failed_attempts,
                remaining_lock_secs = state.remaining_lock_secs,
                "critical login failure threshold reached"
            );
        }

        Ok(state)
    }

    async fn reset_failed_attempts(&self, username: &str) -> Result<(), AppError> {
        if username.trim().is_empty() {
            return Ok(());
        }

        self.ensure_row_exists(username).await?;

        let previous_failed_attempts: i64 = sqlx::query_scalar(
            "SELECT failed_attempts FROM auth_policy WHERE username = ?1",
        )
        .bind(username)
        .fetch_one(&self.pool)
        .await
        .map_err(|error| Self::map_storage_err("read failed attempts before reset", error))?;

        sqlx::query(
            "UPDATE auth_policy
             SET failed_attempts = 0,
                 last_attempt_at = NULL
             WHERE username = ?1",
        )
        .bind(username)
        .execute(&self.pool)
        .await
        .map_err(|error| Self::map_storage_err("reset failed auth attempts", error))?;

        info!(
            username = %username,
            previous_failed_attempts,
            "login success: failed attempts counter reset"
        );

        Ok(())
    }

    async fn get_auto_lock_delay(&self, username: &str) -> Result<i64, AppError> {
        if username.trim().is_empty() {
            return Ok(DEFAULT_AUTO_LOCK_DELAY_MINS);
        }

        self.ensure_row_exists(username).await?;

        let delay_opt: Option<i64> = sqlx::query_scalar(
            "SELECT auto_lock_delay_mins FROM auth_policy WHERE username = ?1",
        )
        .bind(username)
        .fetch_optional(&self.pool)
        .await
        .map_err(|error| Self::map_storage_err("get auto_lock_delay_mins", error))?;

        let delay = delay_opt.unwrap_or(DEFAULT_AUTO_LOCK_DELAY_MINS);
        if Self::is_allowed_auto_lock_delay(delay) {
            Ok(delay)
        } else {
            Ok(DEFAULT_AUTO_LOCK_DELAY_MINS)
        }
    }

    async fn update_auto_lock_delay(&self, username: &str, mins: i64) -> Result<(), AppError> {
        if username.trim().is_empty() {
            return Err(AppError::Validation(
                "username must not be empty for auto-lock settings".to_string(),
            ));
        }
        if !Self::is_allowed_auto_lock_delay(mins) {
            return Err(AppError::Validation(
                "auto-lock delay must be one of: 1, 5, 10, 30".to_string(),
            ));
        }

        self.ensure_row_exists(username).await?;

        sqlx::query(
            "UPDATE auth_policy
             SET auto_lock_delay_mins = ?2
             WHERE username = ?1",
        )
        .bind(username)
        .bind(mins)
        .execute(&self.pool)
        .await
        .map_err(|error| Self::map_storage_err("update auto_lock_delay_mins", error))?;

        info!(username = %username, auto_lock_delay_mins = mins, "auto-lock delay updated");
        Ok(())
    }
}
