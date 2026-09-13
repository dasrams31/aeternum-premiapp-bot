"""
Aeternum PremiApp Bot - Keyboard Antarmuka Pengguna (User UI)
"""

from typing import List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Category, Product, Transaction


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Menu Utama Pembeli."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🛍️ Katalog Produk", callback_data="user_catalog"),
        InlineKeyboardButton(text="💰 Dompet & Saldo", callback_data="user_wallet"),
    )
    builder.row(
        InlineKeyboardButton(text="👥 Program Afiliasi", callback_data="user_referral"),
        InlineKeyboardButton(text="📜 Riwayat Pesanan", callback_data="user_history"),
    )
    builder.row(
        InlineKeyboardButton(text="💎 Cara Pembelian", callback_data="user_how_to_buy"),
        InlineKeyboardButton(text="💬 Bantuan / CS", callback_data="user_help"),
    )
    
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="⚙️ Panel Admin Toko", callback_data="admin_dashboard")
        )
        
    return builder.as_markup()


def wallet_menu_kb() -> InlineKeyboardMarkup:
    """Menu Dompet Saldo Pengguna."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Top Up Saldo via QRIS", callback_data="wallet_topup")
    )
    builder.row(
        InlineKeyboardButton(text="🛍️ Belanja dari Katalog", callback_data="user_catalog"),
        InlineKeyboardButton(text="🏠 Menu Utama", callback_data="back_to_main"),
    )
    return builder.as_markup()


def topup_presets_kb() -> InlineKeyboardMarkup:
    """Preset Nominal Top Up Saldo."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Rp 10.000", callback_data="topup_nom_10000"),
        InlineKeyboardButton(text="Rp 25.000", callback_data="topup_nom_25000"),
    )
    builder.row(
        InlineKeyboardButton(text="Rp 50.000", callback_data="topup_nom_50000"),
        InlineKeyboardButton(text="Rp 100.000", callback_data="topup_nom_100000"),
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Nominal Kustom", callback_data="topup_custom"),
        InlineKeyboardButton(text="❌ Batalkan", callback_data="user_wallet"),
    )
    return builder.as_markup()


def categories_kb(categories: List[Category]) -> InlineKeyboardMarkup:
    """Daftar Kategori Produk."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(
            InlineKeyboardButton(text=f"📂 {cat.name}", callback_data=f"cat_{cat.id}")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Menu Utama", callback_data="back_to_main")
    )
    return builder.as_markup()


def products_kb(products_with_stock: List[tuple[Product, int]]) -> InlineKeyboardMarkup:
    """Daftar Produk dalam Kategori tertentu."""
    builder = InlineKeyboardBuilder()
    for prod, stock_count in products_with_stock:
        if prod.product_type == "TEXT_STOCK":
            stock_badge = f"🟢 Sisa {stock_count}" if stock_count > 0 else "🔴 Habis"
        else:
            stock_badge = "⚡ Instan"
            
        btn_text = f"{prod.name} | Rp {prod.price:,.0f} ({stock_badge})".replace(",", ".")
        builder.row(
            InlineKeyboardButton(text=btn_text, callback_data=f"prod_{prod.id}")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 Pilih Kategori Lain", callback_data="user_catalog"),
        InlineKeyboardButton(text="🏠 Menu Utama", callback_data="back_to_main"),
    )
    return builder.as_markup()


def product_detail_kb(
    product: Product,
    is_available: bool,
    user_balance: float = 0.0,
    current_price: float = 0.0,
    has_promo: bool = False,
) -> InlineKeyboardMarkup:
    """Tombol Aksi pada Halaman Detail Produk."""
    builder = InlineKeyboardBuilder()
    price_to_pay = current_price or float(product.price)

    if is_available:
        # Tombol bayar dengan saldo internal jika cukup
        if user_balance >= price_to_pay:
            builder.row(
                InlineKeyboardButton(
                    text=f"⚡ Bayar Pakai Saldo (Rp {user_balance:,.0f})".replace(",", "."),
                    callback_data=f"pay_balance_{product.id}"
                )
            )
        
        builder.row(
            InlineKeyboardButton(
                text="⚡ Beli Sekarang via QRIS",
                callback_data=f"buy_{product.id}"
            )
        )
        if not has_promo:
            builder.row(
                InlineKeyboardButton(
                    text="🎟️ Pakai Kode Diskon / Voucher",
                    callback_data=f"apply_promo_{product.id}"
                )
            )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🚫 Stok Sedang Habis",
                callback_data="stock_empty_alert"
            )
        )
        
    builder.row(
        InlineKeyboardButton(
            text="🔙 Kembali ke Daftar",
            callback_data=f"cat_{product.category_id}" if product.category_id else "user_catalog"
        ),
        InlineKeyboardButton(text="🏠 Menu Utama", callback_data="back_to_main"),
    )
    return builder.as_markup()


def invoice_kb(invoice_id: str) -> InlineKeyboardMarkup:
    """Tombol Aksi pada Invoice Pembayaran QRIS."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Cek Status Pembayaran", callback_data=f"check_trx_{invoice_id}")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan Pesanan", callback_data=f"cancel_trx_{invoice_id}"),
        InlineKeyboardButton(text="💬 Butuh Bantuan?", callback_data="user_help")
    )
    return builder.as_markup()


def history_list_kb(transactions: List[Transaction]) -> InlineKeyboardMarkup:
    """Daftar Riwayat Transaksi Pengguna."""
    builder = InlineKeyboardBuilder()
    for trx in transactions:
        status_icon = "✅" if trx.status == "PAID" else "⏳" if trx.status == "PENDING" else "❌"
        trx_label = "TopUp" if trx.trx_type == "TOPUP" else f"#{trx.id}"
        btn_text = f"{status_icon} {trx_label} - Rp {trx.amount:,.0f}".replace(",", ".")
        builder.row(
            InlineKeyboardButton(text=btn_text, callback_data=f"view_hist_{trx.id}")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Menu Utama", callback_data="back_to_main")
    )
    return builder.as_markup()


def referral_menu_kb(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    """Menu Program Afiliasi & Referral."""
    builder = InlineKeyboardBuilder()
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    share_url = f"https://t.me/share/url?url={ref_link}&text=Beli%20Akun%20Premium%20Otomatis%20di%20Aeternum%20PremiApp"

    builder.row(
        InlineKeyboardButton(text="🚀 Bagikan Link ke Teman", url=share_url)
    )
    builder.row(
        InlineKeyboardButton(text="💳 Tarik Saldo Komisi", callback_data="user_withdraw_referral"),
        InlineKeyboardButton(text="🏠 Menu Utama", callback_data="back_to_main"),
    )
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    """Tombol Navigasi Cepat ke Beranda."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main")
    )
    return builder.as_markup()
