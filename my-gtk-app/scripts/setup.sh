#!/bin/bash

# This script sets up the environment for the GTK application.

# Update package list
sudo apt update

# Install necessary packages for GTK development
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0

# Install pip if not already installed
if ! command -v pip3 &> /dev/null
then
    sudo apt install -y python3-pip
fi

# Install Python dependencies
pip3 install -r requirements.txt

echo "Setup completed successfully."