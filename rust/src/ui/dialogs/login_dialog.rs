use std::cell::Cell;
use std::rc::Rc;
use std::sync::Arc;

use gtk4::glib;
use gtk4::prelude::*;
use gtk4::{Align, InputPurpose, Justification, Orientation};
use libadwaita as adw;
use secrecy::SecretBox;
use tokio::runtime::Handle;

use crate::services::auth_service::AuthService;

pub struct LoginDialog {
	window: gtk4::Window,
}

impl LoginDialog {
	pub fn new<TAuth>(
		application: &adw::Application,
		parent: &adw::ApplicationWindow,
		runtime_handle: Handle,
		auth_service: Arc<TAuth>,
		two_factor_enabled: bool,
		on_authenticated: impl Fn() + 'static,
		on_cancelled: impl Fn() + 'static,
	) -> Self
	where
		TAuth: AuthService + Send + Sync + 'static,
	{
		let on_authenticated: Rc<dyn Fn()> = Rc::new(on_authenticated);
		let on_cancelled: Rc<dyn Fn()> = Rc::new(on_cancelled);
		let authenticated = Rc::new(Cell::new(false));
		let window = gtk4::Window::builder()
			.application(application)
			.transient_for(parent)
			.title("Connexion")
			.modal(true)
			.resizable(false)
			.default_width(460)
			.default_height(540)
			.build();

		let shell = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.valign(Align::Center)
			.margin_top(24)
			.margin_bottom(24)
			.margin_start(24)
			.margin_end(24)
			.build();
		shell.add_css_class("login-shell");

		let root = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(20)
			.halign(Align::Fill)
			.build();
		root.add_css_class("login-panel");

		let hero_frame = gtk4::Frame::new(None);
		hero_frame.add_css_class("login-hero");

		let hero_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(16)
			.margin_top(22)
			.margin_bottom(22)
			.margin_start(22)
			.margin_end(22)
			.build();

		let hero_icon = gtk4::Image::from_resource(
			"/com/heelonvault/rust/icons/hicolor/128x128/apps/heelonvault.png",
		);
		hero_icon.set_pixel_size(56);
		hero_icon.set_halign(Align::Center);
		hero_icon.set_valign(Align::Start);
		hero_icon.add_css_class("login-hero-icon");

		let hero_text_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(6)
			.hexpand(true)
			.build();

		let eyebrow_label = gtk4::Label::new(Some("HeelonVault"));
		eyebrow_label.add_css_class("login-badge");
		eyebrow_label.set_halign(Align::Start);

		let title_label = gtk4::Label::new(Some("Connexion securisee"));
		title_label.add_css_class("title-1");
		title_label.add_css_class("login-hero-title");
		title_label.set_halign(Align::Start);

		let subtitle_label = gtk4::Label::new(Some(
			"Saisissez vos identifiants pour ouvrir votre coffre local chiffre.",
		));
		subtitle_label.add_css_class("login-hero-copy");
		subtitle_label.set_wrap(true);
		subtitle_label.set_halign(Align::Start);

		let meta_label = gtk4::Label::new(Some(&format!(
			"Version {} • Preview Rust",
			env!("CARGO_PKG_VERSION")
		)));
		meta_label.add_css_class("login-hero-meta");
		meta_label.set_halign(Align::Start);

		hero_text_box.append(&eyebrow_label);
		hero_text_box.append(&title_label);
		hero_text_box.append(&subtitle_label);
		hero_text_box.append(&meta_label);
		hero_box.append(&hero_icon);
		hero_box.append(&hero_text_box);
		hero_frame.set_child(Some(&hero_box));

		let form_card = gtk4::Frame::new(None);
		form_card.add_css_class("login-card");

		let form_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(14)
			.margin_top(20)
			.margin_bottom(20)
			.margin_start(20)
			.margin_end(20)
			.build();

		let security_hint = gtk4::Label::new(Some(
			"Protection locale • verification hors thread UI • aucune fuite de detail technique",
		));
		security_hint.add_css_class("login-support-copy");
		security_hint.set_wrap(true);
		security_hint.set_halign(Align::Start);

		let username_label = gtk4::Label::new(Some("Nom d'utilisateur"));
		username_label.add_css_class("login-field-label");
		username_label.set_halign(Align::Start);

		let username_entry = gtk4::Entry::builder()
			.placeholder_text("alice")
			.hexpand(true)
			.build();
		username_entry.add_css_class("login-entry");
		username_entry.set_activates_default(true);

		let password_label = gtk4::Label::new(Some("Mot de passe"));
		password_label.add_css_class("login-field-label");
		password_label.set_halign(Align::Start);

		let password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text("Saisissez votre mot de passe")
			.hexpand(true)
			.show_peek_icon(true)
			.build();
		password_entry.add_css_class("login-entry");
		password_entry.set_activates_default(true);

		let strength_label = gtk4::Label::new(None);
		strength_label.add_css_class("login-strength");
		strength_label.set_halign(Align::Start);
		strength_label.set_visible(false);

		let totp_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.visible(two_factor_enabled)
			.build();
		totp_box.add_css_class("login-totp-block");

		let totp_label = gtk4::Label::new(Some("Code de verification"));
		totp_label.add_css_class("login-field-label");
		totp_label.set_halign(Align::Start);

		let totp_entry = gtk4::Entry::builder()
			.placeholder_text("000000")
			.max_length(6)
			.input_purpose(InputPurpose::Digits)
			.build();
		totp_entry.add_css_class("login-entry");
		totp_entry.add_css_class("login-totp-entry");
		totp_entry.set_halign(Align::Center);
		totp_entry.set_width_chars(8);
		gtk4::prelude::EntryExt::set_alignment(&totp_entry, 0.5);

		let totp_hint = gtk4::Label::new(Some(
			"Entrez le code a 6 chiffres de votre application d'authentification si la 2FA est activee.",
		));
		totp_hint.add_css_class("login-support-copy");
		totp_hint.set_wrap(true);
		totp_hint.set_justify(Justification::Center);
		totp_hint.set_halign(Align::Fill);

		totp_box.append(&totp_label);
		totp_box.append(&totp_entry);
		totp_box.append(&totp_hint);

		let error_label = gtk4::Label::new(None);
		error_label.add_css_class("login-error");
		error_label.set_wrap(true);
		error_label.set_halign(Align::Start);
		error_label.set_visible(false);

		let button_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.build();

		let back_button = gtk4::Button::with_label("Quitter");
		back_button.add_css_class("secondary-pill");

		let login_button = gtk4::Button::builder()
			.hexpand(true)
			.halign(Align::Fill)
			.build();
		login_button.add_css_class("primary-pill");

		let button_content = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.halign(Align::Center)
			.build();

		let spinner = gtk4::Spinner::new();
		spinner.set_visible(false);

		let button_label = gtk4::Label::new(Some("Connexion"));
		button_label.add_css_class("heading");

		button_content.append(&spinner);
		button_content.append(&button_label);
		login_button.set_child(Some(&button_content));
		button_box.append(&back_button);
		button_box.append(&login_button);

		form_box.append(&security_hint);
		form_box.append(&username_label);
		form_box.append(&username_entry);
		form_box.append(&password_label);
		form_box.append(&password_entry);
		form_box.append(&strength_label);
		form_box.append(&totp_box);
		form_box.append(&error_label);
		form_box.append(&button_box);
		form_card.set_child(Some(&form_box));

		root.append(&hero_frame);
		root.append(&form_card);
		shell.append(&root);
		window.set_child(Some(&shell));
		window.set_default_widget(Some(&login_button));

		let authenticated_for_close = Rc::clone(&authenticated);
		let on_cancelled_for_close = Rc::clone(&on_cancelled);
		window.connect_close_request(move |_| {
			if !authenticated_for_close.get() {
				on_cancelled_for_close();
			}
			glib::Propagation::Proceed
		});

		Self::connect_feedback_reset(&username_entry, &error_label);
		Self::connect_feedback_reset(&password_entry, &error_label);
		Self::connect_feedback_reset(&totp_entry, &error_label);

		let title_for_username = title_label.clone();
		username_entry.connect_changed(move |entry| {
			Self::update_greeting(&title_for_username, entry.text().trim());
		});

		let strength_for_password = strength_label.clone();
		password_entry.connect_changed(move |entry| {
			Self::update_strength_feedback(entry.text().as_str(), &strength_for_password);
		});

		let dialog_for_back = window.clone();
		back_button.connect_clicked(move |_| {
			dialog_for_back.close();
		});

		let button_for_username = login_button.clone();
		username_entry.connect_activate(move |_| {
			button_for_username.emit_clicked();
		});

		let button_for_password = login_button.clone();
		password_entry.connect_activate(move |_| {
			button_for_password.emit_clicked();
		});

		let button_for_totp = login_button.clone();
		totp_entry.connect_activate(move |_| {
			button_for_totp.emit_clicked();
		});

		let dialog_for_submit = window.clone();
		let username_for_submit = username_entry.clone();
		let password_for_submit = password_entry.clone();
		let strength_for_submit = strength_label.clone();
		let totp_for_submit = totp_entry.clone();
		let error_for_submit = error_label.clone();
		let button_for_submit = login_button.clone();
		let spinner_for_submit = spinner.clone();
		let authenticated_for_submit = Rc::clone(&authenticated);
		let on_authenticated_for_submit = Rc::clone(&on_authenticated);
		let auth_for_submit = Arc::clone(&auth_service);
		let runtime_for_submit = runtime_handle.clone();

		login_button.connect_clicked(move |_| {
			Self::clear_feedback(&error_for_submit);

			let username = username_for_submit.text().trim().to_string();
			let password = password_for_submit.text().to_string();
			let totp = totp_for_submit.text().trim().to_string();

			if username.is_empty() {
				Self::show_feedback(
					&error_for_submit,
					"Saisissez votre nom d'utilisateur pour continuer.",
				);
				return;
			}

			if password.is_empty() {
				Self::show_feedback(
					&error_for_submit,
					"Saisissez votre mot de passe avant de vous connecter.",
				);
				return;
			}

			if two_factor_enabled && !Self::is_valid_totp(&totp) {
				Self::show_feedback(
					&error_for_submit,
					"Entrez un code a 6 chiffres pour finaliser la connexion.",
				);
				return;
			}

			Self::set_pending_state(&button_for_submit, &spinner_for_submit, true);

			let (result_sender, result_receiver) = tokio::sync::oneshot::channel();
			let auth_for_task = Arc::clone(&auth_for_submit);
			let username_for_task = username.clone();
			let password_for_task = password.into_bytes();
			let runtime_for_task = runtime_for_submit.clone();

			std::thread::spawn(move || {
				let secret_password = SecretBox::new(Box::new(password_for_task));
				let result = runtime_for_task.block_on(async move {
					auth_for_task
						.verify_password(&username_for_task, secret_password)
						.await
				});
				let _ = result_sender.send(result);
			});

			let dialog_for_result = dialog_for_submit.clone();
			let password_for_result = password_for_submit.clone();
			let strength_for_result = strength_for_submit.clone();
			let error_for_result = error_for_submit.clone();
			let button_for_result = button_for_submit.clone();
			let spinner_for_result = spinner_for_submit.clone();
			let authenticated_for_result = Rc::clone(&authenticated_for_submit);
			let on_authenticated_for_result = Rc::clone(&on_authenticated_for_submit);

			glib::MainContext::default().spawn_local(async move {
				let verification_result = result_receiver.await;
				Self::set_pending_state(&button_for_result, &spinner_for_result, false);

				match verification_result {
					Ok(Ok(true)) if two_factor_enabled => Self::show_feedback(
						&error_for_result,
						"La verification 2FA backend n'est pas encore migree dans cette etape UI.",
					),
					Ok(Ok(true)) => {
						authenticated_for_result.set(true);
						on_authenticated_for_result();
						dialog_for_result.close();
					}
					Ok(Ok(false)) => {
						password_for_result.set_text("");
						Self::update_strength_feedback("", &strength_for_result);
						password_for_result.grab_focus();
						Self::show_feedback(
							&error_for_result,
							"Identifiants invalides. Verifiez vos informations et recommencez.",
						);
					}
					Ok(Err(_)) => Self::show_feedback(
						&error_for_result,
						"Connexion indisponible pour le moment. Reessayez dans un instant.",
					),
					Err(_) => Self::show_feedback(
						&error_for_result,
						"La tentative de connexion a ete interrompue. Reessayez.",
					),
				}
			});
		});

		username_entry.grab_focus();

		Self { window }
	}

	pub fn present(&self) {
		self.window.present();
	}

	fn connect_feedback_reset<TWidget>(widget: &TWidget, error_label: &gtk4::Label)
	where
		TWidget: IsA<gtk4::Editable> + Clone + 'static,
	{
		let error_for_reset = error_label.clone();
		widget.connect_changed(move |_| {
			Self::clear_feedback(&error_for_reset);
		});
	}

	fn clear_feedback(error_label: &gtk4::Label) {
		error_label.set_text("");
		error_label.set_visible(false);
	}

	fn show_feedback(error_label: &gtk4::Label, message: &str) {
		error_label.set_text(message);
		error_label.set_visible(true);
	}

	fn update_greeting(title_label: &gtk4::Label, username: &str) {
		if username.is_empty() {
			title_label.set_text("Connexion securisee");
			return;
		}

		title_label.set_text(&format!("Bonjour, {username}"));
	}

	fn update_strength_feedback(password: &str, strength_label: &gtk4::Label) {
		strength_label.remove_css_class("success");
		strength_label.remove_css_class("warning");
		strength_label.remove_css_class("error");

		if password.is_empty() {
			strength_label.set_text("");
			strength_label.set_visible(false);
			return;
		}

		let mut score = 0_u8;
		let length = password.chars().count();
		if length >= 12 {
			score += 2;
		} else if length >= 8 {
			score += 1;
		}

		let has_lower = password.chars().any(|character| character.is_ascii_lowercase());
		let has_upper = password.chars().any(|character| character.is_ascii_uppercase());
		let has_digit = password.chars().any(|character| character.is_ascii_digit());
		let has_special = password.chars().any(|character| !character.is_ascii_alphanumeric());

		let complexity = [has_lower, has_upper, has_digit, has_special]
			.into_iter()
			.filter(|value| *value)
			.count();

		if complexity >= 3 {
			score += 2;
		} else if complexity >= 2 {
			score += 1;
		}

		let (label, css_class) = if score >= 4 {
			("Robustesse : tres forte", "success")
		} else if score >= 3 {
			("Robustesse : forte", "success")
		} else if score >= 2 {
			("Robustesse : moyenne", "warning")
		} else {
			("Robustesse : faible", "error")
		};

		strength_label.remove_css_class("dim-label");
		strength_label.add_css_class(css_class);
		strength_label.set_text(label);
		strength_label.set_visible(true);
	}

	fn set_pending_state(button: &gtk4::Button, spinner: &gtk4::Spinner, pending: bool) {
		button.set_sensitive(!pending);
		spinner.set_visible(pending);
		spinner.set_spinning(pending);
	}

	fn is_valid_totp(totp: &str) -> bool {
		totp.len() == 6 && totp.chars().all(|character| character.is_ascii_digit())
	}
}
