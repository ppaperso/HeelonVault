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
use crate::services::backup_service::BackupService;
use crate::services::import_service::ImportService;
use crate::services::login_history_service::list_recent_logins;
use crate::services::secret_service::SecretService;
use crate::services::user_service::UserService;
use crate::services::vault_service::VaultService;
use crate::ui::dialogs::add_edit_dialog::{AddEditDialog, DialogMode};
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
	is_weak: bool,
	is_duplicate: bool,
}

#[derive(Clone)]
struct FilterRuntime {
	meta_by_widget: Rc<RefCell<HashMap<String, SecretFilterMeta>>>,
	search_text: Rc<RefCell<String>>,
	selected_category: Rc<Cell<SecretCategoryFilter>>,
	selected_audit: Rc<Cell<AuditFilter>>,
	audit_all_count_label: gtk4::Label,
	audit_weak_count_label: gtk4::Label,
	audit_duplicate_count_label: gtk4::Label,
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

	pub fn new<TSecret, TVault, TUser, TPolicy, TBackup, TImport>(
		application: &adw::Application,
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		user_service: Arc<TUser>,
		auth_policy_service: Arc<TPolicy>,
		backup_service: Arc<TBackup>,
		import_service: Arc<TImport>,
		database_pool: SqlitePool,
		database_path: PathBuf,
		admin_user_id: Uuid,
		admin_master_key: Vec<u8>,
		connected_identity_label: String,
	) -> Self
	where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
		TUser: UserService + Send + Sync + 'static,
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
		let on_auto_lock: Rc<RefCell<Option<Rc<dyn Fn()>>>> = Rc::new(RefCell::new(None));
		let on_logout: Rc<RefCell<Option<Rc<dyn Fn()>>>> = Rc::new(RefCell::new(None));

		let header_bar = adw::HeaderBar::new();
		header_bar.add_css_class("main-headerbar");
		header_bar.set_show_start_title_buttons(false);
		header_bar.set_show_end_title_buttons(true);
		header_bar.set_decoration_layout(Some(":close"));

		let on_logout_for_close = Rc::clone(&on_logout);
		window.connect_close_request(move |_| {
			if let Some(callback) = on_logout_for_close.borrow().as_ref() {
				callback();
			}
			glib::Propagation::Stop
		});

		let root = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(0)
			.build();

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
		title_box.append(&logo);
		title_box.append(&title_label);
		header_bar.set_title_widget(Some(&title_box));

		let profile_button = gtk4::MenuButton::new();
		profile_button.add_css_class("header-badge");
		profile_button.add_css_class("admin-badge");
		profile_button.set_label(&format!("Connecté: {}", connected_identity_label));
		profile_button.set_tooltip_text(Some("Dernières connexions"));

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

		let profile_title = gtk4::Label::new(Some("Dernières connexions"));
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

		let add_button = gtk4::Button::builder()
			.icon_name("list-add-symbolic")
			.build();
		add_button.add_css_class("flat");
		add_button.add_css_class("accent");
		add_button.add_css_class("main-add-button");
		add_button.set_tooltip_text(Some("Ajouter"));

		let trash_button = gtk4::Button::builder()
			.icon_name("user-trash-symbolic")
			.build();
		trash_button.add_css_class("flat");
		trash_button.add_css_class("main-add-button");
		trash_button.set_tooltip_text(Some("Corbeille"));

		let app_for_trash = application.clone();
		let window_for_trash = window.clone();
		let runtime_for_trash = runtime_handle.clone();
		let secret_for_trash = Arc::clone(&secret_service);
		let vault_for_trash = Arc::clone(&vault_service);
		let admin_user_for_trash = admin_user_id;
		let session_master_for_trash = Rc::clone(&session_master_key);

		let center_panel = Self::build_center_panel();
		let sidebar_panel = Self::build_sidebar_panel();
		let secret_flow_for_struct = center_panel.secret_flow.clone();
		let show_passwords_in_edit_pref = Rc::new(Cell::new(false));

		let filter_runtime = FilterRuntime {
			meta_by_widget: Rc::new(RefCell::new(HashMap::new())),
			search_text: Rc::new(RefCell::new(String::new())),
			selected_category: Rc::new(Cell::new(SecretCategoryFilter::All)),
			selected_audit: Rc::new(Cell::new(AuditFilter::All)),
			audit_all_count_label: sidebar_panel.audit_all_badge.clone(),
			audit_weak_count_label: sidebar_panel.audit_weak_badge.clone(),
			audit_duplicate_count_label: sidebar_panel.audit_duplicate_badge.clone(),
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

		let secret_flow_for_refresh = center_panel.secret_flow.clone();
		let stack_for_refresh = center_panel.stack.clone();
		let empty_title_for_refresh = center_panel.empty_title.clone();
		let empty_copy_for_refresh = center_panel.empty_copy.clone();
		let editor_launcher: Rc<RefCell<Option<Rc<dyn Fn(DialogMode)>>>> =
			Rc::new(RefCell::new(None));

		let refresh_list: Rc<dyn Fn()> = {
			let app = application.clone();
			let parent_window = window.clone();
			let runtime = runtime_handle.clone();
			let secret_service = Arc::clone(&secret_service);
			let vault_service = Arc::clone(&vault_service);
			let session_master = Rc::clone(&session_master_key);
			let secret_flow = secret_flow_for_refresh.clone();
			let stack = stack_for_refresh.clone();
			let empty_title = empty_title_for_refresh.clone();
			let empty_copy = empty_copy_for_refresh.clone();
			let filter_runtime = filter_runtime.clone();
			let editor_launcher = Rc::clone(&editor_launcher);
			Rc::new(move || {
				let Some(master_key) = Self::snapshot_session_master_key(&session_master) else {
					empty_title.set_text("Session verrouillée");
					empty_copy.set_text("Reconnectez-vous pour réactiver l'accès aux secrets.");
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
					filter_runtime.clone(),
					editor_launcher.clone(),
				);
			})
		};

		let profile_view = Self::build_profile_view(
			window.clone(),
			runtime_handle.clone(),
			Arc::clone(&user_service),
			Arc::clone(&auth_policy_service),
			Arc::clone(&backup_service),
			Arc::clone(&import_service),
			Arc::clone(&secret_service),
			Arc::clone(&vault_service),
			database_path.clone(),
			admin_user_id,
			profile_button.clone(),
			Rc::clone(&auto_lock_timeout_secs),
			Rc::clone(&auto_lock_source),
			Rc::clone(&auto_lock_armed),
			Rc::clone(&on_auto_lock),
			Rc::clone(&session_master_key),
			Rc::clone(&show_passwords_in_edit_pref),
			Rc::clone(&refresh_list),
		);
		center_panel
			.main_stack
			.add_titled(&profile_view.container, Some("profile_view"), "Profil & Sécurité");

		let main_stack_for_back = center_panel.main_stack.clone();
		profile_view.back_button.connect_clicked(move |_| {
			main_stack_for_back.set_visible_child_name("entries_view");
		});

		let main_stack_for_profile = center_panel.main_stack.clone();
		sidebar_panel.profile_security_button.connect_clicked(move |_| {
			main_stack_for_profile.set_visible_child_name("profile_view");
		});

		let secret_editor_host = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.vexpand(true)
			.hexpand(true)
			.build();
		center_panel
			.main_stack
			.add_titled(&secret_editor_host, Some("secret_editor_view"), "Créer/Modifier");

		let open_editor: Rc<dyn Fn(DialogMode)> = {
			let runtime_for_editor = runtime_handle.clone();
			let secret_for_editor = Arc::clone(&secret_service);
			let vault_for_editor = Arc::clone(&vault_service);
			let session_for_editor = Rc::clone(&session_master_key);
			let refresh_after_save = Rc::clone(&refresh_list);
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
						move || {
							refresh_after_save();
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
		panic_button.set_tooltip_text(Some(
			"Fermeture d'urgence — Efface les données sensibles et ferme l'application",
		));

		let panic_inner = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(5)
			.valign(Align::Center)
			.build();
		let panic_icon = gtk4::Image::from_icon_name("system-shutdown-symbolic");
		panic_icon.add_css_class("panic-badge-label");
		let panic_lbl = gtk4::Label::new(Some("Urgence"));
		panic_lbl.add_css_class("panic-badge-label");
		panic_inner.append(&panic_icon);
		panic_inner.append(&panic_lbl);
		panic_button.set_child(Some(&panic_inner));

		let window_for_panic = window.clone();
		panic_button.connect_clicked(move |_| {
			let dialog = adw::MessageDialog::new(
				Some(&window_for_panic),
				Some("Fermeture d'urgence"),
				Some(
					"Les structures sensibles (clés, SecretBox) seront libérées \
					par le système d'exploitation lors de la terminaison du processus. \
					\n\nCette action est irréversible.",
				),
			);
			dialog.add_response("cancel", "Annuler");
			dialog.add_response("wipe_exit", "Effacer et quitter");
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
		add_button.connect_clicked(move |_| {
			open_editor_for_add(DialogMode::Create);
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
		header_bar.pack_end(&profile_button);
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
			.placeholder_text("Rechercher un secret")
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
		window.set_content(Some(&root));

		let flow_for_search = center_panel.secret_flow.clone();
		let filter_for_search = filter_runtime.clone();
		search_entry.connect_search_changed(move |entry| {
			*filter_for_search.search_text.borrow_mut() = entry.text().to_string();
			Self::apply_filters(&flow_for_search, &filter_for_search);
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

		refresh_list();

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
				return "Robuste".to_string();
			}
		}
		"Faible".to_string()
	}

	fn apply_filters(secret_flow: &gtk4::FlowBox, filter_runtime: &FilterRuntime) {
		let (all_count, weak_count, duplicate_count) = {
			let store = filter_runtime.meta_by_widget.borrow();
			let all_count = store.len();
			let weak_count = store.values().filter(|meta| meta.is_weak).count();
			let duplicate_count = store.values().filter(|meta| meta.is_duplicate).count();
			(all_count, weak_count, duplicate_count)
		};

		Self::update_audit_badge(&filter_runtime.audit_all_count_label, all_count);
		Self::update_audit_badge(&filter_runtime.audit_weak_count_label, weak_count);
		Self::update_audit_badge(&filter_runtime.audit_duplicate_count_label, duplicate_count);

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
		dialog.add_response("ok", "OK");
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

		let loading_label = gtk4::Label::new(Some("Chargement..."));
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
						let row_label = gtk4::Label::new(Some("Aucune connexion recente"));
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
					let row_label = gtk4::Label::new(Some(
						"Historique indisponible (chargement échoué).",
					));
					row_label.set_halign(Align::Start);
					row_label.add_css_class("profile-login-history-muted");
					list_box.append(&row_label);
				}
			}
		});
	}

	#[allow(clippy::too_many_arguments)]
	fn build_profile_view<TUser, TPolicy, TBackup, TImport, TSecret, TVault>(
		window: adw::ApplicationWindow,
		runtime_handle: Handle,
		user_service: Arc<TUser>,
		auth_policy_service: Arc<TPolicy>,
		backup_service: Arc<TBackup>,
		import_service: Arc<TImport>,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		database_path: PathBuf,
		user_id: Uuid,
		profile_badge: gtk4::MenuButton,
		auto_lock_timeout_secs: Rc<Cell<u64>>,
		auto_lock_source: Rc<RefCell<Option<glib::SourceId>>>,
		auto_lock_armed: Rc<Cell<bool>>,
		on_auto_lock: Rc<RefCell<Option<Rc<dyn Fn()>>>>,
		session_master_key: Rc<RefCell<Vec<u8>>>,
		show_passwords_in_edit_pref: Rc<Cell<bool>>,
		on_import_completed_refresh: Rc<dyn Fn()>,
	) -> ProfileViewWidgets
	where
		TUser: UserService + Send + Sync + 'static,
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
		let back_button = gtk4::Button::with_label("← Retour");
		back_button.add_css_class("flat");
		back_button.set_halign(Align::Start);
		let title = gtk4::Label::new(Some("Profil & Sécurité"));
		title.add_css_class("title-3");
		title.add_css_class("heading");
		title.set_hexpand(true);
		title.set_halign(Align::Center);
		header.append(&back_button);
		header.append(&title);
		content.append(&header);

		let profile_intro = gtk4::Label::new(Some(
			"Gérez vos informations de compte, paramètres de sécurité et opérations de données.",
		));
		profile_intro.set_halign(Align::Start);
		profile_intro.set_wrap(true);
		profile_intro.add_css_class("dim-label");
		content.append(&profile_intro);

		let info_frame = gtk4::Frame::builder().label("Informations").build();
		info_frame.add_css_class("profile-section-frame");
		let info_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();
		let info_subtitle = gtk4::Label::new(Some(
			"Les changements d'email nécessitent votre mot de passe actuel.",
		));
		info_subtitle.set_halign(Align::Start);
		info_subtitle.set_wrap(true);
		info_subtitle.add_css_class("profile-section-subtitle");
		info_subtitle.add_css_class("dim-label");
		info_box.append(&info_subtitle);
		let username_label = gtk4::Label::new(Some("Nom d'utilisateur"));
		username_label.set_halign(Align::Start);
		username_label.add_css_class("profile-field-label");
		let username_entry = gtk4::Entry::new();
		username_entry.set_sensitive(false);
		username_entry.set_hexpand(true);
		username_entry.add_css_class("profile-field-entry");
		let display_label = gtk4::Label::new(Some("Nom d'affichage"));
		display_label.set_halign(Align::Start);
		display_label.add_css_class("profile-field-label");
		let display_entry = gtk4::Entry::new();
		display_entry.set_hexpand(true);
		display_entry.add_css_class("profile-field-entry");
		let email_label = gtk4::Label::new(Some("Email"));
		email_label.set_halign(Align::Start);
		email_label.add_css_class("profile-field-label");
		let email_entry = gtk4::Entry::new();
		email_entry.set_hexpand(true);
		email_entry.add_css_class("profile-field-entry");
		let current_email_pw_label = gtk4::Label::new(Some("Mot de passe actuel (si changement email)"));
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
		let save_profile_button = gtk4::Button::with_label("Sauvegarder");
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
			current_email_pw_label.upcast_ref::<gtk4::Widget>(),
			current_email_pw_entry.upcast_ref::<gtk4::Widget>(),
			profile_status_label.upcast_ref::<gtk4::Widget>(),
			save_profile_row.upcast_ref::<gtk4::Widget>(),
		] {
			info_box.append(widget);
		}
		info_frame.set_child(Some(&info_box));
		content.append(&info_frame);

		let security_frame = gtk4::Frame::builder().label("Sécurité").build();
		security_frame.add_css_class("profile-section-frame");
		let security_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();
		let security_subtitle = gtk4::Label::new(Some(
			"Renforcez l'accès à votre coffre et ajustez le verrouillage automatique.",
		));
		security_subtitle.set_halign(Align::Start);
		security_subtitle.set_wrap(true);
		security_subtitle.add_css_class("profile-section-subtitle");
		security_subtitle.add_css_class("dim-label");
		security_box.append(&security_subtitle);
		let current_pw_label = gtk4::Label::new(Some("Mot de passe actuel"));
		current_pw_label.set_halign(Align::Start);
		current_pw_label.add_css_class("profile-field-label");
		let current_pw_entry = gtk4::PasswordEntry::new();
		current_pw_entry.set_hexpand(true);
		current_pw_entry.add_css_class("profile-field-entry");

		let auto_lock_label = gtk4::Label::new(Some("Délai de verrouillage automatique"));
		auto_lock_label.set_halign(Align::Start);
		auto_lock_label.add_css_class("profile-field-label");
		let auto_lock_items = gtk4::StringList::new(&["1 min", "5 min", "15 min", "30 min", "jamais"]);
		let auto_lock_dropdown = gtk4::DropDown::new(Some(auto_lock_items.clone()), None::<gtk4::Expression>);
		auto_lock_dropdown.add_css_class("profile-field-entry");

		let show_edit_passwords_label = gtk4::Label::new(Some(
			"Affichage du mot de passe actuel en mode modification",
		));
		show_edit_passwords_label.set_halign(Align::Start);
		show_edit_passwords_label.add_css_class("profile-field-label");
		let show_edit_passwords_hint = gtk4::Label::new(Some(
			"Affiche des étoiles dans le champ mot de passe de l'éditeur, avec icône oeil pour le révéler.",
		));
		show_edit_passwords_hint.set_halign(Align::Start);
		show_edit_passwords_hint.set_wrap(true);
		show_edit_passwords_hint.add_css_class("dim-label");
		show_edit_passwords_hint.add_css_class("profile-section-subtitle");
		let show_edit_passwords_switch = gtk4::Switch::new();
		show_edit_passwords_switch.set_halign(Align::Start);

		let new_pw_label = gtk4::Label::new(Some("Nouveau mot de passe"));
		new_pw_label.set_halign(Align::Start);
		new_pw_label.add_css_class("profile-field-label");
		let new_pw_entry = gtk4::PasswordEntry::new();
		new_pw_entry.set_hexpand(true);
		new_pw_entry.add_css_class("profile-field-entry");
		let confirm_pw_label = gtk4::Label::new(Some("Confirmer le nouveau mot de passe"));
		confirm_pw_label.set_halign(Align::Start);
		confirm_pw_label.add_css_class("profile-field-label");
		let confirm_pw_entry = gtk4::PasswordEntry::new();
		confirm_pw_entry.set_hexpand(true);
		confirm_pw_entry.add_css_class("profile-field-entry");
		let security_status_label = gtk4::Label::new(None);
		security_status_label.set_halign(Align::Start);
		security_status_label.set_wrap(true);
		security_status_label.add_css_class("inline-status");
		security_status_label.add_css_class("profile-inline-status");
		security_status_label.set_visible(false);

		let security_actions = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.hexpand(true)
			.halign(Align::End)
			.build();
		security_actions.add_css_class("profile-actions-row");
		let change_pw_button = gtk4::Button::with_label("Changer");
		change_pw_button.add_css_class("suggested-action");
		change_pw_button.add_css_class("profile-action-btn");
		change_pw_button.set_tooltip_text(Some(
			"Prépare le changement: place le focus sur les champs mot de passe et rappelle la marche à suivre.",
		));
		let rotate_master_key_button = gtk4::Button::with_label("Mettre à jour la master key");
		rotate_master_key_button.add_css_class("suggested-action");
		rotate_master_key_button.add_css_class("profile-action-btn");
		rotate_master_key_button.set_tooltip_text(Some(
			"Applique le changement de mot de passe maître avec validation (ancien mot de passe, confirmation).",
		));
		security_actions.append(&change_pw_button);
		security_actions.append(&rotate_master_key_button);

		for widget in [
			current_pw_label.upcast_ref::<gtk4::Widget>(),
			current_pw_entry.upcast_ref::<gtk4::Widget>(),
			auto_lock_label.upcast_ref::<gtk4::Widget>(),
			auto_lock_dropdown.upcast_ref::<gtk4::Widget>(),
			show_edit_passwords_label.upcast_ref::<gtk4::Widget>(),
			show_edit_passwords_switch.upcast_ref::<gtk4::Widget>(),
			show_edit_passwords_hint.upcast_ref::<gtk4::Widget>(),
			new_pw_label.upcast_ref::<gtk4::Widget>(),
			new_pw_entry.upcast_ref::<gtk4::Widget>(),
			confirm_pw_label.upcast_ref::<gtk4::Widget>(),
			confirm_pw_entry.upcast_ref::<gtk4::Widget>(),
			security_status_label.upcast_ref::<gtk4::Widget>(),
			security_actions.upcast_ref::<gtk4::Widget>(),
		] {
			security_box.append(widget);
		}
		security_frame.set_child(Some(&security_box));
		content.append(&security_frame);

		let data_frame = gtk4::Frame::builder().label("Gestion des données").build();
		data_frame.add_css_class("profile-section-frame");
		let data_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();
		let export_title = gtk4::Label::new(Some("Exporter ma base (.hvb)"));
		export_title.set_halign(Align::Start);
		export_title.add_css_class("heading");
		export_title.add_css_class("profile-field-label");
		let export_subtitle = gtk4::Label::new(Some("Sauvegarde chiffrée AES-256-GCM avec Recovery Key"));
		export_subtitle.set_halign(Align::Start);
		export_subtitle.add_css_class("dim-label");
		export_subtitle.add_css_class("profile-section-subtitle");
		export_subtitle.set_wrap(true);
		let export_button = gtk4::Button::with_label("Exporter ma base");
		export_button.add_css_class("suggested-action");
		export_button.add_css_class("profile-action-btn");
		export_button.set_halign(Align::End);

		let import_title = gtk4::Label::new(Some("Importer des données (CSV)"));
		import_title.set_halign(Align::Start);
		import_title.add_css_class("heading");
		import_title.add_css_class("profile-field-label");
		let import_subtitle = gtk4::Label::new(Some("Colonnes attendues: name, url, username, password, notes"));
		import_subtitle.set_halign(Align::Start);
		import_subtitle.add_css_class("dim-label");
		import_subtitle.add_css_class("profile-section-subtitle");
		import_subtitle.set_wrap(true);
		let import_button = gtk4::Button::with_label("Importer des données (CSV)");
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
		content.append(&data_frame);

		container.set_child(Some(&content));

		let content_for_compact = content.clone();
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

		let loading_lock = Rc::new(Cell::new(true));
		let (sender, receiver) = tokio::sync::oneshot::channel();
		let service_for_load = Arc::clone(&user_service);
		let policy_for_load = Arc::clone(&auth_policy_service);
		let runtime_for_load = runtime_handle.clone();
		std::thread::spawn(move || {
			let result = runtime_for_load.block_on(async move {
				let user = service_for_load.get_user_profile(user_id).await?;
				let delay = policy_for_load.get_auto_lock_delay(user.username.as_str()).await?;
				Ok::<_, crate::errors::AppError>((user, delay))
			});
			let _ = sender.send(result);
		});

		let username_entry_for_load = username_entry.clone();
		let display_entry_for_load = display_entry.clone();
		let email_entry_for_load = email_entry.clone();
		let auto_lock_for_load = auto_lock_dropdown.clone();
		let show_edit_passwords_for_load = show_edit_passwords_switch.clone();
		let show_passwords_pref_for_load = Rc::clone(&show_passwords_in_edit_pref);
		let loading_lock_for_load = Rc::clone(&loading_lock);
		let profile_status_for_load = profile_status_label.clone();
		glib::MainContext::default().spawn_local(async move {
			match receiver.await {
				Ok(Ok((user, delay))) => {
					username_entry_for_load.set_text(user.username.as_str());
					display_entry_for_load.set_text(user.display_name.as_deref().unwrap_or_default());
					email_entry_for_load.set_text(user.email.as_deref().unwrap_or_default());
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
					loading_lock_for_load.set(false);
				}
				_ => {
					loading_lock_for_load.set(false);
					Self::set_inline_status(
						&profile_status_for_load,
						"Chargement du profil indisponible pour le moment.",
						"error",
					);
				}
			}
		});

		let policy_for_delay = Arc::clone(&auth_policy_service);
		let runtime_for_delay = runtime_handle.clone();
		let username_for_delay = username_entry.clone();
		let loading_lock_for_delay = Rc::clone(&loading_lock);
		let window_for_delay = window.clone();
		let security_status_for_delay = security_status_label.clone();
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
			Self::set_inline_status(
				&security_status_for_delay,
				"Mise à jour du délai de verrouillage...",
				"loading",
			);

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
						Self::set_inline_status(
							&security_status_for_result,
							"Délai de verrouillage automatique mis à jour.",
							"success",
						);
					}
					_ => {
						Self::set_inline_status(
							&security_status_for_result,
							"Impossible de mettre à jour le délai de verrouillage.",
							"error",
						);
					}
				}
			});
		});

		let service_for_profile_save = Arc::clone(&user_service);
		let runtime_for_profile_save = runtime_handle.clone();
		let display_for_save = display_entry.clone();
		let email_for_save = email_entry.clone();
		let current_email_pw_for_save = current_email_pw_entry.clone();
		let show_edit_passwords_for_save = show_edit_passwords_switch.clone();
		let show_passwords_pref_for_save = Rc::clone(&show_passwords_in_edit_pref);
		let profile_badge_for_save = profile_badge.clone();
		let profile_status_for_save = profile_status_label.clone();
		let service_for_toggle = Arc::clone(&user_service);
		let runtime_for_toggle = runtime_handle.clone();
		let profile_status_for_toggle = profile_status_label.clone();
		let show_passwords_pref_for_toggle = Rc::clone(&show_passwords_in_edit_pref);
		show_edit_passwords_switch.connect_active_notify(move |switch_widget| {
			let enabled = switch_widget.is_active();
			Self::set_inline_status(
				&profile_status_for_toggle,
				"Mise à jour de la préférence d'affichage...",
				"loading",
			);

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
						Self::set_inline_status(
							&profile_status_for_result,
							"Préférence d'affichage mot de passe mise à jour.",
							"success",
						);
					}
					_ => {
						Self::set_inline_status(
							&profile_status_for_result,
							"Impossible de mettre à jour cette préférence.",
							"error",
						);
					}
				}
			});
		});
		save_profile_button.connect_clicked(move |_| {
			Self::set_inline_status(
				&profile_status_for_save,
				"Enregistrement des modifications...",
				"loading",
			);
			let payload = crate::services::user_service::UserProfileUpdate {
				email: {
					let value = email_for_save.text().trim().to_string();
					if value.is_empty() { None } else { Some(value) }
				},
				display_name: {
					let value = display_for_save.text().trim().to_string();
					if value.is_empty() { None } else { Some(value) }
				},
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
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok(Ok(user)) => {
						let display = user
							.display_name
							.clone()
							.filter(|value| !value.trim().is_empty())
							.unwrap_or(user.username.clone());
						show_passwords_pref_for_result.set(user.show_passwords_in_edit);
						badge_for_result.set_label(&format!("Connecté: {}", display));
						Self::set_inline_status(&profile_status_for_result, "Profil mis à jour.", "success");
					}
					_ => {
						Self::set_inline_status(
							&profile_status_for_result,
							"Échec de la mise à jour du profil.",
							"error",
						);
					}
				}
			});
		});

		let service_for_pw_change = Arc::clone(&user_service);
		let runtime_for_pw_change = runtime_handle.clone();
		let current_pw_for_change = current_pw_entry.clone();
		let security_status_for_pw_change = security_status_label.clone();
		change_pw_button.connect_clicked(move |_| {
			Self::set_inline_status(
				&security_status_for_pw_change,
				"Changement prêt: renseignez les champs puis cliquez sur 'Mettre à jour la master key'.",
				"success",
			);
			current_pw_for_change.grab_focus();
		});

		let service_for_rotate = Arc::clone(&service_for_pw_change);
		let runtime_for_rotate = runtime_for_pw_change.clone();
		let current_pw_for_rotate = current_pw_entry.clone();
		let new_pw_for_rotate = new_pw_entry.clone();
		let confirm_pw_for_rotate = confirm_pw_entry.clone();
		let security_status_for_rotate = security_status_label.clone();
		rotate_master_key_button.connect_clicked(move |_| {
			let current_raw = current_pw_for_rotate.text().trim().to_string();
			let new_raw = new_pw_for_rotate.text().trim().to_string();
			let confirm_raw = confirm_pw_for_rotate.text().trim().to_string();
			if current_raw.is_empty() || new_raw.is_empty() || confirm_raw.is_empty() {
				Self::set_inline_status(
					&security_status_for_rotate,
					"Tous les champs mot de passe sont obligatoires pour mettre à jour la master key.",
					"error",
				);
				return;
			}
			if new_raw != confirm_raw {
				Self::set_inline_status(
					&security_status_for_rotate,
					"La confirmation ne correspond pas au nouveau mot de passe.",
					"error",
				);
				return;
			}

			Self::set_inline_status(
				&security_status_for_rotate,
				"Mise à jour de la master key...",
				"loading",
			);

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
						Self::set_inline_status(
							&security_status_for_result,
							"Master key mise à jour.",
							"success",
						);
					}
					_ => {
						Self::set_inline_status(
							&security_status_for_result,
							"Échec du changement de mot de passe.",
							"error",
						);
					}
				}
			});
		});

		let window_for_export = window.clone();
		let backup_for_export = Arc::clone(&backup_service);
		let database_path_for_export = database_path.clone();
		export_button.connect_clicked(move |_| {
			let chooser = gtk4::FileChooserNative::builder()
				.title("Exporter la base chiffrée")
				.transient_for(&window_for_export)
				.accept_label("Exporter")
				.cancel_label("Annuler")
				.action(gtk4::FileChooserAction::Save)
				.build();
			chooser.set_current_name("heelonvault_backup.hvb");

			let window_for_response = window_for_export.clone();
			let backup_for_response = Arc::clone(&backup_for_export);
			let db_path_for_response = database_path_for_export.clone();
			chooser.connect_response(move |dialog, response| {
				if response != gtk4::ResponseType::Accept {
					dialog.destroy();
					return;
				}

				let selected = dialog.file();
				dialog.destroy();
				let Some(file) = selected else {
					Self::show_feedback_dialog(&window_for_response, "Export", "Destination invalide.");
					return;
				};
				let Some(mut export_path) = file.path() else {
					Self::show_feedback_dialog(&window_for_response, "Export", "Chemin invalide.");
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
							"Export",
							"Impossible de générer la Recovery Key.",
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
				std::thread::spawn(move || {
					let result = backup_for_task.export_hvb_with_recovery_key(
						db_for_task.as_path(),
						path_for_task.as_path(),
						&phrase_for_task,
					);
					let _ = sender.send(result);
				});

				let window_for_result = window_for_response.clone();
				glib::MainContext::default().spawn_local(async move {
					match receiver.await {
						Ok(Ok(_)) => {
							let message = format!(
								"Export terminé. Notez votre Recovery Key:\n\n{}",
								recovery_text
							);
							Self::show_feedback_dialog(&window_for_result, "Export .hvb", message.as_str());
						}
						_ => {
							Self::show_feedback_dialog(&window_for_result, "Export", "Échec de l'export .hvb.");
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
		import_button.connect_clicked(move |_| {
			let chooser = gtk4::FileChooserNative::builder()
				.title("Importer des données CSV")
				.transient_for(&window_for_import)
				.accept_label("Importer")
				.cancel_label("Annuler")
				.action(gtk4::FileChooserAction::Open)
				.build();

			let window_for_response = window_for_import.clone();
			let import_for_response = Arc::clone(&import_for_profile);
			let secret_for_response = Arc::clone(&secret_for_import);
			let vault_for_response = Arc::clone(&vault_for_import);
			let runtime_for_response = runtime_for_import.clone();
			let session_for_response = Rc::clone(&session_for_import);
			let refresh_for_response = Rc::clone(&refresh_for_import);
			chooser.connect_response(move |dialog, response| {
				if response != gtk4::ResponseType::Accept {
					dialog.destroy();
					return;
				}

				let selected = dialog.file();
				dialog.destroy();
				let Some(file) = selected else {
					Self::show_feedback_dialog(&window_for_response, "Import", "Fichier CSV invalide.");
					return;
				};
				let Some(csv_path) = file.path() else {
					Self::show_feedback_dialog(&window_for_response, "Import", "Chemin CSV invalide.");
					return;
				};

				let Some(master_key) = Self::snapshot_session_master_key(&session_for_response) else {
					Self::show_feedback_dialog(
						&window_for_response,
						"Import",
						"Session verrouillée, reconnectez-vous.",
					);
					return;
				};

				let (sender, receiver) = tokio::sync::oneshot::channel();
				let import_for_task = Arc::clone(&import_for_response);
				let secret_for_task = Arc::clone(&secret_for_response);
				let vault_for_task = Arc::clone(&vault_for_response);
				let runtime_for_task = runtime_for_response.clone();
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
				glib::MainContext::default().spawn_local(async move {
					match receiver.await {
						Ok(Ok(count)) => {
							refresh_for_result();
							let message = format!("Import CSV terminé: {} secrets.", count);
							Self::show_feedback_dialog(&window_for_result, "Import", message.as_str());
						}
						_ => {
							Self::show_feedback_dialog(&window_for_result, "Import", "Échec de l'import CSV.");
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

		let audit_title = gtk4::Label::new(Some("Audit de Sécurité"));
		audit_title.add_css_class("main-section-title");
		audit_title.set_halign(Align::Start);
		sidebar_box.append(&audit_title);

		let audit_list = gtk4::ListBox::new();
		audit_list.add_css_class("boxed-list");
		audit_list.add_css_class("main-audit-list");
		audit_list.set_selection_mode(gtk4::SelectionMode::Single);

		let (audit_all_row, audit_all_badge) = Self::build_audit_sidebar_row("Tous", "view-grid-symbolic");
		let (audit_weak_row, audit_weak_badge) = Self::build_audit_sidebar_row(
			"Mots de passe faibles",
			"dialog-warning-symbolic",
		);
		let (audit_duplicate_row, audit_duplicate_badge) =
			Self::build_audit_sidebar_row("Doublons", "content-copy-symbolic");
		audit_list.append(&audit_all_row);
		audit_list.append(&audit_weak_row);
		audit_list.append(&audit_duplicate_row);
		audit_list.select_row(Some(&audit_all_row));
		sidebar_box.append(&audit_list);

		let sidebar_title = gtk4::Label::new(Some("Catégories"));
		sidebar_title.add_css_class("main-section-title");
		sidebar_title.set_halign(Align::Start);
		sidebar_box.append(&sidebar_title);

		let category_list = gtk4::ListBox::new();
		category_list.add_css_class("boxed-list");
		category_list.add_css_class("main-category-list");
		category_list.set_selection_mode(gtk4::SelectionMode::Single);

		let rows = [
			("Toutes les catégories", "view-grid-symbolic"),
			("Mots de passe", "dialog-password-symbolic"),
			("Tokens API", "dialog-key-symbolic"),
			("Clés SSH", "network-wired-symbolic"),
			("Documents sécurisés", "folder-documents-symbolic"),
		];

		for (index, (title, icon_name)) in rows.into_iter().enumerate() {
			let row = Self::build_sidebar_row(title, icon_name);
			category_list.append(&row);
			if index == 0 {
				category_list.select_row(Some(&row));
			}
		}

		sidebar_box.append(&category_list);

		let account_title = gtk4::Label::new(Some("Compte"));
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
		let profile_security_label = gtk4::Label::new(Some("Profil & Sécurité"));
		profile_security_label.add_css_class("main-sidebar-label");
		profile_security_label.set_halign(Align::Start);
		profile_security_label.set_hexpand(true);
		profile_security_inner.append(&profile_security_icon);
		profile_security_inner.append(&profile_security_label);
		profile_security_button.set_child(Some(&profile_security_inner));
		sidebar_box.append(&profile_security_button);

		sidebar_frame.set_child(Some(&sidebar_box));
		SidebarWidgets {
			frame: sidebar_frame,
			category_list,
			audit_list,
			audit_all_badge,
			audit_weak_badge,
			audit_duplicate_badge,
			profile_security_button,
		}
	}

	fn build_audit_sidebar_row(title: &str, icon_name: &str) -> (gtk4::ListBoxRow, gtk4::Label) {
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
		(row, badge)
	}

	fn build_sidebar_row(title: &str, icon_name: &str) -> gtk4::ListBoxRow {
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
		row
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
			.title("Aucun secret trouvé")
			.description("Ajustez votre recherche ou vos filtres.")
			.icon_name("edit-find-symbolic")
			.build();
		filtered_status_page.set_visible(false);
		filtered_status_page.set_can_target(false);

		let list_overlay = gtk4::Overlay::new();
		list_overlay.set_child(Some(&list_scroll));
		list_overlay.add_overlay(&filtered_status_page);

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

		let empty_title = gtk4::Label::new(Some("Aucun secret pour le moment"));
		empty_title.add_css_class("title-3");
		empty_title.add_css_class("main-empty-title");

		let empty_description = gtk4::Label::new(Some(
			"Utilisez le bouton Ajouter en haut a droite pour creer votre premier secret.",
		));
		empty_description.set_wrap(true);
		empty_description.set_justify(gtk4::Justification::Center);
		empty_description.set_max_width_chars(54);
		empty_description.add_css_class("main-empty-copy");

		empty_state.append(&empty_icon);
		empty_state.append(&empty_title);
		empty_state.append(&empty_description);

		entries_stack.add_titled(&list_overlay, Some("list"), "Grille");
		entries_stack.add_titled(&empty_state, Some("empty"), "Vide");
		entries_stack.set_visible_child_name("empty");

		let main_stack = gtk4::Stack::builder()
			.vexpand(true)
			.hexpand(true)
			.transition_type(gtk4::StackTransitionType::Crossfade)
			.build();
		main_stack.set_transition_duration(200);
		main_stack.add_titled(&entries_stack, Some("entries_view"), "Secrets");
		main_stack.set_visible_child_name("entries_view");

		center_frame.set_child(Some(&main_stack));
		CenterPanelWidgets {
			frame: center_frame,
			main_stack,
			stack: entries_stack,
			secret_flow,
			filtered_status_page,
			empty_title,
			empty_copy: empty_description,
		}
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
		filter_runtime: FilterRuntime,
		editor_launcher: Rc<RefCell<Option<Rc<dyn Fn(DialogMode)>>>>,
	) where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
	{
		empty_title.set_text("Chargement des secrets...");
		empty_copy.set_text("Veuillez patienter.");
		stack.set_visible_child_name("empty");

		let runtime_for_loader = runtime_handle.clone();
		let secret_for_loader = Arc::clone(&secret_service);
		let vault_for_loader = Arc::clone(&vault_service);
		let admin_master_for_loader = admin_master_key.clone();

		let (sender, receiver) = tokio::sync::oneshot::channel();
		std::thread::spawn(move || {
			let result: Result<Vec<SecretRowView>, crate::errors::AppError> =
				runtime_for_loader.block_on(async move {
				let vaults = vault_for_loader.list_user_vaults(admin_user_id).await?;
				let first_vault = match vaults.into_iter().next() {
					Some(value) => value,
					None => return Ok(Vec::new()),
				};

				let vault_key = vault_for_loader
					.open_vault(
						first_vault.id,
						SecretBox::new(Box::new(admin_master_for_loader.clone())),
					)
					.await?;

				let items = secret_for_loader.list_by_vault(first_vault.id).await?;
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
						crate::models::SecretType::Password => ("dialog-password-symbolic", "Mot de passe"),
						crate::models::SecretType::ApiToken => ("dialog-key-symbolic", "Token API"),
						crate::models::SecretType::SshKey => ("network-wired-symbolic", "Clé SSH"),
						crate::models::SecretType::SecureDocument => {
							("folder-documents-symbolic", "Document sécurisé")
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

					let title = item.title.unwrap_or_else(|| type_label_text.to_string());
					let created_at = item
						.created_at
						.unwrap_or_else(|| "date indisponible".to_string());
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

				Ok(rows)
			});
			let _ = sender.send(result);
		});

		glib::MainContext::default().spawn_local(async move {
			match receiver.await {
				Ok(Ok(items)) => {
					filter_runtime.meta_by_widget.borrow_mut().clear();
					filter_runtime.audit_all_count_label.set_text("0");
					filter_runtime.audit_weak_count_label.set_text("0");
					filter_runtime.audit_duplicate_count_label.set_text("0");
					filter_runtime.filtered_status_page.set_visible(false);

					while let Some(child) = secret_flow.first_child() {
						secret_flow.remove(&child);
					}

					if items.is_empty() {
						empty_title.set_text("Aucun secret pour le moment");
						empty_copy.set_text(
							"Utilisez le bouton Ajouter en haut a droite pour creer votre premier secret.",
						);
						stack.set_visible_child_name("empty");
						return;
					}

					let mut duplicate_counts: HashMap<String, usize> = HashMap::new();
					for item in &items {
						if !item.secret_value.is_empty() {
							*duplicate_counts.entry(item.secret_value.clone()).or_insert(0) += 1;
						}
					}

					for item in items {
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
						let secret_id_for_delete = item.secret_id;
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
							glib::MainContext::default().spawn_local(async move {
								if matches!(receiver.await, Ok(Ok(()))) {
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
								is_weak: item.health == "Faible",
								is_duplicate,
							},
						);
						secret_flow.insert(&card_widget, -1);
					}

					Self::apply_filters(&secret_flow, &filter_runtime);
					stack.set_visible_child_name("list");
				}
				Ok(Err(_)) | Err(_) => {
					empty_title.set_text("Liste indisponible");
					empty_copy.set_text(
						"Impossible de charger les secrets pour le moment. Réessayez dans un instant.",
					);
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
	secret_flow: gtk4::FlowBox,
	filtered_status_page: adw::StatusPage,
	empty_title: gtk4::Label,
	empty_copy: gtk4::Label,
}

struct ProfileViewWidgets {
	container: gtk4::ScrolledWindow,
	back_button: gtk4::Button,
}

struct SidebarWidgets {
	frame: gtk4::Frame,
	category_list: gtk4::ListBox,
	audit_list: gtk4::ListBox,
	audit_all_badge: gtk4::Label,
	audit_weak_badge: gtk4::Label,
	audit_duplicate_badge: gtk4::Label,
	profile_security_button: gtk4::Button,
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
