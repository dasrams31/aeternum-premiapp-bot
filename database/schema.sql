-- ============================================================
-- Aeternum PremiApp Bot - PostgreSQL Database Schema
-- ============================================================

-- 1. Tabel Users (Termasuk Afiliasi & Saldo Komisi)
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,               -- Telegram User ID
    username VARCHAR(100),
    first_name VARCHAR(150),
    is_admin BOOLEAN DEFAULT FALSE,
    referred_by BIGINT,                  -- ID Telegram Pengundang
    referral_balance NUMERIC(12, 2) DEFAULT 0.0, -- Saldo komisi referral
    total_referrals INT DEFAULT 0,       -- Jumlah teman yang diundang
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
CREATE TABLE IF NOT EXISTS products (
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
CREATE TABLE IF NOT EXISTS product_items (
    id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    is_sold BOOLEAN DEFAULT FALSE,
    sold_at TIMESTAMP WITH TIME ZONE,
    transaction_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Tabel Kode Promo & Kupon Diskon
CREATE TABLE IF NOT EXISTS promo_codes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    discount_type VARCHAR(20) DEFAULT 'PERCENT', -- 'PERCENT' atau 'FIXED'
    discount_value NUMERIC(12, 2) NOT NULL,
    min_purchase NUMERIC(12, 2) DEFAULT 0.0,
    max_discount NUMERIC(12, 2),
    max_usage INT DEFAULT 100,
    used_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    expired_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Tabel Penggunaan Promo
CREATE TABLE IF NOT EXISTS promo_usages (
    id SERIAL PRIMARY KEY,
    promo_id INT REFERENCES promo_codes(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    transaction_id VARCHAR(50) NOT NULL,
    discount_amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. Tabel Transaksi / Invoice
CREATE TABLE IF NOT EXISTS transactions (
    id VARCHAR(50) PRIMARY KEY,          -- Format: AP-YYYYMMDD-XXXX
    user_id BIGINT REFERENCES users(id),
    product_id INT REFERENCES products(id),
    original_amount NUMERIC(12, 2) DEFAULT 0.0,
    discount_amount NUMERIC(12, 2) DEFAULT 0.0,
    promo_code VARCHAR(50),
    amount NUMERIC(12, 2) NOT NULL,      -- Total akhir setelah diskon
    qris_string TEXT,                    -- Payload QRIS
    qris_image_url TEXT,                 -- URL Gambar QRIS dari gateway
    gateway_reference VARCHAR(100),      -- Ref ID dari Payment Gateway
    status VARCHAR(30) DEFAULT 'PENDING',-- PENDING, PAID, EXPIRED, FAILED
    delivered_content TEXT,              -- Salinan produk yang dikirimkan (arsip)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at TIMESTAMP WITH TIME ZONE,
    expired_at TIMESTAMP WITH TIME ZONE
);
