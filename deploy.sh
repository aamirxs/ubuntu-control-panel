#!/bin/bash

# Ubuntu Control Panel Deployment Script
# For Ubuntu 24.04 LTS

set -e

echo "=== Ubuntu Control Panel Installation ==="
echo "This script will install and configure the Ubuntu Control Panel."
echo "It requires sudo privileges for system configuration."
echo "Press Ctrl+C to cancel or Enter to continue..."
read

# Check if running as root
if [ "$(id -u)" -eq 0 ]; then
    echo "Please do not run this script as root directly."
    echo "The script will use sudo for commands that require elevated permissions."
    exit 1
fi

# Function to print step information
print_step() {
    echo -e "\n\033[1;34m==>\033[0m \033[1m$1\033[0m"
}

# Update system
print_step "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
print_step "Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv nodejs npm mongodb nginx certbot python3-certbot-nginx git

# Create directories
print_step "Creating directories..."
sudo mkdir -p /opt/ubuntu-control-panel
sudo mkdir -p /opt/python_scripts
sudo mkdir -p /var/log/ubuntu-control-panel

# Clone repository
print_step "Cloning repository..."
git clone https://github.com/yourusername/ubuntu-control-panel.git /tmp/ubuntu-control-panel

# Setup backend
print_step "Setting up backend..."
cd /tmp/ubuntu-control-panel
sudo cp -r backend/* /opt/ubuntu-control-panel/
cd /opt/ubuntu-control-panel

# Create virtual environment
sudo python3 -m venv venv
sudo ./venv/bin/pip install --upgrade pip
sudo ./venv/bin/pip install -r requirements.txt

# Create .env file
if [ ! -f .env ]; then
    print_step "Creating .env file..."
    # Generate random secret key
    SECRET_KEY=$(openssl rand -hex 32)
    
    # Generate random admin password
    ADMIN_PASSWORD=$(openssl rand -base64 12)
    
    cat > .env << EOF
# Database configuration
MONGODB_URL=mongodb://localhost:27017
DB_NAME=ubuntucontrolpanel

# Security
SECRET_KEY=$SECRET_KEY

# Admin user
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$ADMIN_PASSWORD
ADMIN_EMAIL=admin@example.com

# Directories
FILES_BASE_DIR=/home
PYTHON_DIR=/opt/python_scripts

# Server configuration
HOST=0.0.0.0
PORT=8000
EOF

    echo "=== IMPORTANT ==="
    echo "Admin username: admin"
    echo "Admin password: $ADMIN_PASSWORD"
    echo "Please note these credentials and change the password after first login."
    echo "================="
fi

# Setup systemd service
print_step "Setting up systemd service..."
cat > /tmp/ubuntu-control-panel.service << EOF
[Unit]
Description=Ubuntu Control Panel
After=network.target mongodb.service

[Service]
User=root
WorkingDirectory=/opt/ubuntu-control-panel
ExecStart=/opt/ubuntu-control-panel/venv/bin/python run.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/ubuntu-control-panel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ubuntu-control-panel.service
sudo systemctl start ubuntu-control-panel.service

# Setup Nginx
print_step "Setting up Nginx..."
cat > /tmp/ubuntu-control-panel-nginx.conf << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo mv /tmp/ubuntu-control-panel-nginx.conf /etc/nginx/sites-available/ubuntu-control-panel
sudo ln -sf /etc/nginx/sites-available/ubuntu-control-panel /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# Configure the firewall
print_step "Configuring firewall..."
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh

echo "=== Installation Complete ==="
echo "Ubuntu Control Panel has been installed and is running."
echo "You can access it at: http://your-server-ip"
echo ""
echo "To setup HTTPS, run:"
echo "sudo certbot --nginx -d your-domain.com"
echo ""
echo "Don't forget to change the default admin password after first login!"

# Cleanup
rm -rf /tmp/ubuntu-control-panel

exit 0 