#!/bin/bash
# Script de test de l'application gestionnaire de mots de passe
# Utilise le venv venv-dev avec accès aux packages système
# Usage: ./test-app.sh [run]
#   sans argument: lance les tests
#   avec "run": lance l'application

set -e

# ⚠️ SÉCURITÉ: Forcer le mode développement pour les tests
export DEV_MODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "${ROOT_DIR}"  # Assure que tous les chemins relatifs sont corrects

VENV_DIR="${ROOT_DIR}/venv-dev"
APP_FILE="${ROOT_DIR}/heelonvault.py"

# Si l'argument est "run", lancer directement l'application
if [ "$1" = "run" ]; then
    exec "${ROOT_DIR}/run-dev.sh"
fi

echo "╔════════════════════════════════════════════════════╗"
echo "║   🧪 TESTS SUR ENVIRONNEMENT DE DÉVELOPPEMENT    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "🔒 Mode DEV activé: DEV_MODE=$DEV_MODE"
echo "📂 Données de test: src/data/"
echo "⚠️  Les données de production ne seront PAS touchées"
echo ""
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

from pathlib import Path
import tempfile
import os

from src.services.auth_service import AuthService
from src.services.password_generator import PasswordGenerator
from src.services.crypto_service import CryptoService
from src.repositories.password_repository import PasswordRepository
from src.services.password_service import PasswordService
from src.models.password_entry import PasswordEntry

with tempfile.TemporaryDirectory() as tmpdir:
    try:
        test_db = Path(tmpdir) / "test_users.db"
        
        print("  🔐 Test AuthService...")
        auth = AuthService(test_db)
        
        # Test création utilisateur
        assert auth.create_user("test_user", "test_password"), "Création utilisateur échoué"
        print("    ✅ Création utilisateur OK")
        
        # Test authentification
        user_info = auth.authenticate("test_user", "test_password")
        assert user_info is not None, "Authentification échoué"
        assert user_info['username'] == "test_user", "Username incorrect"
        print("    ✅ Authentification OK")
        
        # Test auth avec mauvais mot de passe
        assert auth.authenticate("test_user", "wrong_password") is None, "Auth devrait échouer"
        print("    ✅ Rejet mauvais mot de passe OK")
        
        auth.close()
        
        print("  🔑 Test PasswordGenerator...")
        # Test générateur
        pwd = PasswordGenerator.generate(16)
        assert len(pwd) == 16, f"Longueur incorrecte: {len(pwd)}"
        print(f"    ✅ Mot de passe généré: {pwd[:4]}...{pwd[-4:]}")
        
        # Test phrase de passe
        phrase = PasswordGenerator.generate_passphrase(4)
        assert len(phrase.split('-')) >= 4, "Phrase de passe incorrecte"
        print(f"    ✅ Phrase de passe générée: {phrase}")
        
        print("  🔐 Test CryptoService...")
        crypto = CryptoService("master_password")
        encrypted = crypto.encrypt("secret_data")
        assert 'nonce' in encrypted and 'ciphertext' in encrypted, "Chiffrement invalide"
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == "secret_data", "Déchiffrement incorrect"
        print("    ✅ Chiffrement/Déchiffrement OK")

        print("  💾 Test PasswordRepository/Service...")
        test_pwd_db = Path(tmpdir) / "test_passwords.db"
        repository = PasswordRepository(test_pwd_db)
        service = PasswordService(repository, crypto)

        entry = PasswordEntry(
            title="Test Entry",
            username="user@example.com",
            password="my_password",
            url="https://example.com",
            notes="Test notes",
            category="Personnel",
            tags=["tag1", "tag2"],
        )
        entry_id = service.create_entry(entry)
        assert entry_id > 0, "Ajout entrée échoué"
        print("    ✅ Ajout entrée OK")

        fetched = service.get_entry(entry_id)
        assert fetched is not None, "Récupération échouée"
        assert fetched.password == "my_password", "Password incorrect"
        assert fetched.title == "Test Entry", "Title incorrect"
        print("    ✅ Récupération entrée OK")

        entries = service.list_entries()
        assert len(entries) > 0, "Liste vide"
        print("    ✅ Liste entrées OK")

        service.close()
        
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

echo ""
echo "=================================================="
echo "🧪 Tests de protection des données et rotation"
echo "=================================================="
echo ""

# Test des permissions
echo "🔐 Test des permissions des fichiers..."
bash "${ROOT_DIR}/tests/test-data-protection.sh"
if [ $? -ne 0 ]; then
    echo "⚠️  Avertissement: certains tests de protection ont échoué"
fi

echo ""

# Test des sauvegardes et rotation
echo "🔄 Test du service de sauvegarde et rotation..."
python3 -m unittest tests.unit.test_backup_service -v
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Tests de sauvegarde échoués"
    exit 1
fi

echo ""

# Test de rotation spécifique
echo "🔄 Test de rotation des sauvegardes..."
python3 -m unittest tests.unit.test_backup_rotation -v
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Test de rotation échoué"
    exit 1
fi

echo ""
echo "=================================================="
echo "✅ Tous les tests sont réussis!"
echo ""
echo "📊 Résumé des tests:"
echo "   ✅ Syntaxe Python"
echo "   ✅ Imports et dépendances"
echo "   ✅ Tests unitaires de base"
echo "   ✅ Protection des données (permissions 600)"
echo "   ✅ Service de sauvegarde"
echo "   ✅ Rotation des sauvegardes (max 7)"
echo ""
echo "🚀 L'application est prête à être lancée:"
echo "   ./test-app.sh run    # ou ./run-dev.sh"
echo ""
echo "🐋 Pour conteneuriser:"
echo "   ./build-container.sh"
echo "=================================================="
