"""
Aeternum PremiApp Bot - Payment Proof Handlers (Kirim Bukti Pembayaran)

Pembeli yang membayar QRIS (beli produk maupun top-up saldo) tapi
pembayarannya tidak terkonfirmasi otomatis bisa mengirim foto/screenshot
bukti transfer lewat tombol "Kirim Bukti Pembayaran" di pesan invoice.

Alurnya:
- Pembeli mengetuk tombol -> bot meminta foto bukti (FSM state).
- Pembeli mengirim foto -> file_id + waktu kirim (aware UTC) disimpan di
  kolom payment_proof_file_id / proof_sent_at transaksi, lalu admin
  menerima DM berisi FOTO bukti + tombol Terima / Tolak / Abaikan
  (keyboard keputusan yang sama dengan notif PERCOBAAN CHECKOUT).
- Admin menekan Terima HANYA setelah mencocokkan bukti dengan
  mutasi/dashboard: produk/saldo dikirim lewat jalur fulfillment yang
  sama seperti auto-confirm. Tolak = REJECTED tanpa info ke pembeli.

Invoice TIDAK lagi kedaluwarsa (perintah user 11 Nov 2026), jadi bukti
bisa dikirim kapan pun selama status masih PENDING. Kirim ulang foto
mengganti bukti sebelumnya; yang terbaru yang dipakai admin.
"""

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from bot.services.broadcast import notify_admin_payment_proof

logger = logging.getLogger(__name__)
router = Router(name="payment_proof_router")


class PaymentProofState(StatesGroup):
    waiting_for_photo = State()


def _rupiah(amount) -> str:
    return f"Rp {float(amount or 0):,.0f}".replace(",", ".")


@router.callback_query(F.data.startswith("send_proof_"))
async def cb_send_proof(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Tombol 'Kirim Bukti Pembayaran' di pesan invoice QRIS (beli + top-up)."""
    invoice_id = callback.data.replace("send_proof_", "", 1)
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)

    if not trx:
        await callback.answer("Invoice tidak ditemukan!", show_alert=True)
        return

    if callback.from_user.id != trx.user_id:
        await callback.answer("Tombol ini hanya untuk pemilik pesanan ini.", show_alert=True)
        return

    if trx.status == "PAID":
        await callback.answer("Pembayaran sudah terkonfirmasi lunas.", show_alert=True)
        return

    if trx.status != "PENDING":
        # Netral seperti penolakan manual: jangan beri tahu pembeli soal
        # status pastinya, cukup bahwa bukti sudah tidak bisa diterima.
        await callback.answer(
            "Invoice ini sudah tidak dapat menerima bukti pembayaran.",
            show_alert=True,
        )
        return

    product = None
    if trx.product_id:
        product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
    product_label = product.name if product else "Top Up Saldo"

    await state.set_state(PaymentProofState.waiting_for_photo)
    await state.update_data(proof_invoice_id=invoice_id)

    text = (
        f"📤 <b>KIRIM BUKTI PEMBAYARAN</b>\n\n"
        f"🧾 <b>Invoice:</b> <code>{trx.id}</code>\n"
        f"📦 <b>Produk:</b> {product_label}\n"
        f"💰 <b>Nominal:</b> <code>{_rupiah(trx.amount)}</code>\n\n"
        f"Kirim foto/screenshot bukti transfer di chat ini. "
        f"Foto akan diteruskan ke admin untuk diverifikasi, lalu pesananmu "
        f"diproses setelah pembayaran terverifikasi.\n\n"
        f"<i>Kalau salah kirim, kirim ulang foto yang benar, foto terbaru yang dipakai. "
        f"Ketik batal kalau tidak jadi mengirim.</i>"
    )
    if callback.message:
        await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


async def _save_proof(
    message: Message, session: AsyncSession, state: FSMContext, file_id: str
) -> None:
    """Simpan file_id bukti + stempel waktu, teruskan fotonya ke admin."""
    data = await state.get_data()
    invoice_id = data.get("proof_invoice_id")
    if not invoice_id:
        await state.clear()
        await message.answer(
            "Sesi pengiriman bukti sudah berakhir. Ketuk lagi tombol "
            "Kirim Bukti Pembayaran di pesan invoice."
        )
        return

    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)
    if not trx or message.from_user.id != trx.user_id:
        await state.clear()
        await message.answer("Invoice tidak ditemukan.")
        return

    if trx.status == "PAID":
        await state.clear()
        await message.answer("Pembayaran sudah terkonfirmasi lunas, bukti tidak diperlukan lagi.")
        return

    if trx.status != "PENDING":
        await state.clear()
        await message.answer("Invoice ini sudah tidak dapat menerima bukti pembayaran.")
        return

    # WAJIB aware-UTC: Postgres server ini menafsir datetime naive sebagai
    # Asia/Shanghai, jadi nilai naive tersimpan 8 jam lebih awal.
    trx.payment_proof_file_id = file_id
    trx.proof_sent_at = datetime.now(timezone.utc)
    await session.commit()

    product = None
    if trx.product_id:
        product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
    product_label = product.name if product else "Top Up Saldo"
    buyer = await crud.get_user_by_id(session=session, user_id=trx.user_id)
    buyer_label = f"ID {trx.user_id}"
    if buyer:
        if buyer.username:
            buyer_label = f"{buyer.first_name or ''} (@{buyer.username})".strip()
        elif buyer.first_name:
            buyer_label = buyer.first_name

    await notify_admin_payment_proof(
        message.bot,
        invoice_id=trx.id,
        product_label=product_label,
        amount=float(trx.amount),
        buyer_id=trx.user_id,
        buyer_label=buyer_label,
        buyer_username=buyer.username if buyer else None,
        proof_file_id=file_id,
    )

    await message.answer(
        "✅ <b>Bukti pembayaran diterima</b> dan sudah diteruskan ke admin.\n\n"
        "Admin akan memeriksa dan pesananmu diproses setelah pembayaran "
        "terverifikasi. Kalau ada yang kurang, admin akan menghubungimu.",
        parse_mode="HTML",
    )
    await state.clear()


@router.message(PaymentProofState.waiting_for_photo, F.photo)
async def process_proof_photo(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    file_id = message.photo[-1].file_id
    await _save_proof(message, session, state, file_id)


@router.message(PaymentProofState.waiting_for_photo, F.document)
async def process_proof_document(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    # Screenshot yang dikirim sebagai file (bukan foto terkompres): terima
    # hanya bila memang gambar.
    doc = message.document
    if not doc or not (doc.mime_type or "").startswith("image/"):
        await message.answer(
            "File itu bukan gambar. Kirim foto/screenshot bukti pembayarannya ya."
        )
        return
    await _save_proof(message, session, state, doc.file_id)


@router.message(PaymentProofState.waiting_for_photo)
async def process_proof_other(
    message: Message, state: FSMContext
) -> None:
    text = (message.text or "").strip().lower()
    if text == "batal":
        await state.clear()
        await message.answer("Pengiriman bukti dibatalkan. Invoice tetap menunggu pembayaran.")
        return
    await message.answer(
        "Kirim foto/screenshot bukti pembayarannya ya (bukan teks).\n"
        "Ketik batal kalau tidak jadi mengirim."
    )
