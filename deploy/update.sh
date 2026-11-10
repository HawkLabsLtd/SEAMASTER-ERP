#!/usr/bin/env bash
# =============================================================================
# Quick Update Script for Ubuntu Server (SeaMaster)
# Run when code files have been updated
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

TARGET_DIR="/opt/seamaster"

if [ ! -d "${TARGET_DIR}" ]; then
    echo -e "${RED}[ERROR] Target directory ${TARGET_DIR} not found. Run 'sudo bash deploy/deploy.sh' first.${NC}"
    exit 1
fi

cd "${TARGET_DIR}"

echo -e "${GREEN}[1/4] Updating dependencies...${NC}"
"${TARGET_DIR}/.venv/bin/pip" install --upgrade pip -q
"${TARGET_DIR}/.venv/bin/pip" install -r "${TARGET_DIR}/requirements.txt" -q

echo -e "${GREEN}[2/4] Verifying database integrity, schema & permissions...${NC}"
if [ -f "${TARGET_DIR}/instance/seamaster.db" ]; then
    CHECK_RESULT=$(sqlite3 "${TARGET_DIR}/instance/seamaster.db" "PRAGMA quick_check;" 2>&1 || echo "malformed")
    if [[ "$CHECK_RESULT" != *"ok"* ]]; then
        echo -e "${YELLOW}[WARN] Malformed SQLite database detected. Recreating cleanly...${NC}"
        mv "${TARGET_DIR}/instance/seamaster.db" "${TARGET_DIR}/instance/seamaster.db.corrupt.$(date +%s)"
        rm -f "${TARGET_DIR}/instance/seamaster.db-wal" "${TARGET_DIR}/instance/seamaster.db-shm"
    fi
fi

"${TARGET_DIR}/.venv/bin/python" -m flask --app app init-db

echo -e "${GREEN}[3/4] Ensuring static and instance file permissions & Nginx config...${NC}"
chmod -R 755 "${TARGET_DIR}"
chmod -R a+rX "${TARGET_DIR}/static"
chmod -R 777 "${TARGET_DIR}/instance" || true
chmod 666 "${TARGET_DIR}/instance/"*.db 2>/dev/null || true

# Update and enforce Nginx config
cp "${TARGET_DIR}/deploy/nginx-seamaster.conf" /etc/nginx/sites-available/seamaster.conf
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/seamaster.conf /etc/nginx/sites-enabled/seamaster.conf

echo -e "${GREEN}[4/4] Restarting Seamaster and Nginx services...${NC}"
systemctl daemon-reload
systemctl restart seamaster.service
nginx -t && systemctl restart nginx

SERVER_IP=$(hostname -I | awk '{print $1}')
echo -e "${BLUE}=====================================================${NC}"
echo -e "${GREEN}✔ Update complete! App is live at: http://${SERVER_IP}/${NC}"
echo -e "${BLUE}=====================================================${NC}"
