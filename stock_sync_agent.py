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
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime

sys.path.insert(0, "/home/ubuntu/aeternum-premiapp-bot")

from sqlalchemy import or_, select, update

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


if __name__ == "__main__":
    main()
