# PANDUAN INSTALASI & SETUP VPS BARU 🚀
## Aeternum PremiApp Bot

Panduan ini mempermudah pemindahan (*migrasi*) atau instalasi baru **Aeternum PremiApp Bot** pada VPS baru (Ubuntu 20.04 / 22.04 / 24.04 LTS / Debian).

---

## METODE 1: INSTALASI OTOMATIS SATU KLIK (SANGAT DIREKOMENDASIKAN)

Cukup hubungkan VPS baru via SSH dan jalankan perintah berikut:

```bash
# 1. Clone repositori ke VPS
git clone https://gitlab.com/RamsNotes31/aeternum-premiapp-bot.git
cd aeternum-premiapp-bot

# 2. Jalankan skrip installer otomatis
sudo bash scripts/install.sh
```

### Apa yang Dilakukan oleh Skrip Installer Otomatis?
1. Menginstall seluruh paket Linux (`Python3`, `PostgreSQL`, `Nginx`, `Certbot`, `UFW`, `libpq-dev`).
2. Membuat database PostgreSQL `aeternum_premiapp_db` dan user terautentikasi otomatis.
3. Menyiapkan Python Virtual Environment (`venv`) dan menginstall semua pustaka dependensi.
4. Memandu input token bot, Admin ID (`606533609`), dan membuat kunci enkripsi AES-256 secara acak dan aman.
5. Menginisialisasi seluruh skema tabel, relasi, dan indeks database secara otomatis.
6. Mendaftarkan layanan latar belakang **Systemd (`aeternum-bot.service`)** dengan fitur auto-restart saat VPS reboot / crash.
7. Memasang cronjob backup harian otomatis (`scripts/backup_db.sh`) dengan rotasi retensi 7 hari.

---

## METODE 2: SETUP MANUAL (LANGKAH DEMI LANGKAH)

Jika Anda ingin mengontrol setiap langkah instalasi secara manual:

### 1. Update Paket & Install Dependensi
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib libpq-dev git
```

### 2. Konfigurasi Database PostgreSQL
```bash
sudo -u postgres psql -c "CREATE DATABASE aeternum_premiapp_db;"
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'secretpassword';"
```

### 3. Setup Virtual Environment Python
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Buat File Konfigurasi `.env`
Salin template dan sesuaikan isinya:
```bash
cp .env.example .env
nano .env
```
Isi konfigurasi minimal:
```ini
BOT_TOKEN=8623661389:AAGyE4EIYHiYF8nUD11V_QTriSFvbluBTvQ
ADMIN_ID=606533609
DATABASE_URL=postgresql+asyncpg://postgres:secretpassword@localhost:5432/aeternum_premiapp_db
PAYMENT_GATEWAY=tripay
PORT=8088
```

### 5. Inisialisasi Database & Test
```bash
venv/bin/python -c "import asyncio; from database.connection import init_db; asyncio.run(init_db())"
```

### 6. Setup Systemd Service
Buat file service di `/etc/systemd/system/aeternum-bot.service`:
```ini
[Unit]
Description=Aeternum PremiApp Telegram Bot and Webhook Server
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/aeternum-premiapp-bot
ExecStart=/path/to/aeternum-premiapp-bot/venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
Aktifkan dan jalankan:
```bash
sudo systemctl daemon-reload
sudo systemctl enable aeternum-bot
sudo systemctl start aeternum-bot
```

---

## METODE 3: DEPLOYMENT DOCKER COMPOSE

Jika VPS Anda menggunakan Docker:

```bash
# 1. Salin konfigurasi environment
cp .env.example .env

# 2. Jalankan skrip docker
bash scripts/install_docker.sh
```

---

## 🛠️ PERINTAH MANAJEMEN UMUM

| Kebutuhan | Perintah |
| :--- | :--- |
| **Cek Status Bot** | `sudo systemctl status aeternum-bot` |
| **Lihat Log Live** | `journalctl -u aeternum-bot -f` |
| **Restart Bot** | `sudo systemctl restart aeternum-bot` |
| **Stop Bot** | `sudo systemctl stop aeternum-bot` |
| **Jalankan Test Suite** | `venv/bin/python tests/test_suite.py` |
| **Backup Database Manual** | `sudo bash scripts/backup_db.sh` |
