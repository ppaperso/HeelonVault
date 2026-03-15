use std::fs;
use std::path::Path;

use aes_gcm::aead::consts::U12;
use aes_gcm::aead::Aead;
use aes_gcm::{Aes256Gcm, KeyInit, Nonce};
use gtk4::glib::{Checksum, ChecksumType};
use secrecy::{ExposeSecret, SecretBox};
use crate::errors::AppError;

const BACKUP_MAGIC: &[u8; 5] = b"HVBK1";
const SHA256_HEX_LEN: usize = 64;
const BACKUP_NONCE_LEN: usize = 12;
const SQLITE_HEADER: &[u8; 16] = b"SQLite format 3\0";
const AES_256_KEY_LEN: usize = 32;

#[derive(Debug, Clone)]
pub struct BackupMetadata {
    pub sha256_hex: String,
    pub plaintext_size: usize,
}

#[allow(async_fn_in_trait)]
pub trait BackupService {
    fn export_backup(
        &self,
        sqlite_db_path: &Path,
        backup_file_path: &Path,
        backup_key: SecretBox<Vec<u8>>,
    ) -> Result<BackupMetadata, AppError>;
    fn import_backup(
        &self,
        backup_file_path: &Path,
        target_sqlite_db_path: &Path,
        backup_key: SecretBox<Vec<u8>>,
    ) -> Result<BackupMetadata, AppError>;
}

pub struct BackupServiceImpl;

impl BackupServiceImpl {
    pub fn new() -> Self {
        Self
    }

    fn validate_backup_key(backup_key: &SecretBox<Vec<u8>>) -> Result<(), AppError> {
        if backup_key.expose_secret().len() != AES_256_KEY_LEN {
            return Err(AppError::Validation(format!(
                "backup key must be {AES_256_KEY_LEN} bytes"
            )));
        }

        Ok(())
    }

    fn validate_sqlite_bytes(bytes: &[u8]) -> Result<(), AppError> {
        if bytes.len() < SQLITE_HEADER.len() || !bytes.starts_with(SQLITE_HEADER) {
            return Err(AppError::Validation(
                "input is not a valid SQLite file header".to_string(),
            ));
        }

        Ok(())
    }

    fn sha256_hex(bytes: &[u8]) -> Result<String, AppError> {
        let mut checksum = Checksum::new(ChecksumType::Sha256)
            .ok_or_else(|| AppError::Validation("failed to initialize SHA-256".to_string()))?;
        checksum.update(bytes);
        checksum
            .string()
            .map(|value| value.to_string())
            .ok_or_else(|| AppError::Validation("failed to finalize SHA-256".to_string()))
    }

    fn generate_nonce() -> Result<[u8; BACKUP_NONCE_LEN], AppError> {
        let mut nonce = [0_u8; BACKUP_NONCE_LEN];
        getrandom::fill(&mut nonce)
            .map_err(|err| AppError::Crypto(format!("backup nonce generation failed: {err}")))?;
        Ok(nonce)
    }

    fn encrypt_bytes(
        plaintext: &[u8],
        backup_key: &SecretBox<Vec<u8>>,
    ) -> Result<(String, [u8; BACKUP_NONCE_LEN], Vec<u8>), AppError> {
        Self::validate_backup_key(backup_key)?;
        Self::validate_sqlite_bytes(plaintext)?;

        let sha256_hex = Self::sha256_hex(plaintext)?;
        let nonce = Self::generate_nonce()?;
        let nonce_ga: Nonce<U12> = nonce.into();

        let cipher = Aes256Gcm::new_from_slice(backup_key.expose_secret().as_slice())
            .map_err(|err| AppError::Crypto(format!("invalid backup key: {err}")))?;
        let ciphertext = cipher
            .encrypt(&nonce_ga, plaintext)
            .map_err(|_| AppError::Crypto("backup encryption failed".to_string()))?;

        Ok((sha256_hex, nonce, ciphertext))
    }

    fn decrypt_bytes(
        sha256_hex: &str,
        nonce: [u8; BACKUP_NONCE_LEN],
        ciphertext: &[u8],
        backup_key: &SecretBox<Vec<u8>>,
    ) -> Result<Vec<u8>, AppError> {
        Self::validate_backup_key(backup_key)?;

        let cipher = Aes256Gcm::new_from_slice(backup_key.expose_secret().as_slice())
            .map_err(|err| AppError::Crypto(format!("invalid backup key: {err}")))?;
        let nonce_ga: Nonce<U12> = nonce.into();
        let plaintext = cipher
            .decrypt(&nonce_ga, ciphertext)
            .map_err(|_| AppError::Crypto("backup decryption failed".to_string()))?;

        Self::validate_sqlite_bytes(plaintext.as_slice())?;

        let actual_sha256 = Self::sha256_hex(plaintext.as_slice())?;
        if actual_sha256 != sha256_hex {
            return Err(AppError::Validation(
                "backup integrity verification failed before restore".to_string(),
            ));
        }

        Ok(plaintext)
    }

    fn serialize_backup(
        sha256_hex: &str,
        nonce: [u8; BACKUP_NONCE_LEN],
        ciphertext: &[u8],
    ) -> Result<Vec<u8>, AppError> {
        if sha256_hex.len() != SHA256_HEX_LEN {
            return Err(AppError::Validation(
                "backup SHA-256 digest has invalid length".to_string(),
            ));
        }

        let mut bytes = Vec::with_capacity(
            BACKUP_MAGIC.len() + SHA256_HEX_LEN + BACKUP_NONCE_LEN + ciphertext.len(),
        );
        bytes.extend_from_slice(BACKUP_MAGIC);
        bytes.extend_from_slice(sha256_hex.as_bytes());
        bytes.extend_from_slice(&nonce);
        bytes.extend_from_slice(ciphertext);
        Ok(bytes)
    }

    fn parse_backup(bytes: &[u8]) -> Result<(String, [u8; BACKUP_NONCE_LEN], Vec<u8>), AppError> {
        let minimum_len = BACKUP_MAGIC.len() + SHA256_HEX_LEN + BACKUP_NONCE_LEN + 1;
        if bytes.len() < minimum_len {
            return Err(AppError::Validation(
                "backup file is too short".to_string(),
            ));
        }

        if &bytes[0..BACKUP_MAGIC.len()] != BACKUP_MAGIC {
            return Err(AppError::Validation(
                "backup file has an invalid header".to_string(),
            ));
        }

        let digest_start = BACKUP_MAGIC.len();
        let digest_end = digest_start + SHA256_HEX_LEN;
        let nonce_end = digest_end + BACKUP_NONCE_LEN;

        let sha256_hex = std::str::from_utf8(&bytes[digest_start..digest_end])
            .map_err(|_| AppError::Validation("backup digest is not valid UTF-8".to_string()))?
            .to_string();
        if !sha256_hex.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err(AppError::Validation(
                "backup digest is not valid hexadecimal".to_string(),
            ));
        }

        let mut nonce = [0_u8; BACKUP_NONCE_LEN];
        nonce.copy_from_slice(&bytes[digest_end..nonce_end]);

        let ciphertext = bytes[nonce_end..].to_vec();
        if ciphertext.is_empty() {
            return Err(AppError::Validation(
                "backup file does not contain ciphertext".to_string(),
            ));
        }

        Ok((sha256_hex, nonce, ciphertext))
    }

    fn ensure_parent_exists(path: &Path) -> Result<(), AppError> {
        match path.parent() {
            Some(parent) if !parent.as_os_str().is_empty() => {
                fs::create_dir_all(parent).map_err(|err| {
                    AppError::Storage(format!("failed to create parent directory: {err}"))
                })
            }
            _ => Ok(()),
        }
    }
}

impl Default for BackupServiceImpl {
    fn default() -> Self {
        Self::new()
    }
}

impl BackupService for BackupServiceImpl {
    fn export_backup(
        &self,
        sqlite_db_path: &Path,
        backup_file_path: &Path,
        backup_key: SecretBox<Vec<u8>>,
    ) -> Result<BackupMetadata, AppError> {
        let sqlite_bytes = fs::read(sqlite_db_path)
            .map_err(|err| AppError::Storage(format!("failed to read SQLite database: {err}")))?;

        let (sha256_hex, nonce, ciphertext) =
            Self::encrypt_bytes(sqlite_bytes.as_slice(), &backup_key)?;
        let backup_bytes = Self::serialize_backup(&sha256_hex, nonce, ciphertext.as_slice())?;

        Self::ensure_parent_exists(backup_file_path)?;
        fs::write(backup_file_path, backup_bytes).map_err(|err| {
            AppError::Storage(format!("failed to write backup file: {err}"))
        })?;

        let exported_sha256 = Self::sha256_hex(sqlite_bytes.as_slice())?;
        if exported_sha256 != sha256_hex {
            return Err(AppError::Validation(
                "backup integrity verification failed after export".to_string(),
            ));
        }

        Ok(BackupMetadata {
            sha256_hex,
            plaintext_size: sqlite_bytes.len(),
        })
    }

    fn import_backup(
        &self,
        backup_file_path: &Path,
        target_sqlite_db_path: &Path,
        backup_key: SecretBox<Vec<u8>>,
    ) -> Result<BackupMetadata, AppError> {
        let backup_bytes = fs::read(backup_file_path)
            .map_err(|err| AppError::Storage(format!("failed to read backup file: {err}")))?;
        let (sha256_hex, nonce, ciphertext) = Self::parse_backup(backup_bytes.as_slice())?;
        let plaintext =
            Self::decrypt_bytes(&sha256_hex, nonce, ciphertext.as_slice(), &backup_key)?;

        Self::ensure_parent_exists(target_sqlite_db_path)?;
        fs::write(target_sqlite_db_path, plaintext.as_slice()).map_err(|err| {
            AppError::Storage(format!("failed to write restored SQLite database: {err}"))
        })?;

        let restored_bytes = fs::read(target_sqlite_db_path).map_err(|err| {
            AppError::Storage(format!("failed to reread restored SQLite database: {err}"))
        })?;
        let restored_sha256 = Self::sha256_hex(restored_bytes.as_slice())?;
        if restored_sha256 != sha256_hex {
            return Err(AppError::Validation(
                "backup integrity verification failed after restore".to_string(),
            ));
        }

        Ok(BackupMetadata {
            sha256_hex,
            plaintext_size: restored_bytes.len(),
        })
    }
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::{Path, PathBuf};

    use secrecy::{ExposeSecret, SecretBox};
    use uuid::Uuid;

    use crate::errors::AppError;

    use super::{BackupService, BackupServiceImpl, BACKUP_MAGIC};

    struct TestTempDir {
        path: PathBuf,
    }

    impl TestTempDir {
        fn new() -> Result<Self, AppError> {
            let path = std::env::temp_dir().join(format!("heelonvault-backup-test-{}", Uuid::new_v4()));
            fs::create_dir_all(&path)
                .map_err(|err| AppError::Storage(format!("failed to create temp dir: {err}")))?;
            Ok(Self { path })
        }

        fn path(&self) -> &Path {
            &self.path
        }
    }

    impl Drop for TestTempDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn sample_sqlite_bytes() -> Vec<u8> {
        let mut bytes = Vec::new();
        bytes.extend_from_slice(b"SQLite format 3\0");
        bytes.extend_from_slice(&[0_u8; 256]);
        bytes
    }

    fn write_sample_sqlite(path: &Path) -> Result<Vec<u8>, AppError> {
        let bytes = sample_sqlite_bytes();
        fs::write(path, bytes.as_slice())
            .map_err(|err| AppError::Storage(format!("failed to seed sqlite file: {err}")))?;
        Ok(bytes)
    }

    #[test]
    fn export_and_import_roundtrip_preserves_sha256_and_bytes() {
        let temp_dir_result = TestTempDir::new();
        assert!(temp_dir_result.is_ok(), "temp dir creation should succeed");
        let temp_dir = match temp_dir_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let source_db_path = temp_dir.path().join("source.db");
        let backup_path = temp_dir.path().join("backup.hvbk");
        let restored_db_path = temp_dir.path().join("restored.db");
        let original_bytes_result = write_sample_sqlite(&source_db_path);
        assert!(original_bytes_result.is_ok(), "sqlite seed should succeed");
        let original_bytes = match original_bytes_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let service = BackupServiceImpl::new();
        let backup_key = SecretBox::new(Box::new(vec![7_u8; 32]));

        let export_result = service.export_backup(
            &source_db_path,
            &backup_path,
            SecretBox::new(Box::new(backup_key.expose_secret().clone())),
        );
        assert!(export_result.is_ok(), "backup export should succeed");
        let export_metadata = match export_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let import_result = service.import_backup(&backup_path, &restored_db_path, backup_key);
        assert!(import_result.is_ok(), "backup import should succeed");
        let import_metadata = match import_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let restored_bytes_result = fs::read(&restored_db_path)
            .map_err(|err| AppError::Storage(format!("failed to read restored db: {err}")));
        assert!(restored_bytes_result.is_ok(), "restored file should be readable");
        let restored_bytes = match restored_bytes_result {
            Ok(value) => value,
            Err(_) => return,
        };

        assert_eq!(export_metadata.sha256_hex, import_metadata.sha256_hex);
        assert_eq!(export_metadata.plaintext_size, original_bytes.len());
        assert_eq!(restored_bytes, original_bytes);
    }

    #[test]
    fn export_rejects_non_sqlite_input() {
        let temp_dir_result = TestTempDir::new();
        assert!(temp_dir_result.is_ok(), "temp dir creation should succeed");
        let temp_dir = match temp_dir_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let source_db_path = temp_dir.path().join("invalid.db");
        let backup_path = temp_dir.path().join("backup.hvbk");
        let seed_result = fs::write(&source_db_path, b"not-a-sqlite-file");
        assert!(seed_result.is_ok(), "invalid seed file should be writable");
        if seed_result.is_err() {
            return;
        }

        let service = BackupServiceImpl::new();
        let export_result =
            service.export_backup(&source_db_path, &backup_path, SecretBox::new(Box::new(vec![3_u8; 32])));

        assert!(matches!(export_result, Err(AppError::Validation(_))));
    }

    #[test]
    fn import_rejects_tampered_backup_digest() {
        let temp_dir_result = TestTempDir::new();
        assert!(temp_dir_result.is_ok(), "temp dir creation should succeed");
        let temp_dir = match temp_dir_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let source_db_path = temp_dir.path().join("source.db");
        let backup_path = temp_dir.path().join("backup.hvbk");
        let restored_db_path = temp_dir.path().join("restored.db");
        let seed_result = write_sample_sqlite(&source_db_path);
        assert!(seed_result.is_ok(), "sqlite seed should succeed");
        if seed_result.is_err() {
            return;
        }

        let service = BackupServiceImpl::new();
        let backup_key = SecretBox::new(Box::new(vec![9_u8; 32]));
        let export_result = service.export_backup(
            &source_db_path,
            &backup_path,
            SecretBox::new(Box::new(backup_key.expose_secret().clone())),
        );
        assert!(export_result.is_ok(), "backup export should succeed");
        if export_result.is_err() {
            return;
        }

        let backup_bytes_result = fs::read(&backup_path)
            .map_err(|err| AppError::Storage(format!("failed to read backup file: {err}")));
        assert!(backup_bytes_result.is_ok(), "backup should be readable");
        let mut backup_bytes = match backup_bytes_result {
            Ok(value) => value,
            Err(_) => return,
        };

        let digest_index = BACKUP_MAGIC.len();
        backup_bytes[digest_index] = if backup_bytes[digest_index] == b'a' { b'b' } else { b'a' };

        let rewrite_result = fs::write(&backup_path, backup_bytes);
        assert!(rewrite_result.is_ok(), "tampered backup should be writable");
        if rewrite_result.is_err() {
            return;
        }

        let import_result = service.import_backup(&backup_path, &restored_db_path, backup_key);
        assert!(matches!(import_result, Err(AppError::Validation(_))));
    }
}
