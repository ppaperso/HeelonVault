"""Application Adwaita orchestrant les couches services et UI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from src.config.environment import get_data_directory
from src.config.logging_config import configure_logging
from src.i18n import _, init_i18n
from src.repositories.password_repository import PasswordRepository
from src.services.auth_service import AuthService
from src.services.backup_service import BackupService
from src.services.crypto_service import CryptoService
from src.services.csv_importer import CSVImporter
from src.services.password_service import PasswordService
from src.ui.dialogs.about_dialog import show_about_dialog
from src.ui.dialogs.backup_manager_dialog import BackupManagerDialog
from src.ui.dialogs.import_dialog import ImportCSVDialog
from src.ui.windows.main_window import PasswordManagerWindow
from src.version import get_version

import gi  # type: ignore[import]

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio  # type: ignore[attr-defined]  # noqa: E402

configure_logging()
init_i18n()
logger = logging.getLogger(__name__)
DATA_DIR = get_data_directory()


class PasswordManagerApplication(Adw.Application):
    """Application principale reliant services et interface graphique."""

    def __init__(self):
        super().__init__(
            application_id='org.example.passwordmanager',
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.window: Optional[PasswordManagerWindow] = None
        self.selection_dialog: Optional[UserSelectionDialog] = None
        self.auth_service: Optional[AuthService] = None
        self.crypto_service: Optional[CryptoService] = None
        self.repository: Optional[PasswordRepository] = None
        self.password_service: Optional[PasswordService] = None
        self.current_user: Optional[dict] = None
        self.current_db_path: Optional[Path] = None
        self.backup_service = BackupService(DATA_DIR)

        self._register_actions()
        logger.info("Application initialisée")

    # ------------------------------------------------------------------
    def _register_actions(self) -> None:
        self._add_action("logout", self.on_logout)
        self._add_action("switch_user", self.on_switch_user)
        self._add_action("manage_users", self.on_manage_users)
        self._add_action("change_own_password", self.on_change_own_password)
        self._add_action("import_csv", self.on_import_csv)
        self._add_action("manage_backups", self.on_manage_backups)
        self._add_action("about", self.on_about)

    def _add_action(self, name: str, handler) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", handler)
        self.add_action(action)

    # ------------------------------------------------------------------
    def do_activate(self):
        logger.info("Activation de l'application")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        users_db_path = DATA_DIR / "users.db"
        self.auth_service = AuthService(users_db_path)
        self.show_user_selection()

    def show_user_selection(self):
        self._secure_sensitive_files()
        if not self.auth_service:
            raise RuntimeError("AuthService non initialisé")
        self.selection_dialog = UserSelectionDialog(self, self.auth_service, self.on_user_authenticated)
        self.selection_dialog.set_application(self)
        self.selection_dialog.present()

    def _secure_sensitive_files(self):
        try:
            users_db = DATA_DIR / "users.db"
            if users_db.exists():
                users_db.chmod(0o600)
            for salt_file in DATA_DIR.glob("salt_*.bin"):
                salt_file.chmod(0o600)
            for db_file in DATA_DIR.glob("passwords_*.db"):
                db_file.chmod(0o600)
        except Exception as exc:
            logger.warning("Impossible de sécuriser certains fichiers: %s", exc)

    def on_user_authenticated(self, user_info: dict, master_password: str):
        try:
            username = user_info['username']
            self.current_user = user_info
            db_path = DATA_DIR / f"passwords_{username}.db"
            salt_path = DATA_DIR / f"salt_{username}.bin"

            if salt_path.exists():
                salt = salt_path.read_bytes()
            else:
                salt = user_info['salt']
                salt_path.write_bytes(salt)
                salt_path.chmod(0o600)

            self._close_repository()
            self.crypto_service = CryptoService(master_password, salt)
            self.repository = PasswordRepository(db_path)
            self.password_service = PasswordService(self.repository, self.crypto_service)
            self.current_db_path = db_path

            if self.selection_dialog:
                self.selection_dialog.close()
                self.selection_dialog = None
            if self.window:
                self.window.close()

            self.window = PasswordManagerWindow(self, self.password_service, user_info)
            self.window.present()
            logger.debug("Fenêtre principale affichée pour %s", username)
        except Exception as exc:
            logger.exception("Erreur lors de l'initialisation pour %s", user_info.get('username'))
            dialog = Adw.MessageDialog.new(None)
            dialog.set_heading(_("Erreur"))
            dialog.set_body(_("Impossible d'initialiser l'application: %s") % exc)
            dialog.add_response("ok", _("OK"))
            dialog.present()

    def on_logout(self, _action=None, _param=None):
        logger.info("Déconnexion demandée")
        if self.current_user and self.password_service and self.current_db_path:
            username = self.current_user['username']
            if self.password_service.has_unsaved_changes():
                backup_path = self.backup_service.create_user_db_backup(username)
                if backup_path:
                    self.password_service.mark_as_saved()
                    if self.window and hasattr(self.window, 'toast_overlay'):
                        toast = Adw.Toast.new(_("💾 Sauvegarde créée: %s") % backup_path.name)
                        toast.set_timeout(3)
                        self.window.toast_overlay.add_toast(toast)
        if self.window:
            self.window.close()
            self.window = None
        self._close_repository()
        self.current_user = None
        self.current_db_path = None
        self.show_user_selection()

    def on_switch_user(self, action, param):
        self.on_logout(action, param)

    def on_manage_users(self, _action, _param):
        if self.current_user and self.current_user['role'] == 'admin' and self.window and self.auth_service:
            ManageUsersDialog(self.window, self.auth_service, self.current_user['username']).present()

    def on_change_own_password(self, _action, _param):
        if self.current_user and self.window and self.auth_service:
            ChangeOwnPasswordDialog(self.window, self.auth_service, self.current_user['username']).present()

    def on_import_csv(self, _action, _param):
        if self.window and self.password_service:
            csv_importer = CSVImporter()
            ImportCSVDialog(self.window, self.password_service, csv_importer).present()

    def on_manage_backups(self, _action, _param):
        if self.current_user and self.current_user['role'] == 'admin' and self.window:
            BackupManagerDialog(self.window, self.backup_service, self.current_user['username']).present()

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


def _validate_password_rules(password: str, confirm: str) -> Optional[str]:
    if not password:
        return _("Le mot de passe est requis")
    if len(password) < 8:
        return _("Le mot de passe doit contenir au moins 8 caractères")
    if password != confirm:
        return _("Les mots de passe ne correspondent pas")
    return None


class UserSelectionDialog(Adw.ApplicationWindow):
    """Fenêtre de sélection d'utilisateur."""

    def __init__(self, app, auth_service: AuthService, callback: Callable[[dict, str], None]):
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

        title = Gtk.Label(label=_("🔐 Gestionnaire de mots de passe"))
        title.set_css_classes(['title-1'])
        content.append(title)

        version_label = Gtk.Label(label=_("Version %s") % get_version())
        version_label.set_css_classes(['caption', 'dim-label'])
        content.append(version_label)

        subtitle = Gtk.Label(label=_("Sélectionnez votre compte"))
        subtitle.set_css_classes(['title-4'])
        content.append(subtitle)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(200)
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(['boxed-list'])
        self.users_listbox.connect("row-activated", self.on_user_selected)
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)

        self.load_users()
        box.append(content)
        self.set_content(box)

    def load_users(self):
        self.users_listbox.remove_all()
        users = self.auth_service.get_all_users()
        for username, role, created_at, last_login in users:
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
            name_label.set_css_classes(['title-4'])
            name_box.append(name_label)
            if role == 'admin':
                admin_label = Gtk.Label(label=_("Admin"))
                admin_label.set_css_classes(['caption', 'accent'])
                name_box.append(admin_label)
            info_box.append(name_box)
            if last_login:
                last_login_label = Gtk.Label(label=_("Dernière connexion: %s") % last_login[:16], xalign=0)
                last_login_label.set_css_classes(['caption', 'dim-label'])
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

    def __init__(self, parent, auth_service: AuthService, username: str, callback: Callable[[dict, str], None]):
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
        title.set_css_classes(['title-2'])
        box.append(title)

        subtitle = Gtk.Label(label=_("Entrez votre mot de passe maître"))
        box.append(subtitle)

        version_label = Gtk.Label(label=_("v%s") % get_version())
        version_label.set_css_classes(['caption', 'dim-label'])
        version_label.set_margin_top(10)

        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.connect("activate", lambda _x: self.on_login())
        box.append(self.password_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        box.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)

        cancel_btn = Gtk.Button(label=_("Retour"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)

        login_btn = Gtk.Button(label=_("Se connecter"))
        login_btn.set_css_classes(['suggested-action'])
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

    def __init__(self, parent, auth_service: AuthService, on_success: Callable[[], None]):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(450, 420)
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
        title.set_css_classes(['title-2'])
        content.append(title)

        username_label = Gtk.Label(label=_("Nom d'utilisateur"), xalign=0)
        content.append(username_label)
        self.username_entry = Gtk.Entry()
        content.append(self.username_entry)

        password_label = Gtk.Label(label=_("Mot de passe maître"), xalign=0)
        content.append(password_label)
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        content.append(self.password_entry)

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
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        content.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Annuler"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        create_btn = Gtk.Button(label=_("Créer le compte"))
        create_btn.set_css_classes(['suggested-action'])
        create_btn.connect("clicked", self.on_create_clicked)
        button_box.append(create_btn)
        content.append(button_box)

        box.append(content)
        self.set_content(box)

    def on_create_clicked(self, _button):
        username = self.username_entry.get_text().strip()
        password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()

        if len(username) < 3:
            self.show_error(_("Le nom d'utilisateur doit contenir au moins 3 caractères"))
            return
        error = _validate_password_rules(password, confirm)
        if error:
            self.show_error(error)
            return
        role = 'admin' if self.role_admin.get_active() else 'user'
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
        title.set_css_classes(['title-2'])
        content.append(title)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.users_listbox = Gtk.ListBox()
        self.users_listbox.set_css_classes(['boxed-list'])
        scrolled.set_child(self.users_listbox)
        content.append(scrolled)

        self.load_users()

        create_user_btn = Gtk.Button(label=_("➕ Créer un nouvel utilisateur"))
        create_user_btn.set_css_classes(['suggested-action', 'pill'])
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
            name_label.set_css_classes(['title-4'])
            name_box.append(name_label)
            if role == 'admin':
                admin_label = Gtk.Label(label=_("Admin"))
                admin_label.set_css_classes(['caption', 'accent'])
                name_box.append(admin_label)
            info_box.append(name_box)
            created_label = Gtk.Label(label=_("Créé: %s") % created_at[:10], xalign=0)
            created_label.set_css_classes(['caption', 'dim-label'])
            info_box.append(created_label)
            user_box.append(info_box)
            if username != self.current_username:
                action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                reset_btn = Gtk.Button(label=_("Réinitialiser MdP"))
                reset_btn.connect("clicked", lambda _b, u=username: self.on_reset_password(u))
                action_box.append(reset_btn)
                delete_btn = Gtk.Button(label=_("Supprimer"))
                delete_btn.set_css_classes(['destructive-action'])
                delete_btn.connect("clicked", lambda _b, u=username: self.on_delete_user(u))
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
            _("Voulez-vous vraiment supprimer l'utilisateur '%s' ?\n\nToutes ses données seront perdues.") % username
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

    def __init__(self, parent, auth_service: AuthService, username: str):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(450, 400)
        self.set_title(_("Changer mon mot de passe"))
        self.auth_service = auth_service
        self.username = username

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)

        title = Gtk.Label(label=_("Changer votre mot de passe maître"))
        title.set_css_classes(['title-3'])
        title.set_wrap(True)
        box.append(title)

        info = Gtk.Label(label=_("Pour des raisons de sécurité, vous devez d'abord saisir votre mot de passe actuel."))
        info.set_css_classes(['caption', 'dim-label'])
        info.set_wrap(True)
        box.append(info)

        current_label = Gtk.Label(label=_("Mot de passe actuel"), xalign=0)
        current_label.set_css_classes(['title-4'])
        box.append(current_label)
        self.current_entry = Gtk.PasswordEntry()
        self.current_entry.set_show_peek_icon(True)
        box.append(self.current_entry)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(10)
        separator.set_margin_bottom(10)
        box.append(separator)

        new_label = Gtk.Label(label=_("Nouveau mot de passe"), xalign=0)
        new_label.set_css_classes(['title-4'])
        box.append(new_label)
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        box.append(self.password_entry)

        confirm_label = Gtk.Label(label=_("Confirmer le nouveau mot de passe"), xalign=0)
        box.append(confirm_label)
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_show_peek_icon(True)
        box.append(self.confirm_entry)

        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        self.error_label.set_wrap(True)
        box.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Annuler"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        change_btn = Gtk.Button(label=_("Changer le mot de passe"))
        change_btn.set_css_classes(['suggested-action'])
        change_btn.connect("clicked", self.on_change_clicked)
        button_box.append(change_btn)
        box.append(button_box)

        self.set_content(box)

    def on_change_clicked(self, _button):
        current = self.current_entry.get_text()
        new_password = self.password_entry.get_text()
        confirm = self.confirm_entry.get_text()

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
            self.show_error(_("Le nouveau mot de passe doit être différent de l'ancien"))
            return
        if self.auth_service.change_user_password(self.username, current, new_password):
            dialog = Adw.MessageDialog.new(self)
            dialog.set_heading(_("✅ Succès"))
            dialog.set_body(_("Votre mot de passe maître a été changé avec succès."))
            dialog.add_response("ok", _("OK"))
            dialog.connect("response", lambda _d, _r: self.close())
            dialog.present()
        else:
            self.show_error(_("❌ Erreur lors du changement de mot de passe"))

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
        title.set_css_classes(['title-3'])
        title.set_wrap(True)
        box.append(title)

        warning = Gtk.Label(label=_("⚠️ L'utilisateur devra utiliser ce nouveau mot de passe"))
        warning.set_css_classes(['caption'])
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
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        box.append(self.error_label)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label=_("Annuler"))
        cancel_btn.connect("clicked", lambda _x: self.close())
        button_box.append(cancel_btn)
        reset_btn = Gtk.Button(label=_("Réinitialiser"))
        reset_btn.set_css_classes(['destructive-action'])
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
            dialog.set_body(_("Le mot de passe de '%s' a été réinitialisé.") % self.username)
            dialog.add_response("ok", _("OK"))
            dialog.connect("response", lambda _d, _r: self.close())
            dialog.present()
        else:
            self.show_error(_("Erreur lors de la réinitialisation"))

    def show_error(self, message: str):
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
