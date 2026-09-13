-- ============================================================
-- Aeternum PremiApp Bot - PostgreSQL Database Schema
-- ============================================================

-- 1. Tabel Users
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,               -- Telegram User ID
    username VARCHAR(100),
    first_name VARCHAR(150),
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Tabel Kategori Produk
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Tabel Katalog Produk
-- Tipe Produk:
-- 'TEXT_STOCK'  : Akun / Lisensi / Voucher habis pakai (stok unik)
-- 'TEXT_STATIC' : Teks template / Prompt AI / Link statis reusable
-- 'FILE'        : Dokumen / ZIP / PDF via Telegram file_id
-- 'INVITE_LINK' : Undangan channel VIP otomatis
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    category_id INT REFERENCES categories(id) ON DELETE SET NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price NUMERIC(12, 2) NOT NULL,
    product_type VARCHAR(50) NOT NULL,
    text_content TEXT,                 -- Digunakan jika tipe TEXT_STATIC
    telegram_file_id TEXT,             -- Digunakan jika tipe FILE
    vip_chat_id BIGINT,                -- Digunakan jika tipe INVITE_LINK
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Tabel Stok Teks / Lisensi Unik
CREATE TABLE IF NOT EXISTS product_items (
    id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(id) ON DELETE CASCADE,
    content TEXT NOT NULL,               -- Akun / Key / Baris Teks
    is_sold BOOLEAN DEFAULT FALSE,
    sold_at TIMESTAMP WITH TIME ZONE,
    transaction_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Tabel Transaksi / Invoice
CREATE TABLE IF NOT EXISTS transactions (
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
