"""
Aeternum PremiApp Bot - Broadcast rutin ke channel & grup Peka.

PEMISAHAN PEKA vs AETERNUM (perintah user 7 Nov 2026):
- Channel Peka @peka_aichannel (-1001475296402): HANYA info stok ready
  (digest harian) + konten Peka (dikirim helper telegram_channel.py).
  Urusan jual-beli lain TIDAK masuk sini.
- Channel Aeternum @aeternum_premich (-1001369908930): SEMUA broadcast
  komersial (transaksi berhasil, stok habis, stok ditambah, produk baru)
  + digest stok ready harian + user bergabung.
- Grup Peka @peka_aigroup (-1001167087205): TIDAK dikirimi broadcast
  langsung. Grup adalah discussion group yang terhubung ke channel Peka
  (linked_chat_id dua arah, terverifikasi 7 Nov 2026), jadi tiap postingan
  channel Peka otomatis muncul di grup. Mengirim ke grup juga = pesan dobel.
  Satu-satunya pesan bot di grup: sambutan member baru (welcome).
- Channel Peka TIDAK lagi memberi sambutan gabung (bersih buat broadcast);
  gabung channel Aeternum dapat kabar singkat.

FORMAT BROADCAST PRODUK (perintah user 7 Nov 2026, meniru format toko lain):
- Restock: "🔄 RESTOCK PRODUK!" + nama + kategori + stok ditambah + total
  stok + harga mulai + tombol [🛒 Beli Sekarang] (deep-link produk).
- Produk baru: "🆕 PRODUK BARU!" + nama + kategori + stok + harga mulai
  (+ deskripsi singkat) + tombol [🛒 Beli Sekarang].
- Stok habis: "🔴 STOK HABIS!" + tombol [🔔 Ingatkan Saya Saat Restock]
  (deep-link /start remind_<id>).
- Broadcast dikirim ke channel Aeternum DAN ke DM semua pengguna bot.
  Aturan anti-ganda: penunggu restock suatu produk HANYA menerima
  notifikasi subscriber (bukan DM broadcast umum produk itu) — lihat
  broadcast_restock_event() di bot/services/stock_updater.py.

Semua helper di sini TIDAK PERNAH melempar exception ke pemanggil: kegagalan
kirim hanya dicatat di log supaya alur utama (pembayaran, restock, digest)
tidak pernah rusak gara-gara broadcast.
"""

import asyncio
import html
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set, Tuple

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from config import settings
from database.models import Category, Product

logger = logging.getLogger(__name__)

KNOWN_PRODUCTS_FILE = Path(__file__).resolve().parent.parent.parent / "known_products.txt"

BOT_USERNAME = "aeternum_premibot"
BOT_DEEP_LINK_BASE = f"https://t.me/{BOT_USERNAME}"


def _rupiah(price) -> str:
    return f"Rp {float(price):,.0f}".replace(",", ".")


def checkout_decision_kb(
    invoice_id: str, buyer_username: Optional[str]
) -> InlineKeyboardMarkup:
    """Tombol keputusan admin di notif checkout: Terima / Tolak / Abaikan.

    Terima HANYA bila pembayaran sudah masuk (cek mutasi/dashboard):
    Terima langsung mengirim produk/saldo ke pembeli. Tolak menandai
    invoice REJECTED tanpa info apa pun ke pembeli. Abaikan hanya
    menutup kartu dan membiarkan invoice apa adanya.
    """
    rows: list = []
    if buyer_username:
        rows.append(
            [InlineKeyboardButton(text="💬 Chat Pembeli", url=f"https://t.me/{buyer_username}")]
        )
    rows.append(
        [
            InlineKeyboardButton(text="✅ Terima", callback_data=f"co_acc_{invoice_id}"),
            InlineKeyboardButton(text="❌ Tolak", callback_data=f"co_rej_{invoice_id}"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="👁 Abaikan", callback_data=f"co_ign_{invoice_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def notify_admin_checkout_attempt(
    bot: Bot,
    *,
    invoice_id: str,
    product_label: str,
    amount: float,
    buyer_id: int,
    buyer_label: str,
    buyer_username: Optional[str],
    gateway_ok: bool,
) -> bool:
    """DM admin realtime tiap ada percobaan checkout (invoice QRIS dibuat).

    Dipanggil sekali saat invoice dibuat, baik gateway sukses maupun gagal
    (QR fallback). Tidak pernah melempar exception ke pemanggil supaya
    alur checkout tidak pernah rusak gara-gara notifikasi.
    """
    wib_now = (datetime.utcnow() + timedelta(hours=7)).strftime("%d %b %Y %H:%M WIB")
    if gateway_ok:
        gw_line = "✅ <b>Gateway:</b> OK, QR KlikQRIS terbit."
    else:
        gw_line = (
            "⚠️ <b>Gateway:</b> GAGAL, QR fallback (bukan QR KlikQRIS). "
            "Pembeli mungkin bayar ke QRIS statis, cek manual."
        )
    text = (
        f"🛒 <b>PERCOBAAN CHECKOUT</b>\n\n"
        f"📦 <b>Produk:</b> {html.escape(product_label)}\n"
        f"👤 <b>Pembeli:</b> {html.escape(buyer_label)}\n"
        f"🆔 <b>ID:</b> <code>{buyer_id}</code>\n"
        f"💰 <b>Nominal:</b> {_rupiah(amount)}\n"
        f"🧾 <b>Invoice:</b> <code>{html.escape(invoice_id)}</code>\n"
        f"💳 <b>Metode:</b> QRIS\n"
        f"{gw_line}\n"
        f"🕐 <b>Waktu:</b> {wib_now}\n\n"
        f"⚠️ <b>Keputusan admin:</b> Terima HANYA bila pembayaran sudah masuk (cek mutasi/dashboard). "
        f"Terima langsung mengirim produk ke pembeli. Tolak = pembeli tidak diberi info apa pun.\n\n"
        f"<i>Percobaan checkout baru. Balas lewat tombol chat di bawah.</i>"
    )
    markup = checkout_decision_kb(invoice_id, buyer_username)
    try:
        await bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
        return True
    except Exception:
        logger.exception(f"Gagal notifikasi checkout #{invoice_id} ke admin")
        return False


async def notify_admin_payment_proof(
    bot: Bot,
    *,
    invoice_id: str,
    product_label: str,
    amount: float,
    buyer_id: int,
    buyer_label: str,
    buyer_username: Optional[str],
    proof_file_id: str,
) -> bool:
    """DM admin berisi FOTO bukti pembayaran + tombol Terima/Tolak/Abaikan.

    Dipanggil saat pembeli mengirim foto bukti lewat tombol "Kirim Bukti
    Pembayaran" di invoice QRIS (beli produk / top-up). Keyboard keputusan
    sama dengan notif PERCOBAAN CHECKOUT, jadi Terima di sini langsung
    mengirim produk/saldo lewat process_checkout_decision. Tidak pernah
    melempar exception ke pemanggil.
    """
    wib_now = (datetime.utcnow() + timedelta(hours=7)).strftime("%d %b %Y %H:%M WIB")
    caption = (
        f"🧾 <b>BUKTI PEMBAYARAN</b>\n\n"
        f"📦 <b>Produk:</b> {html.escape(product_label)}\n"
        f"👤 <b>Pembeli:</b> {html.escape(buyer_label)}\n"
        f"🆔 <b>ID:</b> <code>{buyer_id}</code>\n"
        f"💰 <b>Nominal:</b> {_rupiah(amount)}\n"
        f"🧾 <b>Invoice:</b> <code>{html.escape(invoice_id)}</code>\n"
        f"🕐 <b>Waktu kirim:</b> {wib_now}\n\n"
        f"⚠️ <b>Keputusan admin:</b> cocokkan foto bukti dengan mutasi/dashboard dulu. "
        f"Terima langsung mengirim produk/saldo ke pembeli. "
        f"Tolak = pembeli tidak diberi info apa pun.\n\n"
        f"<i>Bukti pembayaran dari pembeli. Balas lewat tombol chat di bawah.</i>"
    )
    markup = checkout_decision_kb(invoice_id, buyer_username)
    try:
        await bot.send_photo(
            chat_id=settings.ADMIN_ID,
            photo=proof_file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
        return True
    except Exception:
        logger.exception(f"Gagal notifikasi bukti bayar #{invoice_id} ke admin")
        return False


def product_buy_kb(product_id: int) -> InlineKeyboardMarkup:
    """Tombol [🛒 Beli Sekarang]: deep-link ke detail produk di bot."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Beli Sekarang",
                    url=f"{BOT_DEEP_LINK_BASE}?start=product_{product_id}",
                )
            ]
        ]
    )


def digest_kb() -> InlineKeyboardMarkup:
    """Tombol [Buka Bot Telegram] di bawah ringkasan stok ready harian.

    Dipasang hanya di chunk terakhir digest, di semua tujuan (channel Peka,
    channel Aeternum, DM user): tap tombol -> bot terbuka dengan /start,
    user tinggal buka Katalog Produk untuk memesan.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Buka Bot Telegram",
                    url=BOT_DEEP_LINK_BASE,
                )
            ]
        ]
    )


def digest_dm_kb() -> InlineKeyboardMarkup:
    """Tombol [Belanja Sekarang] di bawah ringkasan stok ready harian, KHUSUS DM user.

    Hanya dipakai di DM digest ke user yang sudah /start bot: tap tombol ->
    bot terbuka dengan /start shop -> menu utama muncul lagi (/start ulang),
    user langsung bisa buka Katalog Produk. Argumen 'shop' tidak dikenali
    handler /start, jadi jatuh ke menu utama biasa. Channel tetap pakai
    digest_kb() ('Buka Bot Telegram').
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Belanja Sekarang",
                    url=f"{BOT_DEEP_LINK_BASE}?start=shop",
                )
            ]
        ]
    )


def remind_kb(product_id: int) -> InlineKeyboardMarkup:
    """Tombol [🔔 Ingatkan Saya Saat Restock]: deep-link subscribe pengingat.

    Dipakai di pesan channel (callback tidak bisa dipakai dari channel):
    tap tombol -> bot terbuka dengan /start remind_<id> -> user langsung
    terdaftar sebagai penunggu restock produk itu.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔔 Ingatkan Saya Saat Restock",
                    url=f"{BOT_DEEP_LINK_BASE}?start=remind_{product_id}",
                )
            ]
        ]
    )


async def get_category_name(session, category_id: Optional[int]) -> str:
    """Nama kategori produk; 'Lainnya' bila tidak ada."""
    if not category_id:
        return "Lainnya"
    res = await session.execute(select(Category).where(Category.id == category_id))
    cat = res.scalar_one_or_none()
    return cat.name if cat else "Lainnya"


def _stock_line(product: Product, count: Optional[int]) -> str:
    """Baris stok untuk broadcast produk baru."""
    if product.product_type == "TEXT_STOCK":
        if count is None or count == 0:
            return "Segera hadir"
        return f"{count} unit"
    return "Tersedia"


def build_restock_broadcast_text(
    product: Product, cat_name: str, added: Optional[int], total: int
) -> str:
    """Teks broadcast restock (satu sumber: channel + DM + notifikasi subscriber).

    `added=None` (jalur sinkronisasi harian, jumlah penambahan tidak
    diketahui) -> baris 'Stok ditambah' dihilangkan.
    """
    name = html.escape(product.name)
    cat = html.escape(cat_name)
    lines = [
        "🔄 <b>RESTOCK PRODUK!</b>",
        "",
        f"📦 <b>{name}</b>",
        f"🏷️ Kategori: {cat}",
    ]
    if added is not None:
        lines.append(f"➕ Stok ditambah: <b>+{added} unit</b>")
    lines.append(f"📊 Total stok siap kirim: <b>{total} unit</b>")
    lines.append(f"💲 Harga mulai: <b>{_rupiah(product.price)}</b>")
    lines.append("")
    lines.append("Stok sudah kembali segar dan siap dikirim otomatis! 👇")
    return "\n".join(lines)


def build_new_product_broadcast_text(
    product: Product, cat_name: str, count: Optional[int]
) -> str:
    """Teks broadcast produk baru (satu sumber: channel + DM)."""
    name = html.escape(product.name)
    cat = html.escape(cat_name)
    lines = [
        "🆕 <b>PRODUK BARU!</b>",
        "",
        f"📦 <b>{name}</b>",
        f"🏷️ Kategori: {cat}",
        f"📊 Stok siap kirim: <b>{_stock_line(product, count)}</b>",
        f"💲 Harga mulai: <b>{_rupiah(product.price)}</b>",
    ]
    if product.description:
        desc = " ".join(product.description.split())[:200]
        lines.append(f"📝 {html.escape(desc)}")
    lines.append("")
    lines.append("Cek langsung di @aeternum_premibot — bayar QRIS, langsung dikirim.")
    return "\n".join(lines)


def build_stock_out_text(product: Product, cat_name: str) -> str:
    """Teks broadcast stok habis (channel Aeternum)."""
    name = html.escape(product.name)
    cat = html.escape(cat_name)
    return (
        "🔴 <b>STOK HABIS!</b>\n\n"
        f"📦 <b>{name}</b>\n"
        f"🏷️ Kategori: {cat}\n"
        f"💲 Harga mulai: <b>{_rupiah(product.price)}</b>\n\n"
        "Stok sedang diusahakan. Tekan tombol di bawah biar dikabari begitu restock!"
    )


async def send_to_channel(bot: Bot, text: str, **kwargs) -> bool:
    """Kirim satu pesan ke channel Peka. Kembalikan True bila terkirim."""
    try:
        await bot.send_message(
            chat_id=settings.PEKA_CHANNEL_ID, text=text, parse_mode="HTML", **kwargs
        )
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim ke channel Peka: {e}")
        return False


async def send_to_aeternum(bot: Bot, text: str, **kwargs) -> bool:
    """Kirim satu pesan ke channel Aeternum (@aeternum_premich). True bila terkirim."""
    try:
        await bot.send_message(
            chat_id=settings.AETERNUM_CHANNEL_ID, text=text, parse_mode="HTML", **kwargs
        )
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim ke channel Aeternum: {e}")
        return False


async def send_to_group(bot: Bot, text: str, **kwargs) -> bool:
    """Kirim satu pesan ke grup Peka. Kembalikan True bila terkirim."""
    try:
        await bot.send_message(
            chat_id=settings.PEKA_GROUP_ID, text=text, parse_mode="HTML", **kwargs
        )
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim ke grup Peka: {e}")
        return False


async def broadcast_to_all_users(
    bot: Bot,
    session,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    exclude_ids: Optional[Set[int]] = None,
) -> Tuple[int, int]:
    """Kirim pesan ke DM semua pengguna bot (kecuali exclude_ids).

    Dipakai broadcast produk baru & restock. Kegagalan per user (mis. bot
    diblokir / akun stale 'chat not found') hanya dicatat, tidak
    menghentikan pengiriman ke user lain. Kembalikan (terkirim, gagal).
    """
    from database import crud

    excluded = exclude_ids or set()
    user_ids = await crud.get_all_user_ids(session=session)
    sent, failed = 0, 0
    for uid in user_ids:
        if uid in excluded:
            continue
        try:
            await bot.send_message(
                chat_id=uid, text=text, parse_mode="HTML", reply_markup=reply_markup
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f"Gagal kirim broadcast DM ke {uid}: {e}")
    return sent, failed


async def broadcast_ready_digest_to_channel(bot: Bot, chunks: List[str]) -> int:
    """Kirim ringkasan stok ready harian ke channel Peka (grup ikut dapat
    lewat discussion yang terhubung, tanpa kirim dobel). Kembalikan jumlah pesan terkirim."""
    sent = 0
    for i, chunk in enumerate(chunks):
        kb = digest_kb() if i == len(chunks) - 1 else None
        if await send_to_channel(bot, chunk, reply_markup=kb):
            sent += 1
            await asyncio.sleep(0.3)
    if sent:
        logger.info("Ready digest terkirim ke channel Peka (%s pesan).", sent)
    return sent


async def broadcast_ready_digest_to_aeternum(bot: Bot, chunks: List[str]) -> int:
    """Kirim ringkasan stok ready harian ke channel Aeternum. Kembalikan jumlah pesan terkirim."""
    sent = 0
    for i, chunk in enumerate(chunks):
        kb = digest_kb() if i == len(chunks) - 1 else None
        if await send_to_aeternum(bot, chunk, reply_markup=kb):
            sent += 1
            await asyncio.sleep(0.3)
    if sent:
        logger.info("Ready digest terkirim ke channel Aeternum (%s pesan).", sent)
    return sent


async def broadcast_transaction_success(
    bot: Bot, product_name: str, amount: float, buyer_first_name: Optional[str]
) -> bool:
    """Transaksi berhasil -> channel Aeternum. Tanpa data sensitif (tanpa WA, ID, atau isi akun)."""
    buyer_line = (
        f"👤 <b>Pembeli:</b> <b>{buyer_first_name}</b>\n" if buyer_first_name else ""
    )
    text = (
        f"✅ <b>TRANSAKSI BERHASIL!</b>\n\n"
        f"📦 <b>Produk:</b> {product_name}\n"
        f"💵 <b>Nominal:</b> <code>{_rupiah(amount)}</code>\n"
        f"{buyer_line}\n"
        f"Beli juga di @aeternum_premibot — bayar QRIS, langsung dikirim."
    )
    return await send_to_aeternum(bot, text)


async def broadcast_stock_out(bot: Bot, session, product: Product) -> bool:
    """Produk TEXT_STOCK kehabisan stok -> channel Aeternum, dengan tombol
    pengingat restock (deep-link /start remind_<id>)."""
    cat_name = await get_category_name(session, product.category_id)
    text = build_stock_out_text(product, cat_name)
    return await send_to_aeternum(bot, text, reply_markup=remind_kb(product.id))


async def broadcast_stock_added(
    bot: Bot,
    session,
    product: Product,
    added: int,
    total: int,
    test_label: str = "",
) -> bool:
    """Admin menambah stok akun -> channel Aeternum (format restock baru +
    tombol Beli Sekarang). Bagian channel dari broadcast_restock_event."""
    cat_name = await get_category_name(session, product.category_id)
    text = build_restock_broadcast_text(product, cat_name, added, total)
    if test_label:
        text = f"{test_label}\n{text}"
    return await send_to_aeternum(bot, text, reply_markup=product_buy_kb(product.id))


async def broadcast_product_added(
    bot: Bot, session, product: Product, test_label: str = ""
) -> bool:
    """Produk baru masuk katalog -> channel Aeternum (format baru + tombol
    Beli Sekarang). Bagian channel dari broadcast_new_product_event."""
    from database import crud

    cat_name = await get_category_name(session, product.category_id)
    count = None
    if product.product_type == "TEXT_STOCK":
        count = await crud.count_available_stock(session=session, product_id=product.id)
    text = build_new_product_broadcast_text(product, cat_name, count)
    if test_label:
        text = f"{test_label}\n{text}"
    return await send_to_aeternum(bot, text, reply_markup=product_buy_kb(product.id))


async def broadcast_user_joined(bot: Bot, chat_id: int, first_name: str) -> bool:
    """User baru gabung CHANNEL AETERNUM -> kabar singkat di channel itu."""
    text = (
        f"👋 Selamat datang <b>{html.escape(first_name)}</b> di channel Aeternum!\n\n"
        f"Info produk digital, stok ready, dan promo ada di sini. "
        f"Katalog produk: @aeternum_premibot"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim sambutan gabung ke {chat_id}: {e}")
        return False


def build_group_welcome_text(user_id: int, first_name: str, username: Optional[str]) -> str:
    """Teks sambutan member baru di grup: tag nama + username + info singkat Peka."""
    name = html.escape(first_name or "teman baru")
    mention = f'<a href="tg://user?id={user_id}">{name}</a>'
    username_line = f" (@{html.escape(username)})" if username else ""
    return (
        f"👋 Selamat datang, {mention}{username_line}!\n\n"
        f"Kamu sekarang ada di grup <b>PekaAI - Sharing info & Bansos AI</b>.\n\n"
        f"<b>Peka itu apa?</b>\n"
        f"Peka AI adalah komunitas seputar AI: info AI terbaru, tools dan "
        f"gratisan AI, bansos AI, dan produk digital murah.\n\n"
        f"Yang bisa kamu lakukan di sini:\n"
        f"• Baca info terbaru di channel @peka_aichannel\n"
        f"• Belanja produk digital di store.peka.ai.id\n"
        f"• Order akun premium lewat bot @aeternum_premibot (bayar QRIS, langsung dikirim)\n"
        f"• Tanya-tanya soal Peka di chatbot peka.ai.id\n\n"
        f"Selamat bergabung, jangan sungkan bertanya!"
    )


async def welcome_new_group_member(
    bot: Bot, chat_id: int, user_id: int, first_name: str, username: Optional[str]
) -> bool:
    """Member baru gabung GRUP -> sambutan + tag + info singkat Peka."""
    text = build_group_welcome_text(user_id, first_name, username)
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim sambutan member baru ke {chat_id}: {e}")
        return False


def _read_known_ids() -> Set[int]:
    """ID produk yang sudah dikenal worker (pernah di-broadcast / dicatat)."""
    try:
        return set(
            int(x) for x in KNOWN_PRODUCTS_FILE.read_text().split() if x.strip().isdigit()
        )
    except FileNotFoundError:
        return set()
    except Exception as e:
        logger.warning(f"Tidak bisa baca known_products: {e}")
        return set()


def mark_products_known(product_ids: List[int]) -> None:
    """Catat ID produk sebagai 'sudah dikenal' supaya worker harian tidak
    me-broadcast ulang produk yang sudah di-broadcast saat dibuat admin."""
    try:
        known = _read_known_ids()
        known.update(int(i) for i in product_ids)
        KNOWN_PRODUCTS_FILE.write_text("\n".join(str(i) for i in sorted(known)))
    except Exception as e:
        logger.warning(f"Tidak bisa tulis known_products: {e}")


async def detect_new_products(session) -> List[Product]:
    """Produk aktif yang belum pernah terlihat worker ini.

    Daftar ID yang sudah dikenal disimpan di known_products.txt. Run pertama
    hanya mencatat ID yang ada (tanpa broadcast) supaya tidak membanjiri
    channel dengan seluruh katalog lama.
    """
    res = await session.execute(
        select(Product).where(Product.is_active.is_(True)).order_by(Product.id)
    )
    products = list(res.scalars().all())
    known = _read_known_ids()
    current_ids = {p.id for p in products}
    new = [p for p in products if p.id not in known]
    first_run = not KNOWN_PRODUCTS_FILE.exists()
    mark_products_known(sorted(current_ids))
    if first_run:
        return []
    return new
