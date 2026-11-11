"""
Aeternum PremiApp Bot - Order Chat (relay pembeli <-> admin per invoice).

Pola BWR: setelah produk terkirim, pembeli bisa chat penjual dari dalam bot.
Satu thread per invoice (tabel order_chats + chat_messages). Pembeli kirim
pesan -> bot teruskan ke DM admin lengkap dengan produk + invoice; admin
tekan Balas -> jawabannya diteruskan balik ke pembeli. Tanda dibaca
eksplisit (tombol "Tandai pesan dibaca"), tidak otomatis saat thread dibuka.

Batasan v1: teks saja (foto/dokumen belum didukung). FSM state disimpan di
memory (MemoryStorage) seperti alur bukti pembayaran; restart bot
menghapus state "menunggu pesan" yang belum terkirim.
"""

import logging
from datetime import datetime, timedelta, timezone
from html import escape as html_escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from database.models import ChatMessage, OrderChat, Transaction

logger = logging.getLogger(__name__)
router = Router(name="order_chat_router")

WIB = timezone(timedelta(hours=7))
MAX_MESSAGE_LEN = 2000
THREAD_VIEW_LIMIT = 5
FULL_HISTORY_LIMIT = 20
SNIPPET_LEN = 300


class OrderChatState(StatesGroup):
    waiting_for_message = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wib(dt: datetime | None) -> str:
    """Format '11 Nov, 22.34' WIB. Kolom timestamptz disimpan aware UTC."""
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB).strftime("%d %b, %H.%M")


def _is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID


async def _load_chat(session: AsyncSession, invoice_id: str) -> OrderChat | None:
    return (
        await session.execute(
            select(OrderChat).where(OrderChat.transaction_id == invoice_id)
        )
    ).scalars().first()


async def _get_or_create_chat(
    session: AsyncSession, trx: Transaction
) -> OrderChat:
    chat = await _load_chat(session, trx.id)
    if chat is not None:
        return chat
    chat = OrderChat(transaction_id=trx.id, buyer_id=trx.user_id)
    session.add(chat)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        chat = await _load_chat(session, trx.id)
        if chat is None:
            raise
    return chat


async def _load_messages(
    session: AsyncSession, chat_id: int, limit: int
) -> list[ChatMessage]:
    """Pesan terbaru, urutan kronologis (lama -> baru)."""
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(reversed(rows))


def _render_thread(
    product_name: str,
    invoice_id: str,
    messages: list[ChatMessage],
    viewer_is_admin: bool,
    viewer_unread: int,
    buyer_label: str,
    show_all: bool = False,
) -> str:
    last_sender = messages[-1].sender_role if messages else None
    if last_sender is None:
        follow_up = "Menunggu pesan pertama"
    elif last_sender == "buyer":
        follow_up = (
            "Menunggu balasan kamu" if viewer_is_admin
            else "Menunggu balasan seller"
        )
    else:
        follow_up = (
            "Menunggu balasan pembeli" if viewer_is_admin
            else "Menunggu balasan kamu"
        )
    header = "\n".join(
        [
            "💬 <b>CHAT PENJUAL</b>",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"📦 <b>Produk:</b> {html_escape(product_name)}",
            f"🧾 <b>Invoice:</b> <code>{html_escape(invoice_id)}</code>",
            "📊 <b>Status:</b> Chat dengan seller",
            f"⏳ <b>Tindak lanjut:</b> {follow_up}",
            "━━━━━━━━━━━━━━━━━━━━━",
            "💬 <b>Pesan:</b>",
            "",
        ]
    )
    if not messages:
        body = "<i>Belum ada pesan. Tekan ✍️ Balas untuk mengirim pesan pertama.</i>"
        text = header + body
    else:
        blocks: list[str] = []
        for msg in messages:
            if msg.sender_role == "admin":
                who = "Anda · Admin" if viewer_is_admin else "Admin · Penjual"
            else:
                who = buyer_label if viewer_is_admin else "Anda · Pembeli"
            if show_all:
                body_msg = html_escape(msg.text)
            elif len(msg.text) > SNIPPET_LEN:
                body_msg = html_escape(msg.text[:SNIPPET_LEN]) + "…"
            else:
                body_msg = html_escape(msg.text)
            blocks.append(
                f"<b>{html_escape(who)}</b> · {_wib(msg.created_at)}\n{body_msg}\n"
            )
        # Anggaran ~3400 karakter: pesan lama yang tidak muat tidak ditampilkan
        # (buka 📱 Chat lengkap untuk riwayat; potongan tidak pernah memotong
        # tag HTML di tengah, jadi render tidak bisa gagal karena itu).
        chosen: list[str] = []
        total = len(header)
        for block in reversed(blocks):
            if chosen and total + len(block) > 3400:
                break
            chosen.append(block)
            total += len(block)
        chosen.reverse()
        text = header + "\n".join(chosen)
        if len(chosen) < len(blocks):
            text += (
                f"\n<i>(Menampilkan {len(chosen)} pesan terakhir. "
                "Buka 📱 Chat lengkap untuk riwayat penuh.)</i>"
            )
    if viewer_unread > 0:
        text += (
            f"\n<i>Belum ditandai dibaca ({viewer_unread} pesan baru). "
            "Tekan 👁️ Tandai pesan dibaca untuk menandainya, "
            "atau 📱 Chat lengkap untuk seluruh riwayat.</i>"
        )
    return text


def _thread_kb(invoice_id: str, viewer_is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✍️ Balas", callback_data=f"chat_reply_{invoice_id}"
            ),
            InlineKeyboardButton(
                text="📱 Chat lengkap", callback_data=f"chat_full_{invoice_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="👁️ Tandai pesan dibaca",
                callback_data=f"chat_read_{invoice_id}",
            ),
            InlineKeyboardButton(
                text="🔃 Muat ulang", callback_data=f"chat_refresh_{invoice_id}"
            ),
        ],
    ]
    if viewer_is_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔙 Menu utama", callback_data="back_to_main"
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💬 Percakapan saya", callback_data="chat_list"
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔙 Kembali ke pesanan",
                    callback_data=f"view_hist_{invoice_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _load_trx_and_product(
    session: AsyncSession, invoice_id: str
) -> tuple[Transaction | None, str, str]:
    """Return (trx, product_name, buyer_label). buyer_label untuk sisi admin."""
    trx = await crud.get_transaction_by_id(session=session, transaction_id=invoice_id)
    if trx is None:
        return None, "-", "-"
    product = (
        await crud.get_product_by_id(session=session, product_id=trx.product_id)
        if trx.product_id
        else None
    )
    product_name = product.name if product else (
        "Top Up Saldo" if trx.trx_type == "TOPUP" else "Produk Digital"
    )
    buyer = await crud.get_user_by_id(session=session, user_id=trx.user_id)
    if buyer and buyer.username:
        buyer_label = f"{buyer.first_name or ''} (@{buyer.username}) · Pembeli".strip()
    elif buyer and buyer.first_name:
        buyer_label = f"{buyer.first_name} · Pembeli"
    else:
        buyer_label = f"ID {trx.user_id} · Pembeli"
    return trx, product_name, buyer_label


async def _check_actor(
    callback: CallbackQuery, trx: Transaction | None
) -> tuple[bool, bool]:
    """Return (allowed, viewer_is_admin). Menjawab alert bila tidak boleh."""
    if trx is None:
        await callback.answer("Pesanan tidak ditemukan!", show_alert=True)
        return False, False
    viewer_is_admin = _is_admin(callback.from_user.id)
    if not viewer_is_admin and callback.from_user.id != trx.user_id:
        await callback.answer(
            "Percakapan ini hanya untuk pembeli pesanan ini.", show_alert=True
        )
        return False, False
    if trx.status != "PAID":
        await callback.answer(
            "Chat penjual tersedia setelah pembayaran lunas.", show_alert=True
        )
        return False, False
    return True, viewer_is_admin


async def _send_thread_view(
    callback: CallbackQuery,
    session: AsyncSession,
    invoice_id: str,
    *,
    edit: bool,
    show_all: bool = False,
) -> None:
    trx, product_name, buyer_label = await _load_trx_and_product(
        session, invoice_id
    )
    allowed, viewer_is_admin = await _check_actor(callback, trx)
    if not allowed:
        return
    chat = await _get_or_create_chat(session, trx)
    await session.commit()
    messages = await _load_messages(
        session, chat.id, FULL_HISTORY_LIMIT if show_all else THREAD_VIEW_LIMIT
    )
    viewer_unread = chat.admin_unread if viewer_is_admin else chat.buyer_unread
    text = _render_thread(
        product_name, invoice_id, messages, viewer_is_admin,
        viewer_unread, buyer_label, show_all=show_all,
    )
    kb = _thread_kb(invoice_id, viewer_is_admin)
    if edit and callback.message is not None:
        try:
            await callback.message.edit_text(
                text=text, reply_markup=kb, parse_mode="HTML"
            )
        except Exception:
            pass
    elif callback.message is not None:
        await callback.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# Thread view
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("chat_seller_"))
async def cb_open_thread(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Buka thread chat per invoice (pesan baru, pesan pengiriman tetap utuh)."""
    invoice_id = callback.data.replace("chat_seller_", "", 1)
    await _send_thread_view(callback, session, invoice_id, edit=False)


@router.callback_query(F.data.startswith("chat_refresh_"))
async def cb_refresh_thread(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    invoice_id = callback.data.replace("chat_refresh_", "", 1)
    await _send_thread_view(callback, session, invoice_id, edit=True)


@router.callback_query(F.data.startswith("chat_full_"))
async def cb_full_history(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    invoice_id = callback.data.replace("chat_full_", "", 1)
    await _send_thread_view(callback, session, invoice_id, edit=True, show_all=True)


@router.callback_query(F.data.startswith("chat_read_"))
async def cb_mark_read(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Tandai pesan dibaca (eksplisit, ala BWR): nol-kan unread sisi viewer."""
    invoice_id = callback.data.replace("chat_read_", "", 1)
    trx, _, _ = await _load_trx_and_product(session, invoice_id)
    allowed, viewer_is_admin = await _check_actor(callback, trx)
    if not allowed:
        return
    chat = await _get_or_create_chat(session, trx)
    if viewer_is_admin:
        chat.admin_unread = 0
    else:
        chat.buyer_unread = 0
    await session.commit()
    await _send_thread_view(callback, session, invoice_id, edit=True)
    await callback.answer("Ditandai sudah dibaca.")


@router.callback_query(F.data == "chat_list")
async def cb_my_chats(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Daftar percakapan pembeli (thread open, terbaru dulu)."""
    chats = (
        await session.execute(
            select(OrderChat)
            .where(OrderChat.buyer_id == callback.from_user.id)
            .order_by(
                func.coalesce(OrderChat.last_message_at, OrderChat.created_at).desc()
            )
            .limit(10)
        )
    ).scalars().all()
    if not chats:
        text = (
            "💬 <b>PERCAKAPAN SAYA</b>\n\n"
            "<i>Belum ada percakapan. Chat penjual muncul setelah "
            "pembayaran lunas, lewat tombol di pesan pengiriman.</i>"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Menu utama", callback_data="back_to_main"
                    )
                ]
            ]
        )
    else:
        rows = []
        for chat in chats:
            trx, product_name, _ = await _load_trx_and_product(
                session, chat.transaction_id
            )
            label = product_name[:32]
            if chat.buyer_unread > 0:
                label += f" ({chat.buyer_unread} baru)"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"chat_seller_{chat.transaction_id}",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔙 Menu utama", callback_data="back_to_main"
                )
            ]
        )
        text = (
            "💬 <b>PERCAKAPAN SAYA</b>\n\n"
            "<i>Ketuk salah satu untuk membuka percakapan.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                text=text, reply_markup=kb, parse_mode="HTML"
            )
        except Exception:
            pass
    await callback.answer()


# ---------------------------------------------------------------------------
# Reply flow (FSM)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("chat_reply_"))
async def cb_start_reply(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Masuk mode balas: pesan teks berikutnya diteruskan ke lawan bicara."""
    invoice_id = callback.data.replace("chat_reply_", "", 1)
    trx, product_name, _ = await _load_trx_and_product(session, invoice_id)
    allowed, viewer_is_admin = await _check_actor(callback, trx)
    if not allowed:
        return
    await _get_or_create_chat(session, trx)
    await session.commit()
    await state.set_state(OrderChatState.waiting_for_message)
    await state.update_data(
        invoice_id=invoice_id,
        role="admin" if viewer_is_admin else "buyer",
    )
    who = "pembeli" if viewer_is_admin else "admin"
    if callback.message is not None:
        await callback.message.answer(
            "✍️ <b>BALAS PESAN</b>\n\n"
            f"Ketik pesanmu untuk {who} (produk: {html_escape(product_name)}).\n"
            "<i>Kirim 'batal' untuk membatalkan. Saat ini hanya teks.</i>",
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(OrderChatState.waiting_for_message)
async def process_chat_message(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    """Teruskan satu pesan teks ke lawan bicara + simpan di thread."""
    data = await state.get_data()
    invoice_id = data.get("invoice_id")
    role = data.get("role", "buyer")
    if not invoice_id:
        await state.clear()
        return

    if message.text is None:
        await message.answer(
            "Saat ini chat hanya mendukung pesan teks. "
            "Ketik pesanmu, atau kirim 'batal' untuk membatalkan."
        )
        return
    text = message.text.strip()
    if text.lower() == "batal":
        await state.clear()
        await message.answer("Dibatalkan, tidak ada pesan yang dikirim.")
        return
    if len(text) > MAX_MESSAGE_LEN:
        await message.answer(
            f"Pesan terlalu panjang ({len(text)} karakter, maks {MAX_MESSAGE_LEN}). "
            "Persingkat lalu kirim lagi."
        )
        return

    trx, product_name, buyer_label = await _load_trx_and_product(
        session, invoice_id
    )
    if trx is None:
        await state.clear()
        await message.answer("Pesanan tidak ditemukan, pesan tidak dikirim.")
        return
    sender_is_admin = _is_admin(message.from_user.id)
    if role == "admin" and not sender_is_admin:
        await state.clear()
        await message.answer("Sesi balasan ini sudah berakhir, coba tekan Balas lagi.")
        return
    if role == "buyer" and (
        sender_is_admin or message.from_user.id != trx.user_id
    ):
        await state.clear()
        await message.answer("Sesi balasan ini sudah berakhir, coba tekan Balas lagi.")
        return

    chat = await _get_or_create_chat(session, trx)
    now = datetime.now(timezone.utc)
    session.add(
        ChatMessage(
            chat_id=chat.id,
            sender_role=role,
            sender_id=message.from_user.id,
            text=text,
        )
    )
    if role == "buyer":
        chat.admin_unread = (chat.admin_unread or 0) + 1
    else:
        chat.buyer_unread = (chat.buyer_unread or 0) + 1
    chat.last_message_at = now
    await session.commit()
    await state.clear()

    view_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Lihat percakapan",
                    callback_data=f"chat_seller_{invoice_id}",
                )
            ]
        ]
    )
    if role == "buyer":
        admin_text = (
            "💬 <b>PESAN PEMBELI</b>\n\n"
            f"📦 <b>Produk:</b> {html_escape(product_name)}\n"
            f"🧾 <b>Invoice:</b> <code>{html_escape(invoice_id)}</code>\n"
            f"👤 <b>Pembeli:</b> {html_escape(buyer_label)}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{html_escape(text)}"
        )
        admin_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✍️ Balas", callback_data=f"chat_reply_{invoice_id}"
                    ),
                    InlineKeyboardButton(
                        text="📜 Lihat percakapan",
                        callback_data=f"chat_seller_{invoice_id}",
                    ),
                ]
            ]
        )
        try:
            await bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=admin_text,
                reply_markup=admin_kb,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Gagal meneruskan pesan chat #%s ke admin", invoice_id
            )
        await message.answer(
            "✅ Balasan terkirim.", reply_markup=view_kb
        )
    else:
        buyer_text = (
            "💬 <b>BALASAN ADMIN</b>\n\n"
            f"📦 <b>Produk:</b> {html_escape(product_name)}\n"
            f"🧾 <b>Invoice:</b> <code>{html_escape(invoice_id)}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{html_escape(text)}"
        )
        try:
            await bot.send_message(
                chat_id=trx.user_id,
                text=buyer_text,
                reply_markup=view_kb,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Gagal meneruskan balasan admin #%s ke pembeli", invoice_id
            )
        await message.answer(
            "✅ Balasan terkirim.", reply_markup=view_kb
        )
