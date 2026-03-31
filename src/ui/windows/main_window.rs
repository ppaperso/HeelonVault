use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Datelike, Local, NaiveDateTime, Timelike, Utc};
use gtk4::glib;
use gtk4::prelude::*;
use gtk4::{Align, Orientation};
use libadwaita as adw;
use libadwaita::prelude::*;
use secrecy::{ExposeSecret, SecretBox};
use serde_json::Value;
use sqlx::{Row, SqlitePool};
use tokio::runtime::Handle;
use tracing::{info, warn};
use uuid::Uuid;
use zeroize::Zeroize;

use crate::services::auth_policy_service::AuthPolicyService;
use crate::services::admin_service::AdminService;
use crate::services::backup_service::BackupService;
use crate::services::import_service::ImportService;
use crate::services::login_history_service::list_recent_logins;
use crate::services::secret_service::SecretService;
use crate::services::team_service::TeamService;
use crate::services::totp_service::TotpService;
use crate::services::user_service::UserService;
use crate::ui::messages;
use crate::services::vault_service::VaultService;
use crate::ui::dialogs::add_edit_dialog::{AddEditDialog, DialogMode};
use crate::ui::dialogs::manage_teams_dialog::ManageTeamsDialog;
use crate::ui::dialogs::manage_users_dialog::ManageUsersDialog;
use crate::ui::dialogs::trash_dialog::TrashDialog;
use crate::ui::widgets::secret_card::{SecretCard, SecretRowData};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SecretCategoryFilter {
	All,
	Password,
	ApiToken,
	SshKey,
	SecureDocument,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum AuditFilter {
	All,
	Weak,
	Duplicate,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SecretSortMode {
	Recent,
	Title,
	Risk,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SecretKind {
	Password,
	ApiToken,
	SshKey,
	SecureDocument,
}

#[derive(Clone)]
struct SecretFilterMeta {
	searchable_text: String,
	title_text: String,
	login_text: String,
	email_text: String,
	url_text: String,
	notes_text: String,
	category_text: String,
	tags_text: String,
	type_text: String,
	kind: SecretKind,
	original_rank: usize,
	is_weak: bool,
	is_duplicate: bool,
}

#[derive(Clone)]
struct FilterRuntime {
	meta_by_widget: Rc<RefCell<HashMap<String, SecretFilterMeta>>>,
	search_text: Rc<RefCell<String>>,
	selected_category: Rc<Cell<SecretCategoryFilter>>,
	selected_audit: Rc<Cell<AuditFilter>>,
	selected_sort: Rc<Cell<SecretSortMode>>,
	audit_all_count_label: gtk4::Label,
	audit_weak_count_label: gtk4::Label,
	audit_duplicate_count_label: gtk4::Label,
	total_count_label: gtk4::Label,
	non_compliant_count_label: gtk4::Label,
	filtered_status_page: adw::StatusPage,
}

pub struct MainWindow {
	window: adw::ApplicationWindow,
	secret_flow: gtk4::FlowBox,
	refresh_entries: Rc<dyn Fn()>,
	auto_lock_timeout_secs: Rc<Cell<u64>>,
	auto_lock_source: Rc<RefCell<Option<glib::SourceId>>>,
	auto_lock_armed: Rc<Cell<bool>>,
	session_master_key: Rc<RefCell<Vec<u8>>>,
	on_auto_lock: Rc<RefCell<Option<Rc<dyn Fn()>>>>,
	on_logout: Rc<RefCell<Option<Rc<dyn Fn()>>>>,
}

impl MainWindow {
	const DEFAULT_AUTO_LOCK_TIMEOUT_SECS: u64 = 5 * 60;
	const DEFAULT_WINDOW_WIDTH: i32 = 1180;
	const DEFAULT_WINDOW_HEIGHT: i32 = 760;
	const MIN_WINDOW_WIDTH: i32 = 980;
	const MIN_WINDOW_HEIGHT: i32 = 640;

	fn initial_window_size() -> (i32, i32) {
		let mut width = Self::DEFAULT_WINDOW_WIDTH;
		let mut height = Self::DEFAULT_WINDOW_HEIGHT;

		if let Some(display) = gtk4::gdk::Display::default() {
			let monitors = display.monitors();
			if let Some(monitor_obj) = monitors.item(0) {
				if let Ok(monitor) = monitor_obj.downcast::<gtk4::gdk::Monitor>() {
					let geometry = monitor.geometry();
					let target_width = ((geometry.width() as f64) * 0.70).round() as i32;
					let target_height = ((geometry.height() as f64) * 0.70).round() as i32;

					width = target_width.max(Self::MIN_WINDOW_WIDTH);
					height = target_height.max(Self::MIN_WINDOW_HEIGHT);
				}
			}
		}

		(width, height)
	}

	pub fn new<TSecret, TVault, TUser, TAdmin, TTeam, TTotp, TPolicy, TBackup, TImport>(
		application: &adw::Application,
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		user_service: Arc<TUser>,
		admin_service: Arc<TAdmin>,
		team_service: Arc<TTeam>,
		totp_service: Arc<TTotp>,
		auth_policy_service: Arc<TPolicy>,
		backup_service: Arc<TBackup>,
		import_service: Arc<TImport>,
		database_pool: SqlitePool,
		database_path: PathBuf,
		admin_user_id: Uuid,
		admin_master_key: Vec<u8>,
		connected_identity_label: String,
		is_admin: bool,
	) -> Self
	where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
		TUser: UserService + Send + Sync + 'static,
		TAdmin: AdminService + Send + Sync + 'static,
		TTeam: TeamService + Send + Sync + 'static,
		TTotp: TotpService + Send + Sync + 'static,
		TPolicy: AuthPolicyService + Send + Sync + 'static,
		TBackup: BackupService + Send + Sync + 'static,
		TImport: ImportService + Send + Sync + 'static,
	{
		let (initial_width, initial_height) = Self::initial_window_size();
		let window = adw::ApplicationWindow::builder()
			.application(application)
			.title("HeelonVault")
			.default_width(initial_width)
			.default_height(initial_height)
			.build();
		window.add_css_class("app-window");
		window.add_css_class("main-window");
		window.set_icon_name(Some("heelonvault"));

		let auto_lock_source: Rc<RefCell<Option<glib::SourceId>>> = Rc::new(RefCell::new(None));
		let auto_lock_armed = Rc::new(Cell::new(false));
		let auto_lock_timeout_secs = Rc::new(Cell::new(Self::DEFAULT_AUTO_LOCK_TIMEOUT_SECS));
		let session_master_key = Rc::new(RefCell::new(admin_master_key));
		let active_vault_id: Rc<RefCell<Option<Uuid>>> = Rc::new(RefCell::new(None));
		let on_auto_lock: Rc<RefCell<Option<Rc<dyn Fn()>>>> = Rc::new(RefCell::new(None));
		let on_logout: Rc<RefCell<Option<Rc<dyn Fn()>>>> = Rc::new(RefCell::new(None));
		let critical_ops_in_flight = Rc::new(Cell::new(0_u32));

		let header_bar = adw::HeaderBar::new();
		header_bar.add_css_class("main-headerbar");
		header_bar.set_show_start_title_buttons(false);
		header_bar.set_show_end_title_buttons(true);
		header_bar.set_decoration_layout(Some(":close"));

		let on_logout_for_close = Rc::clone(&on_logout);
		let critical_ops_for_close = Rc::clone(&critical_ops_in_flight);
		window.connect_close_request(move |win| {
			if critical_ops_for_close.get() > 0 {
				Self::show_feedback_dialog(
					win,
					"Opération en cours",
					"Une opération d'import/export est en cours. Attendez la fin avant de fermer la fenêtre.",
				);
				return glib::Propagation::Stop;
			}

			if let Some(callback) = on_logout_for_close.borrow().as_ref() {
				callback();
			}
			glib::Propagation::Stop
		});

		let root = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(0)
			.build();
		let toast_overlay = adw::ToastOverlay::new();

		let title_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();
		let logo = gtk4::Image::from_resource("/com/heelonvault/rust/icons/Logo_Heelonys_transparent.png");
		logo.set_pixel_size(22);
		logo.add_css_class("main-title-logo");
		let title_label = gtk4::Label::new(Some("HeelonVault"));
		title_label.add_css_class("title-3");
		title_label.add_css_class("main-title");
		let header_beta_badge = gtk4::Label::new(Some("BETA"));
		header_beta_badge.add_css_class("beta-badge");
		header_beta_badge.add_css_class("header-beta-badge");
		title_box.append(&logo);
		title_box.append(&title_label);
		title_box.append(&header_beta_badge);
		header_bar.set_title_widget(Some(&title_box));

		let profile_button = gtk4::MenuButton::new();
		profile_button.add_css_class("header-badge");
		profile_button.set_label(
			crate::i18n::tr_args(
				"main-connected-label",
				&[("name", crate::i18n::I18nArg::Str(connected_identity_label.as_str()))],
			)
			.as_str(),
		);
		profile_button.set_tooltip_text(Some(crate::tr!("main-last-logins-tooltip").as_str()));

		let profile_popover = gtk4::Popover::new();
		profile_popover.set_has_arrow(true);
		profile_popover.set_autohide(true);
		let profile_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(6)
			.margin_top(10)
			.margin_bottom(10)
			.margin_start(10)
			.margin_end(10)
			.build();
		profile_box.add_css_class("profile-login-history-popover");

		let profile_title = gtk4::Label::new(Some(crate::tr!("main-last-logins-title").as_str()));
		profile_title.set_halign(Align::Start);
		profile_title.add_css_class("profile-login-history-title");
		profile_box.append(&profile_title);

		let login_history_list = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(4)
			.build();
		profile_box.append(&login_history_list);

		let runtime_for_login_history = runtime_handle.clone();
		let db_for_login_history = database_pool.clone();
		let history_list_for_show = login_history_list.clone();
		let runtime_for_login_history_click = runtime_handle.clone();
		let db_for_login_history_click = database_pool.clone();
		let history_list_for_click = login_history_list.clone();
		profile_popover.connect_show(move |_| {
			Self::refresh_login_history_popover(
				runtime_for_login_history.clone(),
				db_for_login_history.clone(),
				admin_user_id,
				history_list_for_show.clone(),
			);
		});
		profile_button.connect_notify_local(Some("active"), move |button, _| {
			if !button.property::<bool>("active") {
				return;
			}
			Self::refresh_login_history_popover(
				runtime_for_login_history_click.clone(),
				db_for_login_history_click.clone(),
				admin_user_id,
				history_list_for_click.clone(),
			);
		});

		profile_popover.set_child(Some(&profile_box));
		profile_button.set_popover(Some(&profile_popover));

		let user_identity_box = gtk4::Box::builder()
			.orientation(gtk4::Orientation::Horizontal)
			.spacing(6)
			.build();
		user_identity_box.append(&profile_button);
		if is_admin {
			let admin_badge = gtk4::Label::new(Some(crate::tr!("main-admin-badge").as_str()));
			admin_badge.add_css_class("header-badge");
			admin_badge.add_css_class("admin-badge");
			admin_badge.add_css_class("warning");
			admin_badge.set_tooltip_text(Some(crate::tr!("main-admin-badge-tooltip").as_str()));
			user_identity_box.append(&admin_badge);
		}

		let add_button = gtk4::Button::builder()
			.icon_name("list-add-symbolic")
			.build();
		add_button.add_css_class("flat");
		add_button.add_css_class("accent");
		add_button.add_css_class("main-add-button");
		add_button.set_tooltip_text(Some(crate::tr!("main-add-tooltip").as_str()));

		let trash_button = gtk4::Button::builder()
			.icon_name("user-trash-symbolic")
			.build();
		trash_button.add_css_class("flat");
		trash_button.add_css_class("main-add-button");
		trash_button.set_tooltip_text(Some(crate::tr!("main-trash-tooltip").as_str()));

		let app_for_trash = application.clone();
		let window_for_trash = window.clone();
		let runtime_for_trash = runtime_handle.clone();
		let secret_for_trash = Arc::clone(&secret_service);
		let vault_for_trash = Arc::clone(&vault_service);
		let admin_user_for_trash = admin_user_id;
		let session_master_for_trash = Rc::clone(&session_master_key);

		let center_panel = Self::build_center_panel();
		let sidebar_panel = Self::build_sidebar_panel();
		let sidebar_i18n_refresh: Rc<dyn Fn()> = {
			let sidebar = SidebarWidgets {
				frame: sidebar_panel.frame.clone(),
				my_vaults_title: sidebar_panel.my_vaults_title.clone(),
				create_vault_button: sidebar_panel.create_vault_button.clone(),
				my_vaults_list: sidebar_panel.my_vaults_list.clone(),
				shared_vaults_title: sidebar_panel.shared_vaults_title.clone(),
				shared_vaults_list: sidebar_panel.shared_vaults_list.clone(),
				category_list: sidebar_panel.category_list.clone(),
				audit_list: sidebar_panel.audit_list.clone(),
				audit_title: sidebar_panel.audit_title.clone(),
				categories_title: sidebar_panel.categories_title.clone(),
				account_title: sidebar_panel.account_title.clone(),
				audit_all_label: sidebar_panel.audit_all_label.clone(),
				audit_weak_label: sidebar_panel.audit_weak_label.clone(),
				audit_duplicate_label: sidebar_panel.audit_duplicate_label.clone(),
				category_all_label: sidebar_panel.category_all_label.clone(),
				category_passwords_label: sidebar_panel.category_passwords_label.clone(),
				category_api_tokens_label: sidebar_panel.category_api_tokens_label.clone(),
				category_ssh_keys_label: sidebar_panel.category_ssh_keys_label.clone(),
				category_documents_label: sidebar_panel.category_documents_label.clone(),
				audit_all_badge: sidebar_panel.audit_all_badge.clone(),
				audit_weak_badge: sidebar_panel.audit_weak_badge.clone(),
				audit_duplicate_badge: sidebar_panel.audit_duplicate_badge.clone(),
				profile_security_label: sidebar_panel.profile_security_label.clone(),
				profile_security_button: sidebar_panel.profile_security_button.clone(),
				teams_label: sidebar_panel.teams_label.clone(),
				teams_button: sidebar_panel.teams_button.clone(),
				administration_label: sidebar_panel.administration_label.clone(),
				administration_button: sidebar_panel.administration_button.clone(),
			};
			Rc::new(move || {
				sidebar.audit_title.set_text(crate::tr!("main-audit-title").as_str());
				sidebar
					.audit_all_label
					.set_text(crate::tr!("main-audit-all").as_str());
				sidebar
					.audit_weak_label
					.set_text(crate::tr!("main-audit-weak").as_str());
				sidebar
					.audit_duplicate_label
					.set_text(crate::tr!("main-audit-duplicates").as_str());
				sidebar
					.categories_title
					.set_text(crate::tr!("main-categories-title").as_str());
				sidebar
					.category_all_label
					.set_text(crate::tr!("main-category-all").as_str());
				sidebar
					.category_passwords_label
					.set_text(crate::tr!("main-category-passwords").as_str());
				sidebar
					.category_api_tokens_label
					.set_text(crate::tr!("main-category-api-tokens").as_str());
				sidebar
					.category_ssh_keys_label
					.set_text(crate::tr!("main-category-ssh-keys").as_str());
				sidebar
					.category_documents_label
					.set_text(crate::tr!("main-category-documents").as_str());
				sidebar
					.account_title
					.set_text(crate::tr!("main-account-title").as_str());
				sidebar
					.profile_security_label
					.set_text(crate::tr!("main-profile-security").as_str());
				sidebar
					.my_vaults_title
					.set_text(crate::tr!("main-my-vaults-title").as_str());
				sidebar
					.shared_vaults_title
					.set_text(crate::tr!("main-shared-with-me-title").as_str());
				sidebar
					.create_vault_button
					.set_tooltip_text(Some(crate::tr!("main-create-vault-button").as_str()));
				sidebar.teams_label.set_text(crate::tr!("main-teams-nav").as_str());
				sidebar
					.administration_label
					.set_text(crate::tr!("main-user-nav").as_str());
			})
		};
		let on_main_i18n_refresh: Rc<RefCell<Option<Rc<dyn Fn()>>>> = Rc::new(RefCell::new(None));
		let on_main_i18n_refresh_bridge: Rc<dyn Fn()> = {
			let holder = Rc::clone(&on_main_i18n_refresh);
			Rc::new(move || {
				if let Some(refresh) = holder.borrow().as_ref() {
					refresh();
				}
			})
		};
		let secret_flow_for_struct = center_panel.secret_flow.clone();
		let show_passwords_in_edit_pref = Rc::new(Cell::new(false));

		let filter_runtime = FilterRuntime {
			meta_by_widget: Rc::new(RefCell::new(HashMap::new())),
			search_text: Rc::new(RefCell::new(String::new())),
			selected_category: Rc::new(Cell::new(SecretCategoryFilter::All)),
			selected_audit: Rc::new(Cell::new(AuditFilter::All)),
			selected_sort: Rc::new(Cell::new(SecretSortMode::Recent)),
			audit_all_count_label: sidebar_panel.audit_all_badge.clone(),
			audit_weak_count_label: sidebar_panel.audit_weak_badge.clone(),
			audit_duplicate_count_label: sidebar_panel.audit_duplicate_badge.clone(),
			total_count_label: center_panel.status_total_badge.clone(),
			non_compliant_count_label: center_panel.status_non_compliant_badge.clone(),
			filtered_status_page: center_panel.filtered_status_page.clone(),
		};

		let runtime_for_flow_filter = filter_runtime.clone();
		center_panel.secret_flow.set_filter_func(move |child| {
			let Some(content) = child.child() else {
				return false;
			};
			let key = content.widget_name().to_string();
			let store = runtime_for_flow_filter.meta_by_widget.borrow();
			let Some(meta) = store.get(&key) else {
				return true;
			};

			let query = runtime_for_flow_filter.search_text.borrow().to_string();
			let terms = Self::parse_search_terms(query.as_str());
			let matches_query = terms.is_empty()
				|| terms
					.iter()
					.all(|term| Self::matches_search_term(meta, term));

			let matches_category = match runtime_for_flow_filter.selected_category.get() {
				SecretCategoryFilter::All => true,
				SecretCategoryFilter::Password => meta.kind == SecretKind::Password,
				SecretCategoryFilter::ApiToken => meta.kind == SecretKind::ApiToken,
				SecretCategoryFilter::SshKey => meta.kind == SecretKind::SshKey,
				SecretCategoryFilter::SecureDocument => meta.kind == SecretKind::SecureDocument,
			};

			let matches_audit = match runtime_for_flow_filter.selected_audit.get() {
				AuditFilter::All => true,
				AuditFilter::Weak => meta.is_weak,
				AuditFilter::Duplicate => meta.is_duplicate,
			};

			matches_query && matches_category && matches_audit
		});

		let runtime_for_flow_sort = filter_runtime.clone();
		center_panel.secret_flow.set_sort_func(move |left, right| {
			let left_key = left
				.child()
				.map(|child| child.widget_name().to_string())
				.unwrap_or_default();
			let right_key = right
				.child()
				.map(|child| child.widget_name().to_string())
				.unwrap_or_default();

			let store = runtime_for_flow_sort.meta_by_widget.borrow();
			let Some(left_meta) = store.get(&left_key) else {
				return left_key.cmp(&right_key).into();
			};
			let Some(right_meta) = store.get(&right_key) else {
				return left_key.cmp(&right_key).into();
			};

			match runtime_for_flow_sort.selected_sort.get() {
				SecretSortMode::Recent => left_meta.original_rank.cmp(&right_meta.original_rank).into(),
				SecretSortMode::Title => left_meta
					.title_text
					.cmp(&right_meta.title_text)
					.then(left_meta.original_rank.cmp(&right_meta.original_rank))
					.into(),
				SecretSortMode::Risk => {
					let left_score = usize::from(left_meta.is_weak) + usize::from(left_meta.is_duplicate);
					let right_score = usize::from(right_meta.is_weak) + usize::from(right_meta.is_duplicate);
					right_score
						.cmp(&left_score)
						.then(left_meta.title_text.cmp(&right_meta.title_text))
						.then(left_meta.original_rank.cmp(&right_meta.original_rank))
						.into()
				}
			}
		});

		let secret_flow_for_refresh = center_panel.secret_flow.clone();
		let stack_for_refresh = center_panel.stack.clone();
		let empty_title_for_refresh = center_panel.empty_title.clone();
		let empty_copy_for_refresh = center_panel.empty_copy.clone();
		let vault_selection_sync = Rc::new(Cell::new(false));
		let default_vault_creation_in_progress = Rc::new(Cell::new(false));
		let refresh_after_vault_mutation: Rc<RefCell<Option<Rc<dyn Fn()>>>> = Rc::new(RefCell::new(None));
		let editor_launcher: Rc<RefCell<Option<Rc<dyn Fn(DialogMode)>>>> =
			Rc::new(RefCell::new(None));

		let refresh_vault_sections: Rc<dyn Fn()> = {
			let app_for_secret_refresh = application.clone();
			let parent_for_secret_refresh = window.clone();
			let runtime_for_secret_refresh = runtime_handle.clone();
			let secret_service_for_secret_refresh = Arc::clone(&secret_service);
			let vault_service_for_secret_refresh = Arc::clone(&vault_service);
			let toast_for_secret_refresh = toast_overlay.clone();
			let active_vault_for_secret_refresh = Rc::clone(&active_vault_id);
			let secret_flow_for_secret_refresh = secret_flow_for_refresh.clone();
			let stack_for_secret_refresh = stack_for_refresh.clone();
			let empty_title_for_secret_refresh = empty_title_for_refresh.clone();
			let empty_copy_for_secret_refresh = empty_copy_for_refresh.clone();
			let filter_for_secret_refresh = filter_runtime.clone();
			let editor_launcher_for_secret_refresh = Rc::clone(&editor_launcher);
			let session_for_secret_refresh = Rc::clone(&session_master_key);
			let refresh_secrets: Rc<dyn Fn()> = Rc::new(move || {
				let Some(master_key) = Self::snapshot_session_master_key(&session_for_secret_refresh) else {
					empty_title_for_secret_refresh.set_text(crate::tr!("main-session-locked-title").as_str());
					empty_copy_for_secret_refresh.set_text(crate::tr!("main-session-locked-description").as_str());
					stack_for_secret_refresh.set_visible_child_name("empty");
					return;
				};

				Self::refresh_secret_flow(
					app_for_secret_refresh.clone(),
					parent_for_secret_refresh.clone(),
					runtime_for_secret_refresh.clone(),
					Arc::clone(&secret_service_for_secret_refresh),
					Arc::clone(&vault_service_for_secret_refresh),
					admin_user_id,
					master_key,
					secret_flow_for_secret_refresh.clone(),
					stack_for_secret_refresh.clone(),
					empty_title_for_secret_refresh.clone(),
					empty_copy_for_secret_refresh.clone(),
					active_vault_for_secret_refresh.clone(),
					toast_for_secret_refresh.clone(),
					filter_for_secret_refresh.clone(),
					editor_launcher_for_secret_refresh.clone(),
				);
			});

			let runtime_for_vaults = runtime_handle.clone();
			let vault_service_for_vaults = Arc::clone(&vault_service);
			let secret_service_for_vaults = Arc::clone(&secret_service);
			let session_master_for_vaults = Rc::clone(&session_master_key);
			let my_vaults_list = sidebar_panel.my_vaults_list.clone();
			let shared_vaults_title = sidebar_panel.shared_vaults_title.clone();
			let shared_vaults_list = sidebar_panel.shared_vaults_list.clone();
			let active_vault_id = Rc::clone(&active_vault_id);
			let vault_selection_sync = Rc::clone(&vault_selection_sync);
			let creating_default_vault = Rc::clone(&default_vault_creation_in_progress);
			let refresh_secrets_for_vaults = Rc::clone(&refresh_secrets);
			let window_for_delete_vault = window.clone();
			let runtime_for_delete_vault = runtime_handle.clone();
			let vault_service_for_delete_vault = Arc::clone(&vault_service);
			let refresh_after_vault_mutation = Rc::clone(&refresh_after_vault_mutation);
			Rc::new(move || {
				let refresh_after_delete_holder = Rc::clone(&refresh_after_vault_mutation);
				let active_vault_for_delete = Rc::clone(&active_vault_id);
				let delete_vault_action: Rc<dyn Fn(Uuid, String)> = {
					let parent_window = window_for_delete_vault.clone();
					let runtime_for_action = runtime_for_delete_vault.clone();
					let vault_service_for_action = Arc::clone(&vault_service_for_delete_vault);
					Rc::new(move |vault_id: Uuid, vault_name: String| {
						let body = crate::i18n::tr_args(
							"main-delete-vault-confirm-body",
							&[("name", crate::i18n::I18nArg::Str(vault_name.as_str()))],
						);
						let dialog = adw::MessageDialog::new(
							Some(&parent_window),
							Some(crate::tr!("main-delete-vault-confirm-title").as_str()),
							Some(body.as_str()),
						);
						dialog.add_response("cancel", crate::tr!("common-cancel").as_str());
						dialog.add_response("delete", crate::tr!("main-delete-vault-confirm-cta").as_str());
						dialog.set_response_appearance("delete", adw::ResponseAppearance::Destructive);
						dialog.set_default_response(Some("cancel"));
						dialog.set_close_response("cancel");

						let runtime_for_confirm = runtime_for_action.clone();
						let vault_service_for_confirm = Arc::clone(&vault_service_for_action);
						let parent_for_confirm = parent_window.clone();
						let refresh_after_confirm_holder = Rc::clone(&refresh_after_delete_holder);
						let active_for_confirm = Rc::clone(&active_vault_for_delete);
						dialog.connect_response(None, move |_dlg, response| {
							if response != "delete" {
								return;
							}

							let (sender, receiver) = tokio::sync::oneshot::channel();
							let runtime_for_task = runtime_for_confirm.clone();
							let vault_service_for_task = Arc::clone(&vault_service_for_confirm);
							std::thread::spawn(move || {
								let result = runtime_for_task.block_on(async move {
									vault_service_for_task.delete_vault(admin_user_id, vault_id).await
								});
								let _ = sender.send(result);
							});

							let parent_for_result = parent_for_confirm.clone();
							let refresh_after_result_holder = Rc::clone(&refresh_after_confirm_holder);
							let active_after_result = Rc::clone(&active_for_confirm);
							glib::MainContext::default().spawn_local(async move {
								match receiver.await {
									Ok(Ok(())) => {
										if *active_after_result.borrow() == Some(vault_id) {
											*active_after_result.borrow_mut() = None;
										}
										if let Some(refresh) = refresh_after_result_holder.borrow().as_ref() {
											refresh();
										}
									}
									Ok(Err(error)) => {
										let message = error.to_string();
										Self::show_feedback_dialog(
											&parent_for_result,
											crate::tr!("main-delete-vault-error-title").as_str(),
											message.as_str(),
										);
									}
									Err(_) => {
										Self::show_feedback_dialog(
											&parent_for_result,
											crate::tr!("main-delete-vault-error-title").as_str(),
											crate::tr!("main-list-unavailable-description").as_str(),
										);
									}
								}
							});
						});
						dialog.present();
					})
				};

				while let Some(child) = my_vaults_list.first_child() {
					my_vaults_list.remove(&child);
				}
				while let Some(child) = shared_vaults_list.first_child() {
					shared_vaults_list.remove(&child);
				}

				let (sender, receiver) = tokio::sync::oneshot::channel();
				let runtime_for_task = runtime_for_vaults.clone();
				let vault_service_for_task = Arc::clone(&vault_service_for_vaults);
				let secret_service_for_task = Arc::clone(&secret_service_for_vaults);
				let can_attempt_default_create = !creating_default_vault.get();
				let master_for_default_create = if can_attempt_default_create {
					Self::snapshot_session_master_key(&session_master_for_vaults)
				} else {
					None
				};
				if can_attempt_default_create && master_for_default_create.is_some() {
					creating_default_vault.set(true);
				}
				std::thread::spawn(move || {
					let result = runtime_for_task.block_on(async move {
						let mut owned_vaults = vault_service_for_task.list_owned_vaults(admin_user_id).await?;
					if owned_vaults.is_empty() {
						if let Some(master_key) = master_for_default_create {
							let _ = vault_service_for_task
								.create_vault(
									admin_user_id,
									"perso",
									SecretBox::new(Box::new(master_key)),
								)
								.await;
							owned_vaults = vault_service_for_task.list_owned_vaults(admin_user_id).await?;
						}
					}
					let mut owned_with_counts: Vec<(crate::models::Vault, usize, bool)> = Vec::with_capacity(owned_vaults.len());
					for vault in owned_vaults {
						let count = secret_service_for_task.list_by_vault(vault.id).await?.len();
						let is_shared_with_others = vault_service_for_task
							.is_vault_shared_with_others(admin_user_id, vault.id)
							.await?;
						owned_with_counts.push((vault, count, is_shared_with_others));
					}

					let shared_access = vault_service_for_task.list_shared_vault_access(admin_user_id).await?;
					let mut shared_with_counts: Vec<(crate::models::AccessibleVault, usize)> =
						Vec::with_capacity(shared_access.len());
					for access in shared_access {
						let count = secret_service_for_task.list_by_vault(access.vault.id).await?.len();
						shared_with_counts.push((access, count));
					}

					Ok::<_, crate::errors::AppError>((owned_with_counts, shared_with_counts))
				});
				let _ = sender.send((result, can_attempt_default_create));
			});
			let my_vaults_for_recv = my_vaults_list.clone();
			let shared_title_for_recv = shared_vaults_title.clone();
			let shared_list_for_recv = shared_vaults_list.clone();
			let active_vault_for_recv = Rc::clone(&active_vault_id);
			let sync_for_recv = Rc::clone(&vault_selection_sync);
			let creating_default_vault_for_recv = Rc::clone(&creating_default_vault);
			let delete_action_for_recv = Rc::clone(&delete_vault_action);
			let refresh_secrets_for_recv = Rc::clone(&refresh_secrets_for_vaults);
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok((Ok((owned_vaults, shared_vaults)), attempted_default_create)) => {
						if attempted_default_create {
							creating_default_vault_for_recv.set(false);
						}
						sync_for_recv.set(true);
						let mut first_vault_id: Option<Uuid> = None;
						for (vault, secret_count, is_shared_with_others) in owned_vaults {
							if first_vault_id.is_none() {
								first_vault_id = Some(vault.id);
							}
							let row = Self::build_vault_sidebar_row(
								vault.name.as_str(),
								vault.id,
								true,
								is_shared_with_others,
								None,
								secret_count,
								Some(Rc::clone(&delete_action_for_recv)),
							);
							my_vaults_for_recv.append(&row);
						}

						let mut first_shared_vault_id: Option<Uuid> = None;
						for (access, secret_count) in shared_vaults {
							if first_shared_vault_id.is_none() {
								first_shared_vault_id = Some(access.vault.id);
							}
							let row = Self::build_vault_sidebar_row(
								access.vault.name.as_str(),
								access.vault.id,
								false,
								false,
								Some(access.role),
								secret_count,
								None,
							);
							shared_list_for_recv.append(&row);
						}
						let has_shared = shared_list_for_recv.first_child().is_some();
						shared_title_for_recv.set_visible(has_shared);
						shared_list_for_recv.set_visible(has_shared);

						let active = *active_vault_for_recv.borrow();
						if let Some(active_id) = active {
							if let Some(row) = Self::find_vault_row(&my_vaults_for_recv, active_id) {
								my_vaults_for_recv.select_row(Some(&row));
							} else if let Some(row) = Self::find_vault_row(&shared_list_for_recv, active_id) {
								shared_list_for_recv.select_row(Some(&row));
							} else if let Some(fallback_id) = first_vault_id {
								*active_vault_for_recv.borrow_mut() = Some(fallback_id);
								if let Some(row) = Self::find_vault_row(&my_vaults_for_recv, fallback_id) {
									my_vaults_for_recv.select_row(Some(&row));
								}
							} else if let Some(fallback_id) = first_shared_vault_id {
								*active_vault_for_recv.borrow_mut() = Some(fallback_id);
								if let Some(row) = Self::find_vault_row(&shared_list_for_recv, fallback_id) {
									shared_list_for_recv.select_row(Some(&row));
								}
							} else {
								*active_vault_for_recv.borrow_mut() = None;
								my_vaults_for_recv.unselect_all();
								shared_list_for_recv.unselect_all();
							}
						} else if let Some(fallback_id) = first_vault_id {
							*active_vault_for_recv.borrow_mut() = Some(fallback_id);
							if let Some(row) = Self::find_vault_row(&my_vaults_for_recv, fallback_id) {
								my_vaults_for_recv.select_row(Some(&row));
							}
						} else if let Some(fallback_id) = first_shared_vault_id {
							*active_vault_for_recv.borrow_mut() = Some(fallback_id);
							if let Some(row) = Self::find_vault_row(&shared_list_for_recv, fallback_id) {
								shared_list_for_recv.select_row(Some(&row));
							}
						}
						sync_for_recv.set(false);
						refresh_secrets_for_recv();
					}
					Ok((Err(_), attempted_default_create)) => {
						if attempted_default_create {
							creating_default_vault_for_recv.set(false);
						}
						sync_for_recv.set(false);
					}
					_ => {
						sync_for_recv.set(false);
					}
				}
			});
		})
	};

		let refresh_list: Rc<dyn Fn()> = {
			let refresh_vault_sections = Rc::clone(&refresh_vault_sections);
			Rc::new(move || {
				refresh_vault_sections();
			})
		};
		*refresh_after_vault_mutation.borrow_mut() = Some(Rc::clone(&refresh_list));

		let window_for_create_vault = window.clone();
		let runtime_for_create_vault = runtime_handle.clone();
		let vault_service_for_create_vault = Arc::clone(&vault_service);
		let session_for_create_vault = Rc::clone(&session_master_key);
		let refresh_for_create_vault = Rc::clone(&refresh_list);
		sidebar_panel.create_vault_button.connect_clicked(move |_| {
			let create_window = gtk4::Window::builder()
				.title(crate::tr!("main-create-vault-window-title").as_str())
				.modal(true)
				.transient_for(&window_for_create_vault)
				.default_width(440)
				.default_height(140)
				.build();

			let root = gtk4::Box::builder()
				.orientation(Orientation::Vertical)
				.spacing(10)
				.margin_top(12)
				.margin_bottom(12)
				.margin_start(12)
				.margin_end(12)
				.build();
			let name_entry = gtk4::Entry::new();
			name_entry.set_placeholder_text(Some(crate::tr!("main-create-vault-name-placeholder").as_str()));

			let actions = gtk4::Box::builder()
				.orientation(Orientation::Horizontal)
				.spacing(8)
				.halign(Align::End)
				.build();
			let cancel = gtk4::Button::with_label(crate::tr!("common-cancel").as_str());
			let create = gtk4::Button::with_label(crate::tr!("main-create-vault-create").as_str());
			create.add_css_class("suggested-action");
			actions.append(&cancel);
			actions.append(&create);

			root.append(&name_entry);
			root.append(&actions);
			create_window.set_child(Some(&root));

			let create_window_for_cancel = create_window.clone();
			cancel.connect_clicked(move |_| create_window_for_cancel.close());

			let runtime_for_apply = runtime_for_create_vault.clone();
			let vault_for_apply = Arc::clone(&vault_service_for_create_vault);
			let session_for_apply = Rc::clone(&session_for_create_vault);
			let window_for_apply = window_for_create_vault.clone();
			let refresh_after_apply = Rc::clone(&refresh_for_create_vault);
			let create_window_for_apply = create_window.clone();
			create.connect_clicked(move |_| {
				let vault_name = name_entry.text().to_string();
				if vault_name.trim().is_empty() {
					Self::show_feedback_dialog(
						&window_for_apply,
						crate::tr!("main-create-vault-window-title").as_str(),
						crate::tr!("main-create-vault-error-empty-name").as_str(),
					);
					return;
				}

				let Some(master_key) = Self::snapshot_session_master_key(&session_for_apply) else {
					Self::show_feedback_dialog(
						&window_for_apply,
						crate::tr!("main-create-vault-window-title").as_str(),
						crate::tr!("main-create-vault-error-session-locked").as_str(),
					);
					return;
				};

				let (sender, receiver) = tokio::sync::oneshot::channel();
				let runtime_for_task = runtime_for_apply.clone();
				let vault_for_task = Arc::clone(&vault_for_apply);
				std::thread::spawn(move || {
					let result = runtime_for_task.block_on(async move {
						vault_for_task
							.create_vault(
								admin_user_id,
								vault_name.trim(),
								SecretBox::new(Box::new(master_key)),
							)
							.await
					});
					let _ = sender.send(result);
				});

				let window_for_result = window_for_apply.clone();
				let refresh_after_result = Rc::clone(&refresh_after_apply);
				let create_window_close = create_window_for_apply.clone();
				glib::MainContext::default().spawn_local(async move {
					match receiver.await {
						Ok(Ok(_)) => {
							create_window_close.close();
							refresh_after_result();
						}
						Ok(Err(error)) => {
							let message = error.to_string();
							Self::show_feedback_dialog(
								&window_for_result,
								crate::tr!("main-create-vault-window-title").as_str(),
								message.as_str(),
							);
						}
						Err(_) => {
							Self::show_feedback_dialog(
								&window_for_result,
								crate::tr!("main-create-vault-window-title").as_str(),
								crate::tr!("main-list-unavailable-description").as_str(),
							);
						}
					}
				});
			});

			create_window.present();
		});

			let profile_view = Self::build_profile_view(
			window.clone(),
			runtime_handle.clone(),
			Arc::clone(&user_service),
				Arc::clone(&totp_service),
			Arc::clone(&auth_policy_service),
			Arc::clone(&backup_service),
			Arc::clone(&import_service),
			Arc::clone(&secret_service),
			Arc::clone(&vault_service),
			database_path.clone(),
			admin_user_id,
			profile_button.clone(),
				Rc::clone(&critical_ops_in_flight),
			Rc::clone(&auto_lock_timeout_secs),
			Rc::clone(&auto_lock_source),
			Rc::clone(&auto_lock_armed),
			Rc::clone(&on_auto_lock),
			Rc::clone(&session_master_key),
			Rc::clone(&show_passwords_in_edit_pref),
			Rc::clone(&refresh_list),
			Rc::clone(&on_main_i18n_refresh_bridge),
		);
		center_panel
			.main_stack
			.add_titled(&profile_view.container, Some("profile_view"), crate::tr!("main-profile-security").as_str());

		let main_stack_for_back = center_panel.main_stack.clone();
		profile_view.back_button.connect_clicked(move |_| {
			main_stack_for_back.set_visible_child_name("entries_view");
		});

		let main_stack_for_profile = center_panel.main_stack.clone();
		sidebar_panel.profile_security_button.connect_clicked(move |_| {
			main_stack_for_profile.set_visible_child_name("profile_view");
		});

		let users_view_container = gtk4::ScrolledWindow::builder()
			.vexpand(true)
			.hexpand(true)
			.hscrollbar_policy(gtk4::PolicyType::Never)
			.build();
		let users_view_root = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(18)
			.margin_top(16)
			.margin_bottom(16)
			.margin_start(16)
			.margin_end(16)
			.build();
		users_view_root.add_css_class("profile-view-content");
		let users_header = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.build();
		users_header.add_css_class("profile-view-header");
		let users_back_button = gtk4::Button::builder()
			.label(crate::tr!("main-view-back").as_str())
			.icon_name("go-previous-symbolic")
			.build();
		users_back_button.add_css_class("flat");
		users_back_button.add_css_class("main-inline-back-button");
		users_back_button.set_halign(Align::Start);
		let users_title = gtk4::Label::new(Some(crate::tr!("main-users-view-title").as_str()));
		users_title.add_css_class("title-3");
		users_title.add_css_class("heading");
		users_title.add_css_class("main-section-title");
		users_title.set_hexpand(true);
		users_title.set_halign(Align::Center);
		users_header.append(&users_back_button);
		users_header.append(&users_title);
		users_view_root.append(&users_header);
		let users_intro = gtk4::Label::new(Some(crate::tr!("main-users-view-intro").as_str()));
		users_intro.set_halign(Align::Start);
		users_intro.set_wrap(true);
		users_intro.add_css_class("dim-label");
		users_view_root.append(&users_intro);
		if is_admin {
		let app_for_admin = application.clone();
		let window_for_admin = window.clone();
		let runtime_for_admin = runtime_handle.clone();
		let admin_for_admin = Arc::clone(&admin_service);
		let users_dialog = ManageUsersDialog::new(
			&app_for_admin,
			&window_for_admin,
			runtime_for_admin,
			Arc::clone(&admin_for_admin),
			Arc::clone(&vault_service),
			admin_user_id,
		);
		let users_content = users_dialog
			.take_content()
			.unwrap_or_else(|| gtk4::Box::new(Orientation::Vertical, 0).upcast::<gtk4::Widget>());
		let users_frame = gtk4::Frame::new(None);
		users_frame.add_css_class("profile-section-frame");
		users_frame.set_child(Some(&users_content));
		users_view_root.append(&users_frame);
		users_view_container.set_child(Some(&users_view_root));
		center_panel
			.main_stack
			.add_titled(
				&users_view_container,
				Some("users_view"),
				crate::tr!("main-user-nav").as_str(),
			);
		let main_stack_for_users_back = center_panel.main_stack.clone();
		users_back_button.connect_clicked(move |_| {
			main_stack_for_users_back.set_visible_child_name("entries_view");
		});
		let main_stack_for_users = center_panel.main_stack.clone();
		sidebar_panel.administration_button.connect_clicked(move |_| {
			main_stack_for_users.set_visible_child_name("users_view");
		});
		}

		let teams_view_container = gtk4::ScrolledWindow::builder()
			.vexpand(true)
			.hexpand(true)
			.hscrollbar_policy(gtk4::PolicyType::Never)
			.build();
		let teams_view_root = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(18)
			.margin_top(16)
			.margin_bottom(16)
			.margin_start(16)
			.margin_end(16)
			.build();
		teams_view_root.add_css_class("profile-view-content");
		let teams_header = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.build();
		teams_header.add_css_class("profile-view-header");
		let teams_back_button = gtk4::Button::builder()
			.label(crate::tr!("main-view-back").as_str())
			.icon_name("go-previous-symbolic")
			.build();
		teams_back_button.add_css_class("flat");
		teams_back_button.add_css_class("main-inline-back-button");
		teams_back_button.set_halign(Align::Start);
		let teams_title = gtk4::Label::new(Some(crate::tr!("main-teams-view-title").as_str()));
		teams_title.add_css_class("title-3");
		teams_title.add_css_class("heading");
		teams_title.add_css_class("main-section-title");
		teams_title.set_hexpand(true);
		teams_title.set_halign(Align::Center);
		teams_header.append(&teams_back_button);
		teams_header.append(&teams_title);
		teams_view_root.append(&teams_header);
		let teams_intro = gtk4::Label::new(Some(crate::tr!("main-teams-view-intro").as_str()));
		teams_intro.set_halign(Align::Start);
		teams_intro.set_wrap(true);
		teams_intro.add_css_class("dim-label");
		teams_view_root.append(&teams_intro);
		if is_admin {
		let app_for_teams = application.clone();
		let window_for_teams = window.clone();
		let runtime_for_teams = runtime_handle.clone();
		let team_for_teams = Arc::clone(&team_service);
		let vault_for_teams = Arc::clone(&vault_service);
		let master_for_teams = Rc::clone(&session_master_key);
		let active_vault_for_teams = Rc::clone(&active_vault_id);
		let refresh_for_teams = Rc::clone(&refresh_list);
		let teams_dialog = ManageTeamsDialog::new(
			&app_for_teams,
			&window_for_teams,
			runtime_for_teams,
			Arc::clone(&team_for_teams),
			Arc::clone(&vault_for_teams),
			admin_user_id,
			Rc::clone(&master_for_teams),
			Rc::clone(&active_vault_for_teams),
			Rc::clone(&refresh_for_teams),
		);
		let teams_content = teams_dialog
			.take_content()
			.unwrap_or_else(|| gtk4::Box::new(Orientation::Vertical, 0).upcast::<gtk4::Widget>());
		let teams_frame = gtk4::Frame::new(None);
		teams_frame.add_css_class("profile-section-frame");
		teams_frame.set_child(Some(&teams_content));
		teams_view_root.append(&teams_frame);
		teams_view_container.set_child(Some(&teams_view_root));
		center_panel
			.main_stack
			.add_titled(
				&teams_view_container,
				Some("teams_view"),
				crate::tr!("main-teams-nav").as_str(),
			);
		let main_stack_for_teams_back = center_panel.main_stack.clone();
		teams_back_button.connect_clicked(move |_| {
			main_stack_for_teams_back.set_visible_child_name("entries_view");
		});
		let main_stack_for_teams = center_panel.main_stack.clone();
		sidebar_panel.teams_button.connect_clicked(move |_| {
			main_stack_for_teams.set_visible_child_name("teams_view");
		});
		}

		sidebar_panel.administration_button.set_visible(is_admin);
		sidebar_panel.teams_button.set_visible(is_admin);

		let secret_editor_host = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.vexpand(true)
			.hexpand(true)
			.build();
		center_panel
			.main_stack
			.add_titled(
				&secret_editor_host,
				Some("secret_editor_view"),
				crate::tr!("main-stack-editor").as_str(),
			);

		let open_editor: Rc<dyn Fn(DialogMode)> = {
			let runtime_for_editor = runtime_handle.clone();
			let secret_for_editor = Arc::clone(&secret_service);
			let vault_for_editor = Arc::clone(&vault_service);
			let session_for_editor = Rc::clone(&session_master_key);
			let refresh_after_save = Rc::clone(&refresh_list);
			let toast_overlay_for_editor = toast_overlay.clone();
			let show_passwords_in_edit_pref = Rc::clone(&show_passwords_in_edit_pref);
			let stack_for_editor = center_panel.main_stack.clone();
			let host_for_editor = secret_editor_host.clone();
			Rc::new(move |mode| {
				let Some(master_key) = Self::snapshot_session_master_key(&session_for_editor) else {
					info!("secret editor blocked: session is locked");
					return;
				};

				while let Some(child) = host_for_editor.first_child() {
					host_for_editor.remove(&child);
				}

				let stack_for_cancel = stack_for_editor.clone();
				let inline_view = AddEditDialog::build_inline(
					runtime_for_editor.clone(),
					Arc::clone(&secret_for_editor),
					Arc::clone(&vault_for_editor),
					admin_user_id,
					master_key,
					show_passwords_in_edit_pref.get(),
					mode,
					move || {
						stack_for_cancel.set_visible_child_name("entries_view");
					},
					{
						let refresh_after_save = Rc::clone(&refresh_after_save);
						let toast_overlay_for_save = toast_overlay_for_editor.clone();
						move |saved_title: String| {
							refresh_after_save();
							let toast_message = messages::toast_secret_saved(saved_title.as_str());
							toast_overlay_for_save.add_toast(adw::Toast::new(toast_message.as_str()));
						}
					},
				);

				host_for_editor.append(&inline_view.container);
				stack_for_editor.set_visible_child_name("secret_editor_view");
			})
		};
		*editor_launcher.borrow_mut() = Some(open_editor.clone());

		// ── Bouton Urgence (Panic) ─────────────────────────────────────────
		// Place dans la zone de fin de la HeaderBar pour être visible mais
		// séparé des actions habituelles.
		let panic_button = gtk4::Button::new();
		panic_button.add_css_class("panic-badge");
		panic_button.set_tooltip_text(Some(crate::tr!("main-panic-tooltip").as_str()));

		let panic_inner = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(5)
			.valign(Align::Center)
			.build();
		let panic_icon = gtk4::Image::from_icon_name("system-shutdown-symbolic");
		panic_icon.add_css_class("panic-badge-label");
		let panic_lbl = gtk4::Label::new(Some(crate::tr!("main-panic-label").as_str()));
		panic_lbl.add_css_class("panic-badge-label");
		panic_inner.append(&panic_icon);
		panic_inner.append(&panic_lbl);
		panic_button.set_child(Some(&panic_inner));

		let window_for_panic = window.clone();
		panic_button.connect_clicked(move |_| {
			let dialog = adw::MessageDialog::new(
				Some(&window_for_panic),
				Some(crate::tr!("main-panic-title").as_str()),
				Some(crate::tr!("main-panic-body").as_str()),
			);
			dialog.add_response("cancel", crate::tr!("main-panic-cancel").as_str());
			dialog.add_response("wipe_exit", crate::tr!("main-panic-confirm").as_str());
			dialog.set_response_appearance(
				"wipe_exit",
				adw::ResponseAppearance::Destructive,
			);
			dialog.set_default_response(Some("cancel"));
			dialog.set_close_response("cancel");
			dialog.connect_response(None, |_dlg, response| {
				if response == "wipe_exit" {
					// Journalise l'événement avant la sortie.
					// DailyLogFileWriter est synchrone : le message est écrit
					// sur disque avant que process::exit ne termine le processus.
					info!("Panic mode activated - wiping memory and exiting");
					// Les SecretBox allouées dans les closures GTK seront
					// retirées de la mémoire virtuelle par le noyau lors de la
					// libération du tas du processus. L'OS zero-fill les pages
					// avant de les réattribuer (comportement garanti par Linux).
					std::process::exit(0);
				}
			});
			dialog.present();
		});

		let open_editor_for_add = open_editor.clone();
		let active_vault_for_add = Rc::clone(&active_vault_id);
		let runtime_for_add = runtime_handle.clone();
		let vault_service_for_add = Arc::clone(&vault_service);
		let window_for_add = window.clone();
		add_button.connect_clicked(move |_| {
			let maybe_vault_id = *active_vault_for_add.borrow();
			let Some(vault_id) = maybe_vault_id else {
				open_editor_for_add(DialogMode::Create);
				return;
			};

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let runtime_for_task = runtime_for_add.clone();
			let vault_for_task = Arc::clone(&vault_service_for_add);
			std::thread::spawn(move || {
				let result = runtime_for_task.block_on(async move {
					let access = vault_for_task
						.get_vault_access_for_user(admin_user_id, vault_id)
						.await?
						.ok_or_else(|| crate::errors::AppError::Authorization("vault access denied for this user".to_string()))?;
					let is_shared = access.vault.owner_user_id != admin_user_id;
					Ok::<bool, crate::errors::AppError>(!is_shared || access.role.can_admin())
				});
				let _ = sender.send(result);
			});

			let open_editor_for_result = open_editor_for_add.clone();
			let window_for_result = window_for_add.clone();
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok(Ok(true)) => {
						open_editor_for_result(DialogMode::CreateInVault(vault_id));
					}
					Ok(Ok(false)) => {
						Self::show_feedback_dialog(
							&window_for_result,
							crate::tr!("main-add-shared-denied-title").as_str(),
							crate::tr!("main-add-shared-denied-body").as_str(),
						);
					}
					_ => {
						Self::show_feedback_dialog(
							&window_for_result,
							crate::tr!("main-add-shared-denied-title").as_str(),
							crate::tr!("main-list-unavailable-description").as_str(),
						);
					}
				}
			});
		});
		let refresh_for_trash = Rc::clone(&refresh_list);
		header_bar.pack_start(&add_button);
		trash_button.connect_clicked(move |_| {
			let Some(master_key) = Self::snapshot_session_master_key(&session_master_for_trash) else {
				info!("trash access blocked: session is locked");
				return;
			};
			let refresh_after_trash = Rc::clone(&refresh_for_trash);
			let dialog = TrashDialog::new(
				&app_for_trash,
				&window_for_trash,
				runtime_for_trash.clone(),
				Arc::clone(&secret_for_trash),
				Arc::clone(&vault_for_trash),
				admin_user_for_trash,
				master_key,
				move || {
					refresh_after_trash();
				},
			);
			dialog.present();
		});
		header_bar.pack_start(&trash_button);
		header_bar.pack_end(&user_identity_box);
		header_bar.pack_end(&panic_button);
		root.append(&header_bar);

		let content = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(12)
			.margin_top(14)
			.margin_bottom(14)
			.margin_start(14)
			.margin_end(14)
			.build();

		let actions_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(12)
			.build();

		let search_entry = gtk4::SearchEntry::builder()
			.placeholder_text(crate::tr!("main-search-placeholder").as_str())
			.hexpand(true)
			.build();
		search_entry.add_css_class("main-search-entry");
		actions_row.append(&search_entry);

		let split = gtk4::Paned::builder()
			.orientation(Orientation::Horizontal)
			.wide_handle(true)
			.vexpand(true)
			.build();
		split.set_position(270);

		split.set_start_child(Some(&sidebar_panel.frame));

		split.set_end_child(Some(&center_panel.frame));

		content.append(&actions_row);
		content.append(&split);
		root.append(&content);
		toast_overlay.set_child(Some(&root));
		window.set_content(Some(&toast_overlay));

		let main_i18n_refresh: Rc<dyn Fn()> = {
			let sidebar_i18n_refresh = Rc::clone(&sidebar_i18n_refresh);
			let profile_button = profile_button.clone();
			let profile_title = profile_title.clone();
			let add_button = add_button.clone();
			let trash_button = trash_button.clone();
			let panic_button = panic_button.clone();
			let panic_lbl = panic_lbl.clone();
			let search_entry = search_entry.clone();
			let status_total_chip = center_panel.status_total_chip.clone();
			let status_non_compliant_chip = center_panel.status_non_compliant_chip.clone();
			let sort_recent_button = center_panel.sort_recent_button.clone();
			let sort_title_button = center_panel.sort_title_button.clone();
			let sort_risk_button = center_panel.sort_risk_button.clone();
			let filtered_status_page = center_panel.filtered_status_page.clone();
			let entries_stack = center_panel.stack.clone();
			let list_page = center_panel.list_page.clone();
			let empty_state = center_panel.empty_state.clone();
			let main_stack = center_panel.main_stack.clone();
			let profile_container = profile_view.container.clone();
			let secret_editor_host = secret_editor_host.clone();
			let users_view_container = users_view_container.clone();
			let teams_view_container = teams_view_container.clone();
			let users_back_button = users_back_button.clone();
			let users_title = users_title.clone();
			let users_intro = users_intro.clone();
			let teams_back_button = teams_back_button.clone();
			let teams_title = teams_title.clone();
			let teams_intro = teams_intro.clone();
			Rc::new(move || {
				sidebar_i18n_refresh();
				profile_button.set_tooltip_text(Some(crate::tr!("main-last-logins-tooltip").as_str()));
				profile_title.set_text(crate::tr!("main-last-logins-title").as_str());
				add_button.set_tooltip_text(Some(crate::tr!("main-add-tooltip").as_str()));
				trash_button.set_tooltip_text(Some(crate::tr!("main-trash-tooltip").as_str()));
				panic_button.set_tooltip_text(Some(crate::tr!("main-panic-tooltip").as_str()));
				panic_lbl.set_text(crate::tr!("main-panic-label").as_str());
				search_entry.set_placeholder_text(Some(crate::tr!("main-search-placeholder").as_str()));
				status_total_chip.set_tooltip_text(Some(crate::tr!("main-status-total-tooltip").as_str()));
				status_non_compliant_chip
					.set_tooltip_text(Some(crate::tr!("main-status-noncompliant-tooltip").as_str()));
				sort_recent_button.set_tooltip_text(Some(crate::tr!("main-sort-recent-tooltip").as_str()));
				sort_title_button.set_tooltip_text(Some(crate::tr!("main-sort-title-tooltip").as_str()));
				sort_risk_button.set_tooltip_text(Some(crate::tr!("main-sort-risk-tooltip").as_str()));

				filtered_status_page.set_title(crate::tr!("main-filtered-empty-title").as_str());
				filtered_status_page
					.set_description(Some(crate::tr!("main-filtered-empty-description").as_str()));

				entries_stack
					.page(&list_page)
					.set_title(crate::tr!("main-stack-grid").as_str());
				entries_stack
					.page(&empty_state)
					.set_title(crate::tr!("main-stack-empty").as_str());

				main_stack
					.page(&entries_stack)
					.set_title(crate::tr!("main-stack-secrets").as_str());
				main_stack
					.page(&profile_container)
					.set_title(crate::tr!("main-profile-security").as_str());
				if is_admin {
					main_stack
						.page(&users_view_container)
						.set_title(crate::tr!("main-user-nav").as_str());
					main_stack
						.page(&teams_view_container)
						.set_title(crate::tr!("main-teams-nav").as_str());
				}
				main_stack
					.page(&secret_editor_host)
					.set_title(crate::tr!("main-stack-editor").as_str());

				users_back_button.set_label(crate::tr!("main-view-back").as_str());
				users_title.set_text(crate::tr!("main-users-view-title").as_str());
				users_intro.set_text(crate::tr!("main-users-view-intro").as_str());
				teams_back_button.set_label(crate::tr!("main-view-back").as_str());
				teams_title.set_text(crate::tr!("main-teams-view-title").as_str());
				teams_intro.set_text(crate::tr!("main-teams-view-intro").as_str());
			})
		};
		*on_main_i18n_refresh.borrow_mut() = Some(Rc::clone(&main_i18n_refresh));
		on_main_i18n_refresh_bridge();

		Self::update_sort_button_states(
			&center_panel.sort_recent_button,
			&center_panel.sort_title_button,
			&center_panel.sort_risk_button,
			filter_runtime.selected_sort.get(),
		);

		let flow_for_recent_sort = center_panel.secret_flow.clone();
		let filter_for_recent_sort = filter_runtime.clone();
		let recent_button = center_panel.sort_recent_button.clone();
		let title_button = center_panel.sort_title_button.clone();
		let risk_button = center_panel.sort_risk_button.clone();
		center_panel.sort_recent_button.connect_clicked(move |_| {
			filter_for_recent_sort.selected_sort.set(SecretSortMode::Recent);
			Self::update_sort_button_states(
				&recent_button,
				&title_button,
				&risk_button,
				SecretSortMode::Recent,
			);
			Self::apply_filters(&flow_for_recent_sort, &filter_for_recent_sort);
		});

		let flow_for_title_sort = center_panel.secret_flow.clone();
		let filter_for_title_sort = filter_runtime.clone();
		let recent_button = center_panel.sort_recent_button.clone();
		let title_button = center_panel.sort_title_button.clone();
		let risk_button = center_panel.sort_risk_button.clone();
		center_panel.sort_title_button.connect_clicked(move |_| {
			filter_for_title_sort.selected_sort.set(SecretSortMode::Title);
			Self::update_sort_button_states(
				&recent_button,
				&title_button,
				&risk_button,
				SecretSortMode::Title,
			);
			Self::apply_filters(&flow_for_title_sort, &filter_for_title_sort);
		});

		let flow_for_risk_sort = center_panel.secret_flow.clone();
		let filter_for_risk_sort = filter_runtime.clone();
		let recent_button = center_panel.sort_recent_button.clone();
		let title_button = center_panel.sort_title_button.clone();
		let risk_button = center_panel.sort_risk_button.clone();
		center_panel.sort_risk_button.connect_clicked(move |_| {
			filter_for_risk_sort.selected_sort.set(SecretSortMode::Risk);
			Self::update_sort_button_states(
				&recent_button,
				&title_button,
				&risk_button,
				SecretSortMode::Risk,
			);
			Self::apply_filters(&flow_for_risk_sort, &filter_for_risk_sort);
		});

		let flow_for_search = center_panel.secret_flow.clone();
		let filter_for_search = filter_runtime.clone();
		search_entry.connect_search_changed(move |entry| {
			*filter_for_search.search_text.borrow_mut() = entry.text().to_string();
			Self::apply_filters(&flow_for_search, &filter_for_search);
		});

		let active_vault_for_my_list = Rc::clone(&active_vault_id);
		let other_shared_list = sidebar_panel.shared_vaults_list.clone();
		let refresh_for_my_list = {
			let app = application.clone();
			let parent_window = window.clone();
			let runtime = runtime_handle.clone();
			let secret_service = Arc::clone(&secret_service);
			let vault_service = Arc::clone(&vault_service);
			let toast_overlay = toast_overlay.clone();
			let session_master = Rc::clone(&session_master_key);
			let active_vault_id = Rc::clone(&active_vault_id);
			let secret_flow = secret_flow_for_refresh.clone();
			let stack = stack_for_refresh.clone();
			let empty_title = empty_title_for_refresh.clone();
			let empty_copy = empty_copy_for_refresh.clone();
			let filter_runtime = filter_runtime.clone();
			let editor_launcher = Rc::clone(&editor_launcher);
			Rc::new(move || {
				let Some(master_key) = Self::snapshot_session_master_key(&session_master) else {
					empty_title.set_text(crate::tr!("main-session-locked-title").as_str());
					empty_copy.set_text(crate::tr!("main-session-locked-description").as_str());
					stack.set_visible_child_name("empty");
					return;
				};
				Self::refresh_secret_flow(
					app.clone(),
					parent_window.clone(),
					runtime.clone(),
					Arc::clone(&secret_service),
					Arc::clone(&vault_service),
					admin_user_id,
					master_key,
					secret_flow.clone(),
					stack.clone(),
					empty_title.clone(),
					empty_copy.clone(),
					active_vault_id.clone(),
					toast_overlay.clone(),
					filter_runtime.clone(),
					editor_launcher.clone(),
				);
			})
		};
		let main_stack_for_my_list = center_panel.main_stack.clone();
		let sync_for_my_list = Rc::clone(&vault_selection_sync);
		let refresh_for_my_list_handler = Rc::clone(&refresh_for_my_list);
		let my_list_for_shared = sidebar_panel.my_vaults_list.clone();
		let active_vault_for_shared_list = Rc::clone(&active_vault_id);
		let sync_for_shared_list = Rc::clone(&vault_selection_sync);
		let refresh_for_shared_list_handler = Rc::clone(&refresh_for_my_list);
		let main_stack_for_shared_list = center_panel.main_stack.clone();
		sidebar_panel.my_vaults_list.connect_row_selected(move |_list, row_opt| {
			if sync_for_my_list.get() {
				return;
			}
			if let Some(row) = row_opt {
				if let Some(vault_id) = Self::vault_id_from_row(&row) {
					sync_for_my_list.set(true);
					other_shared_list.unselect_all();
					sync_for_my_list.set(false);
					*active_vault_for_my_list.borrow_mut() = Some(vault_id);
					main_stack_for_my_list.set_visible_child_name("entries_view");
					refresh_for_my_list_handler();
				}
			}
		});

		sidebar_panel.shared_vaults_list.connect_row_selected(move |_list, row_opt| {
			if sync_for_shared_list.get() {
				return;
			}
			if let Some(row) = row_opt {
				if let Some(vault_id) = Self::vault_id_from_row(&row) {
					sync_for_shared_list.set(true);
					my_list_for_shared.unselect_all();
					sync_for_shared_list.set(false);
					*active_vault_for_shared_list.borrow_mut() = Some(vault_id);
					main_stack_for_shared_list.set_visible_child_name("entries_view");
					refresh_for_shared_list_handler();
				}
			}
		});

		let flow_for_category = center_panel.secret_flow.clone();
		let filter_for_category = filter_runtime.clone();
		let main_stack_for_category = center_panel.main_stack.clone();
		sidebar_panel.category_list.connect_row_selected(move |_list, row_opt| {
			if let Some(row) = row_opt {
				main_stack_for_category.set_visible_child_name("entries_view");
				let category = match row.index() {
					1 => SecretCategoryFilter::Password,
					2 => SecretCategoryFilter::ApiToken,
					3 => SecretCategoryFilter::SshKey,
					4 => SecretCategoryFilter::SecureDocument,
					_ => SecretCategoryFilter::All,
				};
				filter_for_category.selected_category.set(category);
			}
			Self::apply_filters(&flow_for_category, &filter_for_category);
		});

		let flow_for_audit = center_panel.secret_flow.clone();
		let filter_for_audit = filter_runtime.clone();
		let main_stack_for_audit = center_panel.main_stack.clone();
		sidebar_panel.audit_list.connect_row_selected(move |_list, row_opt| {
			if let Some(row) = row_opt {
				main_stack_for_audit.set_visible_child_name("entries_view");
				let audit = match row.index() {
					1 => AuditFilter::Weak,
					2 => AuditFilter::Duplicate,
					_ => AuditFilter::All,
				};
				filter_for_audit.selected_audit.set(audit);
			}
			Self::apply_filters(&flow_for_audit, &filter_for_audit);
		});

		let key_controller = gtk4::EventControllerKey::new();
		let window_for_key = window.clone();
		let source_for_key = Rc::clone(&auto_lock_source);
		let armed_for_key = Rc::clone(&auto_lock_armed);
		let timeout_for_key = Rc::clone(&auto_lock_timeout_secs);
		let callback_for_key = Rc::clone(&on_auto_lock);
		let session_for_key = Rc::clone(&session_master_key);
		key_controller.connect_key_pressed(move |_controller, _key, _keycode, _state| {
			Self::reset_auto_lock_timer(
				&window_for_key,
				&source_for_key,
				&armed_for_key,
				timeout_for_key.get(),
				&callback_for_key,
				&session_for_key,
			);
			glib::Propagation::Proceed
		});
		window.add_controller(key_controller);

		let motion_controller = gtk4::EventControllerMotion::new();
		let window_for_motion = window.clone();
		let source_for_motion = Rc::clone(&auto_lock_source);
		let armed_for_motion = Rc::clone(&auto_lock_armed);
		let timeout_for_motion = Rc::clone(&auto_lock_timeout_secs);
		let callback_for_motion = Rc::clone(&on_auto_lock);
		let session_for_motion = Rc::clone(&session_master_key);
		motion_controller.connect_motion(move |_controller, _x, _y| {
			Self::reset_auto_lock_timer(
				&window_for_motion,
				&source_for_motion,
				&armed_for_motion,
				timeout_for_motion.get(),
				&callback_for_motion,
				&session_for_motion,
			);
		});
		window.add_controller(motion_controller);

		Self {
			window,
			secret_flow: secret_flow_for_struct,
			refresh_entries: Rc::clone(&refresh_list),
			auto_lock_timeout_secs,
			auto_lock_source,
			auto_lock_armed,
			session_master_key,
			on_auto_lock,
			on_logout,
		}
	}

	pub fn window(&self) -> &adw::ApplicationWindow {
		&self.window
	}

	pub fn set_on_auto_lock(&self, callback: Rc<dyn Fn()>) {
		*self.on_auto_lock.borrow_mut() = Some(callback);
	}

	pub fn set_session_master_key(&self, key: Vec<u8>) {
		let mut current = self.session_master_key.borrow_mut();
		current.zeroize();
		*current = key;
	}

	pub fn refresh_entries(&self) {
		(self.refresh_entries)();
	}

	pub fn activate_auto_lock(&self) {
		if self.auto_lock_timeout_secs.get() == 0 {
			self.auto_lock_armed.set(false);
			return;
		}
		self.auto_lock_armed.set(true);
		Self::reset_auto_lock_timer(
			&self.window,
			&self.auto_lock_source,
			&self.auto_lock_armed,
			self.auto_lock_timeout_secs.get(),
			&self.on_auto_lock,
			&self.session_master_key,
		);
	}

	pub fn set_auto_lock_timeout(&self, mins: u64) {
		let mins = match mins {
			0 | 1 | 5 | 10 | 15 | 30 => mins,
			_ => 5,
		};
		self.auto_lock_timeout_secs.set(mins.saturating_mul(60));
		if mins == 0 {
			self.deactivate_auto_lock();
			return;
		}
		if self.auto_lock_armed.get() {
			Self::reset_auto_lock_timer(
				&self.window,
				&self.auto_lock_source,
				&self.auto_lock_armed,
				self.auto_lock_timeout_secs.get(),
				&self.on_auto_lock,
				&self.session_master_key,
			);
		}
	}

	pub fn deactivate_auto_lock(&self) {
		self.auto_lock_armed.set(false);
		if let Some(source_id) = self.auto_lock_source.borrow_mut().take() {
			source_id.remove();
		}
	}

	pub fn clear_sensitive_session(&self) {
		self.deactivate_auto_lock();
		{
			let mut key = self.session_master_key.borrow_mut();
			key.zeroize();
			key.clear();
		}
		while let Some(child) = self.secret_flow.first_child() {
			self.secret_flow.remove(&child);
		}
	}

	pub fn set_on_logout(&self, callback: Rc<dyn Fn()>) {
		*self.on_logout.borrow_mut() = Some(callback);
	}

	pub fn trigger_logout(&self) {
		if let Some(callback) = self.on_logout.borrow().as_ref() {
			callback();
		}
	}

	fn snapshot_session_master_key(session_master_key: &Rc<RefCell<Vec<u8>>>) -> Option<Vec<u8>> {
		let key = session_master_key.borrow();
		if key.is_empty() {
			None
		} else {
			Some(key.clone())
		}
	}

	fn reset_auto_lock_timer(
		window: &adw::ApplicationWindow,
		auto_lock_source: &Rc<RefCell<Option<glib::SourceId>>>,
		auto_lock_armed: &Rc<Cell<bool>>,
		timeout_secs: u64,
		on_auto_lock: &Rc<RefCell<Option<Rc<dyn Fn()>>>>,
		session_master_key: &Rc<RefCell<Vec<u8>>>,
	) {
		if !auto_lock_armed.get() || !window.is_visible() || timeout_secs == 0 {
			return;
		}

		if let Some(source_id) = auto_lock_source.borrow_mut().take() {
			source_id.remove();
		}

		let auto_lock_source_for_timeout = Rc::clone(auto_lock_source);
		let auto_lock_armed_for_timeout = Rc::clone(auto_lock_armed);
		let on_auto_lock_for_timeout = Rc::clone(on_auto_lock);
		let session_master_for_timeout = Rc::clone(session_master_key);
		let source_id = glib::timeout_add_local_once(Duration::from_secs(timeout_secs), move || {
			if !auto_lock_armed_for_timeout.get() {
				return;
			}
			if let Some(active_source) = auto_lock_source_for_timeout.borrow_mut().take() {
				active_source.remove();
			}
			auto_lock_armed_for_timeout.set(false);
			{
				let mut key = session_master_for_timeout.borrow_mut();
				key.zeroize();
				key.clear();
			}
			info!("Auto-lock triggered due to inactivity");
			if let Some(callback) = on_auto_lock_for_timeout.borrow().as_ref() {
				callback();
			}
		});

		*auto_lock_source.borrow_mut() = Some(source_id);
	}

	fn evaluate_password_strength_label(secret_value: &str) -> String {
		if secret_value.len() >= 12 {
			let has_uppercase = secret_value.chars().any(|c| c.is_uppercase());
			let has_lowercase = secret_value.chars().any(|c| c.is_lowercase());
			let has_digit = secret_value.chars().any(|c| c.is_numeric());
			let has_special = secret_value.chars().any(|c| !c.is_alphanumeric());
			let complexity = [has_uppercase, has_lowercase, has_digit, has_special]
				.iter()
				.filter(|&&v| v)
				.count();
			if complexity >= 3 {
				return crate::tr!("main-strength-strong");
			}
		}
		crate::tr!("main-strength-weak")
	}

	fn apply_filters(secret_flow: &gtk4::FlowBox, filter_runtime: &FilterRuntime) {
		let (all_count, weak_count, duplicate_count, non_compliant_count) = {
			let store = filter_runtime.meta_by_widget.borrow();
			let all_count = store.len();
			let weak_count = store.values().filter(|meta| meta.is_weak).count();
			let duplicate_count = store.values().filter(|meta| meta.is_duplicate).count();
			let non_compliant_count = store
				.values()
				.filter(|meta| meta.is_weak || meta.is_duplicate)
				.count();
			(all_count, weak_count, duplicate_count, non_compliant_count)
		};

		Self::update_audit_badge(&filter_runtime.audit_all_count_label, all_count);
		Self::update_audit_badge(&filter_runtime.audit_weak_count_label, weak_count);
		Self::update_audit_badge(&filter_runtime.audit_duplicate_count_label, duplicate_count);
		Self::update_audit_badge(&filter_runtime.total_count_label, all_count);
		Self::update_audit_badge(&filter_runtime.non_compliant_count_label, non_compliant_count);

		secret_flow.invalidate_sort();
		secret_flow.invalidate_filter();

		let mut visible_count = 0;
		let mut cursor = secret_flow.first_child();
		while let Some(child) = cursor {
			if let Some(flow_child) = child.downcast_ref::<gtk4::FlowBoxChild>() {
				if flow_child.is_child_visible() {
					visible_count += 1;
				}
			}
			cursor = child.next_sibling();
		}

		filter_runtime
			.filtered_status_page
			.set_visible(visible_count == 0);
	}

	fn update_audit_badge(label: &gtk4::Label, value: usize) {
		let next_text = value.to_string();
		let current_text = label.text().to_string();
		if current_text == next_text {
			return;
		}

		label.set_text(&next_text);
		label.remove_css_class("audit-count-badge-pulse");
		label.add_css_class("audit-count-badge-pulse");

		let label_clone = label.clone();
		glib::timeout_add_local_once(Duration::from_millis(240), move || {
			label_clone.remove_css_class("audit-count-badge-pulse");
		});
	}

	fn update_sort_button_states(
		recent_button: &gtk4::Button,
		title_button: &gtk4::Button,
		risk_button: &gtk4::Button,
		selected_sort: SecretSortMode,
	) {
		for button in [recent_button, title_button, risk_button] {
			button.remove_css_class("vault-secret-sort-button-active");
		}

		match selected_sort {
			SecretSortMode::Recent => recent_button.add_css_class("vault-secret-sort-button-active"),
			SecretSortMode::Title => title_button.add_css_class("vault-secret-sort-button-active"),
			SecretSortMode::Risk => risk_button.add_css_class("vault-secret-sort-button-active"),
		}
	}

	fn normalize_search_text(raw: &str) -> String {
		let mut normalized = String::with_capacity(raw.len());
		for ch in raw.chars() {
			let mapped = match ch {
				'a'..='z' | '0'..='9' => ch,
				'A'..='Z' => ch.to_ascii_lowercase(),
				'À' | 'Á' | 'Â' | 'Ã' | 'Ä' | 'Å' | 'à' | 'á' | 'â' | 'ã' | 'ä' | 'å' => 'a',
				'Ç' | 'ç' => 'c',
				'È' | 'É' | 'Ê' | 'Ë' | 'è' | 'é' | 'ê' | 'ë' => 'e',
				'Ì' | 'Í' | 'Î' | 'Ï' | 'ì' | 'í' | 'î' | 'ï' => 'i',
				'Ñ' | 'ñ' => 'n',
				'Ò' | 'Ó' | 'Ô' | 'Õ' | 'Ö' | 'Ø' | 'ò' | 'ó' | 'ô' | 'õ' | 'ö' | 'ø' => 'o',
				'Ù' | 'Ú' | 'Û' | 'Ü' | 'ù' | 'ú' | 'û' | 'ü' => 'u',
				'Ý' | 'Ÿ' | 'ý' | 'ÿ' => 'y',
				'Æ' | 'æ' => 'a',
				'Œ' | 'œ' => 'o',
				_ => {
					if ch.is_whitespace() || ch == '-' || ch == '_' || ch == '.' || ch == '@' {
						' '
					} else {
						continue;
					}
				}
			};
			normalized.push(mapped);
		}
		normalized
			.split_whitespace()
			.collect::<Vec<&str>>()
			.join(" ")
	}

	fn within_one_edit(left: &str, right: &str) -> bool {
		let left_chars: Vec<char> = left.chars().collect();
		let right_chars: Vec<char> = right.chars().collect();
		let left_len = left_chars.len();
		let right_len = right_chars.len();

		if left_len.abs_diff(right_len) > 1 {
			return false;
		}

		let mut i = 0;
		let mut j = 0;
		let mut edits = 0_u8;

		while i < left_len && j < right_len {
			if left_chars[i] == right_chars[j] {
				i += 1;
				j += 1;
				continue;
			}

			edits += 1;
			if edits > 1 {
				return false;
			}

			if left_len > right_len {
				i += 1;
			} else if right_len > left_len {
				j += 1;
			} else {
				i += 1;
				j += 1;
			}
		}

		if i < left_len || j < right_len {
			edits += 1;
		}

		edits <= 1
	}

	fn token_matches_haystack(token: &str, haystack: &str) -> bool {
		if token.is_empty() {
			return true;
		}

		if haystack.contains(token) {
			return true;
		}

		if token.chars().count() < 4 {
			return false;
		}

		haystack
			.split_whitespace()
			.any(|word| Self::within_one_edit(token, word))
	}

	fn parse_search_terms(query: &str) -> Vec<(Option<String>, String)> {
		query
			.split_whitespace()
			.filter_map(|term| {
				let Some((raw_key, raw_value)) = term.split_once(':') else {
					let token = Self::normalize_search_text(term);
					if token.is_empty() {
						return None;
					}
					return Some((None, token));
				};

				if raw_key.is_empty() || raw_value.is_empty() {
					let token = Self::normalize_search_text(term);
					if token.is_empty() {
						return None;
					}
					return Some((None, token));
				}

				let value = Self::normalize_search_text(raw_value);
				if value.is_empty() {
					return None;
				}
				let key_normalized = Self::normalize_search_text(raw_key);

				let key = match key_normalized.as_str() {
					"title" | "titre" | "name" | "nom" => "title",
					"login" | "user" | "username" | "identifiant" => "login",
					"email" | "mail" => "email",
					"url" | "site" | "domaine" | "domain" => "url",
					"note" | "notes" => "notes",
					"category" | "categorie" | "cat" => "category",
					"tag" | "tags" => "tags",
					"type" | "kind" => "type",
					_ => return Some((None, Self::normalize_search_text(term))),
				};

				Some((Some(key.to_string()), value))
			})
			.filter(|(_, value)| !value.is_empty())
			.collect()
	}

	fn matches_search_term(meta: &SecretFilterMeta, term: &(Option<String>, String)) -> bool {
		let value = term.1.as_str();
		if value.is_empty() {
			return true;
		}

		match term.0.as_deref() {
			Some("title") => Self::token_matches_haystack(value, meta.title_text.as_str()),
			Some("login") => Self::token_matches_haystack(value, meta.login_text.as_str()),
			Some("email") => Self::token_matches_haystack(value, meta.email_text.as_str()),
			Some("url") => Self::token_matches_haystack(value, meta.url_text.as_str()),
			Some("notes") => Self::token_matches_haystack(value, meta.notes_text.as_str()),
			Some("category") => Self::token_matches_haystack(value, meta.category_text.as_str()),
			Some("tags") => Self::token_matches_haystack(value, meta.tags_text.as_str()),
			Some("type") => Self::token_matches_haystack(value, meta.type_text.as_str()),
			_ => Self::token_matches_haystack(value, meta.searchable_text.as_str()),
		}
	}

	fn show_feedback_dialog(parent: &adw::ApplicationWindow, title: &str, body: &str) {
		let dialog = adw::MessageDialog::new(Some(parent), Some(title), Some(body));
		dialog.add_response("ok", crate::tr!("common-ok").as_str());
		dialog.set_default_response(Some("ok"));
		dialog.set_close_response("ok");
		dialog.present();
	}

	fn set_inline_status(label: &gtk4::Label, message: &str, kind: &str) {
		label.remove_css_class("inline-status-loading");
		label.remove_css_class("inline-status-success");
		label.remove_css_class("inline-status-error");
		match kind {
			"loading" => label.add_css_class("inline-status-loading"),
			"success" => label.add_css_class("inline-status-success"),
			_ => label.add_css_class("inline-status-error"),
		}
		label.set_text(message);
		label.set_visible(true);

		if kind != "loading" {
			let label_for_hide = label.clone();
			glib::timeout_add_local_once(Duration::from_millis(3200), move || {
				label_for_hide.set_visible(false);
			});
		}
	}

	fn set_twofa_badge_state(label: &gtk4::Label, enabled: bool) {
		label.remove_css_class("status-role-admin");
		label.remove_css_class("status-role-user");
		if enabled {
			let text = messages::twofa_badge_enabled();
			label.set_text(text.as_str());
			label.add_css_class("status-role-admin");
		} else {
			let text = messages::twofa_badge_disabled();
			label.set_text(text.as_str());
			label.add_css_class("status-role-user");
		}
	}

	fn map_twofa_error(error: &crate::errors::AppError, fallback: &str) -> String {
		match error {
			crate::errors::AppError::Authorization(_) => {
				crate::tr!("twofa-error-invalid-clock")
			}
			crate::errors::AppError::Validation(message) => {
				if message.to_ascii_lowercase().contains("code") {
					crate::tr!("twofa-error-invalid-clock")
				} else {
					crate::tr!("twofa-error-invalid-setup")
				}
			}
			crate::errors::AppError::Storage(_) => {
				crate::tr!("twofa-error-storage")
			}
			crate::errors::AppError::Crypto(_) => {
				crate::tr!("twofa-error-crypto")
			}
			_ => fallback.to_string(),
		}
	}

	fn format_login_timestamp_fr(raw: &str) -> String {
		const MONTHS: [&str; 12] = [
			"janvier",
			"fevrier",
			"mars",
			"avril",
			"mai",
			"juin",
			"juillet",
			"aout",
			"septembre",
			"octobre",
			"novembre",
			"decembre",
		];

		let parsed_local = DateTime::parse_from_rfc3339(raw)
			.map(|value| value.with_timezone(&Local))
			.or_else(|_| {
				NaiveDateTime::parse_from_str(raw, "%Y-%m-%dT%H:%M:%S")
					.map(|naive| DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc).with_timezone(&Local))
			})
			.or_else(|_| {
				NaiveDateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S")
					.map(|naive| DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc).with_timezone(&Local))
			});

		match parsed_local {
			Ok(value) => {
				let month_label = MONTHS
					.get(value.month0() as usize)
					.copied()
					.unwrap_or("mois");
				format!("{} {} {} - {:02}h{:02}", value.day(), month_label, value.year(), value.hour(), value.minute())
			}
			Err(_) => raw.to_string(),
		}
	}

	fn refresh_login_history_popover(
		runtime_handle: Handle,
		database_pool: SqlitePool,
		user_id: Uuid,
		list_box: gtk4::Box,
	) {
		while let Some(child) = list_box.first_child() {
			list_box.remove(&child);
		}

		let loading_label = gtk4::Label::new(Some(crate::tr!("login-history-loading").as_str()));
		loading_label.set_halign(Align::Start);
		loading_label.add_css_class("profile-login-history-muted");
		list_box.append(&loading_label);

		let (sender, receiver) = tokio::sync::oneshot::channel();
		runtime_handle.spawn(async move {
			let result = list_recent_logins(&database_pool, user_id, 5).await;
			match result {
				Ok(entries) => {
					let _ = sender.send(Ok(entries));
				}
				Err(primary_err) => {
					warn!(
						user_id = %user_id,
						error = %primary_err,
						"login_history service path failed, falling back to direct SQL query"
					);
					let fallback_rows = sqlx::query(
						"SELECT login_at, ip_address, device_info
						 FROM login_history
						 WHERE user_id = ?1
						 ORDER BY login_at DESC
						 LIMIT 5",
					)
					.bind(user_id.to_string())
					.fetch_all(&database_pool)
					.await;

					match fallback_rows {
						Ok(rows) => {
							let mut entries = Vec::with_capacity(rows.len());
							for row in rows {
								let login_at: String = row.try_get("login_at").unwrap_or_default();
								let ip_address: Option<String> = row.try_get("ip_address").ok().flatten();
								let device_info: Option<String> = row.try_get("device_info").ok().flatten();
								entries.push(crate::services::login_history_service::LoginHistoryEntry {
									login_at,
									ip_address,
									device_info,
								});
							}
							let _ = sender.send(Ok(entries));
						}
						Err(fallback_err) => {
							warn!(
								user_id = %user_id,
								error = %fallback_err,
								"login_history fallback SQL query failed"
							);
							let _ = sender.send(Err(primary_err));
						}
					}
				}
			}
		});

		glib::MainContext::default().spawn_local(async move {
			while let Some(child) = list_box.first_child() {
				list_box.remove(&child);
			}

			match receiver.await {
				Ok(Ok(entries)) => {
					info!(user_id = %user_id, count = entries.len(), "login history loaded for popover");
					if entries.is_empty() {
						let row_label = gtk4::Label::new(Some(crate::tr!("login-history-empty").as_str()));
						row_label.set_halign(Align::Start);
						row_label.add_css_class("profile-login-history-muted");
						list_box.append(&row_label);
						return;
					}

					for entry in entries {
						let formatted_login = Self::format_login_timestamp_fr(entry.login_at.as_str());
						let mut line = formatted_login;
						if let Some(device) = entry
							.device_info
							.as_deref()
							.filter(|value| !value.trim().is_empty())
						{
							line.push_str("  •  ");
							line.push_str(device);
						} else if let Some(ip) = entry
							.ip_address
							.as_deref()
							.filter(|value| !value.trim().is_empty())
						{
							line.push_str("  •  ");
							line.push_str(ip);
						}

						let row_label = gtk4::Label::new(Some(line.as_str()));
						row_label.set_halign(Align::Start);
						row_label.set_xalign(0.0);
						row_label.add_css_class("profile-login-history-row");
						list_box.append(&row_label);
					}
				}
				_ => {
					let row_label = gtk4::Label::new(Some(crate::tr!("login-history-unavailable").as_str()));
					row_label.set_halign(Align::Start);
					row_label.add_css_class("profile-login-history-muted");
					list_box.append(&row_label);
				}
			}
		});
	}

	#[allow(clippy::too_many_arguments)]
	fn build_profile_view<TUser, TTotp, TPolicy, TBackup, TImport, TSecret, TVault>(
		window: adw::ApplicationWindow,
		runtime_handle: Handle,
		user_service: Arc<TUser>,
		totp_service: Arc<TTotp>,
		auth_policy_service: Arc<TPolicy>,
		backup_service: Arc<TBackup>,
		import_service: Arc<TImport>,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		database_path: PathBuf,
		user_id: Uuid,
		profile_badge: gtk4::MenuButton,
		critical_ops_in_flight: Rc<Cell<u32>>,
		auto_lock_timeout_secs: Rc<Cell<u64>>,
		auto_lock_source: Rc<RefCell<Option<glib::SourceId>>>,
		auto_lock_armed: Rc<Cell<bool>>,
		on_auto_lock: Rc<RefCell<Option<Rc<dyn Fn()>>>>,
		session_master_key: Rc<RefCell<Vec<u8>>>,
		show_passwords_in_edit_pref: Rc<Cell<bool>>,
		on_import_completed_refresh: Rc<dyn Fn()>,
		on_language_changed: Rc<dyn Fn()>,
	) -> ProfileViewWidgets
	where
		TUser: UserService + Send + Sync + 'static,
		TTotp: TotpService + Send + Sync + 'static,
		TPolicy: AuthPolicyService + Send + Sync + 'static,
		TBackup: BackupService + Send + Sync + 'static,
		TImport: ImportService + Send + Sync + 'static,
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
	{
		let container = gtk4::ScrolledWindow::builder()
			.vexpand(true)
			.hexpand(true)
			.hscrollbar_policy(gtk4::PolicyType::Never)
			.build();

		let content = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(18)
			.margin_top(16)
			.margin_bottom(16)
			.margin_start(16)
			.margin_end(16)
			.build();
		content.add_css_class("profile-view-content");

		let header = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.build();
		header.add_css_class("profile-view-header");
		let back_button = gtk4::Button::with_label(crate::tr!("profile-view-back").as_str());
		back_button.add_css_class("flat");
		back_button.set_halign(Align::Start);
		let title = gtk4::Label::new(Some(crate::tr!("profile-view-title").as_str()));
		title.add_css_class("title-3");
		title.add_css_class("heading");
		title.set_hexpand(true);
		title.set_halign(Align::Center);
		header.append(&back_button);
		header.append(&title);
		content.append(&header);

		let profile_intro = gtk4::Label::new(Some(crate::tr!("profile-view-intro").as_str()));
		profile_intro.set_halign(Align::Start);
		profile_intro.set_wrap(true);
		profile_intro.add_css_class("dim-label");
		content.append(&profile_intro);

		let sections_columns = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(18)
			.hexpand(true)
			.homogeneous(true)
			.build();
		sections_columns.add_css_class("profile-sections-columns");

		let sections_left = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(18)
			.hexpand(true)
			.build();
		sections_left.add_css_class("profile-sections-column");

		let sections_right = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(18)
			.hexpand(true)
			.build();
		sections_right.add_css_class("profile-sections-column");

		sections_columns.append(&sections_left);
		sections_columns.append(&sections_right);
		content.append(&sections_columns);

		let info_frame = gtk4::Frame::builder().label(crate::tr!("profile-section-info").as_str()).build();
		info_frame.add_css_class("profile-section-frame");
		let info_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();
		let info_subtitle = gtk4::Label::new(Some(crate::tr!("profile-section-info-subtitle").as_str()));
		info_subtitle.set_halign(Align::Start);
		info_subtitle.set_wrap(true);
		info_subtitle.add_css_class("profile-section-subtitle");
		info_subtitle.add_css_class("dim-label");
		info_box.append(&info_subtitle);
		let username_label = gtk4::Label::new(Some(crate::tr!("profile-field-username").as_str()));
		username_label.set_halign(Align::Start);
		username_label.add_css_class("profile-field-label");
		let username_entry = gtk4::Entry::new();
		username_entry.set_sensitive(false);
		username_entry.set_hexpand(true);
		username_entry.add_css_class("profile-field-entry");
		let display_label = gtk4::Label::new(Some(crate::tr!("profile-field-display-name").as_str()));
		display_label.set_halign(Align::Start);
		display_label.add_css_class("profile-field-label");
		let display_entry = gtk4::Entry::new();
		display_entry.set_hexpand(true);
		display_entry.add_css_class("profile-field-entry");
		let email_label = gtk4::Label::new(Some(crate::tr!("profile-field-email").as_str()));
		email_label.set_halign(Align::Start);
		email_label.add_css_class("profile-field-label");
		let email_entry = gtk4::Entry::new();
		email_entry.set_hexpand(true);
		email_entry.add_css_class("profile-field-entry");
		let language_label = gtk4::Label::new(Some(crate::tr!("profile-language-title").as_str()));
		language_label.set_halign(Align::Start);
		language_label.add_css_class("profile-field-label");
		let language_hint = gtk4::Label::new(Some(crate::tr!("profile-language-subtitle").as_str()));
		language_hint.set_halign(Align::Start);
		language_hint.set_wrap(true);
		language_hint.add_css_class("dim-label");
		language_hint.add_css_class("profile-section-subtitle");
		let language_items = gtk4::StringList::new(&[
			crate::tr!("language-option-fr").as_str(),
			crate::tr!("language-option-en").as_str(),
		]);
		let language_dropdown = gtk4::DropDown::new(Some(language_items.clone()), None::<gtk4::Expression>);
		language_dropdown.add_css_class("profile-field-entry");
		language_dropdown.set_selected(0);
		let current_email_pw_label = gtk4::Label::new(Some(crate::tr!("profile-field-current-password-email-change").as_str()));
		current_email_pw_label.set_halign(Align::Start);
		current_email_pw_label.add_css_class("profile-field-label");
		let current_email_pw_entry = gtk4::PasswordEntry::new();
		current_email_pw_entry.set_hexpand(true);
		current_email_pw_entry.add_css_class("profile-field-entry");
		let profile_status_label = gtk4::Label::new(None);
		profile_status_label.set_halign(Align::Start);
		profile_status_label.set_wrap(true);
		profile_status_label.add_css_class("inline-status");
		profile_status_label.add_css_class("profile-inline-status");
		profile_status_label.set_visible(false);
		let save_profile_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.hexpand(true)
			.halign(Align::End)
			.build();
		save_profile_row.add_css_class("profile-actions-row");
		let save_profile_button = gtk4::Button::with_label(crate::tr!("profile-save").as_str());
		save_profile_button.add_css_class("suggested-action");
		save_profile_button.add_css_class("profile-action-btn");
		save_profile_row.append(&save_profile_button);

		for widget in [
			username_label.upcast_ref::<gtk4::Widget>(),
			username_entry.upcast_ref::<gtk4::Widget>(),
			display_label.upcast_ref::<gtk4::Widget>(),
			display_entry.upcast_ref::<gtk4::Widget>(),
			email_label.upcast_ref::<gtk4::Widget>(),
			email_entry.upcast_ref::<gtk4::Widget>(),
			language_label.upcast_ref::<gtk4::Widget>(),
			language_dropdown.upcast_ref::<gtk4::Widget>(),
			language_hint.upcast_ref::<gtk4::Widget>(),
			current_email_pw_label.upcast_ref::<gtk4::Widget>(),
			current_email_pw_entry.upcast_ref::<gtk4::Widget>(),
			profile_status_label.upcast_ref::<gtk4::Widget>(),
			save_profile_row.upcast_ref::<gtk4::Widget>(),
		] {
			info_box.append(widget);
		}
		info_frame.set_child(Some(&info_box));
		info_frame.set_hexpand(true);
		sections_left.append(&info_frame);

		let password_change_frame = gtk4::Frame::builder().label(crate::tr!("profile-section-password-change").as_str()).build();
		password_change_frame.add_css_class("profile-section-frame");
		let password_change_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();
		let password_change_subtitle = gtk4::Label::new(Some(crate::tr!("profile-section-password-change-subtitle").as_str()));
		password_change_subtitle.set_halign(Align::Start);
		password_change_subtitle.set_wrap(true);
		password_change_subtitle.add_css_class("profile-section-subtitle");
		password_change_subtitle.add_css_class("dim-label");
		password_change_box.append(&password_change_subtitle);

		let current_pw_label = gtk4::Label::new(Some(crate::tr!("profile-field-current-password").as_str()));
		current_pw_label.set_halign(Align::Start);
		current_pw_label.add_css_class("profile-field-label");
		let current_pw_entry = gtk4::PasswordEntry::new();
		current_pw_entry.set_hexpand(true);
		current_pw_entry.add_css_class("profile-field-entry");

		let new_pw_label = gtk4::Label::new(Some(crate::tr!("profile-field-new-password").as_str()));
		new_pw_label.set_halign(Align::Start);
		new_pw_label.add_css_class("profile-field-label");
		let new_pw_entry = gtk4::PasswordEntry::new();
		new_pw_entry.set_hexpand(true);
		new_pw_entry.add_css_class("profile-field-entry");

		let confirm_pw_label = gtk4::Label::new(Some(crate::tr!("profile-field-confirm-new-password").as_str()));
		confirm_pw_label.set_halign(Align::Start);
		confirm_pw_label.add_css_class("profile-field-label");
		let confirm_pw_entry = gtk4::PasswordEntry::new();
		confirm_pw_entry.set_hexpand(true);
		confirm_pw_entry.add_css_class("profile-field-entry");

		let password_change_status_label = gtk4::Label::new(None);
		password_change_status_label.set_halign(Align::Start);
		password_change_status_label.set_wrap(true);
		password_change_status_label.add_css_class("inline-status");
		password_change_status_label.add_css_class("profile-inline-status");
		password_change_status_label.set_visible(false);

		let security_actions = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.hexpand(true)
			.halign(Align::End)
			.build();
		security_actions.add_css_class("profile-actions-row");
		let change_pw_button = gtk4::Button::with_label(crate::tr!("profile-change-button").as_str());
		change_pw_button.add_css_class("suggested-action");
		change_pw_button.add_css_class("profile-action-btn");
		change_pw_button.set_tooltip_text(Some(crate::tr!("profile-change-button-tooltip").as_str()));
		let rotate_master_key_button = gtk4::Button::with_label(crate::tr!("profile-rotate-button").as_str());
		rotate_master_key_button.add_css_class("suggested-action");
		rotate_master_key_button.add_css_class("profile-action-btn");
		rotate_master_key_button.set_tooltip_text(Some(crate::tr!("profile-rotate-button-tooltip").as_str()));
		security_actions.append(&change_pw_button);
		security_actions.append(&rotate_master_key_button);

		for widget in [
			current_pw_label.upcast_ref::<gtk4::Widget>(),
			current_pw_entry.upcast_ref::<gtk4::Widget>(),
			new_pw_label.upcast_ref::<gtk4::Widget>(),
			new_pw_entry.upcast_ref::<gtk4::Widget>(),
			confirm_pw_label.upcast_ref::<gtk4::Widget>(),
			confirm_pw_entry.upcast_ref::<gtk4::Widget>(),
			password_change_status_label.upcast_ref::<gtk4::Widget>(),
			security_actions.upcast_ref::<gtk4::Widget>(),
		] {
			password_change_box.append(widget);
		}
		password_change_frame.set_child(Some(&password_change_box));
		password_change_frame.set_hexpand(true);
		sections_right.append(&password_change_frame);

		let security_prefs_frame = gtk4::Frame::builder().label(crate::tr!("profile-section-security-prefs").as_str()).build();
		security_prefs_frame.add_css_class("profile-section-frame");
		let security_prefs_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();

		let auto_lock_label = gtk4::Label::new(Some(crate::tr!("profile-auto-lock-title").as_str()));
		auto_lock_label.set_halign(Align::Start);
		auto_lock_label.add_css_class("profile-field-label");
		let auto_lock_items = gtk4::StringList::new(&[
			crate::tr!("profile-auto-lock-1").as_str(),
			crate::tr!("profile-auto-lock-5").as_str(),
			crate::tr!("profile-auto-lock-15").as_str(),
			crate::tr!("profile-auto-lock-30").as_str(),
			crate::tr!("profile-auto-lock-never").as_str(),
		]);
		let auto_lock_dropdown = gtk4::DropDown::new(Some(auto_lock_items.clone()), None::<gtk4::Expression>);
		auto_lock_dropdown.add_css_class("profile-field-entry");

		let show_edit_passwords_label = gtk4::Label::new(Some(crate::tr!("profile-show-edit-passwords-title").as_str()));
		show_edit_passwords_label.set_halign(Align::Start);
		show_edit_passwords_label.add_css_class("profile-field-label");
		let show_edit_passwords_hint = gtk4::Label::new(Some(crate::tr!("profile-show-edit-passwords-hint").as_str()));
		show_edit_passwords_hint.set_halign(Align::Start);
		show_edit_passwords_hint.set_wrap(true);
		show_edit_passwords_hint.add_css_class("dim-label");
		show_edit_passwords_hint.add_css_class("profile-section-subtitle");
		let show_edit_passwords_switch = gtk4::Switch::new();
		show_edit_passwords_switch.set_halign(Align::Start);

		let security_prefs_status_label = gtk4::Label::new(None);
		security_prefs_status_label.set_halign(Align::Start);
		security_prefs_status_label.set_wrap(true);
		security_prefs_status_label.add_css_class("inline-status");
		security_prefs_status_label.add_css_class("profile-inline-status");
		security_prefs_status_label.set_visible(false);

		for widget in [
			auto_lock_label.upcast_ref::<gtk4::Widget>(),
			auto_lock_dropdown.upcast_ref::<gtk4::Widget>(),
			show_edit_passwords_label.upcast_ref::<gtk4::Widget>(),
			show_edit_passwords_switch.upcast_ref::<gtk4::Widget>(),
			show_edit_passwords_hint.upcast_ref::<gtk4::Widget>(),
			security_prefs_status_label.upcast_ref::<gtk4::Widget>(),
		] {
			security_prefs_box.append(widget);
		}
		security_prefs_frame.set_child(Some(&security_prefs_box));
		security_prefs_frame.set_hexpand(true);
		sections_right.append(&security_prefs_frame);

		let twofa_frame = gtk4::Frame::new(None);
		twofa_frame.add_css_class("profile-section-frame");
		let twofa_header = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();
		let twofa_title = gtk4::Label::new(Some(crate::tr!("profile-section-2fa-title").as_str()));
		twofa_title.add_css_class("profile-field-label");
		twofa_title.set_halign(Align::Start);
		let twofa_badge_text = messages::twofa_badge_disabled();
		let twofa_state_badge = gtk4::Label::new(Some(twofa_badge_text.as_str()));
		twofa_state_badge.add_css_class("status-role-pill");
		twofa_state_badge.add_css_class("status-role-user");
		twofa_state_badge.set_halign(Align::Start);
		twofa_header.append(&twofa_title);
		twofa_header.append(&twofa_state_badge);
		twofa_frame.set_label_widget(Some(&twofa_header));
		Self::set_twofa_badge_state(&twofa_state_badge, false);
		let twofa_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();

		let twofa_stack = gtk4::Stack::builder()
			.hexpand(true)
			.transition_type(gtk4::StackTransitionType::Crossfade)
			.build();

		let twofa_disabled_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.build();
		let twofa_disabled_copy = gtk4::Label::new(Some(crate::tr!("profile-2fa-disabled-copy").as_str()));
		twofa_disabled_copy.set_halign(Align::Start);
		twofa_disabled_copy.set_wrap(true);
		twofa_disabled_copy.add_css_class("dim-label");
		twofa_disabled_copy.add_css_class("profile-section-subtitle");
		let twofa_activate_button = gtk4::Button::with_label(crate::tr!("profile-2fa-activate").as_str());
		twofa_activate_button.add_css_class("suggested-action");
		twofa_activate_button.add_css_class("profile-action-btn");
		twofa_activate_button.set_halign(Align::Start);
		twofa_disabled_box.append(&twofa_disabled_copy);
		twofa_disabled_box.append(&twofa_activate_button);

		let twofa_setup_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.build();
		let twofa_setup_copy = gtk4::Label::new(Some(crate::tr!("profile-2fa-setup-copy").as_str()));
		twofa_setup_copy.set_halign(Align::Start);
		twofa_setup_copy.set_wrap(true);
		twofa_setup_copy.add_css_class("dim-label");
		twofa_setup_copy.add_css_class("profile-section-subtitle");
		let twofa_qr_picture = gtk4::Picture::new();
		twofa_qr_picture.set_size_request(200, 200);
		twofa_qr_picture.add_css_class("totp-qr-container");
		let twofa_secret_label = gtk4::Label::new(Some(crate::tr!("profile-2fa-secret-base32").as_str()));
		twofa_secret_label.set_halign(Align::Start);
		twofa_secret_label.add_css_class("profile-field-label");
		let twofa_secret_entry = gtk4::Entry::new();
		twofa_secret_entry.set_editable(false);
		twofa_secret_entry.add_css_class("profile-field-entry");
		let twofa_code_label = gtk4::Label::new(Some(crate::tr!("profile-2fa-code").as_str()));
		twofa_code_label.set_halign(Align::Start);
		twofa_code_label.add_css_class("profile-field-label");
		let twofa_code_entry = gtk4::Entry::new();
		twofa_code_entry.set_input_purpose(gtk4::InputPurpose::Digits);
		twofa_code_entry.set_max_length(6);
		twofa_code_entry.add_css_class("profile-field-entry");
		let twofa_setup_actions = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();
		twofa_setup_actions.add_css_class("profile-actions-row");
		let twofa_confirm_button = gtk4::Button::with_label(crate::tr!("profile-2fa-confirm").as_str());
		twofa_confirm_button.add_css_class("suggested-action");
		twofa_confirm_button.add_css_class("profile-action-btn");
		let twofa_cancel_setup_button = gtk4::Button::with_label(crate::tr!("profile-2fa-cancel").as_str());
		twofa_cancel_setup_button.add_css_class("flat");
		twofa_cancel_setup_button.add_css_class("profile-action-btn");
		twofa_setup_actions.append(&twofa_confirm_button);
		twofa_setup_actions.append(&twofa_cancel_setup_button);
		for widget in [
			twofa_setup_copy.upcast_ref::<gtk4::Widget>(),
			twofa_qr_picture.upcast_ref::<gtk4::Widget>(),
			twofa_secret_label.upcast_ref::<gtk4::Widget>(),
			twofa_secret_entry.upcast_ref::<gtk4::Widget>(),
			twofa_code_label.upcast_ref::<gtk4::Widget>(),
			twofa_code_entry.upcast_ref::<gtk4::Widget>(),
			twofa_setup_actions.upcast_ref::<gtk4::Widget>(),
		] {
			twofa_setup_box.append(widget);
		}

		let twofa_enabled_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.build();
		let twofa_enabled_copy = gtk4::Label::new(Some(crate::tr!("profile-2fa-enabled-copy").as_str()));
		twofa_enabled_copy.set_halign(Align::Start);
		twofa_enabled_copy.set_wrap(true);
		twofa_enabled_copy.add_css_class("dim-label");
		twofa_enabled_copy.add_css_class("profile-section-subtitle");
		let twofa_disable_toggle_button = gtk4::Button::with_label(crate::tr!("profile-2fa-disable").as_str());
		twofa_disable_toggle_button.add_css_class("flat");
		twofa_disable_toggle_button.add_css_class("profile-action-btn");
		twofa_disable_toggle_button.set_halign(Align::Start);
		let twofa_disable_confirm_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.visible(false)
			.build();
		twofa_disable_confirm_row.add_css_class("profile-actions-row");
		let twofa_disable_confirm_button = gtk4::Button::with_label(crate::tr!("profile-2fa-disable-confirm").as_str());
		twofa_disable_confirm_button.add_css_class("suggested-action");
		twofa_disable_confirm_button.add_css_class("profile-action-btn");
		let twofa_disable_cancel_button = gtk4::Button::with_label(crate::tr!("profile-2fa-cancel").as_str());
		twofa_disable_cancel_button.add_css_class("flat");
		twofa_disable_cancel_button.add_css_class("profile-action-btn");
		twofa_disable_confirm_row.append(&twofa_disable_confirm_button);
		twofa_disable_confirm_row.append(&twofa_disable_cancel_button);
		twofa_enabled_box.append(&twofa_enabled_copy);
		twofa_enabled_box.append(&twofa_disable_toggle_button);
		twofa_enabled_box.append(&twofa_disable_confirm_row);

		twofa_stack.add_titled(&twofa_disabled_box, Some("disabled"), crate::tr!("profile-2fa-stack-disabled").as_str());
		twofa_stack.add_titled(&twofa_setup_box, Some("setup"), crate::tr!("profile-2fa-stack-setup").as_str());
		twofa_stack.add_titled(&twofa_enabled_box, Some("enabled"), crate::tr!("profile-2fa-stack-enabled").as_str());
		twofa_stack.set_visible_child_name("disabled");

		let twofa_status_label = gtk4::Label::new(None);
		twofa_status_label.set_halign(Align::Start);
		twofa_status_label.set_wrap(true);
		twofa_status_label.add_css_class("inline-status");
		twofa_status_label.add_css_class("profile-inline-status");
		twofa_status_label.set_visible(false);

		twofa_box.append(&twofa_stack);
		twofa_box.append(&twofa_status_label);
		twofa_frame.set_child(Some(&twofa_box));
		twofa_frame.set_hexpand(true);
		sections_right.append(&twofa_frame);

		let data_frame = gtk4::Frame::builder().label(crate::tr!("profile-section-data").as_str()).build();
		data_frame.add_css_class("profile-section-frame");
		let data_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();
		let export_title = gtk4::Label::new(Some(crate::tr!("profile-export-title").as_str()));
		export_title.set_halign(Align::Start);
		export_title.add_css_class("heading");
		export_title.add_css_class("profile-field-label");
		let export_subtitle = gtk4::Label::new(Some(crate::tr!("profile-export-subtitle").as_str()));
		export_subtitle.set_halign(Align::Start);
		export_subtitle.add_css_class("dim-label");
		export_subtitle.add_css_class("profile-section-subtitle");
		export_subtitle.set_wrap(true);
		let export_button = gtk4::Button::with_label(crate::tr!("profile-export-button").as_str());
		export_button.add_css_class("suggested-action");
		export_button.add_css_class("profile-action-btn");
		export_button.set_halign(Align::End);

		let import_title = gtk4::Label::new(Some(crate::tr!("profile-import-title").as_str()));
		import_title.set_halign(Align::Start);
		import_title.add_css_class("heading");
		import_title.add_css_class("profile-field-label");
		let import_subtitle = gtk4::Label::new(Some(crate::tr!("profile-import-subtitle").as_str()));
		import_subtitle.set_halign(Align::Start);
		import_subtitle.add_css_class("dim-label");
		import_subtitle.add_css_class("profile-section-subtitle");
		import_subtitle.set_wrap(true);
		let import_button = gtk4::Button::with_label(crate::tr!("profile-import-button").as_str());
		import_button.add_css_class("suggested-action");
		import_button.add_css_class("profile-action-btn");
		import_button.set_halign(Align::End);

		for widget in [
			export_title.upcast_ref::<gtk4::Widget>(),
			export_subtitle.upcast_ref::<gtk4::Widget>(),
			export_button.upcast_ref::<gtk4::Widget>(),
			import_title.upcast_ref::<gtk4::Widget>(),
			import_subtitle.upcast_ref::<gtk4::Widget>(),
			import_button.upcast_ref::<gtk4::Widget>(),
		] {
			data_box.append(widget);
		}
		data_frame.set_child(Some(&data_box));
		data_frame.set_hexpand(true);
		sections_left.append(&data_frame);

		container.set_child(Some(&content));

		let back_button_for_i18n = back_button.clone();
		let title_for_i18n = title.clone();
		let intro_for_i18n = profile_intro.clone();
		let info_frame_for_i18n = info_frame.clone();
		let info_subtitle_for_i18n = info_subtitle.clone();
		let username_label_for_i18n = username_label.clone();
		let display_label_for_i18n = display_label.clone();
		let email_label_for_i18n = email_label.clone();
		let language_label_for_i18n = language_label.clone();
		let language_hint_for_i18n = language_hint.clone();
		let language_dropdown_for_i18n = language_dropdown.clone();
		let language_items_for_i18n = language_items.clone();
		let current_email_pw_label_for_i18n = current_email_pw_label.clone();
		let save_profile_button_for_i18n = save_profile_button.clone();

		let password_change_frame_for_i18n = password_change_frame.clone();
		let password_change_subtitle_for_i18n = password_change_subtitle.clone();
		let current_pw_label_for_i18n = current_pw_label.clone();
		let new_pw_label_for_i18n = new_pw_label.clone();
		let confirm_pw_label_for_i18n = confirm_pw_label.clone();
		let change_pw_button_for_i18n = change_pw_button.clone();
		let rotate_master_key_button_for_i18n = rotate_master_key_button.clone();

		let security_prefs_frame_for_i18n = security_prefs_frame.clone();
		let auto_lock_label_for_i18n = auto_lock_label.clone();
		let auto_lock_dropdown_for_i18n = auto_lock_dropdown.clone();
		let auto_lock_items_for_i18n = auto_lock_items.clone();
		let show_edit_passwords_label_for_i18n = show_edit_passwords_label.clone();
		let show_edit_passwords_hint_for_i18n = show_edit_passwords_hint.clone();

		let twofa_title_for_i18n = twofa_title.clone();
		let twofa_disabled_copy_for_i18n = twofa_disabled_copy.clone();
		let twofa_activate_button_for_i18n = twofa_activate_button.clone();
		let twofa_setup_copy_for_i18n = twofa_setup_copy.clone();
		let twofa_secret_label_for_i18n = twofa_secret_label.clone();
		let twofa_code_label_for_i18n = twofa_code_label.clone();
		let twofa_confirm_button_for_i18n = twofa_confirm_button.clone();
		let twofa_cancel_setup_button_for_i18n = twofa_cancel_setup_button.clone();
		let twofa_enabled_copy_for_i18n = twofa_enabled_copy.clone();
		let twofa_disable_toggle_button_for_i18n = twofa_disable_toggle_button.clone();
		let twofa_disable_confirm_button_for_i18n = twofa_disable_confirm_button.clone();
		let twofa_disable_cancel_button_for_i18n = twofa_disable_cancel_button.clone();
		let twofa_stack_for_i18n = twofa_stack.clone();
		let twofa_disabled_box_for_i18n = twofa_disabled_box.clone();
		let twofa_setup_box_for_i18n = twofa_setup_box.clone();
		let twofa_enabled_box_for_i18n = twofa_enabled_box.clone();
		let twofa_badge_for_i18n = twofa_state_badge.clone();

		let data_frame_for_i18n = data_frame.clone();
		let export_title_for_i18n = export_title.clone();
		let export_subtitle_for_i18n = export_subtitle.clone();
		let export_button_for_i18n = export_button.clone();
		let import_title_for_i18n = import_title.clone();
		let import_subtitle_for_i18n = import_subtitle.clone();
		let import_button_for_i18n = import_button.clone();

		let on_language_changed_for_i18n = Rc::clone(&on_language_changed);
		let apply_profile_i18n: Rc<dyn Fn()> = Rc::new(move || {
			back_button_for_i18n.set_label(crate::tr!("profile-view-back").as_str());
			title_for_i18n.set_text(crate::tr!("profile-view-title").as_str());
			intro_for_i18n.set_text(crate::tr!("profile-view-intro").as_str());

			info_frame_for_i18n.set_label(Some(crate::tr!("profile-section-info").as_str()));
			info_subtitle_for_i18n.set_text(crate::tr!("profile-section-info-subtitle").as_str());
			username_label_for_i18n.set_text(crate::tr!("profile-field-username").as_str());
			display_label_for_i18n.set_text(crate::tr!("profile-field-display-name").as_str());
			email_label_for_i18n.set_text(crate::tr!("profile-field-email").as_str());
			language_label_for_i18n.set_text(crate::tr!("profile-language-title").as_str());
			language_hint_for_i18n.set_text(crate::tr!("profile-language-subtitle").as_str());
			current_email_pw_label_for_i18n
				.set_text(crate::tr!("profile-field-current-password-email-change").as_str());
			save_profile_button_for_i18n.set_label(crate::tr!("profile-save").as_str());

			let lang_selected = language_dropdown_for_i18n.selected();
			language_items_for_i18n.splice(
				0,
				language_items_for_i18n.n_items(),
				&[
					crate::tr!("language-option-fr").as_str(),
					crate::tr!("language-option-en").as_str(),
				],
			);
			language_dropdown_for_i18n.set_selected(lang_selected.min(1));

			password_change_frame_for_i18n
				.set_label(Some(crate::tr!("profile-section-password-change").as_str()));
			password_change_subtitle_for_i18n
				.set_text(crate::tr!("profile-section-password-change-subtitle").as_str());
			current_pw_label_for_i18n.set_text(crate::tr!("profile-field-current-password").as_str());
			new_pw_label_for_i18n.set_text(crate::tr!("profile-field-new-password").as_str());
			confirm_pw_label_for_i18n
				.set_text(crate::tr!("profile-field-confirm-new-password").as_str());
			change_pw_button_for_i18n.set_label(crate::tr!("profile-change-button").as_str());
			change_pw_button_for_i18n
				.set_tooltip_text(Some(crate::tr!("profile-change-button-tooltip").as_str()));
			rotate_master_key_button_for_i18n.set_label(crate::tr!("profile-rotate-button").as_str());
			rotate_master_key_button_for_i18n
				.set_tooltip_text(Some(crate::tr!("profile-rotate-button-tooltip").as_str()));

			security_prefs_frame_for_i18n
				.set_label(Some(crate::tr!("profile-section-security-prefs").as_str()));
			auto_lock_label_for_i18n.set_text(crate::tr!("profile-auto-lock-title").as_str());
			let auto_lock_selected = auto_lock_dropdown_for_i18n.selected();
			auto_lock_items_for_i18n.splice(
				0,
				auto_lock_items_for_i18n.n_items(),
				&[
					crate::tr!("profile-auto-lock-1").as_str(),
					crate::tr!("profile-auto-lock-5").as_str(),
					crate::tr!("profile-auto-lock-15").as_str(),
					crate::tr!("profile-auto-lock-30").as_str(),
					crate::tr!("profile-auto-lock-never").as_str(),
				],
			);
			auto_lock_dropdown_for_i18n.set_selected(auto_lock_selected.min(4));
			show_edit_passwords_label_for_i18n
				.set_text(crate::tr!("profile-show-edit-passwords-title").as_str());
			show_edit_passwords_hint_for_i18n
				.set_text(crate::tr!("profile-show-edit-passwords-hint").as_str());

			twofa_title_for_i18n.set_text(crate::tr!("profile-section-2fa-title").as_str());
			twofa_disabled_copy_for_i18n.set_text(crate::tr!("profile-2fa-disabled-copy").as_str());
			twofa_activate_button_for_i18n.set_label(crate::tr!("profile-2fa-activate").as_str());
			twofa_setup_copy_for_i18n.set_text(crate::tr!("profile-2fa-setup-copy").as_str());
			twofa_secret_label_for_i18n.set_text(crate::tr!("profile-2fa-secret-base32").as_str());
			twofa_code_label_for_i18n.set_text(crate::tr!("profile-2fa-code").as_str());
			twofa_confirm_button_for_i18n.set_label(crate::tr!("profile-2fa-confirm").as_str());
			twofa_cancel_setup_button_for_i18n.set_label(crate::tr!("profile-2fa-cancel").as_str());
			twofa_enabled_copy_for_i18n.set_text(crate::tr!("profile-2fa-enabled-copy").as_str());
			twofa_disable_toggle_button_for_i18n.set_label(crate::tr!("profile-2fa-disable").as_str());
			twofa_disable_confirm_button_for_i18n
				.set_label(crate::tr!("profile-2fa-disable-confirm").as_str());
			twofa_disable_cancel_button_for_i18n.set_label(crate::tr!("profile-2fa-cancel").as_str());
			twofa_stack_for_i18n
				.page(&twofa_disabled_box_for_i18n)
				.set_title(crate::tr!("profile-2fa-stack-disabled").as_str());
			twofa_stack_for_i18n
				.page(&twofa_setup_box_for_i18n)
				.set_title(crate::tr!("profile-2fa-stack-setup").as_str());
			twofa_stack_for_i18n
				.page(&twofa_enabled_box_for_i18n)
				.set_title(crate::tr!("profile-2fa-stack-enabled").as_str());
			let is_twofa_enabled = twofa_stack_for_i18n
				.visible_child_name()
				.as_ref()
				.map_or(false, |name| name == "enabled");
			Self::set_twofa_badge_state(&twofa_badge_for_i18n, is_twofa_enabled);

			data_frame_for_i18n.set_label(Some(crate::tr!("profile-section-data").as_str()));
			export_title_for_i18n.set_text(crate::tr!("profile-export-title").as_str());
			export_subtitle_for_i18n.set_text(crate::tr!("profile-export-subtitle").as_str());
			export_button_for_i18n.set_label(crate::tr!("profile-export-button").as_str());
			import_title_for_i18n.set_text(crate::tr!("profile-import-title").as_str());
			import_subtitle_for_i18n.set_text(crate::tr!("profile-import-subtitle").as_str());
			import_button_for_i18n.set_label(crate::tr!("profile-import-button").as_str());

			on_language_changed_for_i18n();
		});
		apply_profile_i18n();

		let content_for_compact = content.clone();
		let sections_columns_for_compact = sections_columns.clone();
		let save_row_for_compact = save_profile_row.clone();
		let security_actions_for_compact = security_actions.clone();
		let save_btn_for_compact = save_profile_button.clone();
		let change_btn_for_compact = change_pw_button.clone();
		let rotate_btn_for_compact = rotate_master_key_button.clone();
		let export_btn_for_compact = export_button.clone();
		let import_btn_for_compact = import_button.clone();
		container.add_tick_callback(move |widget, _clock| {
			if widget.allocated_width() < 760 {
				content_for_compact.add_css_class("profile-compact");
				sections_columns_for_compact.set_orientation(Orientation::Vertical);
				sections_columns_for_compact.set_homogeneous(false);
				save_row_for_compact.set_orientation(Orientation::Vertical);
				save_row_for_compact.set_halign(Align::Fill);
				security_actions_for_compact.set_orientation(Orientation::Vertical);
				security_actions_for_compact.set_halign(Align::Fill);

				for button in [
					save_btn_for_compact.clone(),
					change_btn_for_compact.clone(),
					rotate_btn_for_compact.clone(),
					export_btn_for_compact.clone(),
					import_btn_for_compact.clone(),
				] {
					button.set_hexpand(true);
					button.set_halign(Align::Fill);
				}
			} else {
				content_for_compact.remove_css_class("profile-compact");
				sections_columns_for_compact.set_orientation(Orientation::Horizontal);
				sections_columns_for_compact.set_homogeneous(true);
				save_row_for_compact.set_orientation(Orientation::Horizontal);
				save_row_for_compact.set_halign(Align::End);
				security_actions_for_compact.set_orientation(Orientation::Horizontal);
				security_actions_for_compact.set_halign(Align::End);

				for button in [
					save_btn_for_compact.clone(),
					change_btn_for_compact.clone(),
					rotate_btn_for_compact.clone(),
					export_btn_for_compact.clone(),
					import_btn_for_compact.clone(),
				] {
					button.set_hexpand(false);
					button.set_halign(Align::End);
				}
			}
			glib::ControlFlow::Continue
		});

		let begin_critical_operation: Rc<dyn Fn()> = {
			let counter = Rc::clone(&critical_ops_in_flight);
			let export_btn = export_button.clone();
			let import_btn = import_button.clone();
			Rc::new(move || {
				let next = counter.get().saturating_add(1);
				counter.set(next);
				export_btn.set_sensitive(false);
				import_btn.set_sensitive(false);
			})
		};

		let end_critical_operation: Rc<dyn Fn()> = {
			let counter = Rc::clone(&critical_ops_in_flight);
			let export_btn = export_button.clone();
			let import_btn = import_button.clone();
			Rc::new(move || {
				let next = counter.get().saturating_sub(1);
				counter.set(next);
				if next == 0 {
					export_btn.set_sensitive(true);
					import_btn.set_sensitive(true);
				}
			})
		};

		let loading_lock = Rc::new(Cell::new(true));
		let (sender, receiver) = tokio::sync::oneshot::channel();
		let service_for_load = Arc::clone(&user_service);
		let totp_for_load = Arc::clone(&totp_service);
		let policy_for_load = Arc::clone(&auth_policy_service);
		let runtime_for_load = runtime_handle.clone();
		std::thread::spawn(move || {
			let result = runtime_for_load.block_on(async move {
				let user = service_for_load.get_user_profile(user_id).await?;
				let delay = policy_for_load.get_auto_lock_delay(user.username.as_str()).await?;
				let totp_enabled = totp_for_load.is_totp_enabled_for_user_id(user_id).await?;
				Ok::<_, crate::errors::AppError>((user, delay, totp_enabled))
			});
			let _ = sender.send(result);
		});

		let username_entry_for_load = username_entry.clone();
		let display_entry_for_load = display_entry.clone();
		let email_entry_for_load = email_entry.clone();
		let auto_lock_for_load = auto_lock_dropdown.clone();
		let language_dropdown_for_load = language_dropdown.clone();
		let show_edit_passwords_for_load = show_edit_passwords_switch.clone();
		let show_passwords_pref_for_load = Rc::clone(&show_passwords_in_edit_pref);
		let twofa_stack_for_load = twofa_stack.clone();
		let twofa_disable_confirm_row_for_load = twofa_disable_confirm_row.clone();
		let twofa_badge_for_load = twofa_state_badge.clone();
		let loading_lock_for_load = Rc::clone(&loading_lock);
		let profile_status_for_load = profile_status_label.clone();
		let apply_profile_i18n_for_load = Rc::clone(&apply_profile_i18n);
		glib::MainContext::default().spawn_local(async move {
			match receiver.await {
				Ok(Ok((user, delay, totp_enabled))) => {
					let language = user.preferred_language.trim().to_ascii_lowercase();
					let _ = crate::i18n::set_language(language.as_str());
					apply_profile_i18n_for_load();
					username_entry_for_load.set_text(user.username.as_str());
					display_entry_for_load.set_text(user.display_name.as_deref().unwrap_or_default());
					email_entry_for_load.set_text(user.email.as_deref().unwrap_or_default());
					language_dropdown_for_load.set_selected(if language.starts_with("en") { 1 } else { 0 });
					let selected = match delay {
						1 => 0,
						5 => 1,
						15 => 2,
						30 => 3,
						0 => 4,
						_ => 1,
					};
					auto_lock_for_load.set_selected(selected);
					show_edit_passwords_for_load.set_active(user.show_passwords_in_edit);
					show_passwords_pref_for_load.set(user.show_passwords_in_edit);
					twofa_stack_for_load.set_visible_child_name(if totp_enabled {
						"enabled"
					} else {
						"disabled"
					});
					Self::set_twofa_badge_state(&twofa_badge_for_load, totp_enabled);
					twofa_disable_confirm_row_for_load.set_visible(false);
					loading_lock_for_load.set(false);
				}
				_ => {
					loading_lock_for_load.set(false);
					Self::set_inline_status(&profile_status_for_load, crate::tr!("profile-status-load-failed").as_str(), "error");
				}
			}
		});

		let policy_for_delay = Arc::clone(&auth_policy_service);
		let runtime_for_delay = runtime_handle.clone();
		let username_for_delay = username_entry.clone();
		let loading_lock_for_delay = Rc::clone(&loading_lock);
		let window_for_delay = window.clone();
		let security_status_for_delay = security_prefs_status_label.clone();
		let session_for_delay = Rc::clone(&session_master_key);
		auto_lock_dropdown.connect_selected_notify(move |dropdown| {
			if loading_lock_for_delay.get() {
				return;
			}

			let username = username_for_delay.text().trim().to_string();
			if username.is_empty() {
				return;
			}

			let mins = match dropdown.selected() {
				0 => 1,
				1 => 5,
				2 => 15,
				3 => 30,
				4 => 0,
				_ => 5,
			};
			Self::set_inline_status(&security_status_for_delay, crate::tr!("profile-status-lock-delay-updating").as_str(), "loading");

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let runtime_for_task = runtime_for_delay.clone();
			let policy_for_task = Arc::clone(&policy_for_delay);
			std::thread::spawn(move || {
				let result = runtime_for_task.block_on(async move {
					policy_for_task.update_auto_lock_delay(username.as_str(), mins).await
				});
				let _ = sender.send((mins, result));
			});

			let security_status_for_result = security_status_for_delay.clone();
			let auto_lock_timeout_for_result = Rc::clone(&auto_lock_timeout_secs);
			let auto_lock_source_for_result = Rc::clone(&auto_lock_source);
			let auto_lock_armed_for_result = Rc::clone(&auto_lock_armed);
			let on_auto_lock_for_result = Rc::clone(&on_auto_lock);
			let session_for_result = Rc::clone(&session_for_delay);
			let window_for_result = window_for_delay.clone();
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok((updated_mins, Ok(()))) => {
						auto_lock_timeout_for_result.set((updated_mins as u64).saturating_mul(60));
						if updated_mins == 0 {
							auto_lock_armed_for_result.set(false);
							if let Some(source_id) = auto_lock_source_for_result.borrow_mut().take() {
								source_id.remove();
							}
						} else if auto_lock_armed_for_result.get() {
							Self::reset_auto_lock_timer(
								&window_for_result,
								&auto_lock_source_for_result,
								&auto_lock_armed_for_result,
								auto_lock_timeout_for_result.get(),
								&on_auto_lock_for_result,
								&session_for_result,
							);
						}
						Self::set_inline_status(&security_status_for_result, crate::tr!("profile-status-lock-delay-updated").as_str(), "success");
					}
					_ => {
						Self::set_inline_status(&security_status_for_result, crate::tr!("profile-status-lock-delay-failed").as_str(), "error");
					}
				}
			});
		});

		let service_for_profile_save = Arc::clone(&user_service);
		let runtime_for_profile_save = runtime_handle.clone();
		let display_for_save = display_entry.clone();
		let email_for_save = email_entry.clone();
		let language_dropdown_for_save = language_dropdown.clone();
		let current_email_pw_for_save = current_email_pw_entry.clone();
		let show_edit_passwords_for_save = show_edit_passwords_switch.clone();
		let show_passwords_pref_for_save = Rc::clone(&show_passwords_in_edit_pref);
		let profile_badge_for_save = profile_badge.clone();
		let profile_status_for_save = profile_status_label.clone();
		let apply_profile_i18n_for_save = Rc::clone(&apply_profile_i18n);
		let service_for_toggle = Arc::clone(&user_service);
		let runtime_for_toggle = runtime_handle.clone();
		let profile_status_for_toggle = security_prefs_status_label.clone();
		let show_passwords_pref_for_toggle = Rc::clone(&show_passwords_in_edit_pref);
		show_edit_passwords_switch.connect_active_notify(move |switch_widget| {
			let enabled = switch_widget.is_active();
			Self::set_inline_status(&profile_status_for_toggle, crate::tr!("profile-status-show-passwords-updating").as_str(), "loading");

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let runtime_for_task = runtime_for_toggle.clone();
			let service_for_task = Arc::clone(&service_for_toggle);
			std::thread::spawn(move || {
				let result = runtime_for_task.block_on(async move {
					service_for_task
						.update_show_passwords_in_edit(user_id, enabled)
						.await
				});
				let _ = sender.send((enabled, result));
			});

			let profile_status_for_result = profile_status_for_toggle.clone();
			let show_passwords_pref_for_result = Rc::clone(&show_passwords_pref_for_toggle);
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok((_, Ok(user))) => {
						show_passwords_pref_for_result.set(user.show_passwords_in_edit);
						Self::set_inline_status(&profile_status_for_result, crate::tr!("profile-status-show-passwords-updated").as_str(), "success");
					}
					_ => {
						Self::set_inline_status(&profile_status_for_result, crate::tr!("profile-status-show-passwords-failed").as_str(), "error");
					}
				}
			});
		});
		save_profile_button.connect_clicked(move |_| {
			Self::set_inline_status(&profile_status_for_save, crate::tr!("profile-status-saving").as_str(), "loading");
			let payload = crate::services::user_service::UserProfileUpdate {
				email: {
					let value = email_for_save.text().trim().to_string();
					if value.is_empty() { None } else { Some(value) }
				},
				display_name: {
					let value = display_for_save.text().trim().to_string();
					if value.is_empty() { None } else { Some(value) }
				},
					preferred_language: Some(if language_dropdown_for_save.selected() == 1 {
					"en".to_string()
				} else {
					"fr".to_string()
				}),
				show_passwords_in_edit: Some(show_edit_passwords_for_save.is_active()),
				current_password: {
					let value = current_email_pw_for_save.text().trim().to_string();
					if value.is_empty() {
						None
					} else {
						Some(SecretBox::new(Box::new(value.into_bytes())))
					}
				},
			};

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let runtime_for_task = runtime_for_profile_save.clone();
			let service_for_task = Arc::clone(&service_for_profile_save);
			std::thread::spawn(move || {
				let result = runtime_for_task.block_on(async move {
					service_for_task.update_user_profile(user_id, payload).await
				});
				let _ = sender.send(result);
			});

			let badge_for_result = profile_badge_for_save.clone();
			let profile_status_for_result = profile_status_for_save.clone();
			let show_passwords_pref_for_result = Rc::clone(&show_passwords_pref_for_save);
			let apply_profile_i18n_for_result = Rc::clone(&apply_profile_i18n_for_save);
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok(Ok(user)) => {
						let _ = crate::i18n::set_language(user.preferred_language.as_str());
						apply_profile_i18n_for_result();
						let display = user
							.display_name
							.clone()
							.filter(|value| !value.trim().is_empty())
							.unwrap_or(user.username.clone());
						show_passwords_pref_for_result.set(user.show_passwords_in_edit);
						badge_for_result.set_label(
							crate::i18n::tr_args(
								"main-connected-label",
								&[("name", crate::i18n::I18nArg::Str(display.as_str()))],
							)
							.as_str(),
						);
						Self::set_inline_status(&profile_status_for_result, crate::tr!("profile-status-saved").as_str(), "success");
					}
					_ => {
						Self::set_inline_status(&profile_status_for_result, crate::tr!("profile-status-save-failed").as_str(), "error");
					}
				}
			});
		});

		let service_for_pw_change = Arc::clone(&user_service);
		let runtime_for_pw_change = runtime_handle.clone();
		let current_pw_for_change = current_pw_entry.clone();
		let security_status_for_pw_change = password_change_status_label.clone();
		change_pw_button.connect_clicked(move |_| {
			Self::set_inline_status(&security_status_for_pw_change, crate::tr!("profile-status-password-change-ready").as_str(), "success");
			current_pw_for_change.grab_focus();
		});

		let service_for_rotate = Arc::clone(&service_for_pw_change);
		let runtime_for_rotate = runtime_for_pw_change.clone();
		let current_pw_for_rotate = current_pw_entry.clone();
		let new_pw_for_rotate = new_pw_entry.clone();
		let confirm_pw_for_rotate = confirm_pw_entry.clone();
		let security_status_for_rotate = password_change_status_label.clone();
		rotate_master_key_button.connect_clicked(move |_| {
			let current_raw = current_pw_for_rotate.text().trim().to_string();
			let new_raw = new_pw_for_rotate.text().trim().to_string();
			let confirm_raw = confirm_pw_for_rotate.text().trim().to_string();
			if current_raw.is_empty() || new_raw.is_empty() || confirm_raw.is_empty() {
				Self::set_inline_status(&security_status_for_rotate, crate::tr!("profile-status-password-fields-required").as_str(), "error");
				return;
			}
			if new_raw != confirm_raw {
				Self::set_inline_status(&security_status_for_rotate, crate::tr!("profile-status-password-confirm-mismatch").as_str(), "error");
				return;
			}

			Self::set_inline_status(&security_status_for_rotate, crate::tr!("profile-status-password-updating").as_str(), "loading");

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let runtime_for_task = runtime_for_rotate.clone();
			let service_for_task = Arc::clone(&service_for_rotate);
			std::thread::spawn(move || {
				let result = runtime_for_task.block_on(async move {
					service_for_task
						.change_master_password(
							user_id,
							SecretBox::new(Box::new(current_raw.into_bytes())),
							SecretBox::new(Box::new(new_raw.into_bytes())),
						)
						.await
				});
				let _ = sender.send(result);
			});

			let current_for_result = current_pw_for_rotate.clone();
			let new_for_result = new_pw_for_rotate.clone();
			let confirm_for_result = confirm_pw_for_rotate.clone();
			let security_status_for_result = security_status_for_rotate.clone();
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok(Ok(())) => {
						current_for_result.set_text("");
						new_for_result.set_text("");
						confirm_for_result.set_text("");
						Self::set_inline_status(&security_status_for_result, crate::tr!("profile-status-password-updated").as_str(), "success");
					}
					_ => {
						Self::set_inline_status(&security_status_for_result, crate::tr!("profile-status-password-failed").as_str(), "error");
					}
				}
			});
		});

		let pending_totp_secret: Rc<RefCell<Option<String>>> = Rc::new(RefCell::new(None));

		let username_for_twofa_activate = username_entry.clone();
		let twofa_stack_for_activate = twofa_stack.clone();
		let twofa_qr_for_activate = twofa_qr_picture.clone();
		let twofa_secret_for_activate = twofa_secret_entry.clone();
		let twofa_code_for_activate = twofa_code_entry.clone();
		let twofa_status_for_activate = twofa_status_label.clone();
		let pending_secret_for_activate = Rc::clone(&pending_totp_secret);
		let totp_for_activate = Arc::clone(&totp_service);
		twofa_activate_button.connect_clicked(move |_| {
			let username = username_for_twofa_activate.text().trim().to_string();
			if username.is_empty() {
				Self::set_inline_status(&twofa_status_for_activate, crate::tr!("profile-status-twofa-profile-missing-start").as_str(), "error");
				return;
			}

			match totp_for_activate.create_setup_payload(username.as_str()) {
				Ok(payload) => {
					*pending_secret_for_activate.borrow_mut() = Some(payload.base32_secret.clone());
					let loader = gtk4::gdk_pixbuf::PixbufLoader::new();
					if loader.write(&payload.qr_png).is_ok() && loader.close().is_ok() {
						if let Some(pixbuf) = loader.pixbuf() {
							let texture = gtk4::gdk::Texture::for_pixbuf(&pixbuf);
							twofa_qr_for_activate.set_paintable(Some(&texture));
						}
					}
					twofa_secret_for_activate.set_text(payload.base32_secret.as_str());
					twofa_code_for_activate.set_text("");
					twofa_stack_for_activate.set_visible_child_name("setup");
					Self::set_inline_status(&twofa_status_for_activate, crate::tr!("profile-status-twofa-ready").as_str(), "success");
				}
				Err(error) => {
					Self::set_inline_status(
						&twofa_status_for_activate,
						Self::map_twofa_error(
							&error,
							crate::tr!("profile-status-twofa-prepare-failed").as_str(),
						)
						.as_str(),
						"error",
					);
				}
			}
		});

		let pending_secret_for_cancel = Rc::clone(&pending_totp_secret);
		let twofa_stack_for_cancel = twofa_stack.clone();
		let twofa_status_for_cancel = twofa_status_label.clone();
		twofa_cancel_setup_button.connect_clicked(move |_| {
			*pending_secret_for_cancel.borrow_mut() = None;
			twofa_stack_for_cancel.set_visible_child_name("disabled");
			Self::set_inline_status(&twofa_status_for_cancel, crate::tr!("profile-status-twofa-cancelled").as_str(), "success");
		});

		let username_for_twofa_confirm = username_entry.clone();
		let twofa_code_for_confirm = twofa_code_entry.clone();
		let twofa_stack_for_confirm = twofa_stack.clone();
		let twofa_status_for_confirm = twofa_status_label.clone();
		let twofa_badge_for_confirm = twofa_state_badge.clone();
		let pending_secret_for_confirm = Rc::clone(&pending_totp_secret);
		let totp_for_confirm = Arc::clone(&totp_service);
		let runtime_for_twofa_confirm = runtime_handle.clone();
		twofa_confirm_button.connect_clicked(move |_| {
			let username = username_for_twofa_confirm.text().trim().to_string();
			let code = twofa_code_for_confirm.text().trim().to_string();

			if username.is_empty() {
				Self::set_inline_status(&twofa_status_for_confirm, crate::tr!("profile-status-twofa-profile-missing-finish").as_str(), "error");
				return;
			}

			let Some(secret) = pending_secret_for_confirm.borrow().clone() else {
				Self::set_inline_status(&twofa_status_for_confirm, crate::tr!("profile-status-twofa-none-pending").as_str(), "error");
				return;
			};

			if let Some(validation_message) = messages::validate_totp_code_format(code.as_str()) {
				Self::set_inline_status(
					&twofa_status_for_confirm,
					validation_message.as_str(),
					"error",
				);
				return;
			}

			match totp_for_confirm.verify_setup_code(username.as_str(), secret.as_str(), code.as_str()) {
				Ok(true) => {
					Self::set_inline_status(&twofa_status_for_confirm, crate::tr!("profile-status-twofa-enabling").as_str(), "loading");

					let (sender, receiver) = tokio::sync::oneshot::channel();
					let runtime_for_task = runtime_for_twofa_confirm.clone();
					let totp_for_task = Arc::clone(&totp_for_confirm);
					std::thread::spawn(move || {
						let result = runtime_for_task.block_on(async move {
							totp_for_task
								.enable_totp(
									user_id,
									username.as_str(),
									secret.as_str(),
									code.as_str(),
								)
								.await
						});
						let _ = sender.send(result);
					});

					let twofa_stack_for_result = twofa_stack_for_confirm.clone();
					let twofa_status_for_result = twofa_status_for_confirm.clone();
					let twofa_badge_for_result = twofa_badge_for_confirm.clone();
					let twofa_code_for_result = twofa_code_for_confirm.clone();
					let pending_secret_for_result = Rc::clone(&pending_secret_for_confirm);
					glib::MainContext::default().spawn_local(async move {
						match receiver.await {
							Ok(Ok(())) => {
								*pending_secret_for_result.borrow_mut() = None;
								twofa_code_for_result.set_text("");
								twofa_stack_for_result.set_visible_child_name("enabled");
								Self::set_twofa_badge_state(&twofa_badge_for_result, true);
								Self::set_inline_status(&twofa_status_for_result, crate::tr!("profile-status-twofa-enabled").as_str(), "success");
							}
							Ok(Err(error)) => {
								Self::set_inline_status(
									&twofa_status_for_result,
									Self::map_twofa_error(
										&error,
										crate::tr!("profile-status-twofa-enable-failed").as_str(),
									)
									.as_str(),
									"error",
								);
							}
							Err(_) => {
								Self::set_inline_status(&twofa_status_for_result, crate::tr!("profile-status-twofa-interrupted").as_str(), "error");
							}
						}
					});
				}
				Ok(false) => {
					Self::set_inline_status(
						&twofa_status_for_confirm,
						messages::profile_totp_code_invalid_error().as_str(),
						"error",
					);
				}
				Err(error) => {
					Self::set_inline_status(
						&twofa_status_for_confirm,
						Self::map_twofa_error(
							&error,
							crate::tr!("profile-status-twofa-verify-failed").as_str(),
						)
						.as_str(),
						"error",
					);
				}
			}
		});

		let twofa_confirm_row_for_toggle = twofa_disable_confirm_row.clone();
		twofa_disable_toggle_button.connect_clicked(move |_| {
			twofa_confirm_row_for_toggle.set_visible(true);
		});

		let twofa_confirm_row_for_cancel = twofa_disable_confirm_row.clone();
		twofa_disable_cancel_button.connect_clicked(move |_| {
			twofa_confirm_row_for_cancel.set_visible(false);
		});

		let totp_for_disable = Arc::clone(&totp_service);
		let runtime_for_disable = runtime_handle.clone();
		let twofa_stack_for_disable = twofa_stack.clone();
		let twofa_status_for_disable = twofa_status_label.clone();
		let twofa_badge_for_disable = twofa_state_badge.clone();
		let twofa_confirm_row_for_disable = twofa_disable_confirm_row.clone();
		twofa_disable_confirm_button.connect_clicked(move |_| {
			Self::set_inline_status(&twofa_status_for_disable, crate::tr!("profile-status-twofa-disabling").as_str(), "loading");

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let runtime_for_task = runtime_for_disable.clone();
			let totp_for_task = Arc::clone(&totp_for_disable);
			std::thread::spawn(move || {
				let result = runtime_for_task.block_on(async move { totp_for_task.disable_totp(user_id).await });
				let _ = sender.send(result);
			});

			let twofa_stack_for_result = twofa_stack_for_disable.clone();
			let twofa_status_for_result = twofa_status_for_disable.clone();
			let twofa_badge_for_result = twofa_badge_for_disable.clone();
			let twofa_confirm_row_for_result = twofa_confirm_row_for_disable.clone();
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok(Ok(())) => {
						twofa_confirm_row_for_result.set_visible(false);
						twofa_stack_for_result.set_visible_child_name("disabled");
						Self::set_twofa_badge_state(&twofa_badge_for_result, false);
						Self::set_inline_status(&twofa_status_for_result, crate::tr!("profile-status-twofa-disabled").as_str(), "success");
					}
					Ok(Err(error)) => {
						Self::set_inline_status(
							&twofa_status_for_result,
							Self::map_twofa_error(
								&error,
								crate::tr!("profile-status-twofa-disable-failed").as_str(),
							)
							.as_str(),
							"error",
						);
					}
					Err(_) => {
						Self::set_inline_status(&twofa_status_for_result, crate::tr!("profile-status-twofa-interrupted").as_str(), "error");
					}
				}
			});
		});

		let window_for_export = window.clone();
		let backup_for_export = Arc::clone(&backup_service);
		let database_path_for_export = database_path.clone();
		let begin_critical_for_export = Rc::clone(&begin_critical_operation);
		let end_critical_for_export = Rc::clone(&end_critical_operation);
		export_button.connect_clicked(move |_| {
			let chooser = gtk4::FileChooserNative::builder()
				.title(crate::tr!("profile-export-chooser-title").as_str())
				.transient_for(&window_for_export)
				.accept_label(crate::tr!("profile-export-accept").as_str())
				.cancel_label(crate::tr!("trash-dialog-cancel").as_str())
				.action(gtk4::FileChooserAction::Save)
				.build();
			chooser.set_current_name("heelonvault_backup.hvb");

			let window_for_response = window_for_export.clone();
			let backup_for_response = Arc::clone(&backup_for_export);
			let db_path_for_response = database_path_for_export.clone();
			let begin_critical_for_response = Rc::clone(&begin_critical_for_export);
			let end_critical_for_response = Rc::clone(&end_critical_for_export);
			chooser.connect_response(move |dialog, response| {
				if response != gtk4::ResponseType::Accept {
					dialog.destroy();
					return;
				}

				let selected = dialog.file();
				dialog.destroy();
				let Some(file) = selected else {
					Self::show_feedback_dialog(&window_for_response, crate::tr!("profile-export-accept").as_str(), crate::tr!("profile-export-invalid-destination").as_str());
					return;
				};
				let Some(mut export_path) = file.path() else {
					Self::show_feedback_dialog(&window_for_response, crate::tr!("profile-export-accept").as_str(), crate::tr!("profile-export-invalid-path").as_str());
					return;
				};
				if export_path.extension().is_none() {
					export_path.set_extension("hvb");
				}

				let recovery = match backup_for_response.generate_recovery_key() {
					Ok(value) => value,
					Err(_) => {
						Self::show_feedback_dialog(
							&window_for_response,
							crate::tr!("profile-export-accept").as_str(),
							crate::tr!("profile-export-recovery-key-failed").as_str(),
						);
						return;
					}
				};

				let recovery_text = recovery.recovery_phrase.expose_secret().to_string();
				let (sender, receiver) = tokio::sync::oneshot::channel();
				let backup_for_task = Arc::clone(&backup_for_response);
				let db_for_task = db_path_for_response.clone();
				let path_for_task = export_path.clone();
				let phrase_for_task = recovery.recovery_phrase.clone();
				begin_critical_for_response();
				std::thread::spawn(move || {
					let result = backup_for_task.export_hvb_with_recovery_key(
						db_for_task.as_path(),
						path_for_task.as_path(),
						&phrase_for_task,
					);
					let _ = sender.send(result);
				});

				let window_for_result = window_for_response.clone();
				let end_critical_for_result = Rc::clone(&end_critical_for_response);
				glib::MainContext::default().spawn_local(async move {
					let result = receiver.await;
					end_critical_for_result();
					match result {
						Ok(Ok(_)) => {
							let message = crate::i18n::tr_args(
								"profile-export-success-body",
								&[("key", crate::i18n::I18nArg::Str(recovery_text.as_str()))],
							);
							Self::show_feedback_dialog(&window_for_result, crate::tr!("profile-export-success-title").as_str(), message.as_str());
						}
						_ => {
							Self::show_feedback_dialog(&window_for_result, crate::tr!("profile-export-accept").as_str(), crate::tr!("profile-export-failed").as_str());
						}
					}
				});
			});

			chooser.show();
		});

		let window_for_import = window.clone();
		let import_for_profile = Arc::clone(&import_service);
		let secret_for_import = Arc::clone(&secret_service);
		let vault_for_import = Arc::clone(&vault_service);
		let runtime_for_import = runtime_handle.clone();
		let session_for_import = Rc::clone(&session_master_key);
		let refresh_for_import = Rc::clone(&on_import_completed_refresh);
		let begin_critical_for_import = Rc::clone(&begin_critical_operation);
		let end_critical_for_import = Rc::clone(&end_critical_operation);
		import_button.connect_clicked(move |_| {
			let chooser = gtk4::FileChooserNative::builder()
				.title(crate::tr!("profile-import-chooser-title").as_str())
				.transient_for(&window_for_import)
				.accept_label(crate::tr!("profile-import-accept").as_str())
				.cancel_label(crate::tr!("trash-dialog-cancel").as_str())
				.action(gtk4::FileChooserAction::Open)
				.build();

			let window_for_response = window_for_import.clone();
			let import_for_response = Arc::clone(&import_for_profile);
			let secret_for_response = Arc::clone(&secret_for_import);
			let vault_for_response = Arc::clone(&vault_for_import);
			let runtime_for_response = runtime_for_import.clone();
			let session_for_response = Rc::clone(&session_for_import);
			let refresh_for_response = Rc::clone(&refresh_for_import);
			let begin_critical_for_response = Rc::clone(&begin_critical_for_import);
			let end_critical_for_response = Rc::clone(&end_critical_for_import);
			chooser.connect_response(move |dialog, response| {
				if response != gtk4::ResponseType::Accept {
					dialog.destroy();
					return;
				}

				let selected = dialog.file();
				dialog.destroy();
				let Some(file) = selected else {
					Self::show_feedback_dialog(&window_for_response, crate::tr!("profile-import-accept").as_str(), crate::tr!("profile-import-invalid-file").as_str());
					return;
				};
				let Some(csv_path) = file.path() else {
					Self::show_feedback_dialog(&window_for_response, crate::tr!("profile-import-accept").as_str(), crate::tr!("profile-import-invalid-path").as_str());
					return;
				};

				let Some(master_key) = Self::snapshot_session_master_key(&session_for_response) else {
					Self::show_feedback_dialog(
						&window_for_response,
						crate::tr!("profile-import-accept").as_str(),
						crate::tr!("profile-import-session-locked").as_str(),
					);
					return;
				};

				let (sender, receiver) = tokio::sync::oneshot::channel();
				let import_for_task = Arc::clone(&import_for_response);
				let secret_for_task = Arc::clone(&secret_for_response);
				let vault_for_task = Arc::clone(&vault_for_response);
				let runtime_for_task = runtime_for_response.clone();
				begin_critical_for_response();
				std::thread::spawn(move || {
					let result = runtime_for_task.block_on(async move {
						import_for_task
							.import_csv(
								csv_path.as_path(),
								user_id,
								SecretBox::new(Box::new(master_key)),
								secret_for_task,
								vault_for_task,
							)
							.await
					});
					let _ = sender.send(result);
				});

				let window_for_result = window_for_response.clone();
				let refresh_for_result = Rc::clone(&refresh_for_response);
				let end_critical_for_result = Rc::clone(&end_critical_for_response);
				glib::MainContext::default().spawn_local(async move {
					let result = receiver.await;
					end_critical_for_result();
					match result {
						Ok(Ok(count)) => {
							refresh_for_result();
							let message = crate::i18n::tr_args(
								"profile-import-success-body",
								&[("count", crate::i18n::I18nArg::Num(count as i64))],
							);
							Self::show_feedback_dialog(&window_for_result, crate::tr!("profile-import-accept").as_str(), message.as_str());
						}
						_ => {
							Self::show_feedback_dialog(&window_for_result, crate::tr!("profile-import-accept").as_str(), crate::tr!("profile-import-failed").as_str());
						}
					}
				});
			});

			chooser.show();
		});

		ProfileViewWidgets {
			container,
			back_button,
		}
	}

	fn build_sidebar_panel() -> SidebarWidgets {
		let sidebar_frame = gtk4::Frame::new(None);
		sidebar_frame.add_css_class("main-sidebar");

		let sidebar_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(14)
			.margin_bottom(14)
			.margin_start(14)
			.margin_end(14)
			.build();

		let my_vaults_title = gtk4::Label::new(Some(crate::tr!("main-my-vaults-title").as_str()));
		my_vaults_title.add_css_class("main-section-title");
		my_vaults_title.set_halign(Align::Start);

		let create_vault_button = gtk4::Button::builder()
			.icon_name("list-add-symbolic")
			.build();
		create_vault_button.add_css_class("flat");
		create_vault_button.add_css_class("accent");
		create_vault_button.set_tooltip_text(Some(crate::tr!("main-create-vault-button").as_str()));

		let my_vaults_header = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(6)
			.build();
		my_vaults_header.append(&my_vaults_title);
		my_vaults_header.append(&create_vault_button);
		sidebar_box.append(&my_vaults_header);

		let my_vaults_list = gtk4::ListBox::new();
		my_vaults_list.add_css_class("boxed-list");
		my_vaults_list.add_css_class("main-category-list");
		my_vaults_list.set_selection_mode(gtk4::SelectionMode::Single);
		sidebar_box.append(&my_vaults_list);

		let shared_vaults_title = gtk4::Label::new(Some(crate::tr!("main-shared-with-me-title").as_str()));
		shared_vaults_title.add_css_class("main-section-title");
		shared_vaults_title.set_halign(Align::Start);
		shared_vaults_title.set_visible(false);

		let shared_vaults_list = gtk4::ListBox::new();
		shared_vaults_list.add_css_class("boxed-list");
		shared_vaults_list.add_css_class("main-category-list");
		shared_vaults_list.set_selection_mode(gtk4::SelectionMode::Single);
		shared_vaults_list.set_visible(false);
		sidebar_box.append(&shared_vaults_title);
		sidebar_box.append(&shared_vaults_list);

		let vaults_separator = gtk4::Separator::new(Orientation::Horizontal);
		sidebar_box.append(&vaults_separator);

		let audit_title = gtk4::Label::new(Some(crate::tr!("main-audit-title").as_str()));
		audit_title.add_css_class("main-section-title");
		audit_title.set_halign(Align::Start);
		sidebar_box.append(&audit_title);

		let audit_list = gtk4::ListBox::new();
		audit_list.add_css_class("boxed-list");
		audit_list.add_css_class("main-audit-list");
		audit_list.set_selection_mode(gtk4::SelectionMode::Single);

		let (audit_all_row, audit_all_label, audit_all_badge) =
			Self::build_audit_sidebar_row(crate::tr!("main-audit-all").as_str(), "view-grid-symbolic");
		let (audit_weak_row, audit_weak_label, audit_weak_badge) = Self::build_audit_sidebar_row(
			crate::tr!("main-audit-weak").as_str(),
			"dialog-warning-symbolic",
		);
		let (audit_duplicate_row, audit_duplicate_label, audit_duplicate_badge) =
			Self::build_audit_sidebar_row(crate::tr!("main-audit-duplicates").as_str(), "content-copy-symbolic");
		audit_list.append(&audit_all_row);
		audit_list.append(&audit_weak_row);
		audit_list.append(&audit_duplicate_row);
		audit_list.select_row(Some(&audit_all_row));
		sidebar_box.append(&audit_list);

		let sidebar_title = gtk4::Label::new(Some(crate::tr!("main-categories-title").as_str()));
		sidebar_title.add_css_class("main-section-title");
		sidebar_title.set_halign(Align::Start);
		sidebar_box.append(&sidebar_title);

		let category_list = gtk4::ListBox::new();
		category_list.add_css_class("boxed-list");
		category_list.add_css_class("main-category-list");
		category_list.set_selection_mode(gtk4::SelectionMode::Single);

		let rows = [
			(crate::tr!("main-category-all"), "view-grid-symbolic"),
			(crate::tr!("main-category-passwords"), "dialog-password-symbolic"),
			(crate::tr!("main-category-api-tokens"), "dialog-key-symbolic"),
			(crate::tr!("main-category-ssh-keys"), "network-wired-symbolic"),
			(crate::tr!("main-category-documents"), "folder-documents-symbolic"),
		];

		let mut category_labels: Vec<gtk4::Label> = Vec::new();
		for (index, (title, icon_name)) in rows.into_iter().enumerate() {
			let (row, label) = Self::build_sidebar_row(title.as_str(), icon_name);
			category_labels.push(label);
			category_list.append(&row);
			if index == 0 {
				category_list.select_row(Some(&row));
			}
		}

		sidebar_box.append(&category_list);

		let account_title = gtk4::Label::new(Some(crate::tr!("main-account-title").as_str()));
		account_title.add_css_class("main-section-title");
		account_title.set_halign(Align::Start);
		sidebar_box.append(&account_title);

		let profile_security_button = gtk4::Button::new();
		profile_security_button.add_css_class("flat");
		profile_security_button.add_css_class("sidebar-profile-entry");
		profile_security_button.set_halign(Align::Fill);
		let profile_security_inner = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(8)
			.margin_bottom(8)
			.margin_start(10)
			.margin_end(10)
			.build();
		let profile_security_icon = gtk4::Image::from_icon_name("preferences-system-symbolic");
		profile_security_icon.set_pixel_size(18);
		profile_security_icon.add_css_class("main-sidebar-icon");
		let profile_security_label = gtk4::Label::new(Some(crate::tr!("main-profile-security").as_str()));
		profile_security_label.add_css_class("main-sidebar-label");
		profile_security_label.set_halign(Align::Start);
		profile_security_label.set_hexpand(true);
		profile_security_inner.append(&profile_security_icon);
		profile_security_inner.append(&profile_security_label);
		profile_security_button.set_child(Some(&profile_security_inner));
		sidebar_box.append(&profile_security_button);

		let teams_button = gtk4::Button::new();
		teams_button.add_css_class("flat");
		teams_button.add_css_class("sidebar-profile-entry");
		teams_button.set_halign(Align::Fill);
		let teams_inner = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(8)
			.margin_bottom(8)
			.margin_start(10)
			.margin_end(10)
			.build();
		let teams_icon = gtk4::Image::from_icon_name("system-users-symbolic");
		teams_icon.set_pixel_size(18);
		teams_icon.add_css_class("main-sidebar-icon");
		let teams_label = gtk4::Label::new(Some(crate::tr!("main-teams-nav").as_str()));
		teams_label.add_css_class("main-sidebar-label");
		teams_label.set_halign(Align::Start);
		teams_label.set_hexpand(true);
		teams_inner.append(&teams_icon);
		teams_inner.append(&teams_label);
		teams_button.set_child(Some(&teams_inner));
		sidebar_box.append(&teams_button);

		let administration_button = gtk4::Button::new();
		administration_button.add_css_class("flat");
		administration_button.add_css_class("sidebar-profile-entry");
		administration_button.set_halign(Align::Fill);
		let administration_inner = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(8)
			.margin_bottom(8)
			.margin_start(10)
			.margin_end(10)
			.build();
		let administration_icon = gtk4::Image::from_icon_name("avatar-default-symbolic");
		administration_icon.set_pixel_size(18);
		administration_icon.add_css_class("main-sidebar-icon");
		let administration_label = gtk4::Label::new(Some(crate::tr!("main-user-nav").as_str()));
		administration_label.add_css_class("main-sidebar-label");
		administration_label.set_halign(Align::Start);
		administration_label.set_hexpand(true);
		administration_inner.append(&administration_icon);
		administration_inner.append(&administration_label);
		administration_button.set_child(Some(&administration_inner));
		sidebar_box.append(&administration_button);
		administration_button.set_visible(false);

		sidebar_frame.set_child(Some(&sidebar_box));
		SidebarWidgets {
			frame: sidebar_frame,
			my_vaults_title,
			create_vault_button,
			my_vaults_list,
			shared_vaults_title,
			shared_vaults_list,
			category_list,
			audit_list,
			audit_title,
			categories_title: sidebar_title,
			account_title,
			audit_all_label,
			audit_weak_label,
			audit_duplicate_label,
			category_all_label: category_labels[0].clone(),
			category_passwords_label: category_labels[1].clone(),
			category_api_tokens_label: category_labels[2].clone(),
			category_ssh_keys_label: category_labels[3].clone(),
			category_documents_label: category_labels[4].clone(),
			audit_all_badge,
			audit_weak_badge,
			audit_duplicate_badge,
			profile_security_label,
			profile_security_button,
			teams_label,
			teams_button,
			administration_label,
			administration_button,
		}
	}

	fn build_audit_sidebar_row(title: &str, icon_name: &str) -> (gtk4::ListBoxRow, gtk4::Label, gtk4::Label) {
		let row = gtk4::ListBoxRow::new();
		let content = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(8)
			.margin_bottom(8)
			.margin_start(10)
			.margin_end(10)
			.build();

		let icon = gtk4::Image::from_icon_name(icon_name);
		icon.set_pixel_size(18);
		icon.add_css_class("main-sidebar-icon");
		content.append(&icon);

		let label = gtk4::Label::new(Some(title));
		label.set_halign(Align::Start);
		label.set_hexpand(true);
		label.add_css_class("main-sidebar-label");
		content.append(&label);

		let badge = gtk4::Label::new(Some("0"));
		badge.add_css_class("audit-count-badge");
		content.append(&badge);

		row.set_child(Some(&content));
		(row, label, badge)
	}

	fn build_sidebar_row(title: &str, icon_name: &str) -> (gtk4::ListBoxRow, gtk4::Label) {
		let row = gtk4::ListBoxRow::new();
		let content = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(8)
			.margin_bottom(8)
			.margin_start(10)
			.margin_end(10)
			.build();

		let icon = gtk4::Image::from_icon_name(icon_name);
		icon.set_pixel_size(18);
		icon.add_css_class("main-sidebar-icon");
		content.append(&icon);

		let label = gtk4::Label::new(Some(title));
		label.set_halign(Align::Start);
		label.set_hexpand(true);
		label.add_css_class("main-sidebar-label");
		content.append(&label);

		row.set_child(Some(&content));
		(row, label)
	}

	fn build_vault_sidebar_row(
		title: &str,
		vault_id: Uuid,
		can_delete: bool,
		is_shared_with_others: bool,
		shared_role: Option<crate::models::VaultShareRole>,
		secret_count: usize,
		on_delete: Option<Rc<dyn Fn(Uuid, String)>>,
	) -> gtk4::ListBoxRow {
		let row = gtk4::ListBoxRow::new();
		let content = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(8)
			.margin_bottom(8)
			.margin_start(10)
			.margin_end(10)
			.build();

		let icon = gtk4::Image::from_icon_name("folder-symbolic");
		icon.set_pixel_size(18);
		icon.add_css_class("main-sidebar-icon");
		content.append(&icon);

		let label = gtk4::Label::new(Some(title));
		label.set_halign(Align::Start);
		label.set_hexpand(true);
		label.add_css_class("main-sidebar-label");
		content.append(&label);

		if shared_role.is_some() || is_shared_with_others {
			let shared_icon = gtk4::Image::from_icon_name("emblem-shared-symbolic");
			shared_icon.set_pixel_size(14);
			shared_icon.add_css_class("main-sidebar-icon");
			shared_icon.add_css_class("vault-shared-indicator");
			shared_icon.set_tooltip_text(Some(crate::tr!("main-vault-shared-tooltip").as_str()));
			content.append(&shared_icon);
		}

		if let Some(role) = shared_role {
			let role_badge = gtk4::Label::new(None);
			let badge_text = match role {
				crate::models::VaultShareRole::Read => "READ",
				crate::models::VaultShareRole::Write => "WRITE",
				crate::models::VaultShareRole::Admin => "ADMIN",
			};
			role_badge.set_text(badge_text);
			role_badge.add_css_class("vault-share-role-badge");
			role_badge.set_margin_end(6);
			content.append(&role_badge);
		}

		let count_text = secret_count.to_string();
		let count_badge = gtk4::Label::new(Some(count_text.as_str()));
		count_badge.add_css_class("audit-count-badge");
		count_badge.set_margin_end(6);
		content.append(&count_badge);

		if can_delete {
			let delete_button = gtk4::Button::builder()
				.icon_name("user-trash-symbolic")
				.build();
			delete_button.add_css_class("flat");
			delete_button.set_valign(Align::Center);
			delete_button.set_tooltip_text(Some(crate::tr!("main-delete-vault-tooltip").as_str()));
			delete_button.set_opacity(0.0);
			delete_button.set_sensitive(false);
			delete_button.set_can_target(false);
			if let Some(delete_callback) = on_delete {
				let vault_name = title.to_string();
				delete_button.connect_clicked(move |_| {
					delete_callback(vault_id, vault_name.clone());
				});
			}

			let delete_button_enter = delete_button.clone();
			let delete_button_leave = delete_button.clone();
			let hover_controller = gtk4::EventControllerMotion::new();
			hover_controller.connect_enter(move |_controller, _x, _y| {
				delete_button_enter.set_opacity(1.0);
				delete_button_enter.set_sensitive(true);
				delete_button_enter.set_can_target(true);
			});
			hover_controller.connect_leave(move |_controller| {
				delete_button_leave.set_opacity(0.0);
				delete_button_leave.set_sensitive(false);
				delete_button_leave.set_can_target(false);
			});
			row.add_controller(hover_controller);

			content.append(&delete_button);
		}

		row.set_child(Some(&content));
		row.set_widget_name(format!("vault-{}", vault_id).as_str());
		row
	}

	fn vault_id_from_row(row: &gtk4::ListBoxRow) -> Option<Uuid> {
		row
			.widget_name()
			.strip_prefix("vault-")
			.and_then(|raw| Uuid::parse_str(raw).ok())
	}

	fn find_vault_row(list: &gtk4::ListBox, vault_id: Uuid) -> Option<gtk4::ListBoxRow> {
		let mut child_opt = list.first_child();
		while let Some(child) = child_opt {
			let next = child.next_sibling();
			if let Ok(row) = child.clone().downcast::<gtk4::ListBoxRow>() {
				if Self::vault_id_from_row(&row) == Some(vault_id) {
					return Some(row);
				}
			}
			child_opt = next;
		}
		None
	}

	fn build_center_panel() -> CenterPanelWidgets {
		let center_frame = gtk4::Frame::new(None);
		center_frame.add_css_class("main-center-panel");

		let entries_stack = gtk4::Stack::builder()
			.vexpand(true)
			.hexpand(true)
			.transition_type(gtk4::StackTransitionType::Crossfade)
			.build();

		let list_scroll = gtk4::ScrolledWindow::builder()
			.hscrollbar_policy(gtk4::PolicyType::Never)
			.vexpand(true)
			.hexpand(true)
			.build();
		list_scroll.add_css_class("main-secret-grid-scroll");

		let secret_flow = gtk4::FlowBox::builder()
			.homogeneous(true)
			.max_children_per_line(5)
			.min_children_per_line(1)
			.row_spacing(16)
			.column_spacing(16)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.selection_mode(gtk4::SelectionMode::None)
			.halign(gtk4::Align::Start)
			.valign(gtk4::Align::Start)
			.build();
		secret_flow.add_css_class("main-secret-grid");
		list_scroll.set_child(Some(&secret_flow));

		let filtered_status_page = adw::StatusPage::builder()
			.title(crate::tr!("main-filtered-empty-title").as_str())
			.description(crate::tr!("main-filtered-empty-description").as_str())
			.icon_name("edit-find-symbolic")
			.build();
		filtered_status_page.set_visible(false);
		filtered_status_page.set_can_target(false);

		let list_overlay = gtk4::Overlay::new();
		list_overlay.set_child(Some(&list_scroll));
		list_overlay.add_overlay(&filtered_status_page);

		let status_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(0)
			.margin_start(12)
			.margin_end(12)
			.build();
		status_row.add_css_class("vault-secret-status-row");

		let metrics_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.hexpand(true)
			.build();

		let (status_total_chip, status_total_badge) =
			Self::build_status_metric_chip("view-grid-symbolic", "0", false);
		let (status_non_compliant_chip, status_non_compliant_badge) =
			Self::build_status_metric_chip("dialog-warning-symbolic", "0", true);
		metrics_box.append(&status_total_chip);
		metrics_box.append(&status_non_compliant_chip);

		let sort_switch = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(4)
			.halign(Align::End)
			.build();
		sort_switch.add_css_class("vault-secret-sort-switch");

		let sort_recent_button = Self::build_status_sort_button("view-sort-descending-symbolic");
		let sort_title_button = Self::build_status_sort_button("insert-text-symbolic");
		let sort_risk_button = Self::build_status_sort_button("dialog-warning-symbolic");
		sort_switch.append(&sort_recent_button);
		sort_switch.append(&sort_title_button);
		sort_switch.append(&sort_risk_button);

		status_row.append(&metrics_box);
		status_row.append(&sort_switch);

		let list_page = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.vexpand(true)
			.hexpand(true)
			.build();
		list_page.append(&status_row);
		list_page.append(&list_overlay);

		let empty_state = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.halign(Align::Center)
			.valign(Align::Center)
			.vexpand(true)
			.hexpand(true)
			.build();
		empty_state.add_css_class("main-empty-state");

		let empty_icon =
			gtk4::Image::from_resource("/com/heelonvault/rust/icons/hicolor/128x128/apps/heelonvault.png");
		empty_icon.set_pixel_size(64);
		empty_icon.add_css_class("main-empty-icon");

		let empty_title = gtk4::Label::new(Some(crate::tr!("main-empty-title").as_str()));
		empty_title.add_css_class("title-3");
		empty_title.add_css_class("main-empty-title");

		let empty_description = gtk4::Label::new(Some(crate::tr!("main-empty-description").as_str()));
		empty_description.set_wrap(true);
		empty_description.set_justify(gtk4::Justification::Center);
		empty_description.set_max_width_chars(54);
		empty_description.add_css_class("main-empty-copy");

		empty_state.append(&empty_icon);
		empty_state.append(&empty_title);
		empty_state.append(&empty_description);

		entries_stack.add_titled(&list_page, Some("list"), crate::tr!("main-stack-grid").as_str());
		entries_stack.add_titled(&empty_state, Some("empty"), crate::tr!("main-stack-empty").as_str());
		entries_stack.set_visible_child_name("empty");

		let main_stack = gtk4::Stack::builder()
			.vexpand(true)
			.hexpand(true)
			.transition_type(gtk4::StackTransitionType::Crossfade)
			.build();
		main_stack.set_transition_duration(200);
		main_stack.add_titled(&entries_stack, Some("entries_view"), crate::tr!("main-stack-secrets").as_str());
		main_stack.set_visible_child_name("entries_view");

		center_frame.set_child(Some(&main_stack));
		CenterPanelWidgets {
			frame: center_frame,
			main_stack,
			stack: entries_stack,
			list_page,
			empty_state,
			secret_flow,
			filtered_status_page,
			status_total_chip,
			status_total_badge,
			status_non_compliant_chip,
			status_non_compliant_badge,
			sort_recent_button,
			sort_title_button,
			sort_risk_button,
			empty_title,
			empty_copy: empty_description,
		}
	}

	fn build_status_metric_chip(icon_name: &str, count: &str, warning: bool) -> (gtk4::Box, gtk4::Label) {
		let chip = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();
		chip.add_css_class("vault-secret-status-chip");
		if warning {
			chip.add_css_class("vault-secret-status-chip-warning");
		}

		let icon = gtk4::Image::from_icon_name(icon_name);
		icon.set_pixel_size(16);
		icon.add_css_class("vault-secret-status-icon");
		chip.append(&icon);

		let badge = gtk4::Label::new(Some(count));
		badge.add_css_class("audit-count-badge");
		badge.add_css_class("vault-secret-status-badge");
		if warning {
			badge.add_css_class("vault-secret-status-badge-warning");
		}
		chip.append(&badge);

		(chip, badge)
	}

	fn build_status_sort_button(icon_name: &str) -> gtk4::Button {
		let button = gtk4::Button::builder().icon_name(icon_name).build();
		button.add_css_class("flat");
		button.add_css_class("vault-secret-sort-button");
		button
	}

	#[allow(clippy::too_many_arguments)]
	fn refresh_secret_flow<TSecret, TVault>(
		application: adw::Application,
		parent_window: adw::ApplicationWindow,
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		admin_user_id: Uuid,
		admin_master_key: Vec<u8>,
		secret_flow: gtk4::FlowBox,
		stack: gtk4::Stack,
		empty_title: gtk4::Label,
		empty_copy: gtk4::Label,
		active_vault_id: Rc<RefCell<Option<Uuid>>>,
		toast_overlay: adw::ToastOverlay,
		filter_runtime: FilterRuntime,
		editor_launcher: Rc<RefCell<Option<Rc<dyn Fn(DialogMode)>>>>,
	) where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
	{
		empty_title.set_text(crate::tr!("main-secrets-loading-title").as_str());
		empty_copy.set_text(crate::tr!("main-secrets-loading-description").as_str());
		stack.set_visible_child_name("empty");

		let runtime_for_loader = runtime_handle.clone();
		let secret_for_loader = Arc::clone(&secret_service);
		let vault_for_loader = Arc::clone(&vault_service);
		let admin_master_for_loader = admin_master_key.clone();
		let selected_vault_id = *active_vault_id.borrow();

		let (sender, receiver) = tokio::sync::oneshot::channel();
		std::thread::spawn(move || {
			let result: Result<(Option<(Uuid, bool, bool, bool)>, Vec<SecretRowView>, bool), crate::errors::AppError> =
				runtime_for_loader.block_on(async move {
				let vaults = vault_for_loader.list_user_vaults(admin_user_id).await?;
				let resolved_selected_id = selected_vault_id
					.or_else(|| vaults.first().map(|vault| vault.id));
				let Some(selected_id) = resolved_selected_id else {
					return Ok((None, Vec::new(), true));
				};

				let selected_vault = match vaults.into_iter().find(|vault| vault.id == selected_id) {
					Some(value) => value,
					None => return Ok((None, Vec::new(), false)),
				};
				let access = vault_for_loader
					.get_vault_access_for_user(admin_user_id, selected_vault.id)
					.await?
					.ok_or_else(|| crate::errors::AppError::Authorization("vault access denied for this user".to_string()))?;
				let is_shared = selected_vault.owner_user_id != admin_user_id;
				let can_write = access.role.can_write();
				let can_admin = access.role.can_admin();
				let vault_state = Some((selected_vault.id, is_shared, can_write, can_admin));

				let vault_key = vault_for_loader
					.open_vault_for_user(
						admin_user_id,
						selected_vault.id,
						SecretBox::new(Box::new(admin_master_for_loader.clone())),
					)
					.await?;

				let items = secret_for_loader.list_by_vault(selected_vault.id).await?;
				let mut rows = Vec::with_capacity(items.len());
				for item in items {
					let secret_result = secret_for_loader
						.get_secret(
							item.id,
							SecretBox::new(Box::new(vault_key.expose_secret().clone())),
						)
						.await;
					let secret_value = match secret_result {
						Ok(secret) => {
							String::from_utf8(secret.secret_value.expose_secret().clone()).unwrap_or_default()
						}
						Err(_) => String::new(),
					};

					let (login, email, url, notes, category) = match item.metadata_json.as_deref() {
						Some(raw) => match serde_json::from_str::<Value>(raw) {
							Ok(value) => {
								let login = value
									.get("login")
									.and_then(Value::as_str)
									.unwrap_or_default()
									.to_string();
								let email = value
									.get("email")
									.and_then(Value::as_str)
									.unwrap_or_default()
									.to_string();
								let url = value
									.get("url")
									.and_then(Value::as_str)
									.unwrap_or_default()
									.to_string();
								let notes = value
									.get("notes")
									.and_then(Value::as_str)
									.unwrap_or_default()
									.to_string();
								let category = value
									.get("category")
									.and_then(Value::as_str)
									.unwrap_or_default()
									.to_string();
								(login, email, url, notes, category)
							}
							Err(_) => (
								String::new(),
								String::new(),
								String::new(),
								String::new(),
								String::new(),
							),
						},
						None => (
							String::new(),
							String::new(),
							String::new(),
							String::new(),
							String::new(),
						),
					};

					let (icon_name, type_label_text) = match item.secret_type {
						crate::models::SecretType::Password => ("dialog-password-symbolic", crate::tr!("secret-type-password")),
						crate::models::SecretType::ApiToken => ("dialog-key-symbolic", crate::tr!("secret-type-api-token")),
						crate::models::SecretType::SshKey => ("network-wired-symbolic", crate::tr!("secret-type-ssh-key")),
						crate::models::SecretType::SecureDocument => {
							("folder-documents-symbolic", crate::tr!("secret-type-secure-document"))
						}
					};
					let (color_class, kind) = match item.secret_type {
						crate::models::SecretType::Password => ("secret-type-password", SecretKind::Password),
						crate::models::SecretType::ApiToken => ("secret-type-token", SecretKind::ApiToken),
						crate::models::SecretType::SshKey => ("secret-type-ssh", SecretKind::SshKey),
						crate::models::SecretType::SecureDocument => {
							("secret-type-document", SecretKind::SecureDocument)
						}
					};

					let title = item.title.unwrap_or_else(|| type_label_text.clone());
					let created_at = item
						.created_at
						.unwrap_or_else(|| crate::tr!("login-history-unavailable"));
					let health = Self::evaluate_password_strength_label(secret_value.as_str());
					let tags = item.tags.clone().unwrap_or_default();

					rows.push(SecretRowView {
						secret_id: item.id,
						icon_name: icon_name.to_string(),
						type_label: type_label_text.to_string(),
						title,
						created_at,
						login,
						email,
						url,
						notes,
						category,
						tags,
						secret_value,
						kind,
						color_class: color_class.to_string(),
						health,
						usage_count: item.usage_count,
					});
				}

				Ok((vault_state, rows, false))
			});
			let _ = sender.send(result);
		});

		let active_vault_for_receiver = Rc::clone(&active_vault_id);
		glib::MainContext::default().spawn_local(async move {
			match receiver.await {
				Ok(Ok((vault_state, items, no_selection))) => {
					if let Some((vault_id, _, _, _)) = vault_state {
						*active_vault_for_receiver.borrow_mut() = Some(vault_id);
					}

					if no_selection {
						empty_title.set_text("Aucun coffre sélectionné");
						empty_copy.set_text("Sélectionnez un coffre dans la barre latérale pour afficher ses secrets.");
						stack.set_visible_child_name("empty");
						return;
					}

					if vault_state.is_none() {
						*active_vault_for_receiver.borrow_mut() = None;
						empty_title.set_text("Coffre non disponible");
						empty_copy.set_text("Le coffre sélectionné n'est plus accessible. Sélectionnez-en un autre.");
						stack.set_visible_child_name("empty");
						return;
					}

					filter_runtime.meta_by_widget.borrow_mut().clear();
					filter_runtime.audit_all_count_label.set_text("0");
					filter_runtime.audit_weak_count_label.set_text("0");
					filter_runtime.audit_duplicate_count_label.set_text("0");
					filter_runtime.total_count_label.set_text("0");
					filter_runtime.non_compliant_count_label.set_text("0");
					filter_runtime.filtered_status_page.set_visible(false);

					while let Some(child) = secret_flow.first_child() {
						secret_flow.remove(&child);
					}

					if items.is_empty() {
						empty_title.set_text(crate::tr!("main-empty-title").as_str());
						empty_copy.set_text(crate::tr!("main-empty-description").as_str());
						stack.set_visible_child_name("empty");
						return;
					}

					let mut duplicate_counts: HashMap<String, usize> = HashMap::new();
					for item in &items {
						if !item.secret_value.is_empty() {
							*duplicate_counts.entry(item.secret_value.clone()).or_insert(0) += 1;
						}
					}

								let shared_vault = vault_state.map(|(_, is_shared, _, _)| is_shared).unwrap_or(false);
								let can_write = vault_state.map(|(_, _, can_write, _)| can_write).unwrap_or(false);
								let can_admin = vault_state.map(|(_, _, _, can_admin)| can_admin).unwrap_or(false);
					for (original_rank, item) in items.into_iter().enumerate() {
						let is_duplicate = duplicate_counts
							.get(&item.secret_value)
							.copied()
							.unwrap_or(0)
							> 1;

						let card_data = SecretRowData {
							secret_id: item.secret_id,
							icon_name: item.icon_name.clone(),
							type_label: item.type_label.clone(),
							title: item.title.clone(),
							created_at: item.created_at.clone(),
							login: item.login.clone(),
							url: item.url.clone(),
							secret_value: item.secret_value.clone(),
							color_class: item.color_class.clone(),
							health: item.health.clone(),
							usage_count: item.usage_count,
							is_duplicate,
							is_shared_vault: shared_vault,
									can_edit: !shared_vault || can_write,
									can_delete: !shared_vault || can_admin,
						};

						let card = Rc::new(SecretCard::new(card_data));
						let usage_count = Rc::new(Cell::new(item.usage_count));
						let kind = item.kind;

						let editor_launcher_for_edit = editor_launcher.clone();
						let secret_id_for_edit = item.secret_id;
						card.get_edit_button().connect_clicked(move |_| {
							if let Some(open_editor) = editor_launcher_for_edit.borrow().as_ref() {
								open_editor(DialogMode::Edit(secret_id_for_edit));
							}
						});

						let app_for_delete = application.clone();
						let parent_for_delete = parent_window.clone();
						let runtime_for_delete = runtime_handle.clone();
						let secret_for_delete = Arc::clone(&secret_service);
						let vault_for_delete = Arc::clone(&vault_service);
						let flow_for_delete = secret_flow.clone();
						let stack_for_delete = stack.clone();
						let empty_title_for_delete = empty_title.clone();
						let empty_copy_for_delete = empty_copy.clone();
						let master_for_delete = admin_master_key.clone();
						let filter_for_delete = filter_runtime.clone();
						let editor_launcher_for_delete = editor_launcher.clone();
						let active_vault_for_delete = active_vault_id.clone();
						let secret_id_for_delete = item.secret_id;
						let secret_title_for_delete = item.title.clone();
						let toast_overlay_for_delete = toast_overlay.clone();
						card.get_trash_button().connect_clicked(move |_| {
							let (sender, receiver) = tokio::sync::oneshot::channel();
							let secret_service_for_task = Arc::clone(&secret_for_delete);
							let runtime_for_task = runtime_for_delete.clone();
							std::thread::spawn(move || {
								let result = runtime_for_task.block_on(async move {
									secret_service_for_task.soft_delete(secret_id_for_delete).await
								});
								let _ = sender.send(result);
							});

							let app_for_refresh = app_for_delete.clone();
							let parent_for_refresh = parent_for_delete.clone();
							let runtime_for_refresh = runtime_for_delete.clone();
							let secret_for_refresh = Arc::clone(&secret_for_delete);
							let vault_for_refresh = Arc::clone(&vault_for_delete);
							let flow_for_refresh = flow_for_delete.clone();
							let stack_for_refresh = stack_for_delete.clone();
							let empty_title_refresh = empty_title_for_delete.clone();
							let empty_copy_refresh = empty_copy_for_delete.clone();
							let master_for_refresh = master_for_delete.clone();
							let filter_for_refresh = filter_for_delete.clone();
							let editor_launcher_for_refresh = editor_launcher_for_delete.clone();
							let secret_title_for_refresh = secret_title_for_delete.clone();
							let toast_overlay_for_refresh = toast_overlay_for_delete.clone();
							let active_vault_for_refresh = active_vault_for_delete.clone();
							glib::MainContext::default().spawn_local(async move {
								if matches!(receiver.await, Ok(Ok(()))) {
									let toast_message = messages::toast_secret_deleted(secret_title_for_refresh.as_str());
									toast_overlay_for_refresh.add_toast(adw::Toast::new(toast_message.as_str()));
									Self::refresh_secret_flow(
										app_for_refresh.clone(),
										parent_for_refresh.clone(),
										runtime_for_refresh.clone(),
										Arc::clone(&secret_for_refresh),
										Arc::clone(&vault_for_refresh),
										admin_user_id,
										master_for_refresh.clone(),
										flow_for_refresh.clone(),
										stack_for_refresh.clone(),
										empty_title_refresh.clone(),
										empty_copy_refresh.clone(),
										active_vault_for_refresh.clone(),
										toast_overlay_for_refresh.clone(),
										filter_for_refresh.clone(),
										editor_launcher_for_refresh.clone(),
									);
								}
							});
						});

						let copy_value = if !item.secret_value.is_empty() {
							item.secret_value.clone()
						} else {
							item.login.clone()
						};

						if copy_value.is_empty() {
							card.get_copy_button().set_sensitive(false);
						} else {
							let card_for_copy = Rc::clone(&card);
							let service_for_copy = Arc::clone(&secret_service);
							let runtime_for_copy = runtime_handle.clone();
							let usage_for_copy = Rc::clone(&usage_count);
							let secret_id_for_copy = item.secret_id;
							card.get_copy_button().connect_clicked(move |_| {
								if let Some(display) = gtk4::gdk::Display::default() {
									display.clipboard().set_text(&copy_value);
								}

								let new_value = usage_for_copy.get().saturating_add(1);
								usage_for_copy.set(new_value);
								card_for_copy.update_usage_count(new_value);

								let service_for_task = Arc::clone(&service_for_copy);
								let runtime_for_task = runtime_for_copy.clone();
								std::thread::spawn(move || {
									let _ = runtime_for_task.block_on(async move {
										service_for_task.increment_usage_count(secret_id_for_copy).await
									});
								});
							});
						}

						let card_widget = card.get_widget();
						let widget_key = format!("secret-card-{}", item.secret_id);
						card_widget.set_widget_name(&widget_key);
						filter_runtime.meta_by_widget.borrow_mut().insert(
							widget_key,
							SecretFilterMeta {
								searchable_text: Self::normalize_search_text(
									vec![
										item.title.clone(),
										item.type_label.clone(),
										item.login.clone(),
										item.email.clone(),
										item.url.clone(),
										item.notes.clone(),
										item.category.clone(),
										item.tags.clone(),
										item.created_at.clone(),
										item.health.clone(),
									]
									.join(" ")
									.as_str(),
								),
								title_text: Self::normalize_search_text(item.title.as_str()),
								login_text: Self::normalize_search_text(item.login.as_str()),
								email_text: Self::normalize_search_text(item.email.as_str()),
								url_text: Self::normalize_search_text(item.url.as_str()),
								notes_text: Self::normalize_search_text(item.notes.as_str()),
								category_text: Self::normalize_search_text(item.category.as_str()),
								tags_text: Self::normalize_search_text(item.tags.as_str()),
								type_text: Self::normalize_search_text(
									vec![
										item.type_label.clone(),
										match kind {
											SecretKind::Password => "password motdepasse mdp".to_string(),
											SecretKind::ApiToken => "token api acces".to_string(),
											SecretKind::SshKey => "ssh cle key".to_string(),
											SecretKind::SecureDocument => "document fichier".to_string(),
										},
									]
									.join(" ")
									.as_str(),
								),
								kind,
								original_rank,
								is_weak: item.health == crate::tr!("main-strength-weak"),
								is_duplicate,
							},
						);
						secret_flow.insert(&card_widget, -1);
					}

					Self::apply_filters(&secret_flow, &filter_runtime);
					stack.set_visible_child_name("list");
				}
				Ok(Err(_)) | Err(_) => {
					empty_title.set_text(crate::tr!("main-list-unavailable-title").as_str());
					empty_copy.set_text(crate::tr!("main-list-unavailable-description").as_str());
					stack.set_visible_child_name("empty");
				}
			}
		});
	}
}

struct CenterPanelWidgets {
	frame: gtk4::Frame,
	main_stack: gtk4::Stack,
	stack: gtk4::Stack,
	list_page: gtk4::Box,
	empty_state: gtk4::Box,
	secret_flow: gtk4::FlowBox,
	filtered_status_page: adw::StatusPage,
	status_total_chip: gtk4::Box,
	status_total_badge: gtk4::Label,
	status_non_compliant_chip: gtk4::Box,
	status_non_compliant_badge: gtk4::Label,
	sort_recent_button: gtk4::Button,
	sort_title_button: gtk4::Button,
	sort_risk_button: gtk4::Button,
	empty_title: gtk4::Label,
	empty_copy: gtk4::Label,
}

struct ProfileViewWidgets {
	container: gtk4::ScrolledWindow,
	back_button: gtk4::Button,
}

struct SidebarWidgets {
	frame: gtk4::Frame,
	my_vaults_title: gtk4::Label,
	create_vault_button: gtk4::Button,
	my_vaults_list: gtk4::ListBox,
	shared_vaults_title: gtk4::Label,
	shared_vaults_list: gtk4::ListBox,
	category_list: gtk4::ListBox,
	audit_list: gtk4::ListBox,
	audit_title: gtk4::Label,
	categories_title: gtk4::Label,
	account_title: gtk4::Label,
	audit_all_label: gtk4::Label,
	audit_weak_label: gtk4::Label,
	audit_duplicate_label: gtk4::Label,
	category_all_label: gtk4::Label,
	category_passwords_label: gtk4::Label,
	category_api_tokens_label: gtk4::Label,
	category_ssh_keys_label: gtk4::Label,
	category_documents_label: gtk4::Label,
	audit_all_badge: gtk4::Label,
	audit_weak_badge: gtk4::Label,
	audit_duplicate_badge: gtk4::Label,
	profile_security_label: gtk4::Label,
	profile_security_button: gtk4::Button,
	teams_label: gtk4::Label,
	teams_button: gtk4::Button,
	administration_label: gtk4::Label,
	administration_button: gtk4::Button,
}

struct SecretRowView {
	secret_id: Uuid,
	icon_name: String,
	type_label: String,
	title: String,
	created_at: String,
	login: String,
	email: String,
	url: String,
	notes: String,
	category: String,
	tags: String,
	secret_value: String,
	kind: SecretKind,
	color_class: String,
	health: String,
	usage_count: u32,
}
