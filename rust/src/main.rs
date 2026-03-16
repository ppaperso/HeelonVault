use std::path::PathBuf;
use std::sync::Arc;

use anyhow::{anyhow, Context, Result};
use gtk4::gio;
use gtk4::prelude::*;
use libadwaita as adw;
use secrecy::SecretBox;
use sqlx::sqlite::SqliteConnectOptions;
use sqlx::{Row, SqlitePool};
use tokio::runtime::Builder;
use tracing::info;
use tracing_subscriber::EnvFilter;

use heelonvault_rust::config::constants::APP_ID;
use heelonvault_rust::errors::AppError;
use heelonvault_rust::repositories::secret_repository::SqlxSecretRepository;
use heelonvault_rust::repositories::vault_repository::SqlxVaultRepository;
use heelonvault_rust::services::auth_service::AuthServiceImpl;
use heelonvault_rust::services::backup_service::BackupServiceImpl;
use heelonvault_rust::services::crypto_service::CryptoServiceImpl;
use heelonvault_rust::services::password_service::PasswordServiceImpl;
use heelonvault_rust::services::secret_service::SecretServiceImpl;
use heelonvault_rust::services::vault_service::{
	VaultKeyEnvelopeRepository, VaultServiceImpl,
};
use uuid::Uuid;

type VaultServiceHandle =
	VaultServiceImpl<SqlxVaultRepository, SqlxVaultEnvelopeRepository, CryptoServiceImpl>;
type SecretServiceHandle = SecretServiceImpl<SqlxSecretRepository, CryptoServiceImpl>;

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
	_auth_service: AuthServiceImpl<CryptoServiceImpl>,
	_vault_service: VaultServiceHandle,
	_secret_service: SecretServiceHandle,
	_password_service: PasswordServiceImpl,
	_backup_service: BackupServiceImpl,
}

fn main() -> Result<()> {
	initialize_tracing()?;

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

	let app_context_for_activate = Arc::clone(&app_context);
	application.connect_activate(move |app| {
		let _context = Arc::clone(&app_context_for_activate);

		let window = adw::ApplicationWindow::builder()
			.application(app)
			.title("HeelonVault")
			.default_width(960)
			.default_height(640)
			.build();

		window.present();
	});

	let _exit_code = application.run();
	Ok(())
}

fn initialize_tracing() -> Result<()> {
	let env_filter = EnvFilter::try_from_default_env()
		.unwrap_or_else(|_| EnvFilter::new("info"));

	tracing_subscriber::fmt()
		.with_env_filter(env_filter)
		.with_target(false)
		.try_init()
		.map_err(|error| anyhow!("failed to initialize tracing subscriber: {error}"))?;

	Ok(())
}

async fn initialize_app_context() -> Result<AppContext> {
	let database_path = PathBuf::from("heelonvault.db");
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
	let auth_service = AuthServiceImpl::new(CryptoServiceImpl::default());
	let vault_service = VaultServiceImpl::new(
		SqlxVaultRepository::new(pool.clone()),
		SqlxVaultEnvelopeRepository::new(pool.clone()),
		CryptoServiceImpl::default(),
	);
	let secret_service =
		SecretServiceImpl::new(SqlxSecretRepository::new(pool.clone()), CryptoServiceImpl::default());
	let password_service = PasswordServiceImpl::new();
	let backup_service = BackupServiceImpl::new();

	info!("all services are initialized and ready");

	Ok(AppContext {
		_pool: pool,
		_crypto_service: crypto_service,
		_auth_service: auth_service,
		_vault_service: vault_service,
		_secret_service: secret_service,
		_password_service: password_service,
		_backup_service: backup_service,
	})
}
