#!/bin/bash
# Script d'installation unifié pour le Gestionnaire de mots de passe en production
# Avec logs détaillés et gestion des erreurs

set -e
exec > >(tee -i /tmp/install-heelonvault.log) 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
APP_NAME="heelonvault"
INSTALL_DIR="/opt/$APP_NAME"
VENV_DIR="$INSTALL_DIR/venv"
DATA_DIR="/var/lib/${APP_NAME}-shared"
DESKTOP_FILE="$APP_NAME.desktop"
SYSTEM_APPS_DIR="/usr/share/applications"
USER_APPS_DIR="$HOME/.local/share/applications"
REQUIREMENTS_FILE="$INSTALL_DIR/requirements.txt"
DESKTOP_SOURCE="$INSTALL_DIR/$DESKTOP_FILE"
RUN_SCRIPT="$INSTALL_DIR/run.sh"
ICONS_SOURCE_DIR="$INSTALL_DIR/src/resources/icons/hicolor"
SYSTEM_ICONS_DIR="/usr/share/icons/hicolor"
FILTERED_REQUIREMENTS=""

# Nettoie le fichier temporaire des dépendances python filtrées
cleanup_filtered_requirements() {
    if [ -n "$FILTERED_REQUIREMENTS" ] && [ -f "$FILTERED_REQUIREMENTS" ]; then
        rm -f "$FILTERED_REQUIREMENTS"
    fi
}

trap cleanup_filtered_requirements EXIT

# Prépare la liste des paquets pip (exclut PyGObject, fourni par le système)
filter_pip_requirements() {
    FILTERED_REQUIREMENTS=$(mktemp)
    awk '!/^[[:space:]]*($|#)/ && $0 !~ /PyGObject/ { print }' "$REQUIREMENTS_FILE" > "$FILTERED_REQUIREMENTS"
}

# Fonction pour afficher un message d'erreur et quitter
error_exit() {
    echo "❌ ERREUR: $1" >&2
    echo "   Voir /tmp/install-heelonvault.log pour plus de détails."
    exit 1
}

# Fonction pour vérifier l'existence d'un fichier
check_file() {
    if [ ! -f "$1" ]; then
        error_exit "Fichier $1 introuvable."
    fi
}

# Fonction pour vérifier l'existence d'un répertoire
check_dir() {
    if [ ! -d "$1" ]; then
        error_exit "Répertoire $1 introuvable."
    fi
}

# Copie les fichiers de l'application dans l'emplacement d'installation
copy_application_files() {
    if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
        echo "ℹ️ Le répertoire source est déjà $INSTALL_DIR, aucune copie nécessaire."
        return
    fi

    echo "📦 Déploiement des fichiers de l'application dans $INSTALL_DIR..."
    if command -v rsync &>/dev/null; then
        rsync -a \
            --exclude '.git/' \
            --exclude '.gitignore' \
            --exclude 'venvpwdmanager/' \
            --exclude 'venv/' \
            --exclude 'venv-dev/' \
            --exclude '__pycache__/' \
            --exclude '*/__pycache__/' \
            --exclude '**/__pycache__/' \
            --exclude 'data/' \
            --exclude 'logs/' \
            --exclude '*.pyc' \
            --exclude '.pytest_cache/' \
            --exclude '.vscode/' \
            "$SCRIPT_DIR/" "$INSTALL_DIR/" \
            || error_exit "Impossible de copier les fichiers vers $INSTALL_DIR (rsync)"
    else
        cp -a "$SCRIPT_DIR/." "$INSTALL_DIR/" || error_exit "Impossible de copier les fichiers vers $INSTALL_DIR"
        rm -rf "$INSTALL_DIR/.git" "$INSTALL_DIR/.gitignore" \
            "$INSTALL_DIR/venvpwdmanager" \
            "$INSTALL_DIR/venv" \
            "$INSTALL_DIR/venv-dev" \
            "$INSTALL_DIR/data" \
            "$INSTALL_DIR/logs" \
            "$INSTALL_DIR/__pycache__" "$INSTALL_DIR/src/__pycache__" \
            "$INSTALL_DIR/tests/__pycache__" \
            "$INSTALL_DIR/.pytest_cache" \
            "$INSTALL_DIR/.vscode" > /dev/null 2>&1 || true
        find "$INSTALL_DIR" -name "*.pyc" -delete 2>/dev/null || true
    fi

    echo "✅ Fichiers copiés"
}

# S'assure que l'utilisateur sudo appartient au groupe users
ensure_users_group_membership() {
    if [ -z "$SUDO_USER" ]; then
        return
    fi

    if ! getent group users > /dev/null; then
        echo "⚠️ Groupe users introuvable, les utilisateurs devront avoir des droits d'écriture sur $DATA_DIR manuellement."
        return
    fi

    if id -nG "$SUDO_USER" | grep -qw "users"; then
        return
    fi

    usermod -a -G users "$SUDO_USER" || error_exit "Impossible d'ajouter $SUDO_USER au groupe users"
    echo "✅ $SUDO_USER ajouté au groupe users (déconnexion/reconnexion requise pour prendre effet)"
}

grant_user_acl_on_data_dir() {
    if [ -z "$SUDO_USER" ]; then
        return
    fi

    if ! command -v setfacl >/dev/null 2>&1; then
        echo "ℹ️ Installez le paquet 'acl' pour accorder un accès immédiat sans déconnexion."
        return
    fi

    setfacl -m "u:$SUDO_USER:rwx" "$DATA_DIR" || true
    setfacl -d -m "u:$SUDO_USER:rwx" "$DATA_DIR" || true
    setfacl -d -m "g::rwx" "$DATA_DIR" || true
    
    # Fixer les permissions des fichiers existants créés par root
    find "$DATA_DIR" -type f -user root -exec chmod 664 {} \; 2>/dev/null || true
    
    # Ajouter des ACL utilisateur sur les fichiers DB et salt existants pour accès immédiat
    find "$DATA_DIR" -type f -name "*.db" -exec setfacl -m "u:$SUDO_USER:rw" {} \; 2>/dev/null || true
    find "$DATA_DIR" -type f -name "salt_*.bin" -exec setfacl -m "u:$SUDO_USER:r" {} \; 2>/dev/null || true
    
    echo "✅ Accès immédiat accordé à $SUDO_USER sur $DATA_DIR"
}

# Afficher les informations de début
echo ""
echo "🔐 Installation du Gestionnaire de mots de passe en production"
echo "============================================================"
echo "  • Répertoire d'installation: $INSTALL_DIR"
echo "  • Répertoire de données: $DATA_DIR"
echo "  • Logs: /tmp/install-heelonvault.log"
echo ""

# Vérifier que le script est lancé en root
if [ "$(id -u)" -ne 0 ]; then
    error_exit "Ce script doit être lancé avec sudo."
fi

# Détecter si c'est une mise à jour
if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/heelonvault.py" ]; then
    echo ""
    echo "⚠️  Une installation existante a été détectée dans $INSTALL_DIR"
    echo ""
    if [ -f "$SCRIPT_DIR/update.sh" ]; then
        echo "🔄 Pour une mise à jour sécurisée avec backup automatique, utilisez:"
        echo "   sudo bash update.sh"
        echo ""
        echo "⚠️  Le script install.sh va ÉCRASER l'installation existante sans backup!"
        echo ""
        echo "Continuer quand même avec install.sh (non recommandé)? [o/N]"
        read -r response
        if [[ ! "$response" =~ ^[oO]$ ]]; then
            echo "Installation annulée. Utilisez update.sh pour une mise à jour sécurisée."
            exit 0
        fi
        echo ""
        echo "⚠️  Vous avez choisi de continuer sans backup automatique."
        echo "   Assurez-vous d'avoir sauvegardé vos données manuellement!"
        echo ""
        sleep 3
    else
        echo "⚠️  ATTENTION: Cette opération va écraser l'installation existante."
        echo "   Assurez-vous d'avoir sauvegardé $DATA_DIR avant de continuer!"
        echo ""
        echo "Continuer? [o/N]"
        read -r response
        if [[ ! "$response" =~ ^[oO]$ ]]; then
            echo "Installation annulée."
            exit 0
        fi
    fi
fi

# Vérifier les prérequis système
echo "📋 Vérification des prérequis système..."
if ! command -v python3 &> /dev/null; then
    error_exit "Python 3 n'est pas installé. Installation requise."
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
if [ $? -ne 0 ]; then
    error_exit "Impossible de détecter la version de Python."
fi
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
    error_exit "Dépendances manquantes: ${MISSING_DEPS[*]}. Installez-les avec: sudo dnf install -y ${MISSING_DEPS[*]}"
fi
echo "✅ Toutes les dépendances système sont présentes"

ensure_users_group_membership

# Création du répertoire d'installation
echo ""
echo "📦 Création du répertoire d'installation: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" || error_exit "Impossible de créer $INSTALL_DIR"
copy_application_files
chown -R $SUDO_USER:$SUDO_USER "$INSTALL_DIR" || error_exit "Impossible de définir les permissions pour $INSTALL_DIR"

# Vérifier la présence des fichiers nécessaires
echo ""
echo "📋 Vérification des fichiers nécessaires..."
check_file "$REQUIREMENTS_FILE"
check_file "$DESKTOP_SOURCE"
check_file "$RUN_SCRIPT"
chmod +x "$RUN_SCRIPT"
echo "✅ Tous les fichiers nécessaires sont présents"

# Création de l'environnement virtuel
echo ""
echo "📦 Création de l'environnement virtuel de production..."
python3 -m venv --system-site-packages "$VENV_DIR" || error_exit "Impossible de créer l'environnement virtuel"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip > /dev/null 2>&1 || error_exit "Impossible de mettre à jour pip"
echo "ℹ️ PyGObject (bindings GTK4) est fourni par les paquets système listés précédemment."
filter_pip_requirements
if [ -s "$FILTERED_REQUIREMENTS" ]; then
    pip install -r "$FILTERED_REQUIREMENTS" > /dev/null 2>&1 || error_exit "Impossible d'installer les dépendances Python"
else
    echo "ℹ️ Aucun paquet pip supplémentaire n'est nécessaire."
fi
echo "✅ Dépendances Python installées"

# Création du répertoire de données partagé
echo ""
echo "📂 Création du répertoire de données partagé: $DATA_DIR"
mkdir -p "$DATA_DIR" || error_exit "Impossible de créer $DATA_DIR"
chown root:users "$DATA_DIR" || error_exit "Impossible d'ajuster les propriétaires de $DATA_DIR"
chmod 2775 "$DATA_DIR" || error_exit "Impossible de définir les permissions pour $DATA_DIR"
grant_user_acl_on_data_dir
echo "✅ Répertoire de données partagé créé, permissions et groupe configurés"

# Installation des icônes applicatives (thème hicolor)
echo ""
echo "🎨 Installation des icônes applicatives..."
if [ -d "$ICONS_SOURCE_DIR" ]; then
    mkdir -p "$SYSTEM_ICONS_DIR" || error_exit "Impossible de créer $SYSTEM_ICONS_DIR"
    cp -a "$ICONS_SOURCE_DIR/." "$SYSTEM_ICONS_DIR/" || error_exit "Impossible de copier les icônes hicolor"
    gtk-update-icon-cache -f "$SYSTEM_ICONS_DIR" 2>/dev/null || true
    echo "✅ Icônes installées dans $SYSTEM_ICONS_DIR"
else
    echo "⚠️ Répertoire d'icônes introuvable: $ICONS_SOURCE_DIR"
fi

# Installation du fichier .desktop pour tous les utilisateurs
echo ""
echo "📝 Installation du lanceur pour tous les utilisateurs..."
cp "$DESKTOP_SOURCE" "$SYSTEM_APPS_DIR/" || error_exit "Impossible de copier le fichier .desktop"
sed -i "s|Exec=.*|Exec=$RUN_SCRIPT|g" "$SYSTEM_APPS_DIR/$DESKTOP_FILE" || error_exit "Impossible de modifier le fichier .desktop"
chmod +x "$SYSTEM_APPS_DIR/$DESKTOP_FILE" || error_exit "Impossible de rendre le fichier .desktop exécutable"
update-desktop-database "$SYSTEM_APPS_DIR" 2>/dev/null || true
echo "✅ Lanceur installé pour tous les utilisateurs"

# Vérification de l'installation
echo ""
echo "🔍 Vérification de l'installation..."
if [ -f "$SYSTEM_APPS_DIR/$DESKTOP_FILE" ] && [ -d "$VENV_DIR" ] && [ -d "$DATA_DIR" ]; then
    echo "✅ Installation réussie !"
    echo ""
    echo "🎯 L'application '$APP_NAME' est prête à être utilisée."
    echo "   - Lanceur disponible dans le menu Applications."
    echo "   - Répertoire d'installation: $INSTALL_DIR"
    echo "   - Répertoire de données: $DATA_DIR"
    echo "   - Logs: /tmp/install-heelonvault.log"
else
    error_exit "L'installation a échoué. Vérifiez les erreurs ci-dessus."
fi
