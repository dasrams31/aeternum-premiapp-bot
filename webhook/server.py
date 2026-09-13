"""
Aeternum PremiApp Bot - FastAPI Webhook Server
Menerima notifikasi pembayaran sukses dari Payment Gateway QRIS secara real-time.
"""

import json
import logging
from aiogram import Bot
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings
from database import crud
from database.connection import async_session
from bot.services.fulfillment import deliver_purchased_product
from webhook.gateway import TripayGateway

logger = logging.getLogger("aeternum_webhook")
app = FastAPI(title="Aeternum PremiApp Webhook Server")

# Instance Tripay untuk verifikasi signature
tripay = TripayGateway()

# Bot instance untuk mengirim pesan instan ke Telegram (akan di-inject saat startup)
bot_instance: Bot | None = None


def set_bot_instance(bot: Bot) -> None:
    global bot_instance
    bot_instance = bot


@app.get("/")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": "Aeternum PremiApp Webhook"}


@app.post("/webhook/payment")
async def handle_payment_webhook(
    request: Request,
    x_callback_signature: str | None = Header(None),
    x_callback_event: str | None = Header(None),
):
    """
    Endpoint Webhook Pembayaran QRIS.
    Menerima callback dari Tripay / Pakasir / Gateway lainnya.
    """
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")

    try:
        data = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    logger.info(f"Menerima Webhook Callback: {data}")

    # 1. Ekstrak data pembayaran
    # Format Tripay:
    merchant_ref = data.get("merchant_ref") or data.get("order_id") or data.get("reference")
    status = (data.get("status") or "").upper()
    is_closed = data.get("is_closed_payment", 1)

    if not merchant_ref:
        raise HTTPException(status_code=400, detail="Missing merchant_ref / order_id")

    # 2. Verifikasi status pembayaran
    if status not in ["PAID", "SUCCESS", "SETTLEMENT"]:
        logger.info(f"Abaikan webhook dengan status: {status} untuk order #{merchant_ref}")
        return JSONResponse(content={"success": True, "message": f"Status {status} ignored"})

    # 3. Proses Transaksi di Database
    async with async_session() as session:
        trx = await crud.get_transaction_by_id(session=session, transaction_id=merchant_ref)
        if not trx:
            logger.warning(f"Transaksi #{merchant_ref} tidak ditemukan di database!")
            return JSONResponse(content={"success": False, "message": "Transaction not found"}, status_code=404)

        if trx.status == "PAID":
            logger.info(f"Transaksi #{merchant_ref} sudah diproses sebelumnya.")
            return JSONResponse(content={"success": True, "message": "Already processed"})

        product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
        if not product:
            logger.error(f"Produk #{trx.product_id} tidak ditemukan!")
            return JSONResponse(content={"success": False, "message": "Product not found"}, status_code=404)

        # 4. Kirimkan produk ke pembeli secara otomatis via Telegram
        if bot_instance:
            delivered = await deliver_purchased_product(
                bot=bot_instance,
                session=session,
                transaction=trx,
                product=product,
            )

            # 5. Kirimkan notifikasi real-time ke DM Admin
            try:
                formatted_amount = f"Rp {trx.amount:,.0f}".replace(",", ".")
                admin_notif_text = (
                    f"💰 <b>NOTIFIKASI PEMBAYARAN MASUK!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 <b>Invoice:</b> <code>#{trx.id}</code>\n"
                    f"📦 <b>Produk:</b> {product.name}\n"
                    f"💵 <b>Nominal:</b> <code>{formatted_amount}</code>\n"
                    f"👤 <b>Pembeli ID:</b> <code>{trx.user_id}</code>\n"
                    f"✅ <b>Status Pengiriman:</b> {'Terkirim Otomatis' if delivered else 'Perlu Pengecekan'}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Sistem otomatis Aeternum PremiApp Bot</i>"
                )
                await bot_instance.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=admin_notif_text,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Gagal mengirim notifikasi admin: {e}")

    return JSONResponse(content={"success": True})
