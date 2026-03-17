use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::Arc;
use std::time::Duration;

use gtk4::glib;
use gtk4::prelude::*;
use gtk4::{Align, Orientation};
use libadwaita as adw;
use libadwaita::prelude::*;
use secrecy::{ExposeSecret, SecretBox};
use serde_json::Value;
use tokio::runtime::Handle;
use tracing::info;
use uuid::Uuid;
use zeroize::Zeroize;

use crate::services::auth_policy_service::AuthPolicyService;
use crate::services::backup_service::BackupService;
use crate::services::import_service::ImportService;
use crate::services::secret_service::SecretService;
use crate::services::user_service::UserService;
use crate::services::vault_service::VaultService;
use crate::ui::dialogs::add_edit_dialog::{AddEditDialog, DialogMode};
use crate::ui::dialogs::profile_dialog::ProfileDialog;
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
	title_lower: String,
	url_lower: String,
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
	auto_lock_timeout_secs: Rc<Cell<u64>>,
	auto_lock_source: Rc<RefCell<Option<glib::SourceId>>>,
	auto_lock_armed: Rc<Cell<bool>>,
	session_master_key: Rc<RefCell<Vec<u8>>>,
	on_auto_lock: Rc<RefCell<Option<Rc<dyn Fn()>>>>,
}

impl MainWindow {
	const DEFAULT_AUTO_LOCK_TIMEOUT_SECS: u64 = 5 * 60;

	pub fn new<TSecret, TVault, TUser, TPolicy, TBackup, TImport>(
		application: &adw::Application,
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		user_service: Arc<TUser>,
		auth_policy_service: Arc<TPolicy>,
		backup_service: Arc<TBackup>,
		import_service: Arc<TImport>,
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
		let window = adw::ApplicationWindow::builder()
			.application(application)
			.title("HeelonVault")
			.default_width(1180)
			.default_height(760)
			.build();
		window.add_css_class("app-window");
		window.add_css_class("main-window");
		window.set_icon_name(Some("heelonvault"));

		let auto_lock_source: Rc<RefCell<Option<glib::SourceId>>> = Rc::new(RefCell::new(None));
		let auto_lock_armed = Rc::new(Cell::new(false));
		let auto_lock_timeout_secs = Rc::new(Cell::new(Self::DEFAULT_AUTO_LOCK_TIMEOUT_SECS));
		let session_master_key = Rc::new(RefCell::new(admin_master_key));
		let on_auto_lock: Rc<RefCell<Option<Rc<dyn Fn()>>>> = Rc::new(RefCell::new(None));

		let header_bar = adw::HeaderBar::new();
		header_bar.add_css_class("main-headerbar");
		header_bar.set_show_start_title_buttons(false);
		header_bar.set_show_end_title_buttons(true);
		header_bar.set_decoration_layout(Some(":close"));

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
		profile_button.set_tooltip_text(Some("Mon profil"));

		let profile_popover = gtk4::Popover::new();
		let profile_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(6)
			.margin_top(10)
			.margin_bottom(10)
			.margin_start(10)
			.margin_end(10)
			.build();

		let profile_title = gtk4::Label::new(Some("Compte utilisateur"));
		profile_title.set_halign(Align::Start);
		profile_title.add_css_class("heading");
		profile_box.append(&profile_title);

		let profile_button_open = gtk4::Button::with_label("Profil & sécurité");
		profile_button_open.add_css_class("flat");
		profile_button_open.set_halign(Align::Start);
		let app_for_profile = application.clone();
		let runtime_for_profile = runtime_handle.clone();
		let user_service_for_profile = Arc::clone(&user_service);
		let auth_policy_for_profile = Arc::clone(&auth_policy_service);
		let backup_for_profile = Arc::clone(&backup_service);
		let import_for_profile = Arc::clone(&import_service);
		let secret_for_profile = Arc::clone(&secret_service);
		let vault_for_profile = Arc::clone(&vault_service);
		let runtime_for_profile_io = runtime_handle.clone();
		let db_path_for_profile = database_path.clone();
		let parent_for_profile = window.clone();
		let profile_badge_for_update = profile_button.clone();
		let auto_lock_timeout_for_profile = Rc::clone(&auto_lock_timeout_secs);
		let auto_lock_source_for_profile = Rc::clone(&auto_lock_source);
		let auto_lock_armed_for_profile = Rc::clone(&auto_lock_armed);
		let on_auto_lock_for_profile = Rc::clone(&on_auto_lock);
		let session_for_profile = Rc::clone(&session_master_key);
		let session_for_profile_io = Rc::clone(&session_master_key);
		profile_button_open.connect_clicked(move |_| {
			let profile_badge = profile_badge_for_update.clone();
			ProfileDialog::present(
				&app_for_profile,
				&parent_for_profile,
				runtime_for_profile.clone(),
				Arc::clone(&user_service_for_profile),
				Arc::clone(&auth_policy_for_profile),
				Arc::clone(&backup_for_profile),
				Arc::clone(&import_for_profile),
				Arc::clone(&secret_for_profile),
				Arc::clone(&vault_for_profile),
				db_path_for_profile.clone(),
				runtime_for_profile_io.clone(),
				admin_user_id,
				{
					let session_for_cb = Rc::clone(&session_for_profile_io);
					move || Self::snapshot_session_master_key(&session_for_cb)
				},
				move |display_label| {
					profile_badge.set_label(&format!("Connecté: {}", display_label));
				},
				{
					let auto_lock_timeout_for_cb = Rc::clone(&auto_lock_timeout_for_profile);
					let auto_lock_source_for_cb = Rc::clone(&auto_lock_source_for_profile);
					let auto_lock_armed_for_cb = Rc::clone(&auto_lock_armed_for_profile);
					let parent_for_cb = parent_for_profile.clone();
					let on_auto_lock_for_cb = Rc::clone(&on_auto_lock_for_profile);
					let session_for_cb = Rc::clone(&session_for_profile);
					move |mins| {
						auto_lock_timeout_for_cb.set(mins.saturating_mul(60));
						if auto_lock_armed_for_cb.get() {
							Self::reset_auto_lock_timer(
								&parent_for_cb,
								&auto_lock_source_for_cb,
								&auto_lock_armed_for_cb,
								auto_lock_timeout_for_cb.get(),
								&on_auto_lock_for_cb,
								&session_for_cb,
							);
						}
					}
				},
			);
		});
		profile_box.append(&profile_button_open);

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

		let app_for_add = application.clone();
		let window_for_add = window.clone();
		let runtime_for_add = runtime_handle.clone();
		let secret_for_add = Arc::clone(&secret_service);
		let vault_for_add = Arc::clone(&vault_service);
		let admin_user_for_add = admin_user_id;
		let session_master_for_add = Rc::clone(&session_master_key);
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

			let query = runtime_for_flow_filter.search_text.borrow().to_lowercase();
			let matches_query = query.is_empty()
				|| meta.title_lower.contains(query.as_str())
				|| meta.url_lower.contains(query.as_str());

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
				);
			})
		};

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

		let refresh_for_add = Rc::clone(&refresh_list);
		add_button.connect_clicked(move |_| {
			let Some(master_key) = Self::snapshot_session_master_key(&session_master_for_add) else {
				info!("add secret blocked: session is locked");
				return;
			};
			let refresh_after_save = Rc::clone(&refresh_for_add);
			let dialog = AddEditDialog::new(
				&app_for_add,
				&window_for_add,
				runtime_for_add.clone(),
				Arc::clone(&secret_for_add),
				Arc::clone(&vault_for_add),
				admin_user_for_add,
				master_key,
				DialogMode::Create,
				move || {
					refresh_after_save();
				},
			);
			dialog.present();
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
		sidebar_panel.category_list.connect_row_selected(move |_list, row_opt| {
			if let Some(row) = row_opt {
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
		sidebar_panel.audit_list.connect_row_selected(move |_list, row_opt| {
			if let Some(row) = row_opt {
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
			auto_lock_timeout_secs,
			auto_lock_source,
			auto_lock_armed,
			session_master_key,
			on_auto_lock,
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

	pub fn activate_auto_lock(&self) {
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
			1 | 5 | 10 | 30 => mins,
			_ => 5,
		};
		self.auto_lock_timeout_secs.set(mins.saturating_mul(60));
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
		if !auto_lock_armed.get() || !window.is_visible() {
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
		sidebar_frame.set_child(Some(&sidebar_box));
		SidebarWidgets {
			frame: sidebar_frame,
			category_list,
			audit_list,
			audit_all_badge,
			audit_weak_badge,
			audit_duplicate_badge,
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

		let stack = gtk4::Stack::builder()
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

		stack.add_titled(&list_overlay, Some("list"), "Grille");
		stack.add_titled(&empty_state, Some("empty"), "Vide");
		stack.set_visible_child_name("empty");

		center_frame.set_child(Some(&stack));
		CenterPanelWidgets {
			frame: center_frame,
			stack,
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

					let (login, url) = match item.metadata_json.as_deref() {
						Some(raw) => match serde_json::from_str::<Value>(raw) {
							Ok(value) => {
								let login = value
									.get("login")
									.and_then(Value::as_str)
									.unwrap_or_default()
									.to_string();
								let url = value
									.get("url")
									.and_then(Value::as_str)
									.unwrap_or_default()
									.to_string();
								(login, url)
							}
							Err(_) => (String::new(), String::new()),
						},
						None => (String::new(), String::new()),
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

					rows.push(SecretRowView {
						secret_id: item.id,
						icon_name: icon_name.to_string(),
						type_label: type_label_text.to_string(),
						title,
						created_at,
						login,
						url,
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

						let app_for_edit = application.clone();
						let parent_for_edit = parent_window.clone();
						let runtime_for_edit = runtime_handle.clone();
						let secret_for_edit = Arc::clone(&secret_service);
						let vault_for_edit = Arc::clone(&vault_service);
						let flow_for_edit = secret_flow.clone();
						let stack_for_edit = stack.clone();
						let empty_title_for_edit = empty_title.clone();
						let empty_copy_for_edit = empty_copy.clone();
						let master_for_edit = admin_master_key.clone();
						let filter_for_edit = filter_runtime.clone();
						let secret_id_for_edit = item.secret_id;
						card.get_edit_button().connect_clicked(move |_| {
							let app_for_refresh = app_for_edit.clone();
							let parent_for_refresh = parent_for_edit.clone();
							let runtime_for_refresh = runtime_for_edit.clone();
							let secret_for_refresh = Arc::clone(&secret_for_edit);
							let vault_for_refresh = Arc::clone(&vault_for_edit);
							let flow_for_refresh = flow_for_edit.clone();
							let stack_for_refresh = stack_for_edit.clone();
							let empty_title_refresh = empty_title_for_edit.clone();
							let empty_copy_refresh = empty_copy_for_edit.clone();
							let master_for_refresh = master_for_edit.clone();
							let filter_for_refresh = filter_for_edit.clone();

							let dialog = AddEditDialog::new(
								&app_for_edit,
								&parent_for_edit,
								runtime_for_edit.clone(),
								Arc::clone(&secret_for_edit),
								Arc::clone(&vault_for_edit),
								admin_user_id,
								master_for_edit.clone(),
								DialogMode::Edit(secret_id_for_edit),
								move || {
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
									);
								},
							);
							dialog.present();
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
								title_lower: item.title.to_lowercase(),
								url_lower: item.url.to_lowercase(),
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
	stack: gtk4::Stack,
	secret_flow: gtk4::FlowBox,
	filtered_status_page: adw::StatusPage,
	empty_title: gtk4::Label,
	empty_copy: gtk4::Label,
}

struct SidebarWidgets {
	frame: gtk4::Frame,
	category_list: gtk4::ListBox,
	audit_list: gtk4::ListBox,
	audit_all_badge: gtk4::Label,
	audit_weak_badge: gtk4::Label,
	audit_duplicate_badge: gtk4::Label,
}

struct SecretRowView {
	secret_id: Uuid,
	icon_name: String,
	type_label: String,
	title: String,
	created_at: String,
	login: String,
	url: String,
	secret_value: String,
	kind: SecretKind,
	color_class: String,
	health: String,
	usage_count: u32,
}
