-- ============================================================
-- Aeternum PremiApp Bot - PostgreSQL Database Schema & Indexes
-- ============================================================

-- 1. Tabel Users
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,               -- Telegram User ID
    username VARCHAR(100),
    first_name VARCHAR(150),
    is_admin BOOLEAN DEFAULT FALSE,
    balance NUMERIC(12, 2) DEFAULT 0.0,  -- Saldo dompet internal
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
    text_content TEXT,
    telegram_file_id TEXT,
    vip_chat_id BIGINT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Tabel Stok Teks / Lisensi Unik (Dengan Sistem Reservasi Kunci Sementara)
CREATE TABLE IF NOT EXISTS product_items (
    id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    is_sold BOOLEAN DEFAULT FALSE,
    sold_at TIMESTAMP WITH TIME ZONE,
    transaction_id VARCHAR(100),
    reserved_by_trx VARCHAR(50),         -- ID Transaksi yang sedang mengunci stok
    reserved_until TIMESTAMP WITH TIME ZONE, -- Batas waktu kunci (15 menit)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Tabel Kode Promo & Kupon Diskon
CREATE TABLE IF NOT EXISTS promo_codes (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    discount_type VARCHAR(20) DEFAULT 'PERCENT',
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
    trx_type VARCHAR(20) DEFAULT 'PURCHASE', -- 'PURCHASE' atau 'TOPUP'
    payment_method VARCHAR(30) DEFAULT 'QRIS', -- 'QRIS' atau 'BALANCE'
    original_amount NUMERIC(12, 2) DEFAULT 0.0,
    discount_amount NUMERIC(12, 2) DEFAULT 0.0,
    promo_code VARCHAR(50),
    amount NUMERIC(12, 2) NOT NULL,
    qris_string TEXT,
    qris_image_url TEXT,
    gateway_reference VARCHAR(100),
    status VARCHAR(30) DEFAULT 'PENDING',-- PENDING, PAID, EXPIRED, FAILED
    delivered_content TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at TIMESTAMP WITH TIME ZONE,
    expired_at TIMESTAMP WITH TIME ZONE
);

-- 8. Tabel Ulasan & Rating Pelanggan
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(50) REFERENCES transactions(id) ON DELETE CASCADE UNIQUE NOT NULL,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    product_id INT REFERENCES products(id) ON DELETE CASCADE NOT NULL,
    rating INT NOT NULL,
    comment TEXT,
    is_posted_to_channel BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 9. Tabel Tiket Klaim Garansi & Kendala Akun
CREATE TABLE IF NOT EXISTS warranty_tickets (
    id SERIAL PRIMARY KEY,
    ticket_code VARCHAR(50) UNIQUE NOT NULL,
    transaction_id VARCHAR(50) REFERENCES transactions(id) ON DELETE CASCADE NOT NULL,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    product_id INT REFERENCES products(id) ON DELETE CASCADE NOT NULL,
    issue_description TEXT NOT NULL,
    proof_file_id TEXT,
    status VARCHAR(30) DEFAULT 'OPEN',   -- 'OPEN', 'RESOLVED', 'REJECTED'
    admin_notes TEXT,
    replacement_content TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- ============================================================
-- PERFORMANCE & HIGH-CONCURRENCY INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_products_cat_active ON products(category_id, is_active);
CREATE INDEX IF NOT EXISTS idx_product_items_stock ON product_items(product_id, is_sold);
CREATE INDEX IF NOT EXISTS idx_product_items_reservation ON product_items(product_id, is_sold, reserved_until);
CREATE INDEX IF NOT EXISTS idx_transactions_user_status ON transactions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_transactions_expired ON transactions(status, expired_at);
CREATE INDEX IF NOT EXISTS idx_warranty_tickets_user ON warranty_tickets(user_id, status);
