"""
Aeternum PremiApp Bot - Daily Stock Updater
Worker harian: menyelaraskan flag is_out_of_stock produk TEXT_STOCK dengan
jumlah stok asli yang belum terjual, memberi tahu pembeli yang menunggu
restock saat sebuah produk kembali ready, dan mengirim ringkasan stok ready
harian ke semua user yang sudah /start bot.

Latar: add_stock_items_bulk() tidak pernah mengubah is_out_of_stock, jadi
produk yang di-restock manual bisa tetap tampil "Stok Belum Tersedia" sampai
flag-nya dibersihkan manual. Worker ini menutup celah itu setiap hari.

Hanya produk TEXT_STOCK yang disentuh untuk sinkron flag. TEXT_STATIC /
FILE / INVITE_LINK tidak punya baris product_items sehingga flag mereka
tetap manual, tapi mereka ikut tampil di ringkasan harian selama aktif
dan tidak ditandai out-of-stock.

Digest harian dikirim maksimal sekali per hari kalender (WIB), dicatat di
last_digest.txt di folder bot, supaya restart bot tidak mengirim duplikat
di hari yang sama.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select

from bot.services.broadcast import (
    broadcast_product_added,
    broadcast_ready_digest_to_channel,
    broadcast_stock_out,
    detect_new_products,
)
from database import crud
from database.connection import async_session
from database.models import Category, Product

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
MAX_CHUNK = 3500
DIGEST_STAMP_FILE = Path(__file__).resolve().parent.parent.parent / "last_digest.txt"


def _rupiah(price) -> str:
    return f"Rp {float(price):,.0f}".replace(",", ".")


def build_restock_text(product: Product, new_total: int) -> str:
    """Teks notifikasi restock (satu sumber, dipakai worker + admin)."""
    return (
        f"\U0001f514 <b>PRODUK SUDAH RESTOCK!</b>\n\n"
        f"Produk <b>{product.name}</b> yang Anda tunggu kini telah tersedia kembali!\n"
        f"\U0001f7e2 <b>Stok Baru:</b> <code>{new_total} item</code>\n"
        f"\U0001f4b5 <b>Harga:</b> <code>{_rupiah(product.price)}</code>\n\n"
        f"Bila berminat, bisa /start lalu buka \U0001f6cd\ufe0f Katalog Produk "
        f"untuk memesan sebelum kehabisan!"
    )


async def notify_restock_subscribers(bot: Bot, session, product: Product, new_total: int) -> int:
    """Kirim notifikasi restock ke semua penunggu produk; kembalikan jumlah terkirim."""
    waiting = await crud.get_and_clear_restock_subscribers(session=session, product_id=product.id)
    sent = 0
    for uid in waiting:
        try:
            await bot.send_message(
                chat_id=uid, text=build_restock_text(product, new_total), parse_mode="HTML"
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Gagal kirim notifikasi restock ke {uid} ({product.name}): {e}")
    return sent


async def sync_stock_flags(session) -> List[Tuple[Product, bool, bool, int]]:
    """Samakan flag is_out_of_stock dengan stok asli. Kembalikan produk yang berubah."""
    res = await session.execute(
        select(Product).where(
            Product.product_type == "TEXT_STOCK",
            Product.is_active.is_(True),
        )
    )
    changed = []
    for product in res.scalars().all():
        count = await crud.count_available_stock(session=session, product_id=product.id)
        new_flag = count == 0
        if product.is_out_of_stock != new_flag:
            changed.append((product, product.is_out_of_stock, new_flag, count))
            product.is_out_of_stock = new_flag
    if changed:
        await session.commit()
    return changed


async def get_ready_products(session) -> List[Tuple[Product, Optional[int], str]]:
    """Produk yang bisa dibeli sekarang: aktif + tidak out-of-stock.

    TEXT_STOCK wajib punya item belum terjual (>0). Tipe lain ready
    selama flag-nya False. Kembalikan (product, jumlah_item/None, nama_kategori).
    """
    cats = (await session.execute(select(Category))).scalars().all()
    cat_names = {c.id: c.name for c in cats}
    res = await session.execute(
        select(Product)
        .where(Product.is_active.is_(True), Product.is_out_of_stock.is_(False))
        .order_by(Product.category_id, Product.name)
    )
    ready = []
    for product in res.scalars().all():
        count = None
        if product.product_type == "TEXT_STOCK":
            count = await crud.count_available_stock(session=session, product_id=product.id)
            if count == 0:
                continue
        ready.append((product, count, cat_names.get(product.category_id, "Lainnya")))
    return ready


def build_ready_digest_chunks(ready: List[Tuple[Product, Optional[int], str]]) -> List[str]:
    """Ringkasan stok ready harian, dipecah per max 3500 karakter."""
    date_str = datetime.now(WIB).strftime("%d %B %Y")
    header = f"\U0001f4e6 <b>STOK READY HARI INI</b>\n\U0001f4c5 {date_str}"
    footer = (
        "\nBila berminat, bisa /start lalu buka "
        "\U0001f6cd\ufe0f Katalog Produk untuk memesan!"
    )
    lines = [header]
    current_cat = None
    for product, count, cat_name in ready:
        if cat_name != current_cat:
            current_cat = cat_name
            lines.append(f"\n<b>{cat_name}</b>")
        if count is not None:
            lines.append(f"\u2022 {product.name} \u2014 {_rupiah(product.price)} ({count} item)")
        else:
            lines.append(f"\u2022 {product.name} \u2014 {_rupiah(product.price)}")
    lines.append(footer)
    chunks: List[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > MAX_CHUNK and current:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def _digest_sent_today() -> bool:
    try:
        return DIGEST_STAMP_FILE.read_text().strip() == datetime.now(WIB).strftime("%Y-%m-%d")
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Tidak bisa baca stamp digest: {e}")
        return False


def _mark_digest_sent() -> None:
    try:
        DIGEST_STAMP_FILE.write_text(datetime.now(WIB).strftime("%Y-%m-%d"))
    except Exception as e:
        logger.warning(f"Tidak bisa tulis stamp digest: {e}")


async def send_daily_ready_digest(bot: Bot, session) -> Tuple[int, int]:
    """Kirim ringkasan stok ready ke semua user (maks 1x/hari). Kembalikan (penerima, pesan)."""
    if _digest_sent_today():
        logger.info("Daily ready digest dilewati: sudah terkirim hari ini.")
        return 0, 0
    ready = await get_ready_products(session)
    if not ready:
        logger.info("Daily ready digest dilewati: tidak ada produk ready.")
        return 0, 0
    chunks = build_ready_digest_chunks(ready)
    # Broadcast rutin: ringkasan dikirim ke channel Peka saja. Grup ikut
    # dapat lewat discussion yang terhubung (tanpa kirim dobel).
    await broadcast_ready_digest_to_channel(bot, chunks)
    user_ids = await crud.get_all_user_ids(session=session)
    sent = 0
    for uid in user_ids:
        ok = True
        for chunk in chunks:
            try:
                await bot.send_message(chat_id=uid, text=chunk, parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(f"Gagal kirim ready digest ke {uid}: {e}")
                ok = False
                break
        if not ok:
            continue
    _mark_digest_sent()
    logger.info(
        "Daily ready digest terkirim ke %s user (%s produk ready, %s pesan).",
        len(user_ids), len(ready), sent,
    )
    return len(user_ids), sent


async def run_daily_stock_update(bot: Bot):
    """Satu putaran update: sinkron flag, notifikasi restock, lalu digest harian."""
    async with async_session() as session:
        changed = await sync_stock_flags(session)
        notified_total = 0
        for product, old_flag, new_flag, count in changed:
            if old_flag and not new_flag:
                notified_total += await notify_restock_subscribers(bot, session, product, count)
            elif not old_flag and new_flag:
                # Broadcast rutin: produk kehabisan stok -> channel Peka
                await broadcast_stock_out(bot, product)
        # Broadcast rutin: produk baru masuk katalog -> channel Peka
        for new_product in await detect_new_products(session):
            await broadcast_product_added(bot, new_product)
        if changed:
            for product, old_flag, new_flag, count in changed:
                logger.info(
                    "Stok %s (id=%s): flag %s -> %s, tersedia %s item",
                    product.name, product.id, old_flag, new_flag, count,
                )
        recipients, digest_sent = await send_daily_ready_digest(bot, session)
        logger.info(
            "Daily stock update selesai: %s produk berubah, %s notifikasi restock terkirim, "
            "digest ke %s user (%s pesan).",
            len(changed), notified_total, recipients, digest_sent,
        )
        return changed, notified_total, recipients, digest_sent


async def start_daily_stock_updater(bot: Bot) -> None:
    """Task background: jalan 60 detik setelah bot start (catch-up sinkronisasi),
    lalu tiap hari jam 08:00 WIB."""
    logger.info("Background Daily Stock Updater aktif.")
    await asyncio.sleep(60)
    while True:
        try:
            await run_daily_stock_update(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Daily stock update gagal (akan dicoba lagi besok).")
        await asyncio.sleep(_seconds_until_next_0800())


def _seconds_until_next_0800() -> float:
    """Detik sampai jam 08:00 WIB berikutnya."""
    now = datetime.now(WIB)
    target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()
