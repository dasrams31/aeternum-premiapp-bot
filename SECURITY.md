# PANDUAN HARDENING SECURITY & PRODUCTION ARCHITECTURE 🛡️
## Aeternum PremiApp Bot

Dokumen ini berisi arsitektur keamanan menyeluruh (*Defense-in-Depth*) yang telah diterapkan pada **Aeternum PremiApp Bot** untuk memastikan transaksi finansial, kredensial akun, dan server terlindungi dari berbagai vektor serangan.

---

### 1. 🔐 ENCRYPTION AT REST (AES-256 FERNET)
* **Lokasi**: `bot/services/crypto.py`
* **Mekanisme**:
  - Setiap kredensial akun (*email:password*), serial key, atau teks lisensi yang diinput via Bulk Import otomatis dienkripsi dengan algoritma **AES-256 (Fernet)** sebelum disimpan ke kolom `content` di tabel `product_items` PostgreSQL.
  - Jika database dibobol atau file dump backup bocor, penyerang hanya melihat hash terenkripsi `ENC::gAAAAAB...` yang tidak dapat dibaca.
  - Teks hanya didekripsi di memori pada saat proses pengiriman instan ke chat pembeli yang sah.

---

### 2. 🛡️ STEALTH MODE & SILENT DROP ADMIN
* **Lokasi**: `bot/handlers/admin.py`
* **Mekanisme**:
  - Jika ada pengguna selain ID Telegram Admin (`ADMIN_ID`) yang mengetik `/admin` atau mencoba menembak callback query admin (`adm_xxx`), sistem **langsung membuang request tanpa respons (Silent Drop)**.
  - Bot tidak membalas pesan "Akses Ditolak" sehingga penyerang tidak mengetahui keberadaan panel manajemen.
  - Setiap upaya akses ilegal dicatat ke log peringatan keamanan server.

---

### 3. ⏱️ ANTI-REPLAY ATTACK & WEBHOOK IDEMPOTENCY
* **Lokasi**: `webhook/server.py` & `webhook/gateway.py`
* **Mekanisme**:
  - **Timestamp Expiry**: Payload webhook yang memiliki selisih waktu lebih dari 5 menit (300 detik) otomatis ditolak dengan `400 Bad Request`.
  - **HMAC Signature Check**: Wajib memvalidasi signature HMAC SHA512 dari payment gateway.
  - **Idempotency**: Transaksi yang sudah berstatus `PAID` tidak akan memproses pengiriman produk ulang.

---

### 4. 🐳 DOCKER CONTAINER HARDENING (NON-ROOT)
* **Lokasi**: `Dockerfile`
* **Mekanisme**:
  - Container dijalankan dengan user non-root `appuser` (UID 1000).
  - Mengurangi risiko eskalasi hak akses (*privilege escalation*) jika terjadi eksploitasi pada library pihak ketiga.

---

### 5. 🚫 GLOBAL ERROR MASKING & ADMIN CRASH ALERT
* **Lokasi**: `bot/middlewares/error_handler.py`
* **Mekanisme**:
  - Semua unhandled exception ditangkap secara global.
  - **Ke Pengguna**: Menampilkan pesan sopan ramah tanpa membocorkan pesan error Python, struktur query SQL, atau direktori server.
  - **Ke Admin DM**: Mengirimkan alert real-time lengkap dengan detail error, nama user, event type, dan potongan *traceback* untuk investigasi cepat.

---

### 6. 🌐 NGINX RATE LIMITING & REVERSE PROXY
* **Lokasi**: `nginx/aeternum.conf`
* **Mekanisme**:
  - Rate limiting pada endpoint webhook (max 10 request/detik) untuk memitigasi serangan DDoS / HTTP Flooding.
  - Header keamanan HSTS, X-Frame-Options DENY, dan X-Content-Type-Options nosniff.

---

### 7. 🗄️ BACKUP OTOMATIS & CONCURRENCY LOCK
* **Lokasi**: `scripts/backup_db.sh` & `database/crud.py`
* **Mekanisme**:
  - Rotasi backup PostgreSQL otomatis 7 hari via script cronjob.
  - Concurrency Lock `SELECT ... FOR UPDATE SKIP LOCKED` pada sistem reservasi stok 15 menit.
