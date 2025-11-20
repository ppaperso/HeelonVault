#!/bin/bash
# Script d'installation du fichier .desktop pour tous les utilisateurs

set -e

DESKTOP_FILE="password-manager.desktop"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SOURCE_FILE="${SCRIPT_DIR}/${DESKTOP_FILE}"

echo "🚀 Installation du lanceur Password Manager"
echo ""

# Vérifier que le fichier .desktop existe
if [ ! -f "${SOURCE_FILE}" ]; then
    echo "❌ Fichier ${DESKTOP_FILE} introuvable"
    exit 1
fi

# Installation pour l'utilisateur courant
USER_APPS_DIR="${HOME}/.local/share/applications"
mkdir -p "${USER_APPS_DIR}"

echo "📝 Création du fichier de lancement personnalisé..."
# Créer une copie avec le bon chemin absolu
sed "s|Exec=.*|Exec=${SCRIPT_DIR}/run-container.sh|g" "${SOURCE_FILE}" > "${USER_APPS_DIR}/${DESKTOP_FILE}"
chmod +x "${USER_APPS_DIR}/${DESKTOP_FILE}"

echo "✅ Lanceur installé pour ${USER}"
echo "📁 Emplacement: ${USER_APPS_DIR}/${DESKTOP_FILE}"
echo ""
echo "🔄 Mise à jour de la base de données des applications..."
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "${USER_APPS_DIR}" 2>/dev/null || true
fi

echo ""
echo "✅ Installation terminée !"
echo ""
echo "🎯 Le lanceur 'Password Manager' devrait maintenant apparaître"
echo "   dans votre menu d'applications."
echo ""
echo "💡 Pour installer pour tous les utilisateurs:"
echo "   sudo cp ${SOURCE_FILE} /usr/share/applications/"
echo "   sudo sed -i 's|Exec=.*|Exec=${SCRIPT_DIR}/run-container.sh|g' /usr/share/applications/${DESKTOP_FILE}"
