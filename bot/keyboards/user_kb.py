"""
Aeternum PremiApp Bot - Keyboard Antarmuka Pengguna (User UI)
Desain antarmuka modern, interaktif, dan rapi dalam Bahasa Indonesia.
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


def categories_kb(categories: List[Category]) -> InlineKeyboardMarkup:
    """Daftar Kategori Produk."""
    builder = InlineKeyboardBuilder()
    
    for cat in categories:
        builder.row(
            InlineKeyboardButton(
                text=f"📂 {cat.name}",
                callback_data=f"cat_{cat.id}"
            )
        )
        
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Menu Utama", callback_data="back_to_main")
    )
    return builder.as_markup()


def products_kb(products_with_stock: List[tuple[Product, int]]) -> InlineKeyboardMarkup:
    """
    Daftar Produk dalam Kategori tertentu.
    Menampilkan label harga dan ketersediaan stok live.
    """
    builder = InlineKeyboardBuilder()
    
    for prod, stock_count in products_with_stock:
        # Format label stok
        if prod.product_type == "TEXT_STOCK":
            stock_badge = f"🟢 Sisa {stock_count}" if stock_count > 0 else "🔴 Habis"
        else:
            stock_badge = "⚡ Instan"
            
        btn_text = f"{prod.name} | Rp {prod.price:,.0f} ({stock_badge})".replace(",", ".")
        builder.row(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"prod_{prod.id}"
            )
        )
        
    builder.row(
        InlineKeyboardButton(text="🔙 Pilih Kategori Lain", callback_data="user_catalog"),
        InlineKeyboardButton(text="🏠 Menu Utama", callback_data="back_to_main"),
    )
    return builder.as_markup()


def product_detail_kb(product: Product, is_available: bool) -> InlineKeyboardMarkup:
    """Tombol Aksi pada Halaman Detail Produk."""
    builder = InlineKeyboardBuilder()
    
    if is_available:
        builder.row(
            InlineKeyboardButton(
                text="⚡ Beli Sekarang via QRIS",
                callback_data=f"buy_{product.id}"
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
        InlineKeyboardButton(
            text="🔄 Cek Status Pembayaran",
            callback_data=f"check_trx_{invoice_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Batalkan Pesanan",
            callback_data=f"cancel_trx_{invoice_id}"
        ),
        InlineKeyboardButton(
            text="💬 Butuh Bantuan?",
            callback_data="user_help"
        )
    )
    return builder.as_markup()


def history_list_kb(transactions: List[Transaction]) -> InlineKeyboardMarkup:
    """Daftar Riwayat Transaksi Pengguna."""
    builder = InlineKeyboardBuilder()
    
    for trx in transactions:
        status_icon = "✅" if trx.status == "PAID" else "⏳" if trx.status == "PENDING" else "❌"
        btn_text = f"{status_icon} #{trx.id} - Rp {trx.amount:,.0f}".replace(",", ".")
        builder.row(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"view_hist_{trx.id}"
            )
        )
        
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Menu Utama", callback_data="back_to_main")
    )
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    """Tombol Navigasi Cepat ke Beranda."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main")
    )
    return builder.as_markup()
