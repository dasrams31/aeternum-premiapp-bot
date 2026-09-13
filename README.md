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
2. **🔒 Temporary Stock Reservation (Kunci Stok Otomatis)**:
   - Stok dikunci sementara 15 menit saat user membuat invoice QRIS.
   - Jika pembayaran berhasil -> stok menjadi *Terjual Permanen*.
   - Jika dibatalkan atau waktu habis -> stok otomatis dikembalikan ke etalase.
3. **💰 Dompet Saldo Internal (Instant 1-Second Checkout)**:
   - Pengguna dapat melakukan deposit/top up saldo via QRIS.
   - Pembelian produk dapat dibayar langsung menggunakan saldo tanpa perlu scan QRIS lagi.
4. **🔔 Restock Notifier (Pengingat Stok Otomatis)**:
   - Pembeli dapat mendaftar pengingat jika stok produk kosong.
   - Begitu Admin mengisi stok baru, bot otomatis mengirimkan DM broadcast ke semua pembeli yang menunggu.
5. **📊 Export Laporan Penjualan ke Excel / CSV**:
   - Admin dapat mendownload laporan pembukuan transaksi lunas dalam format CSV/Excel siap pakai langsung dari chat Telegram.
6. **⏱️ Subscription Expiry Reminder (Pengingat H-3 & H-1)**:
   - Bot otomatis mengirimkan pengingat perpanjangan masa aktif akun pada H-3 dan H-1 sebelum langganan pembeli habis.
7. **🎟️ Sistem Kupon & Diskon Promo**:
   - Diskon berbasis persentase (`PERCENT`) atau potongan tetap (`FIXED`) dengan kuota limit & minimal transaksi.
8. **👥 Program Afiliasi & Referral Organik**:
   - Link referral unik per pengguna (`/start ref_USERID`) dengan bagi hasil komisi otomatis 5%.
9. **⭐ Sistem Rating & Auto-Testimoni ke Channel**:
   - Prompt ulasan bintang 1-5 dan auto-forwarding ulasan positif ke Channel Publik Testimoni.
10. **🛡️ Sistem Tiket Klaim Garansi & Kendala Akun**:
    - Pelaporan kendala akun dengan bukti foto screenshot & penyelesaian tiket langsung dari DM Admin.
11. **📢 Broadcast Notifikasi Massal (Admin Tool)**:
    - Kirim siaran pesan teks/gambar ke seluruh pengguna dengan proteksi anti-flood limit.

---

## 📁 Struktur Proyek
```text
aeternum-premiapp-bot/
├── bot/
│   ├── handlers/          # Router perintah & alur chat
│   │   ├── admin.py       # Panel manajemen produk, stok, kupon, export CSV & broadcast
│   │   ├── catalog.py     # Navigasi katalog, promo & restock alert
│   │   ├── history.py     # Riwayat belanja pengguna & klaim garansi
│   │   ├── order.py       # Pembuatan invoice QRIS & stock lock
│   │   ├── review.py      # Rating bintang & komentar testimoni
│   │   ├── start.py       # Menu utama, panduan & referral dashboard
│   │   ├── wallet.py      # Top up deposit QRIS & bayar pakai saldo
│   │   └── warranty.py    # Tiket garansi & resolusi kendala akun
│   ├── keyboards/         # Inline keyboard builder (User & Admin UI)
│   ├── middlewares/       # Anti-spam rate limiter & database session
│   └── services/          # Fulfillment engine, subscription reminders & cleaner
├── database/
│   ├── connection.py      # Async PostgreSQL engine (SQLAlchemy + asyncpg)
│   ├── crud.py            # Operasi database atomic (FOR UPDATE SKIP LOCKED)
│   ├── models.py          # Definisi ORM tabel
│   └── schema.sql         # Skema DDL PostgreSQL
├── scripts/
│   └── backup_db.sh       # Script backup otomatis PostgreSQL + rotasi 7 hari
├── webhook/
│   ├── server.py          # FastAPI listener callback pembayaran (IP & signature verified)
│   └── gateway.py         # Integrasi API Payment Gateway QRIS
├── config.example.py      # Template konfigurasi environment
├── Dockerfile             # Multi-stage container image
├── docker-compose.yml     # Orkestrasi Bot + PostgreSQL
├── requirements.txt       # Daftar dependensi Python
├── SECURITY.md            # Panduan keamanan & hardening production
├── PRD.md                 # Product Requirement Document Lengkap
└── README.md
```

---

## 📄 Dokumentasi PRD & Security
- Spesifikasi lengkap: [PRD.md](./PRD.md)
- Panduan keamanan: [SECURITY.md](./SECURITY.md)
