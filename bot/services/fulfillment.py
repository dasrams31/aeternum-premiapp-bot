"""
Aeternum PremiApp Bot - Automated Fulfillment & Commission Engine
Pengiriman produk instan, finalisasi stok terjual permanen, masa aktif langganan, komisi & review.
"""

from datetime import datetime, timedelta
import logging
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from database.models import Product, PromoCode, Transaction, User
from config import settings
from bot.keyboards.user_kb import contact_admin_kb, review_prompt_kb

logger = logging.getLogger(__name__)


async def deliver_purchased_product(
    bot: Bot,
    session: AsyncSession,
    transaction: Transaction,
    product: Product,
) -> bool:
    """
    Mengirimkan produk yang berhasil dibayar ke chat pembeli secara otomatis,
    mengubah stok reserved menjadi TERJUAL PERMANEN, mencatat masa aktif langganan,
    mencatat promo, dan membagikan komisi.
    """
    user_id = transaction.user_id
    delivered_text = ""

    # Hapus pesan invoice QRIS agar tidak menumpuk di chat pembeli
    if transaction.telegram_message_id:
        try:
            await bot.delete_message(chat_id=user_id, message_id=transaction.telegram_message_id)
        except Exception:
            pass

    try:
        # ==========================================
        # 1. TIPE: TEXT_STOCK (Finalisasi Kunci Stok ke Terjual)
        # ==========================================
        if product.product_type == "TEXT_STOCK":
            item = await crud.finalize_reserved_stock(
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
            
            war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus")
            war_desc = f"\n<i>{product.warranty_note}</i>" if product.warranty_note else ""

            message_text = (
                f"🎉 <b>PEMBAYARAN BERHASIL & TERKONFIRMASI!</b>\n\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"🧾 <b>No. Invoice:</b> <code>{transaction.id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 <b>DETAIL KREDENSIAL / LISENSI ANDA:</b>\n\n"
                f"<code>{delivered_text}</code>\n\n"
                f"<i>💡 Ketuk kotak abu-abu di atas untuk menyalin langsung.</i>\n"
                f"📞 <b>Konfirmasi pembelian:</b> @dasrams\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ <b>KETENTUAN GARANSI:</b>\n"
                f"<b>{war_badge}</b>{war_desc}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <i>Simpan kredensial ini. Riwayat tersimpan di menu /riwayat.</i>"
            )

            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="HTML",
                protect_content=True,
                reply_markup=contact_admin_kb(transaction.id),
            )

        # ==========================================
        # 2. TIPE: TEXT_STATIC
        # ==========================================
        elif product.product_type == "TEXT_STATIC":
            delivered_text = product.text_content or "Tidak ada teks konten."
            war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus")
            war_desc = f"\n<i>{product.warranty_note}</i>" if product.warranty_note else ""

            message_text = (
                f"🎉 <b>PEMBAYARAN BERHASIL & TERKONFIRMASI!</b>\n\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"🧾 <b>No. Invoice:</b> <code>{transaction.id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>KONTEN PRODUK / AKSES:</b>\n\n"
                f"{delivered_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ <b>KETENTUAN GARANSI:</b>\n"
                f"<b>{war_badge}</b>{war_desc}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📞 <b>Konfirmasi pembelian:</b> @dasrams\n"
                f"Terima kasih telah berbelanja di <b>Aeternum PremiApp Bot</b>!"
            )

            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="HTML",
                protect_content=True,
                reply_markup=contact_admin_kb(transaction.id),
            )

        # ==========================================
        # 3. TIPE: FILE
        # ==========================================
        elif product.product_type == "FILE":
            if not product.telegram_file_id:
                logger.error(f"File ID kosong untuk produk #{product.id}")
                return False

            war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus")
            war_desc = f"\n<i>{product.warranty_note}</i>" if product.warranty_note else ""

            caption = (
                f"🎉 <b>PEMBAYARAN BERHASIL!</b>\n\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"🧾 <b>No. Invoice:</b> <code>{transaction.id}</code>\n\n"
                f"🛡️ <b>Ketentuan Garansi:</b> <b>{war_badge}</b>{war_desc}\n\n"
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
        # 4. TIPE: INVITE_LINK
        # ==========================================
        elif product.product_type == "INVITE_LINK":
            if not product.vip_chat_id:
                logger.error(f"VIP Chat ID kosong untuk produk #{product.id}")
                return False

            war_badge = "❌ Tidak Ada Garansi" if product.warranty_type == "NONE" else ("⚡ Garansi 24 Jam" if product.warranty_type == "24_HOURS" else "📝 Garansi Khusus")
            war_desc = f"\n<i>{product.warranty_note}</i>" if product.warranty_note else ""

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
                f"<i>⚠️ Tautan ini eksklusif dan hanya berlaku untuk 1 kali penggunaan.</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ <b>KETENTUAN GARANSI:</b>\n"
                f"<b>{war_badge}</b>{war_desc}\n"
            )

            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="HTML",
                protect_content=True,
            )

        # ==========================================
        # 5. HITUNG MASA AKTIF LANGGANAN
        # ==========================================
        expires_service_at = None
        if product.duration_days and product.duration_days > 0:
            expires_service_at = datetime.utcnow() + timedelta(days=product.duration_days)

        # ==========================================
        # 6. CATAT PENGGUNAAN PROMO
        # ==========================================
        if transaction.promo_code:
            promo_res = await session.execute(
                select(PromoCode).where(PromoCode.code == transaction.promo_code)
            )
            promo_obj = promo_res.scalar_one_or_none()
            if promo_obj:
                await crud.record_promo_usage(
                    session=session,
                    promo_id=promo_obj.id,
                    user_id=user_id,
                    transaction_id=transaction.id,
                    discount_amount=float(transaction.discount_amount or 0.0),
                )

        # ==========================================
        # 6b. POTONG SALDO KOMISI (diskon referral 10%)
        # ==========================================
        ref_discount = float(getattr(transaction, "referral_discount", 0.0) or 0.0)
        if ref_discount > 0:
            deducted = await crud.deduct_referral_balance_atomic(
                session=session, user_id=user_id, amount=ref_discount
            )
            logger.info(
                "Diskon saldo komisi order #%s: dijanjikan Rp%s, terpotong Rp%s",
                transaction.id,
                ref_discount,
                deducted,
            )

        # ==========================================
        # 7. DISTRIBUSI KOMISI REFERRAL (5%)
        # ==========================================
        user_res = await session.execute(select(User).where(User.id == user_id))
        buyer = user_res.scalar_one_or_none()

        if buyer and buyer.referred_by:
            commission = float(transaction.amount) * 0.05
            if commission > 0:
                await crud.add_referral_commission(
                    session=session,
                    referrer_id=buyer.referred_by,
                    commission_amount=commission,
                )
                try:
                    formatted_commission = f"Rp {commission:,.0f}".replace(",", ".")
                    await bot.send_message(
                        chat_id=buyer.referred_by,
                        text=(
                            f"💰 <b>KOMISI REFERRAL DITERIMA!</b>\n\n"
                            f"Teman yang Anda undang baru saja membeli <b>{product.name}</b>.\n"
                            f"➕ Saldo Komisi: <b>+{formatted_commission}</b>\n\n"
                            f"<i>Saldo komisi bisa dipakai sebagai diskon 10% di pembelianmu berikutnya. "
                            f"Cek totalnya di menu '👥 Program Afiliasi'.</i>"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        # ==========================================
        # 8. KIRIM PROMPT RATING & ULASAN
        # ==========================================
        try:
            review_prompt_text = (
                f"⭐ <b>BAGAIMANA PENGALAMAN BERBELANJA ANDA?</b>\n\n"
                f"Pesanan untuk <b>{product.name}</b> telah selesai.\n"
                f"Beri kami nilai untuk membantu meningkatkan kualitas layanan kami:"
            )
            await bot.send_message(
                chat_id=user_id,
                text=review_prompt_text,
                reply_markup=review_prompt_kb(transaction.id),
                parse_mode="HTML",
            )
        except Exception:
            pass

        # ==========================================
        # 9. NOTIFIKASI PEMBELIAN KE ADMIN (TEXT_STOCK: konfirmasi manual)
        # ==========================================
        if product.product_type == "TEXT_STOCK":
            try:
                buyer_label = f"ID {user_id}"
                if buyer:
                    if buyer.username:
                        buyer_label = f"{buyer.first_name or ''} (@{buyer.username})".strip()
                    elif buyer.first_name:
                        buyer_label = buyer.first_name
                remaining = await crud.count_available_stock(session=session, product_id=product.id)
                wib_now = (datetime.utcnow() + timedelta(hours=7)).strftime("%d %b %Y %H:%M WIB")
                price_str = f"Rp {float(transaction.amount or 0):,.0f}".replace(",", ".")
                admin_text = (
                    f"🛒 <b>PEMBELIAN BARU</b>\n\n"
                    f"📦 <b>Produk:</b> {product.name}\n"
                    f"👤 <b>Pembeli:</b> {buyer_label}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                    f"💰 <b>Harga:</b> {price_str}\n"
                    f"🧾 <b>Invoice:</b> <code>{transaction.id}</code>\n"
                    f"📦 <b>Sisa stok:</b> {remaining}\n"
                    f"🕐 <b>Waktu:</b> {wib_now}"
                )
                await bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=admin_text,
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception(f"Gagal mengirim notifikasi pembelian #{transaction.id} ke admin")

        # Catat status transaksi PAID, arsip konten terkirim & masa aktif langganan
        await crud.mark_transaction_paid(
            session=session,
            transaction_id=transaction.id,
            delivered_content=delivered_text,
            expires_service_at=expires_service_at,
        )
        return True

    except Exception as e:
        logger.exception(f"Gagal memproses fulfillment order #{transaction.id}: {e}")
        return False
