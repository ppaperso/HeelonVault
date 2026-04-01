use crate::models::{License, LicenseTier};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use ed25519_dalek::{Signature, VerifyingKey};
use hex::FromHex;
use serde::Deserialize;
use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use tracing::{debug, info, warn};

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum LicensePayload {
    JsonString(String),
    JsonObject(Value),
}

#[derive(Debug, Deserialize)]
struct SignedLicenseEnvelope {
    payload: LicensePayload,
    signature: String,
}

fn sanitize_hex_input(input: &str) -> String {
    let trimmed = input.trim();
    let without_prefix = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
        .unwrap_or(trimmed);

    without_prefix
        .chars()
        .filter(|c| !c.is_whitespace())
        .collect()
}

/// Public key for verifying license signatures.
/// This is the HEELONYS public key hardcoded at build time.
/// Format: 32 bytes in hex (64 characters).
const LICENSE_SIGNING_PUBLIC_KEY: &str = 
    "0c00513e16abc701916dd3e8fbd9ae8cacd7f73f3cc09cfac12c91de2bd3177d";

/// Community (free) edition - always valid, no signature check needed.
fn create_community_license() -> License {
    License {
        id: uuid::Uuid::new_v4().to_string(),
        customer_name: "Community Edition".to_string(),
        slots_count: 1,
        expiration_date: "9999-12-31T23:59:59Z".to_string(),
        features: vec!["audit_log".to_string()],
        tier: LicenseTier::Community,
    }
}

/// LicenseService handles license validation and loading.
pub struct LicenseService {
    /// Cached license after first successful load / verification.
    cached_license: Option<License>,
}

impl LicenseService {
    pub fn new() -> Self {
        Self {
            cached_license: None,
        }
    }

    /// Attempt to load and verify a license from the system.
    /// Returns Community tier if no Professional license found.
    pub async fn load_license(&mut self) -> Result<License, Box<dyn std::error::Error>> {
        // If cached, return it
        if let Some(cached) = &self.cached_license {
            return Ok(cached.clone());
        }

        // Attempt to load Professional license from platform-specific path
        let license_path = Self::get_license_path();
        debug!(path = ?license_path, "attempting to load professional license");

        match fs::read_to_string(&license_path) {
            Ok(content) => {
                match self.verify_and_parse_license(&content).await {
                    Ok(license) => {
                        info!(customer = license.customer_name, slots = license.slots_count, "professional license loaded and verified");
                        self.cached_license = Some(license.clone());
                        Ok(license)
                    }
                    Err(e) => {
                        warn!(path = ?license_path, error = %e, "professional license verification failed, falling back to community");
                        let community = create_community_license();
                        self.cached_license = Some(community.clone());
                        Ok(community)
                    }
                }
            }
            Err(_) => {
                debug!(path = ?license_path, "no professional license file found, using community edition");
                let community = create_community_license();
                self.cached_license = Some(community.clone());
                Ok(community)
            }
        }
    }

    /// Verify ed25519 signature and parse license from signed bundle.
    async fn verify_and_parse_license(
        &self,
        signed_content: &str,
    ) -> Result<License, Box<dyn std::error::Error>> {
        // Parse the signed license JSON
        let signed: SignedLicenseEnvelope = serde_json::from_str(signed_content)
            .map_err(|e| format!("invalid license JSON format: {}", e))?;

        let (payload_to_verify, license_payload) = match signed.payload {
            LicensePayload::JsonString(raw) => {
                let license: License = serde_json::from_str(&raw)
                    .map_err(|e| format!("invalid license payload JSON: {}", e))?;
                (raw, license)
            }
            LicensePayload::JsonObject(value) => {
                // Canonical compact serialization for signature verification when payload is embedded as object.
                let payload_json = serde_json::to_string(&value)
                    .map_err(|e| format!("invalid embedded payload JSON: {}", e))?;
                let license: License = serde_json::from_value(value)
                    .map_err(|e| format!("invalid embedded license payload: {}", e))?;
                (payload_json, license)
            }
        };

        // Decode public key from hex
        let normalized_public_key = sanitize_hex_input(LICENSE_SIGNING_PUBLIC_KEY);
        let pubkey_bytes: [u8; 32] =
            <[u8; 32]>::from_hex(normalized_public_key.as_str())
                .map_err(|e| format!("invalid public key format: {}", e))?;
        let verifying_key = VerifyingKey::from_bytes(&pubkey_bytes)
            .map_err(|e| format!("failed to construct verifying key: {}", e))?;

        // Decode signature from hex (should be 64 bytes = 128 hex chars)
        let normalized_signature = sanitize_hex_input(&signed.signature);
        let sig_bytes: Vec<u8> = match hex::decode(normalized_signature.as_str()) {
            Ok(bytes) => bytes,
            Err(hex_error) => STANDARD
                .decode(&signed.signature)
                .map_err(|b64_error| {
                    format!(
                        "invalid signature format (hex/base64): hex={}, base64={}",
                        hex_error, b64_error
                    )
                })?,
        };
        
        if sig_bytes.len() != 64 {
            return Err(format!(
                "invalid signature length: expected 64 bytes, got {}",
                sig_bytes.len()
            ).into());
        }

        let signature = Signature::from_slice(&sig_bytes)
            .map_err(|e| format!("failed to parse signature: {}", e))?;

        // Verify signature
        verifying_key
            .verify_strict(payload_to_verify.as_bytes(), &signature)
            .map_err(|e| format!("signature verification failed: {}", e))?;

        // Check expiration
        if !license_payload.is_valid() {
            return Err("license has expired".into());
        }

        Ok(license_payload)
    }

    /// Get platform-specific license file path.
    /// - Linux development: ~/.config/heelonvault/license.hvl
    /// - Linux production: /etc/heelonvault/license.hvl (requires permissions)
    /// - Windows: %PROGRAMDATA%\HeelonVault\license.hvl
    /// - macOS: /Library/Application Support/heelonvault/license.hvl
    fn get_license_path() -> PathBuf {
        #[cfg(target_os = "linux")]
        {
            // Check if we're in development (current_exe is in target/debug or target/release)
            if let Ok(exe_path) = std::env::current_exe() {
                if exe_path.to_string_lossy().contains("target/debug")
                    || exe_path.to_string_lossy().contains("target/release")
                {
                    // Development mode: use ~/.config/heelonvault/
                    if let Ok(home) = std::env::var("HOME") {
                        return PathBuf::from(format!("{}/.config/heelonvault/license.hvl", home));
                    }
                }
            }
            // Production mode: use /etc/heelonvault/
            PathBuf::from("/etc/heelonvault/license.hvl")
        }

        #[cfg(target_os = "windows")]
        {
            if let Ok(program_data) = std::env::var("PROGRAMDATA") {
                PathBuf::from(format!("{}\\HeelonVault\\license.hvl", program_data))
            } else {
                PathBuf::from("C:\\ProgramData\\HeelonVault\\license.hvl")
            }
        }

        #[cfg(target_os = "macos")]
        {
            if let Ok(home) = std::env::var("HOME") {
                PathBuf::from(format!(
                    "{}/Library/Application Support/heelonvault/license.hvl",
                    home
                ))
            } else {
                PathBuf::from("/Library/Application Support/heelonvault/license.hvl")
            }
        }

        #[cfg(not(any(target_os = "linux", target_os = "windows", target_os = "macos")))]
        {
            PathBuf::from("license.hvl")
        }
    }

    /// Get the current cached license (if loaded).
    pub fn get_cached(&self) -> Option<&License> {
        self.cached_license.as_ref()
    }

    /// Check if a given number of slots is available under current license.
    pub fn has_capacity(&self, current_slots: u32) -> bool {
        self.cached_license
            .as_ref()
            .map(|lic| lic.has_capacity(current_slots))
            .unwrap_or(true)
    }
}

impl Default for LicenseService {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_community_license_creation() {
        let lic = create_community_license();
        assert_eq!(lic.tier, LicenseTier::Community);
        assert!(lic.is_valid());
        assert!(lic.has_capacity(0));
    }
}
