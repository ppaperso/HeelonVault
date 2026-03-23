use std::env;
use std::fs;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::rc::Rc;
use std::sync::Arc;

use anyhow::{anyhow, Context, Result};
use gtk4::gdk;
use gtk4::gio;
use gtk4::glib;
use gtk4::prelude::*;
use libadwaita as adw;
use secrecy::{ExposeSecret, SecretBox};
use sqlx::sqlite::SqliteConnectOptions;
use sqlx::{Row, SqlitePool};
use tokio::runtime::Builder;
use tracing::info;
use tracing::warn;
use chrono::Local;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::fmt::time::FormatTime;
use tracing_subscriber::prelude::*;
use tracing_subscriber::EnvFilter;

use heelonvault_rust::config::constants::APP_ID;
use heelonvault_rust::errors::AppError;
use heelonvault_rust::repositories::secret_repository::SqlxSecretRepository;
use heelonvault_rust::repositories::user_repository::SqlxUserRepository;
use heelonvault_rust::repositories::vault_repository::SqlxVaultRepository;
use heelonvault_rust::services::auth_policy_service::{AuthPolicyService, SqlxAuthPolicyService};
use heelonvault_rust::services::auth_service::{AuthService, AuthServiceImpl};
use heelonvault_rust::services::backup_service::{BackupService, BackupServiceImpl};
use heelonvault_rust::services::crypto_service::CryptoServiceImpl;
use heelonvault_rust::services::import_service::ImportServiceImpl;
use heelonvault_rust::services::login_history_service::record_successful_login;
use heelonvault_rust::services::password_service::PasswordServiceImpl;
use heelonvault_rust::services::secret_service::SecretServiceImpl;
use heelonvault_rust::services::totp_service::SqliteTotpService;
use heelonvault_rust::services::user_service::{UserService, UserServiceImpl};
use heelonvault_rust::services::vault_service::{
	VaultKeyEnvelopeRepository, VaultService, VaultServiceImpl,
};
use heelonvault_rust::ui::dialogs::login_dialog::LoginDialog;
use heelonvault_rust::ui::windows::main_window::MainWindow;
use uuid::Uuid;

type VaultServiceHandle =
	VaultServiceImpl<SqlxVaultRepository, SqlxVaultEnvelopeRepository, CryptoServiceImpl>;
type SecretServiceHandle = SecretServiceImpl<SqlxSecretRepository, CryptoServiceImpl>;
type UserServiceHandle = UserServiceImpl<SqlxUserRepository, AuthServiceImpl<CryptoServiceImpl>>;
type TotpServiceHandle = SqliteTotpService<AuthServiceImpl<CryptoServiceImpl>, CryptoServiceImpl>;

struct SqlxVaultEnvelopeRepository {
	pool: SqlitePool,
}

impl SqlxVaultEnvelopeRepository {
	fn new(pool: SqlitePool) -> Self {
		Self { pool }
	}

	fn map_storage_err(context: &str, error: impl ToString) -> AppError {
		AppError::Storage(format!("{context}: {}", error.to_string()))
	}
}

impl VaultKeyEnvelopeRepository for SqlxVaultEnvelopeRepository {
	async fn get_vault_key_envelope(
		&self,
		vault_id: Uuid,
	) -> Result<Option<SecretBox<Vec<u8>>>, AppError> {
		let row_opt = sqlx::query("SELECT vault_key_envelope FROM vaults WHERE id = ?1")
			.bind(vault_id.to_string())
			.fetch_optional(&self.pool)
			.await
			.map_err(|error| Self::map_storage_err("get vault key envelope", error))?;

		match row_opt {
			Some(row) => {
				let envelope_bytes: Option<Vec<u8>> = row
					.try_get("vault_key_envelope")
					.map_err(|error| Self::map_storage_err("read vault key envelope", error))?;
				Ok(envelope_bytes.map(|bytes| SecretBox::new(Box::new(bytes))))
			}
			None => Ok(None),
		}
	}
}

struct AppContext {
	database_path: PathBuf,
	pool: SqlitePool,
	_crypto_service: CryptoServiceImpl,
	auth_service: Arc<AuthServiceImpl<CryptoServiceImpl>>,
	auth_policy_service: Arc<SqlxAuthPolicyService>,
	vault_service: Arc<VaultServiceHandle>,
	secret_service: Arc<SecretServiceHandle>,
	backup_service: Arc<BackupServiceImpl>,
	import_service: Arc<ImportServiceImpl>,
	user_service: Arc<UserServiceHandle>,
	totp_service: Arc<TotpServiceHandle>,
	admin_user_id: Uuid,
	admin_username: String,
	admin_identity_label: String,
	admin_master_key: Vec<u8>,
	_password_service: PasswordServiceImpl,
}

struct DailyLogFileWriter {
	log_dir: PathBuf,
	base_name: String,
	current_date: String,
	file: File,
}

impl DailyLogFileWriter {
	fn new(log_dir: PathBuf, base_name: impl Into<String>) -> Result<Self> {
		let base_name = base_name.into();
		let current_date = Self::date_stamp_local();
		let file = Self::open_file(&log_dir, &base_name, &current_date)?;
		Ok(Self {
			log_dir,
			base_name,
			current_date,
			file,
		})
	}

	/// Returns the current local date as `YYYYMMDD` (no hyphens).
	fn date_stamp_local() -> String {
		Local::now().format("%Y%m%d").to_string()
	}

	fn path_for(log_dir: &std::path::Path, base_name: &str, date_stamp: &str) -> PathBuf {
		log_dir.join(format!("{base_name}_{date_stamp}.log"))
	}

	fn open_file(log_dir: &std::path::Path, base_name: &str, date_stamp: &str) -> Result<File> {
		let log_path = Self::path_for(log_dir, base_name, date_stamp);
		OpenOptions::new()
			.create(true)
			.append(true)
			.open(&log_path)
			.with_context(|| format!("failed to open log file {}", log_path.display()))
	}

	fn rotate_if_needed(&mut self) -> std::io::Result<()> {
		let today = Self::date_stamp_local();
		if today == self.current_date {
			return Ok(());
		}

		let next_file = Self::open_file(&self.log_dir, &self.base_name, &today)
			.map_err(|error| std::io::Error::other(error.to_string()))?;
		self.file = next_file;
		self.current_date = today;
		Ok(())
	}
}

impl Write for DailyLogFileWriter {
	fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
		self.rotate_if_needed()?;
		self.file.write(buf)
	}

	fn flush(&mut self) -> std::io::Result<()> {
		self.file.flush()
	}
}

fn main() -> Result<()> {
	let _logging_guard = init_logging()?;
	register_resources()?;

	let runtime = Builder::new_multi_thread()
		.enable_all()
		.build()
		.context("failed to start tokio runtime")?;
	let runtime = Arc::new(runtime);
	info!("tokio runtime started");

	let app_context = Arc::new(runtime.block_on(initialize_app_context())?);

	let application = adw::Application::builder()
		.application_id(APP_ID)
		.flags(gio::ApplicationFlags::empty())
		.build();
	application.connect_startup(|_| {
		install_application_css();
		setup_icon_theme();
	});

	let runtime_handle = runtime.handle().clone();
	let runtime_for_activate = Arc::clone(&runtime);
	let app_context_for_activate = Arc::clone(&app_context);
	application.connect_activate(move |app| {
		let context = Arc::clone(&app_context_for_activate);
		let runtime_for_restore = Arc::clone(&runtime_for_activate);

		let main_window = Rc::new(MainWindow::new(
			app,
			runtime_handle.clone(),
			Arc::clone(&context.secret_service),
			Arc::clone(&context.vault_service),
			Arc::clone(&context.user_service),
			Arc::clone(&context.totp_service),
			Arc::clone(&context.auth_policy_service),
			Arc::clone(&context.backup_service),
			Arc::clone(&context.import_service),
			context.pool.clone(),
			context.database_path.clone(),
			context.admin_user_id,
			context.admin_master_key.clone(),
			context.admin_identity_label.clone(),
		));
		main_window.window().set_icon_name(Some("heelonvault"));
		main_window.window().set_visible(false);

		let app_for_login = app.clone();
		let app_for_restore = app.clone();
		let runtime_for_login = runtime_handle.clone();
		let context_for_login = Arc::clone(&context);
		let main_for_login = Rc::clone(&main_window);
		let present_login: Rc<dyn Fn()> = Rc::new(move || {
			main_for_login.deactivate_auto_lock();
			main_for_login.window().set_visible(false);

			let app_for_cancel = app_for_login.clone();
			let app_for_restore_completed = app_for_restore.clone();
			let main_for_success = Rc::clone(&main_for_login);
			let context_for_success = Arc::clone(&context_for_login);
			let context_for_restore = Arc::clone(&context_for_login);
			let runtime_for_success = runtime_for_login.clone();
			let runtime_for_restore_task = Arc::clone(&runtime_for_restore);
			let login_dialog = LoginDialog::new(
				&app_for_login,
				main_for_login.window(),
				runtime_for_login.clone(),
				Arc::clone(&context_for_login.auth_service),
				Arc::clone(&context_for_login.auth_policy_service),
				Arc::clone(&context_for_login.user_service),
				Arc::clone(&context_for_login.totp_service),
				move |backup_file_path, recovery_phrase, new_password| {
					let staging_path = build_restore_staging_path(&context_for_restore.database_path);
					cleanup_restore_staging_path(&staging_path).map_err(|error| {
						AppError::Storage(format!("failed to prepare restore staging area: {error}"))
					})?;

					context_for_restore.backup_service.import_hvb_with_recovery_key(
						backup_file_path.as_path(),
						&secrecy::SecretString::new(recovery_phrase.into_boxed_str()),
						staging_path.as_path(),
					)?;

					runtime_for_restore_task.block_on(async {
						apply_restored_login_password(
							staging_path.as_path(),
							new_password.as_str(),
						)
						.await
					}).map_err(|error| {
						AppError::Storage(format!("failed to update restored password envelope: {error}"))
					})?;

					runtime_for_restore_task.block_on(async {
						context_for_restore.pool.close().await;
					});

					promote_staged_restore(
						staging_path.as_path(),
						context_for_restore.database_path.as_path(),
					).map_err(|error| {
						AppError::Storage(format!("failed to promote restored database: {error}"))
					})?;
					context_for_restore.auth_service.signal_shutdown();
					Ok(())
				},
				move || {
					if let Err(error) = restart_current_process() {
						warn!(error = %error, "failed to restart application after restore");
					}
					app_for_restore_completed.quit();
				},
				move || {
					let preferred_language = runtime_for_success.block_on(async {
						context_for_success
							.user_service
							.get_user_profile(context_for_success.admin_user_id)
							.await
							.ok()
							.map(|user| user.preferred_language)
					});
					if let Some(language) = preferred_language {
						let _ = heelonvault_rust::i18n::set_language(language.as_str());
					}

					main_for_success
						.set_session_master_key(context_for_success.admin_master_key.clone());
					main_for_success.refresh_entries();

					let runtime_for_history = runtime_for_success.clone();
					let pool_for_history = context_for_success.pool.clone();
					let user_id_for_history = context_for_success.admin_user_id;
					std::thread::spawn(move || {
						let device_info = format!("{} / GTK4 Desktop", std::env::consts::OS);
						let _ = runtime_for_history.block_on(async move {
							let _ = record_successful_login(
								&pool_for_history,
								user_id_for_history,
								None,
								Some(device_info.as_str()),
							)
							.await;
						});
					});

					let (sender, receiver) = tokio::sync::oneshot::channel();
					let runtime_for_task = runtime_for_success.clone();
					let policy_for_task = Arc::clone(&context_for_success.auth_policy_service);
					let username_for_task = context_for_success.admin_username.clone();
					std::thread::spawn(move || {
						let result = runtime_for_task.block_on(async move {
							policy_for_task.get_auto_lock_delay(username_for_task.as_str()).await
						});
						let _ = sender.send(result);
					});

					let main_for_delay = Rc::clone(&main_for_success);
					glib::MainContext::default().spawn_local(async move {
						if let Ok(Ok(delay_mins)) = receiver.await {
							main_for_delay.set_auto_lock_timeout(delay_mins as u64);
						}
					});

					main_for_success.window().present();
					main_for_success.activate_auto_lock();
				},
				move || {
					app_for_cancel.quit();
				},
			);
			login_dialog.present();
		});

		let main_for_logout = Rc::clone(&main_window);
		let present_for_logout = Rc::clone(&present_login);
		main_window.set_on_logout(Rc::new(move || {
			main_for_logout.clear_sensitive_session();
			present_for_logout.as_ref()();
		}));

		let main_for_auto_lock = Rc::clone(&main_window);
		main_window.set_on_auto_lock(Rc::new(move || {
			main_for_auto_lock.trigger_logout();
		}));

		present_login.as_ref()();
	});

	let _exit_code = application.run();
	Ok(())
}

fn register_resources() -> Result<()> {
	gio::resources_register_include!("heelonvault.gresource")
		.context("failed to register compiled resources")?;
	Ok(())
}

fn setup_icon_theme() {
	gtk4::Window::set_default_icon_name("heelonvault");
	if let Some(display) = gdk::Display::default() {
		let theme = gtk4::IconTheme::for_display(&display);
		theme.add_resource_path("/com/heelonvault/rust");
	}
}

fn install_application_css() {
	let provider = gtk4::CssProvider::new();
	provider.load_from_resource("/com/heelonvault/rust/style.css");

	if let Some(display) = gdk::Display::default() {
		gtk4::style_context_add_provider_for_display(
			&display,
			&provider,
			gtk4::STYLE_PROVIDER_PRIORITY_APPLICATION,
		);
	}
}

/// Custom timer for `tracing_subscriber` that formats each log record timestamp
/// as RFC 3339 in the system's local timezone (e.g. `2026-03-17T14:40:06+01:00`).
/// Using `chrono::Local` avoids the `SAFETY` caveats of `time::UtcOffset::current_local_offset()`
/// in a multi-threaded context.
struct LocalRfc3339Timer;

impl FormatTime for LocalRfc3339Timer {
	fn format_time(&self, w: &mut tracing_subscriber::fmt::format::Writer<'_>) -> std::fmt::Result {
		write!(w, "{}", Local::now().to_rfc3339())
	}
}

fn init_logging() -> Result<WorkerGuard> {
	const SENSITIVE_TARGETS: &[&str] = &[
		"vault::crypto",
		"auth::session",
		"heelonvault_rust::services::crypto_service",
		"heelonvault_rust::services::secret_service",
		"heelonvault_rust::services::auth_service",
		"heelonvault_rust::services::vault_service",
	];

	let default_level = if cfg!(debug_assertions) {
		"debug"
	} else {
		"info"
	};
	let base_filter_spec = env::var("RUST_LOG")
		.ok()
		.filter(|value| !value.trim().is_empty())
		.or_else(|| {
			env::var("HEELONVAULT_LOG_LEVEL")
				.ok()
				.filter(|value| !value.trim().is_empty())
		})
		.unwrap_or_else(|| default_level.to_string());

	let mut filter_spec = base_filter_spec.clone();
	for target in SENSITIVE_TARGETS {
		if !base_filter_spec.contains(target) {
			filter_spec.push(',');
			filter_spec.push_str(target);
			filter_spec.push_str("=warn");
		}
	}

	let env_filter = EnvFilter::try_new(filter_spec.clone())
		.with_context(|| format!("invalid log level/filter: {filter_spec}"))?;

	let log_dir = env::var("HEELONVAULT_LOG_DIR")
		.ok()
		.filter(|value| !value.trim().is_empty())
		.unwrap_or_else(|| "logs".to_string());
	let log_dir_path = PathBuf::from(&log_dir);
	fs::create_dir_all(&log_dir_path)
		.with_context(|| format!("failed to create log directory {}", log_dir_path.display()))?;

	let rolling_writer = DailyLogFileWriter::new(log_dir_path.clone(), "heelonvault")?;
	let (file_writer, guard) = tracing_appender::non_blocking(rolling_writer);

	let is_debug_logging = base_filter_spec.to_ascii_lowercase().contains("debug");
	let is_dev_mode = cfg!(debug_assertions);

	if is_dev_mode {
		let console_layer = tracing_subscriber::fmt::layer()
			.pretty()
			.with_writer(std::io::stdout)
			.with_target(false)
			.with_timer(LocalRfc3339Timer);
		let file_layer = tracing_subscriber::fmt::layer()
			.json()
			.with_ansi(false)
			.with_writer(file_writer)
			.with_target(is_debug_logging)
			.with_line_number(is_debug_logging)
			.with_file(is_debug_logging)
			.with_timer(LocalRfc3339Timer);

		tracing_subscriber::registry()
			.with(env_filter)
			.with(console_layer)
			.with(file_layer)
			.try_init()
			.map_err(|error| anyhow!("failed to initialize tracing subscriber: {error}"))?;
	} else {
		let console_layer = tracing_subscriber::fmt::layer()
			.compact()
			.with_writer(std::io::stdout)
			.with_target(false)
			.with_timer(LocalRfc3339Timer);
		let file_layer = tracing_subscriber::fmt::layer()
			.json()
			.with_ansi(false)
			.with_writer(file_writer)
			.with_target(is_debug_logging)
			.with_line_number(is_debug_logging)
			.with_file(is_debug_logging)
			.with_timer(LocalRfc3339Timer);

		tracing_subscriber::registry()
			.with(env_filter)
			.with(console_layer)
			.with(file_layer)
			.try_init()
			.map_err(|error| anyhow!("failed to initialize tracing subscriber: {error}"))?;
	}

	Ok(guard)
}

async fn initialize_app_context() -> Result<AppContext> {
	let database_path = resolve_database_path()?;
	if let Some(parent) = database_path.parent() {
		if !parent.as_os_str().is_empty() {
			fs::create_dir_all(parent).with_context(|| {
				format!("failed to create database directory {}", parent.display())
			})?;
		}
	}

	let connect_options = SqliteConnectOptions::new()
		.filename(&database_path)
		.create_if_missing(true);

	let pool = SqlitePool::connect_with(connect_options)
		.await
		.with_context(|| {
			format!(
				"failed to open sqlite database at {}",
				database_path.display()
			)
		})?;

	sqlx::migrate!()
		.run(&pool)
		.await
		.context("failed to run sqlx migrations")?;
	info!(database = %database_path.display(), "sqlx migrations applied successfully");

	let crypto_service = CryptoServiceImpl::default();
	let auth_service = Arc::new(AuthServiceImpl::new(CryptoServiceImpl::default()));
	let auth_policy_service = Arc::new(SqlxAuthPolicyService::new(pool.clone()));
	let vault_service = Arc::new(VaultServiceImpl::new(
		SqlxVaultRepository::new(pool.clone()),
		SqlxVaultEnvelopeRepository::new(pool.clone()),
		CryptoServiceImpl::default(),
	));
	let secret_service = Arc::new(SecretServiceImpl::new(
		SqlxSecretRepository::new(pool.clone()),
		CryptoServiceImpl::default(),
	));
    let user_service = Arc::new(UserServiceImpl::new(
        SqlxUserRepository::new(pool.clone()),
        Arc::clone(&auth_service),
    ));

	let (admin_user_id, admin_master_key) = ensure_dev_admin_context(
		&pool,
		&auth_service,
		Arc::clone(&vault_service),
	)
	.await?;

	let admin_row = sqlx::query(
		"SELECT username, COALESCE(NULLIF(display_name, ''), username) AS identity_label FROM users WHERE id = ?1",
	)
	.bind(admin_user_id.to_string())
	.fetch_one(&pool)
	.await
	.context("failed to resolve admin identity label")?;

	let admin_username: String = admin_row
		.try_get("username")
		.context("failed to read admin username")?;
	let admin_identity_label: String = admin_row
		.try_get("identity_label")
		.context("failed to read admin identity label")?;

	let password_service = PasswordServiceImpl::new();
	let backup_service = Arc::new(BackupServiceImpl::new());
	let import_service = Arc::new(ImportServiceImpl::new());
	let totp_service = Arc::new(SqliteTotpService::new(
		pool.clone(),
		Arc::clone(&auth_service),
		CryptoServiceImpl::default(),
		"HeelonVault",
	));

	info!("all services are initialized and ready");

	Ok(AppContext {
		database_path,
		pool,
		_crypto_service: crypto_service,
		auth_service,
		auth_policy_service,
		vault_service,
		secret_service,
		backup_service,
		import_service,
		user_service,
		totp_service,
		admin_user_id,
		admin_username,
		admin_identity_label,
		admin_master_key,
		_password_service: password_service,
	})
}

fn resolve_database_path() -> Result<PathBuf> {
	if let Ok(path_raw) = env::var("HEELONVAULT_DB_PATH") {
		let trimmed = path_raw.trim();
		if !trimmed.is_empty() {
			return Ok(PathBuf::from(trimmed));
		}
	}

	let current_dir = env::current_dir().context("failed to resolve current directory")?;
	Ok(resolve_default_database_path(&current_dir))
}

fn resolve_default_database_path(current_dir: &Path) -> PathBuf {
	let db_name = "heelonvault-rust-dev.db";
	if current_dir.file_name().is_some_and(|name| name == "rust") {
		if let Some(project_root) = current_dir.parent() {
			return project_root.join("data").join(db_name);
		}
	}

	current_dir.join("data").join(db_name)
}

#[cfg(test)]
mod tests {
	use super::resolve_default_database_path;
	use std::path::Path;

	#[test]
	fn default_database_path_uses_root_data_when_cwd_is_project_root() {
		let project_root = Path::new("/tmp/heelonvault");
		assert_eq!(
			resolve_default_database_path(project_root),
			project_root.join("data").join("heelonvault-rust-dev.db")
		);
	}

	#[test]
	fn default_database_path_uses_parent_data_when_cwd_is_rust_dir() {
		let rust_dir = Path::new("/tmp/heelonvault/rust");
		assert_eq!(
			resolve_default_database_path(rust_dir),
			Path::new("/tmp/heelonvault")
				.join("data")
				.join("heelonvault-rust-dev.db")
		);
	}
}

fn build_restore_staging_path(database_path: &Path) -> PathBuf {
	let file_name = database_path
		.file_name()
		.and_then(|value| value.to_str())
		.unwrap_or("heelonvault-rust.db");
	database_path.with_file_name(format!("{file_name}.restore.tmp"))
}

fn cleanup_restore_staging_path(staging_path: &Path) -> Result<()> {
	if staging_path.exists() {
		fs::remove_file(staging_path).with_context(|| {
			format!("failed to remove previous staged restore {}", staging_path.display())
		})?;
	}

	let staging_old_path = staging_path.with_extension("old");
	if staging_old_path.exists() {
		fs::remove_file(&staging_old_path).with_context(|| {
			format!(
				"failed to remove previous staged restore backup {}",
				staging_old_path.display()
			)
		})?;
	}

	Ok(())
}

fn promote_staged_restore(staging_path: &Path, database_path: &Path) -> Result<()> {
	if let Some(parent) = database_path.parent() {
		if !parent.as_os_str().is_empty() {
			fs::create_dir_all(parent).with_context(|| {
				format!("failed to create database directory {}", parent.display())
			})?;
		}
	}

	let old_database_path = database_path.with_extension("old");
	if old_database_path.exists() {
		fs::remove_file(&old_database_path).with_context(|| {
			format!(
				"failed to remove previous rotated database {}",
				old_database_path.display()
			)
		})?;
	}

	let original_database_was_present = database_path.exists();
	if original_database_was_present {
		fs::rename(database_path, &old_database_path).with_context(|| {
			format!(
				"failed to rotate current database to {}",
				old_database_path.display()
			)
		})?;
	}

	if let Err(error) = fs::rename(staging_path, database_path) {
		if original_database_was_present && old_database_path.exists() {
			let _ = fs::rename(&old_database_path, database_path);
		}
		return Err(anyhow!(
			"failed to promote staged restore {} to {}: {}",
			staging_path.display(),
			database_path.display(),
			error
		));
	}

	Ok(())
}

fn restart_current_process() -> Result<()> {
	let current_executable = env::current_exe().context("failed to resolve current executable")?;
	let args: Vec<String> = env::args().skip(1).collect();
	Command::new(&current_executable)
		.args(args)
		.spawn()
		.with_context(|| {
			format!(
				"failed to restart application from {}",
				current_executable.display()
			)
		})?;
	Ok(())
}

async fn apply_restored_login_password(database_path: &Path, new_password: &str) -> Result<()> {
	let connect_options = SqliteConnectOptions::new()
		.filename(database_path)
		.create_if_missing(false);
	let pool = SqlitePool::connect_with(connect_options)
		.await
		.with_context(|| {
			format!(
				"failed to open restored database at {}",
				database_path.display()
			)
		})?;

	let selected_user = sqlx::query(
		"SELECT username FROM users ORDER BY CASE WHEN username = 'admin' THEN 0 ELSE 1 END, rowid LIMIT 1",
	)
	.fetch_optional(&pool)
	.await
	.context("failed to resolve restored user for password reset")?
	.ok_or_else(|| anyhow!("restored database does not contain any user"))?;

	let username: String = selected_user
		.try_get("username")
		.context("failed to read restored username")?;

	let auth_service = AuthServiceImpl::new(CryptoServiceImpl::default());
	auth_service
		.create_user(
			username.as_str(),
			SecretBox::new(Box::new(new_password.as_bytes().to_vec())),
		)
		.await
		.map_err(|error| anyhow!("failed to stage restored password envelope: {error}"))?;

	let password_envelope = auth_service
		.get_password_envelope(username.as_str())
		.await
		.map_err(|error| anyhow!("failed to export restored password envelope: {error}"))?;

	sqlx::query("UPDATE users SET password_envelope = ?1 WHERE username = ?2")
		.bind(password_envelope.expose_secret().as_slice())
		.bind(username.as_str())
		.execute(&pool)
		.await
		.context("failed to persist restored password envelope")?;

	let _ = sqlx::query("DELETE FROM auth_policy").execute(&pool).await;
	pool.close().await;
	Ok(())
}

async fn ensure_dev_admin_context(
	pool: &SqlitePool,
	auth_service: &Arc<AuthServiceImpl<CryptoServiceImpl>>,
	vault_service: Arc<VaultServiceHandle>,
) -> Result<(Uuid, Vec<u8>)> {
	let (admin_user_id, password_envelope): (Uuid, Option<Vec<u8>>) = match sqlx::query("SELECT id, password_envelope FROM users WHERE username = ?1")
		.bind("admin")
		.fetch_optional(pool)
		.await
		.context("failed to query admin user")?
	{
		Some(row) => {
			let id_raw: String = row
				.try_get("id")
				.context("failed to read admin user id")?;
			let parsed_id = Uuid::parse_str(&id_raw).context("failed to parse admin user id")?;
			let envelope: Option<Vec<u8>> = row
				.try_get("password_envelope")
				.context("failed to read admin password envelope")?;
			(parsed_id, envelope)
		}
		None => {
			let user_id = Uuid::new_v4();
			sqlx::query("INSERT INTO users (id, username, role) VALUES (?1, ?2, ?3)")
				.bind(user_id.to_string())
				.bind("admin")
				.bind("admin")
				.execute(pool)
				.await
				.context("failed to insert admin user row")?;
			(user_id, None)
		}
	};

	if let Some(envelope) = password_envelope {
		auth_service
			.upsert_password_envelope("admin", SecretBox::new(Box::new(envelope)))
			.await
			.map_err(|error| anyhow!("failed to load persisted admin auth credentials: {error}"))?;
		info!("admin credentials loaded from password envelope");
	} else {
		// TODO: remove before release
		auth_service
			.create_user("admin", SecretBox::new(Box::new(b"Admin1234!".to_vec())))
			.await
			.map_err(|error| anyhow!("failed to create default development admin user: {error}"))?;

		let generated_envelope = auth_service
			.get_password_envelope("admin")
			.await
			.map_err(|error| anyhow!("failed to export admin password envelope: {error}"))?;

		sqlx::query("UPDATE users SET password_envelope = ?1 WHERE id = ?2")
			.bind(generated_envelope.expose_secret().as_slice())
			.bind(admin_user_id.to_string())
			.execute(pool)
			.await
			.context("failed to persist admin password envelope")?;
		info!("admin password envelope persisted");
	}

	let admin_master_key = vec![0x41_u8; 32];
	let vaults = vault_service
		.list_user_vaults(admin_user_id)
		.await
		.context("failed to list admin vaults")?;
	if vaults.is_empty() {
		// TODO: remove before release
		let _vault = vault_service
			.create_vault(
				admin_user_id,
				"Admin",
				SecretBox::new(Box::new(admin_master_key.clone())),
			)
			.await
			.context("failed to create default admin vault")?;
		info!("development admin vault created");
	}

	Ok((admin_user_id, admin_master_key))
}
