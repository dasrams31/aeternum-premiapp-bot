"""
Aeternum PremiApp Bot - Broadcast rutin ke channel & grup Peka.

Tujuan (ID terverifikasi 7 Nov 2026, bot administrator di keduanya):
- Channel @peka_aichannel  (-1001475296402): transaksi berhasil, info stok,
  stok habis, stok ditambah, produk baru, user bergabung.
- Grup @peka_aigroup      (-1001167087205): ringkasan stok ready harian
  (digest yang sama dengan yang dikirim ke user), user bergabung.

Semua helper di sini TIDAK PERNAH melempar exception ke pemanggil: kegagalan
kirim hanya dicatat di log supaya alur utama (pembayaran, restock, digest)
tidak pernah rusak gara-gara broadcast.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from aiogram import Bot
from sqlalchemy import select

from config import settings
from database.models import Product

logger = logging.getLogger(__name__)

KNOWN_PRODUCTS_FILE = Path(__file__).resolve().parent.parent.parent / "known_products.txt"


def _rupiah(price) -> str:
    return f"Rp {float(price):,.0f}".replace(",", ".")


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


async def broadcast_ready_digest_to_group(bot: Bot, chunks: List[str]) -> int:
    """Kirim ringkasan stok ready harian ke grup Peka. Kembalikan jumlah pesan terkirim."""
    sent = 0
    for chunk in chunks:
        if await send_to_group(bot, chunk):
            sent += 1
            await asyncio.sleep(0.3)
    if sent:
        logger.info("Ready digest terkirim ke grup Peka (%s pesan).", sent)
    return sent


async def broadcast_transaction_success(
    bot: Bot, product_name: str, amount: float, buyer_first_name: Optional[str]
) -> bool:
    """Transaksi berhasil -> channel. Tanpa data sensitif (tanpa WA, ID, atau isi akun)."""
    buyer_line = (
        f"\U0001f464 <b>Pembeli:</b> <b>{buyer_first_name}</b>\n" if buyer_first_name else ""
    )
    text = (
        f"\u2705 <b>TRANSAKSI BERHASIL!</b>\n\n"
        f"\U0001f4e6 <b>Produk:</b> {product_name}\n"
        f"\U0001f4b5 <b>Nominal:</b> <code>{_rupiah(amount)}</code>\n"
        f"{buyer_line}\n"
        f"Beli juga di @aeternum_premibot \u2014 bayar QRIS, langsung dikirim."
    )
    return await send_to_channel(bot, text)


async def broadcast_stock_out(bot: Bot, product: Product) -> bool:
    """Produk TEXT_STOCK kehabisan stok -> channel."""
    text = (
        f"\U0001f525 <b>STOK HABIS!</b>\n\n"
        f"\U0001f4e6 <b>Produk:</b> {product.name}\n"
        f"\U0001f4b5 <b>Harga:</b> <code>{_rupiah(product.price)}</code>\n\n"
        f"Stok sedang diusahakan. Tekan \U0001f514 <b>Ingatkan Saya Saat Restock</b> "
        f"di bot @aeternum_premibot biar dikabari begitu ready lagi."
    )
    return await send_to_channel(bot, text)


async def broadcast_stock_added(bot: Bot, product: Product, added: int, total: int) -> bool:
    """Admin menambah stok akun -> channel."""
    text = (
        f"\U0001f4e6 <b>STOK DITAMBAH!</b>\n\n"
        f"\U0001f4e6 <b>Produk:</b> {product.name}\n"
        f"\u2795 <b>Ditambahkan:</b> <code>+{added} item</code>\n"
        f"\U0001f7e2 <b>Total tersedia:</b> <code>{total} item</code>\n"
        f"\U0001f4b5 <b>Harga:</b> <code>{_rupiah(product.price)}</code>\n\n"
        f"Bila berminat, bisa /start lalu buka \U0001f6cd\ufe0f Katalog Produk "
        f"untuk memesan sebelum kehabisan!"
    )
    return await send_to_channel(bot, text)


async def broadcast_product_added(bot: Bot, product: Product) -> bool:
    """Produk baru masuk katalog -> channel."""
    text = (
        f"\U0001f195 <b>PRODUK BARU!</b>\n\n"
        f"\U0001f4e6 <b>Produk:</b> {product.name}\n"
        f"\U0001f4b5 <b>Harga:</b> <code>{_rupiah(product.price)}</code>\n\n"
        f"Cek langsung di @aeternum_premibot \u2014 bayar QRIS, langsung dikirim."
    )
    return await send_to_channel(bot, text)


async def broadcast_user_joined(bot: Bot, chat_id: int, first_name: str) -> bool:
    """User baru gabung channel/grup -> umumkan di chat yang sama."""
    text = (
        f"\U0001f44b Selamat datang <b>{first_name}</b> di komunitas Peka!\n\n"
        f"Info AI terbaru, bansos, dan produk digital ada di sini. "
        f"Katalog produk: @aeternum_premibot"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"Gagal kirim sambutan gabung ke {chat_id}: {e}")
        return False


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
    try:
        known = set(
            int(x) for x in KNOWN_PRODUCTS_FILE.read_text().split() if x.strip().isdigit()
        )
    except FileNotFoundError:
        known = set()
    except Exception as e:
        logger.warning(f"Tidak bisa baca known_products: {e}")
        known = set()
    current_ids = {p.id for p in products}
    new = [p for p in products if p.id not in known]
    first_run = not KNOWN_PRODUCTS_FILE.exists()
    try:
        KNOWN_PRODUCTS_FILE.write_text("\n".join(str(i) for i in sorted(current_ids)))
    except Exception as e:
        logger.warning(f"Tidak bisa tulis known_products: {e}")
    if first_run:
        return []
    return new
