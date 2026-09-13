"""
Aeternum PremiApp Bot - FastAPI Webhook Server
Menerima notifikasi pembayaran sukses dari Payment Gateway QRIS dengan verifikasi signature & IP whitelisting.
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

tripay = TripayGateway()
bot_instance: Bot | None = None


def set_bot_instance(bot: Bot) -> None:
    global bot_instance
    bot_instance = bot


def get_client_ip(request: Request) -> str:
    """Mendapatkan IP pengirim asli di belakang Cloudflare / Reverse Proxy."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    cf_connecting_ip = request.headers.get("CF-Connecting-IP")
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    return request.client.host if request.client else ""


@app.get("/")
async def health_check():
    return {"status": "ok", "app": "Aeternum PremiApp Webhook"}


@app.post("/webhook/payment")
async def handle_payment_webhook(
    request: Request,
    x_callback_signature: str | None = Header(None),
    x_callback_event: str | None = Header(None),
):
    """
    Endpoint Webhook Pembayaran QRIS dengan Security Hardening:
    1. IP Whitelisting (opsional jika dikonfigurasi)
    2. Verifikasi Signature HMAC SHA512
    3. Idempotensi & Atomic Concurrency Fulfillment
    """
    client_ip = get_client_ip(request)
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")

    # 1. IP WHITELISTING CHECK (JIKA DIKONFIGURASI)
    if settings.VERIFY_GATEWAY_IP and settings.GATEWAY_ALLOWED_IPS:
        allowed_list = [ip.strip() for ip in settings.GATEWAY_ALLOWED_IPS.split(",") if ip.strip()]
        if allowed_list and client_ip not in allowed_list:
            logger.warning(f"🚨 Ditolak akses Webhook dari IP tidak dikenal: {client_ip}")
            raise HTTPException(status_code=403, detail="Forbidden IP Address")

    # 2. SIGNATURE VERIFICATION
    if settings.GATEWAY_PRIVATE_KEY:
        if not x_callback_signature:
            logger.warning(f"🚨 Request webhook tanpa signature header dari IP: {client_ip}")
            raise HTTPException(status_code=401, detail="Missing Callback Signature")

        is_valid_sig = tripay.verify_webhook_signature(
            json_data=body_str, received_signature=x_callback_signature
        )
        if not is_valid_sig:
            logger.warning(f"🚨 Signature Webhook TIDAK VALID! IP: {client_ip}")
            raise HTTPException(status_code=403, detail="Invalid Callback Signature")

    try:
        data = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    logger.info(f"Webhook Valid Diterima ({client_ip}): {data}")

    merchant_ref = data.get("merchant_ref") or data.get("order_id") or data.get("reference")
    status = (data.get("status") or "").upper()

    if not merchant_ref:
        raise HTTPException(status_code=400, detail="Missing merchant_ref / order_id")

    if status not in ["PAID", "SUCCESS", "SETTLEMENT"]:
        logger.info(f"Status '{status}' diabaikan untuk order #{merchant_ref}")
        return JSONResponse(content={"success": True, "message": f"Status {status} ignored"})

    # 3. PROSES TRANSAKSI SECARA IDEMPOTEN
    async with async_session() as session:
        trx = await crud.get_transaction_by_id(session=session, transaction_id=merchant_ref)
        if not trx:
            logger.warning(f"Transaksi #{merchant_ref} tidak ditemukan!")
            return JSONResponse(content={"success": False, "message": "Transaction not found"}, status_code=404)

        if trx.status == "PAID":
            logger.info(f"Transaksi #{merchant_ref} sudah pernah diproses lunas (Idempotent response).")
            return JSONResponse(content={"success": True, "message": "Already processed"})

        formatted_amount = f"Rp {trx.amount:,.0f}".replace(",", ".")

        # ==========================================
        # TOP UP SALDO
        # ==========================================
        if trx.trx_type == "TOPUP":
            await crud.add_user_balance(session=session, user_id=trx.user_id, amount=float(trx.amount))
            await crud.mark_transaction_paid(session=session, transaction_id=trx.id, delivered_content=f"TOPUP:{trx.amount}")

            if bot_instance:
                try:
                    await bot_instance.send_message(
                        chat_id=trx.user_id,
                        text=(
                            f"🎉 <b>TOP UP SALDO BERHASIL!</b>\n\n"
                            f"🧾 <b>No. Invoice:</b> <code>{trx.id}</code>\n"
                            f"➕ <b>Nominal Masuk:</b> <code>+{formatted_amount}</code>\n\n"
                            f"Saldo Anda telah aktif dan siap digunakan untuk berbelanja secara instan di menu katalog!"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

                try:
                    admin_notif = (
                        f"💰 <b>NOTIFIKASI TOP UP SALDO MASUK!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🆔 <b>Invoice:</b> <code>#{trx.id}</code>\n"
                        f"💵 <b>Nominal:</b> <code>{formatted_amount}</code>\n"
                        f"👤 <b>User ID:</b> <code>{trx.user_id}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━"
                    )
                    await bot_instance.send_message(
                        chat_id=settings.ADMIN_ID,
                        text=admin_notif,
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            return JSONResponse(content={"success": True})

        # ==========================================
        # PEMBELIAN PRODUK DIGITAL
        # ==========================================
        product = await crud.get_product_by_id(session=session, product_id=trx.product_id)
        if not product:
            logger.error(f"Produk #{trx.product_id} tidak ditemukan!")
            return JSONResponse(content={"success": False, "message": "Product not found"}, status_code=404)

        if bot_instance:
            delivered = await deliver_purchased_product(
                bot=bot_instance,
                session=session,
                transaction=trx,
                product=product,
            )

            try:
                admin_notif_text = (
                    f"💰 <b>NOTIFIKASI PEMBELIAN MASUK!</b>\n"
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
