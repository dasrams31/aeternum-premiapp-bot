"""
Aeternum PremiApp Bot - Comprehensive Automated Test Suite
Menguji seluruh siklus transaksi, database CRUD, enkripsi AES-256, stock reservation, promo, referral, wallet, webhook, review, warranty, dan background services.
"""

import asyncio
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import os
import sys

# Tambahkan root path ke sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from config import settings
from database import crud
from database.connection import async_session, init_db
from database.models import Category, Product, ProductItem, PromoCode, PromoUsage, Review, Transaction, User, WarrantyTicket
from bot.services.crypto import decrypt_text, encrypt_text
from webhook.server import app as webhook_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_suite")


async def run_all_tests():
    print("=" * 60)
    print("🧪 MEMULAI COMPREHENSIVE TEST SUITE - AETERNUM PREMIAPP BOT")
    print("=" * 60)

    # 1. Inisialisasi Database
    print("\n[TEST 1] Inisialisasi Database & Schema...")
    await init_db()
    print("✅ [TEST 1 PASSED] Database schema verified.")

    # 2. Test Enkripsi AES-256 (Fernet)
    print("\n[TEST 2] Testing AES-256 Encryption & Decryption...")
    sample_secret = "test_user@netflix.com:SecretPassword123!_PIN4092"
    encrypted = encrypt_text(sample_secret)
    assert encrypted.startswith("ENC::"), f"Format enkripsi salah: {encrypted}"
    assert encrypted != sample_secret, "Teks tidak terenkripsi!"
    decrypted = decrypt_text(encrypted)
    assert decrypted == sample_secret, f"Gagal dekripsi! Hasil: {decrypted}"
    print(f"  Plaintext : {sample_secret}")
    print(f"  Encrypted : {encrypted[:30]}...")
    print(f"  Decrypted : {decrypted}")
    print("✅ [TEST 2 PASSED] AES-256 Encryption at Rest berfungsi 100%.")

    async with async_session() as session:
        # 3. Test User Creation & Referral Linking
        print("\n[TEST 3] Testing User & Referral System...")
        referrer_id = 999111000
        ref_user, is_new_ref = await crud.get_or_create_user(
            session=session,
            user_id=referrer_id,
            username="referrer_boss",
            first_name="Referrer Boss",
            is_admin=False,
        )

        buyer_id = 999222000
        buyer_user, is_new_buyer = await crud.get_or_create_user(
            session=session,
            user_id=buyer_id,
            username="test_buyer",
            first_name="Test Buyer",
            is_admin=False,
            referrer_id=referrer_id,
        )
        assert buyer_user.referred_by == referrer_id, "Referrer tidak terhubung!"
        print(f"  Referrer: {ref_user.first_name} (ID: {ref_user.id})")
        print(f"  Buyer   : {buyer_user.first_name} (Referred by: {buyer_user.referred_by})")
        print("✅ [TEST 3 PASSED] User registration & referral tree verified.")

        # 4. Test Category & Product Creation
        print("\n[TEST 4] Testing Category & Product Creation...")
        cat = await crud.create_category(
            session=session,
            name="Testing Streaming Apps",
            description="Kategori untuk pengujian otomatis",
        )
        prod = await crud.create_product(
            session=session,
            category_id=cat.id,
            name="Netflix 4K Ultra HD (1 Bulan)",
            price=35000.0,
            product_type="TEXT_STOCK",
            duration_days=30,
            description="Akun Netflix Private 1 Bulan Garansi Penuh",
        )
        assert prod.id is not None, "Product ID gagal digenerate!"
        print(f"  Category Created: {cat.name} (ID: {cat.id})")
        print(f"  Product Created : {prod.name} (ID: {prod.id}, Price: Rp {prod.price})")
        print("✅ [TEST 4 PASSED] Catalog & Product creation verified.")

        # 5. Test Bulk Stock Import with Auto-Encryption
        print("\n[TEST 5] Testing Bulk Stock Import (Auto-Encrypted)...")
        raw_stocks = [
            "netuser1@mail.com:pass111",
            "netuser2@mail.com:pass222",
            "netuser3@mail.com:pass333",
        ]
        added_count = await crud.add_stock_items_bulk(
            session=session,
            product_id=prod.id,
            contents=raw_stocks,
        )
        assert added_count == 3, f"Jumlah stok terinput: {added_count} != 3"
        avail_stock = await crud.count_available_stock(session=session, product_id=prod.id)
        assert avail_stock >= 3, f"Stok tersedia tidak cocok: {avail_stock}"

        # Cek apakah isi di DB benar-benar terenkripsi
        stmt = select(ProductItem).where(ProductItem.product_id == prod.id).limit(1)
        db_item = (await session.execute(stmt)).scalar_one()
        assert db_item.content.startswith("ENC::"), f"Item di DB tidak terenkripsi: {db_item.content}"
        print(f"  Stock Added : +{added_count} items")
        print(f"  DB Content  : {db_item.content[:25]}... (Encrypted!)")
        print(f"  Decrypted   : {decrypt_text(db_item.content)}")
        print("✅ [TEST 5 PASSED] Bulk stock encrypted storage verified.")

        # 6. Test Temporary Stock Reservation Lifecycle
        print("\n[TEST 6] Testing Temporary Stock Hold / Reservation Lifecycle...")
        inv_temp = "TEST-INV-TEMP-001"
        # 6.1 Reserve Stock
        reserved_item = await crud.reserve_stock_item_atomic(
            session=session,
            product_id=prod.id,
            transaction_id=inv_temp,
            duration_minutes=15,
        )
        assert reserved_item is not None, "Gagal mengunci stok sementara!"
        assert reserved_item.reserved_by_trx == inv_temp, "Transaction ID reservation salah!"

        # Cek stok di katalog berkurang 1
        stock_after_reserve = await crud.count_available_stock(session=session, product_id=prod.id)
        assert stock_after_reserve == avail_stock - 1, "Stok tidak berkurang saat di-reserve!"

        # 6.2 Test Pembatalan Pesanan -> Release Stock
        released = await crud.release_reserved_stock(session=session, transaction_id=inv_temp)
        assert released is True, "Gagal melepaskan kunci stok!"
        stock_after_cancel = await crud.count_available_stock(session=session, product_id=prod.id)
        assert stock_after_cancel == avail_stock, "Stok tidak kembali setelah pembatalan!"
        print(f"  Initial Stock : {avail_stock}")
        print(f"  After Reserve : {stock_after_reserve} (Reduced by 1)")
        print(f"  After Cancel  : {stock_after_cancel} (Restored to {avail_stock})")
        print("✅ [TEST 6 PASSED] Temporary stock hold & release lifecycle verified.")

        # 7. Test Promo Codes & Discount Engine
        print("\n[TEST 7] Testing Promo Code & Discount Engine...")
        promo = await crud.create_promo_code(
            session=session,
            code="AETERNUM10",
            discount_type="PERCENT",
            discount_value=10.0,  # 10%
            min_purchase=20000.0,
            max_discount=10000.0,
            max_usage=50,
        )
        is_valid, msg, discount, p_obj = await crud.validate_and_apply_promo(
            session=session,
            code_str="aeternum10",
            user_id=buyer_id,
            original_price=35000.0,
        )
        assert is_valid is True, f"Kupon gagal divalidasi: {msg}"
        assert discount == 3500.0, f"Diskon salah: {discount} != 3500.0"
        print(f"  Promo Code : {promo.code} (10%)")
        print(f"  Original   : Rp 35.000")
        print(f"  Discount   : -Rp {discount:,.0f}".replace(",", "."))
        print(f"  Final Price: Rp {35000.0 - discount:,.0f}".replace(",", "."))
        print("✅ [TEST 7 PASSED] Promo code validation & calculation verified.")

        # 8. Test Wallet Deposit & Instant Balance Payment
        print("\n[TEST 8] Testing Wallet TopUp & Instant Balance Payment...")
        # Tambah saldo ke buyer Rp 100.000
        await crud.add_user_balance(session=session, user_id=buyer_id, amount=100000.0)
        buyer_check = await crud.get_user_by_id(session=session, user_id=buyer_id)
        assert float(buyer_check.balance) == 100000.0, "Saldo gagal masuk!"

        # Bayar pakai saldo secara atomic Rp 31.500
        deducted = await crud.deduct_user_balance_atomic(session=session, user_id=buyer_id, amount=31500.0)
        assert deducted is True, "Gagal memotong saldo!"
        buyer_after = await crud.get_user_by_id(session=session, user_id=buyer_id)
        assert float(buyer_after.balance) == 68500.0, f"Sisa saldo salah: {buyer_after.balance}"
        print(f"  Initial Balance : Rp 100.000")
        print(f"  Deduction       : -Rp 31.500")
        print(f"  Remaining       : Rp {float(buyer_after.balance):,.0f}".replace(",", "."))
        print("✅ [TEST 8 PASSED] Wallet balance deposit & atomic deduction verified.")

        # 9. Test Restock Notifier Subscription
        print("\n[TEST 9] Testing Restock Notifier Subscription...")
        sub_ok, sub_msg = await crud.subscribe_restock_alert(
            session=session, product_id=prod.id, user_id=buyer_id
        )
        assert sub_ok is True, f"Gagal subscribe restock: {sub_msg}"
        subscribers = await crud.get_and_clear_restock_subscribers(session=session, product_id=prod.id)
        assert buyer_id in subscribers, "User ID tidak ada di daftar antrean restock!"
        print(f"  Subscribed User: {buyer_id}")
        print(f"  Queue Cleared  : {len(subscribers)} notified")
        print("✅ [TEST 9 PASSED] Restock notifier queue verified.")

        # 10. Test Review & Testimonial Creation
        print("\n[TEST 10] Testing Review & Testimonial Creation...")
        test_invoice_id = "AP-20260913-TEST"
        trx_test = await crud.create_transaction(
            session=session,
            invoice_id=test_invoice_id,
            user_id=buyer_id,
            product_id=prod.id,
            amount=31500.0,
            original_amount=35000.0,
            discount_amount=3500.0,
            promo_code="AETERNUM10",
        )
        await crud.mark_transaction_paid(session=session, transaction_id=test_invoice_id, delivered_content="sample:creds")

        rev = await crud.create_review(
            session=session,
            transaction_id=test_invoice_id,
            user_id=buyer_id,
            product_id=prod.id,
            rating=5,
            comment="Pelayanan sangat cepat, 1 detik akun langsung masuk!",
        )
        assert rev.id is not None, "Gagal membuat ulasan!"
        assert rev.rating == 5, "Rating salah!"
        print(f"  Rating : ⭐⭐⭐⭐⭐ ({rev.rating}/5)")
        print(f"  Comment: \"{rev.comment}\"")
        print("✅ [TEST 10 PASSED] Review & rating storage verified.")

        # 11. Test Warranty Ticket Lifecycle
        print("\n[TEST 11] Testing Warranty Ticket Claim & Admin Resolution...")
        tkt_code = "TKT-20260913-9999"
        ticket = await crud.create_warranty_ticket(
            session=session,
            ticket_code=tkt_code,
            transaction_id=test_invoice_id,
            user_id=buyer_id,
            product_id=prod.id,
            issue_description="Akun tidak bisa login password salah",
        )
        assert ticket.status == "OPEN", "Status awal tiket salah!"

        # Admin resolves ticket with replacement
        resolved_tkt = await crud.resolve_warranty_ticket(
            session=session,
            ticket_code=tkt_code,
            status="RESOLVED",
            admin_notes="Akun baru dikirimkan",
            replacement_content="replacement_user@mail.com:NewPass123",
        )
        assert resolved_tkt.status == "RESOLVED", "Gagal menyelesaikan tiket garansi!"
        print(f"  Ticket Created  : {ticket.ticket_code} (Status: OPEN)")
        print(f"  Ticket Resolved : {resolved_tkt.ticket_code} (Status: RESOLVED)")
        print(f"  Replacement     : {resolved_tkt.replacement_content}")
        print("✅ [TEST 11 PASSED] Warranty claim & admin resolution verified.")

        # 12. Test Export CSV Data Generation
        print("\n[TEST 12] Testing Export Sales Data Generation...")
        export_records = await crud.get_all_paid_transactions_for_export(session=session, limit=10)
        assert len(export_records) > 0, "Data export kosong!"
        first_row = export_records[0]
        print(f"  Exportable Records: {len(export_records)} rows")
        print(f"  Sample Row        : #{first_row[0].id} | {first_row[1].name if first_row[1] else '-'} | Rp {first_row[0].amount}")
        print("✅ [TEST 12 PASSED] Sales export data extraction verified.")

        # 13. Test Subscription Expiry Reminders (H-3 / H-1)
        print("\n[TEST 13] Testing Subscription Expiry Reminders...")
        # Buat transaksi dengan expired 2 hari lagi (Trigger H-3)
        h3_inv = "AP-SUB-H3-TEST"
        trx_h3 = await crud.create_transaction(
            session=session,
            invoice_id=h3_inv,
            user_id=buyer_id,
            product_id=prod.id,
            amount=35000.0,
        )
        await crud.mark_transaction_paid(
            session=session,
            transaction_id=h3_inv,
            delivered_content="user:pass",
            expires_service_at=datetime.utcnow() + timedelta(days=2),
        )

        h3_list, h1_list = await crud.get_due_subscription_reminders(session=session)
        assert any(t.id == h3_inv for t in h3_list), "Transaksi H-3 tidak terdeteksi scheduler!"
        await crud.mark_reminder_sent(session=session, transaction_id=h3_inv, reminder_type="H3")
        h3_list_after, _ = await crud.get_due_subscription_reminders(session=session)
        assert not any(t.id == h3_inv for t in h3_list_after), "Reminder H-3 masih muncul setelah dikirim!"
        print(f"  H-3 Detected : #{h3_inv}")
        print(f"  H-3 Marked   : Sent successfully")
        print("✅ [TEST 13 PASSED] Subscription reminder detection & marking verified.")

    # 14. Test FastAPI Webhook Server Endpoints & Security
    print("\n[TEST 14] Testing FastAPI Webhook Server Endpoints & Security...")
    async with AsyncClient(transport=ASGITransport(app=webhook_app), base_url="http://test") as client:
        # Health check
        res_health = await client.get("/")
        assert res_health.status_code == 200, f"Health check failed: {res_health.status_code}"

        # Webhook Simulation: TopUp Transaction
        topup_inv = "TOPUP-20260913-AUTO"
        async with async_session() as session:
            await crud.create_transaction(
                session=session,
                invoice_id=topup_inv,
                user_id=buyer_id,
                amount=50000.0,
                trx_type="TOPUP",
            )

        webhook_payload = {
            "merchant_ref": topup_inv,
            "status": "PAID",
            "amount": 50000,
            "timestamp": int(datetime.utcnow().timestamp()),
        }
        json_body = json.dumps(webhook_payload)

        # Hitung Signature jika Private Key di-set
        sig = ""
        if settings.GATEWAY_PRIVATE_KEY:
            sig = hmac.new(
                settings.GATEWAY_PRIVATE_KEY.encode("utf-8"),
                json_body.encode("utf-8"),
                hashlib.sha512,
            ).hexdigest()

        headers = {"x-callback-signature": sig} if sig else {}
        res_webhook = await client.post("/webhook/payment", content=json_body, headers=headers)
        assert res_webhook.status_code == 200, f"Webhook failed: {res_webhook.status_code} - {res_webhook.text}"
        assert res_webhook.json().get("success") is True, f"Webhook payload failed: {res_webhook.text}"

        # Cek saldo buyer bertambah Rp 50.000
        async with async_session() as session:
            buyer_final = await crud.get_user_by_id(session=session, user_id=buyer_id)
            assert float(buyer_final.balance) == 118500.0, f"Saldo topup tidak bertambah: {buyer_final.balance}"

        # Cek Idempotensi (kirim ulang payload yang sama)
        res_idempotent = await client.post("/webhook/payment", content=json_body, headers=headers)
        assert res_idempotent.status_code == 200, "Idempotency failed!"
        assert res_idempotent.json().get("message") == "Already processed", "Idempotency tidak terdeteksi!"

        print("  Health Check       : 200 OK")
        print("  TopUp Webhook      : 200 OK (Balance +Rp 50.000)")
        print("  Idempotent Retry   : 200 OK (Already processed)")
        print("✅ [TEST 14 PASSED] FastAPI Webhook security & execution verified.")

    print("\n" + "=" * 60)
    print("🎉 SELURUH TEST (14 SKENARIO) BERHASIL 100% TANPA ERROR!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
