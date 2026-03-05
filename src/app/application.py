"""Application Adwaita orchestrant les couches services et UI."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

import gi  # type: ignore[import]

from src.config.environment import get_data_directory, is_dev_mode
from src.config.logging_config import configure_logging
from src.i18n import _, init_i18n, set_language
from src.models.user_info import UserInfo, UserInfoUpdate
from src.repositories.password_repository import PasswordRepository
from src.services.auth_service import AuthService
from src.services.backup_service import BackupService
from src.services.crypto_service import CryptoService
from src.services.csv_exporter import CSVExporter
from src.services.csv_importer import CSVImporter
from src.services.login_attempt_tracker import LoginAttemptTracker
from src.services.password_service import PasswordService
from src.services.totp_service import TOTPService
from src.ui.dialogs.about_dialog import show_about_dialog
from src.ui.dialogs.backup_manager_dialog import BackupManagerDialog
from src.ui.dialogs.change_own_password_dialog import ChangeOwnPasswordDialog
from src.ui.dialogs.email_login_dialog import EmailLoginDialog
from src.ui.dialogs.export_dialog import ExportCSVDialog
from src.ui.dialogs.import_dialog import ImportCSVDialog
from src.ui.dialogs.manage_account_dialog import ManageAccountDialog
from src.ui.dialogs.manage_users_dialog import ManageUsersDialog
from src.ui.dialogs.setup_2fa_dialog import Setup2FADialog
from src.ui.dialogs.trash_dialog import TrashDialog
from src.ui.dialogs.update_email_dialog import UpdateEmailDialog
from src.ui.dialogs.verify_totp_dialog import VerifyTOTPDialog
from src.ui.windows.main_window import PasswordManagerWindow
from src.version import __app_id__

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

configure_logging()
init_i18n()
logger = logging.getLogger(__name__)
DATA_DIR = get_data_directory()
APP_ID = f"{__app_id__}.dev" if is_dev_mode() else __app_id__
APP_ICON_NAME = "heelonvault"
APP_ICON_CANDIDATES = ["heelonvault"]
APP_ICONS_ROOT = Path(__file__).resolve().parents[1] / "resources" / "icons" / "hicolor"
APP_ICON_SEARCH_DIRS = [
    APP_ICONS_ROOT / "48x48" / "apps",
    APP_ICONS_ROOT / "128x128" / "apps",
    APP_ICONS_ROOT / "256x256" / "apps",
]


def _install_branding_css() -> None:
    """Charge le thème Heelonys global dans GTK."""
    display = Gdk.Display.get_default()
    if not display:
        return
    css_path = Path(__file__).resolve().parents[1] / "resources" / "style.css"
    provider = Gtk.CssProvider()
    provider.load_from_path(str(css_path))
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class PasswordManagerApplication(Adw.Application):
    """Application principale reliant services et interface graphique."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        Gtk.Window.set_default_icon_name(APP_ICON_NAME)
        self._branding_css_loaded = False
        self.window: PasswordManagerWindow | None = None
        self.email_login_dialog: EmailLoginDialog | None = None
        self.auth_service: AuthService | None = None
        self.totp_service: TOTPService | None = None
        self.login_tracker: LoginAttemptTracker | None = None
        self.crypto_service: CryptoService | None = None
        self.repository: PasswordRepository | None = None
        self.password_service: PasswordService | None = None
        self.current_user: UserInfo | None = None
        self.current_db_path: Path | None = None
        self.backup_service = BackupService(DATA_DIR)

        self._register_actions()
        logger.info("Application initialized")

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
        self._add_action("export_csv", self.on_export_csv)
        self._add_action("manage_backups", self.on_manage_backups)
        self._add_action("open_trash", self.on_open_trash)
        self._add_action("about", self.on_about)

    def _add_action(self, name: str, handler) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", handler)
        self.add_action(action)

    # ------------------------------------------------------------------
    def do_activate(self) -> None:
        logger.info("Application activation")
        if not self._branding_css_loaded:
            _install_branding_css()
            self._branding_css_loaded = True

        display = Gdk.Display.get_default()
        if display:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            for icon_dir in APP_ICON_SEARCH_DIRS:
                icon_theme.add_search_path(str(icon_dir))
            resolved_icon_name = next(
                (name for name in APP_ICON_CANDIDATES if icon_theme.has_icon(name)),
                None,
            )
            if resolved_icon_name:
                Gtk.Window.set_default_icon_name(resolved_icon_name)
                if resolved_icon_name != APP_ICON_NAME:
                    logger.info(
                        "Application icon '%s' unavailable, using '%s'.",
                        APP_ICON_NAME,
                        resolved_icon_name,
                    )
            else:
                logger.warning(
                    "Application icon candidates %s not found in current icon theme or %s.",
                    APP_ICON_CANDIDATES,
                    APP_ICON_SEARCH_DIRS,
                )
        else:
            logger.warning(
                    "Unable to resolve application icon '%s' because no display is available.",
                    APP_ICON_NAME,
                )

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        users_db_path = DATA_DIR / "users.db"
        self.auth_service = AuthService(users_db_path)
        self.totp_service = TOTPService(DATA_DIR)
        self.login_tracker = LoginAttemptTracker(DATA_DIR / ".login_attempts.json")
        self.show_email_login()

    def show_email_login(self) -> None:
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

    def _on_email_login_closed(self, dialog: EmailLoginDialog) -> bool:
        """Callback après fermeture du dialogue de connexion email."""
        user_info = dialog.get_user_info()
        master_password = dialog.get_master_password()

        if user_info and master_password:
            set_language(user_info.get("language", "en"))
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

    def show_update_email_dialog(self, user_info: UserInfo, master_password: str) -> None:
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
                logger.warning("Email update canceled for %s", user_info.get('username'))
                self.show_email_login()
            return False

        dialog.connect('close-request', on_closed)
        dialog.present()

    def show_setup_2fa_dialog(self, user_info: UserInfo, master_password: str) -> None:
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
                logger.info("2FA configured successfully for %s", user_info.get('username'))
                # Charger le workspace
                self.on_user_authenticated(user_info, master_password)
            else:
                # Si annulé, politique stricte : fermer l'application
                logger.warning("2FA setup canceled for %s", user_info.get('username'))
                self._show_error_and_quit(
                    _("2FA setup required"),
                    _("Two-factor authentication is mandatory to use the application.")
                )
            return False

        dialog.connect('close-request', on_closed)
        dialog.present()

    def show_verify_totp_dialog(self, user_info: UserInfo, master_password: str) -> None:
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
                logger.info("TOTP verified for %s", user_info.get('username'))
                # Charger le workspace
                self.on_user_authenticated(user_info, master_password)
            else:
                # Retour au login
                logger.warning("TOTP verification failed for %s", user_info.get('username'))
                self.show_email_login()
            return False

        dialog.connect('close-request', on_closed)
        dialog.present()

    def _show_error_and_quit(self, title: str, message: str) -> None:
        """Affiche une erreur et ferme l'application.

        Args:
            title: Titre de l'erreur
            message: Message d'erreur
        """
        dialog = Adw.MessageDialog.new(None, title, message)
        dialog.add_response("ok", _("OK"))
        dialog.connect("response", lambda d, r: self.quit())
        dialog.present()

    def _secure_sensitive_files(self) -> None:
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
            logger.warning("Unable to secure some files: %s", exc)

    def on_user_authenticated(self, user_info: UserInfo, master_password: str) -> None:
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
                raise ValueError("missing workspace_uuid in user_info")

            self.current_user = user_info

            # Chemins basés sur workspace_uuid
            db_path = DATA_DIR / f"passwords_{workspace_uuid}.db"
            salt_path = DATA_DIR / f"salt_{workspace_uuid}.bin"

            # Charger ou créer le salt
            if salt_path.exists():
                salt = salt_path.read_bytes()
            else:
                # Créer un nouveau salt (cas d'un nouvel utilisateur)
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
                "Main window displayed for %s (UUID: %s)", username, workspace_uuid[:8]
            )

        except Exception as exc:
            logger.exception(
                "Error during initialization for %s", user_info.get("username")
            )
            dialog = Adw.MessageDialog.new(None)
            dialog.set_heading(_("Error"))
            dialog.set_body(_("Unable to initialize application: %s") % exc)
            dialog.add_response("ok", _("OK"))
            dialog.present()

    def on_logout(
        self,
        _action: Gio.SimpleAction | None = None,
        _param: object | None = None,
    ) -> None:
        logger.info("Logout requested")
        if self.current_user and self.password_service and self.current_db_path:
            username = self.current_user["username"]
            if self.password_service.has_unsaved_changes():
                backup_path = self.backup_service.create_user_db_backup(username)
                if backup_path:
                    self.password_service.mark_as_saved()
                    if self.window and hasattr(self.window, "toast_overlay"):
                        toast = Adw.Toast.new(
                            _("💾 Backup created: %s") % backup_path.name
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

    def on_switch_user(self, action: Gio.SimpleAction | None, param: object | None) -> None:
        self.on_logout(action, param)

    def on_manage_users(self, _action: Gio.SimpleAction | None, _param: object | None) -> None:
        if (
            self.current_user
            and self.current_user.get("role") == "admin"
            and self.window
            and self.auth_service
        ):
            ManageUsersDialog(
                self.window, self.auth_service, self.current_user["username"]
            ).present()

    def on_manage_account(
        self,
        _action: Gio.SimpleAction | None,
        _param: object | None,
    ) -> None:
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

    def on_change_own_password(
        self,
        _action: Gio.SimpleAction | None,
        _param: object | None,
    ) -> None:
        if self.current_user and self.window and self.auth_service:
            ChangeOwnPasswordDialog(
                self.window,
                self.auth_service,
                self.current_user["username"],
                self._change_master_password_and_reencrypt,
            ).present()

    def _reencrypt_workspace_entries(
        self,
        source_crypto: CryptoService,
        target_crypto: CryptoService,
    ) -> bool:
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
            logger.exception("Vault re-encryption failed")
            return False

    def _change_master_password_and_reencrypt(self, old_password: str, new_password: str) -> bool:
        """Change le mot de passe maître et rechiffre le coffre associé."""
        if not (self.current_user and self.auth_service and self.password_service):
            return False

        workspace_uuid = self.current_user.get("workspace_uuid")
        if not workspace_uuid:
            logger.error("Missing workspace_uuid for password change")
            return False

        salt_path = DATA_DIR / f"salt_{workspace_uuid}.bin"
        if not salt_path.exists():
            logger.error("Salt file not found: %s", salt_path)
            return False

        salt = salt_path.read_bytes()
        old_crypto = CryptoService(old_password, salt)
        new_crypto = CryptoService(new_password, salt)

        if not self._reencrypt_workspace_entries(old_crypto, new_crypto):
            return False

        if not self.auth_service.change_user_password(
            self.current_user["username"], old_password, new_password
        ):
            logger.error("Auth update failed, attempting re-encryption rollback")
            rollback_ok = self._reencrypt_workspace_entries(new_crypto, old_crypto)
            if not rollback_ok:
                logger.critical("Re-encryption rollback failed")
            return False

        self.crypto_service = new_crypto
        self.password_service.crypto = new_crypto
        return True

    def on_change_own_email(
        self,
        _action: Gio.SimpleAction | None,
        _param: object | None,
    ) -> None:
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
                    toast = Adw.Toast.new(_("✅ Email updated"))
                    toast.set_timeout(3)
                    self.window.toast_overlay.add_toast(toast)
            return False

        dialog.connect("close-request", on_closed)
        dialog.present()

    def on_reconfigure_2fa(
        self,
        _action: Gio.SimpleAction | None,
        _param: object | None,
    ) -> None:
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
                    toast = Adw.Toast.new(_("✅ Two-factor authentication reconfigured"))
                    toast.set_timeout(4)
                    self.window.toast_overlay.add_toast(toast)
            return False

        dialog.connect("close-request", on_closed)
        dialog.present()

    def _on_account_profile_updated(self, updates: UserInfoUpdate) -> None:
        """Synchronise la fenêtre principale après mise à jour profil."""
        if not self.current_user:
            return

        if "language" in updates:
            set_language(updates["language"])

        self.current_user.update(updates)

        if self.window and hasattr(self.window, "refresh_account_profile"):
            self.window.refresh_account_profile(updates)

    def on_import_csv(self, _action: Gio.SimpleAction | None, _param: object | None) -> None:
        if self.window and self.password_service:
            csv_importer = CSVImporter()
            ImportCSVDialog(self.window, self.password_service, csv_importer).present()

    def on_export_csv(self, _action: Gio.SimpleAction | None, _param: object | None) -> None:
        if self.window and self.password_service:
            csv_exporter = CSVExporter()
            ExportCSVDialog(self.window, self.password_service, csv_exporter).present()

    def on_manage_backups(self, _action: Gio.SimpleAction | None, _param: object | None) -> None:
        if self.current_user and self.current_user.get("role") == "admin" and self.window:
            BackupManagerDialog(
                self.window, self.backup_service, self.current_user["username"]
            ).present()

    def on_open_trash(self, _action: Gio.SimpleAction | None, _param: object | None) -> None:
        """Ouvre le dialogue de la corbeille."""
        if self.window and self.password_service:
            TrashDialog(
                self.window,
                self.password_service,
                on_change_callback=lambda: self.window.load_entries()
                if self.window
                else None,
            ).present()

    def on_about(self, _action: Gio.SimpleAction | None, _param: object | None) -> None:
        if self.window:
            show_about_dialog(self.window)

    def _close_repository(self) -> None:
        if self.password_service:
            self.password_service.close()
            self.password_service = None
            self.repository = None
        elif self.repository:
            self.repository.close()
            self.repository = None
        self.crypto_service = None
