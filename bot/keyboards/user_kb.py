"""
Aeternum PremiApp Bot - Keyboard Antarmuka Pengguna (User UI & MiniApp)
"""

from typing import List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.models import Category, Product, Transaction


def get_miniapp_url() -> str:
    """Mendapatkan URL WebApp."""
    base_url = settings.WEBHOOK_HOST
    if not base_url.startswith("http"):
        base_url = f"https://{base_url}"
    return f"{base_url}/app"


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Tombol Utama: Telegram Mini App (Web Store Modern)
    builder.row(
        InlineKeyboardButton(
            text="🚀 Buka Web Store (MiniApp)",
            web_app=WebAppInfo(url=get_miniapp_url())
        )
    )
    
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
    builder = InlineKeyboardBuilder()
    price_to_pay = current_price or float(product.price)

    if is_available:
        fmt_bal = f"Rp {user_balance:,.0f}".replace(",", ".")
        builder.row(
            InlineKeyboardButton(
                text=f"💳 Bayar Pakai Saldo (Saldo: {fmt_bal})",
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
                text="🔔 Ingatkan Saya Saat Restock",
                callback_data=f"restock_alert_{product.id}"
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


def insufficient_balance_kb(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Top Up Saldo Sekarang", callback_data="wallet_topup")
    )
    builder.row(
        InlineKeyboardButton(text="⚡ Beli Langsung via QRIS", callback_data=f"buy_{product_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Detail Produk", callback_data=f"prod_{product_id}")
    )
    return builder.as_markup()


def invoice_kb(invoice_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Cek Status Pembayaran", callback_data=f"check_trx_{invoice_id}")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Batalkan Pesanan", callback_data=f"cancel_trx_{invoice_id}"),
        InlineKeyboardButton(text="💬 Butuh Bantuan?", callback_data="user_help")
    )
    return builder.as_markup()


def review_prompt_kb(invoice_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"rate_5_{invoice_id}"),
        InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"rate_4_{invoice_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"rate_3_{invoice_id}"),
        InlineKeyboardButton(text="⭐⭐", callback_data=f"rate_2_{invoice_id}"),
        InlineKeyboardButton(text="⭐", callback_data=f"rate_1_{invoice_id}"),
    )
    return builder.as_markup()


def history_detail_kb(invoice_id: str, is_paid: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_paid:
        builder.row(
            InlineKeyboardButton(text="⭐ Beri Ulasan", callback_data=f"prompt_rate_{invoice_id}"),
            InlineKeyboardButton(text="⚠️ Klaim Garansi / Kendala", callback_data=f"claim_warranty_{invoice_id}"),
        )
    builder.row(
        InlineKeyboardButton(text="🔙 Kembali ke Riwayat", callback_data="user_history"),
        InlineKeyboardButton(text="🏠 Menu Utama", callback_data="back_to_main"),
    )
    return builder.as_markup()


def history_list_kb(transactions: List[Transaction]) -> InlineKeyboardMarkup:
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
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main")
    )
    return builder.as_markup()
