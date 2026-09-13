"""
Aeternum PremiApp Bot - Automated Fulfillment Service
Pengiriman produk instan dengan proteksi salin & format teks rapi.
"""

import logging
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from database.models import Product, Transaction

logger = logging.getLogger(__name__)


async def deliver_purchased_product(
    bot: Bot,
    session: AsyncSession,
    transaction: Transaction,
    product: Product,
) -> bool:
    """
    Mengirimkan produk yang berhasil dibayar ke chat pembeli secara otomatis.
    """
    user_id = transaction.user_id
    delivered_text = ""

    try:
        # ==========================================
        # 1. TIPE: TEXT_STOCK (Akun / Serial Key Unik)
        # ==========================================
        if product.product_type == "TEXT_STOCK":
            item = await crud.get_and_lock_available_item(
                session=session,
                product_id=product.id,
                transaction_id=transaction.id,
            )

            if not item:
                logger.error(f"Stok habis mendadak untuk order #{transaction.id}")
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⚠️ <b>Pembayaran Berhasil Diterima!</b>\n\n"
                        "Namun stok produk ini baru saja habis sebelum terkirim. "
                        "Admin kami telah menerima notifikasi dan akan segera menghubungi Anda untuk pengiriman manual / refund."
                    ),
                    parse_mode="HTML",
                )
                return False

            delivered_text = item.content
            message_text = (
                f"🎉 <b>PEMBAYARAN BERHASIL & TERKONFIRMASI!</b>\n\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"🧾 <b>No. Invoice:</b> <code>{transaction.id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 <b>DETAIL KREDENSIAL / LISENSI ANDA:</b>\n\n"
                f"<code>{delivered_text}</code>\n\n"
                f"<i>💡 Ketuk kotak abu-abu di atas untuk menyalin langsung.</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <i>Simpan kredensial ini. Riwayat tersimpan di menu /riwayat.</i>"
            )

            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="HTML",
                protect_content=True,
            )

        # ==========================================
        # 2. TIPE: TEXT_STATIC (Template / Prompt / Link)
        # ==========================================
        elif product.product_type == "TEXT_STATIC":
            delivered_text = product.text_content or "Tidak ada teks konten."
            message_text = (
                f"🎉 <b>PEMBAYARAN BERHASIL & TERKONFIRMASI!</b>\n\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"🧾 <b>No. Invoice:</b> <code>{transaction.id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>KONTEN PRODUK / AKSES:</b>\n\n"
                f"{delivered_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Terima kasih telah berbelanja di <b>Aeternum PremiApp Bot</b>!"
            )

            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="HTML",
                protect_content=True,
            )

        # ==========================================
        # 3. TIPE: FILE (PDF / ZIP / Dokumen)
        # ==========================================
        elif product.product_type == "FILE":
            if not product.telegram_file_id:
                logger.error(f"File ID kosong untuk produk #{product.id}")
                return False

            caption = (
                f"🎉 <b>PEMBAYARAN BERHASIL!</b>\n\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"🧾 <b>No. Invoice:</b> <code>{transaction.id}</code>\n\n"
                f"File produk Anda terlampir di atas. Selamat menikmati!"
            )

            await bot.send_document(
                chat_id=user_id,
                document=product.telegram_file_id,
                caption=caption,
                parse_mode="HTML",
                protect_content=True,
            )
            delivered_text = f"FILE:{product.telegram_file_id}"

        # ==========================================
        # 4. TIPE: INVITE_LINK (Channel / Grup VIP)
        # ==========================================
        elif product.product_type == "INVITE_LINK":
            if not product.vip_chat_id:
                logger.error(f"VIP Chat ID kosong untuk produk #{product.id}")
                return False

            # Buat one-time invite link yang hanya bisa dipakai 1 orang
            invite_link = await bot.create_chat_invite_link(
                chat_id=product.vip_chat_id,
                member_limit=1,
                name=f"Order {transaction.id}",
            )
            delivered_text = invite_link.invite_link

            message_text = (
                f"🎉 <b>PEMBAYARAN BERHASIL & TERKONFIRMASI!</b>\n\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"🧾 <b>No. Invoice:</b> <code>{transaction.id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 <b>TAUTAN UNDANGAN VIP ANDA:</b>\n\n"
                f"👉 <a href='{invite_link.invite_link}'>Klik Di Sini untuk Bergabung</a>\n\n"
                f"<i>⚠️ Tautan ini eksklusif dan hanya berlaku untuk 1 kali penggunaan.</i>"
            )

            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="HTML",
                protect_content=True,
            )

        # Catat status transaksi PAID & arsip konten terkirim
        await crud.mark_transaction_paid(
            session=session,
            transaction_id=transaction.id,
            delivered_content=delivered_text,
        )
        return True

    except Exception as e:
        logger.exception(f"Gagal memproses fulfillment order #{transaction.id}: {e}")
        return False
