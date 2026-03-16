use gtk4::prelude::*;
use gtk4::{Align, Orientation};
use libadwaita as adw;

pub struct AddEditDialog {
	window: gtk4::Window,
}

impl AddEditDialog {
	pub fn new(application: &adw::Application, parent: &adw::ApplicationWindow) -> Self {
		let window = gtk4::Window::builder()
			.application(application)
			.transient_for(parent)
			.title("Nouveau secret")
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

		let title = gtk4::Label::new(Some("Ajouter un secret"));
		title.add_css_class("title-2");
		title.add_css_class("login-hero-title");
		title.set_halign(Align::Start);

		let subtitle = gtk4::Label::new(Some(
			"Selectionnez un type puis renseignez les champs associes.",
		));
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

		let title_entry = Self::build_labeled_entry(
			"Titre *",
			"Nom lisible du secret",
			"dialog-title-entry",
		);
		let category_entry = Self::build_labeled_entry(
			"Categorie",
			"Personnel, Travail, Infrastructure...",
			"dialog-category-entry",
		);
		let tags_entry = Self::build_labeled_entry(
			"Tags (separes par des virgules)",
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

		let password_panel = Self::build_password_panel();
		dynamic_stack.add_titled(&password_panel, Some("password"), "password");

		let api_token_panel = Self::build_api_token_panel();
		dynamic_stack.add_titled(&api_token_panel, Some("api_token"), "api_token");

		let ssh_key_panel = Self::build_ssh_key_panel();
		dynamic_stack.add_titled(&ssh_key_panel, Some("ssh_key"), "ssh_key");

		let secure_doc_panel = Self::build_secure_document_panel();
		dynamic_stack.add_titled(
			&secure_doc_panel,
			Some("secure_document"),
			"secure_document",
		);
		dynamic_stack.set_visible_child_name("password");

		let stack_for_type = dynamic_stack.clone();
		type_dropdown.connect_selected_notify(move |dropdown| {
			let selected = dropdown.selected();
			let view_name = match selected {
				0 => "password",
				1 => "api_token",
				2 => "ssh_key",
				3 => "secure_document",
				_ => "password",
			};
			stack_for_type.set_visible_child_name(view_name);
		});

		let username_entry = Self::build_labeled_entry(
			"Nom d'utilisateur / Login",
			"alice@example.com",
			"dialog-username-entry",
		);
		let url_entry = Self::build_labeled_entry(
			"URL",
			"https://example.com",
			"dialog-url-entry",
		);

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

		let validity_label = gtk4::Label::new(Some("Validite"));
		validity_label.add_css_class("login-field-label");
		validity_label.set_halign(Align::Start);

		let validity_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();

		let validity_unlimited = gtk4::CheckButton::with_label("Validite illimitee");
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

		let button_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.halign(Align::End)
			.build();

		let cancel_button = gtk4::Button::with_label("Annuler");
		cancel_button.add_css_class("secondary-pill");

		let save_button = gtk4::Button::with_label("Enregistrer");
		save_button.add_css_class("primary-pill");

		let dialog_for_cancel = window.clone();
		cancel_button.connect_clicked(move |_| {
			dialog_for_cancel.close();
		});

		let dialog_for_save = window.clone();
		save_button.connect_clicked(move |_| {
			dialog_for_save.close();
		});

		button_row.append(&cancel_button);
		button_row.append(&save_button);

		form_box.append(&title_entry);
		form_box.append(&category_entry);
		form_box.append(&tags_entry);
		form_box.append(&type_label);
		form_box.append(&type_dropdown);
		form_box.append(&dynamic_stack);
		form_box.append(&username_entry);
		form_box.append(&url_entry);
		form_box.append(&notes_label);
		form_box.append(&notes_scrolled);
		form_box.append(&validity_label);
		form_box.append(&validity_box);
		form_box.append(&button_row);

		form_card.set_child(Some(&form_box));
		scrolled.set_child(Some(&form_card));

		root.append(&header_card);
		root.append(&scrolled);
		window.set_child(Some(&root));

		Self::install_local_css();
		Self { window }
	}

	pub fn present(&self) {
		self.window.present();
	}

	fn build_labeled_entry(label_text: &str, placeholder: &str, css_class: &str) -> gtk4::Box {
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
		box_widget
	}

	fn build_password_panel() -> gtk4::Frame {
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

		let password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text("Saisissez un mot de passe")
			.show_peek_icon(true)
			.build();
		password_entry.add_css_class("login-entry");

		let strength_hint = gtk4::Label::new(Some("Robustesse : dynamique dans une etape suivante"));
		strength_hint.add_css_class("login-support-copy");
		strength_hint.set_halign(Align::Start);

		box_widget.append(&password_label);
		box_widget.append(&password_entry);
		box_widget.append(&strength_hint);
		frame.set_child(Some(&box_widget));
		frame
	}

	fn build_api_token_panel() -> gtk4::Frame {
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
			.placeholder_text("pk_live_... ou token equivalant")
			.show_peek_icon(true)
			.build();
		token_entry.add_css_class("login-entry");

		let provider = Self::build_labeled_entry(
			"Fournisseur",
			"GitHub, Stripe, OpenAI...",
			"dialog-api-provider-entry",
		);

		box_widget.append(&token_label);
		box_widget.append(&token_entry);
		box_widget.append(&provider);
		frame.set_child(Some(&box_widget));
		frame
	}

	fn build_ssh_key_panel() -> gtk4::Frame {
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

		let private_key_label = gtk4::Label::new(Some("Cle privee SSH *"));
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

		let public_key = Self::build_labeled_entry(
			"Cle publique",
			"ssh-ed25519 AAAA...",
			"dialog-ssh-public-entry",
		);
		let passphrase = Self::build_labeled_entry(
			"Passphrase (optionnel)",
			"Passphrase de protection de cle",
			"dialog-ssh-passphrase-entry",
		);

		box_widget.append(&private_key_label);
		box_widget.append(&private_key_scrolled);
		box_widget.append(&public_key);
		box_widget.append(&passphrase);
		frame.set_child(Some(&box_widget));
		frame
	}

	fn build_secure_document_panel() -> gtk4::Frame {
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

		let file_path = Self::build_labeled_entry(
			"Chemin du document *",
			"/home/user/Documents/contrat.pdf",
			"dialog-document-path-entry",
		);
		let mime_type = Self::build_labeled_entry(
			"Type MIME",
			"application/pdf",
			"dialog-document-mime-entry",
		);

		let import_hint = gtk4::Label::new(Some(
			"Import de fichier et chiffrement reel branches dans une etape suivante.",
		));
		import_hint.add_css_class("login-support-copy");
		import_hint.set_wrap(true);
		import_hint.set_halign(Align::Start);

		box_widget.append(&file_path);
		box_widget.append(&mime_type);
		box_widget.append(&import_hint);
		frame.set_child(Some(&box_widget));
		frame
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
