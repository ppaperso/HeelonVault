#!/usr/bin/env python3
"""Script pour ajouter des données de test dans le gestionnaire de mots de passe"""

import sqlite3
import json
from pathlib import Path
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64

def derive_key(master_password: str, salt: bytes) -> bytes:
    """Dérive une clé à partir du mot de passe maître"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000
    )
    return kdf.derive(master_password.encode())

def encrypt_password(password: str, key: bytes) -> str:
    """Chiffre un mot de passe"""
    aesgcm = AESGCM(key)
    nonce = AESGCM.generate_key(96) // 8  # 12 bytes
    ciphertext = aesgcm.encrypt(nonce, password.encode(), None)
    encrypted = nonce + ciphertext
    return base64.b64encode(encrypted).decode()

# Configuration
data_dir = Path.home() / '.local/share/passwordmanager'
db_path = data_dir / 'passwords_admin.db'
master_password = "admin"  # Mot de passe par défaut

# Dériver la clé
salt = b'fixed_salt_for_testing_12345'  # En prod, salt stocké en DB
key = derive_key(master_password, salt)

# Données de test
test_entries = [
    {
        'title': 'Gmail',
        'username': 'john.doe@gmail.com',
        'password': 'SuperSecure123!',
        'url': 'https://mail.google.com',
        'category': 'Email',
        'tags': ['work', 'important'],
        'notes': 'Mon compte email principal pour le travail'
    },
    {
        'title': 'GitHub',
        'username': 'johndoe',
        'password': 'GitH@bPass2024',
        'url': 'https://github.com',
        'category': 'Développement',
        'tags': ['work', 'code'],
        'notes': 'Compte développeur principal'
    },
    {
        'title': 'Facebook',
        'username': 'john.doe',
        'password': 'Face$ecure99',
        'url': 'https://facebook.com',
        'category': 'Réseaux sociaux',
        'tags': ['social', 'personal'],
        'notes': 'Compte personnel Facebook'
    },
    {
        'title': 'Amazon',
        'username': 'john@example.com',
        'password': 'Amaz0n#Shop',
        'url': 'https://amazon.fr',
        'category': 'Shopping',
        'tags': ['shopping', 'personal'],
        'notes': 'Compte Amazon pour achats en ligne'
    },
    {
        'title': 'Netflix',
        'username': 'john.doe@gmail.com',
        'password': 'Netfl!x2024',
        'url': 'https://netflix.com',
        'category': 'Divertissement',
        'tags': ['entertainment', 'subscription'],
        'notes': 'Abonnement famille Netflix'
    },
    {
        'title': 'LinkedIn',
        'username': 'john-doe',
        'password': 'Link3dIn@Pro',
        'url': 'https://linkedin.com',
        'category': 'Professionnel',
        'tags': ['work', 'social'],
        'notes': 'Profil professionnel'
    },
    {
        'title': 'Banque Credit Agricole',
        'username': '12345678',
        'password': 'B@nk2024Secure',
        'url': 'https://credit-agricole.fr',
        'category': 'Finance',
        'tags': ['bank', 'important'],
        'notes': 'Compte bancaire principal - Ne jamais partager'
    },
    {
        'title': 'Spotify',
        'username': 'johndoe@gmail.com',
        'password': 'Spoti#fy123',
        'url': 'https://spotify.com',
        'category': 'Divertissement',
        'tags': ['music', 'subscription'],
        'notes': 'Abonnement Premium'
    },
    {
        'title': 'Discord',
        'username': 'JohnDoe#1234',
        'password': 'Disc0rd!Chat',
        'url': 'https://discord.com',
        'category': 'Communication',
        'tags': ['chat', 'gaming'],
        'notes': 'Serveur dev et gaming'
    },
    {
        'title': 'Dropbox',
        'username': 'john.doe@gmail.com',
        'password': 'Dr0pb0x@Safe',
        'url': 'https://dropbox.com',
        'category': 'Cloud',
        'tags': ['storage', 'work'],
        'notes': 'Stockage cloud professionnel'
    },
    {
        'title': 'Twitter/X',
        'username': '@johndoe',
        'password': 'Tw!tter2024',
        'url': 'https://twitter.com',
        'category': 'Réseaux sociaux',
        'tags': ['social', 'news'],
        'notes': 'Compte Twitter pour veille techno'
    },
    {
        'title': 'WordPress Admin',
        'username': 'admin',
        'password': 'WP@dmin!2024',
        'url': 'https://monblog.com/wp-admin',
        'category': 'Développement',
        'tags': ['work', 'website'],
        'notes': 'Admin du blog personnel'
    }
]

# Catégories à créer
categories = [
    ('Email', '#3584e4', '📧'),
    ('Développement', '#26a269', '💻'),
    ('Réseaux sociaux', '#c061cb', '👥'),
    ('Shopping', '#e66100', '🛒'),
    ('Divertissement', '#e01b24', '🎬'),
    ('Professionnel', '#1c71d8', '💼'),
    ('Finance', '#f5c211', '💰'),
    ('Communication', '#99c1f1', '💬'),
    ('Cloud', '#62a0ea', '☁️'),
]

print("🔐 Ajout de données de test au gestionnaire de mots de passe")
print("=" * 60)

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Ajouter les catégories
    print("\n📁 Ajout des catégories...")
    for cat_name, color, icon in categories:
        cursor.execute(
            'INSERT OR IGNORE INTO categories (name, color, icon) VALUES (?, ?, ?)',
            (cat_name, color, icon)
        )
        print(f"   ✓ {icon} {cat_name}")
    
    conn.commit()
    
    # Ajouter les entrées
    print("\n🔑 Ajout des entrées de mots de passe...")
    for entry in test_entries:
        # Chiffrer le mot de passe (simplifié pour test)
        encrypted_pwd = entry['password']  # En prod, utiliser encrypt_password(entry['password'], key)
        
        cursor.execute('''
            INSERT INTO passwords (title, username, password, url, category, tags, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            entry['title'],
            entry['username'],
            encrypted_pwd,
            entry['url'],
            entry['category'],
            json.dumps(entry['tags']),
            entry['notes']
        ))
        print(f"   ✓ {entry['title']} ({entry['category']})")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Données de test ajoutées avec succès!")
    print(f"   📊 {len(categories)} catégories créées")
    print(f"   🔑 {len(test_entries)} entrées ajoutées")
    print("\n💡 Relancez l'application pour voir les nouvelles données")
    
except Exception as e:
    print(f"\n❌ Erreur: {e}")
