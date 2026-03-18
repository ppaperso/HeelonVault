use heelonvault_rust::ui::messages;

#[test]
fn profile_empty_code_returns_expected_error_message() {
    let message = messages::validate_totp_code_format("");
    assert_eq!(
        message,
        Some("Code TOTP requis pour confirmer l'activation.")
    );
}

#[test]
fn profile_wrong_format_returns_expected_error_message() {
    let non_digit_message = messages::validate_totp_code_format("12a456");
    assert_eq!(
        non_digit_message,
        Some("Le code TOTP doit contenir exactement 6 chiffres.")
    );

    let short_message = messages::validate_totp_code_format("12345");
    assert_eq!(
        short_message,
        Some("Le code TOTP doit contenir exactement 6 chiffres.")
    );
}

#[test]
fn profile_wrong_totp_code_message_is_exact() {
    assert_eq!(
        messages::PROFILE_TOTP_CODE_INVALID_ERROR,
        "Code TOTP invalide. Vérifiez votre application d'authentification."
    );
}

#[test]
fn login_missing_code_when_twofa_enabled_returns_expected_error_message() {
    let message = messages::login_totp_error_message("");
    assert_eq!(
        message,
        "Code TOTP requis. Saisissez le code TOTP à 6 chiffres de votre application."
    );
}

#[test]
fn login_invalid_code_returns_expected_error_message() {
    let message = messages::login_totp_error_message("123456");
    assert_eq!(
        message,
        "Code TOTP invalide. Vérifiez votre application d'authentification."
    );
}
