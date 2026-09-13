"""
Aeternum PremiApp Bot - Admin Management & FSM Handlers
Panel khusus Admin untuk tambah produk, input stok akun massal, kupon diskon, broadcast, dan laporan.
"""

import asyncio
from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from database.models import Category, Product, PromoCode, Transaction
from bot.keyboards.admin_kb import (
    admin_main_kb,
    cancel_admin_action_kb,
    confirm_broadcast_kb,
    select_category_kb,
    select_discount_type_kb,
    select_product_for_stock_kb,
    select_product_type_kb,
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
    waiting_for_price = State()
    waiting_for_desc = State()


class AddStockState(StatesGroup):
    waiting_for_product = State()
    waiting_for_items_text = State()


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
    return user_id == settings.ADMIN_ID


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
        f"⚙️ <b>PANEL ADMIN - Aeternum PremiApp Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Selamat datang di pusat manajemen toko digital Anda.\n"
        f"Silakan pilih menu manajemen di bawah ini:"
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
    text = "📁 <b>LANGKAH 1/5: PILIH KATEGORI PRODUK</b>\n\nPilih kategori untuk produk baru ini:"
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
        "📦 <b>LANGKAH 2/5: PILIH JENIS PRODUK DIGITAL</b>\n\n"
        "• <b>Akun / Serial Key</b>: Sistem stok habis pakai (dikirim 1 baris per pembeli).\n"
        "• <b>Teks Statis</b>: Link / Template / Prompt yang sama untuk semua pembeli.\n"
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
        "📝 <b>LANGKAH 3/5: NAMA PRODUK</b>\n\n"
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
    await state.set_state(AddProductState.waiting_for_price)

    await message.answer(
        "💵 <b>LANGKAH 4/5: HARGA PRODUK</b>\n\n"
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
        "📄 <b>LANGKAH 5/5: DESKRIPSI & SYARAT GARANSI</b>\n\n"
        "Ketik deskripsi produk, rincian fitur, dan ketentuan garansi:\n"
        "<i>(Ketik <code>-</code> jika ingin mengosongkan deskripsi)</i>",
        parse_mode="HTML",
    )


@router.message(AddProductState.waiting_for_desc)
async def process_product_desc(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    desc = message.text.strip()
    if desc == "-":
        desc = None

    data = await state.get_data()
    p_type = data["product_type"]

    product = await crud.create_product(
        session=session,
        category_id=data["category_id"],
        name=data["name"],
        price=data["price"],
        product_type=p_type,
        description=desc,
    )
    await state.clear()

    formatted_price = f"Rp {product.price:,.0f}".replace(",", ".")
    await message.answer(
        f"🎉 <b>PRODUK BERHASIL DITAMBAHKAN!</b>\n\n"
        f"📦 <b>Nama:</b> {product.name}\n"
        f"💵 <b>Harga:</b> {formatted_price}\n"
        f"🏷️ <b>Tipe:</b> <code>{product.product_type}</code>\n\n"
        f"<i>💡 Jika tipe produk adalah Akun / Serial Key, silakan isi stok melalui menu 'Tambah Stok'.</i>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )


# ==========================================
# 3. BULK IMPORT STOK AKUN / TEKS
# ==========================================
@router.callback_query(F.data == "admin_add_stock")
async def cb_start_add_stock(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    stmt = select(Product).where(Product.product_type == "TEXT_STOCK")
    res = await session.execute(stmt)
    products = list(res.scalars().all())

    if not products:
        await callback.answer(
            "Belum ada produk bertipe Akun / Stok Teks!", show_alert=True
        )
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
    message: Message, state: FSMContext, session: AsyncSession
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

    await state.clear()
    await message.answer(
        f"✅ <b>STOK BERHASIL DITAMBAHKAN!</b>\n\n"
        f"📦 <b>Produk:</b> {product.name if product else '-'}\n"
        f"➕ <b>Jumlah Ditambahkan:</b> +{total_added} item\n"
        f"🟢 <b>Total Stok Tersedia Sekarang:</b> {new_total} item",
        reply_markup=admin_main_kb(),
        parse_mode="HTML",
    )


# ==========================================
# 4. WIZARD BUAT KODE PROMO / VOUCHER
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
# 5. BROADCAST NOTIFIKASI MASSAL
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
    # Simpan message_id dan chat_id untuk dicopy saat broadcast
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
            await asyncio.sleep(0.05)  # Anti flood-limit (max 20-30 msg/sec)
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
# 6. LAPORAN OMSET & TRANSAKSI
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
