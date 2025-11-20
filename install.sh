#!/bin/bash
# Script d'installation du Gestionnaire de mots de passe
# Installation locale avec base de données partagée multi-utilisateurs

set -e

echo "🔐 Installation du Gestionnaire de mots de passe"
echo "================================================"
echo ""

# Vérifier les prérequis système
echo "📋 Vérification des prérequis..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé. Installation requise."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Python $PYTHON_VERSION détecté"

# Vérifier les dépendances système
MISSING_DEPS=()

if ! python3 -c "import gi; gi.require_version('Gtk', '4.0')" 2>/dev/null; then
    MISSING_DEPS+=("gtk4 python3-gobject")
fi

if ! python3 -c "import gi; gi.require_version('Adw', '1')" 2>/dev/null; then
    MISSING_DEPS+=("libadwaita")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo ""
    echo "❌ Dépendances manquantes: ${MISSING_DEPS[*]}"
    echo ""
    echo "Installez-les avec:"
    echo "  sudo dnf install -y gtk4 libadwaita python3-gobject python3-cairo"
    exit 1
fi

echo "✅ Toutes les dépendances système sont présentes"

# Créer l'environnement virtuel de PRODUCTION si nécessaire
VENV_DIR="venv-prod"
if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "📦 Création de l'environnement virtuel de production..."
    python3 -m venv "$VENV_DIR"
    echo "✅ Environnement virtuel de production créé: $VENV_DIR/"
fi

# Activer l'environnement virtuel
source "$VENV_DIR/bin/activate"

# Installer les dépendances Python
echo ""
echo "📦 Installation des dépendances Python..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
echo "✅ Dépendances Python installées"

# Créer le répertoire de données partagé
DATA_DIR="/var/lib/passwordmanager-shared"

echo ""
echo "📂 Configuration du répertoire de données partagé..."
echo "   Emplacement: $DATA_DIR"

if [ ! -d "$DATA_DIR" ]; then
    echo "   Création du répertoire (sudo requis)..."
    sudo mkdir -p "$DATA_DIR"
    sudo chown root:users "$DATA_DIR"
    sudo chmod 775 "$DATA_DIR"
    echo "✅ Répertoire créé avec succès"
else
    echo "✅ Répertoire existant"
fi

# Vérifier les permissions
if [ ! -w "$DATA_DIR" ]; then
    echo ""
    echo "⚠️  Vous n'avez pas les droits d'écriture sur $DATA_DIR"
    echo "   Ajout de votre utilisateur au groupe 'users'..."
    sudo usermod -a -G users $USER
    echo "✅ Utilisateur ajouté au groupe 'users'"
    echo ""
    echo "⚠️  IMPORTANT: Vous devez vous déconnecter et reconnecter pour que"
    echo "   les changements de groupe prennent effet, ou exécutez:"
    echo "   newgrp users"
fi

# Installer le lanceur .desktop
echo ""
echo "🚀 Installation du lanceur d'application..."
if [ -f "install-desktop.sh" ]; then
    bash install-desktop.sh
    echo "✅ Lanceur installé"
else
    echo "⚠️  Fichier install-desktop.sh non trouvé"
fi

echo ""
echo "================================================"
echo "✅ Installation terminée avec succès!"
echo ""
echo "📍 Répertoire de données partagé: $DATA_DIR"
echo "   • Base de données partagée entre tous les utilisateurs du système"
echo "   • Chaque utilisateur a ses propres identifiants"
echo "   • Données chiffrées avec AES-256"
echo ""
echo "🚀 Pour lancer l'application:"
echo "   • Depuis le menu Applications → Utilitaires"
echo "   • Ou en ligne de commande: ./run-dev.sh"
echo ""
echo "📖 Documentation: README.md"
echo ""
