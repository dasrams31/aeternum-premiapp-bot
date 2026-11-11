"""
Manual checkout decision (Terima / Tolak / Abaikan) for incoming QRIS checkouts.

Admin taps a button on the PERCOBAAN CHECKOUT DM that arrives when an
invoice is created. The three decisions mean:

- Terima: the admin has verified the payment landed (mutasi / dashboard).
  The order is then fulfilled exactly like an automatic payment
  confirmation: purchases go through the same deliver_purchased_product
  path the poller uses (file / credentials / text sent to the buyer,
  referral commission, review prompt, success broadcast), top-ups credit
  the buyer balance the same way the poller does. The decision is stamped
  (manual_approved_at) BEFORE delivery so a second tap or a concurrent
  auto-confirm cannot deliver twice.
- Tolak: the invoice is marked REJECTED (manual_rejected_at). The buyer
  is told NOTHING, the poller never picks a REJECTED invoice up again,
  and the buyer-side status check answers with the same neutral
  "not detected yet" text so the rejection stays silent.
- Abaikan: only dismisses the card. The invoice is left exactly as it
  is, so a later real payment can still auto-confirm.

All timestamps written here are timezone-aware UTC. Never compare them
with naive datetimes (the old-server Postgres runs Asia/Shanghai and
naive utcnow() values land ~8h in the past there).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from database.models import Product, Transaction
from bot.services.broadcast import broadcast_transaction_success
from bot.services.fulfillment import deliver_purchased_product

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _wib(dt: datetime) -> str:
    return (dt.astimezone(timezone.utc) + timedelta(hours=7)).strftime(
        "%d %b %Y %H:%M WIB"
    )


def _rupiah(amount) -> str:
    return f"Rp {float(amount or 0):,.0f}".replace(",", ".")


async def process_checkout_decision(
    bot: Bot,
    session: AsyncSession,
    invoice_id: str,
    decision: str,
    *,
    broadcast: bool = True,
) -> dict:
    """Apply one admin decision to a checkout invoice.

    decision: "accept" | "reject" | "ignore".
    Returns {"ok": bool, "code": str, ...}. Never raises for a bad invoice
    state; only an unexpected DB/Telegram failure propagates.
    """
    # Row lock: two rapid taps on the same card serialize here, so the
    # second one always sees the first decision's marker.
    trx = (
        await session.execute(
            select(Transaction)
            .where(Transaction.id == invoice_id)
            .with_for_update()
        )
    ).scalars().first()
    if trx is None:
        return {"ok": False, "code": "not_found"}

    if decision == "ignore":
        logger.info("Checkout %s diabaikan admin.", invoice_id)
        return {"ok": True, "code": "ignored"}

    if getattr(trx, "manual_approved_at", None):
        return {"ok": False, "code": "already_accepted"}
    if getattr(trx, "manual_rejected_at", None) or trx.status == "REJECTED":
        return {"ok": False, "code": "already_rejected"}
    if trx.status == "PAID":
        return {"ok": False, "code": "already_paid"}

    if decision == "reject":
        trx.status = "REJECTED"
        trx.manual_rejected_at = _now_utc()
        await session.commit()
        logger.info("Checkout %s ditolak admin, pembeli tidak diberi info.", invoice_id)
        return {"ok": True, "code": "rejected"}

    if decision != "accept":
        return {"ok": False, "code": "bad_decision"}

    if trx.status != "PENDING":
        return {"ok": False, "code": "unknown_state"}
    if trx.expired_at is not None and trx.expired_at <= _now_utc():
        return {"ok": False, "code": "expired"}

    # Stamp the decision first, then fulfill. The stamp is what stops a
    # second tap or a concurrent auto-confirm from delivering twice.
    trx.manual_approved_at = _now_utc()
    await session.commit()

    if trx.trx_type == "TOPUP":
        await crud.add_user_balance(
            session=session, user_id=trx.user_id, amount=float(trx.amount)
        )
        await crud.mark_transaction_paid(
            session=session,
            transaction_id=trx.id,
            delivered_content=f"TOPUP:{trx.amount}",
        )
        try:
            await bot.send_message(
                chat_id=trx.user_id,
                text=(
                    f"🎉 <b>TOP UP SALDO BERHASIL!</b>\n\n"
                    f"🧾 <b>No. Invoice:</b> <code>{trx.id}</code>\n"
                    f"➕ <b>Nominal Masuk:</b> <code>+{_rupiah(trx.amount)}</code>\n\n"
                    f"Saldo Anda telah aktif dan siap digunakan untuk berbelanja produk digital secara instan!"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Gagal kirim pesan top-up manual #%s", trx.id)
        try:
            await bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=(
                    f"💰 <b>NOTIFIKASI TOP UP SALDO MANUAL!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 <b>Invoice:</b> <code>#{trx.id}</code>\n"
                    f"💵 <b>Nominal:</b> <code>{_rupiah(trx.amount)}</code>\n"
                    f"👤 <b>User ID:</b> <code>{trx.user_id}</code>\n"
                    f"🕐 <b>Diterima:</b> {_wib(trx.manual_approved_at)}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Gagal kirim notif top-up manual #%s ke admin", trx.id)
        logger.info("Top-up %s diterima manual, saldo masuk.", invoice_id)
        return {"ok": True, "code": "accepted_topup"}

    product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
    if product is None:
        return {"ok": False, "code": "product_missing"}

    delivered = await deliver_purchased_product(
        bot=bot, session=session, transaction=trx, product=product
    )
    if delivered and broadcast:
        buyer = await crud.get_user_by_id(session=session, user_id=trx.user_id)
        await broadcast_transaction_success(
            bot,
            product_name=product.name,
            amount=float(trx.amount),
            buyer_first_name=buyer.first_name if buyer else None,
        )
    try:
        await bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=(
                f"💰 <b>NOTIFIKASI PEMBELIAN MANUAL!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 <b>Invoice:</b> <code>#{trx.id}</code>\n"
                f"📦 <b>Produk:</b> {product.name}\n"
                f"💵 <b>Nominal:</b> <code>{_rupiah(trx.amount)}</code>\n"
                f"👤 <b>Pembeli ID:</b> <code>{trx.user_id}</code>\n"
                f"✅ <b>Status Pengiriman:</b> {'Terkirim Otomatis' if delivered else 'Perlu Pengecekan'}\n"
                f"🕐 <b>Diterima:</b> {_wib(trx.manual_approved_at)}\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Gagal kirim notif pembelian manual #%s ke admin", trx.id)
    logger.info(
        "Checkout %s diterima manual, delivered=%s.", invoice_id, delivered
    )
    if delivered:
        return {"ok": True, "code": "accepted"}
    return {"ok": True, "code": "delivered_failed"}
