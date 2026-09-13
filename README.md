# Aeternum PremiApp Bot 🌟
> **Automated Digital Product & Premium Store Telegram Bot**  
> Powered by Python (`aiogram 3.x`), PostgreSQL, and Dynamic QRIS Payment Gateways.

---

## 📌 Ringkasan Proyek
**Aeternum PremiApp Bot** adalah platform bot Telegram otomatis 24/7 untuk penjualan berbagai kategori produk digital:
- **Teks Kredensial & Akun Premium** (Format 1-Click Copy `<code>` dengan proteksi `protect_content`)
- **Serial Key / Lisensi Unik** (Sistem Atomic Delivery `FOR UPDATE SKIP LOCKED`)
- **Teks Panduan / Prompt AI / Template** (Stok statis reusable)
- **File Dokumen / PDF / E-Book / ZIP**
- **Link Undangan Channel / Grup VIP Otomatis** (One-Time Invite Link)

---

## 🚀 Fitur Utama Lengkap
1. **Pembayaran Otomatis QRIS Dinamis**:
   - Mendukung semua E-Wallet (GoPay, OVO, DANA, ShopeePay, LinkAja) dan Mobile Banking (BCA, Mandiri, BRI, BNI, dll).
   - Verifikasi transaksi instan secara real-time via Webhook.
2. **💰 Dompet Saldo Internal (Instant 1-Second Checkout)**:
   - Pengguna dapat melakukan deposit/top up saldo via QRIS.
   - Pembelian produk dapat dibayar langsung menggunakan saldo tanpa perlu scan QRIS lagi.
3. **🎟️ Sistem Kupon & Diskon Promo**:
   - Diskon berbasis persentase (`PERCENT`) atau potongan tetap (`FIXED`).
   - Validasi batas kuota klaim, minimal pembelian, dan pencegahan klaim ganda per user.
4. **👥 Program Afiliasi & Referral Organik**:
   - Link referral unik per pengguna (`/start ref_USERID`).
   - Pembagian komisi otomatis 5% dari setiap pembelian teman langsung ke saldo komisi.
5. **⭐ Sistem Rating & Auto-Testimoni ke Channel**:
   - Prompt ulasan bintang 1-5 dan komentar setelah pesanan selesai.
   - Ulasan positif (bintang 4 & 5) otomatis diformat dan diposting ke Channel Publik Testimoni.
6. **🛡️ Sistem Tiket Klaim Garansi & Kendala Akun**:
   - Pembeli dapat mengajukan klaim garansi pada menu riwayat lengkap dengan bukti foto screenshot.
   - Admin dapat menyelesaikan tiket langsung dari DM Telegram (`[ Kirim Akun Pengganti ]` / `[ Tolak ]`).
7. **📢 Broadcast Notifikasi Massal (Admin Tool)**:
   - Admin dapat mengirimkan siaran pesan promosi/restock ke seluruh pengguna terdaftar dengan preview & anti-flood protection.
8. **Keamanan & Anti-Fraud**:
   - Transaksi concurrency lock (anti pembeli ganda pada 1 akun unik).
   - Parameter `protect_content=True` mencegah forward dan screenshot teks rahasia.

---

## 📁 Struktur Proyek
```text
aeternum-premiapp-bot/
├── bot/
│   ├── handlers/          # Router perintah & alur chat
│   │   ├── admin.py       # Panel manajemen produk, stok, kupon & broadcast
│   │   ├── catalog.py     # Navigasi katalog & input kode promo
│   │   ├── history.py     # Riwayat belanja pengguna & klaim garansi
│   │   ├── order.py       # Pembuatan invoice QRIS dinamis
│   │   ├── review.py      # Rating bintang & komentar testimoni
│   │   ├── start.py       # Menu utama, panduan & referral dashboard
│   │   ├── wallet.py      # Top up deposit QRIS & bayar pakai saldo
│   │   └── warranty.py    # Tiket garansi & resolusi kendala akun
│   ├── keyboards/         # Inline keyboard builder (User & Admin UI)
│   ├── middlewares/       # Anti-spam & filter otorisasi admin
│   └── services/          # Fulfillment engine, referral reward & protect content
├── database/
│   ├── connection.py      # Async PostgreSQL engine (SQLAlchemy + asyncpg)
│   ├── crud.py            # Operasi database atomic (FOR UPDATE SKIP LOCKED)
│   ├── models.py          # Definisi ORM tabel
│   └── schema.sql         # Skema DDL PostgreSQL
├── webhook/
│   ├── server.py          # FastAPI listener callback pembayaran
│   └── gateway.py         # Integrasi API Payment Gateway QRIS
├── config.example.py      # Template konfigurasi environment
├── Dockerfile             # Multi-stage container image
├── docker-compose.yml     # Orkestrasi Bot + PostgreSQL
├── requirements.txt       # Daftar dependensi Python
├── PRD.md                 # Product Requirement Document Lengkap
└── README.md
```

---

## 📄 Dokumentasi PRD
Spesifikasi lengkap, arsitektur, dan alur sistem dapat dibaca pada [PRD.md](./PRD.md).
