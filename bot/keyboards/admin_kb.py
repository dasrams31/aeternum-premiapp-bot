"""
Aeternum PremiApp Bot - Keyboard Panel Admin (Owner UI)
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Category, Product


def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Kelola & Cek Produk", callback_data="admin_manage_products"),
        InlineKeyboardButton(text="➕ Tambah Produk", callback_data="admin_add_product"),
    )
    builder.row(
        InlineKeyboardButton(text="📦 Tambah Stok Teks", callback_data="admin_add_stock"),
        InlineKeyboardButton(text="📁 Kelola Kategori", callback_data="admin_manage_categories"),
    )
    builder.row(
        InlineKeyboardButton(text="🛡️ Kelola Garansi", callback_data="admin_manage_warranties"),
        InlineKeyboardButton(text="🎟️ Buat Kode Promo", callback_data="admin_add_promo"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 Broadcast Pesan", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="📥 Export CSV / Excel", callback_data="admin_export_csv"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Laporan & Omset", callback_data="admin_reports"),
        InlineKeyboardButton(text="🔙 Menu Pembeli", callback_data="back_to_main"),
    )
    return builder.as_markup()


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚀 Kirim Broadcast Sekarang", callback_data="confirm_send_broadcast"),
        InlineKeyboardButton(text="❌ Batalkan", callback_data="admin_dashboard"),
    )
    return builder.as_markup()


def ticket_admin_kb(ticket_code: str, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Kirim Akun Pengganti", callback_data=f"adm_replace_{ticket_code}"),
        InlineKeyboardButton(text="💬 Balas Pesan", callback_data=f"adm_reply_{ticket_code}"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Tolak Klaim", callback_data=f"adm_reject_{ticket_code}")
    )
    return builder.as_markup()


def select_category_kb(categories: list[Category], action_prefix: str = "adm_cat") -> InlineKeyboardMarkup:
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
    builder = InlineKeyboardBuilder()
    for prod in products:
        builder.row(
            InlineKeyboardButton(text=f"📦 {prod.name}", callback_data=f"adm_stock_{prod.id}")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Panel Admin", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def cancel_admin_action_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan Aksi", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def select_warranty_kb(prefix: str = "adm_war") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ No Garansi", callback_data=f"{prefix}_NONE"),
        InlineKeyboardButton(text="⚡ Garansi 24 Jam", callback_data=f"{prefix}_24H"),
    )
    builder.row(
        InlineKeyboardButton(text="📝 Custom Garansi (Input Note Sendiri)", callback_data=f"{prefix}_CUSTOM")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def select_product_for_warranty_kb(products: list[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for prod in products:
        war_badge = "❌ No Garansi" if prod.warranty_type == "NONE" else ("⚡ 24 Jam" if prod.warranty_type == "24_HOURS" else "📝 Custom")
        builder.row(
            InlineKeyboardButton(text=f"📦 {prod.name} [{war_badge}]", callback_data=f"adm_war_prod_{prod.id}")
        )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Panel Admin", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def product_warranty_action_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Set: No Garansi", callback_data=f"adm_war_set_{product_id}_NONE"),
        InlineKeyboardButton(text="⚡ Set: Garansi 24 Jam", callback_data=f"adm_war_set_{product_id}_24H"),
    )
    builder.row(
        InlineKeyboardButton(text="📝 Set: Custom Garansi (Tulis Note)", callback_data=f"adm_war_set_{product_id}_CUSTOM")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Broadcast Garansi ke Seluruh Pembeli", callback_data=f"adm_war_bcast_{product_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Daftar Garansi", callback_data="admin_manage_warranties")
    )
    return builder.as_markup()


def select_product_to_manage_kb(products: list[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for prod in products:
        dur_str = prod.duration_label or (f"{prod.duration_days} Hari" if prod.duration_days else "Lifetime")
        btn_text = f"📦 {prod.name} | Rp {prod.price:,.0f} ({dur_str})".replace(",", ".")
        builder.row(
            InlineKeyboardButton(text=btn_text, callback_data=f"adm_prod_view_{prod.id}")
        )
    builder.row(
        InlineKeyboardButton(text="➕ Tambah Produk Baru", callback_data="admin_add_product"),
        InlineKeyboardButton(text="🔙 Panel Admin", callback_data="admin_dashboard"),
    )
    return builder.as_markup()


def product_management_detail_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👁️ Cek Isi Stok", callback_data=f"adm_view_stock_{product_id}"),
        InlineKeyboardButton(text="➕ Tambah Stok", callback_data=f"adm_stock_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📥 Ambil / Tarik Stok", callback_data=f"adm_pull_stock_{product_id}"),
        InlineKeyboardButton(text="📤 Kurangi / Hapus Stok", callback_data=f"adm_reduce_stock_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="⏱️ Ubah Masa Aktif", callback_data=f"adm_edit_dur_{product_id}"),
        InlineKeyboardButton(text="🛡️ Kelola Garansi", callback_data=f"adm_war_prod_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Hapus Produk", callback_data=f"adm_del_prod_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Daftar Produk", callback_data="admin_manage_products"),
        InlineKeyboardButton(text="🏠 Panel Admin", callback_data="admin_dashboard"),
    )
    return builder.as_markup()


def pull_stock_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📥 Ambil 1 Akun", callback_data=f"adm_do_pull_{product_id}_1"),
        InlineKeyboardButton(text="📥 Ambil 5 Akun", callback_data=f"adm_do_pull_{product_id}_5"),
    )
    builder.row(
        InlineKeyboardButton(text="✍️ Ketik Jumlah Ambil", callback_data=f"adm_do_pull_{product_id}_custom"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Produk", callback_data=f"adm_prod_view_{product_id}"),
    )
    return builder.as_markup()


def reduce_stock_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➖ Kurangi 1 Stok", callback_data=f"adm_do_red_{product_id}_1"),
        InlineKeyboardButton(text="➖ Kurangi 5 Stok", callback_data=f"adm_do_red_{product_id}_5"),
    )
    builder.row(
        InlineKeyboardButton(text="✍️ Ketik Jumlah Kurangi", callback_data=f"adm_do_red_{product_id}_custom"),
        InlineKeyboardButton(text="🔥 Kosongkan Semua Stok", callback_data=f"adm_do_red_{product_id}_all"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Produk", callback_data=f"adm_prod_view_{product_id}"),
    )
    return builder.as_markup()


def select_duration_kb(prefix: str = "adm_dur") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗓️ 1 Bulan", callback_data=f"{prefix}_1M"),
        InlineKeyboardButton(text="🗓️ 3 Bulan", callback_data=f"{prefix}_3M"),
    )
    builder.row(
        InlineKeyboardButton(text="🗓️ 6 Bulan", callback_data=f"{prefix}_6M"),
        InlineKeyboardButton(text="🗓️ 1 Tahun (12 Bln)", callback_data=f"{prefix}_1Y"),
    )
    builder.row(
        InlineKeyboardButton(text="🗓️ 18 Bulan", callback_data=f"{prefix}_18M"),
        InlineKeyboardButton(text="♾️ Lifetime / Permanen", callback_data=f"{prefix}_LIFETIME"),
    )
    builder.row(
        InlineKeyboardButton(text="✍️ Ketik Bebas / Custom Sendiri", callback_data=f"{prefix}_CUSTOM_TYPING")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan", callback_data="admin_dashboard")
    )
    return builder.as_markup()


def confirm_delete_product_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚠️ Ya, Hapus Produk Ini", callback_data=f"adm_confirm_del_{product_id}"),
        InlineKeyboardButton(text="❌ Batalkan", callback_data=f"adm_prod_view_{product_id}"),
    )
    return builder.as_markup()


