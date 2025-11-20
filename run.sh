#!/bin/bash
# Script de lancement de l'application Password Manager (production)

# Assurer que les fichiers créés sont group-writable
umask 002

source /opt/password-manager/venv/bin/activate
python3 /opt/password-manager/password_manager.py
