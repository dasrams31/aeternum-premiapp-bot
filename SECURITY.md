# PANDUAN HARDENING SECURITY & PRODUCTION CHECKLIST 🛡️
## Aeternum PremiApp Bot

Dokumen ini berisi panduan lengkap pengamanan sistem (Security Hardening) sebelum aplikasi dideploy ke lingkungan produksi (*Live Production*).

---

### 1. KEAMANAN PAYMENT GATEWAY & WEBHOOK (FINANCIAL SHIELD)

* **Wajib Verifikasi Signature Webhook**:
  - Jangan pernah mempercayai payload callback tanpa memvalidasi HMAC SHA256 / SHA512 signature dari Payment Gateway.
  - Skrip verifikasi signature telah tersedia di `webhook/gateway.py`.
* **Idempotensi & Anti Double Delivery**:
  - Webhook gateway bisa mengirimkan callback berulang jika jaringan lambat (*retry mechanism*).
  - Sistem telah dilengkapi pengecekan `if trx.status == 'PAID': return {"success": True}` untuk mencegah pengiriman akun/stok dua kali pada 1 pembayaran.
* **IP Whitelisting Payment Gateway (Nginx Layer)**:
  - Batasi akses ke endpoint `/webhook/payment` hanya dari IP resmi Payment Gateway (misal: IP Tripay / Pakasir).
  - Contoh konfigurasi Nginx:
    ```nginx
    location /webhook/payment {
        # Izinkan hanya IP Gateway
        allow 103.150.190.0/24;  # Contoh IP Gateway
        deny all;
        proxy_pass http://127.0.0.1:8000;
    }
    ```

---

### 2. KEAMANAN BOT TELEGRAM (APPLICATION LAYER)

* **Throttling & Anti-Flood Protection**:
  - `ThrottlingMiddleware` diaktifkan untuk mencegah pengguna melakukan *spam click* pada tombol katalog / order yang bisa membebani database.
* **Proteksi Konten Sensitif (`protect_content=True`)**:
  - Seluruh pengiriman akun, kredensial teks, dan dokumen otomatis mengaktifkan flag `protect_content=True` agar pembeli tidak bisa meneruskan (*forward*) atau mengambil screenshot di HP Android.
* **Role-Based Authorization**:
  - Seluruh akses panel admin, tambah produk, bulk stock, dan broadcast dilindungi pemeriksaan ketat `user.id == settings.ADMIN_ID`.

---

### 3. KEAMANAN DATABASE POSTGRESQL (DATA LAYER)

* **Mencegah Concurrency Race Condition**:
  - Penarikan stok teks menggunakan klausa `SELECT ... FOR UPDATE SKIP LOCKED` sehingga jika ada 100 pembeli bayar bersamaan pada 1 detik yang sama, tidak akan ada 2 pembeli yang menerima akun yang sama.
* **Prinsip Least Privilege**:
  - Buat user PostgreSQL khusus bot dengan hak akses terbatas pada database `aeternum_premiapp_db` (jangan gunakan user superuser `postgres` di production).
* **Backup Otomatis Berkala (Cronjob Backup)**:
  - Pasang script backup otomatis setiap hari pukul 02:00 WIB:
    ```bash
    0 2 * * * pg_dump -U aeternum_user -d aeternum_premiapp_db | gzip > /backups/db_$(date +\%Y\%m\%d).sql.gz
    ```

---

### 4. KEAMANAN INFRASTRUKTUR & SERVER (INFRA LAYER)

* **Gunakan Reverse Proxy Nginx + SSL (HTTPS)**:
  - Jangan mengekspos port 8000 langsung ke internet publik.
  - Gunakan Nginx dengan sertifikat SSL gratis dari Let's Encrypt (Certbot).
* **Firewall Server (UFW)**:
  - Buka hanya port yang diperlukan:
    ```bash
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow 22/tcp    # SSH
    sudo ufw allow 80/tcp    # HTTP
    sudo ufw allow 443/tcp   # HTTPS
    sudo ufw enable
    ```
* **Proteksi Token & Secrets**:
  - File `.env` **TIDAK BOLEH** dikomit ke Git (sudah masuk di `.gitignore`).
  - Ganti nilai `secretpassword` pada PostgreSQL dan `ADMIN_ID` dengan data asli.

---

### 5. SISTEM MONITORING & ERROR ALERTING

* **Auto Expired Invoice Janitor**:
  - Service background berjalan setiap 2 menit untuk membatalkan invoice PENDING yang telah melewati 15 menit agar tidak menumpuk.
* **Crash & Unhandled Exception Notifier**:
  - Logging terpusat dengan log rotation untuk memudahkan audit transaksi.
