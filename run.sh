#!/bin/bash
# Script de lancement de l'application HeelonVault (production)

# Assurer que les fichiers créés sont group-writable
umask 002

source /opt/heelonvault/venv/bin/activate
python3 /opt/heelonvault/heelonvault.py
