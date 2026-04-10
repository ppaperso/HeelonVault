#![allow(clippy::disallowed_methods)]

use std::path::Path;
use std::sync::Arc;

use secrecy::{ExposeSecret, SecretBox};
use serde_json::json;
use tracing::info;
use uuid::Uuid;

use crate::errors::AppError;
use crate::models::SecretType;
use crate::services::secret_service::SecretService;
use crate::services::vault_service::VaultService;

#[trait_variant::make(ImportService: Send)]
pub trait LocalImportService {
    async fn import_csv<TSecret, TVault>(
        &self,
        csv_file_path: &Path,
        admin_user_id: Uuid,
        admin_master_key: SecretBox<Vec<u8>>,
        secret_service: Arc<TSecret>,
        vault_service: Arc<TVault>,
    ) -> Result<usize, AppError>
    where
        TSecret: SecretService + Send + Sync + 'static,
        TVault: VaultService + Send + Sync + 'static;
}

pub struct ImportServiceImpl;

impl ImportServiceImpl {
    pub fn new() -> Self {
        Self
    }

    fn parse_csv_rows(csv_file_path: &Path) -> Result<Vec<CsvRow>, AppError> {
        let mut reader = csv::ReaderBuilder::new()
            .has_headers(true)
            .from_path(csv_file_path)
            .map_err(|error| AppError::Storage(format!("failed to open csv file: {error}")))?;

        let headers = reader
            .headers()
            .map_err(|error| AppError::Validation(format!("failed to read csv headers: {error}")))?
            .clone();

        let required = ["name", "url", "username", "password", "notes"];
        for field in required {
            if !headers.iter().any(|h| h.eq_ignore_ascii_case(field)) {
                return Err(AppError::Validation(format!(
                    "csv is missing required column: {field}"
                )));
            }
        }

        let idx = |name: &str| -> Result<usize, AppError> {
            headers
                .iter()
                .position(|h| h.eq_ignore_ascii_case(name))
                .ok_or_else(|| {
                    AppError::Validation(format!("csv is missing required column: {name}"))
                })
        };

        let name_idx = idx("name")?;
        let url_idx = idx("url")?;
        let username_idx = idx("username")?;
        let password_idx = idx("password")?;
        let notes_idx = idx("notes")?;

        let mut rows = Vec::new();
        for record in reader.records() {
            let record = record
                .map_err(|error| AppError::Validation(format!("invalid csv record: {error}")))?;

            let name = record.get(name_idx).unwrap_or_default().trim().to_string();
            let url = record.get(url_idx).unwrap_or_default().trim().to_string();
            let username = record
                .get(username_idx)
                .unwrap_or_default()
                .trim()
                .to_string();
            let password = record
                .get(password_idx)
                .unwrap_or_default()
                .trim()
                .to_string();
            let notes = record.get(notes_idx).unwrap_or_default().trim().to_string();

            if password.is_empty() {
                continue;
            }

            rows.push(CsvRow {
                name,
                url,
                username,
                password,
                notes,
            });
        }

        Ok(rows)
    }
}

impl Default for ImportServiceImpl {
    fn default() -> Self {
        Self::new()
    }
}

impl ImportService for ImportServiceImpl {
    async fn import_csv<TSecret, TVault>(
        &self,
        csv_file_path: &Path,
        admin_user_id: Uuid,
        admin_master_key: SecretBox<Vec<u8>>,
        secret_service: Arc<TSecret>,
        vault_service: Arc<TVault>,
    ) -> Result<usize, AppError>
    where
        TSecret: SecretService + Send + Sync + 'static,
        TVault: VaultService + Send + Sync + 'static,
    {
        let rows = Self::parse_csv_rows(csv_file_path)?;
        if rows.is_empty() {
            return Ok(0);
        }

        let vaults = vault_service.list_user_vaults(admin_user_id).await?;
        let first_vault = vaults
            .into_iter()
            .next()
            .ok_or_else(|| AppError::NotFound("no vault found for csv import".to_string()))?;

        let vault_key = vault_service
            .open_vault(
                first_vault.id,
                SecretBox::new(Box::new(admin_master_key.expose_secret().clone())),
            )
            .await?;

        let mut imported_count = 0usize;
        for row in rows {
            let metadata = json!({
                "login": row.username,
                "url": row.url,
                "notes": row.notes,
                "source": "csv_import"
            })
            .to_string();

            let title = if row.name.is_empty() {
                Some("Imported secret".to_string())
            } else {
                Some(row.name)
            };

            secret_service
                .create_secret(
                    first_vault.id,
                    SecretType::Password,
                    title,
                    Some(metadata),
                    Some("import,csv".to_string()),
                    None,
                    SecretBox::new(Box::new(row.password.into_bytes())),
                    SecretBox::new(Box::new(vault_key.expose_secret().clone())),
                )
                .await?;
            imported_count += 1;
        }

        info!(
            imported_count,
            vault_id = %first_vault.id,
            "csv import completed successfully"
        );
        Ok(imported_count)
    }
}

struct CsvRow {
    name: String,
    url: String,
    username: String,
    password: String,
    notes: String,
}
