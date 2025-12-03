#!/usr/bin/env python3
"""
Native Messaging Host pour l'intégration navigateur
Communication sécurisée entre l'extension et l'application GTK4
"""

import sys
import os
import json
import struct
import logging
import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List

# Détection du mode (DEV ou PROD)
DEV_MODE = os.environ.get('DEV_MODE', '0') == '1'

# Configuration des chemins selon le mode
if DEV_MODE:
    APP_DIR = Path(__file__).parent.parent  # Remonte au dossier principal
    DATA_DIR = APP_DIR / 'src' / 'data'
    LOG_FILE = APP_DIR / 'logs' / 'native_host_dev.log'
else:
    APP_DIR = Path(__file__).parent.parent
    DATA_DIR = APP_DIR / 'data'
    LOG_FILE = Path.home() / '.local/share/passwordmanager/native_host.log'

# Créer le répertoire de logs si nécessaire
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Configuration du logging
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info(f"Native Host démarré en mode {'DEV' if DEV_MODE else 'PROD'}")
logger.info(f"Répertoire de données: {DATA_DIR}")

class NativeMessagingHost:
    """Native Messaging Host pour communication navigateur <-> application"""
    
    def __init__(self):
        self.session_token = secrets.token_urlsafe(32)
        self.allowed_origins = [
            'chrome-extension://[EXTENSION_ID]/',
            'moz-extension://[EXTENSION_ID]/'
        ]
        self.data_dir = DATA_DIR
        self.dev_mode = DEV_MODE
        logger.info(f"Native Messaging Host initialisé (mode={'DEV' if DEV_MODE else 'PROD'})")
    
    def read_message(self) -> Optional[Dict[str, Any]]:
        """Lit un message depuis stdin (format native messaging)
        
        Format: 4 bytes (longueur) + JSON
        
        Returns:
            dict: Message décodé ou None si erreur
        """
        try:
            # Lire la longueur du message (4 bytes, little-endian)
            text_length_bytes = sys.stdin.buffer.read(4)
            
            if len(text_length_bytes) == 0:
                logger.info("Fin du stream stdin")
                return None
            
            text_length = struct.unpack('I', text_length_bytes)[0]
            
            # Lire le message JSON
            text = sys.stdin.buffer.read(text_length).decode('utf-8')
            message = json.loads(text)
            
            logger.debug(f"Message reçu: {message.get('action', 'unknown')}")
            return message
            
        except struct.error as e:
            logger.error(f"Erreur décodage longueur: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Erreur décodage JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur lecture message: {e}")
            return None
    
    def send_message(self, message: Dict[str, Any]) -> bool:
        """Envoie un message vers stdout (format native messaging)
        
        Args:
            message: Dictionnaire à envoyer
            
        Returns:
            bool: True si succès
        """
        try:
            encoded_message = json.dumps(message).encode('utf-8')
            encoded_length = struct.pack('I', len(encoded_message))
            
            sys.stdout.buffer.write(encoded_length)
            sys.stdout.buffer.write(encoded_message)
            sys.stdout.buffer.flush()
            
            logger.debug(f"Message envoyé: {message.get('action', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi message: {e}")
            return False
    
    def validate_message(self, message: Dict[str, Any]) -> tuple[bool, str]:
        """Valide un message reçu
        
        Args:
            message: Message à valider
            
        Returns:
            tuple: (valide, message_erreur)
        """
        if not isinstance(message, dict):
            return False, "Message n'est pas un dictionnaire"
        
        if 'action' not in message:
            return False, "Champ 'action' manquant"
        
        allowed_actions = [
            'ping',
            'search_credentials',
            'get_credentials',
            'save_credentials',
            'generate_password',
            'check_status'
        ]
        
        if message['action'] not in allowed_actions:
            return False, f"Action non autorisée: {message['action']}"
        
        return True, ""
    
    def handle_ping(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Répond à un ping
        
        Args:
            message: Message ping
            
        Returns:
            dict: Réponse pong
        """
        return {
            'action': 'pong',
            'status': 'success',
            'version': '0.3.0-beta',
            'session': self.session_token
        }
    
    def handle_check_status(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Vérifie le statut de l'application
        
        Returns:
            dict: Statut de l'application
        """
        # TODO: Vérifier si l'application GTK4 est lancée
        # TODO: Vérifier si un utilisateur est connecté
        
        return {
            'action': 'status_response',
            'status': 'success',
            'app_running': False,  # À implémenter
            'user_authenticated': False,  # À implémenter
            'session': self.session_token
        }
    
    def _get_passwords_db(self, username: str = 'admin') -> Optional[Path]:
        """Retourne le chemin de la base de données d'un utilisateur"""
        db_path = self.data_dir / f'passwords_{username}.db'
        if db_path.exists():
            return db_path
        return None
    
    def _search_in_database(self, url: str, show_all: bool = False) -> List[Dict[str, Any]]:
        """Recherche dans la base de données réelle"""
        # Pour l'instant, on utilise l'utilisateur admin
        # TODO: Gérer l'authentification multi-utilisateur
        db_path = self._get_passwords_db('admin')
        
        if not db_path or not db_path.exists():
            logger.warning(f"Base de données non trouvée: {db_path}")
            return []
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Si show_all ou URL vide, retourner TOUS les credentials
            if show_all or not url:
                cursor.execute('''
                    SELECT id, title, username, url, category
                    FROM passwords
                    ORDER BY title
                ''')
                logger.info("Récupération de TOUS les credentials")
            else:
                # Extraire le domaine de l'URL
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc or parsed.path
                
                # Rechercher les entrées correspondantes
                cursor.execute('''
                    SELECT id, title, username, url, category
                    FROM passwords
                    WHERE url LIKE ? OR title LIKE ?
                    ORDER BY title
                ''', (f'%{domain}%', f'%{domain}%'))
                logger.info(f"Recherche pour domaine: {domain}")
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row[0],
                    'title': row[1],
                    'username': row[2],
                    'url': row[3],
                    'category': row[4]
                })
            
            conn.close()
            logger.info(f"Trouvé {len(results)} entrée(s)")
            return results
            
        except Exception as e:
            logger.error(f"Erreur recherche dans DB: {e}", exc_info=True)
            return []
    
    def handle_search_credentials(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Recherche des identifiants pour une URL
        
        Args:
            message: Message avec 'url' et optionnel 'username', 'showAll'
            
        Returns:
            dict: Liste des identifiants trouvés
        """
        url = message.get('url', '')
        username = message.get('username')
        show_all = message.get('showAll', False)
        
        logger.info(f"Recherche identifiants - URL: {url}, showAll: {show_all}")
        
        # Rechercher dans la base de données réelle
        credentials = self._search_in_database(url, show_all=show_all)
        
        return {
            'action': 'search_response',
            'status': 'success',
            'url': url,
            'credentials': credentials
        }
    
    def handle_get_credentials(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Récupère les identifiants complets par ID
        
        Args:
            message: Message avec 'entry_id'
            
        Returns:
            dict: Identifiants complets (déchiffrés)
        """
        entry_id = message.get('entry_id')
        
        if not entry_id:
            return {
                'action': 'get_response',
                'status': 'error',
                'error': 'entry_id manquant'
            }
        
        # TODO: Communiquer avec l'application GTK4
        # TODO: Demander autorisation utilisateur
        # TODO: Retourner les identifiants déchiffrés
        
        logger.info(f"Récupération identifiants ID: {entry_id}")
        
        # TODO: Implémenter la récupération réelle depuis la base
        return {
            'action': 'get_response',
            'status': 'success',
            'entry_id': entry_id,
            'username': 'utilisateur@example.com',
            'password': 'MotDePasseTest123!'  # À implémenter: récupération sécurisée
        }
    
    def handle_save_credentials(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Sauvegarde de nouveaux identifiants
        
        Args:
            message: Message avec 'url', 'username', 'password'
            
        Returns:
            dict: Confirmation de sauvegarde
        """
        url = message.get('url', '')
        username = message.get('username', '')
        password = message.get('password', '')
        
        if not url or not password:
            return {
                'action': 'save_response',
                'status': 'error',
                'error': 'URL ou mot de passe manquant'
            }
        
        # TODO: Communiquer avec l'application GTK4
        # TODO: Demander confirmation utilisateur
        # TODO: Sauvegarder dans la base de données
        
        logger.info(f"Demande sauvegarde pour: {url}")
        
        # TODO: Implémenter la sauvegarde réelle dans la base
        return {
            'action': 'save_response',
            'status': 'success',
            'url': url
        }
    
    def handle_generate_password(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Génère un mot de passe
        
        Args:
            message: Options de génération (length, etc.)
            
        Returns:
            dict: Mot de passe généré
        """
        # TODO: Utiliser PasswordGenerator de l'application
        
        import string
        length = message.get('length', 16)
        
        # Génération simple pour le moment
        chars = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(secrets.choice(chars) for _ in range(length))
        
        return {
            'action': 'generate_response',
            'status': 'success',
            'password': password
        }
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Traite un message et retourne la réponse
        
        Args:
            message: Message à traiter
            
        Returns:
            dict: Réponse
        """
        valid, error = self.validate_message(message)
        if not valid:
            logger.warning(f"Message invalide: {error}")
            return {
                'status': 'error',
                'error': error
            }
        
        action = message['action']
        
        handlers = {
            'ping': self.handle_ping,
            'check_status': self.handle_check_status,
            'search_credentials': self.handle_search_credentials,
            'get_credentials': self.handle_get_credentials,
            'save_credentials': self.handle_save_credentials,
            'generate_password': self.handle_generate_password
        }
        
        handler = handlers.get(action)
        if handler:
            return handler(message)
        
        return {
            'status': 'error',
            'error': f"Handler non trouvé pour: {action}"
        }
    
    def run(self):
        """Boucle principale du native host"""
        logger.info("Démarrage Native Messaging Host")
        
        try:
            while True:
                message = self.read_message()
                
                if message is None:
                    break
                
                response = self.process_message(message)
                
                if not self.send_message(response):
                    logger.error("Échec envoi réponse")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Interruption clavier")
        except Exception as e:
            logger.error(f"Erreur fatale: {e}", exc_info=True)
        finally:
            logger.info("Arrêt Native Messaging Host")

def main():
    """Point d'entrée principal"""
    host = NativeMessagingHost()
    host.run()

if __name__ == '__main__':
    main()
