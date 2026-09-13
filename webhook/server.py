"""
Aeternum PremiApp Bot - FastAPI Webhook Server & Telegram Mini App (TMA) API
Mendukung Webhook QRIS Payment Gateway dan Full-featured Web Store Interface.
"""

import csv
from datetime import datetime, timedelta
import io
import json
import logging
import os
from typing import Optional

from aiogram import Bot
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from config import settings
from database import crud
from database.connection import async_session
from database.models import Category, Product, PromoCode, Transaction, User
from bot.services.auth import validate_telegram_init_data
from bot.services.fulfillment import deliver_purchased_product
from webhook.gateway import BayarGGGateway, TripayGateway, get_payment_gateway

logger = logging.getLogger("aeternum_webhook")

app = FastAPI(title="Aeternum PremiApp Webhook & MiniApp Server")

# Enable CORS for Telegram WebApp
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files mount
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

tripay = TripayGateway()
bot_instance: Bot | None = None


def set_bot_instance(bot: Bot) -> None:
    global bot_instance
    bot_instance = bot


def get_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    cf_connecting_ip = request.headers.get("CF-Connecting-IP")
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    return request.client.host if request.client else ""


# ==============================================================================
# 1. TELEGRAM MINI APP (TMA) WEB INTERFACE
# ==============================================================================
@app.get("/", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
async def serve_miniapp():
    """Menampilkan antarmuka Telegram Mini App."""
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates",
        "index.html",
    )
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Aeternum PremiApp Web Store</h1>")


# ==============================================================================
# 2. MINIAPP JSON APIs
# ==============================================================================
@app.get("/api/catalog")
async def api_get_catalog():
    """Mengambil seluruh kategori & produk dengan live stock count."""
    async with async_session() as session:
        categories = await crud.get_categories(session=session, only_active=True)
        cat_list = [{"id": c.id, "name": c.name, "description": c.description} for c in categories]

        products_data = []
        stmt = (
            select(Product, Category.name)
            .outerjoin(Category, Product.category_id == Category.id)
            .where(Product.is_active.is_(True))
            .order_by(Product.id.asc())
        )
        res = await session.execute(stmt)
        for prod, cat_name in res.all():
            stock = 999
            if prod.product_type == "TEXT_STOCK":
                stock = await crud.count_available_stock(session=session, product_id=prod.id)

            products_data.append({
                "id": prod.id,
                "category_id": prod.category_id,
                "category_name": cat_name or "DIGITAL",
                "name": prod.name,
                "description": prod.description,
                "price": float(prod.price),
                "product_type": prod.product_type,
                "duration_days": prod.duration_days,
                "stock_count": stock,
            })

        return {"success": True, "categories": cat_list, "products": products_data}


@app.get("/api/user/profile")
async def api_get_user_profile(user_id: int = Query(...)):
    """Mengambil profil saldo & referral pengguna."""
    async with async_session() as session:
        user = await crud.get_user_by_id(session=session, user_id=user_id)
        if not user:
            user, _ = await crud.get_or_create_user(session=session, user_id=user_id)

        bot_username = "aeternum_premibot"
        if bot_instance:
            me = await bot_instance.get_me()
            bot_username = me.username or "aeternum_premibot"

        return {
            "success": True,
            "bot_username": bot_username,
            "user": {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "balance": float(user.balance or 0.0),
                "referral_balance": float(user.referral_balance or 0.0),
                "total_referrals": user.total_referrals or 0,
            },
        }


@app.get("/api/user/history")
async def api_get_user_history(user_id: int = Query(...)):
    """Mengambil riwayat transaksi belanja pengguna."""
    async with async_session() as session:
        trxs = await crud.get_user_transactions(session=session, user_id=user_id, limit=20)
        trx_list = []
        for t in trxs:
            prod_name = None
            if t.product_id:
                prod = await crud.get_product_by_id(session=session, product_id=t.product_id)
                prod_name = prod.name if prod else None

            trx_list.append({
                "id": t.id,
                "product_name": prod_name,
                "trx_type": t.trx_type,
                "amount": float(t.amount),
                "status": t.status,
                "delivered_content": t.delivered_content,
                "date": t.created_at.strftime("%d %b %Y, %H:%M WIB") if t.created_at else "-",
            })

        return {"success": True, "transactions": trx_list}


class PromoValidateRequest(BaseModel):
    code: str
    user_id: int
    price: float


@app.post("/api/promo/validate")
async def api_validate_promo(req: PromoValidateRequest):
    async with async_session() as session:
        is_valid, msg, discount_amount, promo = await crud.validate_and_apply_promo(
            session=session,
            code_str=req.code,
            user_id=req.user_id,
            original_price=req.price,
        )
        return {
            "success": is_valid,
            "message": msg,
            "discount_amount": discount_amount,
            "promo_code": promo.code if promo else None,
        }


class OrderCreateRequest(BaseModel):
    user_id: int
    product_id: Optional[int] = None
    amount: Optional[float] = None
    trx_type: str = "PURCHASE"
    payment_method: str = "QRIS"
    promo_code: Optional[str] = None
    discount_amount: float = 0.0


@app.post("/api/order/create")
async def api_create_order(
    req: OrderCreateRequest,
    x_telegram_init_data: Optional[str] = Header(None),
):
    # Jika bayar pakai saldo, verifikasi keaslian Telegram WebApp initData
    if req.payment_method == "BALANCE" and x_telegram_init_data:
        is_valid_auth, auth_user = validate_telegram_init_data(x_telegram_init_data)
        if is_valid_auth and auth_user and auth_user.get("id"):
            req.user_id = int(auth_user["id"])

    async with async_session() as session:
        user = await crud.get_user_by_id(session=session, user_id=req.user_id)
        if not user:
            user, _ = await crud.get_or_create_user(session=session, user_id=req.user_id)

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
        expired_at = datetime.utcnow() + timedelta(minutes=15)

        # ==========================================
        # 1. TOP UP SALDO
        # ==========================================
        if req.trx_type == "TOPUP":
            if not req.amount or req.amount < 5000:
                raise HTTPException(status_code=400, detail="Minimal top up Rp 5.000")

            invoice_id = f"TOPUP-{timestamp}-{user.id % 10000:04d}"
            mock_qris = f"00020101021226670016ID.CO.QRIS.WWW01189360000000000000000215{invoice_id}520458125303360540{int(req.amount)}5802ID5914AETERNUM TOPUP6007JAKARTA6304"

            await crud.create_transaction(
                session=session,
                invoice_id=invoice_id,
                user_id=user.id,
                amount=req.amount,
                trx_type="TOPUP",
                qris_string=mock_qris,
                expired_at=expired_at,
            )
            return {"success": True, "invoice_id": invoice_id}

        # ==========================================
        # 2. PEMBELIAN PRODUK DIGITAL
        # ==========================================
        if not req.product_id:
            raise HTTPException(status_code=400, detail="Product ID diperlukan")

        product = await crud.get_product_by_id(session=session, product_id=req.product_id)
        if not product or not product.is_active:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan atau nonaktif")

        final_price = float(product.price) - req.discount_amount

        # Opsi A: Bayar Pakai Saldo Internal
        if req.payment_method == "BALANCE":
            deducted = await crud.deduct_user_balance_atomic(
                session=session, user_id=user.id, amount=final_price
            )
            if not deducted:
                return {"success": False, "message": "Saldo tidak mencukupi"}

            invoice_id = f"BAL-{timestamp}-{user.id % 10000:04d}"
            trx = await crud.create_transaction(
                session=session,
                invoice_id=invoice_id,
                user_id=user.id,
                product_id=product.id,
                amount=final_price,
                original_amount=float(product.price),
                discount_amount=req.discount_amount,
                promo_code=req.promo_code,
                trx_type="PURCHASE",
                payment_method="BALANCE",
            )
            if bot_instance:
                await deliver_purchased_product(
                    bot=bot_instance, session=session, transaction=trx, product=product
                )
            return {"success": True, "invoice_id": invoice_id, "paid": True}

        # Opsi B: Bayar via QRIS
        invoice_id = f"AP-{timestamp}-{user.id % 10000:04d}"

        # Reserve stock if TEXT_STOCK
        if product.product_type == "TEXT_STOCK":
            reserved = await crud.reserve_stock_item_atomic(
                session=session,
                product_id=product.id,
                transaction_id=invoice_id,
                duration_minutes=15,
            )
            if not reserved:
                return {"success": False, "message": "Stok produk baru saja habis!"}

        mock_qris = f"00020101021226670016ID.CO.QRIS.WWW01189360000000000000000215{invoice_id}520458125303360540{int(final_price)}5802ID5914AETERNUM STORE6007JAKARTA6304"

        await crud.create_transaction(
            session=session,
            invoice_id=invoice_id,
            user_id=user.id,
            product_id=product.id,
            amount=final_price,
            original_amount=float(product.price),
            discount_amount=req.discount_amount,
            promo_code=req.promo_code,
            qris_string=mock_qris,
            expired_at=expired_at,
        )

        return {"success": True, "invoice_id": invoice_id, "paid": False}


# ==============================================================================
# 3. MINIAPP ADMIN APIS (KHUSUS @dasrams)
# ==============================================================================
@app.get("/api/admin/stats")
async def api_admin_stats(user_id: int = Query(...)):
    if user_id != settings.ADMIN_ID:
        raise HTTPException(status_code=403, detail="Unauthorized")

    async with async_session() as session:
        stmt_sales = select(
            func.count(Transaction.id), func.sum(Transaction.amount)
        ).where(Transaction.status == "PAID")
        res_sales = await session.execute(stmt_sales)
        total_trx, total_omset = res_sales.one()

        return {
            "success": True,
            "total_omset": float(total_omset or 0.0),
            "total_trx": total_trx or 0,
        }


@app.get("/api/admin/export-csv")
async def api_admin_export_csv(user_id: int = Query(...)):
    if user_id != settings.ADMIN_ID:
        raise HTTPException(status_code=403, detail="Unauthorized")

    async with async_session() as session:
        records = await crud.get_all_paid_transactions_for_export(session=session, limit=2000)

        output = io.StringIO()
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")

        writer.writerow([
            "No. Invoice",
            "Waktu Transaksi",
            "Nama Produk",
            "Tipe Transaksi",
            "Metode Pembayaran",
            "Harga Normal (Rp)",
            "Potongan Diskon (Rp)",
            "Kode Promo",
            "Total Bersih (Rp)",
            "Telegram User ID",
            "Username Pembeli",
            "Nama Pembeli",
        ])

        for trx, prod, user in records:
            writer.writerow([
                trx.id,
                trx.paid_at.strftime("%Y-%m-%d %H:%M:%S") if trx.paid_at else trx.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                prod.name if prod else ("Top Up Saldo" if trx.trx_type == "TOPUP" else "-"),
                trx.trx_type,
                trx.payment_method,
                f"{trx.original_amount:.2f}",
                f"{trx.discount_amount:.2f}",
                trx.promo_code or "-",
                f"{trx.amount:.2f}",
                user.id,
                f"@{user.username}" if user.username else "-",
                user.first_name or "-",
            ])

        csv_data = output.getvalue().encode("utf-8")
        filename = f"Laporan_Penjualan_Aeternum_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


# ==============================================================================
# 4. PAYMENT GATEWAY WEBHOOK LISTENER
# ==============================================================================
@app.post("/webhook/payment")
async def handle_payment_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(None),
    x_webhook_timestamp: str | None = Header(None),
    x_invoice_id: str | None = Header(None),
    x_callback_signature: str | None = Header(None),
):
    client_ip = get_client_ip(request)
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")

    try:
        data = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")

    logger.info(f"Webhook Callback Diterima ({client_ip}): {data}")

    # Ekstrak data invoice & status
    merchant_ref = (
        data.get("merchant_ref")
        or data.get("invoice_id")
        or x_invoice_id
        or data.get("order_id")
    )
    status = (data.get("status") or "").upper()
    callback_time = data.get("timestamp") or x_webhook_timestamp

    # Anti-Replay Check
    if callback_time:
        try:
            req_ts = float(callback_time)
            now_ts = datetime.utcnow().timestamp()
            if abs(now_ts - req_ts) > 600:
                logger.warning(f"🚨 [ANTI-REPLAY] Webhook expired! Selisih: {abs(now_ts - req_ts)}s")
        except (ValueError, TypeError):
            pass

    if not merchant_ref:
        raise HTTPException(status_code=400, detail="Missing invoice_id / merchant_ref")

    # Verifikasi Signature Gateway jika diatur
    gateway = get_payment_gateway()
    received_sig = x_webhook_signature or data.get("signature") or x_callback_signature
    if settings.GATEWAY_PRIVATE_KEY and received_sig:
        final_amount = data.get("final_amount") or data.get("amount") or 0
        if isinstance(gateway, BayarGGGateway):
            is_valid = gateway.verify_webhook_signature(
                invoice_id=merchant_ref,
                status=data.get("status", "paid"),
                final_amount=final_amount,
                timestamp=callback_time or "",
                received_signature=received_sig,
            )
        else:
            is_valid = gateway.verify_webhook_signature(
                json_data=body_str,
                received_signature=received_sig,
            )
        if not is_valid:
            logger.warning(f"🚨 Signature Webhook TIDAK VALID dari IP: {client_ip}")

    if status not in ["PAID", "SUCCESS", "SETTLEMENT"]:
        logger.info(f"Status '{status}' diabaikan untuk order #{merchant_ref}")
        return JSONResponse(content={"success": True, "message": f"Status {status} ignored"})

    async with async_session() as session:
        # Cari transaksi berdasarkan ID atau Gateway Reference
        trx = await crud.get_transaction_by_id(session=session, transaction_id=merchant_ref)
        if not trx:
            stmt = select(Transaction).where(Transaction.gateway_reference == merchant_ref)
            trx = (await session.execute(stmt)).scalar_one_or_none()

        if not trx:
            logger.warning(f"Transaksi #{merchant_ref} tidak ditemukan di database!")
            return JSONResponse(content={"success": False, "message": "Transaction not found"}, status_code=404)

        if trx.status == "PAID":
            logger.info(f"Transaksi #{merchant_ref} sudah pernah diproses lunas.")
            return JSONResponse(content={"success": True, "message": "Already processed"})

        formatted_amount = f"Rp {trx.amount:,.0f}".replace(",", ".")

        # Top Up Saldo
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
                            f"Saldo Anda telah aktif dan siap digunakan untuk berbelanja secara instan!"
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

        # Pembelian Produk
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
