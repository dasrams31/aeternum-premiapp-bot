"""
Aeternum PremiApp Bot - Catalog & Product Browsing Handlers
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from bot.keyboards.user_kb import (
    back_to_main_kb,
    categories_kb,
    product_detail_kb,
    products_kb,
)

router = Router(name="catalog_router")


class ApplyPromoState(StatesGroup):
    waiting_for_code = State()


@router.callback_query(F.data == "user_catalog")
async def cb_show_categories(callback: CallbackQuery, session: AsyncSession) -> None:
    categories = await crud.get_categories(session=session, only_active=True)

    if not categories:
        text = (
            "🛍️ <b>KATALOG PRODUK</b>\n\n"
            "Saat ini belum ada kategori produk yang tersedia. Silakan cek kembali beberapa saat lagi!"
        )
        if callback.message:
            await callback.message.edit_text(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        await callback.answer()
        return

    text = (
        "🛍️ <b>KATALOG PRODUK DIGITAL</b>\n\n"
        "Silakan pilih kategori produk di bawah ini untuk melihat daftar produk yang tersedia:"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=categories_kb(categories),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_"))
async def cb_show_category_products(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    category_id = int(callback.data.split("_")[1])
    products = await crud.get_products_by_category(
        session=session, category_id=category_id, only_active=True
    )

    if not products:
        text = (
            "📂 <b>DAFTAR PRODUK</b>\n\n"
            "Belum ada produk aktif dalam kategori ini."
        )
        if callback.message:
            await callback.message.edit_text(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        await callback.answer()
        return

    products_with_stock = []
    for prod in products:
        if prod.product_type == "TEXT_STOCK":
            stock = await crud.count_available_stock(session=session, product_id=prod.id)
        else:
            stock = 999
        products_with_stock.append((prod, stock))

    text = (
        "📂 <b>PILIH PRODUK DIGITAL</b>\n\n"
        "Berikut adalah daftar produk yang tersedia. Ketuk salah satu untuk melihat deskripsi lengkap:"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=products_kb(products_with_stock),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("prod_"))
async def cb_show_product_detail(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    user = callback.from_user
    product_id = int(callback.data.split("_")[1])
    product = await crud.get_product_by_id(session=session, product_id=product_id)

    if not product:
        await callback.answer("Produk tidak ditemukan!", show_alert=True)
        return

    db_user = await crud.get_user_by_id(session=session, user_id=user.id)
    user_balance = float(db_user.balance or 0.0) if db_user else 0.0

    is_available = True
    stock_info = "⚡ <b>Pengiriman:</b> Instan 24/7 (Teks / File)"

    if product.product_type == "TEXT_STOCK":
        stock_count = await crud.count_available_stock(session=session, product_id=product.id)
        if stock_count > 0:
            stock_info = f"🟢 <b>Stok Tersedia:</b> <code>{stock_count} Akun / Key</code>"
        else:
            stock_info = "🔴 <b>Stok Tersedia:</b> <i>Habis</i>"
            is_available = False

    formatted_price = f"Rp {product.price:,.0f}".replace(",", ".")
    formatted_balance = f"Rp {user_balance:,.0f}".replace(",", ".")
    desc_text = product.description or "Tidak ada deskripsi tambahan."
    dur_str = product.duration_label or (f"{product.duration_days} Hari" if product.duration_days else "Lifetime / Permanen")
    duration_info = f"\n⏱️ <b>Masa Aktif:</b> <code>{dur_str}</code>"

    war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus")
    war_info = f"\n🛡️ <b>Garansi:</b> <b>{war_badge}</b>"
    if product.warranty_note:
        war_info += f" <i>({product.warranty_note})</i>"

    text = (
        f"📦 <b>DETAIL PRODUK: {product.name.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga:</b> <code>{formatted_price}</code>\n"
        f"💳 <b>Saldo Anda:</b> <code>{formatted_balance}</code>\n"
        f"{stock_info}{duration_info}{war_info}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Deskripsi & Ketentuan:</b>\n"
        f"{desc_text}\n\n"
        f"<i>💡 Pilih opsi pembayaran di bawah untuk memproses pesanan:</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=product_detail_kb(
                product=product,
                is_available=is_available,
                user_balance=user_balance,
                current_price=float(product.price),
            ),
            parse_mode="HTML",
        )
    await callback.answer()


# ==========================================
# RESTOCK NOTIFIER SUBSCRIPTION
# ==========================================
@router.callback_query(F.data.startswith("restock_alert_"))
async def cb_subscribe_restock(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    product_id = int(callback.data.replace("restock_alert_", ""))
    success, msg = await crud.subscribe_restock_alert(
        session=session,
        product_id=product_id,
        user_id=callback.from_user.id,
    )
    await callback.answer(msg, show_alert=True)


# ==========================================
# APLIKASI KODE PROMO (VOUCHER)
# ==========================================
@router.callback_query(F.data.startswith("apply_promo_"))
async def cb_prompt_promo(callback: CallbackQuery, state: FSMContext) -> None:
    product_id = int(callback.data.replace("apply_promo_", ""))
    await state.update_data(promo_product_id=product_id)
    await state.set_state(ApplyPromoState.waiting_for_code)

    text = (
        "🎟️ <b>MASUKKAN KODE PROMO / VOUCHER</b>\n\n"
        "Silakan ketik kode kupon promo Anda di bawah ini:\n"
        "<i>(Contoh: HEMAT10, RAMADHAN, AETERNUM2026)</i>"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(ApplyPromoState.waiting_for_code)
async def process_promo_input(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    code_input = message.text.strip()
    data = await state.get_data()
    product_id = data.get("promo_product_id")

    product = await crud.get_product_by_id(session=session, product_id=product_id)
    if not product:
        await message.answer("Produk tidak ditemukan.", reply_markup=back_to_main_kb())
        await state.clear()
        return

    is_valid, msg, discount_amount, promo = await crud.validate_and_apply_promo(
        session=session,
        code_str=code_input,
        user_id=message.from_user.id,
        original_price=float(product.price),
    )

    if not is_valid or not promo:
        await message.answer(
            f"{msg}\n\nSilakan coba kode lain atau kembali ke katalog:",
            reply_markup=back_to_main_kb(),
        )
        return

    final_price = float(product.price) - discount_amount
    await state.update_data(
        applied_promo_code=promo.code,
        applied_discount=discount_amount,
        final_price=final_price,
    )

    db_user = await crud.get_user_by_id(session=session, user_id=message.from_user.id)
    user_balance = float(db_user.balance or 0.0) if db_user else 0.0

    fmt_orig = f"Rp {product.price:,.0f}".replace(",", ".")
    fmt_disc = f"Rp {discount_amount:,.0f}".replace(",", ".")
    fmt_final = f"Rp {final_price:,.0f}".replace(",", ".")

    text = (
        f"🎉 <b>KODE PROMO BERHASIL DIGUNAKAN!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Produk:</b> {product.name}\n"
        f"🏷️ <b>Kode Kupon:</b> <code>{promo.code}</code>\n"
        f"💰 <b>Harga Awal:</b> <s>{fmt_orig}</s>\n"
        f"✂️ <b>Potongan Diskon:</b> -{fmt_disc}\n"
        f"💵 <b>Total Pembayaran:</b> <code>{fmt_final}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Pilih metode pembayaran di bawah untuk menyelesaikan pesanan:</i>"
    )

    await message.answer(
        text=text,
        reply_markup=product_detail_kb(
            product=product,
            is_available=True,
            user_balance=user_balance,
            current_price=final_price,
            has_promo=True,
        ),
        parse_mode="HTML",
    )
