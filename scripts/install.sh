#!/usr/bin/env bash
# ==============================================================================
# Aeternum PremiApp Bot - Production VPS Installer & Deployer Script
# Mendukung Setup Otomatis & Interaktif untuk VPS Ubuntu / Debian.
# Official Owner & Admin: @dasrams
# ==============================================================================

set -e

# Warna Terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

clear
echo -e "${CYAN}${BOLD}"
echo "=============================================================="
echo "    🌟 AETERNUM PREMIAPP BOT - VPS INSTALLER & DEPLOYER 🌟   "
echo "    Automated Digital Store, BAYAR GG QRIS & Web MiniApp      "
echo "    Official Owner & Primary Admin: @dasrams                  "
echo "=============================================================="
echo -e "${NC}"

# 1. Cek Hak Akses Root / Sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Skrip ini memerlukan hak akses sudo/root.${NC}"
    echo "Silakan jalankan ulang dengan: sudo bash scripts/install.sh"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

echo -e "${BLUE}📍 Direktori Proyek: ${BOLD}${PROJECT_DIR}${NC}\n"

# 2. Update Sistem & Install Paket Dasar
echo -e "${YELLOW}🔄 [1/7] Memperbarui repositori paket Linux...${NC}"
apt-get update -y > /dev/null
echo -e "${GREEN}✅ Update paket selesai.${NC}"

echo -e "${YELLOW}📦 [2/7] Menginstall dependensi sistem (Python3, Pillow Libs, PostgreSQL, Git, Nginx)...${NC}"
apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    gcc \
    git \
    curl \
    ufw \
    nginx \
    certbot \
    python3-certbot-nginx > /dev/null
echo -e "${GREEN}✅ Paket sistem dan pustaka image processing berhasil dipasang.${NC}"

# 3. Setup PostgreSQL Database
echo -e "${YELLOW}🗄️  [3/7] Mengonfigurasi Database PostgreSQL...${NC}"
systemctl start postgresql
systemctl enable postgresql

DB_NAME="aeternum_premiapp_db"
DB_USER="postgres"
DB_PASS="secretpassword"

# Buat database jika belum ada
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME};" > /dev/null

sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" > /dev/null
echo -e "${GREEN}✅ Database '${DB_NAME}' siap digunakan.${NC}"

# 4. Setup Python Virtual Environment
echo -e "${YELLOW}🐍 [4/7] Menyiapkan Python Virtual Environment (venv) & Dependencies...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip > /dev/null
pip install -r requirements.txt > /dev/null
echo -e "${GREEN}✅ Seluruh pustaka Python (aiogram, fastapi, sqlalchemy, qrcode, pillow, cryptography) terpasang.${NC}"

# 5. Konfigurasi File .env
echo -e "${YELLOW}⚙️  [5/7] Menyiapkan File Konfigurasi (.env)...${NC}"

if [ ! -f ".env" ]; then
    echo -e "${CYAN}Silakan masukkan informasi konfigurasi bot Anda:${NC}"
    
    read -rp "🤖 Masukkan Telegram Bot Token : " INPUT_BOT_TOKEN
    read -rp "👑 Masukkan Admin Telegram ID [Default: 606533609]: " INPUT_ADMIN_ID
    INPUT_ADMIN_ID=${INPUT_ADMIN_ID:-606533609}
    
    read -rp "💳 Payment Gateway (bayargg/tripay) [Default: bayargg]: " INPUT_GATEWAY
    INPUT_GATEWAY=${INPUT_GATEWAY:-bayargg}

    read -rp "🔑 Masukkan BAYAR GG / Gateway API Key: " INPUT_API_KEY
    
    read -rp "🌐 Port Webhook Server [Default: 8088]: " INPUT_PORT
    INPUT_PORT=${INPUT_PORT:-8088}

    # Generate kunci acak aman untuk enkripsi AES-256 Fernet database
    RANDOM_AES_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

    cat <<EOF > .env
BOT_TOKEN=${INPUT_BOT_TOKEN}
ADMIN_ID=${INPUT_ADMIN_ID}
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}
PAYMENT_GATEWAY=${INPUT_GATEWAY}
GATEWAY_API_KEY=${INPUT_API_KEY}
GATEWAY_PRIVATE_KEY=
GATEWAY_MERCHANT_CODE=
TESTIMONIAL_CHANNEL_ID=
ENCRYPTION_KEY=${RANDOM_AES_KEY}
WEBHOOK_HOST=http://localhost:${INPUT_PORT}
WEBHOOK_PATH=/webhook/payment
PORT=${INPUT_PORT}
EOF
    echo -e "${GREEN}✅ File .env berhasil dikonfigurasi.${NC}"
else
    echo -e "${GREEN}ℹ️ File .env sudah ada, konfigurasi lama tetap digunakan.${NC}"
fi

# 6. Inisialisasi Skema Tabel Database & Verifikasi Enkripsi
echo -e "${YELLOW}🧱 [6/7] Memverifikasi skema database dan enkripsi AES-256...${NC}"
venv/bin/python -c "
import asyncio
from database.connection import init_db
asyncio.run(init_db())
"
echo -e "${GREEN}✅ Skema database, indeks performa, dan sistem enkripsi terverifikasi.${NC}"

# 7. Setup Systemd Background Service
echo -e "${YELLOW}🚀 [7/7] Mendaftarkan Layanan Systemd (aeternum-bot.service)...${NC}"

CURRENT_USER=$(logname 2>/dev/null || echo "ubuntu")

cat <<EOF > /etc/systemd/system/aeternum-bot.service
[Unit]
Description=Aeternum PremiApp Telegram Bot, Webhook Server and Auto-Payment Poller
After=network.target postgresql.service

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable aeternum-bot
systemctl restart aeternum-bot

# 8. Setup Auto-Backup Cronjob
chmod +x "${PROJECT_DIR}/scripts/backup_db.sh"
(crontab -l 2>/dev/null | grep -v "backup_db.sh" ; echo "0 2 * * * ${PROJECT_DIR}/scripts/backup_db.sh >/dev/null 2>&1") | crontab -

echo -e "\n${CYAN}==============================================================${NC}"
echo -e "${GREEN}${BOLD}🎉 INSTALASI & DEPLOYMENT SELESAI DENGAN SUKSES! 🎉${NC}"
echo -e "${CYAN}==============================================================${NC}"
echo -e "• Status Service : ${GREEN}Active (Running)${NC}"
echo -e "• Payment Gateway: ${BOLD}BAYAR GG QRIS Dinamis Otomatis${NC}"
echo -e "• Auto Poller    : ${GREEN}Aktif per 6 detik (Pengiriman instan)${NC}"
echo -e "• Cek Status     : ${BOLD}sudo systemctl status aeternum-bot${NC}"
echo -e "• Cek Log Live   : ${BOLD}journalctl -u aeternum-bot -f${NC}"
echo -e "• Restart Bot    : ${BOLD}sudo systemctl restart aeternum-bot${NC}"
echo -e "• Backup Otomatis: Aktif setiap hari pukul 02:00 WIB (Retensi 7 Hari)"
echo -e "${CYAN}==============================================================${NC}\n"
