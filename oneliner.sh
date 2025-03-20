#!/bin/bash

# Ubuntu Control Panel One-Line Installer
# This script downloads and runs the deployment script

set -e

# Print banner
echo "========================================"
echo "Ubuntu Control Panel - One-Line Installer"
echo "For Ubuntu 24.04 LTS"
echo "========================================"

# Check if running on Ubuntu
if [ ! -f /etc/lsb-release ] || ! grep -q "Ubuntu" /etc/lsb-release; then
    echo "This script is designed for Ubuntu. Exiting."
    exit 1
fi

# Download and run the installation script
echo "Downloading installation script..."
curl -sSL https://raw.githubusercontent.com/yourusername/ubuntu-control-panel/main/deploy.sh -o /tmp/ubuntu-control-panel-deploy.sh
chmod +x /tmp/ubuntu-control-panel-deploy.sh

echo "Starting installation..."
/tmp/ubuntu-control-panel-deploy.sh

# Clean up
rm -f /tmp/ubuntu-control-panel-deploy.sh

exit 0 