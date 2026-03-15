use uuid::Uuid;

#[derive(Debug, Clone)]
pub enum UserRole {
    User,
    Admin,
}

#[derive(Debug, Clone)]
pub struct User {
    pub id: Uuid,
    pub username: String,
    pub role: UserRole,
}
