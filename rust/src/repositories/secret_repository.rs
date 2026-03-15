use crate::errors::AppError;
use crate::models::{BlobStorage, SecretItem, SecretType};
use secrecy::ExposeSecret;
use secrecy::SecretBox;
use sqlx::{Row, SqlitePool};
use uuid::Uuid;

#[allow(async_fn_in_trait)]
pub trait SecretRepository {
    async fn get_by_id(&self, secret_id: Uuid) -> Result<Option<SecretItem>, AppError>;
    async fn list_by_vault_id(&self, vault_id: Uuid) -> Result<Vec<SecretItem>, AppError>;
    async fn insert_secret_blob(
        &self,
        item: &SecretItem,
        encrypted_secret_blob: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
    async fn update_secret_blob(
        &self,
        secret_id: Uuid,
        encrypted_secret_blob: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
    async fn soft_delete(&self, secret_id: Uuid) -> Result<(), AppError>;
}

pub struct SqlxSecretRepository {
    pool: SqlitePool,
}

impl SqlxSecretRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    fn map_storage_err(context: &str, error: impl ToString) -> AppError {
        AppError::Storage(format!("{context}: {}", error.to_string()))
    }

    fn to_secret_type_db(secret_type: SecretType) -> &'static str {
        match secret_type {
            SecretType::Password => "password",
            SecretType::ApiToken => "api_token",
            SecretType::SshKey => "ssh_key",
            SecretType::SecureDocument => "secure_document",
        }
    }

    fn parse_secret_type_db(raw: &str) -> Result<SecretType, AppError> {
        match raw {
            "password" => Ok(SecretType::Password),
            "api_token" => Ok(SecretType::ApiToken),
            "ssh_key" => Ok(SecretType::SshKey),
            "secure_document" => Ok(SecretType::SecureDocument),
            _ => Err(AppError::Storage("invalid secret_type in storage".to_string())),
        }
    }

    fn to_blob_storage_db(blob_storage: BlobStorage) -> &'static str {
        match blob_storage {
            BlobStorage::Inline => "inline",
            BlobStorage::File => "file",
        }
    }

    fn parse_blob_storage_db(raw: &str) -> Result<BlobStorage, AppError> {
        match raw {
            "inline" => Ok(BlobStorage::Inline),
            "file" => Ok(BlobStorage::File),
            _ => Err(AppError::Storage("invalid blob_storage in storage".to_string())),
        }
    }

    fn row_to_secret_item(row: &sqlx::sqlite::SqliteRow) -> Result<SecretItem, AppError> {
        let id_raw: String = row
            .try_get("id")
            .map_err(|err| Self::map_storage_err("read secret id", err))?;
        let vault_id_raw: String = row
            .try_get("vault_id")
            .map_err(|err| Self::map_storage_err("read vault_id", err))?;
        let secret_type_raw: String = row
            .try_get("secret_type")
            .map_err(|err| Self::map_storage_err("read secret_type", err))?;
        let blob_storage_raw: String = row
            .try_get("blob_storage")
            .map_err(|err| Self::map_storage_err("read blob_storage", err))?;

        let id = Uuid::parse_str(&id_raw).map_err(|err| Self::map_storage_err("parse id", err))?;
        let vault_id = Uuid::parse_str(&vault_id_raw)
            .map_err(|err| Self::map_storage_err("parse vault_id", err))?;
        let secret_type = Self::parse_secret_type_db(&secret_type_raw)?;
        let blob_storage = Self::parse_blob_storage_db(&blob_storage_raw)?;

        let secret_blob_bytes = match blob_storage {
            BlobStorage::Inline => {
                let raw: Option<Vec<u8>> = row
                    .try_get("secret_blob")
                    .map_err(|err| Self::map_storage_err("read inline secret_blob", err))?;
                raw.ok_or_else(|| {
                    AppError::Storage("missing inline secret_blob in storage".to_string())
                })?
            }
            BlobStorage::File => {
                let raw: Option<Vec<u8>> = row
                    .try_get("file_blob_ref")
                    .map_err(|err| Self::map_storage_err("read file blob reference", err))?;
                raw.ok_or_else(|| {
                    AppError::Storage("missing file blob reference in storage".to_string())
                })?
            }
        };

        Ok(SecretItem {
            id,
            vault_id,
            secret_type,
            blob_storage,
            secret_blob: SecretBox::new(Box::new(secret_blob_bytes)),
        })
    }
}

impl SecretRepository for SqlxSecretRepository {
    async fn get_by_id(&self, secret_id: Uuid) -> Result<Option<SecretItem>, AppError> {
        let row_opt = sqlx::query(
            "SELECT id, vault_id, secret_type, blob_storage, secret_blob, file_blob_ref
             FROM secret_items
             WHERE id = ?1 AND deleted_at IS NULL",
        )
        .bind(secret_id.to_string())
        .fetch_optional(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("get secret by id", err))?;

        match row_opt {
            Some(row) => Ok(Some(Self::row_to_secret_item(&row)?)),
            None => Ok(None),
        }
    }

    async fn list_by_vault_id(&self, vault_id: Uuid) -> Result<Vec<SecretItem>, AppError> {
        let rows = sqlx::query(
            "SELECT id, vault_id, secret_type, blob_storage, secret_blob, file_blob_ref
             FROM secret_items
             WHERE vault_id = ?1 AND deleted_at IS NULL
             ORDER BY id",
        )
        .bind(vault_id.to_string())
        .fetch_all(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("list secrets by vault", err))?;

        let mut items = Vec::with_capacity(rows.len());
        for row in rows {
            items.push(Self::row_to_secret_item(&row)?);
        }

        Ok(items)
    }

    async fn insert_secret_blob(
        &self,
        item: &SecretItem,
        encrypted_secret_blob: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError> {
        let secret_blob = if matches!(item.blob_storage, BlobStorage::Inline) {
            Some(encrypted_secret_blob.expose_secret().as_slice())
        } else {
            None
        };
        let file_blob_ref = if matches!(item.blob_storage, BlobStorage::File) {
            Some(encrypted_secret_blob.expose_secret().as_slice())
        } else {
            None
        };

        sqlx::query(
            "INSERT INTO secret_items (
                id, vault_id, secret_type, blob_storage, secret_blob, file_blob_ref, deleted_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL)",
        )
        .bind(item.id.to_string())
        .bind(item.vault_id.to_string())
        .bind(Self::to_secret_type_db(item.secret_type))
        .bind(Self::to_blob_storage_db(item.blob_storage))
        .bind(secret_blob)
        .bind(file_blob_ref)
        .execute(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("insert secret item", err))?;

        Ok(())
    }

    async fn update_secret_blob(
        &self,
        secret_id: Uuid,
        encrypted_secret_blob: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError> {
        let row_opt = sqlx::query(
            "SELECT blob_storage
             FROM secret_items
             WHERE id = ?1 AND deleted_at IS NULL",
        )
        .bind(secret_id.to_string())
        .fetch_optional(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("load blob strategy for update", err))?;

        let row = row_opt
            .ok_or_else(|| AppError::Storage("secret not found for blob update".to_string()))?;
        let blob_storage_raw: String = row
            .try_get("blob_storage")
            .map_err(|err| Self::map_storage_err("read blob strategy", err))?;
        let blob_storage = Self::parse_blob_storage_db(&blob_storage_raw)?;

        let result = match blob_storage {
            BlobStorage::Inline => {
                sqlx::query(
                    "UPDATE secret_items
                     SET secret_blob = ?1, file_blob_ref = NULL
                     WHERE id = ?2 AND deleted_at IS NULL",
                )
                .bind(encrypted_secret_blob.expose_secret().as_slice())
                .bind(secret_id.to_string())
                .execute(&self.pool)
                .await
            }
            BlobStorage::File => {
                sqlx::query(
                    "UPDATE secret_items
                     SET file_blob_ref = ?1, secret_blob = NULL
                     WHERE id = ?2 AND deleted_at IS NULL",
                )
                .bind(encrypted_secret_blob.expose_secret().as_slice())
                .bind(secret_id.to_string())
                .execute(&self.pool)
                .await
            }
        }
        .map_err(|err| Self::map_storage_err("update secret blob", err))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage(
                "secret not found for blob update".to_string(),
            ));
        }

        Ok(())
    }

    async fn soft_delete(&self, secret_id: Uuid) -> Result<(), AppError> {
        let result = sqlx::query(
            "UPDATE secret_items
             SET deleted_at = CURRENT_TIMESTAMP
             WHERE id = ?1 AND deleted_at IS NULL",
        )
        .bind(secret_id.to_string())
        .execute(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("soft delete secret", err))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage("secret not found for delete".to_string()));
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{SecretRepository, SqlxSecretRepository};
    use crate::errors::AppError;
    use crate::models::{BlobStorage, SecretItem, SecretType};
    use secrecy::{ExposeSecret, SecretBox};
    use sqlx::sqlite::SqlitePoolOptions;
    use sqlx::Row;
    use uuid::Uuid;

    async fn setup_repo() -> Result<SqlxSecretRepository, String> {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .map_err(|err| format!("connect in-memory sqlite: {err}"))?;

        sqlx::query(
            "CREATE TABLE secret_items (
                id TEXT PRIMARY KEY NOT NULL,
                vault_id TEXT NOT NULL,
                secret_type TEXT NOT NULL,
                blob_storage TEXT NOT NULL,
                secret_blob BLOB,
                file_blob_ref BLOB,
                deleted_at TEXT
            )",
        )
        .execute(&pool)
        .await
        .map_err(|err| format!("create secret_items table: {err}"))?;

        Ok(SqlxSecretRepository::new(pool))
    }

    fn build_item(vault_id: Uuid, storage: BlobStorage) -> SecretItem {
        SecretItem {
            id: Uuid::new_v4(),
            vault_id,
            secret_type: SecretType::ApiToken,
            blob_storage: storage,
            secret_blob: SecretBox::new(Box::new(Vec::new())),
        }
    }

    #[tokio::test]
    async fn inline_strategy_roundtrip() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let vault_id = Uuid::new_v4();
        let item = build_item(vault_id, BlobStorage::Inline);
        let payload = SecretBox::new(Box::new(vec![1_u8, 2_u8, 3_u8]));

        let insert_result = repo.insert_secret_blob(&item, payload).await;
        assert!(insert_result.is_ok(), "insert should succeed");
        if insert_result.is_err() {
            return;
        }

        let found_result = repo.get_by_id(item.id).await;
        assert!(found_result.is_ok(), "get should succeed");
        let found_opt = match found_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(found_opt.is_some(), "secret should exist");
        let found = match found_opt {
            Some(value) => value,
            None => return,
        };

        assert!(matches!(found.blob_storage, BlobStorage::Inline));
        assert_eq!(found.secret_blob.expose_secret().as_slice(), &[1_u8, 2_u8, 3_u8]);
    }

    #[tokio::test]
    async fn file_strategy_roundtrip() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let vault_id = Uuid::new_v4();
        let item = build_item(vault_id, BlobStorage::File);
        let file_ref = SecretBox::new(Box::new(b"vault-a/item-1.bin".to_vec()));

        let insert_result = repo.insert_secret_blob(&item, file_ref).await;
        assert!(insert_result.is_ok(), "insert should succeed");
        if insert_result.is_err() {
            return;
        }

        let found_result = repo.get_by_id(item.id).await;
        assert!(found_result.is_ok(), "get should succeed");
        let found_opt = match found_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(found_opt.is_some(), "secret should exist");
        let found = match found_opt {
            Some(value) => value,
            None => return,
        };

        assert!(matches!(found.blob_storage, BlobStorage::File));
        assert_eq!(
            found.secret_blob.expose_secret().as_slice(),
            b"vault-a/item-1.bin"
        );
    }

    #[tokio::test]
    async fn list_by_vault_returns_both_strategies() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let vault_id = Uuid::new_v4();
        let inline_item = build_item(vault_id, BlobStorage::Inline);
        let file_item = build_item(vault_id, BlobStorage::File);

        let ins_a = repo
            .insert_secret_blob(&inline_item, SecretBox::new(Box::new(vec![7_u8, 7_u8])))
            .await;
        let ins_b = repo
            .insert_secret_blob(
                &file_item,
                SecretBox::new(Box::new(b"vault-a/item-2.bin".to_vec())),
            )
            .await;

        assert!(ins_a.is_ok(), "inline insert should succeed");
        assert!(ins_b.is_ok(), "file insert should succeed");
        if ins_a.is_err() || ins_b.is_err() {
            return;
        }

        let list_result = repo.list_by_vault_id(vault_id).await;
        assert!(list_result.is_ok(), "list should succeed");
        let items = match list_result {
            Ok(value) => value,
            Err(_) => return,
        };

        assert_eq!(items.len(), 2);
        let has_inline = items
            .iter()
            .any(|item| matches!(item.blob_storage, BlobStorage::Inline));
        let has_file = items
            .iter()
            .any(|item| matches!(item.blob_storage, BlobStorage::File));
        assert!(has_inline);
        assert!(has_file);
    }

    #[tokio::test]
    async fn update_blob_respects_storage_strategy() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let vault_id = Uuid::new_v4();
        let inline_item = build_item(vault_id, BlobStorage::Inline);
        let file_item = build_item(vault_id, BlobStorage::File);

        let ins_a = repo
            .insert_secret_blob(&inline_item, SecretBox::new(Box::new(vec![1_u8])))
            .await;
        let ins_b = repo
            .insert_secret_blob(&file_item, SecretBox::new(Box::new(b"old.bin".to_vec())))
            .await;
        assert!(ins_a.is_ok(), "inline seed should succeed");
        assert!(ins_b.is_ok(), "file seed should succeed");
        if ins_a.is_err() || ins_b.is_err() {
            return;
        }

        let up_a = repo
            .update_secret_blob(inline_item.id, SecretBox::new(Box::new(vec![9_u8, 9_u8])))
            .await;
        let up_b = repo
            .update_secret_blob(file_item.id, SecretBox::new(Box::new(b"new.bin".to_vec())))
            .await;
        assert!(up_a.is_ok(), "inline update should succeed");
        assert!(up_b.is_ok(), "file update should succeed");
        if up_a.is_err() || up_b.is_err() {
            return;
        }

        let inline_row_result = sqlx::query(
            "SELECT secret_blob, file_blob_ref FROM secret_items WHERE id = ?1",
        )
        .bind(inline_item.id.to_string())
        .fetch_one(&repo.pool)
        .await;
        assert!(inline_row_result.is_ok(), "inline readback should succeed");
        let inline_row = match inline_row_result {
            Ok(value) => value,
            Err(_) => return,
        };
        let inline_blob_result: Result<Option<Vec<u8>>, _> = inline_row.try_get("secret_blob");
        let inline_ref_result: Result<Option<Vec<u8>>, _> = inline_row.try_get("file_blob_ref");
        assert!(inline_blob_result.is_ok());
        assert!(inline_ref_result.is_ok());
        let inline_blob = match inline_blob_result {
            Ok(value) => value,
            Err(_) => return,
        };
        let inline_ref = match inline_ref_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(inline_blob, Some(vec![9_u8, 9_u8]));
        assert!(inline_ref.is_none());

        let file_row_result = sqlx::query(
            "SELECT secret_blob, file_blob_ref FROM secret_items WHERE id = ?1",
        )
        .bind(file_item.id.to_string())
        .fetch_one(&repo.pool)
        .await;
        assert!(file_row_result.is_ok(), "file readback should succeed");
        let file_row = match file_row_result {
            Ok(value) => value,
            Err(_) => return,
        };
        let file_blob_result: Result<Option<Vec<u8>>, _> = file_row.try_get("secret_blob");
        let file_ref_result: Result<Option<Vec<u8>>, _> = file_row.try_get("file_blob_ref");
        assert!(file_blob_result.is_ok());
        assert!(file_ref_result.is_ok());
        let file_blob = match file_blob_result {
            Ok(value) => value,
            Err(_) => return,
        };
        let file_ref = match file_ref_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(file_blob.is_none());
        assert_eq!(file_ref, Some(b"new.bin".to_vec()));
    }

    #[tokio::test]
    async fn soft_delete_hides_items() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let vault_id = Uuid::new_v4();
        let item = build_item(vault_id, BlobStorage::Inline);
        let insert_result = repo
            .insert_secret_blob(&item, SecretBox::new(Box::new(vec![5_u8, 5_u8, 5_u8])))
            .await;
        assert!(insert_result.is_ok(), "insert should succeed");
        if insert_result.is_err() {
            return;
        }

        let delete_result = repo.soft_delete(item.id).await;
        assert!(delete_result.is_ok(), "delete should succeed");
        if delete_result.is_err() {
            return;
        }

        let by_id_result = repo.get_by_id(item.id).await;
        assert!(by_id_result.is_ok(), "get_by_id should succeed");
        let by_id = match by_id_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(by_id.is_none());

        let list_result = repo.list_by_vault_id(vault_id).await;
        assert!(list_result.is_ok(), "list should succeed");
        let list = match list_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(list.is_empty());
    }

    #[tokio::test]
    async fn missing_item_operations_return_storage_error() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let missing_id = Uuid::new_v4();
        let update_result = repo
            .update_secret_blob(missing_id, SecretBox::new(Box::new(vec![1_u8])))
            .await;
        assert!(update_result.is_err(), "update should fail for missing item");
        if let Err(err) = update_result {
            assert!(matches!(err, AppError::Storage(_)));
        }

        let delete_result = repo.soft_delete(missing_id).await;
        assert!(delete_result.is_err(), "delete should fail for missing item");
        if let Err(err) = delete_result {
            assert!(matches!(err, AppError::Storage(_)));
        }
    }
}
