#!/bin/bash
# =============================================================================
# Procurement API - LXC Setup Script for Proxmox
# =============================================================================
# This script sets up the application inside an Ubuntu 24.04 LXC container
# 
# Prerequisites:
# 1. Create LXC container in Proxmox:
#    - Template: ubuntu-24.04-standard
#    - CPU: 2 cores
#    - RAM: 2GB (minimum)
#    - Disk: 20GB
#    - Network: DHCP or static IP
#
# 2. SSH into the container and run this script as root
#
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} Procurement API - LXC Setup${NC}"
echo -e "${GREEN}========================================${NC}"

# =============================================================================
# CONFIGURATION
# =============================================================================

APP_USER="procurement"
APP_DIR="/opt/procurement-api"
DB_NAME="procurement"
DB_USER="procurement"
DB_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_API_KEY=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

# =============================================================================
# SYSTEM UPDATES
# =============================================================================

echo -e "\n${YELLOW}[1/7] Updating system packages...${NC}"
apt-get update
apt-get upgrade -y
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    nginx \
    curl \
    git \
    libmagic1 \
    libpq-dev \
    build-essential

# =============================================================================
# POSTGRESQL SETUP
# =============================================================================

echo -e "\n${YELLOW}[2/7] Setting up PostgreSQL...${NC}"

# Start PostgreSQL
systemctl enable postgresql
systemctl start postgresql

# Create database and user
postgres psql <<EOF
CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
\c ${DB_NAME}
GRANT ALL ON SCHEMA public TO ${DB_USER};
EOF

echo -e "${GREEN}PostgreSQL configured${NC}"

# =============================================================================
# APPLICATION USER
# =============================================================================

echo -e "\n${YELLOW}[3/7] Creating application user...${NC}"

# Create user if doesn't exist
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -d /opt/procurement -s /bin/bash $APP_USER
fi

# =============================================================================
# APPLICATION SETUP
# =============================================================================

echo -e "\n${YELLOW}[4/7] Setting up application...${NC}"

# Create directory structure
mkdir -p $APP_DIR
mkdir -p $APP_DIR/uploads
mkdir -p $APP_DIR/logs

# Copy application files (assumes you've uploaded them or cloned repo)
# If cloning from git:
# git clone https://your-repo.git $APP_DIR

# Create virtual environment
python3 -m venv $APP_DIR/venv
source $APP_DIR/venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install wheel
pip install \
    fastapi \
    uvicorn[standard] \
    gunicorn \
    sqlalchemy \
    psycopg2-binary \
    alembic \
    pydantic \
    pydantic-settings \
    python-dotenv \
    python-jose[cryptography] \
    passlib[bcrypt] \
    python-multipart \
    aiofiles \
    python-magic \
    python-dateutil \
    openpyxl

# =============================================================================
# CONFIGURATION FILE
# =============================================================================

echo -e "\n${YELLOW}[5/7] Creating configuration...${NC}"

cat > $APP_DIR/.env <<EOF
# Procurement API Configuration
# Generated: $(date)

APP_NAME="Procurement API"
APP_VERSION="1.0.0"
DEBUG=false

# Database
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}

# File Storage
UPLOAD_DIR=${APP_DIR}/uploads
MAX_UPLOAD_SIZE_MB=25
ALLOWED_EXTENSIONS=pdf,doc,docx,xls,xlsx,png,jpg,jpeg,csv

# Security
SECRET_KEY=${SECRET_KEY}
API_KEYS=${ADMIN_API_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
EOF

chmod 600 $APP_DIR/.env

# =============================================================================
# SYSTEMD SERVICE
# =============================================================================

echo -e "\n${YELLOW}[6/7] Creating systemd service...${NC}"

cat > /etc/systemd/system/procurement-api.service <<EOF
[Unit]
Description=Procurement API
After=network.target postgresql.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${APP_DIR}/uploads ${APP_DIR}/logs

[Install]
WantedBy=multi-user.target
EOF

# =============================================================================
# NGINX CONFIGURATION
# =============================================================================

echo -e "\n${YELLOW}[7/7] Configuring Nginx...${NC}"

cat > /etc/nginx/sites-available/procurement-api <<EOF
server {
    listen 80;
    server_name _;  # Change to your domain/IP
    
    client_max_body_size 25M;
    
    # API
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support (if needed later)
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health check (no auth required)
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
EOF

# Enable site
ln -sf /etc/nginx/sites-available/procurement-api /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx config
nginx -t

# =============================================================================
# SET PERMISSIONS & START SERVICES
# =============================================================================

chown -R $APP_USER:$APP_USER $APP_DIR

# Enable and start services
systemctl daemon-reload
systemctl enable procurement-api
systemctl enable nginx

# Start nginx
systemctl restart nginx

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN} Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Next steps:"
echo -e "1. Copy your application code to: ${YELLOW}${APP_DIR}/app/${NC}"
echo -e "2. Start the service: ${YELLOW}systemctl start procurement-api${NC}"
echo -e "3. Check status: ${YELLOW}systemctl status procurement-api${NC}"
echo -e "4. View logs: ${YELLOW}journalctl -u procurement-api -f${NC}"
echo ""
echo -e "${GREEN}Important credentials (SAVE THESE):${NC}"
echo -e "─────────────────────────────────────────"
echo -e "Database Password: ${YELLOW}${DB_PASS}${NC}"
echo -e "Admin API Key:     ${YELLOW}${ADMIN_API_KEY}${NC}"
echo -e "─────────────────────────────────────────"
echo ""
echo -e "API will be available at: ${YELLOW}http://\$(hostname -I | awk '{print \$1}')${NC}"
echo -e "API Docs at: ${YELLOW}http://\$(hostname -I | awk '{print \$1}')/docs${NC}"
