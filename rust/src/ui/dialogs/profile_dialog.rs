use std::sync::Arc;
use std::rc::Rc;

use gtk4::glib;
use gtk4::prelude::*;
use libadwaita as adw;
use libadwaita::prelude::*;
use secrecy::SecretBox;
use tokio::runtime::Handle;
use tracing::{info, warn};
use uuid::Uuid;

use crate::errors::AppError;
use crate::services::user_service::{UserProfileUpdate, UserService};

pub struct ProfileDialog;

impl ProfileDialog {
    pub fn present<TUser>(
        app: &adw::Application,
        parent: &adw::ApplicationWindow,
        runtime_handle: Handle,
        user_service: Arc<TUser>,
        user_id: Uuid,
        on_profile_updated: impl Fn(String) + 'static,
    ) where
        TUser: UserService + Send + Sync + 'static,
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

        let current_master_password_row = adw::PasswordEntryRow::new();
        current_master_password_row.set_title("Mot de passe actuel");
        current_master_password_row.add_css_class("profile-entry-row");

        let new_master_password_row = adw::PasswordEntryRow::new();
        new_master_password_row.set_title("Nouveau mot de passe");
        new_master_password_row.add_css_class("profile-entry-row");

        let confirm_master_password_row = adw::PasswordEntryRow::new();
        confirm_master_password_row.set_title("Confirmer le nouveau mot de passe");
        confirm_master_password_row.add_css_class("profile-entry-row");

        let password_save_row = adw::ActionRow::new();
        password_save_row.set_title("Mettre à jour la master key");
        let change_password_button = gtk4::Button::with_label("Changer");
        change_password_button.add_css_class("suggested-action");
        password_save_row.add_suffix(&change_password_button);

        security_group.add(&current_master_password_row);
        security_group.add(&new_master_password_row);
        security_group.add(&confirm_master_password_row);
        security_group.add(&password_save_row);
        profile_page.add(&security_group);

        window.add(&profile_page);

        let (load_sender, load_receiver) = tokio::sync::oneshot::channel();
        let service_for_load = Arc::clone(&user_service);
        let runtime_for_load = runtime_handle.clone();
        std::thread::spawn(move || {
            let result = runtime_for_load.block_on(async move { service_for_load.get_user_profile(user_id).await });
            let _ = load_sender.send(result);
        });

        let username_row_for_load = username_row.clone();
        let display_name_row_for_load = display_name_row.clone();
        let email_row_for_load = email_row.clone();
        let window_for_load = window.clone();
        glib::MainContext::default().spawn_local(async move {
            match load_receiver.await {
                Ok(Ok(user)) => {
                    username_row_for_load.set_text(user.username.as_str());
                    display_name_row_for_load.set_text(user.display_name.as_deref().unwrap_or_default());
                    email_row_for_load.set_text(user.email.as_deref().unwrap_or_default());
                }
                Ok(Err(err)) => {
                    warn!("failed to load user profile: {err:?}");
                    let toast = adw::Toast::new("Impossible de charger le profil");
                    window_for_load.add_toast(toast);
                }
                Err(err) => {
                    warn!("failed to receive profile load result: {err:?}");
                    let toast = adw::Toast::new("Impossible de charger le profil");
                    window_for_load.add_toast(toast);
                }
            }
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
        change_password_button.connect_clicked(move |_| {
            let current_password_raw = current_master_password_for_save.text().trim().to_string();
            let new_password_raw = new_master_password_for_save.text().trim().to_string();
            let confirm_password_raw = confirm_master_password_for_save.text().trim().to_string();

            if current_password_raw.is_empty() || new_password_raw.is_empty() || confirm_password_raw.is_empty() {
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
            let current_row_for_result = current_master_password_for_save.clone();
            let new_row_for_result = new_master_password_for_save.clone();
            let confirm_row_for_result = confirm_master_password_for_save.clone();
            glib::MainContext::default().spawn_local(async move {
                match password_receiver.await {
                    Ok(Ok(())) => {
                        current_row_for_result.set_text("");
                        new_row_for_result.set_text("");
                        confirm_row_for_result.set_text("");
                        window_for_result.add_toast(adw::Toast::new("Master key mise à jour"));
                    }
                    Ok(Err(AppError::Authorization(_))) => {
                        window_for_result
                            .add_toast(adw::Toast::new("Mot de passe actuel invalide"));
                    }
                    Ok(Err(AppError::Validation(message))) => {
                        window_for_result.add_toast(adw::Toast::new(message.as_str()));
                    }
                    Ok(Err(_)) | Err(_) => {
                        window_for_result
                            .add_toast(adw::Toast::new("Échec du changement de master key"));
                    }
                }
            });
        });

        window.present();
    }
}
