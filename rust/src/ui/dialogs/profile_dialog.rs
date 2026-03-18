use std::cell::Cell;
use std::fs;
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::Arc;

use chrono::Local;
use gtk4::glib;
use gtk4::prelude::*;
use libadwaita as adw;
use libadwaita::prelude::*;
use secrecy::{ExposeSecret, SecretBox};
use tokio::runtime::Handle;
use tracing::{info, warn};
use uuid::Uuid;

use crate::errors::AppError;
use crate::services::auth_policy_service::AuthPolicyService;
use crate::services::backup_service::BackupService;
use crate::services::import_service::ImportService;
use crate::services::secret_service::SecretService;
use crate::services::user_service::{UserProfileUpdate, UserService};
use crate::services::vault_service::VaultService;
use crate::ui::widgets::password_strength_bar::PasswordStrengthBar;

pub struct ProfileDialog;

impl ProfileDialog {
    pub fn present<TUser, TPolicy, TBackup, TImport, TSecret, TVault>(
        app: &adw::Application,
        parent: &adw::ApplicationWindow,
        runtime_handle: Handle,
        user_service: Arc<TUser>,
        auth_policy_service: Arc<TPolicy>,
        backup_service: Arc<TBackup>,
        import_service: Arc<TImport>,
        secret_service: Arc<TSecret>,
        vault_service: Arc<TVault>,
        database_path: PathBuf,
        runtime_handle_io: Handle,
        user_id: Uuid,
        session_master_key_provider: impl Fn() -> Option<Vec<u8>> + 'static,
        on_profile_updated: impl Fn(String) + 'static,
        on_auto_lock_delay_updated: impl Fn(u64) + 'static,
    ) where
        TUser: UserService + Send + Sync + 'static,
        TPolicy: AuthPolicyService + Send + Sync + 'static,
        TBackup: BackupService + Send + Sync + 'static,
        TImport: ImportService + Send + Sync + 'static,
        TSecret: SecretService + Send + Sync + 'static,
        TVault: VaultService + Send + Sync + 'static,
    {
        info!(user_id = %user_id, "opening profile preferences window");

        let window = adw::PreferencesWindow::builder()
            .application(app)
            .transient_for(parent)
            .modal(true)
            .title("Mon profil")
            .default_width(560)
            .default_height(680)
            .build();

        let profile_page = adw::PreferencesPage::new();
        profile_page.set_title("Profil");

        let info_group = adw::PreferencesGroup::new();
        info_group.set_title("Informations");

        let username_row = adw::EntryRow::new();
        username_row.set_title("Nom d'utilisateur");
        username_row.set_sensitive(false);
        username_row.add_css_class("profile-entry-row");

        let display_name_row = adw::EntryRow::new();
        display_name_row.set_title("Nom d'affichage");
        display_name_row.add_css_class("profile-entry-row");

        let email_row = adw::EntryRow::new();
        email_row.set_title("Email");
        email_row.add_css_class("profile-entry-row");

        let current_password_row = adw::PasswordEntryRow::new();
        current_password_row.set_title("Mot de passe actuel (si changement email)");
        current_password_row.add_css_class("profile-entry-row");

        let save_row = adw::ActionRow::new();
        save_row.set_title("Enregistrer les modifications");
        let save_button = gtk4::Button::with_label("Sauvegarder");
        save_button.add_css_class("suggested-action");
        save_row.add_suffix(&save_button);

        info_group.add(&username_row);
        info_group.add(&display_name_row);
        info_group.add(&email_row);
        info_group.add(&current_password_row);
        info_group.add(&save_row);
        profile_page.add(&info_group);

        let security_group = adw::PreferencesGroup::new();
        security_group.set_title("Sécurité");

        let auto_lock_delay_row = adw::ComboRow::new();
        auto_lock_delay_row.set_title("Délai de verrouillage automatique");
        let auto_lock_options = gtk4::StringList::new(&[
            "1 minute",
            "5 minutes",
            "10 minutes",
            "30 minutes",
        ]);
        auto_lock_delay_row.set_model(Some(&auto_lock_options));

        let current_master_password_row = adw::PasswordEntryRow::new();
        current_master_password_row.set_title("Mot de passe actuel");
        current_master_password_row.add_css_class("profile-entry-row");

        let new_master_password_row = adw::PasswordEntryRow::new();
        new_master_password_row.set_title("Nouveau mot de passe");
        new_master_password_row.add_css_class("profile-entry-row");

        let master_strength_bar = PasswordStrengthBar::new();
        master_strength_bar.connect_to_password_entry_row(&new_master_password_row);
        let master_strength_row = master_strength_bar.into_action_row();

        let confirm_master_password_row = adw::PasswordEntryRow::new();
        confirm_master_password_row.set_title("Confirmer le nouveau mot de passe");
        confirm_master_password_row.add_css_class("profile-entry-row");

        let password_save_row = adw::ActionRow::new();
        password_save_row.set_title("Mettre à jour la master key");
        let change_password_button = gtk4::Button::with_label("Changer");
        change_password_button.add_css_class("suggested-action");
        change_password_button.set_sensitive(false);
        master_strength_bar.connect_and_gate_button(
            &new_master_password_row,
            &change_password_button,
            4,
        );
        password_save_row.add_suffix(&change_password_button);

        security_group.add(&current_master_password_row);
        security_group.add(&auto_lock_delay_row);
        security_group.add(&new_master_password_row);
        security_group.add(&master_strength_row);
        security_group.add(&confirm_master_password_row);
        security_group.add(&password_save_row);

        // ─── Progress panel for master key change (hidden initially) ───────────
        let mkchange_group = adw::PreferencesGroup::new();
        mkchange_group.set_title("Changement de la master key");
        mkchange_group.set_description(Some(
            "Dérivation Argon2id sécurisée \u{2022} Ne fermez pas cette fenêtre",
        ));
        mkchange_group.add_css_class("mkchange-progress-group");
        mkchange_group.set_visible(false);

        let build_step = |label: &str| -> (adw::ActionRow, gtk4::Spinner, gtk4::Image) {
            let row = adw::ActionRow::builder().title(label).build();
            row.add_css_class("mkchange-step-row");
            let prefix = gtk4::Box::builder()
                .orientation(gtk4::Orientation::Horizontal)
                .valign(gtk4::Align::Center)
                .margin_end(4)
                .build();
            let spinner = gtk4::Spinner::new();
            spinner.set_visible(false);
            let icon = gtk4::Image::from_icon_name("radio-symbolic");
            icon.set_pixel_size(18);
            icon.add_css_class("mkchange-step-icon");
            icon.add_css_class("mkchange-step-icon-pending");
            prefix.append(&spinner);
            prefix.append(&icon);
            row.add_prefix(&prefix);
            (row, spinner, icon)
        };

        let (step1_row, step1_spinner, step1_icon) =
            build_step("Vérification du mot de passe actuel");
        let (step2_row, step2_spinner, step2_icon) =
            build_step("Dérivation de la nouvelle clé (Argon2id)");
        let (step3_row, step3_spinner, step3_icon) =
            build_step("Enregistrement sécurisé dans la base");

        mkchange_group.add(&step1_row);
        mkchange_group.add(&step2_row);
        mkchange_group.add(&step3_row);

        let data_group = adw::PreferencesGroup::new();
        data_group.set_title("Gestion des données");

        let export_row = adw::ActionRow::new();
        export_row.set_title("Exporter ma base (.hvb)");
        export_row.set_subtitle("Sauvegarde chiffrée AES-256-GCM avec Recovery Key");
        let export_button = gtk4::Button::with_label("Exporter ma base");
        export_button.add_css_class("suggested-action");
        export_row.add_suffix(&export_button);

        let import_row = adw::ActionRow::new();
        import_row.set_title("Importer des données (CSV)");
        import_row.set_subtitle("Colonnes attendues: name, url, username, password, notes");
        let import_button = gtk4::Button::with_label("Importer des données (CSV)");
        import_button.add_css_class("flat");
        import_row.add_suffix(&import_button);

        data_group.add(&export_row);
        data_group.add(&import_row);

        profile_page.add(&security_group);
        profile_page.add(&mkchange_group);
        profile_page.add(&data_group);

        window.add(&profile_page);

        // ─── Block window close while the operation is in progress ─────────────
        let is_changing_password: Rc<Cell<bool>> = Rc::new(Cell::new(false));
        {
            let guard = Rc::clone(&is_changing_password);
            window.connect_close_request(move |_| {
                if guard.get() {
                    glib::Propagation::Stop
                } else {
                    glib::Propagation::Proceed
                }
            });
        }

        let auto_lock_delay_loading = Rc::new(Cell::new(true));
        let on_auto_lock_delay_updated = Rc::new(on_auto_lock_delay_updated);

        let (load_sender, load_receiver) = tokio::sync::oneshot::channel();
        let service_for_load = Arc::clone(&user_service);
        let auth_policy_for_load = Arc::clone(&auth_policy_service);
        let runtime_for_load = runtime_handle.clone();
        std::thread::spawn(move || {
            let result = runtime_for_load.block_on(async move {
                let user = service_for_load.get_user_profile(user_id).await?;
                let delay = auth_policy_for_load
                    .get_auto_lock_delay(user.username.as_str())
                    .await?;
                Ok::<_, AppError>((user, delay))
            });
            let _ = load_sender.send(result);
        });

        let username_row_for_load = username_row.clone();
        let display_name_row_for_load = display_name_row.clone();
        let email_row_for_load = email_row.clone();
        let auto_lock_row_for_load = auto_lock_delay_row.clone();
        let auto_lock_loading_for_load = Rc::clone(&auto_lock_delay_loading);
        let window_for_load = window.clone();
        glib::MainContext::default().spawn_local(async move {
            match load_receiver.await {
                Ok(Ok((user, delay_mins))) => {
                    username_row_for_load.set_text(user.username.as_str());
                    display_name_row_for_load.set_text(user.display_name.as_deref().unwrap_or_default());
                    email_row_for_load.set_text(user.email.as_deref().unwrap_or_default());
                    let selected = match delay_mins {
                        1 => 0,
                        10 => 2,
                        30 => 3,
                        _ => 1,
                    };
                    auto_lock_row_for_load.set_selected(selected);
                    auto_lock_loading_for_load.set(false);
                }
                Ok(Err(err)) => {
                    warn!("failed to load user profile: {err:?}");
                    let toast = adw::Toast::new("Impossible de charger le profil");
                    window_for_load.add_toast(toast);
                    auto_lock_loading_for_load.set(false);
                }
                Err(err) => {
                    warn!("failed to receive profile load result: {err:?}");
                    let toast = adw::Toast::new("Impossible de charger le profil");
                    window_for_load.add_toast(toast);
                    auto_lock_loading_for_load.set(false);
                }
            }
        });

        let auth_policy_for_delay_save = Arc::clone(&auth_policy_service);
        let runtime_for_delay_save = runtime_handle.clone();
        let username_for_delay = username_row.clone();
        let auto_lock_loading_for_change = Rc::clone(&auto_lock_delay_loading);
        let window_for_delay_save = window.clone();
        let delay_callback_for_change = Rc::clone(&on_auto_lock_delay_updated);
        let session_master_key_provider = Rc::new(session_master_key_provider);
        auto_lock_delay_row.connect_selected_notify(move |row| {
            if auto_lock_loading_for_change.get() {
                return;
            }

            let username = username_for_delay.text().trim().to_string();
            if username.is_empty() {
                return;
            }

            let mins: i64 = match row.selected() {
                0 => 1,
                1 => 5,
                2 => 10,
                3 => 30,
                _ => 5,
            };

            let (sender, receiver) = tokio::sync::oneshot::channel();
            let runtime_for_task = runtime_for_delay_save.clone();
            let auth_policy_for_task = Arc::clone(&auth_policy_for_delay_save);
            let username_for_task = username.clone();
            std::thread::spawn(move || {
                let result = runtime_for_task.block_on(async move {
                    auth_policy_for_task
                        .update_auto_lock_delay(username_for_task.as_str(), mins)
                        .await
                });
                let _ = sender.send((mins, result));
            });

            let window_for_result = window_for_delay_save.clone();
            let delay_callback_for_result = Rc::clone(&delay_callback_for_change);
            glib::MainContext::default().spawn_local(async move {
                match receiver.await {
                    Ok((updated_mins, Ok(()))) => {
                        delay_callback_for_result(updated_mins as u64);
                        window_for_result.add_toast(adw::Toast::new("Délai auto-lock mis à jour"));
                    }
                    Ok((_, Err(_))) | Err(_) => {
                        window_for_result
                            .add_toast(adw::Toast::new("Échec de la mise à jour du délai auto-lock"));
                    }
                }
            });
        });

        let window_for_export = window.clone();
        let backup_for_export = Arc::clone(&backup_service);
        let db_path_for_export = database_path.clone();
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
            let db_path_for_response = db_path_for_export.clone();
            chooser.connect_response(move |dialog, response| {
                if response != gtk4::ResponseType::Accept {
                    dialog.destroy();
                    return;
                }

                let file_opt = dialog.file();
                dialog.destroy();
                let Some(file) = file_opt else {
                    window_for_response.add_toast(adw::Toast::new("Fichier de destination invalide"));
                    return;
                };
                let Some(mut backup_path) = file.path() else {
                    window_for_response.add_toast(adw::Toast::new("Chemin de destination invalide"));
                    return;
                };
                if backup_path.extension().is_none() {
                    backup_path.set_extension("hvb");
                }

                let recovery = match backup_for_response.generate_recovery_key() {
                    Ok(value) => value,
                    Err(_) => {
                        window_for_response
                            .add_toast(adw::Toast::new("Impossible de générer la Recovery Key"));
                        return;
                    }
                };

                let phrase_text = recovery.recovery_phrase.expose_secret().to_string();
                let recovery_words: Vec<String> = phrase_text
                    .split_whitespace()
                    .map(|word| word.to_string())
                    .collect();

                if recovery_words.len() != 24 {
                    window_for_response.add_toast(adw::Toast::new(
                        "Recovery Key invalide: 24 mots attendus",
                    ));
                    return;
                }

                let confirm_dialog = adw::MessageDialog::new(
                    Some(&window_for_response),
                    Some("Recovery Key - à noter maintenant"),
                    Some("Conservez cette phrase de récupération en lieu sûr avant de lancer l'export."),
                );
                confirm_dialog.add_response("cancel", "Annuler");
                confirm_dialog.add_response("confirm", "J'ai noté");
                confirm_dialog.set_response_appearance(
                    "confirm",
                    adw::ResponseAppearance::Suggested,
                );
                confirm_dialog.set_response_enabled("confirm", false);

                let content_box = gtk4::Box::builder()
                    .orientation(gtk4::Orientation::Vertical)
                    .spacing(10)
                    .margin_top(8)
                    .margin_bottom(8)
                    .build();

                let helper_label = gtk4::Label::new(Some(
                    "Sauvegardez votre clé via Copier, Imprimer ou Enregistrer (TXT).",
                ));
                helper_label.set_wrap(true);
                helper_label.set_halign(gtk4::Align::Start);
                helper_label.add_css_class("dim-label");

                let words_flow = gtk4::FlowBox::builder()
                    .selection_mode(gtk4::SelectionMode::None)
                    .max_children_per_line(2)
                    .min_children_per_line(1)
                    .column_spacing(8)
                    .row_spacing(8)
                    .build();

                for (index, word) in recovery_words.iter().enumerate() {
                    let chip_box = gtk4::Box::builder()
                        .orientation(gtk4::Orientation::Horizontal)
                        .spacing(8)
                        .margin_top(6)
                        .margin_bottom(6)
                        .margin_start(8)
                        .margin_end(8)
                        .build();

                    let number_label = gtk4::Label::new(Some(format!("{:02}.", index + 1).as_str()));
                    number_label.add_css_class("dim-label");

                    let separator_label = gtk4::Label::new(Some("|"));
                    separator_label.add_css_class("dim-label");

                    let word_label = gtk4::Label::new(Some(word.as_str()));
                    word_label.add_css_class("monospace");
                    word_label.set_selectable(true);
                    word_label.set_xalign(0.0);

                    chip_box.append(&number_label);
                    chip_box.append(&separator_label);
                    chip_box.append(&word_label);

                    let frame = gtk4::Frame::new(None);
                    frame.set_child(Some(&chip_box));
                    words_flow.insert(&frame, -1);
                }

                let words_scroller = gtk4::ScrolledWindow::builder()
                    .hscrollbar_policy(gtk4::PolicyType::Never)
                    .vscrollbar_policy(gtk4::PolicyType::Automatic)
                    .min_content_height(220)
                    .max_content_height(300)
                    .child(&words_flow)
                    .build();

                let actions_box = gtk4::Box::builder()
                    .orientation(gtk4::Orientation::Horizontal)
                    .spacing(8)
                    .hexpand(true)
                    .build();

                let make_action_button = |icon: &str, label: &str| {
                    let button = gtk4::Button::new();
                    button.add_css_class("flat");
                    let inner = gtk4::Box::builder()
                        .orientation(gtk4::Orientation::Horizontal)
                        .spacing(6)
                        .build();
                    inner.append(&gtk4::Image::from_icon_name(icon));
                    inner.append(&gtk4::Label::new(Some(label)));
                    button.set_child(Some(&inner));
                    button
                };

                let copy_button = make_action_button("edit-copy-symbolic", "Copier");
                let print_button = make_action_button("printer-symbolic", "Imprimer");
                let save_button = make_action_button("document-save-symbolic", "Enregistrer (TXT)");

                actions_box.append(&copy_button);
                actions_box.append(&print_button);
                actions_box.append(&save_button);

                content_box.append(&helper_label);
                content_box.append(&words_scroller);
                content_box.append(&actions_box);
                confirm_dialog.set_extra_child(Some(&content_box));

                let save_action_done = Rc::new(Cell::new(false));
                let save_action_done_for_enable = Rc::clone(&save_action_done);
                let dialog_for_enable = confirm_dialog.clone();
                let enable_confirm = Rc::new(move || {
                    if !save_action_done_for_enable.get() {
                        save_action_done_for_enable.set(true);
                        dialog_for_enable.set_response_enabled("confirm", true);
                    }
                });

                let phrase_for_copy = phrase_text.clone();
                let window_for_copy = window_for_response.clone();
                let enable_for_copy = Rc::clone(&enable_confirm);
                copy_button.connect_clicked(move |_| {
                    let Some(display) = gtk4::gdk::Display::default() else {
                        window_for_copy.add_toast(adw::Toast::new("Presse-papier indisponible"));
                        return;
                    };

                    let clipboard = display.clipboard();
                    clipboard.set_text(phrase_for_copy.as_str());
                    let clipboard_for_clear = clipboard.clone();
                    glib::timeout_add_seconds_local(60, move || {
                        clipboard_for_clear.set_text("");
                        glib::ControlFlow::Break
                    });
                    window_for_copy.add_toast(adw::Toast::new("Recovery Key copiée (effacement dans 60s)"));
                    enable_for_copy();
                });

                let words_for_print = recovery_words.clone();
                let window_for_print = window_for_response.clone();
                let enable_for_print = Rc::clone(&enable_confirm);
                print_button.connect_clicked(move |_| {
                    info!("Recovery key print operation initiated");

                    let print_operation = gtk4::PrintOperation::new();
                    print_operation.connect_begin_print(|operation, _| {
                        operation.set_n_pages(1);
                    });

                    let words = words_for_print.clone();
                    print_operation.connect_draw_page(move |_, print_context, _| {
                        let cr = print_context.cairo_context();

                        let mut y = 36.0_f64;
                        cr.select_font_face(
                            "Monospace",
                            gtk4::cairo::FontSlant::Normal,
                            gtk4::cairo::FontWeight::Bold,
                        );
                        cr.set_font_size(16.0);
                        cr.move_to(36.0, y);
                        let _ = cr.show_text("HeelonVault - Cle de Secours");

                        y += 24.0;
                        cr.select_font_face(
                            "Monospace",
                            gtk4::cairo::FontSlant::Normal,
                            gtk4::cairo::FontWeight::Normal,
                        );
                        cr.set_font_size(11.0);
                        let printed_at = Local::now().format("%d/%m/%Y %H:%M").to_string();
                        cr.move_to(36.0, y);
                        let _ = cr.show_text(format!("Date: {}", printed_at).as_str());

                        y += 28.0;
                        cr.set_font_size(12.0);
                        for (index, word) in words.iter().enumerate() {
                            cr.move_to(36.0, y);
                            let _ = cr.show_text(format!("{:02}. {}", index + 1, word).as_str());
                            y += 18.0;
                        }
                    });

                    match print_operation.run(
                        gtk4::PrintOperationAction::PrintDialog,
                        Some(&window_for_print),
                    ) {
                        Ok(result) => {
                            if result != gtk4::PrintOperationResult::Cancel {
                                enable_for_print();
                            }
                        }
                        Err(_) => {
                            window_for_print
                                .add_toast(adw::Toast::new("Impossible de lancer l'impression"));
                        }
                    }
                });

                let words_for_file = recovery_words.clone();
                let window_for_save = window_for_response.clone();
                let enable_for_save = Rc::clone(&enable_confirm);
                save_button.connect_clicked(move |_| {
                    let chooser = gtk4::FileChooserNative::builder()
                        .title("Enregistrer la Recovery Key (TXT)")
                        .transient_for(&window_for_save)
                        .accept_label("Enregistrer")
                        .cancel_label("Annuler")
                        .action(gtk4::FileChooserAction::Save)
                        .build();
                    chooser.set_current_name("heelonvault_recovery_key.txt");

                    let words_for_response = words_for_file.clone();
                    let window_for_response = window_for_save.clone();
                    let enable_for_response = Rc::clone(&enable_for_save);
                    chooser.connect_response(move |dialog, response| {
                        if response != gtk4::ResponseType::Accept {
                            dialog.destroy();
                            return;
                        }

                        let file_opt = dialog.file();
                        dialog.destroy();
                        let Some(file) = file_opt else {
                            window_for_response
                                .add_toast(adw::Toast::new("Fichier TXT invalide"));
                            return;
                        };

                        let Some(mut txt_path) = file.path() else {
                            window_for_response
                                .add_toast(adw::Toast::new("Chemin TXT invalide"));
                            return;
                        };

                        if txt_path.extension().is_none() {
                            txt_path.set_extension("txt");
                        }

                        let mut content = String::from("HeelonVault - Cle de Secours\n");
                        content.push_str(format!("Date: {}\n\n", Local::now().format("%d/%m/%Y %H:%M")).as_str());
                        for (index, word) in words_for_response.iter().enumerate() {
                            content.push_str(format!("{:02}. {}\n", index + 1, word).as_str());
                        }

                        match fs::write(txt_path.as_path(), content.as_bytes()) {
                            Ok(()) => {
                                window_for_response
                                    .add_toast(adw::Toast::new("Recovery Key enregistrée en TXT"));
                                enable_for_response();
                            }
                            Err(_) => {
                                window_for_response
                                    .add_toast(adw::Toast::new("Échec de l'enregistrement TXT"));
                            }
                        }
                    });

                    chooser.show();
                });

                let window_for_confirm = window_for_response.clone();
                let backup_for_confirm = Arc::clone(&backup_for_response);
                let db_path_for_confirm = db_path_for_response.clone();
                confirm_dialog.connect_response(None, move |d, response_id| {
                    d.close();
                    if response_id != "confirm" {
                        return;
                    }

                    let (sender, receiver) = tokio::sync::oneshot::channel();
                    let backup_for_task = Arc::clone(&backup_for_confirm);
                    let db_for_task = db_path_for_confirm.clone();
                    let backup_path_for_task = backup_path.clone();
                    let recovery_for_task = recovery.recovery_phrase.clone();
                    std::thread::spawn(move || {
                        let result = backup_for_task.export_hvb_with_recovery_key(
                            db_for_task.as_path(),
                            backup_path_for_task.as_path(),
                            &recovery_for_task,
                        );
                        let _ = sender.send(result);
                    });

                    let window_for_result = window_for_confirm.clone();
                    glib::MainContext::default().spawn_local(async move {
                        match receiver.await {
                            Ok(Ok(_)) => {
                                window_for_result.add_toast(adw::Toast::new("Export .hvb terminé"));
                            }
                            Ok(Err(_)) | Err(_) => {
                                window_for_result.add_toast(adw::Toast::new("Échec de l'export .hvb"));
                            }
                        }
                    });
                });
                confirm_dialog.present();
            });

            chooser.show();
        });

        let window_for_import = window.clone();
        let import_for_profile = Arc::clone(&import_service);
        let secret_for_import = Arc::clone(&secret_service);
        let vault_for_import = Arc::clone(&vault_service);
        let runtime_for_import = runtime_handle_io.clone();
        let session_key_for_import = Rc::clone(&session_master_key_provider);
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
            let session_key_for_response = Rc::clone(&session_key_for_import);
            chooser.connect_response(move |dialog, response| {
                if response != gtk4::ResponseType::Accept {
                    dialog.destroy();
                    return;
                }

                let file_opt = dialog.file();
                dialog.destroy();
                let Some(file) = file_opt else {
                    window_for_response.add_toast(adw::Toast::new("Fichier CSV invalide"));
                    return;
                };
                let Some(csv_path) = file.path() else {
                    window_for_response.add_toast(adw::Toast::new("Chemin CSV invalide"));
                    return;
                };

                let Some(master_key) = session_key_for_response() else {
                    window_for_response.add_toast(adw::Toast::new("Session verrouillée, reconnectez-vous"));
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
                glib::MainContext::default().spawn_local(async move {
                    match receiver.await {
                        Ok(Ok(count)) => {
                            window_for_result.add_toast(adw::Toast::new(
                                format!("Import CSV terminé: {} secrets", count).as_str(),
                            ));
                        }
                        Ok(Err(_)) | Err(_) => {
                            window_for_result.add_toast(adw::Toast::new("Échec de l'import CSV"));
                        }
                    }
                });
            });

            chooser.show();
        });

        let service_for_save = Arc::clone(&user_service);
        let runtime_for_save = runtime_handle.clone();
        let display_name_row_for_save = display_name_row.clone();
        let email_row_for_save = email_row.clone();
        let current_password_for_save = current_password_row.clone();
        let window_for_save = window.clone();
        let on_profile_updated = Rc::new(on_profile_updated);
        let callback_for_save = Rc::clone(&on_profile_updated);
        save_button.connect_clicked(move |_| {
            let display_name = display_name_row_for_save.text().trim().to_string();
            let email = email_row_for_save.text().trim().to_string();
            let current_password_raw = current_password_for_save.text().trim().to_string();

            let payload = UserProfileUpdate {
                email: if email.is_empty() { None } else { Some(email) },
                display_name: if display_name.is_empty() {
                    None
                } else {
                    Some(display_name)
                },
                show_passwords_in_edit: None,
                current_password: if current_password_raw.is_empty() {
                    None
                } else {
                    Some(SecretBox::new(Box::new(current_password_raw.into_bytes())))
                },
            };

            let (save_sender, save_receiver) = tokio::sync::oneshot::channel();
            let runtime_for_task = runtime_for_save.clone();
            let service_for_task = Arc::clone(&service_for_save);
            std::thread::spawn(move || {
                let result = runtime_for_task.block_on(async move {
                    service_for_task.update_user_profile(user_id, payload).await
                });
                let _ = save_sender.send(result);
            });

            let window_for_result = window_for_save.clone();
            let callback_for_result = Rc::clone(&callback_for_save);
            glib::MainContext::default().spawn_local(async move {
                match save_receiver.await {
                    Ok(Ok(user)) => {
                        let label = user
                            .display_name
                            .clone()
                            .filter(|value| !value.trim().is_empty())
                            .unwrap_or(user.username);
                        callback_for_result(label);
                        window_for_result.add_toast(adw::Toast::new("Profil mis à jour"));
                    }
                    Ok(Err(AppError::Authorization(_))) => {
                        window_for_result
                            .add_toast(adw::Toast::new("Mot de passe actuel invalide"));
                    }
                    Ok(Err(AppError::Conflict(_))) => {
                        window_for_result
                            .add_toast(adw::Toast::new("Cet email est déjà utilisé"));
                    }
                    Ok(Err(_)) | Err(_) => {
                        window_for_result
                            .add_toast(adw::Toast::new("Échec de la mise à jour du profil"));
                    }
                }
            });
        });

        let service_for_password_change = Arc::clone(&user_service);
        let runtime_for_password_change = runtime_handle.clone();
        let current_master_password_for_save = current_master_password_row.clone();
        let new_master_password_for_save = new_master_password_row.clone();
        let confirm_master_password_for_save = confirm_master_password_row.clone();
        let window_for_password_change = window.clone();
        let is_changing_for_btn = Rc::clone(&is_changing_password);
        let mkchange_group_for_btn = mkchange_group.clone();
        let security_group_for_btn = security_group.clone();
        let password_save_row_for_btn = password_save_row.clone();
        let step1_spinner_for_btn = step1_spinner.clone();
        let step1_icon_for_btn = step1_icon.clone();
        let step2_spinner_for_btn = step2_spinner.clone();
        let step2_icon_for_btn = step2_icon.clone();
        let step3_spinner_for_btn = step3_spinner.clone();
        let step3_icon_for_btn = step3_icon.clone();
        change_password_button.connect_clicked(move |btn| {
            let current_password_raw = current_master_password_for_save.text().trim().to_string();
            let new_password_raw = new_master_password_for_save.text().trim().to_string();
            let confirm_password_raw = confirm_master_password_for_save.text().trim().to_string();

            if current_password_raw.is_empty()
                || new_password_raw.is_empty()
                || confirm_password_raw.is_empty()
            {
                window_for_password_change
                    .add_toast(adw::Toast::new("Tous les champs mot de passe sont obligatoires"));
                return;
            }

            if new_password_raw != confirm_password_raw {
                window_for_password_change
                    .add_toast(adw::Toast::new("La confirmation ne correspond pas"));
                return;
            }

            let current_password = SecretBox::new(Box::new(current_password_raw.into_bytes()));
            let new_password = SecretBox::new(Box::new(new_password_raw.into_bytes()));

            // Switch to progress view
            btn.set_sensitive(false);
            is_changing_for_btn.set(true);
            security_group_for_btn.set_visible(false);
            mkchange_group_for_btn.set_visible(true);

            // Reset all step icons to pending state
            step1_spinner_for_btn.set_visible(true);
            step1_spinner_for_btn.start();
            step1_icon_for_btn.set_visible(false);

            step2_spinner_for_btn.set_visible(false);
            step2_icon_for_btn.set_icon_name(Some("radio-symbolic"));
            step2_icon_for_btn.remove_css_class("mkchange-step-icon-done");
            step2_icon_for_btn.remove_css_class("mkchange-step-icon-error");
            step2_icon_for_btn.add_css_class("mkchange-step-icon-pending");
            step2_icon_for_btn.set_visible(true);

            step3_spinner_for_btn.set_visible(false);
            step3_icon_for_btn.set_icon_name(Some("radio-symbolic"));
            step3_icon_for_btn.remove_css_class("mkchange-step-icon-done");
            step3_icon_for_btn.remove_css_class("mkchange-step-icon-error");
            step3_icon_for_btn.add_css_class("mkchange-step-icon-pending");
            step3_icon_for_btn.set_visible(true);

            // Heuristic timer: after ~1.5 s mark step1 done and start step2 spinner.
            // The op_done flag prevents this heuristic from overriding actual completion.
            let op_done: Rc<Cell<bool>> = Rc::new(Cell::new(false));
            {
                let op_done_t = Rc::clone(&op_done);
                let s1_sp = step1_spinner_for_btn.clone();
                let s1_ic = step1_icon_for_btn.clone();
                let s2_sp = step2_spinner_for_btn.clone();
                let s2_ic = step2_icon_for_btn.clone();
                glib::timeout_add_local_once(
                    std::time::Duration::from_millis(1500),
                    move || {
                        if op_done_t.get() {
                            return;
                        }
                        s1_sp.stop();
                        s1_sp.set_visible(false);
                        s1_ic.set_icon_name(Some("object-select-symbolic"));
                        s1_ic.remove_css_class("mkchange-step-icon-pending");
                        s1_ic.add_css_class("mkchange-step-icon-done");
                        s1_ic.set_visible(true);
                        s2_ic.set_visible(false);
                        s2_sp.set_visible(true);
                        s2_sp.start();
                    },
                );
            }

            let (password_sender, password_receiver) = tokio::sync::oneshot::channel();
            let runtime_for_task = runtime_for_password_change.clone();
            let service_for_task = Arc::clone(&service_for_password_change);
            std::thread::spawn(move || {
                let result = runtime_for_task.block_on(async move {
                    service_for_task
                        .change_master_password(user_id, current_password, new_password)
                        .await
                });
                let _ = password_sender.send(result);
            });

            let window_for_result = window_for_password_change.clone();
            let current_row_c = current_master_password_for_save.clone();
            let new_row_c = new_master_password_for_save.clone();
            let confirm_row_c = confirm_master_password_for_save.clone();
            let btn_c = btn.clone();
            let is_changing_c = Rc::clone(&is_changing_for_btn);
            let security_group_c = security_group_for_btn.clone();
            let mkchange_group_c = mkchange_group_for_btn.clone();
            let password_save_row_c = password_save_row_for_btn.clone();
            let s1_sp_c = step1_spinner_for_btn.clone();
            let s1_ic_c = step1_icon_for_btn.clone();
            let s2_sp_c = step2_spinner_for_btn.clone();
            let s2_ic_c = step2_icon_for_btn.clone();
            let s3_sp_c = step3_spinner_for_btn.clone();
            let s3_ic_c = step3_icon_for_btn.clone();
            glib::MainContext::default().spawn_local(async move {
                fn step_done(spinner: &gtk4::Spinner, icon: &gtk4::Image) {
                    spinner.stop();
                    spinner.set_visible(false);
                    icon.set_icon_name(Some("object-select-symbolic"));
                    icon.remove_css_class("mkchange-step-icon-pending");
                    icon.remove_css_class("mkchange-step-icon-error");
                    icon.add_css_class("mkchange-step-icon-done");
                    icon.set_visible(true);
                }
                fn step_error(spinner: &gtk4::Spinner, icon: &gtk4::Image) {
                    spinner.stop();
                    spinner.set_visible(false);
                    icon.set_icon_name(Some("dialog-error-symbolic"));
                    icon.remove_css_class("mkchange-step-icon-pending");
                    icon.remove_css_class("mkchange-step-icon-done");
                    icon.add_css_class("mkchange-step-icon-error");
                    icon.set_visible(true);
                }
                fn step_reset(spinner: &gtk4::Spinner, icon: &gtk4::Image) {
                    spinner.stop();
                    spinner.set_visible(false);
                    icon.set_icon_name(Some("radio-symbolic"));
                    icon.remove_css_class("mkchange-step-icon-done");
                    icon.remove_css_class("mkchange-step-icon-error");
                    icon.add_css_class("mkchange-step-icon-pending");
                    icon.set_visible(true);
                }

                op_done.set(true);

                match password_receiver.await {
                    Ok(Ok(())) => {
                        step_done(&s1_sp_c, &s1_ic_c);
                        step_done(&s2_sp_c, &s2_ic_c);
                        // Brief spinner on step 3, then mark it done
                        s3_ic_c.set_visible(false);
                        s3_sp_c.set_visible(true);
                        s3_sp_c.start();
                        glib::timeout_add_local_once(
                            std::time::Duration::from_millis(400),
                            move || {
                                step_done(&s3_sp_c, &s3_ic_c);
                                // After 1.5 s restore the form
                                glib::timeout_add_local_once(
                                    std::time::Duration::from_millis(1500),
                                    move || {
                                        current_row_c.set_text("");
                                        new_row_c.set_text("");
                                        confirm_row_c.set_text("");
                                        mkchange_group_c.set_visible(false);
                                        security_group_c.set_visible(true);
                                        password_save_row_c.grab_focus();
                                        btn_c.set_sensitive(true);
                                        is_changing_c.set(false);
                                        window_for_result
                                            .add_toast(adw::Toast::new("Master key mise à jour"));
                                    },
                                );
                            },
                        );
                    }
                    Ok(Err(AppError::Authorization(_))) => {
                        step_error(&s1_sp_c, &s1_ic_c);
                        // Hold the error state briefly so the user can see it
                        glib::timeout_add_local_once(
                            std::time::Duration::from_millis(900),
                            move || {
                                step_reset(&s1_sp_c, &s1_ic_c);
                                step_reset(&s2_sp_c, &s2_ic_c);
                                step_reset(&s3_sp_c, &s3_ic_c);
                                mkchange_group_c.set_visible(false);
                                security_group_c.set_visible(true);
                                btn_c.set_sensitive(true);
                                is_changing_c.set(false);
                                window_for_result
                                    .add_toast(adw::Toast::new("Mot de passe actuel invalide"));
                            },
                        );
                    }
                    Ok(Err(AppError::Validation(message))) => {
                        step_reset(&s1_sp_c, &s1_ic_c);
                        step_reset(&s2_sp_c, &s2_ic_c);
                        step_reset(&s3_sp_c, &s3_ic_c);
                        mkchange_group_c.set_visible(false);
                        security_group_c.set_visible(true);
                        btn_c.set_sensitive(true);
                        is_changing_c.set(false);
                        window_for_result.add_toast(adw::Toast::new(message.as_str()));
                    }
                    Ok(Err(_)) | Err(_) => {
                        step_reset(&s1_sp_c, &s1_ic_c);
                        step_reset(&s2_sp_c, &s2_ic_c);
                        step_reset(&s3_sp_c, &s3_ic_c);
                        mkchange_group_c.set_visible(false);
                        security_group_c.set_visible(true);
                        btn_c.set_sensitive(true);
                        is_changing_c.set(false);
                        window_for_result
                            .add_toast(adw::Toast::new("Échec du changement de master key"));
                    }
                }
            });
        });

        window.present();
    }
}
