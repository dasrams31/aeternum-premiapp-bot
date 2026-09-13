"""
Aeternum PremiApp Bot - Asynchronous Database CRUD Operations
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.crypto import encrypt_text, decrypt_text
from .models import (
    Category,
    Product,
    ProductItem,
    PromoCode,
    PromoUsage,
    RestockNotification,
    Review,
    Transaction,
    User,
    WarrantyTicket,
)


# ==========================================
# 1. USER, BALANCE & REFERRAL OPERATIONS
# ==========================================
async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    is_admin: bool = False,
    referrer_id: Optional[int] = None,
) -> Tuple[User, bool]:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        valid_referrer = None
        if referrer_id and referrer_id != user_id:
            ref_stmt = select(User).where(User.id == referrer_id)
            ref_user = (await session.execute(ref_stmt)).scalar_one_or_none()
            if ref_user:
                valid_referrer = referrer_id
                ref_user.total_referrals += 1

        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            is_admin=is_admin,
            referred_by=valid_referrer,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, True
    else:
        updated = False
        if username and user.username != username:
            user.username = username
            updated = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            updated = True
        if updated:
            await session.commit()
            await session.refresh(user)
        return user, False


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_user_ids(session: AsyncSession) -> List[int]:
    stmt = select(User.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_user_balance(
    session: AsyncSession, user_id: int, amount: float
) -> Optional[User]:
    stmt = (
        select(User)
        .where(User.id == user_id)
        .with_for_update()
    )
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()
    if user:
        user.balance = float(user.balance or 0.0) + amount
        await session.commit()
        await session.refresh(user)
    return user


async def deduct_user_balance_atomic(
    session: AsyncSession, user_id: int, amount: float
) -> bool:
    stmt = (
        select(User)
        .where(User.id == user_id)
        .with_for_update()
    )
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or float(user.balance or 0.0) < amount:
        return False

    user.balance = float(user.balance) - amount
    await session.commit()
    await session.refresh(user)
    return True


async def add_referral_commission(
    session: AsyncSession, referrer_id: int, commission_amount: float
) -> Optional[User]:
    stmt = (
        select(User)
        .where(User.id == referrer_id)
        .with_for_update()
    )
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()
    if user:
        user.referral_balance = float(user.referral_balance or 0.0) + commission_amount
        await session.commit()
        await session.refresh(user)
    return user


# ==========================================
# 2. PROMO CODE & DISCOUNT OPERATIONS
# ==========================================
async def create_promo_code(
    session: AsyncSession,
    code: str,
    discount_type: str,
    discount_value: float,
    min_purchase: float = 0.0,
    max_discount: Optional[float] = None,
    max_usage: int = 100,
    expired_at: Optional[datetime] = None,
) -> PromoCode:
    promo = PromoCode(
        code=code.strip().upper(),
        discount_type=discount_type.upper(),
        discount_value=discount_value,
        min_purchase=min_purchase,
        max_discount=max_discount,
        max_usage=max_usage,
        expired_at=expired_at,
    )
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo


async def validate_and_apply_promo(
    session: AsyncSession,
    code_str: str,
    user_id: int,
    original_price: float,
) -> Tuple[bool, str, float, Optional[PromoCode]]:
    code_clean = code_str.strip().upper()
    stmt = select(PromoCode).where(PromoCode.code == code_clean)
    result = await session.execute(stmt)
    promo = result.scalar_one_or_none()

    if not promo or not promo.is_active:
        return False, "❌ Kode promo tidak ditemukan atau sudah tidak aktif.", 0.0, None

    if promo.expired_at and promo.expired_at < datetime.utcnow():
        return False, "❌ Masa berlaku kode promo ini telah berakhir.", 0.0, None

    if promo.used_count >= promo.max_usage:
        return False, "❌ Kuota penggunaan kode promo ini sudah habis.", 0.0, None

    if original_price < float(promo.min_purchase):
        return (
            False,
            f"❌ Minimal pembelian untuk promo ini adalah Rp {promo.min_purchase:,.0f}.".replace(",", "."),
            0.0,
            None,
        )

    usage_stmt = (
        select(PromoUsage)
        .where(PromoUsage.promo_id == promo.id)
        .where(PromoUsage.user_id == user_id)
    )
    existing_usage = (await session.execute(usage_stmt)).scalar_one_or_none()
    if existing_usage:
        return False, "❌ Anda sudah pernah menggunakan kode promo ini sebelumnya.", 0.0, None

    if promo.discount_type == "PERCENT":
        discount = original_price * (float(promo.discount_value) / 100.0)
        if promo.max_discount and discount > float(promo.max_discount):
            discount = float(promo.max_discount)
    else:
        discount = float(promo.discount_value)
        if discount > original_price:
            discount = original_price

    return True, f"✅ Kupon valid! Potongan diskon Rp {discount:,.0f}.".replace(",", "."), discount, promo


async def record_promo_usage(
    session: AsyncSession,
    promo_id: int,
    user_id: int,
    transaction_id: str,
    discount_amount: float,
) -> None:
    promo_stmt = select(PromoCode).where(PromoCode.id == promo_id)
    promo = (await session.execute(promo_stmt)).scalar_one_or_none()
    if promo:
        promo.used_count += 1

    usage = PromoUsage(
        promo_id=promo_id,
        user_id=user_id,
        transaction_id=transaction_id,
        discount_amount=discount_amount,
    )
    session.add(usage)
    await session.commit()


# ==========================================
# 3. CATEGORY OPERATIONS
# ==========================================
async def get_categories(
    session: AsyncSession, only_active: bool = True
) -> List[Category]:
    stmt = select(Category)
    if only_active:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_category(
    session: AsyncSession, name: str, description: Optional[str] = None
) -> Category:
    category = Category(name=name, description=description)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


# ==========================================
# 4. PRODUCT OPERATIONS
# ==========================================
async def get_products_by_category(
    session: AsyncSession, category_id: int, only_active: bool = True
) -> List[Product]:
    stmt = select(Product).where(Product.category_id == category_id)
    if only_active:
        stmt = stmt.where(Product.is_active.is_(True))
    stmt = stmt.order_by(Product.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_product_by_id(
    session: AsyncSession, product_id: int
) -> Optional[Product]:
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_product(
    session: AsyncSession,
    category_id: int,
    name: str,
    price: float,
    product_type: str,
    duration_days: int = 30,
    description: Optional[str] = None,
    text_content: Optional[str] = None,
    telegram_file_id: Optional[str] = None,
    vip_chat_id: Optional[int] = None,
    warranty_type: str = "NONE",
    warranty_note: Optional[str] = None,
) -> Product:
    product = Product(
        category_id=category_id,
        name=name,
        price=price,
        product_type=product_type,
        duration_days=duration_days,
        description=description,
        text_content=text_content,
        telegram_file_id=telegram_file_id,
        vip_chat_id=vip_chat_id,
        warranty_type=warranty_type,
        warranty_note=warranty_note,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def update_product_warranty(
    session: AsyncSession,
    product_id: int,
    warranty_type: str,
    warranty_note: Optional[str] = None,
) -> Optional[Product]:
    product = await get_product_by_id(session, product_id)
    if product:
        product.warranty_type = warranty_type
        product.warranty_note = warranty_note
        await session.commit()
        await session.refresh(product)
    return product


async def get_product_buyers(
    session: AsyncSession, product_id: int
) -> List[int]:
    """Mengambil list User ID pembeli yang pernah membeli produk ini (berstatus PAID)."""
    stmt = (
        select(Transaction.user_id)
        .where(
            Transaction.product_id == product_id,
            Transaction.status == "PAID",
        )
        .distinct()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ==========================================
# 5. PRODUCT ITEM & TEMPORARY STOCK RESERVATION
# ==========================================
async def count_available_stock(
    session: AsyncSession, product_id: int
) -> int:
    now = datetime.utcnow()
    stmt = (
        select(func.count(ProductItem.id))
        .where(ProductItem.product_id == product_id)
        .where(ProductItem.is_sold.is_(False))
        .where(
            or_(
                ProductItem.reserved_until.is_(None),
                ProductItem.reserved_until < now,
            )
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def add_stock_items_bulk(
    session: AsyncSession, product_id: int, contents: List[str]
) -> int:
    items = [
        ProductItem(product_id=product_id, content=encrypt_text(content.strip()))
        for content in contents
        if content.strip()
    ]
    if not items:
        return 0
    session.add_all(items)
    await session.commit()
    return len(items)


async def reserve_stock_item_atomic(
    session: AsyncSession, product_id: int, transaction_id: str, duration_minutes: int = 15
) -> Optional[ProductItem]:
    now = datetime.utcnow()
    stmt = (
        select(ProductItem)
        .where(ProductItem.product_id == product_id)
        .where(ProductItem.is_sold.is_(False))
        .where(
            or_(
                ProductItem.reserved_until.is_(None),
                ProductItem.reserved_until < now,
            )
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if item:
        item.reserved_by_trx = transaction_id
        item.reserved_until = now + timedelta(minutes=duration_minutes)
        await session.commit()
        await session.refresh(item)

    return item


async def release_reserved_stock(
    session: AsyncSession, transaction_id: str
) -> bool:
    stmt = (
        update(ProductItem)
        .where(ProductItem.reserved_by_trx == transaction_id)
        .where(ProductItem.is_sold.is_(False))
        .values(reserved_by_trx=None, reserved_until=None)
    )
    res = await session.execute(stmt)
    await session.commit()
    return res.rowcount > 0


async def finalize_reserved_stock(
    session: AsyncSession, product_id: int, transaction_id: str
) -> Optional[ProductItem]:
    stmt = (
        select(ProductItem)
        .where(ProductItem.reserved_by_trx == transaction_id)
        .where(ProductItem.is_sold.is_(False))
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    res = await session.execute(stmt)
    item = res.scalar_one_or_none()

    if not item:
        now = datetime.utcnow()
        stmt_fallback = (
            select(ProductItem)
            .where(ProductItem.product_id == product_id)
            .where(ProductItem.is_sold.is_(False))
            .where(
                or_(
                    ProductItem.reserved_until.is_(None),
                    ProductItem.reserved_until < now,
                )
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        res_fallback = await session.execute(stmt_fallback)
        item = res_fallback.scalar_one_or_none()

    if item:
        item.is_sold = True
        item.sold_at = datetime.utcnow()
        item.transaction_id = transaction_id
        item.reserved_by_trx = None
        item.reserved_until = None
        await session.commit()
        await session.refresh(item)
        # Dekripsi konten sebelum digunakan di fulfillment
        item.content = decrypt_text(item.content)

    return item


async def release_all_expired_reservations(session: AsyncSession) -> int:
    now = datetime.utcnow()
    stmt = (
        update(ProductItem)
        .where(ProductItem.is_sold.is_(False))
        .where(ProductItem.reserved_until.is_not(None))
        .where(ProductItem.reserved_until < now)
        .values(reserved_by_trx=None, reserved_until=None)
    )
    res = await session.execute(stmt)
    await session.commit()
    return res.rowcount or 0


# ==========================================
# 6. RESTOCK NOTIFICATION OPERATIONS
# ==========================================
async def subscribe_restock_alert(
    session: AsyncSession, product_id: int, user_id: int
) -> Tuple[bool, str]:
    """Mendaftarkan pengguna ke antrian pengingat restock."""
    stmt = (
        select(RestockNotification)
        .where(RestockNotification.product_id == product_id)
        .where(RestockNotification.user_id == user_id)
        .where(RestockNotification.is_notified.is_(False))
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return False, "Anda sudah terdaftar dalam antrian pengingat restock produk ini!"

    alert = RestockNotification(product_id=product_id, user_id=user_id)
    session.add(alert)
    await session.commit()
    return True, "✅ Berhasil! Bot akan mengirimkan pesan saat produk ini sudah restock."


async def get_and_clear_restock_subscribers(
    session: AsyncSession, product_id: int
) -> List[int]:
    """Mengambil seluruh user_id yang menunggu dan menandainya sebagai sudah dinotifikasi."""
    stmt = (
        select(RestockNotification)
        .where(RestockNotification.product_id == product_id)
        .where(RestockNotification.is_notified.is_(False))
    )
    res = await session.execute(stmt)
    alerts = list(res.scalars().all())

    user_ids = []
    now = datetime.utcnow()
    for al in alerts:
        user_ids.append(al.user_id)
        al.is_notified = True
        al.notified_at = now

    if alerts:
        await session.commit()

    return user_ids


# ==========================================
# 7. TRANSACTION OPERATIONS & EXPORT
# ==========================================
async def create_transaction(
    session: AsyncSession,
    invoice_id: str,
    user_id: int,
    amount: float,
    product_id: Optional[int] = None,
    trx_type: str = "PURCHASE",
    payment_method: str = "QRIS",
    original_amount: float = 0.0,
    discount_amount: float = 0.0,
    promo_code: Optional[str] = None,
    qris_string: Optional[str] = None,
    qris_image_url: Optional[str] = None,
    gateway_reference: Optional[str] = None,
    expired_at: Optional[datetime] = None,
) -> Transaction:
    trx = Transaction(
        id=invoice_id,
        user_id=user_id,
        product_id=product_id,
        trx_type=trx_type,
        payment_method=payment_method,
        original_amount=original_amount or amount,
        discount_amount=discount_amount,
        promo_code=promo_code,
        amount=amount,
        qris_string=qris_string,
        qris_image_url=qris_image_url,
        gateway_reference=gateway_reference,
        status="PENDING",
        expired_at=expired_at,
    )
    session.add(trx)
    await session.commit()
    await session.refresh(trx)
    return trx


async def get_transaction_by_id(
    session: AsyncSession, transaction_id: str
) -> Optional[Transaction]:
    stmt = select(Transaction).where(Transaction.id == transaction_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def mark_transaction_paid(
    session: AsyncSession,
    transaction_id: str,
    delivered_content: Optional[str] = None,
    expires_service_at: Optional[datetime] = None,
) -> Optional[Transaction]:
    trx = await get_transaction_by_id(session, transaction_id)
    if trx:
        trx.status = "PAID"
        trx.paid_at = datetime.utcnow()
        if delivered_content:
            trx.delivered_content = delivered_content
        if expires_service_at:
            trx.expires_service_at = expires_service_at
        await session.commit()
        await session.refresh(trx)
    return trx


async def get_user_transactions(
    session: AsyncSession, user_id: int, limit: int = 10
) -> List[Transaction]:
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_paid_transactions_for_export(
    session: AsyncSession, limit: int = 2000
) -> List[Tuple[Transaction, Optional[Product], User]]:
    """Mengambil data transaksi lengkap untuk diexport ke CSV / Excel."""
    stmt = (
        select(Transaction, Product, User)
        .join(User, Transaction.user_id == User.id)
        .outerjoin(Product, Transaction.product_id == Product.id)
        .where(Transaction.status == "PAID")
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return list(res.all())


# ==========================================
# 8. SUBSCRIPTION EXPIRY REMINDERS
# ==========================================
async def get_due_subscription_reminders(
    session: AsyncSession,
) -> Tuple[List[Transaction], List[Transaction]]:
    """
    Mengambil transaksi yang perlu dikirim reminder H-3 dan H-1.
    Returns: (h3_list, h1_list)
    """
    now = datetime.utcnow()
    h3_cutoff = now + timedelta(days=3)
    h1_cutoff = now + timedelta(days=1)

    # H-3 Reminders: Sisa waktu <= 3 hari dan > 1 hari, reminder_h3_sent = False
    stmt_h3 = (
        select(Transaction)
        .where(Transaction.status == "PAID")
        .where(Transaction.expires_service_at.is_not(None))
        .where(Transaction.expires_service_at <= h3_cutoff)
        .where(Transaction.expires_service_at > h1_cutoff)
        .where(Transaction.reminder_h3_sent.is_(False))
    )
    h3_res = await session.execute(stmt_h3)
    h3_list = list(h3_res.scalars().all())

    # H-1 Reminders: Sisa waktu <= 1 hari dan > now, reminder_h1_sent = False
    stmt_h1 = (
        select(Transaction)
        .where(Transaction.status == "PAID")
        .where(Transaction.expires_service_at.is_not(None))
        .where(Transaction.expires_service_at <= h1_cutoff)
        .where(Transaction.expires_service_at > now)
        .where(Transaction.reminder_h1_sent.is_(False))
    )
    h1_res = await session.execute(stmt_h1)
    h1_list = list(h1_res.scalars().all())

    return h3_list, h1_list


async def mark_reminder_sent(
    session: AsyncSession, transaction_id: str, reminder_type: str
) -> None:
    trx = await get_transaction_by_id(session, transaction_id)
    if trx:
        if reminder_type == "H3":
            trx.reminder_h3_sent = True
        elif reminder_type == "H1":
            trx.reminder_h1_sent = True
        await session.commit()


# ==========================================
# 9. REVIEW & TESTIMONIAL OPERATIONS
# ==========================================
async def create_review(
    session: AsyncSession,
    transaction_id: str,
    user_id: int,
    product_id: int,
    rating: int,
    comment: Optional[str] = None,
) -> Review:
    review = Review(
        transaction_id=transaction_id,
        user_id=user_id,
        product_id=product_id,
        rating=rating,
        comment=comment,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return review


async def get_review_by_transaction(
    session: AsyncSession, transaction_id: str
) -> Optional[Review]:
    stmt = select(Review).where(Review.transaction_id == transaction_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ==========================================
# 10. WARRANTY TICKET OPERATIONS
# ==========================================
async def create_warranty_ticket(
    session: AsyncSession,
    ticket_code: str,
    transaction_id: str,
    user_id: int,
    product_id: int,
    issue_description: str,
    proof_file_id: Optional[str] = None,
) -> WarrantyTicket:
    ticket = WarrantyTicket(
        ticket_code=ticket_code,
        transaction_id=transaction_id,
        user_id=user_id,
        product_id=product_id,
        issue_description=issue_description,
        proof_file_id=proof_file_id,
        status="OPEN",
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_warranty_ticket_by_code(
    session: AsyncSession, ticket_code: str
) -> Optional[WarrantyTicket]:
    stmt = select(WarrantyTicket).where(WarrantyTicket.ticket_code == ticket_code)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def resolve_warranty_ticket(
    session: AsyncSession,
    ticket_code: str,
    status: str,
    admin_notes: Optional[str] = None,
    replacement_content: Optional[str] = None,
) -> Optional[WarrantyTicket]:
    ticket = await get_warranty_ticket_by_code(session, ticket_code)
    if ticket:
        ticket.status = status
        ticket.admin_notes = admin_notes
        ticket.replacement_content = replacement_content
        ticket.resolved_at = datetime.utcnow()
        await session.commit()
        await session.refresh(ticket)
    return ticket
