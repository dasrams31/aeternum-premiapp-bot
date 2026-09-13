"""
Aeternum PremiApp Bot - Warranty & Ticket Handlers
Klaim garansi kendala akun/produk dan penyelesaian tiket oleh admin.
"""

from datetime import datetime
import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from bot.keyboards.admin_kb import ticket_admin_kb
from bot.keyboards.user_kb import back_to_main_kb

logger = logging.getLogger(__name__)
router = Router(name="warranty_router")


class WarrantyState(StatesGroup):
    waiting_for_issue = State()
    waiting_for_proof = State()


class AdminReplyTicketState(StatesGroup):
    waiting_for_replacement = State()
    waiting_for_reply_text = State()


# ==========================================
# 1. ALUR PEMBELI MENGAJUKAN KLAIM GARANSI
# ==========================================
@router.callback_query(F.data.startswith("claim_warranty_"))
async def cb_start_warranty_claim(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    invoice_id = callback.data.replace("claim_warranty_", "")
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)

    if not trx or trx.status != "PAID":
        await callback.answer("Hanya transaksi yang sudah lunas yang bisa mengajukan garansi!", show_alert=True)
        return

    await state.update_data(claim_trx_id=invoice_id, claim_product_id=trx.product_id)
    await state.set_state(WarrantyState.waiting_for_issue)

    text = (
        f"⚠️ <b>FORM KLAIM GARANSI #{invoice_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Silakan jelaskan kendala yang Anda alami secara mendetail:\n"
        f"<i>(Contoh: Akun tidak bisa login password salah / Akun terkena limit / Akses terkunci)</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(WarrantyState.waiting_for_issue)
async def process_warranty_issue(message: Message, state: FSMContext) -> None:
    issue = message.text.strip()
    await state.update_data(claim_issue=issue)
    await state.set_state(WarrantyState.waiting_for_proof)

    await message.answer(
        "📸 <b>KIRIM BUKTI SCREENSHOT (OPSIONAL)</b>\n\n"
        "Silakan kirimkan foto/screenshot bukti kendala error yang Anda alami:\n"
        "<i>(Atau ketik <code>-</code> jika tidak memiliki foto screenshot)</i>",
        parse_mode="HTML",
    )


@router.message(WarrantyState.waiting_for_proof)
async def process_warranty_final(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    proof_file_id = None
    if message.photo:
        proof_file_id = message.photo[-1].file_id

    data = await state.get_data()
    invoice_id = data["claim_trx_id"]
    product_id = data["claim_product_id"] or 0
    issue_desc = data["claim_issue"]
    await state.clear()

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
    ticket_code = f"TKT-{timestamp}-{message.from_user.id % 10000:04d}"

    ticket = await crud.create_warranty_ticket(
        session=session,
        ticket_code=ticket_code,
        transaction_id=invoice_id,
        user_id=message.from_user.id,
        product_id=product_id,
        issue_description=issue_desc,
        proof_file_id=proof_file_id,
    )

    product = await crud.get_product_by_id(session=session, product_id=product_id)
    prod_name = product.name if product else "Produk Digital"

    # Konfirmasi ke user
    await message.answer(
        f"✅ <b>TIKET KLAIM GARANSI BERHASIL DIBUAT!</b>\n\n"
        f"🆔 <b>Nomor Tiket:</b> <code>{ticket_code}</code>\n"
        f"📦 <b>Produk:</b> {prod_name}\n"
        f"⏳ <b>Status:</b> <b>DALAM PENGECEKAN ADMIN UTAMA (@dasrams)</b>\n\n"
        f"Admin kami akan segera memeriksa klaim Anda. Notifikasi akun pengganti atau penyelesaian akan dikirimkan langsung ke chat ini.",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )

    # Kirim Alert Interaktif ke DM Admin
    admin_alert_text = (
        f"🚨 <b>TIKET KLAIM GARANSI BARU!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Tiket:</b> <code>{ticket_code}</code>\n"
        f"🧾 <b>Order:</b> <code>#{invoice_id}</code>\n"
        f"📦 <b>Produk:</b> {prod_name}\n"
        f"👤 <b>Pelapor:</b> {message.from_user.first_name} (ID: <code>{message.from_user.id}</code>)\n"
        f"📝 <b>Kendala:</b>\n<i>\"{issue_desc}\"</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        if proof_file_id:
            await bot.send_photo(
                chat_id=settings.ADMIN_ID,
                photo=proof_file_id,
                caption=admin_alert_text,
                reply_markup=ticket_admin_kb(ticket_code, message.from_user.id),
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=admin_alert_text,
                reply_markup=ticket_admin_kb(ticket_code, message.from_user.id),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Gagal mengirim tiket ke admin: {e}")


# ==========================================
# 2. AKSI RESOLUSI TIKET OLEH ADMIN
# ==========================================
@router.callback_query(F.data.startswith("adm_replace_"))
async def cb_admin_start_replace(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Admin ingin mengirimkan kredensial pengganti."""
    ticket_code = callback.data.replace("adm_replace_", "")
    await state.update_data(target_ticket=ticket_code)
    await state.set_state(AdminReplyTicketState.waiting_for_replacement)

    await callback.message.answer(
        f"🔑 <b>KIRIM KREDENSIAL PENGGANTI UNTUK #{ticket_code}</b>\n\n"
        f"Silakan ketik atau paste data akun/key pengganti yang akan dikirim ke pembeli:\n"
        f"<i>(Format <code>email:password</code> atau Serial Key)</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminReplyTicketState.waiting_for_replacement)
async def process_admin_replacement(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    replacement_text = message.text.strip()
    data = await state.get_data()
    ticket_code = data["target_ticket"]
    await state.clear()

    ticket = await crud.resolve_warranty_ticket(
        session=session,
        ticket_code=ticket_code,
        status="RESOLVED",
        admin_notes="Akun pengganti terkirim",
        replacement_content=replacement_text,
    )

    if ticket:
        # Kirim kredensial baru ke pembeli dengan proteksi content
        buyer_msg = (
            f"🎉 <b>KLAIM GARANSI DISETUJUI & SELESAI!</b>\n\n"
            f"🆔 <b>Tiket:</b> <code>{ticket_code}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 <b>DATA AKUN PENGGANTI ANDA:</b>\n\n"
            f"<code>{replacement_text}</code>\n\n"
            f"<i>💡 Ketuk teks abu-abu di atas untuk menyalin langsung.</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Mohon maaf atas ketidaknyamanannya. Selamat menikmati kembali!"
        )
        try:
            await bot.send_message(
                chat_id=ticket.user_id,
                text=buyer_msg,
                parse_mode="HTML",
                protect_content=True,
            )
            await message.answer(f"✅ Akun pengganti berhasil dikirimkan ke pembeli untuk tiket #{ticket_code}!")
        except Exception as e:
            await message.answer(f"⚠️ Gagal mengirim ke pembeli: {e}")


@router.callback_query(F.data.startswith("adm_reject_"))
async def cb_admin_reject_ticket(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    ticket_code = callback.data.replace("adm_reject_", "")
    ticket = await crud.resolve_warranty_ticket(
        session=session,
        ticket_code=ticket_code,
        status="REJECTED",
        admin_notes="Klaim ditolak admin",
    )

    if ticket:
        try:
            await bot.send_message(
                chat_id=ticket.user_id,
                text=(
                    f"❌ <b>STATUS KLAIM GARANSI #{ticket_code}</b>\n\n"
                    f"Mohon maaf, klaim garansi Anda belum dapat disetujui setelah diverifikasi oleh tim kami.\n"
                    f"Jika ada pertanyaan lebih lanjut, silakan hubungi CS di @dasrams."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.answer("Tiket berhasil ditolak.", show_alert=True)
