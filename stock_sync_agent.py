#!/usr/bin/env python3
"""Stock sync agent (old server): applies store-origin stock events to the bot DB.

Run from the bot repo root with the bot venv:
  PYTHONPATH=/home/ubuntu/aeternum-premiapp-bot venv/bin/python stock_sync_agent.py <cmd>

Subcommands (JSON in/out):
  fetch-events --product-ids 1,2,3   unprocessed bot outbox events for these products
  apply-events                       read [{event_id, product_id, kind, delta, target}] on stdin
  mark-processed                     read [event_id, ...] on stdin
  counts --product-ids 1,2,3         available (unsold + unreserved) counts per product
  stock-out --product-id N          broadcast STOK HABIS to the Aeternum channel
  price-change --product-id N --old-price X --new-price Y [--name S]
                                     broadcast HARGA BERUBAH (channel + DM
                                     semua user + DM admin), dipakai price-watch
                                     watcher saat harga berubah
  prices                             dump produk aktif (id, nama, harga) JSON
  restock --product-id N --added A --total T
                                     broadcast STOK DITAMBAH (channel + DM semua
                                     user + notifikasi subscriber), dipakai sync
                                     worker saat event restock diterapkan
  store-sale                           broadcast a store sale to the Aeternum
                                     channel; read {product, amount, buyer?} on stdin
  recent-sales                         paid bot purchases (30 days) for the
                                     store social-proof feed
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime

sys.path.insert(0, "/home/ubuntu/aeternum-premiapp-bot")

from sqlalchemy import or_, select, text, update

from database import crud
from database.connection import async_session
from database.models import Product, ProductItem, StockSyncApplied, StockSyncEvent
from bot.services.crypto import encrypt_text

DEFAULT_ITEM_TEXT = "Silakan hubungi admin untuk konfirmasi pembelian. Akun akan dikirim setelah admin mengonfirmasi."


def _available_stmt(product_id: int):
    now = datetime.utcnow()
    return (
        select(ProductItem)
        .where(ProductItem.product_id == product_id)
        .where(ProductItem.is_sold.is_(False))
        .where(
            or_(
                ProductItem.reserved_until.is_(None),
                ProductItem.reserved_until < now,
            )
        )
    )


async def _refresh_out_of_stock(session, product_id: int) -> int:
    n = await crud.count_available_stock(session=session, product_id=product_id)
    await session.execute(
        update(Product).where(Product.id == product_id).values(is_out_of_stock=(n == 0))
    )
    return n


async def _apply_one(session, ev: dict) -> dict:
    event_id = ev["event_id"]
    product_id = int(ev["product_id"])
    kind = ev["kind"]
    now = datetime.utcnow()

    done = await session.execute(
        select(StockSyncApplied).where(StockSyncApplied.event_id == event_id)
    )
    if done.scalar_one_or_none():
        return {"event_id": event_id, "status": "already"}

    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if not product or product.product_type != "TEXT_STOCK":
        return {"event_id": event_id, "status": "error", "detail": "product not TEXT_STOCK"}

    if kind == "delta":
        delta = int(ev.get("delta") or 0)
        if delta < 0:
            for _ in range(-delta):
                pick = await session.execute(
                    _available_stmt(product_id)
                    .order_by(ProductItem.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                item = pick.scalar_one_or_none()
                if not item:
                    session.add(StockSyncApplied(event_id=event_id))
                    await session.commit()
                    return {
                        "event_id": event_id,
                        "status": "no-item-drift",
                        "detail": "no available item to consume",
                    }
                item.is_sold = True
                item.sold_at = now
                item.transaction_id = f"STORE-SYNC-{event_id}"
                item.reserved_by_trx = None
                item.reserved_until = None
        elif delta > 0:
            for _ in range(delta):
                pick = await session.execute(
                    select(ProductItem)
                    .where(ProductItem.product_id == product_id)
                    .where(ProductItem.is_sold.is_(True))
                    .where(ProductItem.transaction_id.like("STORE-SYNC-%"))
                    .order_by(ProductItem.sold_at.desc())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                item = pick.scalar_one_or_none()
                if not item:
                    session.add(StockSyncApplied(event_id=event_id))
                    await session.commit()
                    return {
                        "event_id": event_id,
                        "status": "no-item-drift",
                        "detail": "no STORE-SYNC item to release",
                    }
                item.is_sold = False
                item.sold_at = None
                item.transaction_id = None
    elif kind == "set":
        target = int(ev.get("target") or 0)
        avail = await crud.count_available_stock(session=session, product_id=product_id)
        if avail < target:
            probe = await session.execute(
                select(ProductItem.content)
                .where(ProductItem.product_id == product_id)
                .limit(1)
            )
            content = probe.scalar_one_or_none() or encrypt_text(DEFAULT_ITEM_TEXT)
            for _ in range(target - avail):
                session.add(ProductItem(product_id=product_id, content=content))
            await session.flush()
        elif avail > target:
            excess = avail - target
            pick = await session.execute(
                _available_stmt(product_id)
                .order_by(ProductItem.id)
                .with_for_update(skip_locked=True)
                .limit(excess)
            )
            for item in pick.scalars().all():
                item.is_sold = True
                item.sold_at = now
                item.transaction_id = f"STORE-SYNC-SET-{event_id}"
                item.reserved_by_trx = None
                item.reserved_until = None
    else:
        return {"event_id": event_id, "status": "error", "detail": f"unknown kind {kind}"}

    await _refresh_out_of_stock(session, product_id)
    session.add(StockSyncApplied(event_id=event_id))
    await session.commit()
    return {"event_id": event_id, "status": "applied"}


async def cmd_fetch_events(product_ids):
    async with async_session() as s:
        stmt = (
            select(StockSyncEvent)
            .where(StockSyncEvent.processed_at.is_(None))
            .where(StockSyncEvent.product_id.in_(product_ids))
            .order_by(StockSyncEvent.id)
        )
        rows = (await s.execute(stmt)).scalars().all()
        out = [
            {
                "id": r.id,
                "event_id": r.event_id,
                "product_id": r.product_id,
                "kind": r.kind,
                "delta": r.delta,
                "target": r.target,
                "ref": r.ref,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        print(json.dumps(out))


async def cmd_apply_events(events):
    results = []
    for ev in events:
        try:
            async with async_session() as s:
                results.append(await _apply_one(s, ev))
        except Exception as e:  # noqa: BLE001 - report, do not crash the batch
            results.append(
                {"event_id": ev.get("event_id"), "status": "error", "detail": str(e)}
            )
    print(json.dumps(results))


async def cmd_mark_processed(event_ids):
    async with async_session() as s:
        if event_ids:
            await s.execute(
                update(StockSyncEvent)
                .where(StockSyncEvent.event_id.in_(event_ids))
                .values(processed_at=datetime.utcnow())
            )
            await s.commit()
        print(json.dumps({"marked": len(event_ids)}))


async def cmd_counts(product_ids):
    async with async_session() as s:
        out = {}
        for pid in product_ids:
            out[str(pid)] = await crud.count_available_stock(session=s, product_id=pid)
        print(json.dumps(out))


async def cmd_notify_batch(messages):
    """Send store notifications / admin chats to the admin via PremiBot DM."""
    from aiogram import Bot

    from config import settings

    bot = Bot(token=settings.BOT_TOKEN)
    results = []
    try:
        for m in messages:
            try:
                sent = await bot.send_message(
                    settings.ADMIN_ID, m["text"], parse_mode="HTML"
                )
                results.append(
                    {"key": m["key"], "ok": True, "message_id": sent.message_id}
                )
            except Exception as e:  # noqa: BLE001 - report per message, do not crash the batch
                results.append({"key": m["key"], "ok": False, "error": str(e)})
    finally:
        await bot.session.close()
    print(json.dumps(results))


async def cmd_stock_out(product_id: int):
    """Broadcast STOK HABIS realtime ke channel Aeternum.

    Dipanggil sync worker saat stok pool (store + bot) suatu produk
    menyentuh 0. Set flag is_out_of_stock=true dulu supaya updater
    08:00 tidak melihat flip dan tidak broadcast kedua kali.
    Keluar 1 bila produk tidak ditemukan, bukan TEXT_STOCK, atau
    broadcast gagal (worker mencatat ERROR).
    """
    from aiogram import Bot

    from bot.services.broadcast import broadcast_stock_out
    from config import settings

    async with async_session() as s:
        product = await crud.get_product_by_id(session=s, product_id=product_id)
        if not product:
            print(json.dumps({"product_id": product_id, "error": "not found"}))
            raise SystemExit(1)
        if product.product_type != "TEXT_STOCK":
            print(json.dumps({"product_id": product_id, "error": "not TEXT_STOCK"}))
            raise SystemExit(1)
        product.is_out_of_stock = True
        await s.commit()
        bot = Bot(token=settings.BOT_TOKEN)
        try:
            ok = await broadcast_stock_out(bot, s, product)
        finally:
            await bot.session.close()
    print(
        json.dumps(
            {
                "product_id": product_id,
                "name": product.name,
                "broadcasted": bool(ok),
            }
        )
    )
    if not ok:
        raise SystemExit(1)


async def cmd_restock(product_id: int, added: int, total: int):
    """Broadcast STOK DITAMBAH realtime ke channel Aeternum + DM semua user.

    Dipanggil sync worker saat sebuah event restock (tambah stok) diterapkan
    ke produk ini. Memakai broadcast_restock_event yang sama dengan alur
    admin tambah stok. Keluar 1 bila produk tidak ditemukan, bukan
    TEXT_STOCK, atau broadcast channel gagal (worker mencatat ERROR).
    """
    from aiogram import Bot

    from bot.services.stock_updater import broadcast_restock_event
    from config import settings

    async with async_session() as s:
        product = await crud.get_product_by_id(session=s, product_id=product_id)
        if not product:
            print(json.dumps({"product_id": product_id, "error": "not found"}))
            raise SystemExit(1)
        if product.product_type != "TEXT_STOCK":
            print(json.dumps({"product_id": product_id, "error": "not TEXT_STOCK"}))
            raise SystemExit(1)
        if product.is_out_of_stock:
            product.is_out_of_stock = False
            await s.commit()
        bot = Bot(token=settings.BOT_TOKEN)
        try:
            res = await broadcast_restock_event(
                bot, s, product, int(added), int(total)
            )
        finally:
            await bot.session.close()
    print(
        json.dumps(
            {
                "product_id": product_id,
                "name": product.name,
                "added": int(added),
                "total": int(total),
                "channel": res.get("channel"),
                "dm_sent": res.get("dm_sent"),
                "dm_failed": res.get("dm_failed"),
                "subscribers_notified": res.get("subscribers_notified"),
            }
        )
    )
    if not res.get("channel"):
        raise SystemExit(1)


async def cmd_price_change(product_id, old_price, new_price, name=None, sources="", current="", drift=False):
    """Broadcast HARGA BERUBAH ke channel Aeternum + DM semua user + DM admin.

    Dipanggil price-watch watcher saat harga berubah di bot, store, atau
    prices.json. product_id ATAU name wajib diisi: product_id bila produk
    ada di bot (tombol Beli Sekarang ikut), name bila hanya ada di katalog
    (tanpa tombol). Semua tipe produk boleh (TEXT_STATIC ikut).
    Keluar 1 bila produk tidak ditemukan atau broadcast channel gagal.
    """
    from aiogram import Bot

    from bot.services.broadcast import get_category_name
    from bot.services.stock_updater import broadcast_price_change_event
    from config import settings

    if product_id is None and not name:
        print(json.dumps({"error": "product-id or name required"}))
        raise SystemExit(1)
    async with async_session() as s:
        product = None
        cat_name = "Katalog Peka"
        if product_id is not None:
            product = await crud.get_product_by_id(session=s, product_id=product_id)
            if not product:
                print(json.dumps({"product_id": product_id, "error": "not found"}))
                raise SystemExit(1)
            name = product.name
            cat_name = await get_category_name(s, product.category_id)
        bot = Bot(token=settings.BOT_TOKEN)
        try:
            res = await broadcast_price_change_event(
                bot, s, product, name, cat_name,
                int(old_price), int(new_price),
                sources=sources, current_prices=current, drift=drift,
            )
        finally:
            await bot.session.close()
    print(
        json.dumps(
            {
                "product_id": product_id,
                "name": name,
                "old_price": int(old_price),
                "new_price": int(new_price),
                "channel": res.get("channel"),
                "dm_sent": res.get("dm_sent"),
                "dm_failed": res.get("dm_failed"),
                "admin_dm": res.get("admin_dm"),
            },
            ensure_ascii=False,
        )
    )
    if not res.get("channel"):
        raise SystemExit(1)


async def cmd_prices():
    """Dump semua produk aktif (id, nama, harga rupiah, tipe) sebagai JSON.

    Read-only; dipakai price-watch watcher untuk membandingkan harga bot
    dengan snapshot. Tidak mengirim apa pun.
    """
    async with async_session() as s:
        res = await s.execute(
            select(Product).where(Product.is_active.is_(True))
        )
        out = [
            {
                "id": p.id,
                "name": p.name,
                "price": int(p.price),
                "type": p.product_type,
            }
            for p in res.scalars().all()
        ]
    print(json.dumps(out, ensure_ascii=False))


async def cmd_store_sale(payload):
    """Broadcast a store sale to the Aeternum channel, same format as a
    bot purchase (broadcast_transaction_success). Reads
    {product, amount, buyer?} on stdin. No WA / ID / account content.
    Exits 1 on bad payload or failed broadcast (worker logs ERROR and
    leaves the row unsent for retry)."""
    from aiogram import Bot

    from bot.services.broadcast import broadcast_transaction_success
    from config import settings

    payload = payload or {}
    product = payload.get("product")
    amount = payload.get("amount")
    buyer = payload.get("buyer") or None
    if not product or not isinstance(amount, (int, float)) or float(amount) <= 0:
        print(
            json.dumps(
                {"error": "bad payload", "product": product, "amount": amount}
            )
        )
        raise SystemExit(1)
    bot = Bot(token=settings.BOT_TOKEN)
    try:
        ok = await broadcast_transaction_success(
            bot,
            product_name=str(product),
            amount=float(amount),
            buyer_first_name=buyer,
        )
    finally:
        await bot.session.close()
    print(
        json.dumps(
            {"product": product, "amount": float(amount), "broadcasted": bool(ok)}
        )
    )
    if not ok:
        raise SystemExit(1)


async def cmd_recent_sales():
    """Paid bot product purchases (last 30 days) for the store
    social-proof popup. Read-only; prints a JSON list of
    {id, amount, paid_at, product_id, product_name, buyer}."""
    async with async_session() as s:
        res = await s.execute(
            text(
                """
                SELECT t.id, t.amount, t.paid_at,
                       p.id AS product_id, p.name AS product_name,
                       u.first_name AS buyer
                FROM transactions t
                JOIN products p ON p.id = t.product_id
                JOIN users u ON u.id = t.user_id
                WHERE t.trx_type = 'PURCHASE' AND t.status = 'PAID'
                  AND t.paid_at >= NOW() - INTERVAL '30 days'
                ORDER BY t.paid_at DESC
                LIMIT 20
                """
            )
        )
        rows = [
            {
                "id": r.id,
                "amount": float(r.amount),
                "paid_at": r.paid_at.isoformat() if r.paid_at else None,
                "product_id": r.product_id,
                "product_name": r.product_name,
                "buyer": r.buyer or "",
            }
            for r in res
        ]
    print(json.dumps(rows))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch-events")
    f.add_argument("--product-ids", required=True)
    sub.add_parser("apply-events")
    sub.add_parser("mark-processed")
    c = sub.add_parser("counts")
    c.add_argument("--product-ids", required=True)
    sub.add_parser("notify-batch")
    so = sub.add_parser("stock-out")
    so.add_argument("--product-id", required=True, type=int)
    rs = sub.add_parser("restock")
    rs.add_argument("--product-id", required=True, type=int)
    rs.add_argument("--added", required=True, type=int)
    rs.add_argument("--total", required=True, type=int)
    pc = sub.add_parser("price-change")
    pc.add_argument("--product-id", type=int, default=None)
    pc.add_argument("--name", default=None)
    pc.add_argument("--old-price", required=True, type=int)
    pc.add_argument("--new-price", required=True, type=int)
    pc.add_argument("--sources", default="")
    pc.add_argument("--current", default="")
    pc.add_argument("--drift", action="store_true")
    sub.add_parser("prices")
    sub.add_parser("store-sale")
    sub.add_parser("recent-sales")
    args = ap.parse_args()

    if args.cmd == "fetch-events":
        ids = [int(x) for x in args.product_ids.split(",") if x.strip()]
        asyncio.run(cmd_fetch_events(ids))
    elif args.cmd == "apply-events":
        events = json.load(sys.stdin)
        asyncio.run(cmd_apply_events(events))
    elif args.cmd == "mark-processed":
        ids = json.load(sys.stdin)
        asyncio.run(cmd_mark_processed(ids))
    elif args.cmd == "notify-batch":
        messages = json.load(sys.stdin)
        asyncio.run(cmd_notify_batch(messages))
    elif args.cmd == "counts":
        ids = [int(x) for x in args.product_ids.split(",") if x.strip()]
        asyncio.run(cmd_counts(ids))
    elif args.cmd == "stock-out":
        asyncio.run(cmd_stock_out(args.product_id))
    elif args.cmd == "restock":
        asyncio.run(cmd_restock(args.product_id, args.added, args.total))
    elif args.cmd == "price-change":
        asyncio.run(cmd_price_change(args.product_id, args.old_price, args.new_price, name=args.name, sources=args.sources, current=args.current, drift=args.drift))
    elif args.cmd == "prices":
        asyncio.run(cmd_prices())
    elif args.cmd == "store-sale":
        payload = json.load(sys.stdin)
        asyncio.run(cmd_store_sale(payload))
    elif args.cmd == "recent-sales":
        asyncio.run(cmd_recent_sales())


if __name__ == "__main__":
    main()
