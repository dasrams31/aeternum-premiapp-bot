"""
Aeternum PremiApp Bot - Admin Management & FSM Handlers
Panel khusus Admin untuk manajemen produk, restock notifier, export CSV/Excel, promo, dan broadcast.
"""

import asyncio
import csv
from datetime import datetime
import io
import logging
from typing import Optional
from aiogram import Bot, F, Router

logger = logging.getLogger(__name__)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from database.models import Category, Product, PromoCode, Transaction
from bot.keyboards.admin_kb import (
    admin_main_kb,
    cancel_admin_action_kb,
    confirm_broadcast_kb,
    product_warranty_action_kb,
    select_category_kb,
    select_discount_type_kb,
    select_product_for_stock_kb,
    select_product_for_warranty_kb,
    select_product_type_kb,
    select_warranty_kb,
)

router = Router(name="admin_router")


# ==========================================
# DEFINISI STATES (FSM)
# ==========================================
class AddCategoryState(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()


class AddProductState(StatesGroup):
    waiting_for_category = State()
    waiting_for_type = State()
    waiting_for_name = State()
    waiting_for_duration = State()
    waiting_for_price = State()
    waiting_for_desc = State()
    waiting_for_stock = State()
    waiting_for_warranty_choice = State()
    waiting_for_warranty_custom = State()


class AddStockState(StatesGroup):
    waiting_for_product = State()
    waiting_for_items_text = State()
    waiting_for_warranty_action = State()
    waiting_for_custom_note = State()


class AdminWarrantyState(StatesGroup):
    waiting_for_custom_note = State()


class AddPromoState(StatesGroup):
    waiting_for_code = State()
    waiting_for_type = State()
    waiting_for_value = State()
    waiting_for_min_purchase = State()
    waiting_for_max_usage = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()


def is_admin_filter(user_id: int) -> bool:
    is_adm = user_id == settings.ADMIN_ID
    if not is_adm:
        logger.warning(f"🚨 [STEALTH DROP] Unauthorized admin command attempt from user ID: {user_id}")
    return is_adm


@router.message(Command("admin"))
@router.callback_query(F.data == "admin_dashboard")
async def show_admin_dashboard(
    event: Message | CallbackQuery, state: FSMContext
) -> None:
    user = event.from_user
    if not user or not is_admin_filter(user.id):
        return

    await state.clear()
    text = (
        f"⚙️ <b>PANEL ADMIN UTAMA — Aeternum PremiApp Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Admin Terotorisasi:</b> @dasrams (ID: <code>{user.id}</code>)\n"
        f"🛡️ <b>Status Keamanan:</b> Enkripsi AES-256 Aktif | Stealth Mode ON\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Silakan pilih menu kontrol toko di bawah ini:"
    )

    if isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(
            text=text,
            reply_markup=admin_main_kb(),
            parse_mode="HTML",
        )
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(
            text=text,
            reply_markup=admin_main_kb(),
            parse_mode="HTML",
        )


# ==========================================
# 1. WIZARD TAMBAH KATEGORI
# ==========================================
@router.callback_query(F.data == "admin_create_category")
@router.callback_query(F.data == "admin_manage_categories")
async def cb_start_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCategoryState.waiting_for_name)
    text = (
        "📁 <b>TAMBAH KATEGORI BARU</b>\n\n"
        "Silakan ketik nama kategori produk baru:\n"
        "<i>(Contoh: Streaming Apps, AI Tools, VPN & Proxy)</i>"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=cancel_admin_action_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(AddCategoryState.waiting_for_name)
async def process_cat_name(message: Message, state: FSMContext) -> None:
    category_name = message.text.strip()
    await state.update_data(cat_name=category_name)
    await state.set_state(AddCategoryState.waiting_for_desc)
    await message.answer(
        "Ketik deskripsi singkat kategori ini (atau ketik <code>-</code> jika tanpa deskripsi):",
        parse_mode="HTML",
    )


@router.message(AddCategoryState.waiting_for_desc)
async def process_cat_desc(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    desc = message.text.strip()
    if desc == "-":
        desc = None

    data = await state.get_data()
    cat_name = data["cat_name"]

    category = await crud.create_category(
        session=session, name=cat_name, description=desc
    )
    await state.clear()

    await message.answer(
        f"✅ <b>Kategori Berhasil Dibuat!</b>\n\n"
        f"Nama: <b>{category.name}</b>\n"
        f"ID: <code>{category.id}</code>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )


# ==========================================
# 2. WIZARD TAMBAH PRODUK LENGKAP
# ==========================================
@router.callback_query(F.data == "admin_add_product")
async def cb_start_add_product(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    categories = await crud.get_categories(session=session, only_active=True)
    if not categories:
        await callback.answer(
            "Belum ada kategori! Buat kategori terlebih dahulu.", show_alert=True
        )
        return

    await state.set_state(AddProductState.waiting_for_category)
    text = "📁 <b>LANGKAH 1/6: PILIH KATEGORI PRODUK</b>\n\nPilih kategori untuk produk baru ini:"
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=select_category_kb(categories, action_prefix="adm_pcat"),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AddProductState.waiting_for_category, F.data.startswith("adm_pcat_"))
async def cb_pick_product_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.replace("adm_pcat_", ""))
    await state.update_data(category_id=cat_id)
    await state.set_state(AddProductState.waiting_for_type)

    text = (
        "📦 <b>LANGKAH 2/6: PILIH JENIS PRODUK DIGITAL</b>\n\n"
        "• <b>Akun / Serial Key</b>: Sistem stok habis pakai.\n"
        "• <b>Teks Statis</b>: Template / Prompt yang sama untuk semua pembeli.\n"
        "• <b>File Dokumen</b>: File ZIP / PDF langsung dari bot.\n"
        "• <b>Akses VIP</b>: Generate invite link channel privat otomatis."
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=select_product_type_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AddProductState.waiting_for_type, F.data.startswith("type_"))
async def cb_pick_product_type(callback: CallbackQuery, state: FSMContext) -> None:
    p_type = callback.data.replace("type_", "")
    await state.update_data(product_type=p_type)
    await state.set_state(AddProductState.waiting_for_name)

    text = (
        "📝 <b>LANGKAH 3/6: NAMA PRODUK</b>\n\n"
        "Silakan ketik nama produk yang akan ditampilkan di katalog:\n"
        "<i>(Contoh: Netflix Premium 1 Bulan Private Ultra HD)</i>"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=cancel_admin_action_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(AddProductState.waiting_for_name)
async def process_product_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(AddProductState.waiting_for_duration)

    await message.answer(
        "⏱️ <b>LANGKAH 4/6: MASA AKTIF / DURASI (HARI)</b>\n\n"
        "Berapa hari masa aktif langganan akun ini?\n"
        "<i>(Ketik <code>30</code> untuk 1 bulan, <code>7</code> untuk 1 minggu, atau <code>0</code> jika masa aktif permanen/lifetime)</i>",
        parse_mode="HTML",
    )


@router.message(AddProductState.waiting_for_duration)
async def process_product_duration(message: Message, state: FSMContext) -> None:
    try:
        dur = int(message.text.strip())
    except ValueError:
        dur = 30
    await state.update_data(duration_days=dur if dur > 0 else None)
    await state.set_state(AddProductState.waiting_for_price)

    await message.answer(
        "💵 <b>LANGKAH 5/6: HARGA PRODUK</b>\n\n"
        "Masukkan nominal harga produk dalam Rupiah (hanya angka):\n"
        "<i>(Contoh: 35000)</i>",
        parse_mode="HTML",
    )


@router.message(AddProductState.waiting_for_price)
async def process_product_price(message: Message, state: FSMContext) -> None:
    try:
        price = float(message.text.strip().replace(".", "").replace(",", ""))
    except ValueError:
        await message.answer("⚠️ Format harga salah! Masukkan hanya angka (misal: 35000):")
        return

    await state.update_data(price=price)
    await state.set_state(AddProductState.waiting_for_desc)

    await message.answer(
        "📄 <b>LANGKAH 6/6: DESKRIPSI & SYARAT GARANSI</b>\n\n"
        "Ketik deskripsi produk, rincian fitur, dan ketentuan garansi:\n"
        "<i>(Ketik <code>-</code> jika ingin mengosongkan deskripsi)</i>",
        parse_mode="HTML",
    )


@router.message(AddProductState.waiting_for_desc)
async def process_product_desc(
    message: Message, state: FSMContext
) -> None:
    desc = message.text.strip()
    if desc == "-":
        desc = None
    await state.update_data(description=desc)

    data = await state.get_data()
    p_type = data["product_type"]

    await state.set_state(AddProductState.waiting_for_stock)

    if p_type == "TEXT_STOCK":
        await message.answer(
            "📦 <b>LANGKAH 7/8: JUMLAH & STOK PRODUK</b>\n\n"
            "Silakan paste kumpulan akun/serial key untuk stok awal produk ini (<b>1 baris = 1 stok</b>):\n"
            "<i>(Contoh:\nuser1@mail.com:pass123\nuser2@mail.com:pass456)</i>\n\n"
            "<i>💡 Jumlah produk akan dihitung otomatis dari baris yang dimasukkan. Ketik <code>0</code> jika ingin mengosongkan stok terlebih dahulu.</i>",
            parse_mode="HTML",
        )
    elif p_type == "TEXT_STATIC":
        await message.answer(
            "📝 <b>LANGKAH 7/8: ISI KONTEN PRODUK</b>\n\n"
            "Silakan masukkan teks konten, template, atau lisensi bersama yang akan diberikan ke setiap pembeli:",
            parse_mode="HTML",
        )
    elif p_type == "FILE":
        await message.answer(
            "📁 <b>LANGKAH 7/8: UPLOAD FILE PRODUK</b>\n\n"
            "Silakan kirimkan dokumen/file (ZIP, PDF, dsb) untuk produk ini:",
            parse_mode="HTML",
        )
    elif p_type == "INVITE_LINK":
        await message.answer(
            "🔗 <b>LANGKAH 7/8: TELEGRAM CHAT ID VIP</b>\n\n"
            "Silakan masukkan Telegram Chat ID channel/grup privat (contoh: <code>-1001234567890</code>):",
            parse_mode="HTML",
        )


@router.message(AddProductState.waiting_for_stock)
async def process_product_stock(
    message: Message, state: FSMContext
) -> None:
    data = await state.get_data()
    p_type = data["product_type"]
    stock_count_str = "0"

    if p_type == "TEXT_STOCK":
        raw_text = (message.text or "").strip()
        if raw_text == "0":
            lines = []
        else:
            lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        await state.update_data(stock_lines=lines)
        stock_count_str = f"{len(lines)} Akun/Key"
    elif p_type == "TEXT_STATIC":
        await state.update_data(text_content=(message.text or "").strip())
        stock_count_str = "Unlimited (Teks Statis)"
    elif p_type == "FILE":
        if not message.document:
            await message.answer("⚠️ Harap kirimkan dokumen/file (ZIP, PDF, dsb):")
            return
        await state.update_data(telegram_file_id=message.document.file_id)
        stock_count_str = "1 File Digital"
    elif p_type == "INVITE_LINK":
        try:
            vip_id = int((message.text or "").strip())
            await state.update_data(vip_chat_id=vip_id)
            stock_count_str = "Akses VIP Otomatis"
        except ValueError:
            await message.answer("⚠️ Format Chat ID salah! Masukkan angka ID channel/grup:")
            return

    await state.set_state(AddProductState.waiting_for_warranty_choice)
    await message.answer(
        f"🛡️ <b>LANGKAH 8/8: OPSI KETENTUAN GARANSI</b>\n\n"
        f"Detail produk dan jumlah produk (<code>{stock_count_str}</code>) berhasil dicatat!\n\n"
        f"Silakan pilih ketentuan garansi untuk produk ini:\n"
        f"• <b>No Garansi:</b> Produk tidak memiliki garansi setelah terkirim.\n"
        f"• <b>Garansi 24 Jam:</b> Garansi kendala & replace selama 24 jam.\n"
        f"• <b>Custom Garansi:</b> Anda dapat menuliskan catatan garansi sendiri.",
        reply_markup=select_warranty_kb(prefix="adm_newp_war"),
        parse_mode="HTML",
    )


@router.callback_query(AddProductState.waiting_for_warranty_choice, F.data.startswith("adm_newp_war_"))
async def cb_pick_new_product_warranty(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if not callback.data:
        return
    choice = callback.data.replace("adm_newp_war_", "")
    if choice == "NONE":
        await finalize_create_product(
            target=callback,
            state=state,
            session=session,
            warranty_type="NONE",
            warranty_note="Tidak ada garansi untuk produk ini.",
        )
    elif choice == "24H":
        await finalize_create_product(
            target=callback,
            state=state,
            session=session,
            warranty_type="24_HOURS",
            warranty_note="Garansi aktif selama 24 jam setelah pembelian. Penggantian/perbaikan jika kendala login atau error.",
        )
    elif choice == "CUSTOM":
        await state.set_state(AddProductState.waiting_for_warranty_custom)
        text = (
            "✍️ <b>INPUT CATATAN GARANSI KUSTOM</b>\n\n"
            "Silakan ketik catatan/ketentuan garansi Anda untuk produk ini:\n"
            "<i>(Contoh: Garansi replace 7 hari jika akun terkena limit / Garansi refund 3 hari dengan screenshot kendala)</i>"
        )
        if isinstance(callback.message, Message):
            await callback.message.edit_text(text=text, parse_mode="HTML")
        await callback.answer()


@router.message(AddProductState.waiting_for_warranty_custom)
async def process_custom_warranty_note(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    note = (message.text or "").strip()
    await finalize_create_product(
        target=message,
        state=state,
        session=session,
        warranty_type="CUSTOM",
        warranty_note=note,
    )


async def finalize_create_product(
    target: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    warranty_type: str,
    warranty_note: Optional[str],
) -> None:
    data = await state.get_data()
    p_type = data["product_type"]

    product = await crud.create_product(
        session=session,
        category_id=data["category_id"],
        name=data["name"],
        price=data["price"],
        product_type=p_type,
        duration_days=data.get("duration_days", 30),
        description=data.get("description"),
        text_content=data.get("text_content"),
        telegram_file_id=data.get("telegram_file_id"),
        vip_chat_id=data.get("vip_chat_id"),
        warranty_type=warranty_type,
        warranty_note=warranty_note,
    )

    total_added = 0
    stock_lines = data.get("stock_lines", [])
    if stock_lines and p_type == "TEXT_STOCK":
        total_added = await crud.add_stock_items_bulk(
            session=session, product_id=product.id, contents=stock_lines
        )

    await state.clear()

    war_badge = "❌ Tidak Ada Garansi" if warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if warranty_type == "24_HOURS" else "📝 Custom Garansi")
    formatted_price = f"Rp {product.price:,.0f}".replace(",", ".")
    msg_text = (
        f"🎉 <b>PRODUK BERHASIL DITAMBAHKAN!</b>\n\n"
        f"📦 <b>Nama:</b> {product.name}\n"
        f"💵 <b>Harga:</b> {formatted_price}\n"
        f"⏱️ <b>Masa Aktif:</b> {product.duration_days or 'Lifetime'} Hari\n"
        f"🏷️ <b>Tipe:</b> <code>{product.product_type}</code>\n"
        f"🟢 <b>Jumlah Stok:</b> <code>{total_added} item</code>\n"
        f"🛡️ <b>Garansi:</b> <b>{war_badge}</b>\n"
        f"📝 <b>Ketentuan:</b> <i>{warranty_note or '-'}</i>"
    )

    if isinstance(target, CallbackQuery) and isinstance(target.message, Message):
        await target.message.edit_text(
            text=msg_text,
            reply_markup=admin_main_kb(),
            parse_mode="HTML",
        )
        await target.answer()
    elif isinstance(target, Message):
        await target.answer(
            text=msg_text,
            reply_markup=admin_main_kb(),
            parse_mode="HTML",
        )


# ==========================================
# 3. BULK IMPORT STOK & RESTOCK NOTIFIER TRIGGER
# ==========================================
@router.callback_query(F.data == "admin_add_stock")
async def cb_start_add_stock(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    stmt = select(Product).where(Product.product_type == "TEXT_STOCK")
    res = await session.execute(stmt)
    products = list(res.scalars().all())

    if not products:
        await callback.answer("Belum ada produk bertipe Akun / Stok Teks!", show_alert=True)
        return

    await state.set_state(AddStockState.waiting_for_product)
    text = "📦 <b>PILIH PRODUK UNTUK DITAMBAH STOKNYA:</b>"
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=select_product_for_stock_kb(products),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AddStockState.waiting_for_product, F.data.startswith("adm_stock_"))
async def cb_pick_stock_product(callback: CallbackQuery, state: FSMContext) -> None:
    product_id = int(callback.data.replace("adm_stock_", ""))
    await state.update_data(product_id=product_id)
    await state.set_state(AddStockState.waiting_for_items_text)

    text = (
        "📥 <b>BULK INPUT STOK KREDENSIAL / LISENSI</b>\n\n"
        "Silakan paste kumpulan akun/serial key Anda di bawah ini.\n"
        "<b>Setiap 1 baris akan dihitung sebagai 1 stok unik</b>.\n\n"
        "<i>Contoh format yang dipaste:</i>\n"
        "<code>user1@mail.com:pass123\n"
        "user2@mail.com:pass456\n"
        "user3@mail.com:pass789</code>"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=cancel_admin_action_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(AddStockState.waiting_for_items_text)
async def process_stock_paste(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    lines = [line.strip() for line in message.text.split("\n") if line.strip()]
    if not lines:
        await message.answer("⚠️ Tidak ada teks yang terdeteksi. Silakan coba lagi.")
        return

    data = await state.get_data()
    product_id = data["product_id"]

    total_added = await crud.add_stock_items_bulk(
        session=session, product_id=product_id, contents=lines
    )
    product = await crud.get_product_by_id(session=session, product_id=product_id)
    new_total = await crud.count_available_stock(session=session, product_id=product_id)

    # Trigger Restock Notifier Broadcast ke pembeli yang menunggu
    waiting_users = await crud.get_and_clear_restock_subscribers(session=session, product_id=product_id)
    notif_sent = 0
    if waiting_users and product:
        for uid in waiting_users:
            try:
                alert_text = (
                    f"🔔 <b>PRODUK SUDAH RESTOCK!</b>\n\n"
                    f"Produk <b>{product.name}</b> yang Anda tunggu kini telah tersedia kembali!\n"
                    f"🟢 <b>Stok Baru:</b> <code>{new_total} item</code>\n"
                    f"💵 <b>Harga:</b> <code>Rp {product.price:,.0f}</code>\n\n"
                    f"<i>Buka menu /start -> 🛍️ Katalog Produk untuk memesan sekarang sebelum kehabisan!</i>"
                ).replace(",", ".")
                await bot.send_message(chat_id=uid, text=alert_text, parse_mode="HTML")
                notif_sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass

    await state.clear()
    
    stock_success_kb = InlineKeyboardBuilder()
    if product:
        stock_success_kb.row(
            InlineKeyboardButton(text="📢 Broadcast Garansi ke Pembeli", callback_data=f"adm_war_bcast_{product.id}"),
            InlineKeyboardButton(text="🛡️ Kelola Garansi Produk", callback_data=f"adm_war_prod_{product.id}"),
        )
    stock_success_kb.row(
        InlineKeyboardButton(text="🏠 Panel Admin", callback_data="admin_dashboard")
    )

    war_badge = "❌ Tidak Ada Garansi" if (product and product.warranty_type == "NONE") else ("⚡ Garansi 24 Jam" if (product and product.warranty_type == "24_HOURS") else "📝 Custom Garansi")

    await message.answer(
        f"✅ <b>STOK BERHASIL DITAMBAHKAN!</b>\n\n"
        f"📦 <b>Produk:</b> {product.name if product else '-'}\n"
        f"➕ <b>Jumlah Ditambahkan:</b> +{total_added} item\n"
        f"🟢 <b>Total Stok Tersedia:</b> {new_total} item\n"
        f"🛡️ <b>Status Garansi:</b> <b>{war_badge}</b>\n"
        f"🔔 <b>Notifikasi Restock Terkirim:</b> {notif_sent} Pembeli",
        reply_markup=stock_success_kb.as_markup(),
        parse_mode="HTML",
    )


# ==========================================
# 3.1 KELOLA GARANSI & BROADCAST KE PEMBELI
# ==========================================
async def broadcast_warranty_to_buyers(
    bot: Bot,
    session: AsyncSession,
    product: Product,
) -> int:
    """Mengirim pesan broadcast ketentuan garansi ke seluruh user yang pernah membeli produk ini."""
    buyers = await crud.get_product_buyers(session=session, product_id=product.id)
    if not buyers:
        return 0

    war_badge = "❌ Tidak Ada Garansi (No Garansi)" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam Penuh" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus (Custom)")
    war_note = product.warranty_note or "-"

    msg = (
        f"📢 <b>PEMBERITAHUAN KETENTUAN GARANSI PRODUK</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Halo Kak! Berikut informasi pembaruan ketentuan garansi resmi untuk produk yang pernah Anda beli:\n\n"
        f"📦 <b>Produk:</b> {product.name}\n"
        f"🛡️ <b>Status Garansi:</b> <b>{war_badge}</b>\n"
        f"📝 <b>Rincian & Syarat Garansi:</b>\n"
        f"<i>{war_note}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Jika Anda mengalami kendala selama periode garansi berlaku, Anda dapat mengajukan klaim garansi melalui menu Riwayat Transaksi -> Klaim Garansi.</i>"
    )

    success_count = 0
    for uid in buyers:
        try:
            await bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Gagal kirim broadcast garansi ke user {uid}: {e}")

    return success_count


@router.callback_query(F.data == "admin_manage_warranties")
async def cb_manage_warranties(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    stmt = select(Product).where(Product.is_active.is_(True))
    res = await session.execute(stmt)
    products = list(res.scalars().all())

    if not products:
        await callback.answer("Belum ada produk aktif!", show_alert=True)
        return

    text = (
        "🛡️ <b>PANEL KELOLA GARANSI & BROADCAST</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Pilih produk di bawah untuk melihat status garansi, mengubah ketentuan (No Garansi, 24 Jam, Custom), "
        "atau mem-broadcast info garansi ke seluruh pembeli produk tersebut:"
    )

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=text,
            reply_markup=select_product_for_warranty_kb(products),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_war_prod_"))
async def cb_select_product_warranty(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    if not callback.data:
        return
    product_id = int(callback.data.replace("adm_war_prod_", ""))
    product = await crud.get_product_by_id(session=session, product_id=product_id)
    if not product:
        await callback.answer("Produk tidak ditemukan!", show_alert=True)
        return

    buyers = await crud.get_product_buyers(session=session, product_id=product_id)
    war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Custom Garansi")
    war_note = product.warranty_note or "Belum ada catatan khusus."

    text = (
        f"🛡️ <b>DETAIL GARANSI: {product.name.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Tipe:</b> <code>{product.product_type}</code>\n"
        f"🛡️ <b>Status Garansi:</b> <b>{war_badge}</b>\n"
        f"📝 <b>Ketentuan/Note:</b>\n<i>{war_note}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Pembeli Terdaftar:</b> <code>{len(buyers)} Pengguna</code>\n\n"
        f"Pilih opsi di bawah untuk mengatur garansi atau kirim broadcast garansi ke seluruh pembeli produk ini:"
    )

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=text,
            reply_markup=product_warranty_action_kb(product_id=product.id),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_war_set_"))
async def cb_set_product_warranty(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    if not callback.data:
        return
    parts = callback.data.split("_")
    product_id = int(parts[3])
    war_type = parts[4]

    if war_type == "NONE":
        product = await crud.update_product_warranty(
            session=session,
            product_id=product_id,
            warranty_type="NONE",
            warranty_note="Tidak ada garansi untuk produk ini.",
        )
        sent = await broadcast_warranty_to_buyers(bot=bot, session=session, product=product) if product else 0
        await callback.answer(f"✅ Garansi diatur ke No Garansi. Broadcast terkirim ke {sent} pembeli!", show_alert=True)
        await cb_select_product_warranty(callback=callback, session=session)

    elif war_type == "24H":
        product = await crud.update_product_warranty(
            session=session,
            product_id=product_id,
            warranty_type="24_HOURS",
            warranty_note="Garansi aktif selama 24 jam sejak pembelian. Penggantian/perbaikan akun jika terjadi kendala login.",
        )
        sent = await broadcast_warranty_to_buyers(bot=bot, session=session, product=product) if product else 0
        await callback.answer(f"✅ Garansi diatur ke 24 Jam. Broadcast terkirim ke {sent} pembeli!", show_alert=True)
        await cb_select_product_warranty(callback=callback, session=session)

    elif war_type == "CUSTOM":
        await state.update_data(war_product_id=product_id)
        await state.set_state(AdminWarrantyState.waiting_for_custom_note)
        text = (
            "✍️ <b>INPUT CATATAN GARANSI KUSTOM</b>\n\n"
            "Silakan ketik catatan/ketentuan garansi Anda untuk produk ini:\n"
            "<i>(Contoh: Garansi replace 7 hari jika akun backfree / Garansi refund 3 hari dengan screenshot kendala)</i>"
        )
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=text,
                reply_markup=cancel_admin_action_kb(),
                parse_mode="HTML",
            )
        await callback.answer()


@router.message(AdminWarrantyState.waiting_for_custom_note)
async def process_admin_custom_warranty_note(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    data = await state.get_data()
    product_id = data["war_product_id"]
    note = (message.text or "").strip()
    await state.clear()

    product = await crud.update_product_warranty(
        session=session,
        product_id=product_id,
        warranty_type="CUSTOM",
        warranty_note=note,
    )

    sent = await broadcast_warranty_to_buyers(bot=bot, session=session, product=product) if product else 0

    await message.answer(
        f"✅ <b>GARANSI KUSTOM BERHASIL DISIMPAN!</b>\n\n"
        f"📦 <b>Produk:</b> {product.name if product else '-'}\n"
        f"🛡️ <b>Garansi:</b> <b>📝 Custom Garansi</b>\n"
        f"📝 <b>Ketentuan:</b> <i>{note}</i>\n"
        f"📢 <b>Broadcast Garansi Terkirim:</b> {sent} Pembeli",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm_war_bcast_"))
async def cb_broadcast_warranty_manually(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    if not callback.data:
        return
    product_id = int(callback.data.replace("adm_war_bcast_", ""))
    product = await crud.get_product_by_id(session=session, product_id=product_id)
    if not product:
        await callback.answer("Produk tidak ditemukan!", show_alert=True)
        return

    sent = await broadcast_warranty_to_buyers(bot=bot, session=session, product=product)
    await callback.answer(f"📢 Berhasil mengirim broadcast garansi ke {sent} pembeli!", show_alert=True)


# ==========================================
# 4. EXPORT LAPORAN PENJUALAN KE CSV / EXCEL
# ==========================================
@router.callback_query(F.data == "admin_export_csv")
async def cb_export_sales_csv(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    records = await crud.get_all_paid_transactions_for_export(session=session, limit=2000)

    if not records:
        await callback.answer("Belum ada transaksi lunas untuk diexport!", show_alert=True)
        return

    # Buat CSV di memori dengan UTF-8 BOM untuk Excel
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM
    writer = csv.writer(output, delimiter=";")

    # Tulis Header
    writer.writerow([
        "No. Invoice",
        "Waktu Transaksi",
        "Nama Produk",
        "Tipe Transaksi",
        "Metode Pembayaran",
        "Harga Normal (Rp)",
        "Potongan Diskon (Rp)",
        "Kode Promo",
        "Total Bersih (Rp)",
        "Telegram User ID",
        "Username Pembeli",
        "Nama Pembeli",
    ])

    for trx, prod, user in records:
        writer.writerow([
            trx.id,
            trx.paid_at.strftime("%Y-%m-%d %H:%M:%S") if trx.paid_at else trx.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            prod.name if prod else ("Top Up Saldo" if trx.trx_type == "TOPUP" else "-"),
            trx.trx_type,
            trx.payment_method,
            f"{trx.original_amount:.2f}",
            f"{trx.discount_amount:.2f}",
            trx.promo_code or "-",
            f"{trx.amount:.2f}",
            user.id,
            f"@{user.username}" if user.username else "-",
            user.first_name or "-",
        ])

    csv_data = output.getvalue().encode("utf-8")
    output.close()

    filename = f"Laporan_Penjualan_Aeternum_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    doc_file = BufferedInputFile(csv_data, filename=filename)

    if callback.message:
        await callback.message.answer_document(
            document=doc_file,
            caption=f"📊 <b>Laporan Penjualan Toko ({len(records)} Transaksi Lunas)</b>\n<i>Format CSV terstruktur siap dibuka di Microsoft Excel / Google Sheets.</i>",
            parse_mode="HTML",
        )
    await callback.answer("Laporan berhasil digenerate!")


# ==========================================
# 5. WIZARD BUAT KODE PROMO
# ==========================================
@router.callback_query(F.data == "admin_add_promo")
async def cb_start_add_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddPromoState.waiting_for_code)
    text = (
        "🎟️ <b>LANGKAH 1/4: BUAT KODE PROMO BARU</b>\n\n"
        "Silakan ketik nama kode promo/voucher yang ingin dibuat:\n"
        "<i>(Contoh: HEMAT10, RAMADHAN2026, VIPDISKON)</i>"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=cancel_admin_action_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(AddPromoState.waiting_for_code)
async def process_promo_code_name(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    await state.update_data(promo_code=code)
    await state.set_state(AddPromoState.waiting_for_type)

    await message.answer(
        "📊 <b>LANGKAH 2/4: JENIS POTONGAN DISKON</b>\n\nPilih metode potongan diskon:",
        reply_markup=select_discount_type_kb(),
        parse_mode="HTML",
    )


@router.callback_query(AddPromoState.waiting_for_type, F.data.startswith("promo_type_"))
async def cb_pick_discount_type(callback: CallbackQuery, state: FSMContext) -> None:
    disc_type = callback.data.replace("promo_type_", "")
    await state.update_data(discount_type=disc_type)
    await state.set_state(AddPromoState.waiting_for_value)

    example_text = "Masukkan angka persen (contoh: <code>15</code> untuk 15%):" if disc_type == "PERCENT" else "Masukkan nominal potongan Rupiah (contoh: <code>5000</code> untuk Rp 5.000):"
    text = f"💵 <b>LANGKAH 3/4: BESARAN DISKON</b>\n\n{example_text}"

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=cancel_admin_action_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(AddPromoState.waiting_for_value)
async def process_promo_value(message: Message, state: FSMContext) -> None:
    try:
        val = float(message.text.strip().replace(".", "").replace(",", ""))
    except ValueError:
        await message.answer("⚠️ Format angka salah! Masukkan hanya angka:")
        return

    await state.update_data(discount_value=val)
    await state.set_state(AddPromoState.waiting_for_max_usage)

    await message.answer(
        "👥 <b>LANGKAH 4/4: KUOTA MAKSIMAL PENGGUNAAN</b>\n\n"
        "Berapa kali kupon ini dapat digunakan secara keseluruhan?\n"
        "<i>(Contoh: <code>50</code> untuk 50 transaksi pertama)</i>",
        parse_mode="HTML",
    )


@router.message(AddPromoState.waiting_for_max_usage)
async def process_promo_final(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    try:
        max_usage = int(message.text.strip())
    except ValueError:
        max_usage = 100

    data = await state.get_data()
    promo = await crud.create_promo_code(
        session=session,
        code=data["promo_code"],
        discount_type=data["discount_type"],
        discount_value=data["discount_value"],
        max_usage=max_usage,
    )
    await state.clear()

    val_display = f"{promo.discount_value:.0f}%" if promo.discount_type == "PERCENT" else f"Rp {promo.discount_value:,.0f}".replace(",", ".")
    await message.answer(
        f"🎉 <b>KODE PROMO BERHASIL DIBUAT!</b>\n\n"
        f"🏷️ <b>Kode:</b> <code>{promo.code}</code>\n"
        f"✂️ <b>Potongan:</b> {val_display}\n"
        f"👥 <b>Kuota:</b> {promo.max_usage} kali penggunaan\n\n"
        f"<i>Pengguna sekarang dapat memasukkan kode ini saat checkout belanja.</i>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )


# ==========================================
# 6. BROADCAST NOTIFIKASI MASSAL
# ==========================================
@router.callback_query(F.data == "admin_broadcast")
async def cb_start_broadcast(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    user_ids = await crud.get_all_user_ids(session=session)
    await state.set_state(BroadcastState.waiting_for_message)

    text = (
        f"📢 <b>BROADCAST PESAN MASSAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Penerima Terdaftar: <b>{len(user_ids)} Pengguna</b>\n\n"
        f"Silakan kirim pesan yang ingin disiarkan ke seluruh pengguna (bisa berupa teks, foto + teks, atau dokumen):"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=cancel_admin_action_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(BroadcastState.waiting_for_message)
async def process_broadcast_input(message: Message, state: FSMContext) -> None:
    await state.update_data(
        broadcast_chat_id=message.chat.id,
        broadcast_msg_id=message.message_id,
    )
    await state.set_state(BroadcastState.waiting_for_confirmation)

    await message.answer(
        "👁️ <b>PREVIEW PESAN BROADCAST TERVERIFIKASI</b>\n\n"
        "Pesan di atas akan dikirimkan ke seluruh pengguna bot. Apakah Anda yakin ingin melanjutkan?",
        reply_markup=confirm_broadcast_kb(),
        parse_mode="HTML",
    )


@router.callback_query(BroadcastState.waiting_for_confirmation, F.data == "confirm_send_broadcast")
async def cb_execute_broadcast(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    data = await state.get_data()
    src_chat_id = data["broadcast_chat_id"]
    src_msg_id = data["broadcast_msg_id"]
    await state.clear()

    user_ids = await crud.get_all_user_ids(session=session)
    if callback.message:
        await callback.message.edit_text("⏳ <i>Sedang mengirimkan siaran pesan... Mohon tunggu.</i>", parse_mode="HTML")

    success_count = 0
    failed_count = 0

    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=src_chat_id,
                message_id=src_msg_id,
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed_count += 1

    summary_text = (
        f"✅ <b>BROADCAST SELESAI DIKIRIMKAN!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>Berhasil Terkirim:</b> {success_count} Pengguna\n"
        f"🔴 <b>Gagal / Diblokir:</b> {failed_count} Pengguna\n"
        f"👥 <b>Total Target:</b> {len(user_ids)} Pengguna"
    )

    if callback.message:
        await callback.message.answer(
            text=summary_text,
            reply_markup=admin_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer("Broadcast selesai!")


# ==========================================
# 7. LAPORAN OMSET & TRANSAKSI
# ==========================================
@router.message(Command("laporan"))
@router.callback_query(F.data == "admin_reports")
async def show_admin_reports(
    event: Message | CallbackQuery, session: AsyncSession
) -> None:
    user = event.from_user
    if not user or not is_admin_filter(user.id):
        return

    stmt_sales = select(
        func.count(Transaction.id), func.sum(Transaction.amount)
    ).where(Transaction.status == "PAID")
    res_sales = await session.execute(stmt_sales)
    total_trx, total_omset = res_sales.one()

    total_trx = total_trx or 0
    total_omset = total_omset or 0.0

    total_prods = (
        await session.execute(select(func.count(Product.id)))
    ).scalar_one()
    total_cats = (
        await session.execute(select(func.count(Category.id)))
    ).scalar_one()

    formatted_omset = f"Rp {total_omset:,.0f}".replace(",", ".")

    text = (
        f"📊 <b>LAPORAN PENJUALAN TOKO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Total Omset Lunas:</b> <code>{formatted_omset}</code>\n"
        f"🧾 <b>Total Transaksi Sukses:</b> <code>{total_trx} Pesanan</code>\n"
        f"📦 <b>Total Produk Aktif:</b> <code>{total_prods} Produk</code>\n"
        f"📁 <b>Total Kategori:</b> <code>{total_cats} Kategori</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Laporan ini dihitung secara real-time dari database PostgreSQL.</i>"
    )

    if isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(
            text=text,
            reply_markup=admin_main_kb(),
            parse_mode="HTML",
        )
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(
            text=text,
            reply_markup=admin_main_kb(),
            parse_mode="HTML",
        )
