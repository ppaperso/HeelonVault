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
use crate::i18n::I18nArg;
use crate::services::auth_policy_service::AuthPolicyService;
use crate::services::auth_service::AuthService;
use crate::services::totp_service::TotpService;
use crate::services::user_service::UserService;
use crate::ui::messages;
use crate::ui::widgets::password_strength_bar::PasswordStrengthBar;

pub struct LoginDialog {
	window: gtk4::Window,
}

enum LoginAttemptOutcome {
	Success,
	InvalidCredentials { remaining_lock_secs: i64 },
	InvalidTotp { remaining_lock_secs: i64 },
	Locked { remaining_lock_secs: i64 },
	RequiresTotp,
}

impl LoginDialog {
	pub fn new<TAuth, TPolicy, TUser, TTotp>(
		application: &adw::Application,
		parent: &adw::ApplicationWindow,
		runtime_handle: Handle,
		auth_service: Arc<TAuth>,
		auth_policy_service: Arc<TPolicy>,
		user_service: Arc<TUser>,
		totp_service: Arc<TTotp>,
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
		TUser: UserService + Send + Sync + 'static,
		TTotp: TotpService + Send + Sync + 'static,
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
			.title(crate::tr!("login-window-title").as_str())
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
			.orientation(Orientation::Vertical)
			.spacing(10)
			.margin_top(24)
			.margin_bottom(28)
			.margin_start(24)
			.margin_end(24)
			.build();

		let hero_top = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(12)
			.valign(Align::Center)
			.build();

		let hero_icon = gtk4::Image::from_resource(
			"/com/heelonvault/rust/icons/hicolor/128x128/apps/heelonvault.png",
		);
		hero_icon.set_pixel_size(44);
		hero_icon.set_halign(Align::Center);
		hero_icon.set_valign(Align::Center);
		hero_icon.add_css_class("login-hero-icon");

		let eyebrow_label = gtk4::Label::new(Some("HeelonVault"));
		eyebrow_label.add_css_class("login-badge");
		eyebrow_label.set_halign(Align::Start);

		let hero_beta_badge = gtk4::Label::new(Some("BETA"));
		hero_beta_badge.add_css_class("beta-badge");
		hero_beta_badge.add_css_class("login-beta-badge");
		hero_beta_badge.set_halign(Align::Start);

		let title_label = gtk4::Label::new(Some(crate::tr!("login-hero-title").as_str()));
		title_label.add_css_class("title-1");
		title_label.add_css_class("login-hero-title");
		title_label.set_halign(Align::Start);

		let subtitle_label = gtk4::Label::new(Some(crate::tr!("login-hero-subtitle").as_str()));
		subtitle_label.add_css_class("login-hero-copy");
		subtitle_label.set_wrap(true);
		subtitle_label.set_halign(Align::Start);

		let badges_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(6)
			.halign(Align::Start)
			.build();
		for text in [
			"AES-256-GCM".to_string(),
			"2FA TOTP".to_string(),
			format!("v{}", env!("CARGO_PKG_VERSION")),
		] {
			let badge = gtk4::Label::new(Some(text.as_str()));
			badge.add_css_class("login-hero-badge");
			badges_box.append(&badge);
		}

		hero_top.append(&hero_icon);
		hero_top.append(&eyebrow_label);
		hero_top.append(&hero_beta_badge);
		hero_box.append(&hero_top);
		hero_box.append(&title_label);
		hero_box.append(&subtitle_label);
		hero_box.append(&badges_box);
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

		let language_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.halign(Align::Fill)
			.build();
		let language_label = gtk4::Label::new(Some(crate::tr!("login-language-label").as_str()));
		language_label.add_css_class("login-field-label");
		language_label.set_halign(Align::Start);
		language_label.set_hexpand(true);
		let language_selector = gtk4::DropDown::from_strings(&[
			crate::tr!("login-language-fr").as_str(),
			crate::tr!("login-language-en").as_str(),
		]);
		language_selector.set_halign(Align::End);
		let current_lang = crate::i18n::current_language();
		if current_lang.to_ascii_lowercase().starts_with("en") {
			language_selector.set_selected(1);
		} else {
			language_selector.set_selected(0);
		}
		language_row.append(&language_label);
		language_row.append(&language_selector);

		let cps_frame = gtk4::Frame::new(None);
		cps_frame.add_css_class("login-cps-teaser");
		cps_frame.set_sensitive(false);

		let cps_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.margin_top(10)
			.margin_bottom(10)
			.margin_start(12)
			.margin_end(12)
			.build();

		let cps_image = gtk4::Image::from_resource("/com/heelonvault/rust/images/cps_card.png");
		cps_image.add_css_class("login-cps-image");
		cps_image.set_pixel_size(40);
		cps_image.set_size_request(64, 40);
		cps_image.set_halign(Align::Center);
		cps_image.set_valign(Align::Center);

		let cps_info = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(2)
			.hexpand(true)
			.build();

		let cps_name = gtk4::Label::new(Some(crate::tr!("login-cps-name").as_str()));
		cps_name.add_css_class("login-cps-title");
		cps_name.set_halign(Align::Start);

		let cps_sub = gtk4::Label::new(Some(crate::tr!("login-cps-subtitle").as_str()));
		cps_sub.add_css_class("login-cps-copy");
		cps_sub.set_halign(Align::Start);

		let cps_badge = gtk4::Label::new(Some(crate::tr!("login-cps-badge").as_str()));
		cps_badge.add_css_class("login-cps-badge");
		cps_badge.set_halign(Align::End);
		cps_badge.set_valign(Align::Center);

		cps_info.append(&cps_name);
		cps_info.append(&cps_sub);
		cps_box.append(&cps_image);
		cps_box.append(&cps_info);
		cps_box.append(&cps_badge);
		cps_frame.set_child(Some(&cps_box));

		let username_label = gtk4::Label::new(Some(crate::tr!("login-username-label").as_str()));
		username_label.add_css_class("login-field-label");
		username_label.add_css_class("login-field-label-caps");
		username_label.set_halign(Align::Start);

		let username_entry = gtk4::Entry::builder()
			.placeholder_text(crate::tr!("login-username-placeholder").as_str())
			.hexpand(true)
			.build();
		username_entry.add_css_class("login-entry");
		username_entry.set_activates_default(true);

		let password_label = gtk4::Label::new(Some(crate::tr!("login-password-label").as_str()));
		password_label.add_css_class("login-field-label");
		password_label.add_css_class("login-field-label-caps");
		password_label.set_halign(Align::Start);

		let password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text(crate::tr!("login-password-placeholder").as_str())
			.hexpand(true)
			.show_peek_icon(true)
			.build();
		password_entry.add_css_class("login-entry");
		password_entry.set_activates_default(true);

		let strength_label = gtk4::Label::new(None);
		strength_label.add_css_class("login-strength");
		strength_label.set_halign(Align::Start);
		strength_label.set_visible(false);

		let restore_button = gtk4::Button::with_label(crate::tr!("login-restore-button").as_str());
		restore_button.add_css_class("flat");
		restore_button.set_halign(Align::End);

		// STEP 1: Credentials form (always visible initially)
		let credentials_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(14)
			.build();

		credentials_box.append(&username_label);
		credentials_box.append(&username_entry);
		credentials_box.append(&password_label);
		credentials_box.append(&password_entry);
		credentials_box.append(&strength_label);

		let credentials_step_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(14)
			.build();
		credentials_step_box.append(&cps_frame);
		credentials_step_box.append(&credentials_box);
		credentials_step_box.append(&restore_button);

		// STEP 2: Full TOTP view replacing the central content
		let totp_step_box = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(8)
			.build();
		totp_step_box.add_css_class("login-totp-block");

		let totp_back_button = gtk4::Button::with_label(crate::tr!("login-totp-back").as_str());
		totp_back_button.add_css_class("flat");
		totp_back_button.set_halign(Align::Start);

		let totp_spacer = gtk4::Separator::new(Orientation::Horizontal);
		totp_spacer.set_margin_top(8);
		totp_spacer.set_margin_bottom(8);

		let totp_icon = gtk4::Image::from_icon_name("auth-2fa-symbolic");
		totp_icon.set_pixel_size(48);
		totp_icon.set_halign(Align::Center);
		totp_icon.add_css_class("login-totp-icon");

		let totp_title = gtk4::Label::new(Some(crate::tr!("login-totp-title").as_str()));
		totp_title.add_css_class("login-field-label");
		totp_title.set_halign(Align::Center);

		let totp_subtitle = gtk4::Label::new(Some(crate::tr!("login-totp-subtitle").as_str()));
		totp_subtitle.add_css_class("login-support-copy");
		totp_subtitle.set_wrap(true);
		totp_subtitle.set_justify(Justification::Center);
		totp_subtitle.set_halign(Align::Fill);

		let totp_entry_wrap = gtk4::Box::builder()
			.orientation(Orientation::Vertical)
			.spacing(0)
			.halign(Align::Center)
			.build();

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
		totp_entry_wrap.append(&totp_entry);

		totp_step_box.append(&totp_back_button);
		totp_step_box.append(&totp_spacer);
		totp_step_box.append(&totp_icon);
		totp_step_box.append(&totp_title);
		totp_step_box.append(&totp_subtitle);
		totp_step_box.append(&totp_entry_wrap);

		// Stack to switch between credentials and TOTP steps
		let step_stack = gtk4::Stack::builder()
			.transition_type(gtk4::StackTransitionType::SlideLeft)
			.build();

		step_stack.add_named(&credentials_step_box, Some("credentials"));
		step_stack.add_named(&totp_step_box, Some("totp"));
		step_stack.set_visible_child_name("credentials");

		let error_label = gtk4::Label::new(None);
		error_label.add_css_class("login-error");
		error_label.set_wrap(true);
		error_label.set_halign(Align::Start);
		error_label.set_visible(false);

		let button_box = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(10)
			.build();

		let back_button = gtk4::Button::with_label(crate::tr!("login-back-button").as_str());
		back_button.add_css_class("secondary-pill");
		back_button.set_hexpand(false);

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

		let login_button_text = crate::tr!("login-button");
		let button_label = gtk4::Label::new(Some(login_button_text.as_str()));
		button_label.add_css_class("heading");

		button_content.append(&spinner);
		button_content.append(&button_label);
		login_button.set_child(Some(&button_content));
		button_box.append(&back_button);
		button_box.append(&login_button);

		form_box.append(&step_stack);
		form_box.append(&error_label);
		form_box.append(&button_box);

		let sec_strip = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(6)
			.halign(Align::Center)
			.margin_top(4)
			.build();
		let sec_dot = gtk4::Label::new(Some("·"));
		sec_dot.add_css_class("login-sec-dot");
		let sec_text = gtk4::Label::new(Some(crate::tr!("login-security-note").as_str()));
		sec_text.add_css_class("login-support-copy");
		sec_text.set_halign(Align::Center);
		sec_strip.append(&sec_dot);
		sec_strip.append(&sec_text);
		form_box.append(&sec_strip);

		form_box.prepend(&language_row);

		form_card.set_child(Some(&form_box));

		let step_for_back = step_stack.clone();
		let totp_entry_for_back = totp_entry.clone();
		let error_for_back = error_label.clone();
		totp_back_button.connect_clicked(move |_| {
			step_for_back.set_visible_child_name("credentials");
			totp_entry_for_back.set_text("");
			Self::clear_feedback(&error_for_back);
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

		let step_for_button = step_stack.clone();
		let button_label_for_step = button_label.clone();
		let step_for_button_watch = step_stack.clone();
		step_stack.connect_visible_child_name_notify(move |_| {
			let is_totp_step = step_for_button_watch.visible_child_name().as_ref().map_or(false, |n| n == "totp");
			if is_totp_step {
				button_label_for_step.set_text(crate::tr!("login-button-verify").as_str());
			} else {
				button_label_for_step.set_text(crate::tr!("login-button").as_str());
			}
		});

		let window_for_i18n = window.clone();
		let title_for_i18n = title_label.clone();
		let subtitle_for_i18n = subtitle_label.clone();
		let cps_name_for_i18n = cps_name.clone();
		let cps_sub_for_i18n = cps_sub.clone();
		let cps_badge_for_i18n = cps_badge.clone();
		let username_label_for_i18n = username_label.clone();
		let username_entry_for_i18n = username_entry.clone();
		let password_label_for_i18n = password_label.clone();
		let password_entry_for_i18n = password_entry.clone();
		let restore_button_for_i18n = restore_button.clone();
		let totp_back_for_i18n = totp_back_button.clone();
		let totp_title_for_i18n = totp_title.clone();
		let totp_subtitle_for_i18n = totp_subtitle.clone();
		let back_button_for_i18n = back_button.clone();
		let sec_text_for_i18n = sec_text.clone();
		let language_label_for_i18n = language_label.clone();
		let language_selector_for_i18n = language_selector.clone();
		let step_for_i18n = step_stack.clone();
		let button_label_for_i18n = button_label.clone();
		let apply_login_i18n: Rc<dyn Fn()> = Rc::new(move || {
			window_for_i18n.set_title(Some(crate::tr!("login-window-title").as_str()));
			title_for_i18n.set_text(crate::tr!("login-hero-title").as_str());
			subtitle_for_i18n.set_text(crate::tr!("login-hero-subtitle").as_str());
			cps_name_for_i18n.set_text(crate::tr!("login-cps-name").as_str());
			cps_sub_for_i18n.set_text(crate::tr!("login-cps-subtitle").as_str());
			cps_badge_for_i18n.set_text(crate::tr!("login-cps-badge").as_str());
			username_label_for_i18n.set_text(crate::tr!("login-username-label").as_str());
			username_entry_for_i18n.set_placeholder_text(Some(
				crate::tr!("login-username-placeholder").as_str(),
			));
			password_label_for_i18n.set_text(crate::tr!("login-password-label").as_str());
			password_entry_for_i18n.set_placeholder_text(Some(
				crate::tr!("login-password-placeholder").as_str(),
			));
			restore_button_for_i18n.set_label(crate::tr!("login-restore-button").as_str());
			totp_back_for_i18n.set_label(crate::tr!("login-totp-back").as_str());
			totp_title_for_i18n.set_text(crate::tr!("login-totp-title").as_str());
			totp_subtitle_for_i18n.set_text(crate::tr!("login-totp-subtitle").as_str());
			back_button_for_i18n.set_label(crate::tr!("login-back-button").as_str());
			sec_text_for_i18n.set_text(crate::tr!("login-security-note").as_str());
			language_label_for_i18n.set_text(crate::tr!("login-language-label").as_str());

			let selected = language_selector_for_i18n.selected();
			language_selector_for_i18n.set_model(Some(&gtk4::StringList::new(&[
				crate::tr!("login-language-fr").as_str(),
				crate::tr!("login-language-en").as_str(),
			])));
			language_selector_for_i18n.set_selected(selected.min(1));

			let is_totp_step = step_for_i18n
				.visible_child_name()
				.as_ref()
				.map_or(false, |name| name == "totp");
			if is_totp_step {
				button_label_for_i18n.set_text(crate::tr!("login-button-verify").as_str());
			} else {
				button_label_for_i18n.set_text(crate::tr!("login-button").as_str());
			}
		});
		apply_login_i18n();

		let apply_login_i18n_for_selector = Rc::clone(&apply_login_i18n);
		language_selector.connect_selected_notify(move |dropdown| {
			let target_lang = if dropdown.selected() == 1 { "en" } else { "fr" };
			let _ = crate::i18n::set_language(target_lang);
			apply_login_i18n_for_selector();
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
		let user_for_submit = Arc::clone(&user_service);
		let runtime_for_submit = runtime_handle.clone();
		let lock_active_for_submit = Rc::clone(&lock_active);
		let lock_timer_for_submit = Rc::clone(&lock_timer);

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
		let user_for_lock_probe = Arc::clone(&user_service);
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
				let user_for_task = Arc::clone(&user_for_lock_probe);
				let username_for_task = typed_username.clone();
				let username_for_send = username_for_task.clone();
				std::thread::spawn(move || {
					let result = runtime_for_task.block_on(async move {
						let resolved_username = user_for_task
							.resolve_username_for_login_identifier(&username_for_task)
							.await?;
						match resolved_username {
							Some(username) => policy_for_task.get_state(username.as_str()).await.map(Some),
							None => Ok(None),
						}
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
					if let Ok((checked_username, Ok(Some(state)))) = receiver.await {
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

		login_button.connect_clicked(move |_| {
			if lock_active_for_submit.get() {
				return;
			}

			Self::clear_feedback(&error_for_submit);

			let current_step = step_for_button
				.visible_child_name()
				.as_ref()
				.map_or("credentials", |n| n.as_str())
				.to_string();

			if current_step == "credentials" {
				// STEP 1: Validate credentials and check for TOTP requirement
				let username = username_for_submit.text().trim().to_string();
				let password = password_for_submit.text().to_string();

				if username.is_empty() {
					Self::show_feedback(
						&error_for_submit,
						crate::tr!("login-error-username-required").as_str(),
					);
					return;
				}

				if password.is_empty() {
					Self::show_feedback(
						&error_for_submit,
						crate::tr!("login-error-password-required").as_str(),
					);
					return;
				}

				Self::set_pending_state(&button_for_submit, &spinner_for_submit, true);

				let (result_sender, result_receiver) = tokio::sync::oneshot::channel();
				let auth_for_task = Arc::clone(&auth_for_submit);
				let auth_policy_for_task = Arc::clone(&auth_policy_for_submit);
				let user_for_task = Arc::clone(&user_for_submit);
				let totp_for_task = Arc::clone(&totp_service);
				let username_for_task = username.clone();
				let password_for_task = password.into_bytes();
				let runtime_for_task = runtime_for_submit.clone();

				std::thread::spawn(move || {
					let password_bytes = password_for_task;
					let result: Result<LoginAttemptOutcome, AppError> = runtime_for_task.block_on(async move {
						let resolved_username = user_for_task
							.resolve_username_for_login_identifier(&username_for_task)
							.await?;

						let canonical_username = match resolved_username {
							Some(value) => value,
							None => {
								return Ok(LoginAttemptOutcome::InvalidCredentials {
									remaining_lock_secs: 0,
								});
							}
						};

						let lock_state = auth_policy_for_task.get_state(canonical_username.as_str()).await?;
						if lock_state.is_locked() {
							warn!(
								username = %canonical_username,
								remaining_lock_secs = lock_state.remaining_lock_secs,
								failed_attempts = lock_state.failed_attempts,
								"login attempt rejected: account currently locked"
							);
							return Ok(LoginAttemptOutcome::Locked {
								remaining_lock_secs: lock_state.remaining_lock_secs,
							});
						}

						let verified = auth_for_task
							.verify_password(
								canonical_username.as_str(),
								SecretBox::new(Box::new(password_bytes.clone())),
							)
							.await?;

						if verified {
							// Check if user has 2FA enabled
							let has_totp = totp_for_task
								.is_totp_enabled_for_username(canonical_username.as_str())
								.await?;

							if has_totp {
								// Require TOTP entry
								Ok(LoginAttemptOutcome::RequiresTotp)
							} else {
								// No TOTP required, proceed to success
								auth_policy_for_task
									.reset_failed_attempts(canonical_username.as_str())
									.await?;
								Ok(LoginAttemptOutcome::Success)
							}
						} else {
							let state = auth_policy_for_task
								.record_failed_attempt(canonical_username.as_str())
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
				let step_for_result = step_for_button.clone();
				let totp_for_result = totp_for_submit.clone();
				let authenticated_for_result = Rc::clone(&authenticated_for_submit);
				let on_authenticated_for_result = Rc::clone(&on_authenticated_for_submit);
				let lock_active_for_result = Rc::clone(&lock_active_for_submit);
				let lock_timer_for_result = Rc::clone(&lock_timer_for_submit);

				glib::MainContext::default().spawn_local(async move {
					let verification_result = result_receiver.await;

					match verification_result {
						Ok(Ok(LoginAttemptOutcome::Success)) => {
							Self::set_pending_state(&button_for_result, &spinner_for_result, false);
							authenticated_for_result.set(true);
							on_authenticated_for_result();
							dialog_for_result.close();
						}
						Ok(Ok(LoginAttemptOutcome::RequiresTotp)) => {
							Self::set_pending_state(&button_for_result, &spinner_for_result, false);
							// Switch to TOTP step
							step_for_result.set_visible_child_name("totp");
							totp_for_result.grab_focus();
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
									crate::tr!("login-error-invalid-credentials").as_str(),
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
						Ok(Ok(LoginAttemptOutcome::InvalidTotp { .. })) => {
							// Shouldn't reach here in credentials step
							Self::set_pending_state(&button_for_result, &spinner_for_result, false);
							Self::show_feedback(
								&error_for_result,
								crate::tr!("login-error-internal").as_str(),
							);
						}
						Ok(Err(_)) => {
							Self::show_feedback(
								&error_for_result,
								crate::tr!("login-error-unavailable").as_str(),
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
								crate::tr!("login-error-interrupted").as_str(),
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
			} else {
				// STEP 2: Verify TOTP code
				let totp = totp_for_submit.text().trim().to_string();
				let username = username_for_submit.text().trim().to_string();
				let password = password_for_submit.text().to_string();

				Self::set_pending_state(&button_for_submit, &spinner_for_submit, true);

				let (result_sender, result_receiver) = tokio::sync::oneshot::channel();
				let auth_policy_for_task = Arc::clone(&auth_policy_for_submit);
				let user_for_task = Arc::clone(&user_for_submit);
				let totp_for_task = Arc::clone(&totp_service);
				let username_for_task = username;
				let password_for_task = password.into_bytes();
				let totp_for_task_value = totp.clone();
				let runtime_for_task = runtime_for_submit.clone();

				std::thread::spawn(move || {
					let password_bytes = password_for_task;
					let result: Result<LoginAttemptOutcome, AppError> = runtime_for_task.block_on(async move {
						let resolved_username = user_for_task
							.resolve_username_for_login_identifier(&username_for_task)
							.await?;

						let canonical_username = match resolved_username {
							Some(value) => value,
							None => {
								return Ok(LoginAttemptOutcome::InvalidCredentials {
									remaining_lock_secs: 0,
								});
							}
						};

						let lock_state = auth_policy_for_task.get_state(canonical_username.as_str()).await?;
						if lock_state.is_locked() {
							return Ok(LoginAttemptOutcome::Locked {
								remaining_lock_secs: lock_state.remaining_lock_secs,
							});
						}

						if !Self::is_valid_totp(&totp_for_task_value) {
							let state = auth_policy_for_task
								.record_failed_attempt(canonical_username.as_str())
								.await?;
							return Ok(LoginAttemptOutcome::InvalidTotp {
								remaining_lock_secs: state.remaining_lock_secs,
							});
						}

						let totp_ok = totp_for_task
							.verify_login_totp(
								canonical_username.as_str(),
								SecretBox::new(Box::new(password_bytes)),
								totp_for_task_value.as_str(),
							)
							.await?;

						if !totp_ok {
							let state = auth_policy_for_task
								.record_failed_attempt(canonical_username.as_str())
								.await?;
							return Ok(LoginAttemptOutcome::InvalidTotp {
								remaining_lock_secs: state.remaining_lock_secs,
							});
						}

						auth_policy_for_task
							.reset_failed_attempts(canonical_username.as_str())
							.await?;
						Ok(LoginAttemptOutcome::Success)
					});
					let _ = result_sender.send(result);
				});

				let dialog_for_result = dialog_for_submit.clone();
				let error_for_result = error_for_submit.clone();
				let button_for_result = button_for_submit.clone();
				let spinner_for_result = spinner_for_submit.clone();
				let totp_for_result = totp_for_submit.clone();
				let authenticated_for_result = Rc::clone(&authenticated_for_submit);
				let on_authenticated_for_result = Rc::clone(&on_authenticated_for_submit);
				let lock_active_for_result = Rc::clone(&lock_active_for_submit);
				let lock_timer_for_result = Rc::clone(&lock_timer_for_submit);

				glib::MainContext::default().spawn_local(async move {
					let verification_result = result_receiver.await;

					match verification_result {
						Ok(Ok(LoginAttemptOutcome::Success)) => {
							Self::set_pending_state(&button_for_result, &spinner_for_result, false);
							authenticated_for_result.set(true);
							on_authenticated_for_result();
							dialog_for_result.close();
						}
						Ok(Ok(LoginAttemptOutcome::InvalidTotp { remaining_lock_secs })) => {
							totp_for_result.grab_focus();

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
								let totp_feedback = messages::login_totp_error_message(
									totp_for_result.text().trim(),
								);
								Self::show_feedback(
									&error_for_result,
									totp_feedback.as_str(),
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
						Ok(Ok(LoginAttemptOutcome::InvalidCredentials { remaining_lock_secs: _ })) => {
							// This shouldn't happen in TOTP step, but handle it
							Self::set_pending_state(&button_for_result, &spinner_for_result, false);
							Self::show_feedback(
								&error_for_result,
								crate::tr!("login-error-internal").as_str(),
							);
						}
						Ok(Ok(LoginAttemptOutcome::RequiresTotp)) => {
							// Shouldn't happen in TOTP step
							Self::set_pending_state(&button_for_result, &spinner_for_result, false);
						}
						Ok(Err(_)) => {
							Self::show_feedback(
								&error_for_result,
								crate::tr!("login-error-unavailable").as_str(),
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
								crate::tr!("login-error-interrupted").as_str(),
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
			}
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
			Self::show_feedback(error_label, crate::tr!("login-error-retry-now").as_str());
			return;
		}

		lock_active.set(true);
		spinner.set_visible(false);
		spinner.set_spinning(false);
		button.set_sensitive(false);

		Self::show_feedback(
			error_label,
			crate::i18n::tr_args(
				"login-error-account-locked",
				&[("seconds", I18nArg::Num(current_secs))],
			)
			.as_str(),
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
				Self::show_feedback(&error_for_tick, crate::tr!("login-error-retry-now").as_str());
				let _ = lock_timer_for_tick.borrow_mut().take();
				glib::ControlFlow::Break
			} else {
				Self::show_feedback(
					&error_for_tick,
					crate::i18n::tr_args(
						"login-error-account-locked",
						&[("seconds", I18nArg::Num(current_secs))],
					)
					.as_str(),
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
			title_label.set_text(crate::tr!("login-greeting-empty").as_str());
			return;
		}

		title_label.set_text(
			crate::i18n::tr_args("login-greeting-hello", &[("username", I18nArg::Str(username))])
				.as_str(),
		);
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
			(crate::tr!("login-password-strength-very-strong"), "success")
		} else if score >= 3 {
			(crate::tr!("login-password-strength-strong"), "success")
		} else if score >= 2 {
			(crate::tr!("login-password-strength-medium"), "warning")
		} else {
			(crate::tr!("login-password-strength-weak"), "error")
		};

		strength_label.remove_css_class("dim-label");
		strength_label.add_css_class(css_class);
		strength_label.set_text(label.as_str());
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
			.title(crate::tr!("login-restore-dialog-title").as_str())
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
			crate::tr!("login-restore-description").as_str(),
		));
		title.set_wrap(true);
		title.set_halign(Align::Start);

		let file_label = gtk4::Label::new(Some(crate::tr!("login-restore-file-label").as_str()));
		file_label.add_css_class("login-field-label");
		file_label.set_halign(Align::Start);

		let file_row = gtk4::Box::builder()
			.orientation(Orientation::Horizontal)
			.spacing(8)
			.build();

		let file_entry = gtk4::Entry::builder()
			.placeholder_text(crate::tr!("login-restore-file-placeholder").as_str())
			.hexpand(true)
			.build();
		file_entry.add_css_class("login-entry");

		let browse_button = gtk4::Button::with_label(crate::tr!("login-restore-browse").as_str());
		browse_button.add_css_class("secondary-pill");

		file_row.append(&file_entry);
		file_row.append(&browse_button);

		let phrase_label = gtk4::Label::new(Some(crate::tr!("login-restore-phrase-label").as_str()));
		phrase_label.add_css_class("login-field-label");
		phrase_label.set_halign(Align::Start);

		let phrase_entry = gtk4::Entry::builder()
			.placeholder_text(crate::tr!("login-restore-phrase-placeholder").as_str())
			.hexpand(true)
			.build();
		phrase_entry.add_css_class("login-entry");

		let password_label = gtk4::Label::new(Some(crate::tr!("login-restore-password-label").as_str()));
		password_label.add_css_class("login-field-label");
		password_label.set_halign(Align::Start);

		let new_password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text(crate::tr!("login-restore-password-placeholder").as_str())
			.hexpand(true)
			.show_peek_icon(true)
			.build();
		new_password_entry.add_css_class("login-entry");

		let strength_bar = PasswordStrengthBar::new();
		strength_bar.connect_to_password_entry(&new_password_entry);

		let confirm_label = gtk4::Label::new(Some(crate::tr!("login-restore-confirm-label").as_str()));
		confirm_label.add_css_class("login-field-label");
		confirm_label.set_halign(Align::Start);

		let confirm_password_entry = gtk4::PasswordEntry::builder()
			.placeholder_text(crate::tr!("login-restore-confirm-placeholder").as_str())
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

		let cancel_button = gtk4::Button::with_label(crate::tr!("login-restore-cancel").as_str());
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
		let restore_label = gtk4::Label::new(Some(crate::tr!("login-restore-submit").as_str()));
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
