use secrecy::SecretBox;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum SecretType {
    Password,
    ApiToken,
    SshKey,
    SecureDocument,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum BlobStorage {
    Inline,
    File,
}

#[derive(Debug)]
pub struct SecretItem {
    pub id: Uuid,
    pub vault_id: Uuid,
    pub secret_type: SecretType,
    pub blob_storage: BlobStorage,
    pub secret_blob: SecretBox<Vec<u8>>,
}
