use crate::errors::AppError;
use crate::models::{User, UserRole};
use secrecy::ExposeSecret;
use secrecy::SecretBox;
use sqlx::{Row, SqlitePool};
use uuid::Uuid;

#[allow(async_fn_in_trait)]
pub trait UserRepository {
    async fn get_by_id(&self, user_id: Uuid) -> Result<Option<User>, AppError>;
    async fn get_by_username(&self, username: &str) -> Result<Option<User>, AppError>;
    async fn update_user_profile(
        &self,
        user_id: Uuid,
        email: Option<&str>,
        display_name: Option<&str>,
    ) -> Result<(), AppError>;
    async fn update_password_envelope(
        &self,
        user_id: Uuid,
        encrypted_password_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
    async fn update_totp_secret_envelope(
        &self,
        user_id: Uuid,
        encrypted_totp_secret_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError>;
}

pub struct SqlxUserRepository {
    pool: SqlitePool,
}

impl SqlxUserRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    fn map_storage_err(context: &str, error: impl ToString) -> AppError {
        AppError::Storage(format!("{context}: {}", error.to_string()))
    }

    fn parse_role(role: &str) -> Result<UserRole, AppError> {
        match role {
            "user" => Ok(UserRole::User),
            "admin" => Ok(UserRole::Admin),
            _ => Err(AppError::Storage("invalid user role in storage".to_string())),
        }
    }
}

impl UserRepository for SqlxUserRepository {
    async fn get_by_id(&self, user_id: Uuid) -> Result<Option<User>, AppError> {
        let row_opt =
            sqlx::query("SELECT id, username, role, email, display_name, updated_at FROM users WHERE id = ?1")
            .bind(user_id.to_string())
            .fetch_optional(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("get user by id", err))?;

        match row_opt {
            Some(row) => {
                let id_str: String = row
                    .try_get("id")
                    .map_err(|err| Self::map_storage_err("read user id", err))?;
                let username: String = row
                    .try_get("username")
                    .map_err(|err| Self::map_storage_err("read username", err))?;
                let role_raw: String = row
                    .try_get("role")
                    .map_err(|err| Self::map_storage_err("read role", err))?;
                let email: Option<String> = row
                    .try_get("email")
                    .map_err(|err| Self::map_storage_err("read email", err))?;
                let display_name: Option<String> = row
                    .try_get("display_name")
                    .map_err(|err| Self::map_storage_err("read display_name", err))?;
                let updated_at: Option<String> = row
                    .try_get("updated_at")
                    .map_err(|err| Self::map_storage_err("read updated_at", err))?;

                let parsed_id = Uuid::parse_str(&id_str)
                    .map_err(|err| Self::map_storage_err("parse user id", err))?;
                let role = Self::parse_role(&role_raw)?;

                Ok(Some(User {
                    id: parsed_id,
                    username,
                    role,
                    email,
                    display_name,
                    updated_at,
                }))
            }
            None => Ok(None),
        }
    }

    async fn get_by_username(&self, username: &str) -> Result<Option<User>, AppError> {
        let row_opt = sqlx::query(
            "SELECT id, username, role, email, display_name, updated_at FROM users WHERE username = ?1",
        )
        .bind(username)
        .fetch_optional(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("get user by username", err))?;

        match row_opt {
            Some(row) => {
                let id_str: String = row
                    .try_get("id")
                    .map_err(|err| Self::map_storage_err("read user id", err))?;
                let stored_username: String = row
                    .try_get("username")
                    .map_err(|err| Self::map_storage_err("read username", err))?;
                let role_raw: String = row
                    .try_get("role")
                    .map_err(|err| Self::map_storage_err("read role", err))?;
                let email: Option<String> = row
                    .try_get("email")
                    .map_err(|err| Self::map_storage_err("read email", err))?;
                let display_name: Option<String> = row
                    .try_get("display_name")
                    .map_err(|err| Self::map_storage_err("read display_name", err))?;
                let updated_at: Option<String> = row
                    .try_get("updated_at")
                    .map_err(|err| Self::map_storage_err("read updated_at", err))?;

                let parsed_id = Uuid::parse_str(&id_str)
                    .map_err(|err| Self::map_storage_err("parse user id", err))?;
                let role = Self::parse_role(&role_raw)?;

                Ok(Some(User {
                    id: parsed_id,
                    username: stored_username,
                    role,
                    email,
                    display_name,
                    updated_at,
                }))
            }
            None => Ok(None),
        }
    }

    async fn update_user_profile(
        &self,
        user_id: Uuid,
        email: Option<&str>,
        display_name: Option<&str>,
    ) -> Result<(), AppError> {
        let result = sqlx::query(
            "UPDATE users
             SET email = ?1,
                 display_name = ?2,
                 updated_at = CURRENT_TIMESTAMP
             WHERE id = ?3",
        )
        .bind(email)
        .bind(display_name)
        .bind(user_id.to_string())
        .execute(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("update user profile", err))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage("user not found for profile update".to_string()));
        }

        Ok(())
    }

    async fn update_password_envelope(
        &self,
        user_id: Uuid,
        encrypted_password_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError> {
        let result = sqlx::query("UPDATE users SET password_envelope = ?1 WHERE id = ?2")
            .bind(encrypted_password_envelope.expose_secret().as_slice())
            .bind(user_id.to_string())
            .execute(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("update password envelope", err))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage("user not found for password update".to_string()));
        }

        Ok(())
    }

    async fn update_totp_secret_envelope(
        &self,
        user_id: Uuid,
        encrypted_totp_secret_envelope: SecretBox<Vec<u8>>,
    ) -> Result<(), AppError> {
        let result = sqlx::query("UPDATE users SET totp_secret_envelope = ?1 WHERE id = ?2")
            .bind(encrypted_totp_secret_envelope.expose_secret().as_slice())
            .bind(user_id.to_string())
            .execute(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("update totp secret envelope", err))?;

        if result.rows_affected() == 0 {
            return Err(AppError::Storage("user not found for totp update".to_string()));
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::{SqlxUserRepository, UserRepository};
    use crate::errors::AppError;
    use crate::models::UserRole;
    use secrecy::SecretBox;
    use sqlx::sqlite::SqlitePoolOptions;
    use sqlx::Row;
    use uuid::Uuid;

    async fn setup_repo() -> Result<SqlxUserRepository, String> {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .map_err(|err| format!("connect in-memory sqlite: {err}"))?;

        sqlx::query(
            "CREATE TABLE users (
                id TEXT PRIMARY KEY NOT NULL,
                username TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                email TEXT,
                display_name TEXT,
                updated_at TEXT,
                password_envelope BLOB,
                totp_secret_envelope BLOB
            )",
        )
        .execute(&pool)
        .await
        .map_err(|err| format!("create users table: {err}"))?;

        Ok(SqlxUserRepository::new(pool))
    }

    async fn insert_user(
        repo: &SqlxUserRepository,
        user_id: Uuid,
        username: &str,
        role: &str,
    ) -> Result<(), String> {
        sqlx::query("INSERT INTO users (id, username, role) VALUES (?1, ?2, ?3)")
            .bind(user_id.to_string())
            .bind(username)
            .bind(role)
            .execute(&repo.pool)
            .await
            .map_err(|err| format!("insert user: {err}"))?;
        Ok(())
    }

    #[tokio::test]
    async fn get_user_by_id_maps_model() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let user_id = Uuid::new_v4();
        let insert_result = insert_user(&repo, user_id, "alice", "admin").await;
        assert!(insert_result.is_ok(), "seed user should succeed");
        if insert_result.is_err() {
            return;
        }

        let found_result = repo.get_by_id(user_id).await;
        assert!(found_result.is_ok(), "query by id should succeed");
        let found = match found_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(found.is_some(), "user should be found");
        let user = match found {
            Some(value) => value,
            None => return,
        };

        assert_eq!(user.id, user_id);
        assert_eq!(user.username, "alice");
        assert!(matches!(user.role, UserRole::Admin));
    }

    #[tokio::test]
    async fn get_user_by_username_maps_model() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let user_id = Uuid::new_v4();
        let insert_result = insert_user(&repo, user_id, "bob", "user").await;
        assert!(insert_result.is_ok(), "seed user should succeed");
        if insert_result.is_err() {
            return;
        }

        let found_result = repo.get_by_username("bob").await;
        assert!(found_result.is_ok(), "query by username should succeed");
        let found = match found_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert!(found.is_some(), "user should be found");
        let user = match found {
            Some(value) => value,
            None => return,
        };

        assert_eq!(user.id, user_id);
        assert_eq!(user.username, "bob");
        assert!(matches!(user.role, UserRole::User));
    }

    #[tokio::test]
    async fn update_password_envelope_persists_blob() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let user_id = Uuid::new_v4();
        let insert_result = insert_user(&repo, user_id, "carol", "user").await;
        assert!(insert_result.is_ok(), "seed user should succeed");
        if insert_result.is_err() {
            return;
        }

        let envelope = SecretBox::new(Box::new(vec![1_u8, 2_u8, 3_u8, 4_u8]));
        let update_result = repo.update_password_envelope(user_id, envelope).await;
        assert!(update_result.is_ok(), "password update should succeed");
        if update_result.is_err() {
            return;
        }

        let row_result = sqlx::query("SELECT password_envelope FROM users WHERE id = ?1")
            .bind(user_id.to_string())
            .fetch_one(&repo.pool)
            .await;
        assert!(row_result.is_ok(), "readback query should succeed");
        let row = match row_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let stored_result: Result<Vec<u8>, _> = row.try_get("password_envelope");
        assert!(stored_result.is_ok(), "stored blob should be readable");
        let stored = match stored_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(stored, vec![1_u8, 2_u8, 3_u8, 4_u8]);
    }

    #[tokio::test]
    async fn update_totp_secret_envelope_persists_blob() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let user_id = Uuid::new_v4();
        let insert_result = insert_user(&repo, user_id, "dave", "admin").await;
        assert!(insert_result.is_ok(), "seed user should succeed");
        if insert_result.is_err() {
            return;
        }

        let envelope = SecretBox::new(Box::new(vec![9_u8, 8_u8, 7_u8]));
        let update_result = repo
            .update_totp_secret_envelope(user_id, envelope)
            .await;
        assert!(update_result.is_ok(), "totp update should succeed");
        if update_result.is_err() {
            return;
        }

        let row_result = sqlx::query("SELECT totp_secret_envelope FROM users WHERE id = ?1")
            .bind(user_id.to_string())
            .fetch_one(&repo.pool)
            .await;
        assert!(row_result.is_ok(), "readback query should succeed");
        let row = match row_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let stored_result: Result<Vec<u8>, _> = row.try_get("totp_secret_envelope");
        assert!(stored_result.is_ok(), "stored blob should be readable");
        let stored = match stored_result {
            Ok(value) => value,
            Err(_) => return,
        };
        assert_eq!(stored, vec![9_u8, 8_u8, 7_u8]);
    }

    #[tokio::test]
    async fn updates_missing_user_return_storage_error() {
        let repo_result = setup_repo().await;
        assert!(repo_result.is_ok(), "repo setup should succeed");
        let repo = match repo_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let missing_id = Uuid::new_v4();
        let password_result = repo
            .update_password_envelope(
                missing_id,
                SecretBox::new(Box::new(vec![1_u8, 2_u8, 3_u8])),
            )
            .await;
        assert!(password_result.is_err(), "missing user should error");

        let totp_result = repo
            .update_totp_secret_envelope(
                missing_id,
                SecretBox::new(Box::new(vec![4_u8, 5_u8, 6_u8])),
            )
            .await;
        assert!(totp_result.is_err(), "missing user should error");

        if let Err(err) = password_result {
            assert!(matches!(err, AppError::Storage(_)));
        }
        if let Err(err) = totp_result {
            assert!(matches!(err, AppError::Storage(_)));
        }
    }
}
