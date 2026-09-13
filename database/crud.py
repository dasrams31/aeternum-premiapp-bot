"""
Aeternum PremiApp Bot - Asynchronous Database CRUD Operations
"""

from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Category, Product, ProductItem, PromoCode, PromoUsage, Transaction, User


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
    """Mengambil seluruh ID pengguna untuk broadcast massal."""
    stmt = select(User.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_user_balance(
    session: AsyncSession, user_id: int, amount: float
) -> Optional[User]:
    """Menambahkan saldo utama dompet pengguna."""
    user = await get_user_by_id(session, user_id)
    if user:
        user.balance = float(user.balance or 0.0) + amount
        await session.commit()
        await session.refresh(user)
    return user


async def deduct_user_balance_atomic(
    session: AsyncSession, user_id: int, amount: float
) -> bool:
    """
    Mengurangi saldo pengguna secara atomic dengan lock.
    Mengembalikan True jika saldo cukup dan berhasil dipotong.
    """
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
    user = await get_user_by_id(session, referrer_id)
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
    description: Optional[str] = None,
    text_content: Optional[str] = None,
    telegram_file_id: Optional[str] = None,
    vip_chat_id: Optional[int] = None,
) -> Product:
    product = Product(
        category_id=category_id,
        name=name,
        price=price,
        product_type=product_type,
        description=description,
        text_content=text_content,
        telegram_file_id=telegram_file_id,
        vip_chat_id=vip_chat_id,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


# ==========================================
# 5. PRODUCT ITEM & STOCK OPERATIONS
# ==========================================
async def count_available_stock(
    session: AsyncSession, product_id: int
) -> int:
    stmt = (
        select(func.count(ProductItem.id))
        .where(ProductItem.product_id == product_id)
        .where(ProductItem.is_sold.is_(False))
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def add_stock_items_bulk(
    session: AsyncSession, product_id: int, contents: List[str]
) -> int:
    items = [
        ProductItem(product_id=product_id, content=content.strip())
        for content in contents
        if content.strip()
    ]
    if not items:
        return 0
    session.add_all(items)
    await session.commit()
    return len(items)


async def get_and_lock_available_item(
    session: AsyncSession, product_id: int, transaction_id: str
) -> Optional[ProductItem]:
    stmt = (
        select(ProductItem)
        .where(ProductItem.product_id == product_id)
        .where(ProductItem.is_sold.is_(False))
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if item:
        item.is_sold = True
        item.sold_at = datetime.utcnow()
        item.transaction_id = transaction_id
        await session.commit()
        await session.refresh(item)

    return item


# ==========================================
# 6. TRANSACTION OPERATIONS
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
) -> Optional[Transaction]:
    trx = await get_transaction_by_id(session, transaction_id)
    if trx:
        trx.status = "PAID"
        trx.paid_at = datetime.utcnow()
        if delivered_content:
            trx.delivered_content = delivered_content
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
