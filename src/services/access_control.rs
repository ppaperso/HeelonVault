use crate::errors::AppError;
use crate::models::{TeamMemberRole, User, UserRole, VaultShareRole};

#[derive(Debug, Clone, Copy)]
pub enum Action {
    AdminManageUsers,
    TeamManageMembers,
    TeamReadMembers,
    VaultCreate,
    VaultOpen,
    VaultWrite,
    VaultList,
    VaultDelete,
    VaultShare,
    VaultRevoke,
    VaultRotate,
    AuditRead,
    AuditWrite,
}

#[derive(Debug, Clone)]
pub enum Resource {
    Global,
    Team {
        requester_role: Option<TeamMemberRole>,
    },
    Vault {
        is_owner: bool,
        has_direct_share: bool,
        has_team_share: bool,
        share_role: Option<VaultShareRole>,
    },
}

pub fn check_permission(user: &User, action: Action, resource: &Resource) -> Result<(), AppError> {
    if matches!(user.role, UserRole::Admin) {
        return Ok(());
    }

    match (action, resource) {
        (Action::AdminManageUsers, _) => Err(AppError::Authorization("admin role required".to_string())),
        (Action::AuditRead, _) => Err(AppError::Authorization("admin role required".to_string())),
        (Action::AuditWrite, _) => Ok(()),
        (Action::TeamManageMembers, Resource::Team { requester_role }) => {
            if matches!(requester_role, Some(TeamMemberRole::Leader)) {
                Ok(())
            } else {
                Err(AppError::Authorization("team leader role required".to_string()))
            }
        }
        (Action::TeamReadMembers, Resource::Team { requester_role }) => {
            if requester_role.is_some() {
                Ok(())
            } else {
                Err(AppError::Authorization("team membership required".to_string()))
            }
        }
        (Action::VaultCreate, Resource::Global) => Ok(()),
        (Action::VaultList, Resource::Global) => Ok(()),
        (
            Action::VaultDelete,
            Resource::Vault {
                is_owner,
                has_direct_share: _,
                has_team_share: _,
                share_role,
            },
        ) => {
            if *is_owner || share_role.is_some_and(|role| role.can_admin()) {
                Ok(())
            } else {
                Err(AppError::Authorization(
                    "vault deletion requires admin permission on the vault".to_string(),
                ))
            }
        }
        (
            Action::VaultWrite,
            Resource::Vault {
                is_owner,
                has_direct_share,
                has_team_share,
                share_role,
            },
        ) => {
            let has_access = *is_owner || *has_direct_share || *has_team_share;
            if has_access && (*is_owner || share_role.is_some_and(|role| role.can_write())) {
                Ok(())
            } else {
                Err(AppError::Authorization(
                    "vault write denied for this user".to_string(),
                ))
            }
        }
        (
            Action::VaultOpen,
            Resource::Vault {
                is_owner,
                has_direct_share,
                has_team_share,
                share_role: _,
            },
        ) => {
            if *is_owner || *has_direct_share || *has_team_share {
                Ok(())
            } else {
                Err(AppError::Authorization(
                    "vault access denied for this user".to_string(),
                ))
            }
        }
        (
            Action::VaultShare | Action::VaultRevoke | Action::VaultRotate,
            Resource::Vault {
                is_owner,
                has_direct_share,
                has_team_share,
                share_role,
            },
        ) => {
            let has_access = *is_owner || *has_direct_share || *has_team_share;
            if has_access && (*is_owner || share_role.is_some_and(|role| role.can_admin())) {
                Ok(())
            } else {
                Err(AppError::Authorization(
                    "vault administration denied for this user".to_string(),
                ))
            }
        }
        _ => Err(AppError::Authorization("unauthorized action".to_string())),
    }
}
