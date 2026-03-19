use crate::errors::AppError;
use crate::models::Vault;
use secrecy::ExposeSecret;
use secrecy::SecretBox;
use sqlx::{Row, SqlitePool};
use uuid::Uuid;

#[allow(async_fn_in_trait)]
pub trait VaultRepository {
    async fn get_by_id(&self, vault_id: Uuid) -> Result<Option<Vault>, AppError>;
    async fn list_by_user_id(&self, user_id: Uuid) -> Result<Vec<Vault>, AppError>;
    async fn create_vault(&self, vault: &Vault) -> Result<(), AppError>;
    async fn update_vault_key_envelope(
        &self,
        vault_id: Uuid,
        encrypted_vault_key_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
}

pub struct SqlxVaultRepository {
    pool: SqlitePool,
}

impl SqlxVaultRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    fn map_storage_err(context: &str, error: impl ToString) -> AppError {
        AppError::Storage(format!("{context}: {}", error.to_string()))
    }
}

impl VaultRepository for SqlxVaultRepository {
    async fn get_by_id(&self, vault_id: Uuid) -> Result<Option<Vault>, AppError> {
        let row_opt = sqlx::query("SELECT id, owner_user_id, name FROM vaults WHERE id = ?1")
            .bind(vault_id.to_string())
            .fetch_optional(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("get vault by id", err))?;

        match row_opt {
            Some(row) => {
                let id_str: String = row
                    .try_get("id")
                    .map_err(|err| Self::map_storage_err("read vault id", err))?;
                let owner_user_id_str: String = row
                    .try_get("owner_user_id")
                    .map_err(|err| Self::map_storage_err("read owner_user_id", err))?;
                let name: String = row
                    .try_get("name")
                    .map_err(|err| Self::map_storage_err("read vault name", err))?;

                let parsed_id = Uuid::parse_str(&id_str)
                    .map_err(|err| Self::map_storage_err("parse vault id", err))?;
                let parsed_owner_user_id = Uuid::parse_str(&owner_user_id_str)
                    .map_err(|err| Self::map_storage_err("parse owner_user_id", err))?;

                Ok(Some(Vault {
                    id: parsed_id,
                    owner_user_id: parsed_owner_user_id,
                    name,
                }))
            }
            None => Ok(None),
        }
    }

    async fn list_by_user_id(&self, user_id: Uuid) -> Result<Vec<Vault>, AppError> {
        let rows = sqlx::query(
            "SELECT id, owner_user_id, name FROM vaults WHERE owner_user_id = ?1 ORDER BY name",
        )
        .bind(user_id.to_string())
        .fetch_all(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("list vaults by user", err))?;

        let mut vaults = Vec::with_capacity(rows.len());
        for row in rows {
            let id_str: String = row
                .try_get("id")
                .map_err(|err| Self::map_storage_err("read vault id", err))?;
            let owner_user_id_str: String = row
                .try_get("owner_user_id")
                .map_err(|err| Self::map_storage_err("read owner_user_id", err))?;
            let name: String = row
                .try_get("name")
                .map_err(|err| Self::map_storage_err("read vault name", err))?;

            let parsed_id = Uuid::parse_str(&id_str)
                .map_err(|err| Self::map_storage_err("parse vault id", err))?;
            let parsed_owner_user_id = Uuid::parse_str(&owner_user_id_str)
                .map_err(|err| Self::map_storage_err("parse owner_user_id", err))?;

            vaults.push(Vault {
                id: parsed_id,
                owner_user_id: parsed_owner_user_id,
                name,
            });
        }

        Ok(vaults)
    }

    async fn create_vault(&self, vault: &Vault) -> Result<(), AppError> {
        sqlx::query("INSERT INTO vaults (id, owner_user_id, name) VALUES (?1, ?2, ?3)")
            .bind(vault.id.to_string())
            .bind(vault.owner_user_id.to_string())
            .bind(&vault.name)
            .execute(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("create vault", err))?;

        Ok(())
    }

    async fn update_vault_key_envelope(
        &self,
        vault_id: Uuid,
        encrypted_vault_key_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError> {
        let result = sqlx::query("UPDATE vaults SET vault_key_envelope = ?1 WHERE id = ?2")
            .bind(encrypted_vault_key_envelope.expose_secret().as_slice())
            .bind(vault_id.to_string())
            .execute(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("update vault key envelope", err))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage(
                "vault not found for key update".to_string(),
            ));
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{SqlxVaultRepository, VaultRepository};
    use crate::errors::AppError;
    use crate::models::Vault;
    use secrecy::SecretBox;
    use sqlx::sqlite::SqlitePoolOptions;
    use sqlx::Row;
    use uuid::Uuid;

    async fn setup_repo() -> Result<SqlxVaultRepository, String> {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .map_err(|err| format!("connect in-memory sqlite: {err}"))?;

        sqlx::query(
            "CREATE TABLE vaults (
                id TEXT PRIMARY KEY NOT NULL,
                owner_user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                vault_key_envelope BLOB
            )",
        )
        .execute(&pool)
        .await
        .map_err(|err| format!("create vaults table: {err}"))?;

        Ok(SqlxVaultRepository::new(pool))
    }

    async fn seed_vault(
        repo: &SqlxVaultRepository,
        vault_id: Uuid,
        owner_user_id: Uuid,
        name: &str,
    ) -> Result<(), String> {
        sqlx::query("INSERT INTO vaults (id, owner_user_id, name) VALUES (?1, ?2, ?3)")
            .bind(vault_id.to_string())
            .bind(owner_user_id.to_string())
            .bind(name)
            .execute(&repo.pool)
            .await
            .map_err(|err| format!("seed vault: {err}"))?;
        Ok(())
    }

    #[tokio::test]
    async fn create_and_get_vault_by_id() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let vault = Vault {
            id: Uuid::new_v4(),
            owner_user_id: Uuid::new_v4(),
            name: "Primary".to_string(),
        };

        let create_result = repo.create_vault(&vault).await;
        assert!(create_result.is_ok(), "create_vault should succeed");
        if create_result.is_err() {
            return;
        }

        let found_result = repo.get_by_id(vault.id).await;
        assert!(found_result.is_ok(), "get_by_id should succeed");
        let found_opt = match found_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(found_opt.is_some(), "vault should be found");
        let found = match found_opt {
            Some(value) => value,
            None => return,
        };

        assert_eq!(found.id, vault.id);
        assert_eq!(found.owner_user_id, vault.owner_user_id);
        assert_eq!(found.name, vault.name);
    }

    #[tokio::test]
    async fn list_vaults_by_user_id() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let owner_a = Uuid::new_v4();
        let owner_b = Uuid::new_v4();

        let seed_a1 = seed_vault(&repo, Uuid::new_v4(), owner_a, "Alpha").await;
        let seed_a2 = seed_vault(&repo, Uuid::new_v4(), owner_a, "Beta").await;
        let seed_b1 = seed_vault(&repo, Uuid::new_v4(), owner_b, "Gamma").await;

        assert!(seed_a1.is_ok(), "seed a1 should succeed");
        assert!(seed_a2.is_ok(), "seed a2 should succeed");
        assert!(seed_b1.is_ok(), "seed b1 should succeed");
        if seed_a1.is_err() || seed_a2.is_err() || seed_b1.is_err() {
            return;
        }

        let list_result = repo.list_by_user_id(owner_a).await;
        assert!(list_result.is_ok(), "list_by_user_id should succeed");
        let vaults = match list_result {
            Ok(value) => value,
            Err(_) => return,
        };

        assert_eq!(vaults.len(), 2);
        assert_eq!(vaults[0].name, "Alpha");
        assert_eq!(vaults[1].name, "Beta");
        assert!(vaults.iter().all(|vault| vault.owner_user_id == owner_a));
    }

    #[tokio::test]
    async fn update_vault_key_envelope_persists_blob() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let vault_id = Uuid::new_v4();
        let owner_id = Uuid::new_v4();
        let seed_result = seed_vault(&repo, vault_id, owner_id, "Secure Vault").await;
        assert!(seed_result.is_ok(), "seed vault should succeed");
        if seed_result.is_err() {
            return;
        }

        let update_result = repo
            .update_vault_key_envelope(vault_id, SecretBox::new(Box::new(vec![3_u8, 1_u8, 4_u8])))
            .await;
        assert!(update_result.is_ok(), "update should succeed");
        if update_result.is_err() {
            return;
        }

        let row_result = sqlx::query("SELECT vault_key_envelope FROM vaults WHERE id = ?1")
            .bind(vault_id.to_string())
            .fetch_one(&repo.pool)
            .await;
        assert!(row_result.is_ok(), "readback should succeed");
        let row = match row_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let blob_result: Result<Vec<u8>, _> = row.try_get("vault_key_envelope");
        assert!(blob_result.is_ok(), "blob should be readable");
        let blob = match blob_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(blob, vec![3_u8, 1_u8, 4_u8]);
    }

    #[tokio::test]
    async fn update_missing_vault_returns_storage_error() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let update_result = repo
            .update_vault_key_envelope(
                Uuid::new_v4(),
                SecretBox::new(Box::new(vec![8_u8, 8_u8, 8_u8])),
            )
            .await;

        assert!(update_result.is_err(), "missing vault update should fail");
        if let Err(err) = update_result {
            assert!(matches!(err, AppError::Storage(_)));
        }
    }
}
