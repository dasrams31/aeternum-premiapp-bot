"""
Aeternum PremiApp Bot - Order & QRIS Payment Handlers
Terintegrasi langsung dengan Payment Gateway BAYAR GG (QRIS Dinamis API).
"""

from datetime import datetime, timedelta
import io
import logging
import qrcode
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from bot.keyboards.user_kb import back_to_main_kb, invoice_kb
from bot.services.fulfillment import deliver_purchased_product
from webhook.gateway import get_payment_gateway

logger = logging.getLogger(__name__)
router = Router(name="order_router")


def generate_qr_image(payload: str) -> BufferedInputFile:
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)
    return BufferedInputFile(img_byte_arr.getvalue(), filename="qris_payment.png")


@router.callback_query(F.data.startswith("buy_"))
async def cb_create_order(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    user = callback.from_user
    product_id = int(callback.data.split("_")[1])
    product = await crud.get_product_by_id(session=session, product_id=product_id)

    if not product or not product.is_active:
        await callback.answer("Produk tidak tersedia!", show_alert=True)
        return

    state_data = await state.get_data()
    promo_code = state_data.get("applied_promo_code")
    discount_amount = state_data.get("applied_discount", 0.0)
    final_amount = state_data.get("final_price", float(product.price))
    await state.clear()

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
    invoice_id = f"AP-{timestamp}-{user.id % 10000:04d}"
    expired_at = datetime.utcnow() + timedelta(minutes=15)

    # 1. KUNCI STOK SEMENTARA (15 MENIT)
    if product.product_type == "TEXT_STOCK":
        reserved_item = await crud.reserve_stock_item_atomic(
            session=session,
            product_id=product.id,
            transaction_id=invoice_id,
            duration_minutes=15,
        )
        if not reserved_item:
            await callback.answer(
                "Mohon maaf, stok produk ini baru saja habis atau sedang dalam proses pembayaran pembeli lain!",
                show_alert=True,
            )
            return

    # 2. REQUEST QRIS DINAMIS KE PAYMENT GATEWAY (BAYAR GG / TRIPAY)
    gateway = get_payment_gateway()
    gw_res = await gateway.create_qris_transaction(
        merchant_ref=invoice_id,
        amount=int(final_amount),
        customer_name=user.first_name or "Pembeli",
        description=f"Order #{invoice_id} - {product.name}",
    )

    qris_payload = ""
    gateway_ref = None
    pay_url = None

    if gw_res:
        qris_payload = gw_res.get("qris_string") or ""
        gateway_ref = gw_res.get("invoice_id")
        pay_url = gw_res.get("payment_url")

    # Fallback string jika gateway offline
    if not qris_payload:
        qris_payload = f"00020101021226670016ID.CO.QRIS.WWW01189360000000000000000215{invoice_id}520458125303360540{int(final_amount)}5802ID5914AETERNUM STORE6007JAKARTA6304"

    # Simpan transaksi ke database
    trx = await crud.create_transaction(
        session=session,
        invoice_id=invoice_id,
        user_id=user.id,
        product_id=product.id,
        amount=final_amount,
        original_amount=float(product.price),
        discount_amount=discount_amount,
        promo_code=promo_code,
        qris_string=qris_payload,
        gateway_reference=gateway_ref,
        expired_at=expired_at,
    )

    formatted_price = f"Rp {final_amount:,.0f}".replace(",", ".")
    discount_info = f"\n✂️ <b>Diskon Promo ({promo_code}):</b> -Rp {discount_amount:,.0f}".replace(",", ".") if promo_code else ""

    caption_text = (
        f"🧾 <b>INVOICE PEMBAYARAN QRIS RESMI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>No. Invoice:</b> <code>{invoice_id}</code>\n"
        f"📦 <b>Produk:</b> {product.name}\n"
        f"💰 <b>Harga Normal:</b> Rp {product.price:,.0f}".replace(",", ".") + f"{discount_info}\n"
        f"💵 <b>Total Tagihan:</b> <code>{formatted_price}</code>\n"
        f"🔒 <b>Stok:</b> <i>Terkunci untuk Anda (15 Menit)</i>\n"
        f"⏰ <b>Batas Waktu:</b> 15 Menit\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>PETUNJUK PEMBAYARAN:</b>\n"
        f"1. Scan kode QR di atas menggunakan GoPay / OVO / DANA / BCA / Livin / ShopeePay.\n"
        f"2. Pastikan nominal transfer sesuai dengan total tagihan.\n"
        f"3. Setelah transfer berhasil, sistem akan mendeteksi pembayaran secara otomatis.\n"
        f"4. Atau tekan tombol <b>🔄 Cek Status Pembayaran</b> di bawah ini.\n"
    )

    qr_file = generate_qr_image(qris_payload)

    if callback.message:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=qr_file,
            caption=caption_text,
            reply_markup=invoice_kb(invoice_id),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("check_trx_"))
async def cb_check_transaction(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    invoice_id = callback.data.replace("check_trx_", "")
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)

    if not trx:
        await callback.answer("Invoice tidak ditemukan!", show_alert=True)
        return

    if trx.status == "PAID":
        await callback.answer("✅ Pembayaran sudah terkonfirmasi lunas!", show_alert=True)
        return

    # Cek status live ke server Payment Gateway (BAYAR GG)
    gateway = get_payment_gateway()
    check_ref = trx.gateway_reference or trx.id
    status_data = await gateway.check_payment_status(check_ref)

    if status_data and status_data.get("status") in ["paid", "PAID", "SETTLEMENT"]:
        # Pembayaran telah lunas di gateway! Eksekusi pengiriman instan
        product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
        if product:
            await deliver_purchased_product(
                bot=bot, session=session, transaction=trx, product=product
            )
            if callback.message:
                await callback.message.delete()
            await callback.answer("🎉 Pembayaran Anda berhasil dikonfirmasi!", show_alert=True)
            return

    await callback.answer(
        "⏳ Pembayaran belum terdeteksi. Silakan selesaikan transfer lalu coba kembali dalam beberapa detik.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cancel_trx_"))
async def cb_cancel_transaction(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    invoice_id = callback.data.replace("cancel_trx_", "")
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)

    if trx and trx.status == "PENDING":
        trx.status = "CANCELLED"
        await session.commit()
        await crud.release_reserved_stock(session=session, transaction_id=invoice_id)

    text = (
        f"❌ <b>PESANAN DIBATALKAN</b>\n\n"
        f"Invoice <code>{invoice_id}</code> telah berhasil dibatalkan.\n"
        f"Stok produk telah dikembalikan ke sistem. Anda dapat membuat pesanan baru kapan saja."
    )

    if callback.message:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
    await callback.answer("Pesanan dibatalkan & stok dikembalikan.")
