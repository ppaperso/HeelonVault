use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct Vault {
    pub id: Uuid,
    pub owner_user_id: Uuid,
    pub name: String,
}
