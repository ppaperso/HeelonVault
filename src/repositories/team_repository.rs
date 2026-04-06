use sqlx::{Row, SqlitePool};
use uuid::Uuid;

use crate::errors::AppError;
use crate::models::{Team, TeamMember, TeamMemberRole};

#[allow(async_fn_in_trait)]
pub trait TeamRepository {
    async fn create_team(
        &self,
        id: Uuid,
        name: &str,
        created_by: Option<Uuid>,
    ) -> Result<Team, AppError>;
    async fn get_by_id(&self, team_id: Uuid) -> Result<Option<Team>, AppError>;
    async fn list_all(&self) -> Result<Vec<Team>, AppError>;
    async fn list_for_user(&self, user_id: Uuid) -> Result<Vec<Team>, AppError>;
    async fn delete_team(&self, team_id: Uuid) -> Result<(), AppError>;
    async fn add_member(
        &self,
        team_id: Uuid,
        user_id: Uuid,
        role: &TeamMemberRole,
    ) -> Result<(), AppError>;
    async fn remove_member(&self, team_id: Uuid, user_id: Uuid) -> Result<(), AppError>;
    async fn list_members(&self, team_id: Uuid) -> Result<Vec<TeamMember>, AppError>;
    async fn get_member_role(
        &self,
        team_id: Uuid,
        user_id: Uuid,
    ) -> Result<Option<TeamMemberRole>, AppError>;
    /// Returns the user_ids of all members of a team (for bulk operations).
    async fn list_member_user_ids(&self, team_id: Uuid) -> Result<Vec<Uuid>, AppError>;
    /// Returns every team_id that contains this user, used during user deletion.
    async fn list_team_ids_for_user(&self, user_id: Uuid) -> Result<Vec<Uuid>, AppError>;
}

pub struct SqlxTeamRepository {
    pool: SqlitePool,
}

impl SqlxTeamRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    fn map_storage_err(context: &str, error: impl ToString) -> AppError {
        AppError::Storage(format!("{context}: {}", error.to_string()))
    }

    fn parse_member_role(raw: &str) -> Result<TeamMemberRole, AppError> {
        TeamMemberRole::from_db_str(raw)
            .map_err(|err| AppError::Storage(format!("invalid team member role in storage: {err}")))
    }

    fn row_to_team(row: &sqlx::sqlite::SqliteRow) -> Result<Team, AppError> {
        let id_str: String = row
            .try_get("id")
            .map_err(|err| Self::map_storage_err("read team id", err))?;
        let name: String = row
            .try_get("name")
            .map_err(|err| Self::map_storage_err("read team name", err))?;
        let created_by_str: Option<String> = row
            .try_get("created_by")
            .map_err(|err| Self::map_storage_err("read team created_by", err))?;
        let created_at: String = row
            .try_get("created_at")
            .map_err(|err| Self::map_storage_err("read team created_at", err))?;

        let id =
            Uuid::parse_str(&id_str).map_err(|err| Self::map_storage_err("parse team id", err))?;
        let created_by = created_by_str
            .as_deref()
            .map(Uuid::parse_str)
            .transpose()
            .map_err(|err| Self::map_storage_err("parse team created_by", err))?;

        Ok(Team {
            id,
            name,
            created_by,
            created_at,
        })
    }
}

impl TeamRepository for SqlxTeamRepository {
    async fn create_team(
        &self,
        id: Uuid,
        name: &str,
        created_by: Option<Uuid>,
    ) -> Result<Team, AppError> {
        if name.trim().is_empty() {
            return Err(AppError::Validation(
                "team name must not be empty".to_string(),
            ));
        }
        sqlx::query("INSERT INTO teams (id, name, created_by) VALUES (?1, ?2, ?3)")
            .bind(id.to_string())
            .bind(name)
            .bind(created_by.map(|u| u.to_string()))
            .execute(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("create team", err))?;

        let row = sqlx::query("SELECT id, name, created_by, created_at FROM teams WHERE id = ?1")
            .bind(id.to_string())
            .fetch_one(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("fetch created team", err))?;

        Self::row_to_team(&row)
    }

    async fn get_by_id(&self, team_id: Uuid) -> Result<Option<Team>, AppError> {
        let row_opt =
            sqlx::query("SELECT id, name, created_by, created_at FROM teams WHERE id = ?1")
                .bind(team_id.to_string())
                .fetch_optional(&self.pool)
                .await
                .map_err(|err| Self::map_storage_err("get team by id", err))?;

        match row_opt {
            Some(row) => Ok(Some(Self::row_to_team(&row)?)),
            None => Ok(None),
        }
    }

    async fn list_all(&self) -> Result<Vec<Team>, AppError> {
        let rows = sqlx::query("SELECT id, name, created_by, created_at FROM teams ORDER BY name")
            .fetch_all(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("list all teams", err))?;

        rows.iter().map(Self::row_to_team).collect()
    }

    async fn list_for_user(&self, user_id: Uuid) -> Result<Vec<Team>, AppError> {
        let rows = sqlx::query(
            "SELECT t.id, t.name, t.created_by, t.created_at \
             FROM teams t \
             INNER JOIN team_members tm ON tm.team_id = t.id \
             WHERE tm.user_id = ?1 \
             ORDER BY t.name",
        )
        .bind(user_id.to_string())
        .fetch_all(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("list teams for user", err))?;

        rows.iter().map(Self::row_to_team).collect()
    }

    async fn delete_team(&self, team_id: Uuid) -> Result<(), AppError> {
        let result = sqlx::query("DELETE FROM teams WHERE id = ?1")
            .bind(team_id.to_string())
            .execute(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("delete team", err))?;
        if result.rows_affected() == 0 {
            return Err(AppError::NotFound(
                "team not found for deletion".to_string(),
            ));
        }
        Ok(())
    }

    async fn add_member(
        &self,
        team_id: Uuid,
        user_id: Uuid,
        role: &TeamMemberRole,
    ) -> Result<(), AppError> {
        sqlx::query(
            "INSERT INTO team_members (team_id, user_id, role) VALUES (?1, ?2, ?3) \
             ON CONFLICT(team_id, user_id) DO UPDATE SET role = excluded.role",
        )
        .bind(team_id.to_string())
        .bind(user_id.to_string())
        .bind(role.to_db_str())
        .execute(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("add team member", err))?;
        Ok(())
    }

    async fn remove_member(&self, team_id: Uuid, user_id: Uuid) -> Result<(), AppError> {
        let result = sqlx::query("DELETE FROM team_members WHERE team_id = ?1 AND user_id = ?2")
            .bind(team_id.to_string())
            .bind(user_id.to_string())
            .execute(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("remove team member", err))?;
        if result.rows_affected() == 0 {
            return Err(AppError::NotFound(
                "team membership not found for removal".to_string(),
            ));
        }
        Ok(())
    }

    async fn list_members(&self, team_id: Uuid) -> Result<Vec<TeamMember>, AppError> {
        let rows = sqlx::query(
            "SELECT team_id, user_id, role, joined_at \
             FROM team_members WHERE team_id = ?1 ORDER BY joined_at",
        )
        .bind(team_id.to_string())
        .fetch_all(&self.pool)
        .await
        .map_err(|err| Self::map_storage_err("list team members", err))?;

        let mut members = Vec::with_capacity(rows.len());
        for row in &rows {
            let team_id_str: String = row
                .try_get("team_id")
                .map_err(|err| Self::map_storage_err("read team_id", err))?;
            let user_id_str: String = row
                .try_get("user_id")
                .map_err(|err| Self::map_storage_err("read user_id", err))?;
            let role_raw: String = row
                .try_get("role")
                .map_err(|err| Self::map_storage_err("read member role", err))?;
            let joined_at: String = row
                .try_get("joined_at")
                .map_err(|err| Self::map_storage_err("read joined_at", err))?;

            members.push(TeamMember {
                team_id: Uuid::parse_str(&team_id_str)
                    .map_err(|err| Self::map_storage_err("parse team_id", err))?,
                user_id: Uuid::parse_str(&user_id_str)
                    .map_err(|err| Self::map_storage_err("parse user_id", err))?,
                role: Self::parse_member_role(&role_raw)?,
                joined_at,
            });
        }
        Ok(members)
    }

    async fn get_member_role(
        &self,
        team_id: Uuid,
        user_id: Uuid,
    ) -> Result<Option<TeamMemberRole>, AppError> {
        let row_opt =
            sqlx::query("SELECT role FROM team_members WHERE team_id = ?1 AND user_id = ?2")
                .bind(team_id.to_string())
                .bind(user_id.to_string())
                .fetch_optional(&self.pool)
                .await
                .map_err(|err| Self::map_storage_err("get member role", err))?;

        match row_opt {
            Some(row) => {
                let role_raw: String = row
                    .try_get("role")
                    .map_err(|err| Self::map_storage_err("read member role", err))?;
                Ok(Some(Self::parse_member_role(&role_raw)?))
            }
            None => Ok(None),
        }
    }

    async fn list_member_user_ids(&self, team_id: Uuid) -> Result<Vec<Uuid>, AppError> {
        let rows = sqlx::query("SELECT user_id FROM team_members WHERE team_id = ?1")
            .bind(team_id.to_string())
            .fetch_all(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("list member user ids", err))?;

        let mut ids = Vec::with_capacity(rows.len());
        for row in &rows {
            let user_id_str: String = row
                .try_get("user_id")
                .map_err(|err| Self::map_storage_err("read user_id for ids", err))?;
            ids.push(
                Uuid::parse_str(&user_id_str)
                    .map_err(|err| Self::map_storage_err("parse user_id for ids", err))?,
            );
        }
        Ok(ids)
    }

    async fn list_team_ids_for_user(&self, user_id: Uuid) -> Result<Vec<Uuid>, AppError> {
        let rows = sqlx::query("SELECT team_id FROM team_members WHERE user_id = ?1")
            .bind(user_id.to_string())
            .fetch_all(&self.pool)
            .await
            .map_err(|err| Self::map_storage_err("list team ids for user", err))?;

        let mut ids = Vec::with_capacity(rows.len());
        for row in &rows {
            let team_id_str: String = row
                .try_get("team_id")
                .map_err(|err| Self::map_storage_err("read team_id for user", err))?;
            ids.push(
                Uuid::parse_str(&team_id_str)
                    .map_err(|err| Self::map_storage_err("parse team_id for user", err))?,
            );
        }
        Ok(ids)
    }
}

#[cfg(test)]
mod tests {
    use super::{SqlxTeamRepository, TeamRepository};
    use crate::models::TeamMemberRole;
    use sqlx::sqlite::SqlitePoolOptions;
    use uuid::Uuid;

    async fn setup_repo() -> Result<SqlxTeamRepository, String> {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .map_err(|err| format!("connect in-memory sqlite: {err}"))?;

        sqlx::query("PRAGMA foreign_keys = ON")
            .execute(&pool)
            .await
            .map_err(|err| format!("enable foreign keys pragma: {err}"))?;

        sqlx::query(
            "CREATE TABLE users (
                id TEXT PRIMARY KEY NOT NULL,
                username TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'user'
            )",
        )
        .execute(&pool)
        .await
        .map_err(|err| format!("create users table: {err}"))?;

        sqlx::query(
            "CREATE TABLE teams (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL UNIQUE,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            )",
        )
        .execute(&pool)
        .await
        .map_err(|err| format!("create teams table: {err}"))?;

        sqlx::query(
            "CREATE TABLE team_members (
                team_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, user_id),
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                CHECK (role IN ('member', 'leader'))
            )",
        )
        .execute(&pool)
        .await
        .map_err(|err| format!("create team_members table: {err}"))?;

        Ok(SqlxTeamRepository::new(pool))
    }

    async fn seed_user(repo: &SqlxTeamRepository, user_id: Uuid) -> Result<(), String> {
        sqlx::query("INSERT INTO users (id, username) VALUES (?1, ?2)")
            .bind(user_id.to_string())
            .bind(user_id.to_string())
            .execute(&repo.pool)
            .await
            .map_err(|err| format!("seed user: {err}"))?;
        Ok(())
    }

    #[tokio::test]
    async fn create_and_get_team() {
        let repo = setup_repo().await.expect("setup");
        let team_id = Uuid::new_v4();
        let team = repo
            .create_team(team_id, "DevOps", None)
            .await
            .expect("create_team");
        assert_eq!(team.name, "DevOps");
        assert_eq!(team.id, team_id);

        let found = repo.get_by_id(team_id).await.expect("get_by_id");
        assert!(found.is_some());
        assert_eq!(found.unwrap().name, "DevOps");
    }

    #[tokio::test]
    async fn add_and_list_members() {
        let repo = setup_repo().await.expect("setup");
        let team_id = Uuid::new_v4();
        let user_id = Uuid::new_v4();

        seed_user(&repo, user_id).await.expect("seed user");
        repo.create_team(team_id, "Alpha", None)
            .await
            .expect("create_team");
        repo.add_member(team_id, user_id, &TeamMemberRole::Leader)
            .await
            .expect("add_member");

        let members = repo.list_members(team_id).await.expect("list_members");
        assert_eq!(members.len(), 1);
        assert_eq!(members[0].user_id, user_id);
        assert_eq!(members[0].role, TeamMemberRole::Leader);
    }

    #[tokio::test]
    async fn remove_member_decrement() {
        let repo = setup_repo().await.expect("setup");
        let team_id = Uuid::new_v4();
        let user_id = Uuid::new_v4();

        seed_user(&repo, user_id).await.expect("seed user");
        repo.create_team(team_id, "Beta", None)
            .await
            .expect("create_team");
        repo.add_member(team_id, user_id, &TeamMemberRole::Member)
            .await
            .expect("add_member");
        repo.remove_member(team_id, user_id)
            .await
            .expect("remove_member");

        let members = repo.list_members(team_id).await.expect("list_members");
        assert!(members.is_empty());
    }

    #[tokio::test]
    async fn delete_team_cascades_members() {
        let repo = setup_repo().await.expect("setup");
        let team_id = Uuid::new_v4();
        let user_id = Uuid::new_v4();

        seed_user(&repo, user_id).await.expect("seed user");
        repo.create_team(team_id, "Gamma", None)
            .await
            .expect("create_team");
        repo.add_member(team_id, user_id, &TeamMemberRole::Member)
            .await
            .expect("add_member");
        repo.delete_team(team_id).await.expect("delete_team");

        let ids = repo
            .list_member_user_ids(team_id)
            .await
            .expect("list_member_user_ids");
        assert!(ids.is_empty(), "cascade should remove members");
    }
}
