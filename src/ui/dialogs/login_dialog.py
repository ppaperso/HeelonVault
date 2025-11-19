"""Dialogue de connexion pour un utilisateur."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from src.services.login_attempt_tracker import LoginAttemptTracker


class LoginDialog(Adw.Window):
    """Dialogue de connexion pour un utilisateur spécifique.
    
    Demande le mot de passe maître de l'utilisateur.
    Protégé contre les attaques par force brute.
    """
    
    # Instance partagée du tracker (singleton)
    _tracker = LoginAttemptTracker()
    
    def __init__(self, parent, user_manager, username: str, callback):
        """Initialise le dialogue de connexion.
        
        Args:
            parent: Fenêtre parente
            user_manager: Service d'authentification
            username: Nom de l'utilisateur à authentifier
            callback: Fonction appelée après authentification réussie
        """
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(400, 300)
        self.set_title(f"Connexion - {username}")
        self.user_manager = user_manager
        self.username = username
        self.callback = callback
        self.login_btn = None  # Référence au bouton de connexion
        
        self._build_ui()
        self._check_lockout_status()
    
    def _build_ui(self):
        """Construit l'interface utilisateur."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(40)
        box.set_margin_bottom(40)
        
        # Icône utilisateur
        icon = Gtk.Image.new_from_icon_name("avatar-default-symbolic")
        icon.set_pixel_size(64)
        box.append(icon)
        
        # Nom d'utilisateur
        username_label = Gtk.Label(label=self.username)
        username_label.set_css_classes(['title-2'])
        box.append(username_label)
        
        # Champ mot de passe
        password_label = Gtk.Label(label="Mot de passe maître", xalign=0)
        box.append(password_label)
        
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_show_peek_icon(True)
        self.password_entry.connect("activate", lambda e: self.on_login_clicked(None))
        box.append(self.password_entry)
        
        # Message d'erreur
        self.error_label = Gtk.Label(label="")
        self.error_label.set_css_classes(['error'])
        self.error_label.set_visible(False)
        box.append(self.error_label)
        
        # Boutons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.END)
        
        cancel_btn = Gtk.Button(label="Retour")
        cancel_btn.connect("clicked", lambda x: self.close())
        button_box.append(cancel_btn)
        
        self.login_btn = Gtk.Button(label="Se connecter")
        self.login_btn.set_css_classes(['suggested-action'])
        self.login_btn.connect("clicked", self.on_login_clicked)
        button_box.append(self.login_btn)
        
        box.append(button_box)
        
        self.set_content(box)
        self.password_entry.grab_focus()
    
    def _check_lockout_status(self):
        """Vérifie l'état de verrouillage au démarrage."""
        can_attempt, remaining = self._tracker.check_can_attempt(self.username)
        
        if not can_attempt:
            self._disable_login(remaining)
    
    def _disable_login(self, remaining_seconds: int):
        """Désactive la connexion temporairement.
        
        Args:
            remaining_seconds: Nombre de secondes restantes
        """
        self.login_btn.set_sensitive(False)
        self.password_entry.set_sensitive(False)
        
        if remaining_seconds >= 60:
            minutes = remaining_seconds // 60
            self.show_error(f"🔒 Trop de tentatives échouées. Veuillez patienter {minutes} min")
        else:
            self.show_error(f"⏳ Veuillez patienter {remaining_seconds}s avant de réessayer")
        
        # Démarrer un timer pour réactiver
        GLib.timeout_add_seconds(1, self._update_lockout_timer)
    
    def _update_lockout_timer(self):
        """Met à jour le timer de verrouillage."""
        can_attempt, remaining = self._tracker.check_can_attempt(self.username)
        
        if can_attempt:
            # Réactiver la connexion
            self.login_btn.set_sensitive(True)
            self.password_entry.set_sensitive(True)
            self.error_label.set_visible(False)
            return False  # Arrêter le timer
        else:
            # Mettre à jour le message
            if remaining >= 60:
                minutes = remaining // 60
                self.show_error(f"🔒 Trop de tentatives échouées. Veuillez patienter {minutes} min")
            else:
                self.show_error(f"⏳ Veuillez patienter {remaining}s avant de réessayer")
            return True  # Continuer le timer
    
    def on_login_clicked(self, button):
        """Callback du bouton de connexion.
        
        Authentifie l'utilisateur et appelle le callback si succès.
        Protégé contre les attaques par force brute.
        
        Args:
            button: Bouton cliqué (peut être None si Enter pressé)
        """
        # Vérifier si la tentative est autorisée
        can_attempt, remaining = self._tracker.check_can_attempt(self.username)
        
        if not can_attempt:
            self._disable_login(remaining)
            return
        
        password = self.password_entry.get_text()
        
        if not password:
            self.show_error("Le mot de passe est requis")
            return
        
        user_info = self.user_manager.authenticate(self.username, password)
        
        if user_info:
            # Succès : réinitialiser le compteur
            self._tracker.record_successful_attempt(self.username)
            self.callback(user_info, password)
            
            # Fermer les fenêtres de connexion
            parent = self.get_transient_for()
            self.close()
            if parent:
                parent.close()
        else:
            # Échec : enregistrer la tentative
            self._tracker.record_failed_attempt(self.username)
            
            # Vérifier si un verrouillage est maintenant actif
            can_attempt, remaining = self._tracker.check_can_attempt(self.username)
            
            if not can_attempt:
                self._disable_login(remaining)
            else:
                # Calculer le délai progressif
                info = self._tracker.get_attempt_info(self.username)
                if info and info.failed_attempts > 0:
                    delay = self._tracker._calculate_delay(info.failed_attempts)
                    self.show_error(f"❌ Mot de passe incorrect (prochaine tentative dans {int(delay)}s)")
                else:
                    self.show_error("❌ Mot de passe incorrect")
            
            self.password_entry.set_text("")
            self.password_entry.grab_focus()
    
    def show_error(self, message: str):
        """Affiche un message d'erreur.
        
        Args:
            message: Message à afficher
        """
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
