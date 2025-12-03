#!/bin/bash
# Script récapitulatif - Affiche toutes les commandes utiles

cat << 'EOF'

╔═══════════════════════════════════════════════════════════════╗
║           GUIDE RAPIDE - Extension Firefox DEV/PROD          ║
╚═══════════════════════════════════════════════════════════════╝

📦 INSTALLATION
═══════════════════════════════════════════════════════════════

# Mode Développement (utilise src/data/)
cd browser_integration
./install_dev.sh

# Mode Production (utilise data/)
cd browser_integration
./install_prod.sh

🧪 TESTS
═══════════════════════════════════════════════════════════════

# Tester le native host DEV
python3 browser_integration/test_dev_communication.py

# Tester le native host PROD
python3 browser_integration/test_direct_communication.py

# Voir les données DEV
python3 -c "
import sqlite3
conn = sqlite3.connect('src/data/passwords_admin.db')
cursor = conn.cursor()
cursor.execute('SELECT title, username FROM passwords')
for row in cursor.fetchall():
    print(f'{row[0]} - {row[1]}')
"

📋 LOGS
═══════════════════════════════════════════════════════════════

# Logs DEV
tail -f logs/native_host_dev.log

# Logs PROD
tail -f ~/.local/share/passwordmanager/native_host.log

# Nettoyer les logs
> logs/native_host_dev.log
> ~/.local/share/passwordmanager/native_host.log

🔧 FIREFOX
═══════════════════════════════════════════════════════════════

# Ouvrir about:debugging
firefox about:debugging#/runtime/this-firefox

# Charger extension DEV
# → Charger module temporaire
# → Sélectionner: firefox_extension_dev/manifest.json

# Charger extension PROD
# → Charger module temporaire
# → Sélectionner: firefox_extension/manifest.json

# Recharger après modification
# → Trouver l'extension dans about:debugging
# → Cliquer "Recharger"

🔍 VÉRIFICATIONS
═══════════════════════════════════════════════════════════════

# Vérifier les manifests native-messaging
ls -la ~/.mozilla/native-messaging-hosts/
cat ~/.mozilla/native-messaging-hosts/com.passwordmanager.native.dev.json
cat ~/.mozilla/native-messaging-hosts/com.passwordmanager.native.json

# Vérifier les wrappers
ls -la browser_integration/native_host_wrapper*.sh

# Vérifier les extensions
ls -d browser_integration/firefox_extension*

# Test rapide du native host
echo '{"action":"ping"}' | python3 -c '
import sys, json, struct
msg = sys.stdin.read()
data = json.dumps(json.loads(msg)).encode("utf-8")
sys.stdout.buffer.write(struct.pack("I", len(data)))
sys.stdout.buffer.write(data)
' | browser_integration/native_host_wrapper_dev.sh

🛠️  MAINTENANCE
═══════════════════════════════════════════════════════════════

# Synchroniser DEV → PROD (après tests validés)
cd browser_integration
cp firefox_extension_dev/{background,content,popup}.js firefox_extension/
cp firefox_extension_dev/popup.{html,css} firefox_extension/

# Vérifier que background.js utilise le bon native host
grep "connectNative" firefox_extension/background.js
# PROD doit avoir: "com.passwordmanager.native"
# DEV doit avoir: "com.passwordmanager.native.dev"

# Re-packager pour signature
./package_for_signing.sh

📊 STRUCTURE
═══════════════════════════════════════════════════════════════

browser_integration/
├── native_host.py              # Native host intelligent (DEV/PROD)
├── native_host_wrapper.sh      # Wrapper PROD (DEV_MODE=0)
├── native_host_wrapper_dev.sh  # Wrapper DEV (DEV_MODE=1)
├── install_dev.sh              # Installer version DEV
├── install_prod.sh             # Installer version PROD
├── test_dev_communication.py   # Tests base DEV
├── test_direct_communication.py# Tests base PROD
├── firefox_extension/          # Extension PROD
│   ├── manifest.json           # ID: password-manager@example.com
│   ├── background.js           # Native: com.passwordmanager.native
│   └── ...
└── firefox_extension_dev/      # Extension DEV
    ├── manifest.json           # ID: password-manager-dev@example.com
    ├── background.js           # Native: com.passwordmanager.native.dev
    └── ...

🎯 WORKFLOW
═══════════════════════════════════════════════════════════════

1. Développement
   └─> ./install_dev.sh
   └─> Charger dans Firefox
   └─> Tester sur src/data/
   └─> Modifier le code
   └─> Recharger dans Firefox

2. Validation
   └─> python3 test_dev_communication.py
   └─> Vérifier les logs
   └─> Tester dans navigateur

3. Déploiement
   └─> Copier DEV → PROD
   └─> ./install_prod.sh
   └─> ./package_for_signing.sh
   └─> ./sign_extension.sh
   └─> Installer .xpi

📚 DOCUMENTATION
═══════════════════════════════════════════════════════════════

browser_integration/DEV_PROD_SOLUTION.md - Solution complète
browser_integration/DEBUGGING_GUIDE.md - Guide de débogage
browser_integration/SIGNING_GUIDE.md - Signature Mozilla
browser_integration/PERMANENT_EXTENSION.md - Installation permanente

🆘 PROBLÈMES COURANTS
═══════════════════════════════════════════════════════════════

❌ "Not connected to native host"
   → Vérifier: ~/.mozilla/native-messaging-hosts/
   → Relancer: ./install_dev.sh ou ./install_prod.sh

❌ "Pas de credentials"
   → Vérifier: python3 test_dev_communication.py
   → Logs: tail -f logs/native_host_dev.log

❌ Extension ne se charge pas
   → Vérifier manifest.json
   → Console Firefox: Ctrl+Shift+J

❌ Mauvaise base de données
   → DEV utilise: src/data/passwords_admin.db
   → PROD utilise: data/passwords_admin.db
   → Vérifier: grep DEV_MODE native_host_wrapper*.sh

🎉 SUCCÈS
═══════════════════════════════════════════════════════════════

✅ Extension DEV chargée → Badge [DEV] orange visible
✅ Popup ouvert → Credentials affichés
✅ Clic sur credential → Copie réussie
✅ Auto-fill → Formulaire rempli automatiquement

EOF
