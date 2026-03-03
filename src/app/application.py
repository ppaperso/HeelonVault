"""Application Adwaita orchestrant les couches services et UI."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import gi  # type: ignore[import]

from src.config.environment import get_data_directory
from src.config.logging_config import configure_logging
from src.i18n import _, init_i18n
from src.repositories.password_repository import PasswordRepository
from src.services.auth_service import AuthService
from src.services.backup_service import BackupService
from src.services.crypto_service import CryptoService
from src.services.csv_importer import CSVImporter
from src.services.login_attempt_tracker import LoginAttemptTracker
from src.services.password_service import PasswordService
from src.services.totp_service import TOTPService
from src.ui.dialogs.about_dialog import show_about_dialog
from src.ui.dialogs.backup_manager_dialog import BackupManagerDialog
from src.ui.dialogs.email_login_dialog import EmailLoginDialog
from src.ui.dialogs.import_dialog import ImportCSVDialog
from src.ui.dialogs.manage_account_dialog import ManageAccountDialog
from src.ui.dialogs.setup_2fa_dialog import Setup2FADialog
from src.ui.dialogs.update_email_dialog import UpdateEmailDialog
from src.ui.dialogs.verify_totp_dialog import VerifyTOTPDialog
from src.ui.windows.main_window import PasswordManagerWindow
from src.version import (
    __app_display_name__,
    __app_id__,
    get_version,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

configure_logging()
init_i18n()
logger = logging.getLogger(__name__)
DATA_DIR = get_data_directory()


def _install_branding_css() -> None:
    """Charge le thème Heelonys global dans GTK."""
    display = Gdk.Display.get_default()
    if not display:
        return

    css = """
    * {
        font-family: "Space Grotesk", "Inter", "Cantarell", sans-serif;
    }

    window,
    dialog,
    .background {
        background: #F3F6F3;
        color: #2C3E50;
    }

    headerbar {
        background: linear-gradient(135deg, #07393A, #0A5F5C);
        color: #FFFFFF;
    }

    headerbar label,
    headerbar image,
    headerbar button {
        color: #FFFFFF;
    }

    headerbar .title-1,
    headerbar .title-2,
    headerbar .title-3,
    headerbar .title-4,
    headerbar .heading,
    headerbar .caption,
    headerbar .dim-label {
        color: #FFFFFF;
    }

    headerbar .accent {
        background: rgba(255, 255, 255, 0.18);
        color: #FFFFFF;
    }

    headerbar .warning {
        color: #A4DFCF;
    }

    popover,
    popover.background {
        background: transparent;
        border: none;
        box-shadow: none;
    }

    popover contents {
        background: transparent;
        padding: 0;
        border: none;
    }

    popover menu,
    popover box {
        background: #FFFFFF;
        color: #2C3E50;
        border-radius: 16px;
        border: 1px solid #A4DFCF;
        box-shadow: 0 20px 40px rgba(7, 57, 58, 0.12);
    }

    popover modelbutton,
    popover menuitem,
    popover label {
        color: #2C3E50;
    }

    popover modelbutton:hover,
    popover menuitem:hover {
        background: #F3F6F3;
    }

    toast {
        background-image: linear-gradient(120deg, #13A1A1, #1F8678);
        color: #FFFFFF;
        border-radius: 12px;
        border: 1px solid rgba(7, 57, 58, 0.18);
        box-shadow: 0 10px 24px rgba(7, 57, 58, 0.22);
    }

    toast label,
    toast button,
    toast image {
        color: #FFFFFF;
    }

    toast button {
        background: rgba(255, 255, 255, 0.14);
        border: 1px solid rgba(255, 255, 255, 0.28);
        border-radius: 999px;
        transition: all 220ms ease;
    }

    toast button:hover {
        background: rgba(255, 255, 255, 0.22);
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(7, 57, 58, 0.20);
    }

    toast button:active {
        background: rgba(7, 57, 58, 0.22);
        transform: translateY(0);
        box-shadow: none;
    }

    toast button:focus {
        outline: 2px solid #13A1A1;
        outline-offset: 2px;
    }

    button {
        border-radius: 12px;
        transition: all 220ms ease;
    }

    button.suggested-action {
        background-image: linear-gradient(120deg, #13A1A1, #1F8678);
        color: #FFFFFF;
        border-radius: 999px;
        padding: 12px 20px;
        box-shadow: 0 8px 20px rgba(7, 57, 58, 0.18);
        border: none;
    }

    button.suggested-action:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 24px rgba(7, 57, 58, 0.24);
    }

    button.suggested-action:active {
        transform: translateY(0);
    }

    button.pill {
        border-radius: 999px;
    }

    button.destructive-action {
        border-radius: 999px;
    }

    .card {
        background: linear-gradient(135deg, #FFFFFF, #F3F6F3);
        border: 1px solid #A4DFCF;
        border-radius: 20px;
        box-shadow: 0 20px 40px rgba(7, 57, 58, 0.08);
    }

    .sidebar-card,
    .sidebar-expander {
        border-color: rgba(87, 185, 177, 0.40);
        box-shadow: 0 6px 18px rgba(7, 57, 58, 0.07);
    }

    .sidebar-branding {
        border-color: rgba(87, 185, 177, 0.55);
        border-radius: 18px;
        background: linear-gradient(135deg, #FFFFFF 0%, #EEF8F7 100%);
        box-shadow: 0 10px 24px rgba(7, 57, 58, 0.10);
        padding: 8px 12px;
    }

    .sidebar-brand-logo {
        min-width: 22px;
        min-height: 22px;
        padding: 0;
    }

    .sidebar-brand-title {
        font-size: 1.00rem;
        font-weight: 780;
        letter-spacing: 0.08em;
        font-family: "Space Grotesk", "Inter", "Cantarell", sans-serif;
        color: #07393A;
    }

    .dashboard-footer {
        border-top: 1px solid rgba(164, 223, 207, 0.65);
        padding-top: 8px;
    }

    .dashboard-footer-label {
        color: #6B9EA3;
        font-size: 0.84rem;
        font-weight: 520;
    }

    .header-date-label {
        color: #FFFFFF;
        font-size: 0.96rem;
        font-weight: 640;
        letter-spacing: 0.04em;
    }

    .account-page-title {
        color: #07393A;
        font-size: 1.18rem;
        font-weight: 760;
        letter-spacing: 0.02em;
    }

    .account-page-subtitle {
        color: #6B9EA3;
        font-size: 0.86rem;
        font-weight: 500;
    }

    .account-group {
        margin-top: 2px;
        margin-bottom: 2px;
    }

    .account-action-btn {
        min-height: 30px;
        padding-left: 12px;
        padding-right: 12px;
    }

    .account-status {
        font-size: 0.86rem;
        font-weight: 520;
        margin-top: 2px;
    }

    /* ─── STATUS CARD ──────────────────────────────────────────────────── */
    .status-card {
        background: linear-gradient(135deg, #FFFFFF 0%, #EEF8F7 100%);
        border-color: rgba(87, 185, 177, 0.50);
        border-radius: 18px;
        box-shadow: 0 4px 16px rgba(7, 57, 58, 0.08);
    }

    /* Avatar name / role */
    .status-username {
        font-weight: 650;
        font-size: 1.12rem;
        color: #07393A;
    }
    .status-role-pill {
        font-size: 0.80rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        border-radius: 999px;
        padding: 2px 10px;
    }
    .status-role-admin {
        background: rgba(19, 161, 161, 0.14);
        color: #0A5F5C;
        border: 1px solid rgba(19, 161, 161, 0.32);
    }
    .status-role-user {
        background: rgba(44, 62, 80, 0.09);
        color: #4A5568;
        border: 1px solid rgba(44, 62, 80, 0.18);
    }

    /* Séparateurs verticaux dans la status card */
    .status-vsep {
        background: rgba(164, 223, 207, 0.55);
        min-width: 1px;
    }

    /* Chips de statistiques */
    .status-stat-chip { /* no background, just spacing via margins */ }
    .status-stat-icon { color: #57B9B1; opacity: 0.80; }
    .status-stat-value {
        font-weight: 700;
        font-size: 1.20rem;
        color: #07393A;
    }
    .status-stat-sub {
        font-size: 0.82rem;
        color: #8CACB0;
        font-weight: 500;
    }

    /* Dernière connexion */
    .status-meta-icon   { color: #8CACB0; }
    .status-last-login  { font-size: 0.88rem; color: #8CACB0; }

    /* Badge sécurité */
    .status-weak-badge {
        border-radius: 999px;
        padding: 2px 8px;
    }
    .status-weak-ok {
        background: rgba(31, 134, 120, 0.10);
        border: 1px solid rgba(31, 134, 120, 0.28);
    }
    .status-weak-warn {
        background: rgba(231, 76, 60, 0.10);
        border: 1px solid rgba(231, 76, 60, 0.30);
    }
    .status-weak-label      { font-size: 0.88rem; font-weight: 600; color: #6B9EA3; }
    .status-weak-label-warn { color: #C0392B; }

    /* ---legacy metric-tile kept for compat--- */
    .metric-tile {
        background: rgba(19, 161, 161, 0.08);
        border: 1px solid rgba(87, 185, 177, 0.40);
        border-radius: 12px;
        padding: 8px 10px;
    }

    flowbox checkbutton {
        border-radius: 999px;
        border: 1px solid rgba(87, 185, 177, 0.55);
        padding: 4px 8px;
        background: rgba(255, 255, 255, 0.9);
    }

    flowbox checkbutton:checked {
        background-image: linear-gradient(120deg, rgba(19, 161, 161, 0.20), rgba(31, 134, 120, 0.20));
        border-color: #13A1A1;
    }

    flowboxchild > .card {
        border-radius: 14px;
        box-shadow: 0 8px 16px rgba(7, 57, 58, 0.06);
    }

    /* ─── TOOLTIPS PREMIUM ─────────────────────────────────────────────── */

    tooltip {
        background: transparent;
        padding: 0;
    }

    tooltip > * {
        background: linear-gradient(145deg, #07393A 0%, #0C5254 60%, #0F6B60 100%);
        color: #FFFFFF;
        border-radius: 14px;
        border: 1px solid rgba(164, 223, 207, 0.35);
        box-shadow:
            0 16px 40px rgba(7, 57, 58, 0.40),
            0  4px 12px rgba(7, 57, 58, 0.25),
            inset 0 1px 0 rgba(255, 255, 255, 0.10);
        padding: 0;
    }

    tooltip label {
        color: #FFFFFF;
        font-size: 0.90rem;
        font-family: "Space Grotesk", "Inter", "Cantarell", sans-serif;
        padding: 11px 15px;
        line-height: 1.55;
    }

    /* ─── PASSWORD CARDS ────────────────────────────────────────────── */

    .password-card {
        border-radius: 18px;
        border: 1px solid rgba(164, 223, 207, 0.65);
        background: #FFFFFF;
        box-shadow: 0 4px 14px rgba(7, 57, 58, 0.07);
        transition: all 200ms ease;
    }

    .password-card:hover {
        border-color: #57B9B1;
        box-shadow: 0 10px 30px rgba(7, 57, 58, 0.14);
        transform: translateY(-2px);
    }

    /* Bande de force en haut */
    .card-strength-bar {
        border-radius: 18px 18px 0 0;
        min-height: 4px;
    }
    .card-strength-success { background: linear-gradient(90deg, #1F8678, #13A1A1); }
    .card-strength-warning { background: linear-gradient(90deg, #E6B800, #F0C040); }
    .card-strength-error   { background: linear-gradient(90deg, #E74C3C, #FF6B6B); }

    /* Badge icône */
    .card-icon-badge {
        border-radius: 10px;
        padding: 6px;
        min-width: 32px;
        min-height: 32px;
    }
    .card-icon-badge-success { background: rgba(31, 134, 120, 0.12); }
    .card-icon-badge-warning { background: rgba(230, 184, 0,   0.12); }
    .card-icon-badge-error   { background: rgba(231,  76, 60,  0.12); }

    /* Titre de la card */
    .card-title {
        font-weight: 650;
        font-size: 0.95rem;
        color: #07393A;
    }

    /* Catégorie */
    .card-category {
        font-size: 0.73rem;
        color: #6B9EA3;
        font-weight: 500;
    }

    /* Ligne identifiant/domaine */
    .card-hint {
        font-family: "Space Mono", "JetBrains Mono", monospace;
        font-size: 0.72rem;
        color: #8CACB0;
        font-weight: 400;
    }

    /* Séparateur fin */
    .card-sep {
        background: rgba(164, 223, 207, 0.5);
        min-height: 1px;
        margin-top: 2px;
        margin-bottom: 2px;
    }

    /* Boutons d'action dans les cards */
    .card-action-btn {
        min-width: 28px;
        min-height: 28px;
        padding: 4px;
        opacity: 0.65;
        transition: opacity 150ms ease, transform 150ms ease;
    }
    .card-action-btn:hover {
        opacity: 1;
        transform: scale(1.15);
    }

    /* Bouton corbeille */
    .card-delete-btn {
        opacity: 0.35;
        min-width: 26px;
        min-height: 26px;
        padding: 3px;
        transition: opacity 180ms ease, color 180ms ease;
    }
    .card-delete-btn:hover {
        opacity: 0.9;
    }

    /* Badges d'alerte */
    .card-alert-badge {
        font-size: 0.68rem;
        font-weight: 700;
        border-radius: 999px;
        padding: 2px 6px;
    }
    .card-alert-warning {
        background: rgba(230, 184, 0, 0.15);
        color: #9A7A00;
        border: 1px solid rgba(230, 184, 0, 0.4);
    }
    .card-alert-error {
        background: rgba(231, 76, 60, 0.12);
        color: #C0392B;
        border: 1px solid rgba(231, 76, 60, 0.35);
    }

    /* Tag pills */
    .card-tag-pill {
        font-size: 0.65rem;
        font-weight: 600;
        color: #0A5F5C;
        background: rgba(19, 161, 161, 0.10);
        border: 1px solid rgba(19, 161, 161, 0.28);
        border-radius: 999px;
        padding: 1px 7px;
    }
    .card-tag-more {
        font-size: 0.63rem;
        font-weight: 600;
        color: #6B9EA3;
    }

    .accent,
    label.accent {
        background: rgba(19, 161, 161, 0.12);
        color: #0A5F5C;
        border-radius: 999px;
        padding: 6px 14px;
    }

    label.success,
    .success {
        color: #1F8678;
    }

    label.warning,
    .warning {
        color: #13A1A1;
    }

    label.error,
    .error {
        color: #E74C3C;
    }

    label.heading,
    .heading,
    .title-1,
    .title-2,
    .title-3,
    .title-4 {
        color: #07393A;
    }

    entry,
    textview,
    spinbutton {
        border-radius: 12px;
        border: 1px solid #57B9B1;
        background: #FFFFFF;
        color: #2C3E50;
    }

    entry:focus,
    textview:focus,
    spinbutton:focus,
    button:focus,
    row:focus {
        outline: 2px solid #13A1A1;
        outline-offset: 2px;
    }

    list,
    listview,
    preferencesgroup {
        background: transparent;
    }

    /* Overrides finaux: badges dans la barre haute */
    headerbar label.accent,
    headerbar .accent {
        background: rgba(255, 255, 255, 0.22);
        color: #FFFFFF;
        border: 1px solid rgba(255, 255, 255, 0.35);
        border-radius: 999px;
        padding: 3px 10px;
    }

    headerbar label.warning,
    headerbar .warning {
        background: rgba(255, 255, 255, 0.16);
        color: #FFFFFF;
        border: 1px solid rgba(255, 255, 255, 0.28);
        border-radius: 999px;
        padding: 3px 10px;
    }

    headerbar label.header-badge,
    headerbar .header-badge {
        font-size: 0.80rem;
        font-weight: 600;
        min-height: 22px;
        line-height: 1;
        margin-top: 0;
        margin-bottom: 0;
    }

    headerbar label.admin-badge,
    headerbar .admin-badge,
    headerbar label.dev-badge,
    headerbar .dev-badge {
        padding-left: 10px;
        padding-right: 10px;
    }
    """

    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class PasswordManagerApplication(Adw.Application):
    """Application principale reliant services et interface graphique."""

    def __init__(self):
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._branding_css_loaded = False
        self.window: PasswordManagerWindow | None = None
        self.email_login_dialog = None  # EmailLoginDialog (nouveau flux)
        self.auth_service: AuthService | None = None
        self.totp_service: TOTPService | None = None
        self.login_tracker: LoginAttemptTracker | None = None
        self.crypto_service: CryptoService | None = None
        self.repository: PasswordRepository | None = None
        self.password_service: PasswordService | None = None
        self.current_user: dict | None = None
        self.current_db_path: Path | None = None
        self.backup_service = BackupService(DATA_DIR)

        self._register_actions()
        logger.info("Application initialisée")

    # ------------------------------------------------------------------
    def _register_actions(self) -> None:
        self._add_action("logout", self.on_logout)
        self._add_action("switch_user", self.on_switch_user)
        self._add_action("manage_users", self.on_manage_users)
        self._add_action("manage_account", self.on_manage_account)
        self._add_action("change_own_password", self.on_change_own_password)
        self._add_action("change_own_email", self.on_change_own_email)
        self._add_action("reconfigure_2fa", self.on_reconfigure_2fa)
        self._add_action("import_csv", self.on_import_csv)
        self._add_action("manage_backups", self.on_manage_backups)
        self._add_action("open_trash", self.on_open_trash)
        self._add_action("about", self.on_about)

    def _add_action(self, name: str, handler) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", handler)
        self.add_action(action)

    # ------------------------------------------------------------------
    def do_activate(self):
        logger.info("Activation de l'application")
        if not self._branding_css_loaded:
            _install_branding_css()
            self._branding_css_loaded = True
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        users_db_path = DATA_DIR / "users.db"
        self.auth_service = AuthService(users_db_path)
        self.totp_service = TOTPService(DATA_DIR)
        self.login_tracker = LoginAttemptTracker(DATA_DIR / ".login_attempts.json")
        self.show_email_login()

    def show_email_login(self):
        """Affiche le dialogue de connexion par email (nouveau flux)."""
        self._secure_sensitive_files()
        if not self.auth_service or not self.login_tracker:
            raise RuntimeError("Services non initialisés")

        self.email_login_dialog = EmailLoginDialog(
            parent=None,
            auth_service=self.auth_service,
            login_tracker=self.login_tracker
        )
        self.email_login_dialog.set_application(self)
        self.email_login_dialog.connect('close-request', self._on_email_login_closed)
        self.email_login_dialog.present()

    def _on_email_login_closed(self, dialog):
        """Callback après fermeture du dialogue de connexion email."""
        user_info = dialog.get_user_info()
        master_password = dialog.get_master_password()

        if user_info and master_password:
            # Vérifier si email temporaire (migration)
            if self.auth_service and self.auth_service.is_migration_email(user_info['email']):
                self.show_update_email_dialog(user_info, master_password)
            else:
                # Vérifier si 2FA configuré
                if not user_info.get('totp_enabled'):
                    self.show_setup_2fa_dialog(user_info, master_password)
                else:
                    self.show_verify_totp_dialog(user_info, master_password)

        return False  # Propager l'événement close-request

    def show_update_email_dialog(self, user_info: dict, master_password: str):
        """Affiche le dialogue de mise à jour d'email (pour utilisateurs migrés).

        Args:
            user_info: Infos utilisateur avec email temporaire
            master_password: Master password (portée locale uniquement)
        """
        dialog = UpdateEmailDialog(
            parent=None,
            auth_service=self.auth_service,
            user_info=user_info,
            migration_required=True,
        )
        dialog.set_application(self)

        def on_closed(dlg):
            new_email = dlg.get_new_email()
            if new_email:
                # Mettre à jour user_info avec le nouvel email
                user_info['email'] = new_email
                # Forcer la configuration 2FA après mise à jour email
                self.show_setup_2fa_dialog(user_info, master_password)
            else:
                # Si l'utilisateur annule, retour au login
                logger.warning("Mise à jour email annulée pour %s", user_info.get('username'))
                self.show_email_login()
            return False

        dialog.connect('close-request', on_closed)
        dialog.present()

    def show_setup_2fa_dialog(self, user_info: dict, master_password: str):
        """Affiche le dialogue de configuration 2FA (OBLIGATOIRE).

        Args:
            user_info: Infos utilisateur
            master_password: Master password (portée locale uniquement)
        """
        dialog = Setup2FADialog(
            parent=None,
            totp_service=self.totp_service,
            auth_service=self.auth_service,
            user_info=user_info,
            reconfiguration=False,
        )
        dialog.set_application(self)

        def on_closed(dlg):
            if dlg.get_success():
                # 2FA configuré avec succès
                logger.info("2FA configuré avec succès pour %s", user_info.get('username'))
                # Charger le workspace
                self.on_user_authenticated(user_info, master_password)
            else:
                # Si annulé, politique stricte : fermer l'application
                logger.warning("Configuration 2FA annulée pour %s", user_info.get('username'))
                self._show_error_and_quit(
                    _("Configuration 2FA Requise"),
                    _("La double authentification est obligatoire pour utiliser l'application.")
                )
            return False

        dialog.connect('close-request', on_closed)
        dialog.present()

    def show_verify_totp_dialog(self, user_info: dict, master_password: str):
        """Affiche le dialogue de vérification TOTP.

        Args:
            user_info: Infos utilisateur avec 2FA activé
            master_password: Master password (portée locale uniquement)
        """
        dialog = VerifyTOTPDialog(
            parent=None,
            totp_service=self.totp_service,
            auth_service=self.auth_service,
            user_info=user_info
        )
        dialog.set_application(self)

        def on_closed(dlg):
            if dlg.get_verified():
                # TOTP vérifié avec succès
                logger.info("TOTP vérifié pour %s", user_info.get('username'))
                # Charger le workspace
                self.on_user_authenticated(user_info, master_password)
            else:
                # Retour au login
                logger.warning("Vérification TOTP échouée pour %s", user_info.get('username'))
                self.show_email_login()
            return False

        dialog.connect('close-request', on_closed)
        dialog.present()

    def _show_error_and_quit(self, title: str, message: str):
        """Affiche une erreur et ferme l'application.

        Args:
            title: Titre de l'erreur
            message: Message d'erreur
        """
        dialog = Adw.MessageDialog.new(None, title, message)
        dialog.add_response("ok", _("OK"))
        dialog.connect("response", lambda d, r: self.quit())
        dialog.present()

    # ANCIENNE MÉTHODE - Conservée pour compatibilité si nécessaire
    # def show_user_selection(self):
    #     self._secure_sensitive_files()
    #     if not self.auth_service:
    #         raise RuntimeError("AuthService non initialisé")
    #     self.selection_dialog = UserSelectionDialog(
    #         self, self.auth_service, self.on_user_authenticated
    #     )
    #     self.selection_dialog.set_application(self)
    #     self.selection_dialog.present()

    def _secure_sensitive_files(self):
        try:
            users_db = DATA_DIR / "users.db"
            if users_db.exists():
                users_db.chmod(0o600)

            # Sécuriser les fichiers de sécurité 2FA
            email_pepper = DATA_DIR / ".email_pepper"
            if email_pepper.exists():
                email_pepper.chmod(0o600)

            app_key = DATA_DIR / ".app_key"
            if app_key.exists():
                app_key.chmod(0o600)

            # Sécuriser les salt files (username ET uuid)
            for salt_file in DATA_DIR.glob("salt_*.bin"):
                salt_file.chmod(0o600)

            # Sécuriser les databases (username ET uuid)
            for db_file in DATA_DIR.glob("passwords_*.db"):
                db_file.chmod(0o600)
        except Exception as exc:
            logger.warning("Impossible de sécuriser certains fichiers: %s", exc)

    def on_user_authenticated(self, user_info: dict, master_password: str):
        """Appelé après authentification complète (Email + Password + TOTP).

        IMPORTANT: master_password reste UNIQUEMENT dans cette portée locale,
        jamais stocké dans une variable de classe.

        Args:
            user_info: Dictionnaire contenant les infos utilisateur (avec workspace_uuid)
            master_password: Master password (JAMAIS stocké en variable de classe)
        """
        try:
            # Utiliser workspace_uuid au lieu de username pour les fichiers
            workspace_uuid = user_info.get("workspace_uuid")
            username = user_info.get("username")  # Conservé pour l'affichage

            if not workspace_uuid:
                raise ValueError("workspace_uuid manquant dans user_info")

            self.current_user = user_info

            # Chemins basés sur workspace_uuid
            db_path = DATA_DIR / f"passwords_{workspace_uuid}.db"
            salt_path = DATA_DIR / f"salt_{workspace_uuid}.bin"

            # Charger ou créer le salt
            if salt_path.exists():
                salt = salt_path.read_bytes()
            else:
                # Créer un nouveau salt (cas d'un nouvel utilisateur)
                import secrets
                salt = secrets.token_bytes(32)
                salt_path.write_bytes(salt)
                salt_path.chmod(0o600)

            # Fermer l'ancien repository si existant
            self._close_repository()

            # Initialiser CryptoService avec le master_password (portée locale uniquement)
            self.crypto_service = CryptoService(master_password, salt)

            # Initialiser repository et password service
            self.repository = PasswordRepository(db_path, self.backup_service)
            self.password_service = PasswordService(
                self.repository, self.crypto_service
            )
            self.current_db_path = db_path

            # Fermer le dialogue de login si ouvert
            if self.email_login_dialog:
                self.email_login_dialog.close()
                self.email_login_dialog = None

            # Fermer la fenêtre principale si déjà ouverte (switch user)
            if self.window:
                self.window.close()

            # Ouvrir la fenêtre principale
            self.window = PasswordManagerWindow(self, self.password_service, user_info)
            self.window.present()
            logger.debug(
                "Fenêtre principale affichée pour %s (UUID: %s)", username, workspace_uuid[:8]
            )

        except Exception as exc:
            logger.exception(
                "Erreur lors de l'initialisation pour %s", user_info.get("username")
            )
            dialog = Adw.MessageDialog.new(None)
            dialog.set_heading(_("Erreur"))
            dialog.set_body(_("Impossible d'initialiser l'application: %s") % exc)
            dialog.add_response("ok", _("OK"))
            dialog.present()

    def on_logout(self, _action=None, _param=None):
        logger.info("Déconnexion demandée")
        if self.current_user and self.password_service and self.current_db_path:
            username = self.current_user["username"]
            if self.password_service.has_unsaved_changes():
                backup_path = self.backup_service.create_user_db_backup(username)
                if backup_path:
                    self.password_service.mark_as_saved()
                    if self.window and hasattr(self.window, "toast_overlay"):
                        toast = Adw.Toast.new(
                            _("💾 Sauvegarde créée: %s") % backup_path.name
                        )
                        toast.set_timeout(3)
                        self.window.toast_overlay.add_toast(toast)
        if self.window:
            self.window.close()
            self.window = None
        self._close_repository()
        self.current_user = None
        self.current_db_path = None
        self.show_email_login()

    def on_switch_user(self, action, param):
        self.on_logout(action, param)

    def on_manage_users(self, _action, _param):
        if (
            self.current_user
            and self.current_user["role"] == "admin"
            and self.window
            and self.auth_service
        ):
            ManageUsersDialog(
                self.window, self.auth_service, self.current_user["username"]
            ).present()

    def on_manage_account(self, _action, _param):
        """Ouvre la page centralisée de gestion du compte connecté."""
        if not (self.current_user and self.window and self.auth_service and self.totp_service):
            return

        dialog = ManageAccountDialog(
            parent=self.window,
            auth_service=self.auth_service,
            current_user=self.current_user,
            on_profile_updated=self._on_account_profile_updated,
            on_change_password=lambda: self.on_change_own_password(None, None),
            on_change_email=lambda: self.on_change_own_email(None, None),
            on_reconfigure_2fa=lambda: self.on_reconfigure_2fa(None, None),
        )
        dialog.present()

    def on_change_own_password(self, _action, _param):
        if self.current_user and self.window and self.auth_service:
            ChangeOwnPasswordDialog(
                self.window,
                self.auth_service,
                self.current_user["username"],
                self._change_master_password_and_reencrypt,
            ).present()

    def _reencrypt_workspace_entries(self, source_crypto: CryptoService, target_crypto: CryptoService) -> bool:
        """Réchiffre toutes les entrées du coffre de la clé source vers la clé cible."""
        if not self.repository:
            return False

        records = self.repository.list_entries(include_deleted=True)
        conn = self.repository.conn
        try:
            conn.execute("BEGIN")
            for record in records:
                if record.id is None:
                    continue

                plaintext_password = source_crypto.decrypt(record.password_data)
                plaintext_notes = (
                    source_crypto.decrypt(record.notes_data) if record.notes_data else None
                )

                encrypted_password = target_crypto.encrypt(plaintext_password)
                encrypted_notes = (
                    target_crypto.encrypt(plaintext_notes) if plaintext_notes else None
                )

                self.repository.update_encrypted_payload(
                    record.id,
                    encrypted_password,
                    encrypted_notes,
                )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            logger.exception("Echec du rechiffrement du coffre")
            return False

    def _change_master_password_and_reencrypt(self, old_password: str, new_password: str) -> bool:
        """Change le mot de passe maître et rechiffre le coffre associé."""
        if not (self.current_user and self.auth_service and self.password_service):
            return False

        workspace_uuid = self.current_user.get("workspace_uuid")
        if not workspace_uuid:
            logger.error("workspace_uuid manquant pour changement de mot de passe")
            return False

        salt_path = DATA_DIR / f"salt_{workspace_uuid}.bin"
        if not salt_path.exists():
            logger.error("Fichier salt introuvable: %s", salt_path)
            return False

        salt = salt_path.read_bytes()
        old_crypto = CryptoService(old_password, salt)
        new_crypto = CryptoService(new_password, salt)

        if not self._reencrypt_workspace_entries(old_crypto, new_crypto):
            return False

        if not self.auth_service.change_user_password(
            self.current_user["username"], old_password, new_password
        ):
            logger.error("Echec update auth, tentative rollback du rechiffrement")
            rollback_ok = self._reencrypt_workspace_entries(new_crypto, old_crypto)
            if not rollback_ok:
                logger.critical("Rollback rechiffrement impossible")
            return False

        self.crypto_service = new_crypto
        self.password_service.crypto = new_crypto
        return True

    def on_change_own_email(self, _action, _param):
        """Permet à l'utilisateur connecté de changer son email."""
        if not (self.current_user and self.window and self.auth_service):
            return

        dialog = UpdateEmailDialog(
            parent=self.window,
            auth_service=self.auth_service,
            user_info=self.current_user,
            migration_required=False,
        )

        def on_closed(dlg):
            new_email = dlg.get_new_email()
            if new_email and self.current_user:
                self.current_user["email"] = new_email
                if self.window and hasattr(self.window, "toast_overlay"):
                    toast = Adw.Toast.new(_("✅ Email mis à jour"))
                    toast.set_timeout(3)
                    self.window.toast_overlay.add_toast(toast)
            return False

        dialog.connect("close-request", on_closed)
        dialog.present()

    def on_reconfigure_2fa(self, _action, _param):
        """Permet à l'utilisateur connecté de relier un nouveau TOTP."""
        if not (self.current_user and self.window and self.auth_service and self.totp_service):
            return

        dialog = Setup2FADialog(
            parent=self.window,
            totp_service=self.totp_service,
            auth_service=self.auth_service,
            user_info=self.current_user,
            reconfiguration=True,
        )

        def on_closed(dlg):
            if dlg.get_success() and self.current_user:
                self.current_user["totp_enabled"] = True
                self.current_user["totp_confirmed"] = True
                if self.window and hasattr(self.window, "toast_overlay"):
                    toast = Adw.Toast.new(_("✅ Double authentification reconfigurée"))
                    toast.set_timeout(4)
                    self.window.toast_overlay.add_toast(toast)
            return False

        dialog.connect("close-request", on_closed)
        dialog.present()

    def _on_account_profile_updated(self, updates: dict) -> None:
        """Synchronise la fenêtre principale après mise à jour profil."""
        if not self.current_user:
            return

        self.current_user.update(updates)

        if self.window and hasattr(self.window, "refresh_account_profile"):
            self.window.refresh_account_profile(self.current_user)

    def on_import_csv(self, _action, _param):
        if self.window and self.password_service:
            csv_importer = CSVImporter()
            ImportCSVDialog(self.window, self.password_service, csv_importer).present()

    def on_manage_backups(self, _action, _param):
        if self.current_user and self.current_user["role"] == "admin" and self.window:
            BackupManagerDialog(
                self.window, self.backup_service, self.current_user["username"]
            ).present()

    def on_open_trash(self, _action, _param):
        """Ouvre le dialogue de la corbeille."""
        if self.window and self.password_service:
            from src.ui.dialogs.trash_dialog import TrashDialog

            TrashDialog(
                self.window,
                self.password_service,
                on_change_callback=lambda: self.window.load_entries()
                if self.window
                else None,
            ).present()

    def on_about(self, _action, _param):
        if self.window:
            show_about_dialog(self.window)

    def _close_repository(self):
        if self.password_service:
            self.password_service.close()
            self.password_service = None
            self.repository = None
        elif self.repository:
            self.repository.close()
            self.repository = None
        self.crypto_service = None


def _validate_password_rules(password: str, confirm: str) -> str | None:
    if not password:
        return _("Le mot de passe est requis")
    if len(password) < 8:
        return _("Le mot de passe doit contenir au moins 8 caractères")
    if password != confirm:
        return _("Les mots de passe ne correspondent pas")
    return None


class UserSelectionDialog(Adw.ApplicationWindow):
    """Fenêtre de sélection d'utilisateur."""

    def __init__(
        self, app, auth_service: AuthService, callback: Callable[[dict, str], None]
    ):
        super().__init__(application=app)
        self.set_default_size(450, 500)
        self.set_title(_("Sélection d'utilisateur"))
        self.auth_service = auth_service
        self.callback = callback

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_top(20)
        content.set_margin_bottom(40)

        title = Gtk.Label(label=_(__app_display_name__))
        title.set_css_classes(["title-1"])
        content.append(title)

        version_label = Gtk.Label(label=_("Version %s") % get_version())
        version_label.set_css_classes(["caption", "dim-label"])
        content.append(version_label)

        subtitle = Gtk.Label(label=_("Sélectionnez votre compte"))
        subtitle.set_css_classes(["title-4"])
        content.append(subtitle)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(["boxed-list"])
        self.users_listbox.connect("row-activated", self.on_user_selected)
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)

        self.load_users()
        box.append(content)
        self.set_content(box)

    def load_users(self):
        self.users_listbox.remove_all()
        users = self.auth_service.get_all_users()
        for username, role, _created_at, last_login in users:
            row = Gtk.ListBoxRow()
            row.username = username
            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            user_box.set_margin_start(12)
            user_box.set_margin_end(12)
            user_box.set_margin_top(12)
            user_box.set_margin_bottom(12)
            icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
            icon.set_pixel_size(32)
            user_box.append(icon)
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_hexpand(True)
            name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name_label = Gtk.Label(label=username, xalign=0)
            name_label.set_css_classes(["title-4"])
            name_box.append(name_label)

            badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            if role == "admin":
                admin_label = Gtk.Label(label=_("Admin"))
                admin_label.set_css_classes(["caption", "accent"])
                badges_box.append(admin_label)
            if badges_box.get_first_child() is not None:
                name_box.append(badges_box)
            info_box.append(name_box)
            if last_login:
                last_login_label = Gtk.Label(
                    label=_("Dernière connexion: %s") % last_login[:16], xalign=0
                )
                last_login_label.set_css_classes(["caption", "dim-label"])
                info_box.append(last_login_label)
            user_box.append(info_box)
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            user_box.append(arrow)
            row.set_child(user_box)
            self.users_listbox.append(row)

    def on_user_selected(self, _listbox, row):
        username = row.username
        LoginDialog(self, self.auth_service, username, self.callback).present()


class LoginDialog(Adw.Window):
    """Dialogue de connexion."""

    def __init__(
        self,
        parent,
        auth_service: AuthService,
        username: str,
        callback: Callable[[dict, str], None],
    ):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 250)
        self.set_title(_("Connexion"))
        self.auth_service = auth_service
        self.username = username
        self.callback = callback

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)
        box.set_valign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        icon.set_pixel_size(64)
        box.append(icon)

        title = Gtk.Label(label=_("Bonjour, %s") % username)
        title.set_css_classes(["title-2"])
        box.append(title)

        subtitle = Gtk.Label(label=_("Entrez votre mot de passe maître"))
        box.append(subtitle)

        version_label = Gtk.Label(label=_("v%s") % get_version())
        version_label.set_css_classes(["caption", "dim-label"])
        version_label.set_margin_top(10)

        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.connect("activate", lambda _x: self.on_login())
        box.append(self.password_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        box.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)

        cancel_btn = Gtk.Button(label=_("Retour"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)

        login_btn = Gtk.Button(label=_("Se connecter"))
        login_btn.set_css_classes(["suggested-action"])
        login_btn.connect("clicked", lambda _x: self.on_login())
        button_box.append(login_btn)

        box.append(button_box)
        box.append(version_label)
        self.set_content(box)
        self.password_entry.grab_focus()

    def on_login(self):
        password = self.password_entry.get_text()
        if not password:
            self.show_error(_("Veuillez entrer votre mot de passe"))
            return
        user_info = self.auth_service.authenticate(self.username, password)
        if user_info:
            self.callback(user_info, password)
            self.close()
        else:
            self.show_error(_("Mot de passe incorrect"))
            self.password_entry.set_text("")
            self.password_entry.grab_focus()

    def show_error(self, message: str):
        self.error_label.set_text(message)
        self.error_label.set_visible(True)


class CreateUserDialog(Adw.Window):
    """Création d'utilisateur (admin)."""

    def __init__(
        self, parent, auth_service: AuthService, on_success: Callable[[], None]
    ):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(450, 480)
        self.set_title(_("Créer un compte"))
        self.auth_service = auth_service
        self.on_success_callback = on_success

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_top(20)
        content.set_margin_bottom(40)

        title = Gtk.Label(label=_("Créer un nouveau compte"))
        title.set_css_classes(["title-2"])
        content.append(title)

        username_label = Gtk.Label(label=_("Nom d'utilisateur"), xalign=0)
        content.append(username_label)
        self.username_entry = Gtk.Entry()
        content.append(self.username_entry)

        password_label = Gtk.Label(label=_("Mot de passe maître"), xalign=0)
        content.append(password_label)
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.connect("changed", self.on_password_changed)
        content.append(self.password_entry)

        # Indicateur de force du mot de passe
        self.strength_label = Gtk.Label(label="")
        self.strength_label.set_css_classes(["caption"])
        self.strength_label.set_xalign(0)
        self.strength_label.set_margin_bottom(5)
        content.append(self.strength_label)

        confirm_label = Gtk.Label(label=_("Confirmer le mot de passe"), xalign=0)
        content.append(confirm_label)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        content.append(self.confirm_entry)

        role_label = Gtk.Label(label=_("Rôle"), xalign=0)
        content.append(role_label)
        role_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        role_box.set_margin_bottom(10)
        self.role_user = Gtk.CheckButton(label=_("Utilisateur"))
        self.role_user.set_active(True)
        role_box.append(self.role_user)
        self.role_admin = Gtk.CheckButton(label=_("Administrateur"))
        self.role_admin.set_group(self.role_user)
        role_box.append(self.role_admin)
        content.append(role_box)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        content.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Annuler"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        create_btn = Gtk.Button(label=_("Créer le compte"))
        create_btn.set_css_classes(["suggested-action"])
        create_btn.connect("clicked", self.on_create_clicked)
        button_box.append(create_btn)
        content.append(button_box)

        box.append(content)
        self.set_content(box)

    def on_password_changed(self, entry):
        """Affiche la force du mot de passe en temps réel."""
        from src.services.master_password_validator import MasterPasswordValidator

        password = entry.get_text()
        if len(password) == 0:
            self.strength_label.set_text("")
            self.strength_label.set_css_classes(["caption"])
            return

        _, _, score = MasterPasswordValidator.validate(password)
        strength = MasterPasswordValidator.get_strength_description(score)

        # Définir la couleur selon le score
        if score >= 80:
            self.strength_label.set_css_classes(["caption", "success"])
        elif score >= 60:
            self.strength_label.set_css_classes(["caption", "warning"])
        else:
            self.strength_label.set_css_classes(["caption", "error"])

        self.strength_label.set_text(f"Force : {strength} ({score}/100)")

    def on_create_clicked(self, _button):
        from src.services.master_password_validator import MasterPasswordValidator

        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()

        if len(username) < 3:
            self.show_error(
                _("Le nom d'utilisateur doit contenir au moins 3 caractères")
            )
            return

        # Validation avec le nouveau validateur
        is_valid, errors, score = MasterPasswordValidator.validate(password)

        if not is_valid:
            error_msg = _("Mot de passe trop faible :\n")
            error_msg += "\n".join(
                f"• {err}" for err in errors[:3]
            )  # Limiter à 3 erreurs
            self.show_error(error_msg)
            return

        if score < 60:
            # Avertissement mais on autorise quand même
            strength = MasterPasswordValidator.get_strength_description(score)
            error_msg = f"⚠️ Force du mot de passe : {strength} ({score}/100)\n"
            error_msg += _("Recommandé : au moins 60/100")
            self.show_error(error_msg)
            # On continue quand même si l'utilisateur insiste

        error = _validate_password_rules(password, confirm)
        if error:
            self.show_error(error)
            return
        role = "admin" if self.role_admin.get_active() else "user"
        if self.auth_service.create_user(username, password, role):
            self.on_success_callback()
            self.close()
        else:
            self.show_error(_("Ce nom d'utilisateur existe déjà"))

    def show_error(self, message: str):
        self.error_label.set_text(message)
        self.error_label.set_visible(True)


class ManageUsersDialog(Adw.Window):
    """Interface de gestion des utilisateurs."""

    def __init__(self, parent, auth_service: AuthService, current_username: str):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 500)
        self.set_title(_("Gestion des utilisateurs"))
        self.auth_service = auth_service
        self.current_username = current_username

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(20)
        content.set_margin_bottom(20)

        title = Gtk.Label(label=_("Gestion des utilisateurs"))
        title.set_css_classes(["title-2"])
        content.append(title)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(["boxed-list"])
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)

        self.load_users()

        create_user_btn = Gtk.Button(label=_("➕ Créer un nouvel utilisateur"))
        create_user_btn.set_css_classes(["suggested-action", "pill"])
        create_user_btn.connect("clicked", self.on_create_user)
        content.append(create_user_btn)

        box.append(content)
        self.set_content(box)

    def load_users(self):
        self.users_listbox.remove_all()
        users = self.auth_service.get_all_users()
        for username, role, created_at, _last_login in users:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            user_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            user_box.set_margin_start(12)
            user_box.set_margin_end(12)
            user_box.set_margin_top(12)
            user_box.set_margin_bottom(12)
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_hexpand(True)
            name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name_label = Gtk.Label(label=username, xalign=0)
            name_label.set_css_classes(["title-4"])
            name_box.append(name_label)

            badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            if role == "admin":
                admin_label = Gtk.Label(label=_("Admin"))
                admin_label.set_css_classes(["caption", "accent"])
                badges_box.append(admin_label)
            if badges_box.get_first_child() is not None:
                name_box.append(badges_box)
            info_box.append(name_box)
            created_label = Gtk.Label(label=_("Créé: %s") % created_at[:10], xalign=0)
            created_label.set_css_classes(["caption", "dim-label"])
            info_box.append(created_label)
            user_box.append(info_box)
            if username != self.current_username:
                action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                reset_btn = Gtk.Button(label=_("Réinitialiser MdP"))
                reset_btn.connect(
                    "clicked", lambda _b, u=username: self.on_reset_password(u)
                )
                action_box.append(reset_btn)
                delete_btn = Gtk.Button(label=_("Supprimer"))
                delete_btn.set_css_classes(["destructive-action"])
                delete_btn.connect(
                    "clicked", lambda _b, u=username: self.on_delete_user(u)
                )
                action_box.append(delete_btn)
                user_box.append(action_box)
            row.set_child(user_box)
            self.users_listbox.append(row)

    def on_create_user(self, _button):
        CreateUserDialog(self, self.auth_service, self.load_users).present()

    def on_reset_password(self, username: str):
        ResetPasswordDialog(self, self.auth_service, username).present()

    def on_delete_user(self, username: str):
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(_("Confirmer la suppression"))
        dialog.set_body(
            _(
                "Voulez-vous vraiment supprimer l'utilisateur '%s' ?\n\n"
                "Toutes ses données seront perdues."
            )
            % username
        )
        dialog.add_response("cancel", _("Annuler"))
        dialog.add_response("delete", _("Supprimer"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, r: self.delete_confirmed(r, username))
        dialog.present()

    def delete_confirmed(self, response: str, username: str):
        if response == "delete":
            if self.auth_service.delete_user(username):
                user_db = DATA_DIR / f"passwords_{username}.db"
                user_salt = DATA_DIR / f"salt_{username}.bin"
                if user_db.exists():
                    user_db.unlink()
                if user_salt.exists():
                    user_salt.unlink()
                self.load_users()


class ChangeOwnPasswordDialog(Adw.Window):
    """Dialogue pour changer son mot de passe maître."""

    def __init__(
        self,
        parent,
        auth_service: AuthService,
        username: str,
        on_change_master_password: Callable[[str, str], bool] | None = None,
    ):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(450, 400)
        self.set_title(_("Changer mon mot de passe"))
        self.auth_service = auth_service
        self.username = username
        self.on_change_master_password = on_change_master_password

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)

        title = Gtk.Label(label=_("Changer votre mot de passe maître"))
        title.set_css_classes(["title-3"])
        title.set_wrap(True)
        box.append(title)

        info = Gtk.Label(
            label=_(
                "Pour des raisons de sécurité, vous devez d'abord saisir votre mot de passe actuel."
            )
        )
        info.set_css_classes(["caption", "dim-label"])
        info.set_wrap(True)
        box.append(info)

        current_label = Gtk.Label(label=_("Mot de passe actuel"), xalign=0)
        current_label.set_css_classes(["title-4"])
        box.append(current_label)
        self.current_entry = Gtk.PasswordEntry()
        self.current_entry.set_show_peek_icon(True)
        box.append(self.current_entry)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(10)
        separator.set_margin_bottom(10)
        box.append(separator)

        new_label = Gtk.Label(label=_("Nouveau mot de passe"), xalign=0)
        new_label.set_css_classes(["title-4"])
        box.append(new_label)
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        box.append(self.password_entry)

        confirm_label = Gtk.Label(
            label=_("Confirmer le nouveau mot de passe"), xalign=0
        )
        box.append(confirm_label)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        box.append(self.confirm_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        box.append(self.error_label)

        self.progress_label = Gtk.Label(label="")
        self.progress_label.set_css_classes(["caption", "dim-label"])
        self.progress_label.set_visible(False)
        self.progress_label.set_wrap(True)
        box.append(self.progress_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Annuler"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        self.change_btn = Gtk.Button(label=_("Changer le mot de passe"))
        self.change_btn.set_css_classes(["suggested-action"])
        self.change_btn.connect("clicked", self.on_change_clicked)
        button_box.append(self.change_btn)
        box.append(button_box)

        self.set_content(box)

    def on_change_clicked(self, _button):
        current = self.current_entry.get_text()
        new_password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()
        self.error_label.set_visible(False)
        self.progress_label.set_visible(False)

        if not current:
            self.show_error(_("Veuillez saisir votre mot de passe actuel"))
            return
        if not self.auth_service.verify_user(self.username, current):
            self.show_error(_("❌ Mot de passe actuel incorrect"))
            self.current_entry.set_text("")
            self.current_entry.grab_focus()
            return
        error = _validate_password_rules(new_password, confirm)
        if error:
            self.show_error(error)
            return
        if new_password == current:
            self.show_error(
                _("Le nouveau mot de passe doit être différent de l'ancien")
            )
            return

        self.progress_label.set_text(
            _("🔐 Réchiffrement du coffre en cours… Cette opération peut prendre quelques instants.")
        )
        self.progress_label.set_visible(True)
        self.change_btn.set_sensitive(False)
        self.current_entry.set_sensitive(False)
        self.password_entry.set_sensitive(False)
        self.confirm_entry.set_sensitive(False)

        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

        changed = False
        if self.on_change_master_password:
            changed = self.on_change_master_password(current, new_password)
        else:
            changed = self.auth_service.change_user_password(
                self.username, current, new_password
            )

        if changed:
            dialog = Adw.MessageDialog.new(self)
            dialog.set_heading(_("✅ Succès"))
            dialog.set_body(_("Votre mot de passe maître a été changé avec succès."))
            dialog.add_response("ok", _("OK"))
            dialog.connect("response", lambda _d, _r: self.close())
            dialog.present()
        else:
            self.progress_label.set_visible(False)
            self.change_btn.set_sensitive(True)
            self.current_entry.set_sensitive(True)
            self.password_entry.set_sensitive(True)
            self.confirm_entry.set_sensitive(True)
            self.show_error(
                _("❌ Erreur lors du changement de mot de passe ou du rechiffrement du coffre")
            )

    def show_error(self, message: str):
        self.error_label.set_text(message)
        self.error_label.set_visible(True)


class ResetPasswordDialog(Adw.Window):
    """Réinitialisation de mot de passe (admin)."""

    def __init__(self, parent, auth_service: AuthService, username: str):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 300)
        self.set_title(_("Réinitialiser le mot de passe"))
        self.auth_service = auth_service
        self.username = username

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)

        title = Gtk.Label(label=_("Réinitialiser le mot de passe de '%s'") % username)
        title.set_css_classes(["title-3"])
        title.set_wrap(True)
        box.append(title)

        warning = Gtk.Label(
            label=_("⚠️ L'utilisateur devra utiliser ce nouveau mot de passe")
        )
        warning.set_css_classes(["caption"])
        warning.set_wrap(True)
        box.append(warning)

        password_label = Gtk.Label(label=_("Nouveau mot de passe"), xalign=0)
        box.append(password_label)
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        box.append(self.password_entry)

        confirm_label = Gtk.Label(label=_("Confirmer le mot de passe"), xalign=0)
        box.append(confirm_label)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        box.append(self.confirm_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(["error"])
        self.error_label.set_visible(False)
        box.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Annuler"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        reset_btn = Gtk.Button(label=_("Réinitialiser"))
        reset_btn.set_css_classes(["destructive-action"])
        reset_btn.connect("clicked", self.on_reset_clicked)
        button_box.append(reset_btn)
        box.append(button_box)

        self.set_content(box)

    def on_reset_clicked(self, _button):
        password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()
        error = _validate_password_rules(password, confirm)
        if error:
            self.show_error(error)
            return
        if self.auth_service.reset_user_password(self.username, password):
            dialog = Adw.MessageDialog.new(self)
            dialog.set_heading(_("Succès"))
            dialog.set_body(
                _("Le mot de passe de '%s' a été réinitialisé.") % self.username
            )
            dialog.add_response("ok", _("OK"))
            dialog.connect("response", lambda _d, _r: self.close())
            dialog.present()
        else:
            self.show_error(_("Erreur lors de la réinitialisation"))

    def show_error(self, message: str):
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
