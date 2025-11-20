#!/bin/bash
# Script de test de l'application gestionnaire de mots de passe
# Utilise le venv venv-dev avec accès aux packages système
# Usage: ./test-app.sh [run]
#   sans argument: lance les tests
#   avec "run": lance l'application

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv-dev"
APP_FILE="${SCRIPT_DIR}/password_manager.py"

# Si l'argument est "run", lancer directement l'application
if [ "$1" = "run" ]; then
    exec "${SCRIPT_DIR}/run-dev.sh"
fi

echo "🧪 Script de test du gestionnaire de mots de passe"
echo "=================================================="
echo ""

# Vérifier que le venv existe
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Erreur: Le venv 'venv-dev' n'existe pas"
    echo ""
    echo "Création du venv avec accès aux packages système..."
    python3 -m venv --system-site-packages "$VENV_DIR"
    echo "✅ venv créé avec --system-site-packages"
fi

# Activer le venv
echo "📦 Activation du venv venv-dev..."
source "${VENV_DIR}/bin/activate"

# Vérifier Python
echo "🐍 Version Python: $(python --version)"
echo ""

# Vérifier et installer les dépendances
echo "📋 Vérification des dépendances Python..."

if ! python -c "import cryptography" 2>/dev/null; then
    echo "📦 Installation de cryptography..."
    pip install cryptography
    echo "✅ cryptography installé"
else
    echo "✅ cryptography déjà installé"
fi

# Vérifier les packages système GTK4
echo ""
echo "🎨 Vérification de GTK4 et libadwaita..."
if rpm -q gtk4 &>/dev/null; then
    echo "✅ GTK4 installé: $(rpm -q gtk4)"
else
    echo "❌ GTK4 n'est pas installé"
    echo "   Installation requise: sudo dnf install gtk4"
fi

if rpm -q libadwaita &>/dev/null; then
    echo "✅ libadwaita installé: $(rpm -q libadwaita)"
else
    echo "❌ libadwaita n'est pas installé"
    echo "   Installation requise: sudo dnf install libadwaita"
fi

if rpm -q python3-gobject &>/dev/null; then
    echo "✅ python3-gobject installé: $(rpm -q python3-gobject)"
else
    echo "❌ python3-gobject n'est pas installé"
    echo "   Installation requise: sudo dnf install python3-gobject"
fi

echo ""

# Test de syntaxe Python
echo "🔍 Vérification de la syntaxe Python..."
if python -m py_compile "$APP_FILE"; then
    echo "✅ Syntaxe Python correcte"
else
    echo "❌ Erreur de syntaxe dans $APP_FILE"
    exit 1
fi

echo ""

# Test des imports
echo "🔍 Test des imports Python..."
python << 'EOF'
import sys
errors = []

try:
    import gi
    print("✅ gi importé")
except ImportError as e:
    errors.append(f"❌ gi: {e}")

try:
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, GLib, Gio
    print("✅ GTK4 et Adwaita importés")
except Exception as e:
    errors.append(f"❌ GTK4/Adwaita: {e}")

try:
    import sqlite3
    print("✅ sqlite3 importé")
except ImportError as e:
    errors.append(f"❌ sqlite3: {e}")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    print("✅ cryptography importé")
except ImportError as e:
    errors.append(f"❌ cryptography: {e}")

if errors:
    print("\n⚠️  Erreurs détectées:")
    for error in errors:
        print(f"   {error}")
    sys.exit(1)
else:
    print("\n✅ Tous les imports sont OK")
EOF

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Certaines dépendances sont manquantes"
    echo ""
    echo "📝 Pour installer les dépendances manquantes:"
    echo "   sudo dnf install python3-gobject gtk4 libadwaita"
    echo "   pip install cryptography"
    exit 1
fi

echo ""

# Afficher les informations de l'environnement
echo "📊 Informations de l'environnement:"
echo "   Workspace: $SCRIPT_DIR"
echo "   Venv: $VENV_DIR"
echo "   Python: $(which python)"
echo "   Pip: $(which pip)"
echo ""

# Test du code spécifique
echo "🧪 Test des composants principaux..."
python << 'EOF'
import sys
sys.path.insert(0, '.')

# Import des classes principales
exec(open('password_manager.py').read())

# Test UserManager
from pathlib import Path
import tempfile
import os

with tempfile.TemporaryDirectory() as tmpdir:
    try:
        test_db = Path(tmpdir) / "test_users.db"
        
        print("  🔐 Test UserManager...")
        um = UserManager(test_db)
        
        # Test création utilisateur
        assert um.create_user("test_user", "test_password"), "Création utilisateur échoué"
        print("    ✅ Création utilisateur OK")
        
        # Test authentification
        user_info = um.authenticate("test_user", "test_password")
        assert user_info is not None, "Authentification échoué"
        assert user_info['username'] == "test_user", "Username incorrect"
        print("    ✅ Authentification OK")
        
        # Test auth avec mauvais mot de passe
        assert um.authenticate("test_user", "wrong_password") is None, "Auth devrait échouer"
        print("    ✅ Rejet mauvais mot de passe OK")
        
        um.close()
        
        print("  🔑 Test PasswordGenerator...")
        # Test générateur
        pwd = PasswordGenerator.generate(16)
        assert len(pwd) == 16, f"Longueur incorrecte: {len(pwd)}"
        print(f"    ✅ Mot de passe généré: {pwd[:4]}...{pwd[-4:]}")
        
        # Test phrase de passe
        phrase = PasswordGenerator.generate_passphrase(4)
        assert len(phrase.split('-')) >= 4, "Phrase de passe incorrecte"
        print(f"    ✅ Phrase de passe générée: {phrase}")
        
        print("  🔐 Test PasswordCrypto...")
        # Test chiffrement
        crypto = PasswordCrypto("master_password")
        encrypted = crypto.encrypt("secret_data")
        assert 'nonce' in encrypted, "Nonce manquant"
        assert 'ciphertext' in encrypted, "Ciphertext manquant"
        print("    ✅ Chiffrement OK")
        
        # Test déchiffrement
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == "secret_data", "Déchiffrement incorrect"
        print("    ✅ Déchiffrement OK")
        
        print("  💾 Test PasswordDatabase...")
        # Test database
        test_pwd_db = Path(tmpdir) / "test_passwords.db"
        db = PasswordDatabase(test_pwd_db, crypto)
        
        # Test ajout entrée
        entry_id = db.add_entry(
            "Test Entry",
            "user@example.com",
            "my_password",
            "https://example.com",
            "Test notes",
            "Personnel",
            ["tag1", "tag2"]
        )
        assert entry_id > 0, "Ajout entrée échoué"
        print("    ✅ Ajout entrée OK")
        
        # Test récupération
        entry = db.get_entry(entry_id)
        assert entry is not None, "Récupération échoué"
        assert entry['password'] == "my_password", "Password incorrect"
        assert entry['title'] == "Test Entry", "Title incorrect"
        print("    ✅ Récupération entrée OK")
        
        # Test liste
        entries = db.get_all_entries()
        assert len(entries) > 0, "Liste vide"
        print("    ✅ Liste entrées OK")
        
        db.close()
        
        print("\n✅ Tous les tests unitaires passent!")
        print("")
    except Exception as e:
        print(f"\n❌ Erreur lors des tests: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Certains tests ont échoué"
    exit 1
fi

echo "=================================================="
echo "✅ Tous les tests sont réussis!"
echo ""
echo "🚀 L'application est prête à être lancée:"
echo "   ./test-app.sh run    # ou ./run-dev.sh"
echo ""
echo "🐋 Pour conteneuriser:"
echo "   ./build-container.sh"
echo "=================================================="
