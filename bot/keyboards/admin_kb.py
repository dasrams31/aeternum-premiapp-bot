"""
Aeternum PremiApp Bot - Keyboard Panel Admin (Owner UI)
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Category, Product


def admin_main_kb() -> InlineKeyboardMarkup:
    """Menu Utama Panel Admin."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="➕ Tambah Produk", callback_data="admin_add_product"),
        InlineKeyboardButton(text="📁 Kelola Kategori", callback_data="admin_manage_categories"),
    )
    builder.row(
        InlineKeyboardButton(text="📦 Tambah Stok Teks", callback_data="admin_add_stock"),
        InlineKeyboardButton(text="🎟️ Buat Kode Promo", callback_data="admin_add_promo"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Laporan & Omset", callback_data="admin_reports"),
        InlineKeyboardButton(text="🔙 Menu Pembeli", callback_data="back_to_main"),
    )
    return builder.as_markup()


def select_category_kb(categories: list[Category], action_prefix: str = "adm_cat") -> InlineKeyboardMarkup:
    """Pilihan Kategori saat Admin Tambah Produk."""
    builder = InlineKeyboardBuilder()
    
    for cat in categories:
        builder.row(
            InlineKeyboardButton(text=f"📁 {cat.name}", callback_data=f"{action_prefix}_{cat.id}")
        )
        
    builder.row(
        InlineKeyboardButton(text="➕ Buat Kategori Baru", callback_data="admin_create_category"),
        InlineKeyboardButton(text="❌ Batalkan", callback_data="admin_dashboard"),
    )
    return builder.as_markup()


def select_product_type_kb() -> InlineKeyboardMarkup:
    """Pilihan Jenis Produk Digital yang Akan Dijual."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔑 Akun / Serial Key (Stok Unik)", callback_data="type_TEXT_STOCK")
    )
    builder.row(
        InlineKeyboardButton(text="📝 Template / Prompt AI / Teks Statis", callback_data="type_TEXT_STATIC")
    )
    builder.row(
        InlineKeyboardButton(text="📁 File Dokumen / ZIP / PDF", callback_data="type_FILE")
    )
    builder.row(
        InlineKeyboardButton(text="🔗 Akses Channel/Grup VIP", callback_data="type_INVITE_LINK")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def select_discount_type_kb() -> InlineKeyboardMarkup:
    """Pilihan Jenis Diskon Kupon."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Persentase (%)", callback_data="promo_type_PERCENT"),
        InlineKeyboardButton(text="💵 Potongan Tetap (Rp)", callback_data="promo_type_FIXED"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def select_product_for_stock_kb(products: list[Product]) -> InlineKeyboardMarkup:
    """Pilihan Produk saat Admin Ingin Menambah Stok Teks."""
    builder = InlineKeyboardBuilder()
    
    for prod in products:
        if prod.product_type == "TEXT_STOCK":
            builder.row(
                InlineKeyboardButton(text=f"📦 {prod.name}", callback_data=f"adm_stock_{prod.id}")
            )
            
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Panel Admin", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def cancel_admin_action_kb() -> InlineKeyboardMarkup:
    """Tombol Batal Aksi Admin."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan Aksi", callback_data="admin_dashboard")
    )
    return builder.as_markup()
