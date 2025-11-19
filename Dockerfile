# Gestionnaire de mots de passe - Container image
# Base: RHEL 9 UBI avec Python 3.12
FROM registry.access.redhat.com/ubi9/python-312:latest

# Métadonnées
LABEL maintainer="Password Manager Team"
LABEL description="Gestionnaire de mots de passe sécurisé avec GTK4"
LABEL version="1.0"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/opt/app-root/src/password-manager

# Passer en root pour installer les dépendances système
USER root

# Installer les dépendances GTK4, libadwaita et autres outils nécessaires
RUN dnf update -y && \
    dnf install -y \
        gtk4 \
        libadwaita \
        python3-gobject \
        gobject-introspection \
        cairo-gobject \
        cairo-gobject-devel \
        gtk4-devel \
        libadwaita-devel \
        python3-cairo \
        dbus-x11 \
        xorg-x11-server-utils \
        mesa-dri-drivers \
    && dnf clean all && \
    rm -rf /var/cache/dnf

# Créer le répertoire de l'application
WORKDIR ${APP_HOME}

# Copier les fichiers de dépendances Python
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY password_manager.py .
COPY README.md .

# Créer le répertoire pour les données persistantes
RUN mkdir -p /data && \
    chmod 755 /data

# Revenir à l'utilisateur non-root pour la sécurité
USER 1001

# Volume pour les données persistantes
VOLUME ["/data"]

# Variables d'environnement pour le runtime
ENV DISPLAY=:0 \
    XDG_RUNTIME_DIR=/tmp/runtime-dir \
    HOME=/opt/app-root/src

# Point d'entrée
ENTRYPOINT ["python3", "password_manager.py"]
