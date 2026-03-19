pub const TWOFA_BADGE_DISABLED: &str = "Désactivée";
pub const TWOFA_BADGE_ENABLED: &str = "Activée 🔒";

pub const PROFILE_TOTP_CODE_EMPTY_ERROR: &str =
    "Code TOTP requis pour confirmer l'activation.";
pub const PROFILE_TOTP_CODE_FORMAT_ERROR: &str =
    "Le code TOTP doit contenir exactement 6 chiffres.";
pub const PROFILE_TOTP_CODE_INVALID_ERROR: &str =
    "Code TOTP invalide. Vérifiez votre application d'authentification.";

pub const LOGIN_TOTP_CODE_MISSING_ERROR: &str =
    "Code TOTP requis. Saisissez le code TOTP à 6 chiffres de votre application.";
pub const LOGIN_TOTP_CODE_INVALID_ERROR: &str =
    "Code TOTP invalide. Vérifiez votre application d'authentification.";

pub fn validate_totp_code_format(code: &str) -> Option<&'static str> {
    if code.trim().is_empty() {
        return Some(PROFILE_TOTP_CODE_EMPTY_ERROR);
    }

    if code.len() != 6 || !code.chars().all(|character| character.is_ascii_digit()) {
        return Some(PROFILE_TOTP_CODE_FORMAT_ERROR);
    }

    None
}

pub fn login_totp_error_message(code: &str) -> &'static str {
    if code.trim().is_empty() {
        LOGIN_TOTP_CODE_MISSING_ERROR
    } else {
        LOGIN_TOTP_CODE_INVALID_ERROR
    }
}