#!/usr/bin/env bash
# =============================================================================
# Master Production Deployment Script for Ubuntu Server (SeaMaster)
# Domain/IP: http://<server-ip>/ (Root Path)
# Target Directory: /opt/seamaster
# Service: seamaster.service (Port 8000)
# =============================================================================
set -euo pipefail

# Visual output colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=====================================================${NC}"
echo -e "${BLUE}           SeaMaster Production Deployer             ${NC}"
echo -e "${BLUE}=====================================================${NC}"

# Check for root / sudo
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}[ERROR] This script must be run as root or with sudo.${NC}"
    echo "Usage: sudo bash deploy/deploy.sh"
    exit 1
fi

SOURCE_DIR="$(pwd)"
TARGET_DIR="/opt/seamaster"

echo -e "${GREEN}[1/8] Installing system dependencies (nginx, python3, pip, venv, sqlite3)...${NC}"
apt-get update -qq
apt-get install -y nginx python3 python3-venv python3-pip rsync curl sqlite3

echo -e "${GREEN}[2/8] Preparing target directory: ${TARGET_DIR}...${NC}"
mkdir -p "${TARGET_DIR}"
mkdir -p "${TARGET_DIR}/instance"

# Copy application files (preserve existing database if already on server)
if [ "${SOURCE_DIR}" != "${TARGET_DIR}" ]; then
    echo "Copying codebase from ${SOURCE_DIR} to ${TARGET_DIR}..."
    rsync -av \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='instance/*.db-wal' \
        --exclude='instance/*.db-shm' \
        "${SOURCE_DIR}/" "${TARGET_DIR}/"
fi

# Check existing database integrity in target
if [ -f "${TARGET_DIR}/instance/seamaster.db" ]; then
    echo "Checking SQLite database integrity in ${TARGET_DIR}/instance/seamaster.db..."
    CHECK_RESULT=$(sqlite3 "${TARGET_DIR}/instance/seamaster.db" "PRAGMA quick_check;" 2>&1 || echo "malformed")
    if [[ "$CHECK_RESULT" != *"ok"* ]]; then
        echo -e "${YELLOW}[WARN] Database file is malformed ($CHECK_RESULT). Backing up and copying clean database...${NC}"
        mv "${TARGET_DIR}/instance/seamaster.db" "${TARGET_DIR}/instance/seamaster.db.corrupt.$(date +%s)"
        rm -f "${TARGET_DIR}/instance/seamaster.db-wal" "${TARGET_DIR}/instance/seamaster.db-shm"
        if [ -f "${SOURCE_DIR}/instance/seamaster.db" ]; then
            cp "${SOURCE_DIR}/instance/seamaster.db" "${TARGET_DIR}/instance/seamaster.db"
        fi
    fi
else
    if [ -f "${SOURCE_DIR}/instance/seamaster.db" ]; then
        cp "${SOURCE_DIR}/instance/seamaster.db" "${TARGET_DIR}/instance/seamaster.db"
    fi
fi

cd "${TARGET_DIR}"

echo -e "${GREEN}[3/8] Setting up Python virtual environment (.venv)...${NC}"
if [ ! -d "${TARGET_DIR}/.venv" ]; then
    python3 -m venv "${TARGET_DIR}/.venv"
fi

echo -e "${GREEN}[4/8] Installing Python dependencies...${NC}"
"${TARGET_DIR}/.venv/bin/pip" install --upgrade pip setuptools wheel -q
"${TARGET_DIR}/.venv/bin/pip" install -r "${TARGET_DIR}/requirements.txt" -q

echo -e "${GREEN}[5/8] Verifying database schema, migrations and initial data...${NC}"
"${TARGET_DIR}/.venv/bin/python" -m flask --app app init-db

echo -e "${GREEN}[6/8] Setting full read/write permissions for Static files and Database...${NC}"
chmod -R 755 "${TARGET_DIR}"
chmod -R a+rX "${TARGET_DIR}/static"
chmod -R 777 "${TARGET_DIR}/instance" || true
chmod 666 "${TARGET_DIR}/instance/"*.db 2>/dev/null || true

echo -e "${GREEN}[7/8] Configuring Systemd Service (seamaster.service)...${NC}"
# Install main systemd service
cp "${TARGET_DIR}/deploy/seamaster.service" /etc/systemd/system/seamaster.service
systemctl daemon-reload
systemctl enable seamaster.service
systemctl restart seamaster.service

echo -e "${GREEN}[8/8] Configuring Nginx Web Server...${NC}"
# Copy Nginx config
cp "${TARGET_DIR}/deploy/nginx-seamaster.conf" /etc/nginx/sites-available/seamaster.conf
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/seamaster.conf /etc/nginx/sites-enabled/seamaster.conf

# Test Nginx configuration
nginx -t
systemctl restart nginx

# Verify local connection
sleep 2
echo -e "${BLUE}=====================================================${NC}"
echo -e "${GREEN}✔ Deployment completed successfully!${NC}"
echo -e "${BLUE}=====================================================${NC}"

# Display service status summary
SERVER_IP=$(hostname -I | awk '{print $1}')
echo -e "Application is now LIVE at: ${GREEN}http://${SERVER_IP}/${NC}"
echo -e "Service Status:"
systemctl status seamaster.service --no-pager | head -n 12
