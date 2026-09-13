# Aeternum PremiApp Bot 🌟
> **Automated Digital Product & Premium Store Telegram Bot with Dynamic QRIS & Web MiniApp**  
> Powered by Python (`aiogram 3.x`), FastAPI, PostgreSQL, and Official **BAYAR GG** Payment Gateway.  
> Official Owner & Primary Admin: **@dasrams**

---

## 📌 Ringkasan Proyek
**Aeternum PremiApp Bot** adalah platform bot Telegram otomatis 24/7 untuk penjualan berbagai kategori produk digital:
- 🔑 **Kredensial & Akun Premium** (Format 1-Click Copy `<code>` dengan proteksi `protect_content` & Enkripsi AES-256)
- 🗝️ **Serial Key / Lisensi Unik** (Sistem Atomic Delivery `SELECT ... FOR UPDATE SKIP LOCKED`)
- 📝 **Teks Panduan / Prompt AI / Template** (Stok statis reusable)
- 📁 **File Dokumen / PDF / E-Book / ZIP** (Pengiriman via Telegram Document)
- 🔗 **Link Undangan Channel / Grup VIP Otomatis** (One-Time Single-Use Invite Link)

---

## 🚀 Fitur Utama Lengkap

### 1. 💳 Pembayaran QRIS Dinamis Otomatis (BAYAR GG API)
- Terintegrasi langsung dengan API resmi **BAYAR GG** (`https://www.bayar.gg/api-docs`).
- Menghasilkan gambar **QR Code Dinamis Asli** (Bank Mandiri / Nobu) yang dapat di-scan oleh semua Bank (BCA, Mandiri, BRI, BNI) dan E-Wallet (GoPay, OVO, DANA, ShopeePay, LinkAja).
- Dilengkapi **Background Auto-Payment Poller (6 Detik)**: Mendeteksi pembayaran secara *real-time* dan langsung mengirimkan produk ke pembeli tanpa pembeli perlu mengklik tombol konfirmasi apapun.

### 2. 📱 Telegram Mini App (TMA Web Store Interface)
- Antarmuka web modern berbasis **Tailwind CSS & Lucide Icons** yang terbuka langsung di dalam aplikasi Telegram.
- **Katalog Interaktif**: Filter kategori, live stock indicator, modal detail produk, dan input kupon diskon.
- **Owner Dashboard (@dasrams)**: Melihat statistik omset live, total transaksi sukses, dan export laporan CSV satu klik.

### 3. 🔒 Temporary Stock Reservation (Kunci Stok Otomatis 15 Menit)
- Stok akun/serial key dikunci sementara saat pembeli membuat invoice QRIS.
- Jika pembayaran sukses -> Status berubah menjadi **Terjual Permanen (`is_sold = TRUE`)**.
- Jika pembeli membatalkan pesanan atau batas waktu 15 menit habis -> Stok **otomatis dikembalikan ke etalase** oleh background janitor.

### 4. 💰 Dompet Saldo Internal (Instant 1-Second Checkout)
- Pengguna dapat melakukan deposit/top up saldo via QRIS dinamis.
- Pembelian produk dapat dibayar langsung menggunakan saldo dengan satu kali klik tanpa perlu scan QRIS lagi.

### 5. 🔔 Restock Notifier (Pengingat Stok Otomatis)
- Jika stok produk kosong (`0`), pembeli dapat mendaftar antrean pengingat `[ 🔔 Ingatkan Saya Saat Restock ]`.
- Begitu Admin menginput stok baru, bot secara otomatis mengirimkan DM ke seluruh pembeli yang menunggu.

### 6. ⏱️ Subscription Expiry Reminder (Pengingat H-3 & H-1)
- Scheduler background otomatis mendeteksi akun langganan yang akan habis:
  - **H-3**: Pengingat ramah perpanjangan akun.
  - **H-1**: Peringatan terakhir dengan tombol perpanjang instan `[ ⚡ Perpanjang Sekarang ]`.

### 7. 🎟️ Sistem Kupon & Diskon Promo
- Diskon berbasis persentase (`PERCENT`) atau potongan nominal tetap (`FIXED`).
- Validasi kuota penggunaan maksimal, minimal belanja, dan proteksi satu kali klaim per pengguna.

### 8. 👥 Program Afiliasi & Referral Organik (Komisi 5%)
- Tautan referral unik per pengguna (`https://t.me/aeternum_premibot?start=ref_USERID`).
- Pembagian komisi otomatis 5% dari setiap pembelian teman langsung masuk ke saldo akun pengundang.

### 9. ⭐ Sistem Rating Bintang & Auto-Testimoni ke Channel
- Prompt ulasan bintang 1-5 dan komentar setelah pesanan selesai.
- Ulasan bintang 4 & 5 otomatis diformat dan diposting ke Channel Publik Testimoni sebagai *social proof*.

### 10. 🛡️ Tiket Klaim Garansi & Penyelesaian Admin
- Pembeli dapat mengajukan kendala akun pada menu riwayat lengkap dengan bukti foto screenshot.
- Admin dapat menyelesaikan tiket langsung dari DM Telegram (`[ 🔄 Kirim Akun Pengganti ]` / `[ ❌ Tolak ]`).

### 11. 📊 Export Laporan Penjualan ke CSV / Excel
- Admin dapat mengunduh laporan pembukuan transaksi lunas dalam format CSV ber-BOM UTF-8 siap buka di Microsoft Excel / Google Sheets.

### 12. 📢 Broadcast Notifikasi Massal
- Mengirimkan siaran promosi/update restock ke seluruh pengguna terdaftar dengan preview & anti-flood protection.

---

## 🛡️ Arsitektur Keamanan (*Security Hardening*)
- **Enkripsi AES-256 (Fernet) at Rest**: Seluruh kredensial akun (*email:password*, key) dienkripsi sebelum masuk ke PostgreSQL (`ENC::...`).
- **Stealth Mode Admin**: Perintah `/admin` dari non-owner dibuang tanpa respons (*Silent Drop*).
- **Atomic Concurrency Row Locks**: Menggunakan `SELECT ... FOR UPDATE SKIP LOCKED` untuk mencegah *race condition* stok dan saldo.
- **Telegram WebApp initData Verification**: Memvalidasi signature HMAC-SHA256 bot token pada checkout saldo via MiniApp.
- **Anti-Replay Webhook**: Request webhook diverifikasi signature HMAC SHA256/512 dan batas kedaluwarsa waktu.
- **Global Error Masking**: Menyembunyikan pesan error internal dari pengguna dan mengirimkan *traceback* langsung ke DM Admin @dasrams.
- **Automated Backup & 7-Day Retention**: Script backup PostgreSQL otomatis via cronjob setiap hari pukul 02:00 WIB.

---

## 📁 Struktur Proyek
```text
aeternum-premiapp-bot/
├── bot/
│   ├── handlers/          # Router alur interaksi bot
│   │   ├── admin.py       # Panel manajemen produk, stok, kupon & broadcast
│   │   ├── catalog.py     # Navigasi katalog, promo & restock alert
│   │   ├── history.py     # Riwayat belanja pengguna & klaim garansi
│   │   ├── order.py       # Pembuatan invoice QRIS BAYAR GG & stock lock
│   │   ├── review.py      # Rating bintang & auto-post testimoni
│   │   ├── start.py       # Menu utama, panduan & referral dashboard
│   │   ├── wallet.py      # Top up QRIS BAYAR GG & bayar pakai saldo
│   │   └── warranty.py    # Tiket garansi & resolusi kendala akun
│   ├── keyboards/         # Inline keyboard builder (User, Admin & MiniApp)
│   ├── middlewares/       # Throttling anti-spam, global error handler & DB session
│   └── services/          # Fulfillment, crypto AES-256, auto-poller, cleaner & subscription
├── database/
│   ├── connection.py      # Async PostgreSQL engine (SQLAlchemy + asyncpg)
│   ├── crud.py            # Operasi database atomic (FOR UPDATE SKIP LOCKED)
│   ├── models.py          # Definisi ORM tabel PostgreSQL
│   └── schema.sql         # Skema DDL & Performance Indexes
├── static/
│   └── js/
│       └── miniapp.js     # Telegram Mini App client script
├── templates/
│   └── index.html         # Tailwind CSS Telegram Mini App Web Store
├── scripts/
│   ├── install.sh         # Installer otomatis satu-klik untuk VPS
│   ├── install_docker.sh  # Installer Docker satu-klik
│   └── backup_db.sh       # Script backup otomatis PostgreSQL + rotasi 7 hari
├── tests/
│   └── test_suite.py      # 14-Scenario Comprehensive Automated Test Suite
├── nginx/
│   └── aeternum.conf      # Nginx production reverse proxy & rate limiter
├── webhook/
│   ├── server.py          # FastAPI server (Webhook Listener & MiniApp JSON API)
│   └── gateway.py         # Client Payment Gateway (BAYAR GG & Tripay)
├── config.example.py      # Template konfigurasi environment
├── Dockerfile             # Multi-stage container image (Non-Root User)
├── docker-compose.yml     # Orkestrasi Bot + PostgreSQL
├── requirements.txt       # Daftar dependensi Python
├── SECURITY.md            # Panduan keamanan & hardening production
├── INSTALL.md             # Panduan instalasi VPS baru
├── PRD.md                 # Product Requirement Document Lengkap
└── README.md
```

---

## ⚡ Panduan Instalasi Cepat di VPS Baru

Cukup clone repositori dan jalankan installer otomatis:

```bash
# 1. Clone repositori
git clone https://gitlab.com/RamsNotes31/aeternum-premiapp-bot.git
cd aeternum-premiapp-bot

# 2. Jalankan installer otomatis
sudo bash scripts/install.sh
```

### Perintah Manajemen Layanan di VPS:
- **Cek Status Bot**: `sudo systemctl status aeternum-bot`
- **Lihat Log Real-Time**: `journalctl -u aeternum-bot -f`
- **Restart Bot**: `sudo systemctl restart aeternum-bot`
- **Jalankan Test Suite**: `venv/bin/python tests/test_suite.py`
- **Backup Database Manual**: `sudo bash scripts/backup_db.sh`

---

## 📄 Dokumentasi Lengkap
- 📖 [PRD.md](./PRD.md) — Product Requirement Document & Spesifikasi Sistem
- 🚀 [INSTALL.md](./INSTALL.md) — Panduan Instalasi & Migrasi VPS Lengkap
- 🛡️ [SECURITY.md](./SECURITY.md) — Arsitektur Keamanan & Hardening Production

---

## 👤 Kontak & Pengembang
- **Owner & Admin Utama**: [@dasrams](https://t.me/dasrams)
- **Live Bot Telegram**: [@aeternum_premibot](https://t.me/aeternum_premibot)
