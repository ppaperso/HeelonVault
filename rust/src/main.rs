use std::env;
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::{anyhow, Context, Result};
use gtk4::gdk;
use gtk4::gio;
use gtk4::prelude::*;
use libadwaita as adw;
use secrecy::SecretBox;
use sqlx::sqlite::SqliteConnectOptions;
use sqlx::{Row, SqlitePool};
use tokio::runtime::Builder;
use tracing::info;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::fmt::time::UtcTime;
use tracing_subscriber::prelude::*;
use tracing_subscriber::EnvFilter;

use heelonvault_rust::config::constants::APP_ID;
use heelonvault_rust::errors::AppError;
use heelonvault_rust::repositories::secret_repository::SqlxSecretRepository;
use heelonvault_rust::repositories::user_repository::SqlxUserRepository;
use heelonvault_rust::repositories::vault_repository::SqlxVaultRepository;
use heelonvault_rust::services::auth_service::{AuthService, AuthServiceImpl};
use heelonvault_rust::services::backup_service::BackupServiceImpl;
use heelonvault_rust::services::crypto_service::CryptoServiceImpl;
use heelonvault_rust::services::password_service::PasswordServiceImpl;
use heelonvault_rust::services::secret_service::SecretServiceImpl;
use heelonvault_rust::services::user_service::UserServiceImpl;
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
	_pool: SqlitePool,
	_crypto_service: CryptoServiceImpl,
	auth_service: Arc<AuthServiceImpl<CryptoServiceImpl>>,
	vault_service: Arc<VaultServiceHandle>,
	secret_service: Arc<SecretServiceHandle>,
	user_service: Arc<UserServiceHandle>,
	admin_user_id: Uuid,
	admin_identity_label: String,
	admin_master_key: Vec<u8>,
	_password_service: PasswordServiceImpl,
	_backup_service: BackupServiceImpl,
}

fn main() -> Result<()> {
	let _logging_guard = init_logging()?;
	register_resources()?;

	let runtime = Builder::new_multi_thread()
		.enable_all()
		.build()
		.context("failed to start tokio runtime")?;
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
	let app_context_for_activate = Arc::clone(&app_context);
	application.connect_activate(move |app| {
		let context = Arc::clone(&app_context_for_activate);

		let window = MainWindow::new(
			app,
			runtime_handle.clone(),
			Arc::clone(&context.secret_service),
			Arc::clone(&context.vault_service),
			Arc::clone(&context.user_service),
			context.admin_user_id,
			context.admin_master_key.clone(),
			context.admin_identity_label.clone(),
		)
		.into_inner();
		window.set_icon_name(Some("heelonvault"));
		window.set_visible(false);

		let app_for_cancel = app.clone();
		let window_for_success = window.clone();
		let login_dialog = LoginDialog::new(
			app,
			&window,
			runtime_handle.clone(),
			Arc::clone(&context.auth_service),
			false,
			move || {
				window_for_success.present();
			},
			move || {
				app_for_cancel.quit();
			},
		);
		login_dialog.present();
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
	provider.load_from_data(
		r#"
		window.app-window,
		window {
			background:
				radial-gradient(circle at top left, rgba(164, 223, 207, 0.55), transparent 42%),
				radial-gradient(circle at top right, rgba(111, 211, 180, 0.22), transparent 36%),
				#F3F6F3;
			color: #2C3E50;
		}

		.login-shell {
			min-width: 460px;
		}

		.login-panel {
			padding: 12px;
		}

		.login-hero,
		.login-card {
			border-radius: 20px;
			border: 1px solid rgba(164, 223, 207, 0.95);
			box-shadow: 0 20px 40px rgba(7, 57, 58, 0.08);
		}

		.login-hero {
			background: linear-gradient(135deg, #07393A, #0A5F5C);
			color: #FFFFFF;
		}

		.login-hero-icon {
			color: #FFFFFF;
			opacity: 0.95;
		}

		.login-hero-title {
			color: #FFFFFF;
		}

		.login-hero-copy,
		.login-hero-meta {
			color: rgba(255, 255, 255, 0.82);
		}

		.login-badge {
			background: rgba(255, 255, 255, 0.14);
			color: #A4DFCF;
			border-radius: 999px;
			padding: 6px 14px;
			font-weight: 700;
		}

		.login-card {
			background: linear-gradient(135deg, #FFFFFF, #F3F6F3);
		}

		.login-field-label {
			color: #07393A;
			font-weight: 700;
		}

		.login-support-copy,
		.login-strength {
			color: #7F8C9A;
		}

		entry.login-entry,
		passwordentry.login-entry {
			background: rgba(255, 255, 255, 0.92);
			border-radius: 16px;
			border: 1px solid rgba(164, 223, 207, 0.95);
			padding: 12px 14px;
			color: #2C3E50;
			box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
		}

		entry.login-entry:focus,
		passwordentry.login-entry:focus {
			border-color: #13A1A1;
			box-shadow: 0 0 0 2px rgba(19, 161, 161, 0.18);
		}

		entry.login-totp-entry {
			font-size: 1.15rem;
			font-weight: 700;
			letter-spacing: 0.18rem;
		}

		button.primary-pill,
		button.secondary-pill {
			border-radius: 999px;
			padding: 12px 20px;
			font-weight: 700;
			transition: all 200ms ease;
		}

		button.primary-pill {
			background: linear-gradient(120deg, #13A1A1, #1F8678);
			color: #FFFFFF;
			box-shadow: 0 12px 22px rgba(19, 161, 161, 0.24);
		}

		button.primary-pill:hover {
			transform: translateY(-2px);
			box-shadow: 0 16px 26px rgba(19, 161, 161, 0.32);
		}

		button.secondary-pill {
			background: transparent;
			color: #07393A;
			border: 1px solid rgba(7, 57, 58, 0.28);
		}

		button.secondary-pill:hover {
			background: rgba(164, 223, 207, 0.22);
			transform: translateY(-2px);
		}

		label.login-error {
			color: #E74C3C;
			font-weight: 600;
		}

		label.success {
			color: #1F8678;
		}

		label.warning {
			color: #13A1A1;
		}

		label.error {
			color: #E74C3C;
		}

		.main-window {
			background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), #F3F6F3 42%);
		}

		headerbar.main-headerbar {
			background: linear-gradient(120deg, #07393A, #0A5F5C);
			color: #FFFFFF;
			border-radius: 16px;
			padding: 4px 6px;
		}

		.main-title {
			color: #FFFFFF;
			font-weight: 800;
		}

		button.main-add-button {
			padding-left: 20px;
			padding-right: 20px;
		}

		entry.main-search-entry,
		searchentry.main-search-entry {
			border-radius: 14px;
			border: 1px solid rgba(164, 223, 207, 0.95);
			background: rgba(255, 255, 255, 0.95);
			padding: 10px 12px;
		}

		frame.main-sidebar,
		frame.main-center-panel {
			background: #FFFFFF;
			border: 1px solid rgba(164, 223, 207, 0.95);
			border-radius: 18px;
			box-shadow: 0 14px 28px rgba(7, 57, 58, 0.08);
		}

		.main-section-title {
			color: #07393A;
			font-weight: 800;
		}

		list.main-category-list row {
			border-radius: 12px;
			margin: 2px 0;
		}

		list.main-category-list row:selected {
			background: rgba(19, 161, 161, 0.16);
		}

		.main-sidebar-icon {
			color: #0A5F5C;
		}

		.main-sidebar-label {
			color: #2C3E50;
			font-weight: 600;
		}

		.main-empty-state {
			padding: 26px;
		}

		.main-empty-icon {
			opacity: 0.95;
		}

		.main-empty-title {
			color: #07393A;
		}

		.main-empty-copy {
			color: #5B7580;
		}
		"#,
	);

	if let Some(display) = gdk::Display::default() {
		gtk4::style_context_add_provider_for_display(
			&display,
			&provider,
			gtk4::STYLE_PROVIDER_PRIORITY_APPLICATION,
		);
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

	let (file_writer, guard) = tracing_appender::non_blocking(tracing_appender::rolling::daily(
		&log_dir_path,
		"heelonvault.log",
	));

	let is_debug_logging = base_filter_spec.to_ascii_lowercase().contains("debug");
	let is_dev_mode = cfg!(debug_assertions);

	if is_dev_mode {
		let console_layer = tracing_subscriber::fmt::layer()
			.pretty()
			.with_writer(std::io::stdout)
			.with_target(false)
			.with_timer(UtcTime::rfc_3339());
		let file_layer = tracing_subscriber::fmt::layer()
			.json()
			.with_ansi(false)
			.with_writer(file_writer)
			.with_target(is_debug_logging)
			.with_line_number(is_debug_logging)
			.with_file(is_debug_logging)
			.with_timer(UtcTime::rfc_3339());

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
			.with_timer(UtcTime::rfc_3339());
		let file_layer = tracing_subscriber::fmt::layer()
			.json()
			.with_ansi(false)
			.with_writer(file_writer)
			.with_target(is_debug_logging)
			.with_line_number(is_debug_logging)
			.with_file(is_debug_logging)
			.with_timer(UtcTime::rfc_3339());

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

	let users_count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM users")
		.fetch_one(&pool)
		.await
		.context("failed to count users in users table")?;
	let (admin_user_id, admin_master_key) = ensure_dev_admin_context(
		&pool,
		users_count,
		&auth_service,
		Arc::clone(&vault_service),
	)
	.await?;

	let admin_identity_label: String = sqlx::query_scalar(
		"SELECT COALESCE(NULLIF(display_name, ''), username) FROM users WHERE id = ?1",
	)
	.bind(admin_user_id.to_string())
	.fetch_optional(&pool)
	.await
	.context("failed to resolve admin identity label")?
	.unwrap_or_else(|| "admin".to_string());

	let password_service = PasswordServiceImpl::new();
	let backup_service = BackupServiceImpl::new();

	info!("all services are initialized and ready");

	Ok(AppContext {
		_pool: pool,
		_crypto_service: crypto_service,
		auth_service,
		vault_service,
		secret_service,
		user_service,
		admin_user_id,
		admin_identity_label,
		admin_master_key,
		_password_service: password_service,
		_backup_service: backup_service,
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
	Ok(current_dir.join("data").join("heelonvault-rust-dev.db"))
}

async fn ensure_dev_admin_context(
	pool: &SqlitePool,
	users_count: i64,
	auth_service: &Arc<AuthServiceImpl<CryptoServiceImpl>>,
	vault_service: Arc<VaultServiceHandle>,
) -> Result<(Uuid, Vec<u8>)> {
	let admin_user_id = match sqlx::query("SELECT id FROM users WHERE username = ?1")
		.bind("admin")
		.fetch_optional(pool)
		.await
		.context("failed to query admin user")?
	{
		Some(row) => {
			let id_raw: String = row
				.try_get("id")
				.context("failed to read admin user id")?;
			Uuid::parse_str(&id_raw).context("failed to parse admin user id")?
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
			user_id
		}
	};

	if users_count == 0 {
		// TODO: remove before release
		match auth_service
			.create_user("admin", SecretBox::new(Box::new(b"Admin1234!".to_vec())))
			.await
		{
			Ok(()) => info!("development admin user created: username=admin"),
			Err(AppError::Conflict(_)) => {}
			Err(error) => return Err(anyhow!("failed to create default development admin user: {error}")),
		}
	} else {
		match auth_service
			.create_user("admin", SecretBox::new(Box::new(b"Admin1234!".to_vec())))
			.await
		{
			Ok(()) => info!("development admin credentials loaded into auth service"),
			Err(AppError::Conflict(_)) => {}
			Err(error) => return Err(anyhow!("failed to prepare admin auth credentials: {error}")),
		}
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
