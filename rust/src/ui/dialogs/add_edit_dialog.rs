use std::rc::Rc;
use std::sync::Arc;

use gtk4::glib;
use gtk4::prelude::*;
use gtk4::{Align, Orientation};
use libadwaita as adw;
use secrecy::{ExposeSecret, SecretBox};
use serde_json::{Map, Value};
use time::Duration;
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;
use tokio::runtime::Handle;
use uuid::Uuid;

use crate::models::SecretType;
use crate::services::password_service::{PasswordService, PasswordServiceImpl};
use crate::services::secret_service::SecretService;
use crate::services::vault_service::VaultService;
use crate::ui::widgets::password_strength_bar::PasswordStrengthBar;

#[derive(Clone, Copy, Debug)]
pub enum DialogMode {
	Create,
	Edit(Uuid),
}

pub struct AddEditDialog {
	window: gtk4::Window,
}

impl AddEditDialog {
	#[allow(clippy::too_many_arguments)]
	pub fn new<TSecret, TVault>(
		application: &adw::Application,
		parent: &adw::ApplicationWindow,
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		admin_user_id: Uuid,
		admin_master_key: Vec<u8>,
		mode: DialogMode,
		on_saved: impl Fn() + 'static,
	) -> Self
	where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
	{
		let on_saved: Rc<dyn Fn()> = Rc::new(on_saved);
		let window = gtk4::Window::builder()
			.application(application)
			.transient_for(parent)
			.title(match mode {
				DialogMode::Create => "Nouveau secret",
				DialogMode::Edit(_) => "Modifier le secret",
			})
			.modal(true)
			.default_width(660)
			.default_height(760)
			.build();
		window.add_css_class("app-window");
		window.add_css_class("add-edit-dialog");

		let root = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(12)
			.margin_top(16)
			.margin_bottom(16)
			.margin_start(16)
			.margin_end(16)
			.build();

		let header_card = gtk4::Frame::new(None);
		header_card.add_css_class("login-hero");

		let header_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(14)
			.margin_top(16)
			.margin_bottom(16)
			.margin_start(16)
			.margin_end(16)
			.build();

		let header_icon =
			gtk4::Image::from_resource("/com/heelonvault/rust/icons/hicolor/128x128/apps/heelonvault.png");
		header_icon.set_pixel_size(42);
		header_icon.add_css_class("login-hero-icon");

		let header_text = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(4)
			.hexpand(true)
			.build();

		let title = gtk4::Label::new(Some(match mode {
			DialogMode::Create => "Ajouter un secret",
			DialogMode::Edit(_) => "Modifier le secret",
		}));
		title.add_css_class("title-2");
		title.add_css_class("login-hero-title");
		title.set_halign(Align::Start);

		let subtitle = gtk4::Label::new(Some(match mode {
			DialogMode::Create => "Sélectionnez un type puis renseignez les champs associés.",
			DialogMode::Edit(_) => {
				"Mettez a jour les champs souhaites. Laissez le secret vide pour le conserver."
			}
		}));
		subtitle.add_css_class("login-hero-copy");
		subtitle.set_halign(Align::Start);
		subtitle.set_wrap(true);

		header_text.append(&title);
		header_text.append(&subtitle);
		header_box.append(&header_icon);
		header_box.append(&header_text);
		header_card.set_child(Some(&header_box));

		let scrolled = gtk4::ScrolledWindow::builder()
			.vexpand(true)
			.hscrollbar_policy(gtk4::PolicyType::Never)
			.build();

		let form_card = gtk4::Frame::new(None);
		form_card.add_css_class("login-card");

		let form_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(12)
			.margin_top(18)
			.margin_bottom(18)
			.margin_start(18)
			.margin_end(18)
			.build();

		let (title_row, title_entry) =
			Self::build_labeled_entry("Titre *", "Nom lisible du secret", "dialog-title-entry");
		let (category_row, category_entry) = Self::build_labeled_entry(
			"Catégorie",
			"Personnel, Travail, Infrastructure...",
			"dialog-category-entry",
		);
		let (tags_row, tags_entry) = Self::build_labeled_entry(
			"Tags (séparés par des virgules)",
			"prod, client-a, finance",
			"dialog-tags-entry",
		);

		let type_label = gtk4::Label::new(Some("Type de secret"));
		type_label.add_css_class("login-field-label");
		type_label.set_halign(Align::Start);

		let type_items = gtk4::StringList::new(&[
			"password",
			"api_token",
			"ssh_key",
			"secure_document",
		]);
		let type_dropdown = gtk4::DropDown::builder().model(&type_items).build();
		type_dropdown.add_css_class("dialog-type-dropdown");
		type_dropdown.set_selected(0);

		let dynamic_stack = gtk4::Stack::builder()
			.transition_type(gtk4::StackTransitionType::SlideLeftRight)
			.hexpand(true)
			.build();
		dynamic_stack.add_css_class("dialog-dynamic-stack");

		let (password_panel, password_entry, password_strength_bar) = Self::build_password_panel();
		dynamic_stack.add_titled(&password_panel, Some("password"), "password");

		let (api_token_panel, api_token_entry, api_provider_entry) = Self::build_api_token_panel();
		dynamic_stack.add_titled(&api_token_panel, Some("api_token"), "api_token");

		let (ssh_key_panel, ssh_private_text, ssh_public_entry, ssh_passphrase_entry) =
			Self::build_ssh_key_panel();
		dynamic_stack.add_titled(&ssh_key_panel, Some("ssh_key"), "ssh_key");

		let (secure_doc_panel, secure_doc_path_entry, secure_doc_mime_entry) =
			Self::build_secure_document_panel();
		dynamic_stack.add_titled(
			&secure_doc_panel,
			Some("secure_document"),
			"secure_document",
		);
		dynamic_stack.set_visible_child_name("password");

		let stack_for_type = dynamic_stack.clone();
		type_dropdown.connect_selected_notify(move |dropdown| {
			let view_name = match dropdown.selected() {
				0 => "password",
				1 => "api_token",
				2 => "ssh_key",
				3 => "secure_document",
				_ => "password",
			};
			stack_for_type.set_visible_child_name(view_name);
		});

		let (username_row, username_entry) = Self::build_labeled_entry(
			"Nom d'utilisateur / Login",
			"alice@example.com",
			"dialog-username-entry",
		);
		let (url_row, url_entry) =
			Self::build_labeled_entry("URL", "https://example.com", "dialog-url-entry");

		let notes_label = gtk4::Label::new(Some("Notes"));
		notes_label.add_css_class("login-field-label");
		notes_label.set_halign(Align::Start);

		let notes_scrolled = gtk4::ScrolledWindow::builder()
			.min_content_height(120)
			.hscrollbar_policy(gtk4::PolicyType::Never)
			.build();
		notes_scrolled.add_css_class("dialog-notes-scroll");

		let notes_text = gtk4::TextView::new();
		notes_text.set_wrap_mode(gtk4::WrapMode::WordChar);
		notes_text.set_left_margin(10);
		notes_text.set_right_margin(10);
		notes_text.set_top_margin(10);
		notes_text.set_bottom_margin(10);
		notes_text.add_css_class("dialog-notes-text");
		notes_scrolled.set_child(Some(&notes_text));

		let validity_label = gtk4::Label::new(Some("Validité"));
		validity_label.add_css_class("login-field-label");
		validity_label.set_halign(Align::Start);

		let validity_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();

		let validity_unlimited = gtk4::CheckButton::with_label("Validité illimitée");
		validity_unlimited.add_css_class("dialog-validity-check");

		let validity_adjustment = gtk4::Adjustment::new(90.0, 1.0, 3650.0, 1.0, 30.0, 0.0);
		let validity_days = gtk4::SpinButton::builder()
			.adjustment(&validity_adjustment)
			.digits(0)
			.numeric(true)
			.build();
		validity_days.add_css_class("dialog-validity-spin");
		validity_box.append(&validity_unlimited);
		validity_box.append(&validity_days);

		let days_for_toggle = validity_days.clone();
		validity_unlimited.connect_toggled(move |toggle| {
			days_for_toggle.set_sensitive(!toggle.is_active());
		});

		let error_label = gtk4::Label::new(None);
		error_label.add_css_class("login-error");
		error_label.set_halign(Align::Start);
		error_label.set_wrap(true);
		error_label.set_visible(false);

		let button_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.halign(Align::End)
			.build();

		let cancel_button = gtk4::Button::with_label("Annuler");
		cancel_button.add_css_class("secondary-pill");

		let save_button = gtk4::Button::new();
		save_button.add_css_class("primary-pill");
		let save_button_content = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.halign(Align::Center)
			.build();
		let save_spinner = gtk4::Spinner::new();
		save_spinner.set_visible(false);
		let save_label = gtk4::Label::new(Some(match mode {
			DialogMode::Create => "Enregistrer",
			DialogMode::Edit(_) => "Mettre a jour",
		}));
		save_button_content.append(&save_spinner);
		save_button_content.append(&save_label);
		save_button.set_child(Some(&save_button_content));

		// Gate: save is only allowed when the password tab's score is Robuste (4).
		// For all other secret types (api_token, ssh_key, secure_document) there is
		// no password strength requirement, so the button stays enabled.
		{
			use std::rc::Rc;
			let strength  = password_strength_bar.clone();
			let dropdown  = type_dropdown.clone();
			let btn       = save_button.clone();
			let check: Rc<dyn Fn()> = Rc::new(move || {
				let is_password_type = dropdown.selected() == 0;
				btn.set_sensitive(!is_password_type || strength.last_score() >= 4);
			});
			check();
			let c = Rc::clone(&check);
			password_entry.connect_text_notify(move |_| c());
			let c = Rc::clone(&check);
			type_dropdown.connect_selected_notify(move |_| c());
		}

		let dialog_for_cancel = window.clone();
		cancel_button.connect_clicked(move |_| {
			dialog_for_cancel.close();
		});

		let dialog_for_save = window.clone();
		let title_for_save = title_entry.clone();
		let category_for_save = category_entry.clone();
		let tags_for_save = tags_entry.clone();
		let type_for_save = type_dropdown.clone();
		let username_for_save = username_entry.clone();
		let url_for_save = url_entry.clone();
		let notes_for_save = notes_text.buffer();
		let validity_unlimited_for_save = validity_unlimited.clone();
		let validity_days_for_save = validity_days.clone();
		let password_for_save = password_entry.clone();
		let api_token_for_save = api_token_entry.clone();
		let api_provider_for_save = api_provider_entry.clone();
		let ssh_private_for_save = ssh_private_text.clone();
		let ssh_public_for_save = ssh_public_entry.clone();
		let ssh_passphrase_for_save = ssh_passphrase_entry.clone();
		let secure_doc_for_save = secure_doc_path_entry.clone();
		let secure_doc_mime_for_save = secure_doc_mime_entry.clone();
		let error_for_save = error_label.clone();
		let spinner_for_save = save_spinner.clone();
		let save_btn_for_save = save_button.clone();
		let secret_for_save = Arc::clone(&secret_service);
		let vault_for_save = Arc::clone(&vault_service);
		let runtime_for_save = runtime_handle.clone();
		let on_saved_for_save = Rc::clone(&on_saved);
		let mode_for_save = mode;
		let admin_master_for_save_seed = admin_master_key.clone();
		save_button.connect_clicked(move |_| {
			error_for_save.set_visible(false);
			error_for_save.set_text("");

			let title = title_for_save.text().trim().to_string();
			if title.is_empty() {
				error_for_save.set_text("Le titre est obligatoire.");
				error_for_save.set_visible(true);
				return;
			}

			let selected_type = type_for_save.selected();
			let category = category_for_save.text().trim().to_string();
			let tags_value = tags_for_save.text().trim().to_string();
			let username = username_for_save.text().trim().to_string();
			let url = url_for_save.text().trim().to_string();
			let notes = notes_for_save
				.text(&notes_for_save.start_iter(), &notes_for_save.end_iter(), false)
				.to_string();
			let expires_at = if validity_unlimited_for_save.is_active() {
				None
			} else {
				let days = i64::from(validity_days_for_save.value_as_int());
				if days <= 0 {
					None
				} else {
					let ts = OffsetDateTime::now_utc() + Duration::days(days);
					ts.format(&Rfc3339).ok()
				}
			};
			let metadata_json = {
				let mut metadata = Map::new();
				metadata.insert("category".to_string(), Value::String(category));
				metadata.insert("notes".to_string(), Value::String(notes));
				metadata.insert("login".to_string(), Value::String(username));
				metadata.insert("url".to_string(), Value::String(url));
				metadata.insert(
					"validity_unlimited".to_string(),
					Value::Bool(validity_unlimited_for_save.is_active()),
				);
				metadata.insert(
					"validity_days".to_string(),
					Value::Number(i64::from(validity_days_for_save.value_as_int()).into()),
				);
				if selected_type == 1 {
					metadata.insert(
						"provider".to_string(),
						Value::String(api_provider_for_save.text().trim().to_string()),
					);
				}
				if selected_type == 2 {
					metadata.insert(
						"ssh_public_key".to_string(),
						Value::String(ssh_public_for_save.text().trim().to_string()),
					);
					metadata.insert(
						"ssh_passphrase".to_string(),
						Value::String(ssh_passphrase_for_save.text().trim().to_string()),
					);
				}
				if selected_type == 3 {
					metadata.insert(
						"document_mime".to_string(),
						Value::String(secure_doc_mime_for_save.text().trim().to_string()),
					);
				}
				Some(Value::Object(metadata).to_string())
			};

			let (secret_type, secret_text) = match selected_type {
				0 => (SecretType::Password, password_for_save.text().to_string()),
				1 => (SecretType::ApiToken, api_token_for_save.text().to_string()),
				2 => {
					let buffer = ssh_private_for_save.buffer();
					let text = buffer
						.text(&buffer.start_iter(), &buffer.end_iter(), false)
						.to_string();
					(SecretType::SshKey, text)
				}
				3 => (
					SecretType::SecureDocument,
					secure_doc_for_save.text().to_string(),
				),
				_ => (SecretType::Password, password_for_save.text().to_string()),
			};

			if matches!(mode_for_save, DialogMode::Create) && secret_text.trim().is_empty() {
				error_for_save.set_text("Le secret est obligatoire pour ce type.");
				error_for_save.set_visible(true);
				return;
			}

			save_btn_for_save.set_sensitive(false);
			save_spinner.set_visible(true);
			save_spinner.set_spinning(true);

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let secret_service_for_task = Arc::clone(&secret_for_save);
			let vault_service_for_task = Arc::clone(&vault_for_save);
			let runtime_for_task = runtime_for_save.clone();
			let admin_master_for_task = admin_master_for_save_seed.clone();
			let title_for_task = title.clone();
			let metadata_for_task = metadata_json.clone();
			let tags_for_task = if tags_value.is_empty() {
				None
			} else {
				Some(tags_value)
			};
			let expires_for_task = expires_at.clone();
			let secret_payload = secret_text.into_bytes();
			std::thread::spawn(move || {
				let result = runtime_for_task.block_on(async move {
					let vaults = vault_service_for_task.list_user_vaults(admin_user_id).await?;
					let target_vault = vaults
						.into_iter()
						.next()
						.ok_or_else(|| crate::errors::AppError::NotFound("vault not found".to_string()))?;
					let vault_key = vault_service_for_task
						.open_vault(
							target_vault.id,
							SecretBox::new(Box::new(admin_master_for_task.clone())),
						)
						.await?;

					match mode_for_save {
						DialogMode::Create => {
							secret_service_for_task
								.create_secret(
									target_vault.id,
									secret_type,
									Some(title_for_task),
									metadata_for_task,
									tags_for_task,
									expires_for_task,
									SecretBox::new(Box::new(secret_payload)),
									vault_key,
								)
								.await
								.map(|_| ())
						}
						DialogMode::Edit(secret_id) => {
							let secret_to_update = if secret_payload.is_empty() {
								None
							} else {
								Some(SecretBox::new(Box::new(secret_payload)))
							};
							secret_service_for_task
								.update_secret(
									secret_id,
									Some(title_for_task),
									metadata_for_task,
									tags_for_task,
									expires_for_task,
									secret_to_update,
									vault_key,
								)
								.await
						}
					}
				});
				let _ = sender.send(result);
			});

			let dialog_for_result = dialog_for_save.clone();
			let error_for_result = error_for_save.clone();
			let save_btn_for_result = save_btn_for_save.clone();
			let spinner_for_result = spinner_for_save.clone();
			let on_saved_for_result = Rc::clone(&on_saved_for_save);
			glib::MainContext::default().spawn_local(async move {
				save_btn_for_result.set_sensitive(true);
				spinner_for_result.set_visible(false);
				spinner_for_result.set_spinning(false);

				match receiver.await {
					Ok(Ok(_)) => {
						on_saved_for_result();
						dialog_for_result.close();
					}
					Ok(Err(_)) | Err(_) => {
						error_for_result.set_text(
							"Impossible d'enregistrer le secret pour le moment. Réessayez.",
						);
						error_for_result.set_visible(true);
					}
				}
			});
		});

		button_row.append(&cancel_button);
		button_row.append(&save_button);

		form_box.append(&title_row);
		form_box.append(&category_row);
		form_box.append(&tags_row);
		form_box.append(&type_label);
		form_box.append(&type_dropdown);
		form_box.append(&dynamic_stack);
		form_box.append(&username_row);
		form_box.append(&url_row);
		form_box.append(&notes_label);
		form_box.append(&notes_scrolled);
		form_box.append(&validity_label);
		form_box.append(&validity_box);
		form_box.append(&error_label);
		form_box.append(&button_row);

		form_card.set_child(Some(&form_box));
		scrolled.set_child(Some(&form_card));
		root.append(&header_card);
		root.append(&scrolled);
		window.set_child(Some(&root));

		if let DialogMode::Edit(secret_id) = mode {
			type_dropdown.set_sensitive(false);
			Self::setup_for_edit(
				runtime_handle,
				Arc::clone(&secret_service),
				Arc::clone(&vault_service),
				admin_user_id,
				admin_master_key.clone(),
				secret_id,
				title_entry.clone(),
				category_entry.clone(),
				tags_entry.clone(),
				type_dropdown.clone(),
				username_entry.clone(),
				url_entry.clone(),
				notes_text.buffer(),
				validity_unlimited.clone(),
				validity_days.clone(),
				api_provider_entry.clone(),
				ssh_public_entry.clone(),
				ssh_passphrase_entry.clone(),
				secure_doc_mime_entry.clone(),
				error_label.clone(),
			);
		}

		Self::install_local_css();
		Self { window }
	}

	pub fn present(&self) {
		self.window.present();
	}

	fn build_labeled_entry(
		label_text: &str,
		placeholder: &str,
		css_class: &str,
	) -> (gtk4::Box, gtk4::Entry) {
		let box_widget = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(6)
			.build();

		let label = gtk4::Label::new(Some(label_text));
		label.add_css_class("login-field-label");
		label.set_halign(Align::Start);

		let entry = gtk4::Entry::builder().placeholder_text(placeholder).build();
		entry.add_css_class("login-entry");
		entry.add_css_class(css_class);

		box_widget.append(&label);
		box_widget.append(&entry);
		(box_widget, entry)
	}

	fn build_password_panel() -> (gtk4::Frame, gtk4::PasswordEntry, PasswordStrengthBar) {
		let frame = gtk4::Frame::new(None);
		frame.add_css_class("dialog-type-frame");

		let box_widget = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();

		let password_label = gtk4::Label::new(Some("Mot de passe *"));
		password_label.add_css_class("login-field-label");
		password_label.set_halign(Align::Start);

		let password_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();

		let password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text("Saisissez un mot de passe")
			.show_peek_icon(true)
			.hexpand(true)
			.build();
		password_entry.add_css_class("login-entry");

		let generate_button = gtk4::Button::with_label("Générer");
		generate_button.add_css_class("secondary-pill");

		let generated_password_entry = password_entry.clone();
		generate_button.connect_clicked(move |_| {
			let (sender, receiver) = tokio::sync::oneshot::channel();
			std::thread::spawn(move || {
				let service = PasswordServiceImpl::new();
				let result = service.generate_password(24);
				let _ = sender.send(result);
			});

			let entry_for_result = generated_password_entry.clone();
			glib::MainContext::default().spawn_local(async move {
				if let Ok(Ok(value)) = receiver.await {
					if let Ok(text) = String::from_utf8(value.expose_secret().clone()) {
						entry_for_result.set_text(&text);
					}
				}
			});
		});

		password_row.append(&password_entry);
		password_row.append(&generate_button);

		let strength_bar = PasswordStrengthBar::new();
		strength_bar.connect_to_password_entry(&password_entry);

		box_widget.append(&password_label);
		box_widget.append(&password_row);
		box_widget.append(strength_bar.root());
		frame.set_child(Some(&box_widget));
		(frame, password_entry, strength_bar)
	}

	fn build_api_token_panel() -> (gtk4::Frame, gtk4::PasswordEntry, gtk4::Entry) {
		let frame = gtk4::Frame::new(None);
		frame.add_css_class("dialog-type-frame");

		let box_widget = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();

		let token_label = gtk4::Label::new(Some("Token API *"));
		token_label.add_css_class("login-field-label");
		token_label.set_halign(Align::Start);

		let token_entry = gtk4::PasswordEntry::builder()
			.placeholder_text("pk_live_... ou token equivalent")
			.show_peek_icon(true)
			.build();
		token_entry.add_css_class("login-entry");

		let (provider_row, provider_entry) =
			Self::build_labeled_entry("Fournisseur", "GitHub, Stripe, OpenAI...", "dialog-api-provider-entry");

		box_widget.append(&token_label);
		box_widget.append(&token_entry);
		box_widget.append(&provider_row);
		frame.set_child(Some(&box_widget));
		(frame, token_entry, provider_entry)
	}

	fn build_ssh_key_panel() -> (gtk4::Frame, gtk4::TextView, gtk4::Entry, gtk4::Entry) {
		let frame = gtk4::Frame::new(None);
		frame.add_css_class("dialog-type-frame");

		let box_widget = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();

		let private_key_label = gtk4::Label::new(Some("Clé privée SSH *"));
		private_key_label.add_css_class("login-field-label");
		private_key_label.set_halign(Align::Start);

		let private_key_scrolled = gtk4::ScrolledWindow::builder()
			.min_content_height(120)
			.hscrollbar_policy(gtk4::PolicyType::Never)
			.build();

		let private_key_text = gtk4::TextView::new();
		private_key_text.set_wrap_mode(gtk4::WrapMode::WordChar);
		private_key_text.add_css_class("dialog-ssh-private-key-text");
		private_key_scrolled.set_child(Some(&private_key_text));

		let (public_row, public_entry) =
			Self::build_labeled_entry("Clé publique", "ssh-ed25519 AAAA...", "dialog-ssh-public-entry");
		let (passphrase_row, passphrase_entry) = Self::build_labeled_entry(
			"Passphrase (optionnel)",
			"Passphrase de protection de clé",
			"dialog-ssh-passphrase-entry",
		);

		box_widget.append(&private_key_label);
		box_widget.append(&private_key_scrolled);
		box_widget.append(&public_row);
		box_widget.append(&passphrase_row);
		frame.set_child(Some(&box_widget));
		(frame, private_key_text, public_entry, passphrase_entry)
	}

	fn build_secure_document_panel() -> (gtk4::Frame, gtk4::Entry, gtk4::Entry) {
		let frame = gtk4::Frame::new(None);
		frame.add_css_class("dialog-type-frame");

		let box_widget = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.margin_top(12)
			.margin_bottom(12)
			.margin_start(12)
			.margin_end(12)
			.build();

		let (path_row, path_entry) = Self::build_labeled_entry(
			"Chemin du document *",
			"/home/user/Documents/contrat.pdf",
			"dialog-document-path-entry",
		);
		let (mime_row, mime_entry) =
			Self::build_labeled_entry("Type MIME", "application/pdf", "dialog-document-mime-entry");

		let import_hint = gtk4::Label::new(Some(
			"Import de fichier et chiffrement réel branchés dans une étape suivante.",
		));
		import_hint.add_css_class("login-support-copy");
		import_hint.set_wrap(true);
		import_hint.set_halign(Align::Start);

		box_widget.append(&path_row);
		box_widget.append(&mime_row);
		box_widget.append(&import_hint);
		frame.set_child(Some(&box_widget));
		(frame, path_entry, mime_entry)
	}

	#[allow(clippy::too_many_arguments)]
	fn setup_for_edit<TSecret, TVault>(
		runtime_handle: Handle,
		secret_service: Arc<TSecret>,
		vault_service: Arc<TVault>,
		admin_user_id: Uuid,
		admin_master_key: Vec<u8>,
		secret_id: Uuid,
		title_entry: gtk4::Entry,
		category_entry: gtk4::Entry,
		tags_entry: gtk4::Entry,
		type_dropdown: gtk4::DropDown,
		username_entry: gtk4::Entry,
		url_entry: gtk4::Entry,
		notes_buffer: gtk4::TextBuffer,
		validity_unlimited: gtk4::CheckButton,
		validity_days: gtk4::SpinButton,
		api_provider_entry: gtk4::Entry,
		ssh_public_entry: gtk4::Entry,
		ssh_passphrase_entry: gtk4::Entry,
		secure_doc_mime_entry: gtk4::Entry,
		error_label: gtk4::Label,
	) where
		TSecret: SecretService + Send + Sync + 'static,
		TVault: VaultService + Send + Sync + 'static,
	{
		let (sender, receiver) = tokio::sync::oneshot::channel();
		std::thread::spawn(move || {
			let result: Result<crate::models::SecretItem, crate::errors::AppError> =
				runtime_handle.block_on(async move {
					let vaults = vault_service.list_user_vaults(admin_user_id).await?;
					let target_vault = vaults
						.into_iter()
						.next()
						.ok_or_else(|| crate::errors::AppError::NotFound("vault not found".to_string()))?;

					let _vault_key = vault_service
						.open_vault(
							target_vault.id,
							SecretBox::new(Box::new(admin_master_key.clone())),
						)
						.await?;

					let items = secret_service.list_by_vault(target_vault.id).await?;
					items
						.into_iter()
						.find(|item| item.id == secret_id)
						.ok_or_else(|| {
							crate::errors::AppError::NotFound("secret not found".to_string())
						})
				});
			let _ = sender.send(result);
		});

		glib::MainContext::default().spawn_local(async move {
			match receiver.await {
				Ok(Ok(item)) => {
					title_entry.set_text(item.title.as_deref().unwrap_or_default());
					tags_entry.set_text(item.tags.as_deref().unwrap_or_default());

					let type_index = match item.secret_type {
						SecretType::Password => 0,
						SecretType::ApiToken => 1,
						SecretType::SshKey => 2,
						SecretType::SecureDocument => 3,
					};
					type_dropdown.set_selected(type_index);

					if let Some(raw_metadata) = item.metadata_json {
						if let Ok(value) = serde_json::from_str::<Value>(&raw_metadata) {
							category_entry.set_text(
								value
									.get("category")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);
							username_entry.set_text(
								value
									.get("login")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);
							url_entry.set_text(
								value
									.get("url")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);
							notes_buffer.set_text(
								value
									.get("notes")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);

							api_provider_entry.set_text(
								value
									.get("provider")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);
							ssh_public_entry.set_text(
								value
									.get("ssh_public_key")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);
							ssh_passphrase_entry.set_text(
								value
									.get("ssh_passphrase")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);
							secure_doc_mime_entry.set_text(
								value
									.get("document_mime")
									.and_then(Value::as_str)
									.unwrap_or_default(),
							);

							let unlimited = value
								.get("validity_unlimited")
								.and_then(Value::as_bool)
								.unwrap_or(item.expires_at.is_none());
							validity_unlimited.set_active(unlimited);

							if let Some(days) = value.get("validity_days").and_then(Value::as_i64) {
								if days > 0 {
									validity_days.set_value(days as f64);
								}
							}
						}
					} else {
						validity_unlimited.set_active(item.expires_at.is_none());
					}

					validity_days.set_sensitive(!validity_unlimited.is_active());
				}
				Ok(Err(_)) | Err(_) => {
					error_label.set_text(
						"Impossible de charger le secret pour edition. Reessayez dans un instant.",
					);
					error_label.set_visible(true);
				}
			}
		});
	}

	fn install_local_css() {
		let provider = gtk4::CssProvider::new();
		provider.load_from_data(
			r#"
			.add-edit-dialog frame.dialog-type-frame {
				background: rgba(243, 246, 243, 0.72);
				border-radius: 14px;
				border: 1px solid rgba(164, 223, 207, 0.95);
			}

			.add-edit-dialog dropdown.dialog-type-dropdown,
			.add-edit-dialog spinbutton.dialog-validity-spin {
				border-radius: 12px;
				border: 1px solid rgba(164, 223, 207, 0.95);
				background: rgba(255, 255, 255, 0.95);
				padding: 8px 10px;
			}

			.add-edit-dialog textview,
			.add-edit-dialog scrolledwindow.dialog-notes-scroll {
				border-radius: 12px;
				border: 1px solid rgba(164, 223, 207, 0.95);
				background: rgba(255, 255, 255, 0.95);
			}

			.add-edit-dialog textview.dialog-ssh-private-key-text {
				font-family: monospace;
				font-size: 0.92rem;
			}
			"#,
		);

		if let Some(display) = gtk4::gdk::Display::default() {
			gtk4::style_context_add_provider_for_display(
				&display,
				&provider,
				gtk4::STYLE_PROVIDER_PRIORITY_APPLICATION,
			);
		}
	}
}
