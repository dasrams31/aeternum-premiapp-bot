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
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set, Tuple

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from sqlalchemy import select

from config import settings
from database.models import Category, Product

logger = logging.getLogger(__name__)

KNOWN_PRODUCTS_FILE = Path(__file__).resolve().parent.parent.parent / "known_products.txt"
LAST_GROUP_WELCOME_FILE = (
    Path(__file__).resolve().parent.parent.parent / "last_group_welcome.json"
)
LAST_DIGEST_PIN_FILE = (
    Path(__file__).resolve().parent.parent.parent / "last_digest_pin.json"
)
# Slide katalog Aeternum (6 PNG) yang disinkron watcher tiap rebuild ke
# dir tetap ini; digest harian 08:00 melampirkannya sebagai album.
# Bila dir/file belum ada, digest jalan teks saja seperti sebelumnya.
DIGEST_SLIDES_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "aeternum_slides"
)
# Serializes welcome delete+send+store so two rapid joins cannot delete
# each other's message.
_WELCOME_LOCK = asyncio.Lock()

BOT_USERNAME = "aeternum_premibot"
BOT_DEEP_LINK_BASE = f"https://t.me/{BOT_USERNAME}"


def _rupiah(price) -> str:
    return f"Rp {float(price):,.0f}".replace(",", ".")


def admin_chat_kb(
    invoice_id: str, buyer_username: Optional[str]
) -> InlineKeyboardMarkup:
    """Tombol chat admin -> pembeli untuk semua DM admin soal satu invoice.

    Baris pertama SELALU ada: "Balas via Chat Bot" membuka thread order-chat
    (callback chat_seller_<invoice>), yang jalan tanpa peduli pembeli punya
    username atau tidak. Bila pembeli punya username, tambah baris kedua
    berupa link langsung ke DM Telegram-nya.
    """
    rows: list = [
        [
            InlineKeyboardButton(
                text="💬 Balas via Chat Bot",
                callback_data=f"chat_seller_{invoice_id}",
            )
        ]
    ]
    if buyer_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Chat Pembeli (Telegram)",
                    url=f"https://t.me/{buyer_username}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def checkout_decision_kb(
    invoice_id: str, buyer_username: Optional[str]
) -> InlineKeyboardMarkup:
    """Tombol keputusan admin di notif checkout: Terima / Tolak / Abaikan.

    Terima HANYA bila pembayaran sudah masuk (cek mutasi/dashboard):
    Terima langsung mengirim produk/saldo ke pembeli. Tolak menandai
    invoice REJECTED tanpa info apa pun ke pembeli. Abaikan hanya
    menutup kartu dan membiarkan invoice apa adanya.
    """
    # Baris chat SELALU ada (pola yang sama dengan handler konfirmasi/laporan
    # di order.py, commit b56c41e): thread order-chat jalan untuk admin
    # tanpa peduli pembeli punya username atau tidak.
    rows: list = list(admin_chat_kb(invoice_id, buyer_username).inline_keyboard)
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
    quantity: int = 1,
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
    qty_line = (
        f"🔢 <b>Jumlah:</b> {quantity}x\n" if int(quantity or 1) > 1 else ""
    )
    text = (
        f"🛒 <b>PERCOBAAN CHECKOUT</b>\n\n"
        f"📦 <b>Produk:</b> {html.escape(product_label)}\n"
        f"{qty_line}"
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


def build_price_change_broadcast_text(
    name: str, cat_name: str, old_price, new_price
) -> str:
    """Teks broadcast perubahan harga (satu sumber: channel + DM)."""
    name = html.escape(name)
    cat = html.escape(cat_name)
    if float(new_price) < float(old_price):
        header = "📉 <b>HARGA TURUN!</b>"
        closer = "Mumpung turun, langsung checkout sebelum berubah lagi! 👇"
    elif float(new_price) > float(old_price):
        header = "📈 <b>HARGA NAIK</b>"
        closer = "Harga baru berlaku mulai sekarang. 👇"
    else:
        header = "💲 <b>HARGA BERUBAH</b>"
        closer = "Cek harga terbaru di bawah! 👇"
    lines = [
        header,
        "",
        f"📦 <b>{name}</b>",
        f"🏷️ Kategori: {cat}",
        f"💲 Harga lama: {_rupiah(old_price)}",
        f"💲 Harga baru: <b>{_rupiah(new_price)}</b>",
        "",
        closer,
    ]
    return "\n".join(lines)


def build_price_change_admin_text(
    name: str, old_price, new_price, sources: str, current_prices: str, drift: bool
) -> str:
    """Teks DM admin untuk perubahan harga: sumber + harga per sumber."""
    if float(new_price) < float(old_price):
        direction = "📉 Turun"
    elif float(new_price) > float(old_price):
        direction = "📈 Naik"
    else:
        direction = "💲 Berubah"
    lines = [
        "🔔 <b>NOTIF HARGA (ADMIN)</b>",
        "",
        f"📦 <b>{html.escape(name)}</b>",
        f"{direction}: {_rupiah(old_price)} → <b>{_rupiah(new_price)}</b>",
        f"📍 Sumber berubah: {html.escape(sources) if sources else '-'}",
    ]
    if current_prices:
        lines.append(f"💰 Harga saat ini: {html.escape(current_prices)}")
    if drift:
        lines.append("⚠️ Harga antar sumber belum sama, cek konsistensi.")
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


async def send_to_channel_msg(bot: Bot, text: str, **kwargs) -> Optional[Message]:
    """Kirim satu pesan ke channel Peka, kembalikan Message (None bila gagal)."""
    try:
        return await bot.send_message(
            chat_id=settings.PEKA_CHANNEL_ID, text=text, parse_mode="HTML", **kwargs
        )
    except Exception as e:
        logger.warning(f"Gagal kirim ke channel Peka: {e}")
        return None


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


async def send_to_aeternum_msg(bot: Bot, text: str, **kwargs) -> Optional[Message]:
    """Kirim satu pesan ke channel Aeternum, kembalikan Message (None bila gagal)."""
    try:
        return await bot.send_message(
            chat_id=settings.AETERNUM_CHANNEL_ID, text=text, parse_mode="HTML", **kwargs
        )
    except Exception as e:
        logger.warning(f"Gagal kirim ke channel Aeternum: {e}")
        return None


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


async def send_to_admin_dm(bot: Bot, text: str, **kwargs) -> bool:
    """Kirim satu pesan ke DM admin. Kembalikan True bila terkirim."""
    try:
        await bot.send_message(
            chat_id=settings.ADMIN_ID, text=text, parse_mode="HTML", **kwargs
        )
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim DM admin: {e}")
        return False


async def _send_receipt_photo(bot: Bot, chat_id: int, photo: bytes, caption: str) -> bool:
    """Kirim gambar struk + caption teks. True bila terkirim."""
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(photo, filename="struk-aeternum.jpg"),
            caption=caption,
        )
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim struk ke {chat_id}: {e}")
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


def _read_last_digest_pins() -> dict:
    """{str(chat_id): message_id} digest yang sedang ter-pin di tiap channel."""
    try:
        data = json.loads(LAST_DIGEST_PIN_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write_last_digest_pins(ids: dict) -> None:
    try:
        LAST_DIGEST_PIN_FILE.write_text(json.dumps(ids))
    except OSError as e:
        logger.warning(f"Tidak bisa tulis {LAST_DIGEST_PIN_FILE}: {e}")


async def pin_digest_message(bot: Bot, chat_id: int, message_id: int) -> None:
    """Pin digest terbaru di channel (tanpa notifikasi), lalu unpin digest
    hari sebelumnya supaya hanya yang terbaru yang ter-pin. Gagal pin/unpin
    hanya dicatat, tidak menggagalkan digest."""
    try:
        await bot.pin_chat_message(
            chat_id=chat_id, message_id=message_id, disable_notification=True
        )
    except Exception as e:
        logger.warning(f"Gagal pin digest {message_id} di {chat_id}: {e}")
        return
    pins = _read_last_digest_pins()
    prev_id = pins.get(str(chat_id))
    if prev_id and int(prev_id) != message_id:
        try:
            await bot.unpin_chat_message(chat_id=chat_id, message_id=int(prev_id))
        except Exception as e:
            logger.warning(f"Gagal unpin digest lama {prev_id} di {chat_id}: {e}")
    pins[str(chat_id)] = message_id
    _write_last_digest_pins(pins)


def get_digest_slide_paths() -> List[Path]:
    """6 slide katalog Aeternum yang disinkron watcher, atau [] bila belum ada."""
    paths = [DIGEST_SLIDES_DIR / f"slide-{i}.png" for i in range(1, 7)]
    return paths if all(p.is_file() for p in paths) else []


async def send_digest_slides(
    bot: Bot, chat_id: int, file_ids: Optional[List[str]] = None
) -> Optional[List[str]]:
    """Kirim album 6 slide katalog Aeternum ke satu chat.

    Bila file_ids (6) diberikan, pakai file_id Telegram supaya tidak upload
    ulang. Kembalikan daftar file_id album yang terkirim, atau None bila
    tidak ada slide / gagal kirim. Tidak pernah melempar: digest teks
    tetap jalan bila slide gagal.
    """
    if file_ids and len(file_ids) == 6:
        media = [InputMediaPhoto(media=fid) for fid in file_ids]
    else:
        paths = get_digest_slide_paths()
        if not paths:
            return None
        media = [InputMediaPhoto(media=FSInputFile(p)) for p in paths]
    try:
        msgs = await bot.send_media_group(chat_id=chat_id, media=media)
        ids = [m.photo[-1].file_id for m in msgs if m.photo]
        if len(ids) == 6:
            logger.info("Slide digest terkirim ke %s (6 foto).", chat_id)
            return ids
        logger.warning(
            "Slide digest ke %s hanya %s/6 foto, file_id tidak dipakai ulang.",
            chat_id, len(ids),
        )
        return None
    except Exception as e:
        logger.warning(f"Gagal kirim slide digest ke {chat_id}: {e}")
        return None


async def broadcast_ready_digest_to_channel(bot: Bot, chunks: List[str]) -> int:
    """Kirim ringkasan stok ready harian ke channel Peka (grup ikut dapat
    lewat discussion yang terhubung, tanpa kirim dobel). Kembalikan jumlah pesan terkirim."""
    sent = 0
    first_id = None
    for i, chunk in enumerate(chunks):
        kb = digest_kb() if i == len(chunks) - 1 else None
        if i == 0:
            msg = await send_to_channel_msg(bot, chunk, reply_markup=kb)
            if msg:
                first_id = msg.message_id
                sent += 1
        elif await send_to_channel(bot, chunk, reply_markup=kb):
            sent += 1
        await asyncio.sleep(0.3)
    if sent:
        logger.info("Ready digest terkirim ke channel Peka (%s pesan).", sent)
    if first_id:
        await pin_digest_message(bot, settings.PEKA_CHANNEL_ID, first_id)
    return sent


async def broadcast_ready_digest_to_aeternum(bot: Bot, chunks: List[str]) -> int:
    """Kirim ringkasan stok ready harian ke channel Aeternum. Kembalikan jumlah pesan terkirim."""
    sent = 0
    first_id = None
    for i, chunk in enumerate(chunks):
        kb = digest_kb() if i == len(chunks) - 1 else None
        if i == 0:
            msg = await send_to_aeternum_msg(bot, chunk, reply_markup=kb)
            if msg:
                first_id = msg.message_id
                sent += 1
        elif await send_to_aeternum(bot, chunk, reply_markup=kb):
            sent += 1
        await asyncio.sleep(0.3)
    if sent:
        logger.info("Ready digest terkirim ke channel Aeternum (%s pesan).", sent)
    if first_id:
        await pin_digest_message(bot, settings.AETERNUM_CHANNEL_ID, first_id)
    return sent


async def broadcast_transaction_success(
    bot: Bot,
    product_name: str,
    amount: float,
    buyer_first_name: Optional[str] = None,
    invoice_id: Optional[str] = None,
    buyer_username: Optional[str] = None,
    payment_method: Optional[str] = None,
    paid_at: Optional[datetime] = None,
    quantity: int = 1,
    unit_price: Optional[float] = None,
) -> bool:
    """Transaksi berhasil -> channel Aeternum + grup Peka + DM admin.

    Format struk pembelian (perintah user 16 Nov 2026, meniru struk toko
    referensi): gambar kartu struk + teks "STRUK PEMBELIAN" dengan detail
    pembelian dan ID invoice Aeternum (Order), nama pembeli (@username bila
    ada), metode, dan waktu WIB. Tanpa WA atau isi akun. Bila render gambar
    gagal, kirim teks saja supaya broadcast tidak pernah hilang.
    """
    from bot.services.receipt import build_receipt_text, render_receipt_image

    text = build_receipt_text(
        product_name=product_name,
        amount=amount,
        invoice_id=invoice_id,
        buyer_username=buyer_username,
        buyer_first_name=buyer_first_name,
        payment_method=payment_method,
        paid_at=paid_at,
        quantity=quantity,
        unit_price=unit_price,
    )
    try:
        photo = render_receipt_image(
            product_name=product_name,
            amount=amount,
            invoice_id=invoice_id,
            buyer_username=buyer_username,
            buyer_first_name=buyer_first_name,
            payment_method=payment_method,
            paid_at=paid_at,
            quantity=quantity,
            unit_price=unit_price,
        )
    except Exception as e:
        logger.warning(f"Gagal render struk #{invoice_id}: {e}")
        photo = None

    if photo:
        ok = await _send_receipt_photo(
            bot, settings.AETERNUM_CHANNEL_ID, photo, text
        )
        await _send_receipt_photo(bot, settings.PEKA_GROUP_ID, photo, text)
        await _send_receipt_photo(bot, settings.ADMIN_ID, photo, text)
        if not ok:
            ok = await send_to_aeternum(bot, html.escape(text))
            await send_to_group(bot, html.escape(text))
            await send_to_admin_dm(bot, html.escape(text))
        return ok

    ok = await send_to_aeternum(bot, html.escape(text))
    await send_to_group(bot, html.escape(text))
    await send_to_admin_dm(bot, html.escape(text))
    return ok


async def broadcast_stock_out(bot: Bot, session, product: Product) -> bool:
    """Produk TEXT_STOCK kehabisan stok -> channel Aeternum + grup Peka +
    DM admin, dengan tombol pengingat restock (deep-link /start remind_<id>)."""
    cat_name = await get_category_name(session, product.category_id)
    text = build_stock_out_text(product, cat_name)
    kb = remind_kb(product.id)
    ok = await send_to_aeternum(bot, text, reply_markup=kb)
    await send_to_group(bot, text, reply_markup=kb)
    await send_to_admin_dm(bot, text, reply_markup=kb)
    return ok


async def broadcast_price_changed(
    bot: Bot,
    session,
    product,
    name: str,
    cat_name: str,
    old_price,
    new_price,
) -> bool:
    """Harga berubah -> channel Aeternum + grup Peka (format baru + tombol
    Beli Sekarang bila produknya ada di bot). Bagian channel dari
    broadcast_price_change_event."""
    text = build_price_change_broadcast_text(name, cat_name, old_price, new_price)
    kb = product_buy_kb(product.id) if product is not None else None
    ok = await send_to_aeternum(bot, text, reply_markup=kb)
    await send_to_group(bot, text, reply_markup=kb)
    return ok


async def broadcast_stock_added(
    bot: Bot,
    session,
    product: Product,
    added: int,
    total: int,
    test_label: str = "",
) -> bool:
    """Admin menambah stok akun -> channel Aeternum + grup Peka (format
    restock baru + tombol Beli Sekarang). Bagian channel dari
    broadcast_restock_event."""
    cat_name = await get_category_name(session, product.category_id)
    text = build_restock_broadcast_text(product, cat_name, added, total)
    if test_label:
        text = f"{test_label}\n{text}"
    kb = product_buy_kb(product.id)
    ok = await send_to_aeternum(bot, text, reply_markup=kb)
    await send_to_group(bot, text, reply_markup=kb)
    return ok


async def broadcast_product_added(
    bot: Bot, session, product: Product, test_label: str = ""
) -> bool:
    """Produk baru masuk katalog -> channel Aeternum + grup Peka (format
    baru + tombol Beli Sekarang). Bagian channel dari
    broadcast_new_product_event."""
    from database import crud

    cat_name = await get_category_name(session, product.category_id)
    count = None
    if product.product_type == "TEXT_STOCK":
        count = await crud.count_available_stock(session=session, product_id=product.id)
    text = build_new_product_broadcast_text(product, cat_name, count)
    if test_label:
        text = f"{test_label}\n{text}"
    kb = product_buy_kb(product.id)
    ok = await send_to_aeternum(bot, text, reply_markup=kb)
    await send_to_group(bot, text, reply_markup=kb)
    return ok


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


def _read_last_welcome_ids() -> dict:
    """{str(chat_id): message_id} sambutan grup terakhir yang terkirim."""
    try:
        data = json.loads(LAST_GROUP_WELCOME_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write_last_welcome_ids(ids: dict) -> None:
    try:
        LAST_GROUP_WELCOME_FILE.write_text(json.dumps(ids))
    except OSError as e:
        logger.warning(f"Tidak bisa tulis {LAST_GROUP_WELCOME_FILE}: {e}")


async def welcome_new_group_member(
    bot: Bot, chat_id: int, user_id: int, first_name: str, username: Optional[str]
) -> bool:
    """Member baru gabung GRUP -> sambutan + tag + info singkat Peka.

    Rolling: hanya sambutan terbaru yang bertahan. Pesan sambutan lama
    (id tersimpan di last_group_welcome.json) dihapus setelah sambutan
    baru terkirim, lalu id baru disimpan. Kirim dulu baru hapus, supaya
    sambutan tidak hilang bila kirim gagal.
    """
    text = build_group_welcome_text(user_id, first_name, username)
    async with _WELCOME_LOCK:
        prev_ids = _read_last_welcome_ids()
        prev_id = prev_ids.get(str(chat_id))
        try:
            sent = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Gagal kirim sambutan member baru ke {chat_id}: {e}")
            return False
        if prev_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=int(prev_id))
            except Exception as e:
                logger.warning(
                    f"Gagal hapus sambutan lama {prev_id} di {chat_id}: {e}"
                )
        prev_ids[str(chat_id)] = sent.message_id
        _write_last_welcome_ids(prev_ids)
        return True


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
