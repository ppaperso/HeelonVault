"""
Service de chiffrement/déchiffrement des mots de passe.
"""
import secrets
import base64
from typing import Dict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


class CryptoService:
    """Gestion du chiffrement/déchiffrement avec AES-256-GCM."""
    
    def __init__(self, master_password: str, salt: bytes = None):
        """Initialise le service de chiffrement.
        
        Args:
            master_password: Mot de passe maître pour dériver la clé
            salt: Salt pour PBKDF2 (généré si None)
        """
        if salt is None:
            salt = secrets.token_bytes(32)
        self.salt = salt
        
        # Dérivation de clé avec PBKDF2-HMAC-SHA256
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600000,
            backend=default_backend()
        )
        self.key = kdf.derive(master_password.encode())
        self.cipher = AESGCM(self.key)
    
    def encrypt(self, plaintext: str) -> Dict[str, str]:
        """Chiffre un texte avec AES-256-GCM.
        
        Args:
            plaintext: Texte en clair à chiffrer
            
        Returns:
            dict: Dictionnaire avec 'nonce' et 'ciphertext' encodés en base64
        """
        nonce = secrets.token_bytes(12)
        ciphertext = self.cipher.encrypt(nonce, plaintext.encode(), None)
        
        return {
            'nonce': base64.b64encode(nonce).decode(),
            'ciphertext': base64.b64encode(ciphertext).decode()
        }
    
    def decrypt(self, encrypted_data: Dict[str, str]) -> str:
        """Déchiffre un texte.
        
        Args:
            encrypted_data: Dictionnaire avec 'nonce' et 'ciphertext'
            
        Returns:
            str: Texte déchiffré
            
        Raises:
            ValueError: Si le déchiffrement échoue
        """
        nonce = base64.b64decode(encrypted_data['nonce'])
        ciphertext = base64.b64decode(encrypted_data['ciphertext'])
        plaintext = self.cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode()
