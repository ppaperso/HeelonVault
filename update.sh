#!/bin/bash
# Script de mise à jour sécurisé pour le Gestionnaire de mots de passe
# - Détection automatique de la source (workspace local)
# - Backup complet en tar.gz
# - Analyse des fichiers modifiés
# - Validation avant application

set -e
exec > >(tee -i /tmp/update-password-manager.log) 2>&1

# Détection automatique du dossier source (là où se trouve ce script)
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
APP_NAME="password-manager"
INSTALL_DIR="/opt/$APP_NAME"
VENV_DIR="$INSTALL_DIR/venv"
DATA_DIR="/var/lib/${APP_NAME}-shared"
BACKUP_ROOT="/var/backups/${APP_NAME}"
BACKUP_FILE=""
MAX_BACKUPS=10

# Fichiers/dossiers à exclure de la copie
EXCLUDE_PATTERNS=(
    "venv"
    "venv-dev"
    "__pycache__"
    ".git"
    ".gitignore"
    "*.pyc"
    "*.pyo"
    ".vscode"
    ".idea"
    "*.log"
    ".DS_Store"
    "export-csv"
    "tests"
    "data"           # Données de développement uniquement
    "logs"
    "update.sh.old"
)

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Fonction pour afficher un message d'erreur et quitter
error_exit() {
    echo -e "${RED}❌ ERREUR: $1${NC}" >&2
    echo "   Voir /tmp/update-password-manager.log pour plus de détails."
    if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
        echo ""
        echo -e "${YELLOW}⚠️  Un backup complet a été créé: $BACKUP_FILE${NC}"
        echo ""
        echo "   Pour restaurer en cas de problème:"
        echo "   1. Arrêter l'application:"
        echo "      sudo pkill -f password_manager.py"
        echo ""
        echo "   2. Restaurer le backup:"
        echo "      sudo rm -rf $INSTALL_DIR"
        echo "      sudo mkdir -p $INSTALL_DIR"
        echo "      sudo tar -xzf $BACKUP_FILE -C /"
        echo ""
        echo "   3. Relancer l'application"
    fi
    exit 1
}

# Fonction pour afficher un titre
print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Fonction pour nettoyer les anciens backups
cleanup_old_backups() {
    if [ -d "$BACKUP_ROOT" ]; then
        cd "$BACKUP_ROOT"
        BACKUP_COUNT=$(ls -1 *.tar.gz 2>/dev/null | wc -l)
        if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
            echo "🗑️  Nettoyage des anciens backups (conservation des $MAX_BACKUPS plus récents)..."
            ls -t *.tar.gz | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -f
            echo "   ✅ Nettoyage effectué"
        fi
    fi
}

# Fonction pour construire la liste des exclusions pour rsync
build_exclude_args() {
    local exclude_args=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        exclude_args="$exclude_args --exclude=$pattern"
    done
    echo "$exclude_args"
}

# Fonction pour comparer les fichiers et lister les différences
compare_directories() {
    local source="$1"
    local target="$2"
    local temp_file=$(mktemp)
    local count=0
    
    echo "📊 Analyse des différences entre:"
    echo "   Source: $source"
    echo "   Cible:  $target"
    echo ""
    
    # Construire les arguments d'exclusion pour rsync
    local exclude_args=$(build_exclude_args)
    
    # Utiliser rsync en mode dry-run pour détecter les changements
    rsync -avin --delete $exclude_args "$source/" "$target/" > "$temp_file" 2>&1 || true
    
    # Analyser les résultats
    local files_to_update=$(grep -E "^>f" "$temp_file" | wc -l)
    local files_to_delete=$(grep -E "^deleting" "$temp_file" | wc -l)
    local dirs_to_create=$(grep -E "^cd" "$temp_file" | wc -l)
    
    echo "📋 Résumé des changements:"
    echo "   • Fichiers à mettre à jour: $files_to_update"
    echo "   • Fichiers à supprimer: $files_to_delete"
    echo "   • Nouveaux répertoires: $dirs_to_create"
    
    if [ "$files_to_update" -eq 0 ] && [ "$files_to_delete" -eq 0 ] && [ "$dirs_to_create" -eq 0 ]; then
        echo ""
        echo -e "${YELLOW}⚠️  Aucune différence détectée. Aucune mise à jour nécessaire.${NC}"
        rm -f "$temp_file"
        return 1
    fi
    
    echo ""
    echo "📝 Détails des modifications:"
    echo ""
    
    # Afficher les fichiers modifiés (limité aux 30 premiers)
    local modified_count=$(grep -E "^>f" "$temp_file" | wc -l)
    if [ "$modified_count" -gt 0 ]; then
        echo -e "${CYAN}Fichiers modifiés/nouveaux:${NC}"
        grep -E "^>f" "$temp_file" | head -30 | sed 's/^>f[^ ]* /   ✏️  /'
        if [ "$modified_count" -gt 30 ]; then
            echo "   ... et $((modified_count - 30)) autres fichiers"
        fi
        echo ""
    fi
    
    # Afficher les fichiers à supprimer
    local deleted_count=$(grep -E "^deleting" "$temp_file" | wc -l)
    if [ "$deleted_count" -gt 0 ]; then
        echo -e "${CYAN}Fichiers à supprimer:${NC}"
        grep -E "^deleting" "$temp_file" | head -30 | sed 's/^deleting /   🗑️  /'
        if [ "$deleted_count" -gt 30 ]; then
            echo "   ... et $((deleted_count - 30)) autres fichiers"
        fi
        echo ""
    fi
    
    rm -f "$temp_file"
    return 0
}

# Fonction pour créer le backup tar.gz
create_backup() {
    local version="$1"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_name="${APP_NAME}_${version}_${timestamp}.tar.gz"
    
    BACKUP_FILE="$BACKUP_ROOT/$backup_name"
    
    echo "💾 Création du backup complet en tar.gz..."
    echo "   📦 Fichier: $backup_name"
    echo ""
    
    mkdir -p "$BACKUP_ROOT" || error_exit "Impossible de créer $BACKUP_ROOT"
    
    # Calculer la taille totale
    local total_size=$(du -sh "$INSTALL_DIR" 2>/dev/null | cut -f1)
    echo "   📊 Taille du dossier d'installation: $total_size"
    
    # Créer l'archive tar.gz avec barre de progression
    echo "   🔄 Compression en cours..."
    cd /
    tar -czf "$BACKUP_FILE" \
        --exclude="$INSTALL_DIR/venv" \
        --exclude="$INSTALL_DIR/__pycache__" \
        --exclude="$INSTALL_DIR/*.pyc" \
        "opt/$APP_NAME" \
        "var/lib/${APP_NAME}-shared" 2>/dev/null || error_exit "Échec de la création du backup"
    
    # Vérifier le backup
    local backup_size=$(du -sh "$BACKUP_FILE" | cut -f1)
    echo "   ✅ Backup créé avec succès"
    echo "   📦 Taille du backup: $backup_size"
    echo "   📂 Emplacement: $BACKUP_FILE"
    
    # Tester l'intégrité du tar.gz
    echo "   🔍 Vérification de l'intégrité..."
    if tar -tzf "$BACKUP_FILE" > /dev/null 2>&1; then
        echo "   ✅ Intégrité vérifiée"
    else
        error_exit "Le backup est corrompu!"
    fi
}

# Fonction pour appliquer la mise à jour
apply_update() {
    local source="$1"
    local target="$2"
    
    echo "🔄 Application de la mise à jour..."
    echo ""
    
    # Construire les arguments d'exclusion
    local exclude_args=$(build_exclude_args)
    
    # Copier les fichiers avec rsync
    echo "   📂 Copie des fichiers..."
    rsync -av --delete $exclude_args "$source/" "$target/" || error_exit "Échec de la copie des fichiers"
    
    echo ""
    echo "   ✅ Fichiers copiés avec succès"
}

# Fonction pour mettre à jour le venv
update_venv() {
    echo "🐍 Mise à jour de l'environnement virtuel Python..."
    echo ""
    
    # Supprimer l'ancien venv
    if [ -d "$VENV_DIR" ]; then
        echo "   🗑️  Suppression de l'ancien venv..."
        rm -rf "$VENV_DIR"
    fi
    
    # Créer un nouveau venv
    echo "   🔧 Création du nouveau venv..."
    python3 -m venv --system-site-packages "$VENV_DIR" || error_exit "Échec de la création du venv"
    
    # Installer les dépendances
    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        echo "   📦 Installation des dépendances..."
        
        # Filtrer PyGObject (déjà installé via apt)
        local temp_req=$(mktemp)
        grep -v "PyGObject" "$INSTALL_DIR/requirements.txt" > "$temp_req" || true
        
        "$VENV_DIR/bin/pip" install --quiet --upgrade pip
        "$VENV_DIR/bin/pip" install --quiet -r "$temp_req" || error_exit "Échec de l'installation des dépendances"
        
        rm -f "$temp_req"
        echo "   ✅ Dépendances installées"
    fi
}

# Fonction pour mettre à jour les permissions et ACL
update_permissions() {
    echo "🔐 Mise à jour des permissions..."
    echo ""
    
    # Permissions pour le dossier d'installation
    chown -R root:root "$INSTALL_DIR"
    chmod -R 755 "$INSTALL_DIR"
    
    # Scripts exécutables
    if [ -f "$INSTALL_DIR/run.sh" ]; then
        chmod 755 "$INSTALL_DIR/run.sh"
    fi
    
    # Permissions pour les données (SANS écraser les ACL)
    if [ -d "$DATA_DIR" ]; then
        chown -R root:root "$DATA_DIR"
        chmod 750 "$DATA_DIR"
        
        # NE PAS utiliser chmod sur les fichiers sensibles car cela écrase les ACL
        # Les ACL sont gérées par install.sh et doivent être préservées
        
        # Si des nouveaux fichiers ont été créés, fixer les permissions de base
        find "$DATA_DIR" -type f -user root -exec chmod 664 {} \; 2>/dev/null || true
        
        # Réappliquer les ACL si SUDO_USER est défini
        if [ -n "$SUDO_USER" ] && command -v setfacl >/dev/null 2>&1; then
            echo "   🔧 Restauration des ACL pour $SUDO_USER..."
            setfacl -m "u:$SUDO_USER:rwx" "$DATA_DIR" 2>/dev/null || true
            find "$DATA_DIR" -type f -name "*.db" -exec setfacl -m "u:$SUDO_USER:rw" {} \; 2>/dev/null || true
            find "$DATA_DIR" -type f -name "salt_*.bin" -exec setfacl -m "u:$SUDO_USER:r" {} \; 2>/dev/null || true
        fi
    fi
    
    echo "   ✅ Permissions mises à jour"
}

# Fonction pour arrêter l'application
stop_application() {
    echo "⏹️  Arrêt de l'application en cours..."
    
    # Méthode 1: systemd
    if systemctl is-active --quiet password-manager 2>/dev/null; then
        systemctl stop password-manager
        echo "   ✅ Service arrêté via systemd"
        return
    fi
    
    # Méthode 2: pkill
    if pkill -f password_manager.py 2>/dev/null; then
        sleep 2
        echo "   ✅ Processus arrêté via pkill"
        return
    fi
    
    echo "   ℹ️  Aucune instance en cours d'exécution"
}

# Fonction pour afficher le résumé final
print_summary() {
    local old_version="$1"
    local new_version="$2"
    local backup_file="$3"
    
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║             ✅ MISE À JOUR RÉUSSIE !                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "📊 Résumé de la mise à jour:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Version précédente    : $old_version"
    echo "  Version installée     : $new_version"
    echo "  Backup créé           : $(basename "$backup_file")"
    echo "  Emplacement           : $backup_file"
    echo "  Logs                  : /tmp/update-password-manager.log"
    echo ""
    echo "🎯 L'application peut maintenant être relancée:"
    echo "   • Via le menu Applications"
    echo "   • Ou avec: $INSTALL_DIR/run.sh"
    echo ""
    echo "💾 En cas de problème, restaurez le backup:"
    echo "   sudo pkill -f password_manager.py"
    echo "   sudo rm -rf $INSTALL_DIR"
    echo "   sudo mkdir -p $INSTALL_DIR"
    echo "   sudo tar -xzf $backup_file -C /"
    echo ""
}

#═══════════════════════════════════════════════════════════════════
# DÉBUT DU SCRIPT PRINCIPAL
#═══════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                              ║"
echo "║   🔄 MISE À JOUR DU GESTIONNAIRE DE MOTS DE PASSE           ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  📂 Dossier source: $SOURCE_DIR"
echo "  📂 Installation: $INSTALL_DIR"
echo "  📂 Données: $DATA_DIR"
echo "  📂 Backups: $BACKUP_ROOT"
echo "  📝 Logs: /tmp/update-password-manager.log"
echo ""

# ═══════════════════════════════════════════════════════════════
# 1. VÉRIFICATIONS PRÉLIMINAIRES
# ═══════════════════════════════════════════════════════════════

print_header "🔍 Vérifications préliminaires"

# Vérifier que le script est lancé en root
if [ "$(id -u)" -ne 0 ]; then
    error_exit "Ce script doit être lancé avec sudo."
fi
echo "✅ Droits administrateur vérifiés"

# Vérifier que l'application est installée
if [ ! -d "$INSTALL_DIR" ]; then
    error_exit "L'application n'est pas installée dans $INSTALL_DIR. Utilisez install.sh pour l'installation initiale."
fi
echo "✅ Application installée détectée"

# Vérifier que les données existent
if [ ! -d "$DATA_DIR" ]; then
    error_exit "Le répertoire de données $DATA_DIR n'existe pas. Installation corrompue?"
fi
echo "✅ Répertoire de données présent"

# Vérifier que le dossier source contient bien l'application
if [ ! -f "$SOURCE_DIR/password_manager.py" ]; then
    error_exit "Le dossier source ne contient pas password_manager.py. Êtes-vous dans le bon répertoire?"
fi
echo "✅ Dossier source valide"

# ═══════════════════════════════════════════════════════════════
# 2. DÉTECTION DES VERSIONS
# ═══════════════════════════════════════════════════════════════

print_header "📊 Détection des versions"

# Version actuelle
CURRENT_VERSION="inconnue"
if [ -f "$INSTALL_DIR/src/version.py" ]; then
    CURRENT_VERSION=$(python3 -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); from src.version import __version__; print(__version__)" 2>/dev/null || echo "inconnue")
fi
echo "Version actuelle: $CURRENT_VERSION"

# Nouvelle version
NEW_VERSION="inconnue"
if [ -f "$SOURCE_DIR/src/version.py" ]; then
    NEW_VERSION=$(python3 -c "import sys; sys.path.insert(0, '$SOURCE_DIR'); from src.version import __version__; print(__version__)" 2>/dev/null || echo "inconnue")
fi
echo "Nouvelle version: $NEW_VERSION"

# Comparer les versions
if [ "$CURRENT_VERSION" = "$NEW_VERSION" ] && [ "$CURRENT_VERSION" != "inconnue" ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Même version détectée ($CURRENT_VERSION)${NC}"
    echo ""
    read -p "Continuer quand même la mise à jour? [o/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[oO]$ ]]; then
        echo "Mise à jour annulée."
        exit 0
    fi
fi

# ═══════════════════════════════════════════════════════════════
# 3. ANALYSE DES DIFFÉRENCES
# ═══════════════════════════════════════════════════════════════

print_header "🔍 Analyse des fichiers à mettre à jour"

if ! compare_directories "$SOURCE_DIR" "$INSTALL_DIR"; then
    echo ""
    echo "Aucune mise à jour nécessaire. Fin du script."
    exit 0
fi

# ═══════════════════════════════════════════════════════════════
# 4. DEMANDE DE CONFIRMATION
# ═══════════════════════════════════════════════════════════════

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}⚠️  ATTENTION: Une mise à jour va être effectuée${NC}"
echo ""
echo "   1. Un backup complet sera créé en tar.gz"
echo "   2. Les fichiers listés ci-dessus seront mis à jour"
echo "   3. L'environnement virtuel Python sera recréé"
echo "   4. Les permissions seront mises à jour"
echo ""
read -p "Voulez-vous effectuer la mise à jour? [o/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[oO]$ ]]; then
    echo "Mise à jour annulée."
    exit 0
fi

# ═══════════════════════════════════════════════════════════════
# 5. CRÉATION DU BACKUP
# ═══════════════════════════════════════════════════════════════

print_header "💾 Création du backup complet"

create_backup "$CURRENT_VERSION"

echo ""
echo -e "${GREEN}✅ Backup créé avec succès!${NC}"
echo ""
read -p "Continuer avec la mise à jour? [o/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[oO]$ ]]; then
    echo "Mise à jour annulée. Le backup est conservé."
    exit 0
fi

# ═══════════════════════════════════════════════════════════════
# 6. ARRÊT DE L'APPLICATION
# ═══════════════════════════════════════════════════════════════

print_header "⏹️  Arrêt de l'application"

stop_application

# ═══════════════════════════════════════════════════════════════
# 7. APPLICATION DE LA MISE À JOUR
# ═══════════════════════════════════════════════════════════════

print_header "🔄 Application de la mise à jour"

apply_update "$SOURCE_DIR" "$INSTALL_DIR"

# ═══════════════════════════════════════════════════════════════
# 8. MISE À JOUR DU VENV
# ═══════════════════════════════════════════════════════════════

print_header "🐍 Environnement virtuel Python"

update_venv

# ═══════════════════════════════════════════════════════════════
# 9. MISE À JOUR DES PERMISSIONS
# ═══════════════════════════════════════════════════════════════

print_header "🔐 Permissions"

update_permissions

# ═══════════════════════════════════════════════════════════════
# 10. NETTOYAGE DES ANCIENS BACKUPS
# ═══════════════════════════════════════════════════════════════

print_header "🗑️  Nettoyage"

cleanup_old_backups

# ═══════════════════════════════════════════════════════════════
# 11. VÉRIFICATION FINALE
# ═══════════════════════════════════════════════════════════════

print_header "✅ Vérification finale"

# Vérifier la version installée
INSTALLED_VERSION="inconnue"
if [ -f "$INSTALL_DIR/src/version.py" ]; then
    INSTALLED_VERSION=$(python3 -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); from src.version import __version__; print(__version__)" 2>/dev/null || echo "inconnue")
fi

if [ "$INSTALLED_VERSION" = "$NEW_VERSION" ]; then
    echo "✅ Version correctement installée: $INSTALLED_VERSION"
else
    echo "⚠️  Version installée: $INSTALLED_VERSION (attendue: $NEW_VERSION)"
fi

# Vérifier que les données sont toujours présentes
DATA_FILE_COUNT=$(find "$DATA_DIR" -type f 2>/dev/null | wc -l)
echo "✅ Fichiers de données présents: $DATA_FILE_COUNT"

# ═══════════════════════════════════════════════════════════════
# 12. RÉSUMÉ FINAL
# ═══════════════════════════════════════════════════════════════

print_summary "$CURRENT_VERSION" "$INSTALLED_VERSION" "$BACKUP_FILE"

exit 0
