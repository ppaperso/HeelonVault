use std::cell::{Cell, RefCell};
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::Arc;
use std::time::Duration;

use gtk4::glib;
use gtk4::prelude::*;
use gtk4::{Align, InputPurpose, Justification, Orientation};
use libadwaita as adw;
use secrecy::SecretBox;
use tokio::runtime::Handle;
use tracing::warn;

use crate::errors::AppError;
use crate::services::auth_policy_service::AuthPolicyService;
use crate::services::auth_service::AuthService;
use crate::ui::widgets::password_strength_bar::PasswordStrengthBar;

pub struct LoginDialog {
	window: gtk4::Window,
}

enum LoginAttemptOutcome {
	Success,
	InvalidCredentials { remaining_lock_secs: i64 },
	Locked { remaining_lock_secs: i64 },
}

impl LoginDialog {
	pub fn new<TAuth, TPolicy>(
		application: &adw::Application,
		parent: &adw::ApplicationWindow,
		runtime_handle: Handle,
		auth_service: Arc<TAuth>,
		auth_policy_service: Arc<TPolicy>,
		two_factor_enabled: bool,
		on_restore_requested: impl Fn(PathBuf, String, String) -> Result<(), AppError>
			+ Send
			+ Sync
			+ 'static,
		on_restore_completed: impl Fn() + 'static,
		on_authenticated: impl Fn() + 'static,
		on_cancelled: impl Fn() + 'static,
	) -> Self
	where
		TAuth: AuthService + Send + Sync + 'static,
		TPolicy: AuthPolicyService + Send + Sync + 'static,
	{
		const FAILURE_COOLDOWN_MS: u64 = 1200;

		let on_restore_requested: Arc<dyn Fn(PathBuf, String, String) -> Result<(), AppError> + Send + Sync> =
			Arc::new(on_restore_requested);
		let on_restore_completed: Rc<dyn Fn()> = Rc::new(on_restore_completed);
		let on_authenticated: Rc<dyn Fn()> = Rc::new(on_authenticated);
		let on_cancelled: Rc<dyn Fn()> = Rc::new(on_cancelled);
		let authenticated = Rc::new(Cell::new(false));
		let lock_active = Rc::new(Cell::new(false));
		let lock_timer: Rc<RefCell<Option<glib::SourceId>>> = Rc::new(RefCell::new(None));
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

		let restore_button = gtk4::Button::with_label("Recuperer ma base (.hvb)");
		restore_button.add_css_class("flat");
		restore_button.set_halign(Align::End);

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
		form_box.append(&restore_button);
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

		Self::connect_feedback_reset(&username_entry, &error_label, Rc::clone(&lock_active));
		Self::connect_feedback_reset(&password_entry, &error_label, Rc::clone(&lock_active));
		Self::connect_feedback_reset(&totp_entry, &error_label, Rc::clone(&lock_active));

		let title_for_username = title_label.clone();
		let button_for_username_change = login_button.clone();
		let spinner_for_username_change = spinner.clone();
		let error_for_username_change = error_label.clone();
		let lock_active_for_username_change = Rc::clone(&lock_active);
		let lock_timer_for_username_change = Rc::clone(&lock_timer);
		let username_for_lock_probe = username_entry.clone();
		let runtime_for_lock_probe = runtime_handle.clone();
		let auth_policy_for_lock_probe = Arc::clone(&auth_policy_service);
		username_entry.connect_changed(move |entry| {
			let typed_username = entry.text().trim().to_string();
			if lock_active_for_username_change.get() {
				lock_active_for_username_change.set(false);
				if let Some(source_id) = lock_timer_for_username_change.borrow_mut().take() {
					source_id.remove();
				}
				Self::set_pending_state(&button_for_username_change, &spinner_for_username_change, false);
				Self::clear_feedback(&error_for_username_change);
			}

			if !typed_username.is_empty() {
				let (sender, receiver) = tokio::sync::oneshot::channel();
				let runtime_for_task = runtime_for_lock_probe.clone();
				let policy_for_task = Arc::clone(&auth_policy_for_lock_probe);
				let username_for_task = typed_username.clone();
				let username_for_send = username_for_task.clone();
				std::thread::spawn(move || {
					let result = runtime_for_task.block_on(async move {
						policy_for_task.get_state(&username_for_task).await
					});
					let _ = sender.send((username_for_send, result));
				});

				let button_for_result = button_for_username_change.clone();
				let spinner_for_result = spinner_for_username_change.clone();
				let error_for_result = error_for_username_change.clone();
				let lock_active_for_result = Rc::clone(&lock_active_for_username_change);
				let lock_timer_for_result = Rc::clone(&lock_timer_for_username_change);
				let username_entry_for_result = username_for_lock_probe.clone();
				glib::MainContext::default().spawn_local(async move {
					if let Ok((checked_username, Ok(state))) = receiver.await {
						if username_entry_for_result.text().trim() == checked_username && state.is_locked() {
							Self::start_lock_countdown(
								&button_for_result,
								&spinner_for_result,
								&error_for_result,
								state.remaining_lock_secs,
								lock_active_for_result,
								lock_timer_for_result,
							);
						}
					}
				});
			}

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

		let restore_parent = window.clone();
		let restore_request_handler = Arc::clone(&on_restore_requested);
		let restore_complete_handler = Rc::clone(&on_restore_completed);
		restore_button.connect_clicked(move |_| {
			Self::present_restore_dialog(
				&restore_parent,
				Arc::clone(&restore_request_handler),
				Rc::clone(&restore_complete_handler),
			);
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
		let auth_policy_for_submit = Arc::clone(&auth_policy_service);
		let runtime_for_submit = runtime_handle.clone();
		let lock_active_for_submit = Rc::clone(&lock_active);
		let lock_timer_for_submit = Rc::clone(&lock_timer);

		login_button.connect_clicked(move |_| {
			if lock_active_for_submit.get() {
				return;
			}

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
			let auth_policy_for_task = Arc::clone(&auth_policy_for_submit);
			let username_for_task = username.clone();
			let password_for_task = password.into_bytes();
			let runtime_for_task = runtime_for_submit.clone();

			std::thread::spawn(move || {
				let secret_password = SecretBox::new(Box::new(password_for_task));
				let result: Result<LoginAttemptOutcome, AppError> = runtime_for_task.block_on(async move {
					let lock_state = auth_policy_for_task.get_state(&username_for_task).await?;
					if lock_state.is_locked() {
						warn!(
							username = %username_for_task,
							remaining_lock_secs = lock_state.remaining_lock_secs,
							failed_attempts = lock_state.failed_attempts,
							"login attempt rejected: account currently locked"
						);
						return Ok(LoginAttemptOutcome::Locked {
							remaining_lock_secs: lock_state.remaining_lock_secs,
						});
					}

					let verified = auth_for_task
						.verify_password(&username_for_task, secret_password)
						.await?;

					if verified {
						auth_policy_for_task
							.reset_failed_attempts(&username_for_task)
							.await?;
						Ok(LoginAttemptOutcome::Success)
					} else {
						let state = auth_policy_for_task
							.record_failed_attempt(&username_for_task)
							.await?;
						Ok(LoginAttemptOutcome::InvalidCredentials {
							remaining_lock_secs: state.remaining_lock_secs,
						})
					}
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
			let lock_active_for_result = Rc::clone(&lock_active_for_submit);
			let lock_timer_for_result = Rc::clone(&lock_timer_for_submit);

			glib::MainContext::default().spawn_local(async move {
				let verification_result = result_receiver.await;

				match verification_result {
					Ok(Ok(LoginAttemptOutcome::Success)) if two_factor_enabled => {
						Self::set_pending_state(&button_for_result, &spinner_for_result, false);
						Self::show_feedback(
						&error_for_result,
						"La verification 2FA backend n'est pas encore migree dans cette etape UI.",
						);
					}
					Ok(Ok(LoginAttemptOutcome::Success)) => {
						Self::set_pending_state(&button_for_result, &spinner_for_result, false);
						authenticated_for_result.set(true);
						on_authenticated_for_result();
						dialog_for_result.close();
					}
					Ok(Ok(LoginAttemptOutcome::Locked { remaining_lock_secs })) => {
						Self::set_pending_state(&button_for_result, &spinner_for_result, false);
						Self::start_lock_countdown(
							&button_for_result,
							&spinner_for_result,
							&error_for_result,
							remaining_lock_secs,
							Rc::clone(&lock_active_for_result),
							Rc::clone(&lock_timer_for_result),
						);
					}
					Ok(Ok(LoginAttemptOutcome::InvalidCredentials { remaining_lock_secs })) => {
						password_for_result.set_text("");
						Self::update_strength_feedback("", &strength_for_result);
						password_for_result.grab_focus();

						if remaining_lock_secs > 0 {
							Self::set_pending_state(&button_for_result, &spinner_for_result, false);
							Self::start_lock_countdown(
								&button_for_result,
								&spinner_for_result,
								&error_for_result,
								remaining_lock_secs,
								Rc::clone(&lock_active_for_result),
								Rc::clone(&lock_timer_for_result),
							);
						} else {
							Self::show_feedback(
								&error_for_result,
								"Identifiants invalides. Merci de patienter avant une nouvelle tentative.",
							);
							let button_after_delay = button_for_result.clone();
							let spinner_after_delay = spinner_for_result.clone();
							glib::timeout_add_local_once(
								Duration::from_millis(FAILURE_COOLDOWN_MS),
								move || {
									Self::set_pending_state(
										&button_after_delay,
										&spinner_after_delay,
										false,
									);
								},
							);
						}
					}
					Ok(Err(_)) => {
						Self::show_feedback(
							&error_for_result,
							"Connexion indisponible pour le moment. Merci de patienter.",
						);
						let button_after_delay = button_for_result.clone();
						let spinner_after_delay = spinner_for_result.clone();
						glib::timeout_add_local_once(
							Duration::from_millis(FAILURE_COOLDOWN_MS),
							move || {
								Self::set_pending_state(
									&button_after_delay,
									&spinner_after_delay,
									false,
								);
							},
						);
					}
					Err(_) => {
						Self::show_feedback(
							&error_for_result,
							"La tentative de connexion a ete interrompue. Merci de patienter.",
						);
						let button_after_delay = button_for_result.clone();
						let spinner_after_delay = spinner_for_result.clone();
						glib::timeout_add_local_once(
							Duration::from_millis(FAILURE_COOLDOWN_MS),
							move || {
								Self::set_pending_state(
									&button_after_delay,
									&spinner_after_delay,
									false,
								);
							},
						);
					}
				}
			});
		});

		username_entry.grab_focus();

		Self { window }
	}

	pub fn present(&self) {
		self.window.present();
	}

	fn connect_feedback_reset<TWidget>(
		widget: &TWidget,
		error_label: &gtk4::Label,
		lock_active: Rc<Cell<bool>>,
	)
	where
		TWidget: IsA<gtk4::Editable> + Clone + 'static,
	{
		let error_for_reset = error_label.clone();
		widget.connect_changed(move |_| {
			if lock_active.get() {
				return;
			}
			Self::clear_feedback(&error_for_reset);
		});
	}

	fn start_lock_countdown(
		button: &gtk4::Button,
		spinner: &gtk4::Spinner,
		error_label: &gtk4::Label,
		remaining_secs: i64,
		lock_active: Rc<Cell<bool>>,
		lock_timer: Rc<RefCell<Option<glib::SourceId>>>,
	) {
		if let Some(source_id) = lock_timer.borrow_mut().take() {
			source_id.remove();
		}

		let mut current_secs = remaining_secs.max(0);
		if current_secs == 0 {
			lock_active.set(false);
			Self::set_pending_state(button, spinner, false);
			Self::show_feedback(error_label, "Vous pouvez reessayer maintenant.");
			return;
		}

		lock_active.set(true);
		spinner.set_visible(false);
		spinner.set_spinning(false);
		button.set_sensitive(false);

		Self::show_feedback(
			error_label,
			&format!(
				"Compte temporairement verrouille. Nouvelle tentative dans {}s.",
				current_secs
			),
		);

		let button_for_tick = button.clone();
		let spinner_for_tick = spinner.clone();
		let error_for_tick = error_label.clone();
		let lock_active_for_tick = Rc::clone(&lock_active);
		let lock_timer_for_tick = Rc::clone(&lock_timer);
		let source_id = glib::timeout_add_seconds_local(1, move || {
			current_secs = current_secs.saturating_sub(1);
			if current_secs == 0 {
				lock_active_for_tick.set(false);
				Self::set_pending_state(&button_for_tick, &spinner_for_tick, false);
				Self::show_feedback(&error_for_tick, "Vous pouvez reessayer maintenant.");
				let _ = lock_timer_for_tick.borrow_mut().take();
				glib::ControlFlow::Break
			} else {
				Self::show_feedback(
					&error_for_tick,
					&format!(
						"Compte temporairement verrouille. Nouvelle tentative dans {}s.",
						current_secs
					),
				);
				glib::ControlFlow::Continue
			}
		});

		*lock_timer.borrow_mut() = Some(source_id);
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

	fn present_restore_dialog(
		parent: &gtk4::Window,
		on_restore_requested: Arc<dyn Fn(PathBuf, String, String) -> Result<(), AppError> + Send + Sync>,
		on_restore_completed: Rc<dyn Fn()>,
	) {
		let dialog = gtk4::Window::builder()
			.transient_for(parent)
			.title("Recuperation de la base")
			.modal(true)
			.resizable(false)
			.default_width(520)
			.default_height(420)
			.build();

		let content = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(14)
			.margin_top(20)
			.margin_bottom(20)
			.margin_start(20)
			.margin_end(20)
			.build();

		let title = gtk4::Label::new(Some(
			"Restaurez un export chiffre .hvb avec votre phrase de recuperation.",
		));
		title.set_wrap(true);
		title.set_halign(Align::Start);

		let file_label = gtk4::Label::new(Some("Fichier .hvb"));
		file_label.add_css_class("login-field-label");
		file_label.set_halign(Align::Start);

		let file_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();

		let file_entry = gtk4::Entry::builder()
			.placeholder_text("/chemin/vers/sauvegarde.hvb")
			.hexpand(true)
			.build();
		file_entry.add_css_class("login-entry");

		let browse_button = gtk4::Button::with_label("Parcourir");
		browse_button.add_css_class("secondary-pill");

		file_row.append(&file_entry);
		file_row.append(&browse_button);

		let phrase_label = gtk4::Label::new(Some("Phrase de recuperation (24 mots)"));
		phrase_label.add_css_class("login-field-label");
		phrase_label.set_halign(Align::Start);

		let phrase_entry = gtk4::Entry::builder()
			.placeholder_text("word1 word2 ... word24")
			.hexpand(true)
			.build();
		phrase_entry.add_css_class("login-entry");

		let password_label = gtk4::Label::new(Some("Nouveau mot de passe principal"));
		password_label.add_css_class("login-field-label");
		password_label.set_halign(Align::Start);

		let new_password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text("Choisissez un nouveau mot de passe")
			.hexpand(true)
			.show_peek_icon(true)
			.build();
		new_password_entry.add_css_class("login-entry");

		let strength_bar = PasswordStrengthBar::new();
		strength_bar.connect_to_password_entry(&new_password_entry);

		let confirm_label = gtk4::Label::new(Some("Confirmer le mot de passe"));
		confirm_label.add_css_class("login-field-label");
		confirm_label.set_halign(Align::Start);

		let confirm_password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text("Retapez le mot de passe")
			.hexpand(true)
			.show_peek_icon(true)
			.build();
		confirm_password_entry.add_css_class("login-entry");

		let error_label = gtk4::Label::new(None);
		error_label.add_css_class("login-error");
		error_label.set_wrap(true);
		error_label.set_halign(Align::Start);
		error_label.set_visible(false);

		let button_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.build();

		let cancel_button = gtk4::Button::with_label("Annuler");
		cancel_button.add_css_class("secondary-pill");

		let restore_button = gtk4::Button::builder()
			.hexpand(true)
			.halign(Align::Fill)
			.sensitive(false)
			.build();
		restore_button.add_css_class("primary-pill");

		let restore_content = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.halign(Align::Center)
			.build();
		let restore_spinner = gtk4::Spinner::new();
		restore_spinner.set_visible(false);
		let restore_label = gtk4::Label::new(Some("Restaurer et redemarrer"));
		restore_content.append(&restore_spinner);
		restore_content.append(&restore_label);
		restore_button.set_child(Some(&restore_content));

		button_box.append(&cancel_button);
		button_box.append(&restore_button);

		content.append(&title);
		content.append(&file_label);
		content.append(&file_row);
		content.append(&phrase_label);
		content.append(&phrase_entry);
		content.append(&password_label);
		content.append(&new_password_entry);
		content.append(strength_bar.root());
		content.append(&confirm_label);
		content.append(&confirm_password_entry);
		content.append(&error_label);
		content.append(&button_box);
		dialog.set_child(Some(&content));

		let busy = Rc::new(Cell::new(false));
		let update_action_state: Rc<dyn Fn()> = {
			let busy = Rc::clone(&busy);
			let restore_button = restore_button.clone();
			let file_entry = file_entry.clone();
			let phrase_entry = phrase_entry.clone();
			let new_password_entry = new_password_entry.clone();
			let confirm_password_entry = confirm_password_entry.clone();
			Rc::new(move || {
				let has_file = !file_entry.text().trim().is_empty();
				let has_phrase = !phrase_entry.text().trim().is_empty();
				let has_password = !new_password_entry.text().is_empty();
				let matches_confirmation = new_password_entry.text() == confirm_password_entry.text();
				restore_button.set_sensitive(
					!busy.get() && has_file && has_phrase && has_password && matches_confirmation,
				);
			})
		};

		for editable in [
			file_entry.clone().upcast::<gtk4::Editable>(),
			phrase_entry.clone().upcast::<gtk4::Editable>(),
			new_password_entry.clone().upcast::<gtk4::Editable>(),
			confirm_password_entry.clone().upcast::<gtk4::Editable>(),
		] {
			let update_action_state = Rc::clone(&update_action_state);
			editable.connect_changed(move |_| {
				update_action_state();
			});
		}

		let parent_for_chooser = dialog.clone();
		let file_entry_for_chooser = file_entry.clone();
		let update_action_for_chooser = Rc::clone(&update_action_state);
		browse_button.connect_clicked(move |_| {
			let chooser = gtk4::FileChooserNative::builder()
				.title("Choisir un export .hvb")
				.transient_for(&parent_for_chooser)
				.action(gtk4::FileChooserAction::Open)
				.accept_label("Selectionner")
				.cancel_label("Annuler")
				.build();

			let filter = gtk4::FileFilter::new();
			filter.add_pattern("*.hvb");
			filter.set_name(Some("Sauvegardes HeelonVault (*.hvb)"));
			chooser.set_filter(&filter);

			let file_entry_for_response = file_entry_for_chooser.clone();
			let update_action_for_response = Rc::clone(&update_action_for_chooser);
			chooser.connect_response(move |dialog, response| {
				if response == gtk4::ResponseType::Accept {
					if let Some(file) = dialog.file() {
						if let Some(path) = file.path() {
							file_entry_for_response.set_text(&path.display().to_string());
							update_action_for_response();
						}
					}
				}
				dialog.destroy();
			});

			chooser.show();
		});

		let dialog_for_cancel = dialog.clone();
		cancel_button.connect_clicked(move |_| {
			dialog_for_cancel.close();
		});

		let dialog_for_submit = dialog.clone();
		let error_for_submit = error_label.clone();
		let file_for_submit = file_entry.clone();
		let phrase_for_submit = phrase_entry.clone();
		let password_for_submit = new_password_entry.clone();
		let confirm_for_submit = confirm_password_entry.clone();
		let restore_button_for_submit = restore_button.clone();
		let restore_spinner_for_submit = restore_spinner.clone();
		let busy_for_submit = Rc::clone(&busy);
		restore_button.connect_clicked(move |_| {
			let file_path = file_for_submit.text().trim().to_string();
			let recovery_phrase = phrase_for_submit.text().trim().to_string();
			let new_password = password_for_submit.text().to_string();
			let confirmation = confirm_for_submit.text().to_string();

			Self::clear_feedback(&error_for_submit);

			if file_path.is_empty() {
				Self::show_feedback(&error_for_submit, "Selectionnez un export .hvb a restaurer.");
				return;
			}

			if !PathBuf::from(&file_path).exists() {
				Self::show_feedback(&error_for_submit, "Le fichier .hvb selectionne est introuvable.");
				return;
			}

			if recovery_phrase.split_whitespace().count() != 24 {
				Self::show_feedback(
					&error_for_submit,
					"La phrase de recuperation doit contenir exactement 24 mots.",
				);
				return;
			}

			if new_password != confirmation {
				Self::show_feedback(
					&error_for_submit,
					"La confirmation du nouveau mot de passe ne correspond pas.",
				);
				return;
			}

			if strength_bar.last_score() < 3 {
				Self::show_feedback(
					&error_for_submit,
					"Choisissez un mot de passe principal au moins solide avant de restaurer.",
				);
				return;
			}

			busy_for_submit.set(true);
			Self::set_pending_state(
				&restore_button_for_submit,
				&restore_spinner_for_submit,
				true,
			);

			let (sender, receiver) = tokio::sync::oneshot::channel();
			let restore_handler = Arc::clone(&on_restore_requested);
			std::thread::spawn(move || {
				let result = restore_handler(PathBuf::from(file_path), recovery_phrase, new_password);
				let _ = sender.send(result);
			});

			let dialog_for_result = dialog_for_submit.clone();
			let error_for_result = error_for_submit.clone();
			let restore_button_for_result = restore_button_for_submit.clone();
			let restore_spinner_for_result = restore_spinner_for_submit.clone();
			let busy_for_result = Rc::clone(&busy_for_submit);
			let on_restore_completed = Rc::clone(&on_restore_completed);
			let update_action_state = Rc::clone(&update_action_state);
			glib::MainContext::default().spawn_local(async move {
				match receiver.await {
					Ok(Ok(())) => {
						busy_for_result.set(false);
						Self::set_pending_state(
							&restore_button_for_result,
							&restore_spinner_for_result,
							false,
						);

						let info_dialog = gtk4::MessageDialog::builder()
							.transient_for(&dialog_for_result)
							.modal(true)
							.buttons(gtk4::ButtonsType::Ok)
							.text("Restauration terminee")
							.secondary_text(
								"La base a ete restauree et l'application va redemarrer.",
							)
							.build();
						let dialog_for_close = dialog_for_result.clone();
						let on_restore_completed = Rc::clone(&on_restore_completed);
						info_dialog.connect_response(move |message, _| {
							message.close();
							dialog_for_close.close();
							on_restore_completed();
						});
						info_dialog.show();
					}
					Ok(Err(error)) => {
						busy_for_result.set(false);
						Self::set_pending_state(
							&restore_button_for_result,
							&restore_spinner_for_result,
							false,
						);
						Self::show_feedback(&error_for_result, &error.to_string());
						update_action_state();
					}
					Err(_) => {
						busy_for_result.set(false);
						Self::set_pending_state(
							&restore_button_for_result,
							&restore_spinner_for_result,
							false,
						);
						Self::show_feedback(
							&error_for_result,
							"La restauration a ete interrompue avant son terme.",
						);
						update_action_state();
					}
				}
			});
		});

		dialog.present();
	}
}
