"""
Aeternum PremiApp Bot - Order & QRIS Payment Handlers
"""

from datetime import datetime, timedelta
import io
import logging
import qrcode
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from bot.keyboards.user_kb import back_to_main_kb, invoice_kb
from bot.services.fulfillment import deliver_purchased_product

logger = logging.getLogger(__name__)
router = Router(name="order_router")


def generate_qr_image(payload: str) -> BufferedInputFile:
    """Generate gambar QR Code dari string QRIS dinamis."""
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=2,
    )
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
    """Membuat pesanan baru dan menampilkan Invoice QRIS."""
    user = callback.from_user
    product_id = int(callback.data.split("_")[1])
    product = await crud.get_product_by_id(session=session, product_id=product_id)

    if not product or not product.is_active:
        await callback.answer("Produk tidak tersedia!", show_alert=True)
        return

    # Validasi stok jika tipe TEXT_STOCK
    if product.product_type == "TEXT_STOCK":
        stock = await crud.count_available_stock(session=session, product_id=product.id)
        if stock <= 0:
            await callback.answer("Mohon maaf, stok baru saja habis!", show_alert=True)
            return

    # Cek apakah ada promo yang diaplikasikan di state
    state_data = await state.get_data()
    promo_code = state_data.get("applied_promo_code")
    discount_amount = state_data.get("applied_discount", 0.0)
    final_amount = state_data.get("final_price", float(product.price))
    await state.clear()

    # Buat ID Invoice Unik (Format: AP-YYYYMMDD-XXXX)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
    invoice_id = f"AP-{timestamp}-{user.id % 10000:04d}"
    expired_at = datetime.utcnow() + timedelta(minutes=15)

    # String payload QRIS
    mock_qris_string = f"00020101021226670016ID.CO.QRIS.WWW01189360000000000000000215{invoice_id}520458125303360540{int(final_amount)}5802ID5914AETERNUM STORE6007JAKARTA6304"

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
        qris_string=mock_qris_string,
        expired_at=expired_at,
    )

    formatted_price = f"Rp {final_amount:,.0f}".replace(",", ".")
    discount_info = f"\n✂️ <b>Diskon Promo ({promo_code}):</b> -Rp {discount_amount:,.0f}".replace(",", ".") if promo_code else ""

    caption_text = (
        f"🧾 <b>INVOICE PEMBAYARAN QRIS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>No. Invoice:</b> <code>{invoice_id}</code>\n"
        f"📦 <b>Produk:</b> {product.name}\n"
        f"💰 <b>Harga Normal:</b> Rp {product.price:,.0f}".replace(",", ".") + f"{discount_info}\n"
        f"💵 <b>Total Tagihan:</b> <code>{formatted_price}</code>\n"
        f"⏰ <b>Batas Waktu:</b> 15 Menit\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>PETUNJUK PEMBAYARAN:</b>\n"
        f"1. Scan kode QR di atas menggunakan GoPay / OVO / DANA / BCA / Livin / ShopeePay.\n"
        f"2. Pastikan nominal transfer sesuai dengan total tagihan.\n"
        f"3. Setelah transfer berhasil, sistem akan mendeteksi pembayaran secara otomatis.\n"
        f"4. Atau tekan tombol <b>🔄 Cek Status Pembayaran</b> di bawah ini.\n"
    )

    qr_file = generate_qr_image(mock_qris_string)

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
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Pengecekan status pembayaran manual oleh pembeli."""
    invoice_id = callback.data.replace("check_trx_", "")
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)

    if not trx:
        await callback.answer("Invoice tidak ditemukan!", show_alert=True)
        return

    if trx.status == "PAID":
        await callback.answer("✅ Pembayaran sudah terkonfirmasi!", show_alert=True)
        return

    await callback.answer(
        "⏳ Pembayaran belum terdeteksi. Silakan selesaikan transfer lalu coba kembali dalam 10 detik.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cancel_trx_"))
async def cb_cancel_transaction(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Membatalkan invoice pesanan."""
    invoice_id = callback.data.replace("cancel_trx_", "")
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)

    if trx and trx.status == "PENDING":
        trx.status = "CANCELLED"
        await session.commit()

    text = (
        f"❌ <b>PESANAN DIBATALKAN</b>\n\n"
        f"Invoice <code>{invoice_id}</code> telah berhasil dibatalkan.\n"
        f"Anda dapat membuat pesanan baru kapan saja dari katalog produk."
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
    await callback.answer("Pesanan dibatalkan.")
