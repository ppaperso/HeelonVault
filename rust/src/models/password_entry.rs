use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct PasswordEntry {
    pub id: Uuid,
    pub vault_id: Uuid,
    pub title: String,
}
