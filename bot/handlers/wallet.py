"""
Aeternum PremiApp Bot - Wallet & Top Up Handlers
"""

from datetime import datetime, timedelta
import io
import qrcode
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from bot.keyboards.user_kb import (
    back_to_main_kb,
    insufficient_balance_kb,
    invoice_kb,
    topup_presets_kb,
    wallet_menu_kb,
)
from bot.services.fulfillment import deliver_purchased_product

router = Router(name="wallet_router")


class TopUpState(StatesGroup):
    waiting_for_custom_amount = State()


def generate_qr_image(payload: str) -> BufferedInputFile:
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)
    return BufferedInputFile(img_byte_arr.getvalue(), filename="topup_qris.png")


@router.callback_query(F.data == "user_wallet")
async def cb_show_wallet(callback: CallbackQuery, session: AsyncSession) -> None:
    user = callback.from_user
    db_user = await crud.get_user_by_id(session=session, user_id=user.id)
    balance = float(db_user.balance or 0.0) if db_user else 0.0
    ref_balance = float(db_user.referral_balance or 0.0) if db_user else 0.0

    fmt_bal = f"Rp {balance:,.0f}".replace(",", ".")
    fmt_ref = f"Rp {ref_balance:,.0f}".replace(",", ".")

    text = (
        f"💰 <b>DOMPET & SALDO PENGGUNA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Saldo Belanja Aktif:</b> <code>{fmt_bal}</code>\n"
        f"👥 <b>Saldo Komisi Afiliasi:</b> <code>{fmt_ref}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>💡 Keuntungan isi saldo: Anda dapat langsung checkout produk dalam 1 detik tanpa perlu scan QRIS setiap kali transaksi!</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=wallet_menu_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "wallet_topup")
async def cb_prompt_topup(callback: CallbackQuery) -> None:
    text = (
        "➕ <b>TOP UP SALDO VIA QRIS</b>\n\n"
        "Silakan pilih nominal saldo yang ingin Anda isi:"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=topup_presets_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_nom_"))
async def cb_topup_preset(callback: CallbackQuery, session: AsyncSession) -> None:
    amount = float(callback.data.replace("topup_nom_", ""))
    await create_topup_invoice(callback=callback, session=session, amount=amount)


@router.callback_query(F.data == "topup_custom")
async def cb_topup_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TopUpState.waiting_for_custom_amount)
    text = (
        "✏️ <b>NOMINAL TOP UP KUSTOM</b>\n\n"
        "Ketik nominal saldo yang ingin Anda isi (Minimal Rp 5.000):\n"
        "<i>(Contoh: 15000, 75000, 200000)</i>"
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(TopUpState.waiting_for_custom_amount)
async def process_custom_amount(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    try:
        amount = float(message.text.strip().replace(".", "").replace(",", ""))
        if amount < 5000:
            await message.answer("⚠️ Minimal top up adalah Rp 5.000. Silakan ketik ulang:")
            return
    except ValueError:
        await message.answer("⚠️ Masukkan hanya angka tanpa titik/koma:")
        return

    await state.clear()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
    invoice_id = f"TOPUP-{timestamp}-{message.from_user.id % 10000:04d}"
    expired_at = datetime.utcnow() + timedelta(minutes=15)

    mock_qris = f"00020101021226670016ID.CO.QRIS.WWW01189360000000000000000215{invoice_id}520458125303360540{int(amount)}5802ID5914AETERNUM TOPUP6007JAKARTA6304"

    trx = await crud.create_transaction(
        session=session,
        invoice_id=invoice_id,
        user_id=message.from_user.id,
        amount=amount,
        trx_type="TOPUP",
        qris_string=mock_qris,
        expired_at=expired_at,
    )

    fmt_amount = f"Rp {amount:,.0f}".replace(",", ".")
    caption = (
        f"🧾 <b>INVOICE TOP UP SALDO QRIS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>No. Invoice:</b> <code>{invoice_id}</code>\n"
        f"💵 <b>Nominal Top Up:</b> <code>{fmt_amount}</code>\n"
        f"⏰ <b>Batas Waktu:</b> 15 Menit\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <i>Scan QRIS di atas untuk menyelesaikan pengisian saldo. Saldo akan langsung bertambah otomatis ke akun Anda setelah pembayaran berhasil.</i>"
    )

    qr_file = generate_qr_image(mock_qris)
    await message.answer_photo(
        photo=qr_file,
        caption=caption,
        reply_markup=invoice_kb(invoice_id),
        parse_mode="HTML",
    )


async def create_topup_invoice(callback: CallbackQuery, session: AsyncSession, amount: float) -> None:
    user = callback.from_user
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
    invoice_id = f"TOPUP-{timestamp}-{user.id % 10000:04d}"
    expired_at = datetime.utcnow() + timedelta(minutes=15)

    mock_qris = f"00020101021226670016ID.CO.QRIS.WWW01189360000000000000000215{invoice_id}520458125303360540{int(amount)}5802ID5914AETERNUM TOPUP6007JAKARTA6304"

    trx = await crud.create_transaction(
        session=session,
        invoice_id=invoice_id,
        user_id=user.id,
        amount=amount,
        trx_type="TOPUP",
        qris_string=mock_qris,
        expired_at=expired_at,
    )

    fmt_amount = f"Rp {amount:,.0f}".replace(",", ".")
    caption = (
        f"🧾 <b>INVOICE TOP UP SALDO QRIS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>No. Invoice:</b> <code>{invoice_id}</code>\n"
        f"💵 <b>Nominal Top Up:</b> <code>{fmt_amount}</code>\n"
        f"⏰ <b>Batas Waktu:</b> 15 Menit\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <i>Scan QRIS di atas untuk menyelesaikan pengisian saldo. Saldo akan otomatis masuk ke akun Anda.</i>"
    )

    qr_file = generate_qr_image(mock_qris)
    if callback.message:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=qr_file,
            caption=caption,
            reply_markup=invoice_kb(invoice_id),
            parse_mode="HTML",
        )
    await callback.answer()


# ==========================================
# BAYAR PAKAI SALDO INTERNAL (INSTAN 1 DETIK)
# ==========================================
@router.callback_query(F.data.startswith("pay_balance_"))
async def cb_pay_with_balance(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext
) -> None:
    user = callback.from_user
    product_id = int(callback.data.replace("pay_balance_", ""))
    product = await crud.get_product_by_id(session=session, product_id=product_id)

    if not product or not product.is_active:
        await callback.answer("Produk tidak tersedia!", show_alert=True)
        return

    # Ambil promo jika ada di state
    state_data = await state.get_data()
    promo_code = state_data.get("applied_promo_code")
    discount_amount = state_data.get("applied_discount", 0.0)
    final_amount = state_data.get("final_price", float(product.price))

    db_user = await crud.get_user_by_id(session=session, user_id=user.id)
    current_balance = float(db_user.balance or 0.0) if db_user else 0.0

    # JIKA SALDO KURANG: Tampilkan layar bantuan topup / bayar QRIS
    if current_balance < final_amount:
        fmt_bal = f"Rp {current_balance:,.0f}".replace(",", ".")
        fmt_price = f"Rp {final_amount:,.0f}".replace(",", ".")
        fmt_shortage = f"Rp {final_amount - current_balance:,.0f}".replace(",", ".")

        text_insufficient = (
            f"⚠️ <b>SALDO BELANJA TIDAK MENCUKUPI</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Produk:</b> {product.name}\n"
            f"💵 <b>Total Tagihan:</b> <code>{fmt_price}</code>\n"
            f"💳 <b>Saldo Anda:</b> <code>{fmt_bal}</code>\n"
            f"🔴 <b>Kekurangan:</b> <code>{fmt_shortage}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Silakan <b>Top Up Saldo</b> terlebih dahulu atau langsung bayar via <b>QRIS</b> di bawah ini:"
        )

        if callback.message:
            await callback.message.edit_text(
                text=text_insufficient,
                reply_markup=insufficient_balance_kb(product_id),
                parse_mode="HTML",
            )
        await callback.answer("Saldo tidak mencukupi!", show_alert=False)
        return

    # JIKA SALDO CUKUP: Potong saldo secara atomic
    deducted = await crud.deduct_user_balance_atomic(
        session=session, user_id=user.id, amount=final_amount
    )

    if not deducted:
        await callback.answer("Gagal memotong saldo. Silakan coba kembali!", show_alert=True)
        return

    await state.clear()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
    invoice_id = f"BAL-{timestamp}-{user.id % 10000:04d}"

    trx = await crud.create_transaction(
        session=session,
        invoice_id=invoice_id,
        user_id=user.id,
        product_id=product.id,
        amount=final_amount,
        original_amount=float(product.price),
        discount_amount=discount_amount,
        promo_code=promo_code,
        trx_type="PURCHASE",
        payment_method="BALANCE",
    )

    # Kirim produk instan ke pembeli
    await deliver_purchased_product(
        bot=bot, session=session, transaction=trx, product=product
    )

    if callback.message:
        await callback.message.delete()

    await callback.answer("Pembayaran berhasil dipotong dari saldo!", show_alert=True)
