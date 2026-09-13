# PRODUCT REQUIREMENT DOCUMENT (PRD)
## Aeternum PremiApp Bot — Automated Digital & Premium Store

---

### 1. RINGKASAN EKSEKUTIF & TUJUAN
* **Nama Produk**: **Aeternum PremiApp Bot**
* **Deskripsi**: Bot Telegram e-commerce otomatis untuk penjualan produk digital (teks/kredensial, file, serial key, link VIP) dengan pembayaran instan via QRIS Dinamis dan penyimpanan database relasional PostgreSQL.
* **Tujuan Utama**:
  1. Menghilangkan proses transaksi manual (otomatis 24/7 dari katalog, pembayaran, hingga pengiriman instan).
  2. Memberikan kebebasan penuh kepada Admin untuk mengelola produk & stok langsung dari Telegram.
  3. Memastikan pengiriman produk teks/file aman, instan, dan anti-duplikasi (*atomic delivery*).

---

### 2. PENGGUNA SISTEM (USER PERSONAS)
1. **Pembeli (End User / Customer)**:
   - Menjelajahi katalog produk, memilih varian, membayar via QRIS (BCA, GoPay, OVO, Dana, ShopeePay, dll), dan menerima produk dalam hitungan detik di chat Telegram.
2. **Pemilik Toko (Admin / Owner)**:
   - Menambah kategori/produk baru, mengisi stok teks/file secara massal, memantau laporan pendapatan, dan mengatur konfigurasi toko.

---

### 3. ARSITEKTUR & TECH STACK

```text
               ┌──────────────────────────────┐
               │    Aeternum PremiApp Bot     │
               │   (Telegram aiogram 3.x)     │
               └──────────────┬───────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                                         ▼
┌──────────────────┐                     ┌──────────────────┐
│ PostgreSQL Engine│                     │ FastAPI Webhook  │
│ (Data & Stock)   │                     │ (QRIS Listener)  │
└──────────────────┘                     └────────▲─────────┘
                                                  │
                                         ┌────────┴─────────┐
                                         │ Payment Gateway  │
                                         │ (QRIS Dynamic)   │
                                         └──────────────────┘
```

* **Bahasa & Framework**: Python 3.11+ / `aiogram 3.x` (Asynchronous Telegram Framework)
* **Web Server Webhook**: `FastAPI` + `Uvicorn` (menerima callback pembayaran)
* **Database**: PostgreSQL 15+ dengan ORM `SQLAlchemy 2.0 (asyncio)` + driver `asyncpg`
* **Payment Gateway**: Gateway QRIS Dinamis (Tripay / Midtrans / Pakasir / Tokopay)
* **Keamanan Akses**: Telegram Role-based Filtering (hanya Telegram ID Admin yang dapat mengakses panel manajemen).

---

### 4. SKEMA DATABASE DETAIL (POSTGRESQL DDL)

```sql
-- Database: aeternum_premiapp_db

-- 1. Tabel Users
CREATE TABLE users (
    id BIGINT PRIMARY KEY,               -- Telegram User ID
    username VARCHAR(100),
    first_name VARCHAR(150),
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Tabel Kategori
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Tabel Produk
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    category_id INT REFERENCES categories(id) ON DELETE SET NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price NUMERIC(12, 2) NOT NULL,
    product_type VARCHAR(50) NOT NULL, -- 'TEXT_STOCK', 'TEXT_STATIC', 'FILE', 'INVITE_LINK'
    text_content TEXT,                 -- Digunakan jika tipe TEXT_STATIC
    telegram_file_id TEXT,             -- Digunakan jika tipe FILE
    vip_chat_id BIGINT,                -- Digunakan jika tipe INVITE_LINK
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Tabel Stok Teks / Lisensi Unik
CREATE TABLE product_items (
    id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(id) ON DELETE CASCADE,
    content TEXT NOT NULL,               -- Akun / Key / Baris Teks
    is_sold BOOLEAN DEFAULT FALSE,
    sold_at TIMESTAMP WITH TIME ZONE,
    transaction_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Tabel Transaksi / Invoice
CREATE TABLE transactions (
    id VARCHAR(50) PRIMARY KEY,          -- Format: AP-YYYYMMDD-XXXX
    user_id BIGINT REFERENCES users(id),
    product_id INT REFERENCES products(id),
    amount NUMERIC(12, 2) NOT NULL,
    qris_string TEXT,                    -- Payload QRIS
    qris_image_url TEXT,                 -- URL Gambar QRIS dari gateway
    gateway_reference VARCHAR(100),      -- Ref ID dari Payment Gateway
    status VARCHAR(30) DEFAULT 'PENDING',-- PENDING, PAID, EXPIRED, FAILED
    delivered_content TEXT,              -- Salinan produk yang dikirimkan (arsip)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at TIMESTAMP WITH TIME ZONE,
    expired_at TIMESTAMP WITH TIME ZONE
);
```

---

### 5. SPESIFIKASI FITUR FUNGSIONAL

#### A. Fitur Pembeli (Customer Facing)
1. **Katalog & Navigasi**:
   - Menu berhirarki menggunakan Inline Keyboard (`Kategori` -> `Daftar Produk` -> `Detail Produk`).
   - Tampilan stok live di tombol produk untuk tipe `TEXT_STOCK` (contoh: `Netflix 1B [Sisa: 4]`).
2. **Checkout & Pembayaran QRIS**:
   - Tombol `[ ⚡ Beli Sekarang ]` -> Memanggil API Payment Gateway.
   - Bot mengirimkan gambar QRIS Dinamis + Teks Invoice (Nominal, ID Invoice, Timer kedaluwarsa 15 menit).
   - Tombol kontrol invoice: `[ 🔄 Cek Pembayaran ]` dan `[ ❌ Batalkan ]`.
3. **Pengiriman Produk Instan (Fulfillment Engine)**:
   - **Teks Unik (`TEXT_STOCK`)**:
     - Sistem mengambil stok dengan query aman PostgreSQL:
       `SELECT id, content FROM product_items WHERE product_id = :p_id AND is_sold = FALSE FOR UPDATE SKIP LOCKED LIMIT 1;`
     - Dikirim dalam tag `<code>` (fitur 1-klik salin) dan `protect_content=True` (anti-forward/screenshot).
   - **Teks Statis (`TEXT_STATIC`)**: Mengirim isi `text_content` langsung ke chat.
   - **File (`FILE`)**: Mengirim dokumen via `bot.send_document` menggunakan `telegram_file_id`.
   - **Channel VIP (`INVITE_LINK`)**: Bot meng-generate link undangan privat 1-time use (`member_limit=1`).
4. **Riwayat Pembelian (`/riwayat`)**:
   - Pembeli dapat melihat kembali daftar produk, serial key, atau file yang pernah mereka beli.

---

#### B. Fitur Admin (Owner Facing - In-Bot Management)
1. **Proteksi Akses**: Menu admin hanya muncul dan merespons Telegram User ID Owner yang didaftarkan di config.
2. **Wizard Tambah Produk (`/admin -> [+ Tambah Produk]`)**:
   - Step 1: Pilih / Buat Kategori.
   - Step 2: Masukkan Nama Produk & Deskripsi.
   - Step 3: Masukkan Harga (Nominal angka).
   - Step 4: Pilih Tipe Produk (`TEXT_STATIC`, `TEXT_STOCK`, `FILE`, `INVITE_LINK`).
   - Step 5: Input konten:
     - Jika `TEXT_STATIC`: Paste isi teks panduan/link.
     - Jika `TEXT_STOCK`: Paste daftar key/akun (bisa multi-baris sekaligus / bulk import).
     - Jika `FILE`: Cukup forward atau upload file ke bot.
3. **Manajemen Stok Teks (`/admin -> [📦 Kelola Stok]`)**:
   - Fitur tambah stok cepat: Admin memilih produk -> paste kumpulan teks baru per baris -> bot langsung memecah dan memasukkannya ke database.
   - Cek sisa stok per produk.
4. **Notifikasi & Laporan Real-time**:
   - Notifikasi otomatis ke DM Admin setiap ada transaksi lunas (`Invoice ID`, `Nama Produk`, `Nominal`, `Username Pembeli`).
   - Notifikasi peringatan jika stok produk tipe `TEXT_STOCK` tersisa 0 atau < 3 item.
   - Perintah laporan omset harian / bulanan (`/laporan`).

---

### 6. LOGIKA PENGIRIMAN & PENANGANAN EDGE CASES

| Kasus Khusus (Edge Case) | Penanganan Sistem |
| :--- | :--- |
| **Dua pembeli bayar produk teks terakhir secara bersamaan** | Sistem menggunakan mekanisme PostgreSQL `FOR UPDATE SKIP LOCKED`. Transaksi pertama mendapat stok, transaksi kedua diarahkan ke status *Stok Habis* + Notifikasi darurat ke Admin untuk refund/restock manual. |
| **User bayar saat invoice sudah kedaluwarsa** | Webhook tetap memverifikasi pembayaran. Jika gateway menerima dana, bot mengecek ketersediaan stok; jika ada, produk tetap dikirimkan. Jika tidak, tandai transaksi sebagai `MANUAL_REVIEW`. |
| **Webhook Gateway Delay / Timeout** | Pembeli dapat menekan tombol `[ 🔄 Cek Status Bayar ]` untuk memicu query status langsung ke API gateway. |
| **Perlindungan Pembajakan Konten Teks** | Mengaktifkan parameter `protect_content=True` pada Telegram Bot API agar teks/akun sensitif tidak bisa diteruskan (*forwarded*) ke grup publik. |

---

### 7. RENCANA TAHAP PENGEMBANGAN (ROADMAP IMPLEMENTASI)

* **Fase 1: Database & Engine Dasar**
  - Setup skema PostgreSQL (Users, Categories, Products, Product Items, Transactions).
  - Setup bot Telegram boilerplate dengan `aiogram 3` & Router modular.
* **Fase 2: Admin Panel (Katalog & Stok Teks)**
  - Implementasi Finite State Machine (FSM) Wizard untuk tambah produk & bulk import stok teks.
* **Fase 3: Integrasi Payment Gateway & Webhook**
  - Pembuatan endpoint FastAPI Webhook untuk menerima notifikasi pembayaran QRIS.
  - Implementasi logika *Atomic Fulfillment Engine* (pengiriman teks/file otomatis saat webhook valid).
* **Fase 4: User Interface & Fitur Keamanan**
  - Menyusun UI Menu, Katalog, Invoice QRIS, dan Riwayat Belanja.
  - Implementasi *protect content*, rate-limiting (anti-spam), dan graceful error handling.
* **Fase 5: Testing & Deployment**
  - Simulasi transaksi QRIS (Sandbox / Test Mode).
  - Deployment ke VPS / Server dengan Docker Compose / Systemd + Nginx SSL Reverse Proxy.
