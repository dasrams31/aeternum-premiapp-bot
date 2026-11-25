"""
Aeternum PremiApp Bot - Catalog & Product Browsing Handlers
"""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from bot.keyboards.user_kb import (
    NAV_CATALOG,
    back_to_main_kb,
    categories_kb,
    product_detail_kb,
    products_kb,
)

router = Router(name="catalog_router")


def _is_group_chat(message) -> bool:
    """True bila pesan berasal dari grup/supergrup (bukan DM bot).

    Dipakai guard checkout-ke-DM (aturan terkunci 25 Nov 2026): detail
    produk boleh dibuka di grup, tapi tombol bayar di sana harus berupa
    deep-link ke DM, bukan callback yang menerbitkan invoice di grup.
    """
    return bool(message) and message.chat.type in ("group", "supergroup")


class ApplyPromoState(StatesGroup):
    waiting_for_code = State()


@router.message(StateFilter(None), F.text == NAV_CATALOG)
@router.callback_query(F.data == "user_catalog")
async def cb_show_categories(
    event: Message | CallbackQuery, session: AsyncSession
) -> None:
    categories = await crud.get_categories(session=session, only_active=True)

    if not categories:
        text = (
            "🛍️ <b>KATALOG PRODUK</b>\n\n"
            "Saat ini belum ada kategori produk yang tersedia. Silakan cek kembali beberapa saat lagi!"
        )
        if isinstance(event, CallbackQuery) and event.message:
            await event.message.edit_text(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
            await event.answer()
        elif isinstance(event, Message):
            await event.answer(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        return

    text = (
        "🛍️ <b>KATALOG PRODUK DIGITAL</b>\n\n"
        "Silakan pilih kategori produk di bawah ini untuk melihat daftar produk yang tersedia:"
    )

    if isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(
            text=text,
            reply_markup=categories_kb(categories),
            parse_mode="HTML",
        )
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(
            text=text,
            reply_markup=categories_kb(categories),
            parse_mode="HTML",
        )


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
        stock = await crud.count_available_stock(session=session, product_id=prod.id)
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


async def render_product_detail(
    session, product_id, user_id, quantity: int = 1,
    current_price: float | None = None, has_promo: bool = False,
    in_group: bool = False,
):
    """Bangun (teks, keyboard) detail produk.

    Dipakai handler detail katalog dan deep-link /start product_<id> /
    /start remind_<id> supaya tampilannya selalu sama.
    quantity: jumlah pembelian yang sedang dipilih (1-10, default 1 =
    tampilan lama). current_price: harga satuan setelah promo bila ada.
    in_group: True bila detail dibuka di grup; tombol bayar diganti
    deep-link checkout ke DM bot (invoice tidak pernah terbit di grup).
    """
    product = await crud.get_product_by_id(session=session, product_id=product_id)
    if not product:
        return None

    db_user = await crud.get_user_by_id(session=session, user_id=user_id)
    user_balance = float(db_user.balance or 0.0) if db_user else 0.0

    is_available = True
    stock_count = await crud.count_available_stock(session=session, product_id=product.id)

    if getattr(product, "is_out_of_stock", False):
        stock_info = "🔴 <b>Jumlah Stok:</b> <i>Belum Tersedia</i>"
        is_available = False
    elif product.product_type == "TEXT_STOCK":
        if stock_count > 0:
            stock_info = f"🟢 <b>Jumlah Stok:</b> <code>{stock_count} Akun / Serial Key</code>"
        else:
            stock_info = "🔴 <b>Jumlah Stok:</b> <i>Habis (Stok Kosong)</i>"
            is_available = False
    else:
        if stock_count > 0:
            stock_info = f"🟢 <b>Jumlah Stok:</b> <code>{stock_count} Item</code> (Pengiriman Instan)"
        else:
            stock_info = "🟢 <b>Jumlah Stok:</b> <code>Tersedia (Ready Instan 24/7)</code>"

    max_quantity = await crud.max_order_quantity(session, product)
    quantity = max(1, min(int(quantity or 1), max(1, max_quantity))) if is_available else 1
    unit_price = float(current_price) if current_price else float(product.price)

    formatted_price = f"Rp {product.price:,.0f}".replace(",", ".")
    formatted_balance = f"Rp {user_balance:,.0f}".replace(",", ".")
    desc_text = product.description or "Tidak ada deskripsi tambahan."
    dur_str = product.duration_label or (f"{product.duration_days} Hari" if product.duration_days else "Lifetime / Permanen")
    duration_info = f"\n⏱️ <b>Masa Aktif:</b> <code>{dur_str}</code>"

    war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus")
    war_info = f"\n🛡️ <b>Garansi:</b> <b>{war_badge}</b>"
    if product.warranty_note:
        war_info += f" <i>({product.warranty_note})</i>"

    # Baris jumlah hanya tampil bila qty > 1; qty=1 tampilannya identik lama.
    qty_line = ""
    if quantity > 1:
        fmt_unit = f"Rp {unit_price:,.0f}".replace(",", ".")
        fmt_total = f"Rp {unit_price * quantity:,.0f}".replace(",", ".")
        qty_line = f"\n🔢 <b>Jumlah:</b> <code>{quantity}x @ {fmt_unit}</code> = <code>{fmt_total}</code>"

    text = (
        f"📦 <b>DETAIL PRODUK: {product.name.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga:</b> <code>{formatted_price}</code>{qty_line}\n"
        f"💳 <b>Saldo Anda:</b> <code>{formatted_balance}</code>\n"
        f"{stock_info}{duration_info}{war_info}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Deskripsi & Ketentuan:</b>\n"
        f"{desc_text}\n\n"
        f"<i>💡 Pilih opsi pembayaran di bawah untuk memproses pesanan:</i>"
    )

    is_subscribed = False
    if not is_available:
        is_subscribed = await crud.is_restock_subscribed(
            session=session, product_id=product.id, user_id=user_id
        )

    kb = product_detail_kb(
        product=product,
        is_available=is_available,
        user_balance=user_balance,
        current_price=unit_price,
        has_promo=has_promo,
        is_subscribed=is_subscribed,
        quantity=quantity,
        max_quantity=max_quantity,
        in_group=in_group,
    )
    return text, kb


@router.callback_query(F.data.startswith("prod_"))
async def cb_show_product_detail(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    user = callback.from_user
    product_id = int(callback.data.split("_")[1])
    rendered = await render_product_detail(
        session, product_id, user.id, in_group=_is_group_chat(callback.message)
    )
    if not rendered:
        await callback.answer("Produk tidak ditemukan!", show_alert=True)
        return
    text, kb = rendered
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    await callback.answer()


# ==========================================
# STEPPER JUMLAH PEMBELIAN (1-10)
# ==========================================
@router.callback_query(F.data.startswith("qtyplus_"))
@router.callback_query(F.data.startswith("qtyminus_"))
async def cb_change_quantity(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Ubah jumlah pembelian di state lalu render ulang detail produk."""
    is_plus = callback.data.startswith("qtyplus_")
    product_id = int(callback.data.replace("qtyplus_", "").replace("qtyminus_", ""))
    product = await crud.get_product_by_id(session=session, product_id=product_id)
    if not product or not product.is_active:
        await callback.answer("Produk tidak tersedia!", show_alert=True)
        return

    max_quantity = await crud.max_order_quantity(session, product)
    if max_quantity < 1:
        await callback.answer("Stok produk ini baru saja habis!", show_alert=True)
        return

    state_data = await state.get_data()
    qty = int(state_data.get(f"qty_{product_id}", 1) or 1)
    qty = qty + 1 if is_plus else qty - 1
    qty = max(1, min(qty, max_quantity))
    await state.update_data({f"qty_{product_id}": qty})

    unit_price = float(state_data.get("final_price", float(product.price)) or float(product.price))
    has_promo = bool(state_data.get("applied_promo_code"))
    rendered = await render_product_detail(
        session, product_id, callback.from_user.id,
        quantity=qty, current_price=unit_price, has_promo=has_promo,
        in_group=_is_group_chat(callback.message),
    )
    if rendered and callback.message:
        text, kb = rendered
        try:
            await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith("qtyinfo_"))
async def cb_quantity_info(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Tombol tengah stepper: tampilkan total harga jumlah saat ini."""
    product_id = int(callback.data.replace("qtyinfo_", ""))
    product = await crud.get_product_by_id(session=session, product_id=product_id)
    if not product:
        await callback.answer()
        return
    state_data = await state.get_data()
    qty = int(state_data.get(f"qty_{product_id}", 1) or 1)
    max_quantity = await crud.max_order_quantity(session, product)
    qty = max(1, min(qty, max(1, max_quantity)))
    unit_price = float(state_data.get("final_price", float(product.price)) or float(product.price))
    total = unit_price * qty
    await callback.answer(
        f"Jumlah: {qty}x @ Rp {unit_price:,.0f} = Rp {total:,.0f}".replace(",", "."),
        show_alert=False,
    )


# ==========================================
# RESTOCK NOTIFIER SUBSCRIPTION
# ==========================================
@router.callback_query(F.data.startswith("restock_alert_"))
async def cb_subscribe_restock(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    product_id = int(callback.data.replace("restock_alert_", ""))
    success, msg = await crud.subscribe_restock_alert(
        session=session,
        product_id=product_id,
        user_id=callback.from_user.id,
    )
    await _refresh_product_detail_message(callback, session, product_id, state)
    await callback.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("restock_unalert_"))
async def cb_unsubscribe_restock(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    product_id = int(callback.data.replace("restock_unalert_", ""))
    success, msg = await crud.unsubscribe_restock_alert(
        session=session,
        product_id=product_id,
        user_id=callback.from_user.id,
    )
    await _refresh_product_detail_message(callback, session, product_id, state)
    await callback.answer(msg, show_alert=True)


async def _refresh_product_detail_message(callback, session, product_id, state=None) -> None:
    """Render ulang pesan detail produk (teks + keyboard) setelah tombol
    pengingat ditekan, supaya tombol langsung berubah (🔔 <-> 🔕).
    Bila state tersedia, jumlah + promo yang sedang dipilih dipertahankan."""
    if not callback.message:
        return
    quantity = 1
    current_price = None
    has_promo = False
    if state is not None:
        state_data = await state.get_data()
        quantity = int(state_data.get(f"qty_{product_id}", 1) or 1)
        current_price = state_data.get("final_price")
        has_promo = bool(state_data.get("applied_promo_code"))
    rendered = await render_product_detail(
        session, product_id, callback.from_user.id,
        quantity=quantity, current_price=current_price, has_promo=has_promo,
        in_group=_is_group_chat(callback.message),
    )
    if not rendered:
        return
    text, kb = rendered
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


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

    # Jumlah yang sedang dipilih ikut menentukan total (qty=1: sama seperti lama).
    max_quantity = await crud.max_order_quantity(session, product)
    quantity = max(1, min(int(data.get(f"qty_{product_id}", 1) or 1), max(1, max_quantity)))

    fmt_orig = f"Rp {product.price:,.0f}".replace(",", ".")
    fmt_disc = f"Rp {discount_amount:,.0f}".replace(",", ".")
    fmt_final = f"Rp {final_price:,.0f}".replace(",", ".")
    if quantity > 1:
        fmt_total = f"Rp {final_price * quantity:,.0f}".replace(",", ".")
        total_line = (
            f"🏷️ <b>Harga Satuan:</b> <code>{fmt_final}</code>\n"
            f"💵 <b>Total Pembayaran ({quantity}x):</b> <code>{fmt_total}</code>\n"
        )
    else:
        total_line = f"💵 <b>Total Pembayaran:</b> <code>{fmt_final}</code>\n"

    text = (
        f"🎉 <b>KODE PROMO BERHASIL DIGUNAKAN!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Produk:</b> {product.name}\n"
        f"🏷️ <b>Kode Kupon:</b> <code>{promo.code}</code>\n"
        f"💰 <b>Harga Awal:</b> <s>{fmt_orig}</s>\n"
        f"✂️ <b>Potongan Diskon:</b> -{fmt_disc}\n"
        f"{total_line}"
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
            quantity=quantity,
            max_quantity=max_quantity,
            in_group=_is_group_chat(message),
        ),
        parse_mode="HTML",
    )
