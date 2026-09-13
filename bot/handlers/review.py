"""
Aeternum PremiApp Bot - Review & Testimonial Handlers
"""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from bot.keyboards.user_kb import back_to_main_kb

logger = logging.getLogger(__name__)
router = Router(name="review_router")


class ReviewCommentState(StatesGroup):
    waiting_for_comment = State()


@router.callback_query(F.data.startswith("rate_"))
async def cb_receive_rating(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    """Menerima pilihan rating bintang dari pembeli."""
    parts = callback.data.split("_")
    stars = int(parts[1])
    invoice_id = "_".join(parts[2:])

    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)
    if not trx:
        await callback.answer("Transaksi tidak ditemukan!", show_alert=True)
        return

    existing_review = await crud.get_review_by_transaction(
        session=session, transaction_id=invoice_id
    )
    if existing_review:
        await callback.answer("Anda sudah memberikan ulasan untuk transaksi ini!", show_alert=True)
        return

    # Simpan rating dasar
    review = await crud.create_review(
        session=session,
        transaction_id=trx.id,
        user_id=callback.from_user.id,
        product_id=trx.product_id or 0,
        rating=stars,
    )

    await state.update_data(review_id=review.id, invoice_id=trx.id, stars=stars)
    await state.set_state(ReviewCommentState.waiting_for_comment)

    stars_str = "⭐" * stars
    text = (
        f"🌟 <b>TERIMA KASIH ATAS PENILAIAN ANDA!</b>\n\n"
        f"Rating Anda: <b>{stars_str} ({stars}/5)</b>\n\n"
        f"Silakan ketik komentar/testimoni singkat tentang pengalaman berbelanja Anda di bawah ini:\n"
        f"<i>(Atau ketik <code>-</code> jika tidak ingin menambahkan komentar teks)</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(ReviewCommentState.waiting_for_comment)
async def process_review_comment(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    comment = message.text.strip()
    data = await state.get_data()
    invoice_id = data.get("invoice_id")
    stars = data.get("stars", 5)
    await state.clear()

    if comment != "-":
        rev = await crud.get_review_by_transaction(session=session, transaction_id=invoice_id)
        if rev:
            rev.comment = comment
            await session.commit()

    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)
    product = await crud.get_product_by_id(session=session, product_id=trx.product_id) if trx and trx.product_id else None
    prod_name = product.name if product else "Produk Digital"

    stars_str = "⭐" * stars
    user_name = message.from_user.first_name or "Pembeli"

    # Kirim konfirmasi ke pembeli
    await message.answer(
        "🎉 <b>Ulasan Anda berhasil disimpan!</b>\n"
        "Terima kasih telah mempercayai <b>Aeternum PremiApp Bot</b>.",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML",
    )

    # Auto-post ke Channel Testimoni jika Bintang 5 & ada config channel
    testi_channel = getattr(settings, "TESTIMONIAL_CHANNEL_ID", None)
    if testi_channel and stars >= 4:
        try:
            testi_text = (
                f"🌟 <b>TESTIMONI PEMBELIAN BARU</b> 🌟\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>Produk:</b> {prod_name}\n"
                f"👤 <b>Pembeli:</b> {user_name}\n"
                f"⭐ <b>Rating:</b> {stars_str}\n"
                f"💬 <b>Ulasan:</b> <i>\"{comment if comment != '-' else 'Pelayanan cepat dan terpercaya!'}\"</i>\n"
                f"🧾 <b>Order:</b> <code>#{trx.id if trx else '-'}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛒 <i>Beli otomatis 24/7 di @{bot.get_me().username}</i>"
            )
            await bot.send_message(
                chat_id=testi_channel,
                text=testi_text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Gagal mem-forward testimoni ke channel: {e}")
