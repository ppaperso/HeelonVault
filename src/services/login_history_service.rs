use sqlx::{Row, SqlitePool};
use uuid::Uuid;

use crate::errors::AppError;

#[derive(Debug, Clone)]
pub struct LoginHistoryEntry {
    pub login_at: String,
    pub ip_address: Option<String>,
    pub device_info: Option<String>,
}

fn map_storage_err(context: &str, error: impl ToString) -> AppError {
    AppError::Storage(format!("{context}: {}", error.to_string()))
}

pub async fn record_successful_login(
    pool: &SqlitePool,
    user_id: Uuid,
    ip_address: Option<&str>,
    device_info: Option<&str>,
) -> Result<(), AppError> {
    sqlx::query(
        "INSERT INTO login_history (user_id, login_at, ip_address, device_info)
         VALUES (?1, datetime('now'), ?2, ?3)",
    )
    .bind(user_id.to_string())
    .bind(ip_address)
    .bind(device_info)
    .execute(pool)
    .await
    .map_err(|err| map_storage_err("insert login history", err))?;

    Ok(())
}

pub async fn list_recent_logins(
    pool: &SqlitePool,
    user_id: Uuid,
    limit: i64,
) -> Result<Vec<LoginHistoryEntry>, AppError> {
    let safe_limit = limit.clamp(1, 50);

    let rows = sqlx::query(
        "SELECT login_at, ip_address, device_info
         FROM login_history
         WHERE user_id = ?1
         ORDER BY login_at DESC
         LIMIT ?2",
    )
    .bind(user_id.to_string())
    .bind(safe_limit)
    .fetch_all(pool)
    .await
    .map_err(|err| map_storage_err("list login history", err))?;

    let mut entries = Vec::with_capacity(rows.len());
    for row in rows {
        let login_at: String = row
            .try_get("login_at")
            .map_err(|err| map_storage_err("read login_at", err))?;
        let ip_address: Option<String> = row
            .try_get("ip_address")
            .map_err(|err| map_storage_err("read ip_address", err))?;
        let device_info: Option<String> = row
            .try_get("device_info")
            .map_err(|err| map_storage_err("read device_info", err))?;

        entries.push(LoginHistoryEntry {
            login_at,
            ip_address,
            device_info,
        });
    }

    Ok(entries)
}
