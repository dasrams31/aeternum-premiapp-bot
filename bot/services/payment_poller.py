"""
Aeternum PremiApp Bot - Automated Background Payment Poller
Mengecek status pembayaran QRIS secara berkala (setiap 6 detik) ke server BAYAR GG.
Jika terdeteksi sudah dibayar, bot OTOMATIS langsung mengonfirmasi dan mengirimkan produk ke pembeli
tanpa perlu pembeli menekan tombol 'Cek Status' dan tanpa perlu menunggu webhook!
"""

import asyncio
from datetime import datetime
import logging
from aiogram import Bot
from sqlalchemy import select
from database import crud
from database.connection import async_session
from database.models import Product, Transaction
from bot.services.fulfillment import deliver_purchased_product
from config import settings
from webhook.gateway import get_payment_gateway

logger = logging.getLogger("payment_poller")


async def start_auto_payment_poller(bot: Bot, interval_seconds: int = 6) -> None:
    """Task background berkala untuk mendeteksi transaksi QRIS yang sudah lunas."""
    logger.info("Background Auto Payment Poller aktif (Polling interval: %ds).", interval_seconds)
    gateway = get_payment_gateway()

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            now = datetime.utcnow()

            async with async_session() as session:
                # Ambil semua transaksi yang masih PENDING dan belum kedaluwarsa
                stmt = (
                    select(Transaction)
                    .where(Transaction.status == "PENDING")
                    .where(Transaction.expired_at > now)
                    .order_by(Transaction.created_at.desc())
                    .limit(20)
                )
                res = await session.execute(stmt)
                pending_trxs = list(res.scalars().all())

                if not pending_trxs:
                    continue

                for trx in pending_trxs:
                    # Hanya cek ke BAYAR GG jika memiliki gateway_reference yang valid
                    check_ref = trx.gateway_reference
                    if not check_ref:
                        continue

                    try:
                        status_data = await gateway.check_payment_status(check_ref)
                    except Exception as e:
                        logger.warning(f"Gagal cek status payment #{trx.id}: {e}")
                        continue

                    if not status_data:
                        continue

                    raw_status = (status_data.get("status") or "").upper()

                    # JIKA STATUS DI BAYAR GG SUDAH LUNAS / PAID
                    if raw_status in ["PAID", "SUCCESS", "SETTLEMENT"]:
                        logger.info(f"🎉 Auto Poller: Transaksi #{trx.id} terdeteksi LUNAS di BAYAR GG!")

                        # 1. Jika Transaksi TOP UP SALDO
                        if trx.trx_type == "TOPUP":
                            formatted_amount = f"Rp {trx.amount:,.0f}".replace(",", ".")
                            await crud.add_user_balance(session=session, user_id=trx.user_id, amount=float(trx.amount))
                            await crud.mark_transaction_paid(session=session, transaction_id=trx.id, delivered_content=f"TOPUP:{trx.amount}")

                            # Hapus pesan invoice QRIS top-up
                            if trx.telegram_message_id:
                                try:
                                    await bot.delete_message(chat_id=trx.user_id, message_id=trx.telegram_message_id)
                                except Exception:
                                    pass

                            try:
                                await bot.send_message(
                                    chat_id=trx.user_id,
                                    text=(
                                        f"🎉 <b>TOP UP SALDO OTOMATIS BERHASIL!</b>\n\n"
                                        f"🧾 <b>No. Invoice:</b> <code>{trx.id}</code>\n"
                                        f"➕ <b>Nominal Masuk:</b> <code>+{formatted_amount}</code>\n\n"
                                        f"Saldo Anda telah aktif dan siap digunakan untuk berbelanja produk digital secara instan!"
                                    ),
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass

                            try:
                                await bot.send_message(
                                    chat_id=settings.ADMIN_ID,
                                    text=(
                                        f"💰 <b>NOTIFIKASI TOP UP SALDO OTOMATIS!</b>\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                                        f"🆔 <b>Invoice:</b> <code>#{trx.id}</code>\n"
                                        f"💵 <b>Nominal:</b> <code>{formatted_amount}</code>\n"
                                        f"👤 <b>User ID:</b> <code>{trx.user_id}</code>\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━"
                                    ),
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass

                        # 2. Jika Transaksi PEMBELIAN PRODUK
                        else:
                            product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
                            if product:
                                delivered = await deliver_purchased_product(
                                    bot=bot, session=session, transaction=trx, product=product
                                )

                                try:
                                    formatted_amount = f"Rp {trx.amount:,.0f}".replace(",", ".")
                                    await bot.send_message(
                                        chat_id=settings.ADMIN_ID,
                                        text=(
                                            f"💰 <b>NOTIFIKASI PEMBELIAN OTOMATIS!</b>\n"
                                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                                            f"🆔 <b>Invoice:</b> <code>#{trx.id}</code>\n"
                                            f"📦 <b>Produk:</b> {product.name}\n"
                                            f"💵 <b>Nominal:</b> <code>{formatted_amount}</code>\n"
                                            f"👤 <b>Pembeli ID:</b> <code>{trx.user_id}</code>\n"
                                            f"✅ <b>Status Pengiriman:</b> {'Terkirim Otomatis' if delivered else 'Perlu Pengecekan'}\n"
                                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                                            f"<i>Sistem deteksi otomatis Aeternum PremiApp Bot</i>"
                                        ),
                                        parse_mode="HTML",
                                    )
                                except Exception:
                                    pass

                    # JIKA STATUS DI BAYAR GG CANCELLED / EXPIRED
                    elif raw_status in ["EXPIRED", "CANCELLED"]:
                        trx.status = raw_status
                        await session.commit()
                        await crud.release_reserved_stock(session=session, transaction_id=trx.id)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error pada background payment poller: {e}")
