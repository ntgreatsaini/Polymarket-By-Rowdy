#!/usr/bin/env bash
# Ubuntu VPS setup script for Polymarket Bot
set -euo pipefail

echo "=== Polymarket Bot VPS Setup ==="

# System updates
sudo apt-get update && sudo apt-get upgrade -y

# Install dependencies
sudo apt-get install -y \
    python3.12 python3.12-venv python3-pip \
    postgresql postgresql-contrib \
    redis-server \
    nginx \
    git curl

# Create app directory
sudo mkdir -p /opt/polymarket-bot
sudo chown "$USER:$USER" /opt/polymarket-bot

# Clone or copy project
echo "Copy project files to /opt/polymarket-bot/"

# Setup Python environment
cd /opt/polymarket-bot
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup PostgreSQL
sudo -u postgres psql -c "CREATE USER polymarket WITH PASSWORD 'your_secure_password';" || true
sudo -u postgres psql -c "CREATE DATABASE polymarket_bot OWNER polymarket;" || true

# Setup Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Copy and enable systemd service
sudo cp deploy/polymarket-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable polymarket-bot

# Setup Nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/polymarket
sudo ln -sf /etc/nginx/sites-available/polymarket /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

echo "=== Setup Complete ==="
echo "1. Edit /opt/polymarket-bot/.env with your API keys"
echo "2. Run: sudo systemctl start polymarket-bot"
echo "3. Check: sudo systemctl status polymarket-bot"
