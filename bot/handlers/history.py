"""
Aeternum PremiApp Bot - Order History Handlers
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from bot.keyboards.user_kb import back_to_main_kb, history_detail_kb, history_list_kb

router = Router(name="history_router")


@router.message(Command("riwayat"))
@router.callback_query(F.data == "user_history")
async def show_user_history(
    event: Message | CallbackQuery, session: AsyncSession
) -> None:
    user = event.from_user
    if not user:
        return

    transactions = await crud.get_user_transactions(
        session=session, user_id=user.id, limit=10
    )

    if not transactions:
        text = (
            "📜 <b>RIWAYAT PESANAN</b>\n\n"
            "Anda belum memiliki riwayat pembelian di Aeternum PremiApp Bot.\n"
            "Silakan jelajahi <b>🛍️ Katalog Produk</b> untuk melakukan pembelian pertama Anda!"
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
        "📜 <b>RIWAYAT PESANAN ANDA</b>\n\n"
        "Berikut adalah daftar pesanan Anda (terbaru). Ketuk salah satu untuk melihat rincian produk yang telah Anda beli:"
    )

    if isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(
            text=text,
            reply_markup=history_list_kb(transactions),
            parse_mode="HTML",
        )
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(
            text=text,
            reply_markup=history_list_kb(transactions),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("view_hist_"))
async def cb_view_history_detail(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    invoice_id = callback.data.replace("view_hist_", "")
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)

    if not trx:
        await callback.answer("Pesanan tidak ditemukan!", show_alert=True)
        return

    product = await crud.get_product_by_id(session=session, product_id=trx.product_id) if trx.product_id else None
    product_name = product.name if product else ("Top Up Saldo" if trx.trx_type == "TOPUP" else "Produk Digital")

    status_badge = "✅ LUNAS" if trx.status == "PAID" else "⏳ MENUNGGU PEMBAYARAN" if trx.status == "PENDING" else "❌ DIBATALKAN"
    formatted_price = f"Rp {trx.amount:,.0f}".replace(",", ".")
    date_str = trx.created_at.strftime("%d %b %Y, %H:%M WIB") if trx.created_at else "-"

    content_display = trx.delivered_content or "Tidak ada konten tersimpan atau pesanan belum dibayar."

    war_section = ""
    if product:
        war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus")
        war_note = f" <i>({product.warranty_note})</i>" if product.warranty_note else ""
        war_section = f"🛡️ <b>Garansi:</b> {war_badge}{war_note}\n"

    text = (
        f"🧾 <b>RINCIAN PESANAN #{trx.id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Produk:</b> {product_name}\n"
        f"💵 <b>Total:</b> <code>{formatted_price}</code>\n"
        f"📊 <b>Status:</b> <b>{status_badge}</b>\n"
        f"📅 <b>Waktu:</b> {date_str}\n"
        f"{war_section}"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>KONTEN PRODUK YANG DITERIMA:</b>\n\n"
        f"<code>{content_display}</code>\n"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=history_detail_kb(invoice_id=trx.id, is_paid=trx.status == "PAID"),
            parse_mode="HTML",
        )
    await callback.answer()
