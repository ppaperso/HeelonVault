use std::rc::Rc;
use std::sync::Arc;

use gtk4::glib;
use gtk4::prelude::*;
use gtk4::{Align, Orientation};
use libadwaita as adw;
use libadwaita::prelude::*;
use secrecy::SecretBox;
use tokio::runtime::Handle;
use uuid::Uuid;

use crate::services::secret_service::SecretService;
use crate::services::vault_service::VaultService;
use crate::ui::dialogs::add_edit_dialog::AddEditDialog;

pub struct MainWindow {
	window: adw::ApplicationWindow,
}

impl MainWindow {
	pub fn new<TSecret, TVault>(
		application: &adw::Application,
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		admin_user_id: Uuid,
		admin_master_key: Vec<u8>,
	) -> Self
	where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
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

		let header_bar = adw::HeaderBar::new();
		header_bar.add_css_class("main-headerbar");

		let root = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(12)
			.margin_top(10)
			.margin_bottom(10)
			.margin_start(10)
			.margin_end(10)
			.build();

		let title_label = gtk4::Label::new(Some("HeelonVault"));
		title_label.add_css_class("title-3");
		title_label.add_css_class("main-title");
		header_bar.set_title_widget(Some(&title_label));

		let add_button = gtk4::Button::with_label("Ajouter");
		add_button.add_css_class("primary-pill");
		add_button.add_css_class("main-add-button");
		add_button.set_tooltip_text(Some("Ajouter un secret"));

		let app_for_add = application.clone();
		let window_for_add = window.clone();
		let runtime_for_add = runtime_handle.clone();
		let secret_for_add = Arc::clone(&secret_service);
		let vault_for_add = Arc::clone(&vault_service);
		let admin_user_for_add = admin_user_id;
		let admin_master_for_add = admin_master_key.clone();

		let center_panel = Self::build_center_panel();
		let secret_list_for_refresh = center_panel.secret_list.clone();
		let stack_for_refresh = center_panel.stack.clone();
		let empty_title_for_refresh = center_panel.empty_title.clone();
		let empty_copy_for_refresh = center_panel.empty_copy.clone();

		let refresh_list: Rc<dyn Fn()> = {
			let runtime = runtime_handle.clone();
			let secret_service = Arc::clone(&secret_service);
			let vault_service = Arc::clone(&vault_service);
			let admin_master = admin_master_key.clone();
			let secret_list = secret_list_for_refresh.clone();
			let stack = stack_for_refresh.clone();
			let empty_title = empty_title_for_refresh.clone();
			let empty_copy = empty_copy_for_refresh.clone();
			Rc::new(move || {
				Self::refresh_secret_list(
					runtime.clone(),
					Arc::clone(&secret_service),
					Arc::clone(&vault_service),
					admin_user_id,
					admin_master.clone(),
					secret_list.clone(),
					stack.clone(),
					empty_title.clone(),
					empty_copy.clone(),
				);
			})
		};

		let refresh_for_add = Rc::clone(&refresh_list);
		add_button.connect_clicked(move |_| {
			let refresh_after_save = Rc::clone(&refresh_for_add);
			let dialog = AddEditDialog::new(
				&app_for_add,
				&window_for_add,
				runtime_for_add.clone(),
				Arc::clone(&secret_for_add),
				Arc::clone(&vault_for_add),
				admin_user_for_add,
				admin_master_for_add.clone(),
				move || {
					refresh_after_save();
				},
			);
			dialog.present();
		});
		header_bar.pack_end(&add_button);
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

		let sidebar_panel = Self::build_sidebar_panel();
		split.set_start_child(Some(&sidebar_panel));

		split.set_end_child(Some(&center_panel.frame));

		content.append(&actions_row);
		content.append(&split);
		root.append(&content);
		window.set_content(Some(&root));

		refresh_list();

		Self { window }
	}

	pub fn into_inner(self) -> adw::ApplicationWindow {
		self.window
	}

	fn build_sidebar_panel() -> gtk4::Frame {
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

		let sidebar_title = gtk4::Label::new(Some("Categories"));
		sidebar_title.add_css_class("main-section-title");
		sidebar_title.set_halign(Align::Start);
		sidebar_box.append(&sidebar_title);

		let category_list = gtk4::ListBox::new();
		category_list.add_css_class("boxed-list");
		category_list.add_css_class("main-category-list");
		category_list.set_selection_mode(gtk4::SelectionMode::Single);

		let rows = [
			("Toutes les categories", "view-grid-symbolic"),
			("Mots de passe", "dialog-password-symbolic"),
			("Tokens API", "dialog-key-symbolic"),
			("Cles SSH", "network-wired-symbolic"),
			("Documents securises", "folder-documents-symbolic"),
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
		sidebar_frame
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
		list_scroll.add_css_class("main-secret-list-scroll");

		let secret_list = gtk4::ListBox::new();
		secret_list.add_css_class("boxed-list");
		secret_list.add_css_class("main-secret-list");
		list_scroll.set_child(Some(&secret_list));

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

		stack.add_titled(&list_scroll, Some("list"), "Liste");
		stack.add_titled(&empty_state, Some("empty"), "Vide");
		stack.set_visible_child_name("empty");

		center_frame.set_child(Some(&stack));
		CenterPanelWidgets {
			frame: center_frame,
			stack,
			secret_list,
			empty_title,
			empty_copy: empty_description,
		}
	}

	#[allow(clippy::too_many_arguments)]
	fn refresh_secret_list<TSecret, TVault>(
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		admin_user_id: Uuid,
		admin_master_key: Vec<u8>,
		secret_list: gtk4::ListBox,
		stack: gtk4::Stack,
		empty_title: gtk4::Label,
		empty_copy: gtk4::Label,
	) where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
	{
		empty_title.set_text("Chargement des secrets...");
		empty_copy.set_text("Veuillez patienter.");
		stack.set_visible_child_name("empty");

		let (sender, receiver) = tokio::sync::oneshot::channel();
		std::thread::spawn(move || {
			let result = runtime_handle.block_on(async move {
				let vaults = vault_service.list_user_vaults(admin_user_id).await?;
				let first_vault = match vaults.into_iter().next() {
					Some(value) => value,
					None => return Ok(Vec::new()),
				};

				let _vault_key = vault_service
					.open_vault(
						first_vault.id,
						SecretBox::new(Box::new(admin_master_key.clone())),
					)
					.await?;

				secret_service.list_by_vault(first_vault.id).await
			});
			let _ = sender.send(result);
		});

		glib::MainContext::default().spawn_local(async move {
			match receiver.await {
				Ok(Ok(items)) => {
					while let Some(child) = secret_list.first_child() {
						secret_list.remove(&child);
					}

					if items.is_empty() {
						empty_title.set_text("Aucun secret pour le moment");
						empty_copy.set_text(
							"Utilisez le bouton Ajouter en haut a droite pour creer votre premier secret.",
						);
						stack.set_visible_child_name("empty");
						return;
					}

					for item in items {
						let row = gtk4::ListBoxRow::new();
						let row_box = gtk4::Box::builder()
							.orientation(Orientation::Vertical)
							.spacing(4)
							.margin_top(10)
							.margin_bottom(10)
							.margin_start(12)
							.margin_end(12)
							.build();

						let type_label = gtk4::Label::new(Some(&format!(
							"Type: {}",
							match item.secret_type {
								crate::models::SecretType::Password => "password",
								crate::models::SecretType::ApiToken => "api_token",
								crate::models::SecretType::SshKey => "ssh_key",
								crate::models::SecretType::SecureDocument => "secure_document",
							}
						)));
						type_label.set_halign(Align::Start);
						type_label.add_css_class("main-sidebar-label");

						let id_label = gtk4::Label::new(Some(&format!("ID: {}", item.id)));
						id_label.set_halign(Align::Start);
						id_label.add_css_class("login-support-copy");

						row_box.append(&type_label);
						row_box.append(&id_label);
						row.set_child(Some(&row_box));
						secret_list.append(&row);
					}

					stack.set_visible_child_name("list");
				}
				Ok(Err(_)) | Err(_) => {
					empty_title.set_text("Liste indisponible");
					empty_copy.set_text(
						"Impossible de charger les secrets pour le moment. Reessayez dans un instant.",
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
	secret_list: gtk4::ListBox,
	empty_title: gtk4::Label,
	empty_copy: gtk4::Label,
}
