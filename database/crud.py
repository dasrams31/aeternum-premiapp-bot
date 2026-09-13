"""
Aeternum PremiApp Bot - Asynchronous Database CRUD Operations
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Category, Product, ProductItem, Transaction, User


# ==========================================
# 1. USER OPERATIONS
# ==========================================
async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    is_admin: bool = False,
) -> User:
    """Ambil user atau buat baru jika belum ada di database."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            is_admin=is_admin,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update info jika username/name berubah
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

    return user


# ==========================================
# 2. CATEGORY OPERATIONS
# ==========================================
async def get_categories(
    session: AsyncSession, only_active: bool = True
) -> List[Category]:
    """Mengambil semua kategori."""
    stmt = select(Category)
    if only_active:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_category(
    session: AsyncSession, name: str, description: Optional[str] = None
) -> Category:
    """Menambahkan kategori baru."""
    category = Category(name=name, description=description)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


# ==========================================
# 3. PRODUCT OPERATIONS
# ==========================================
async def get_products_by_category(
    session: AsyncSession, category_id: int, only_active: bool = True
) -> List[Product]:
    """Mengambil daftar produk berdasarkan ID kategori."""
    stmt = select(Product).where(Product.category_id == category_id)
    if only_active:
        stmt = stmt.where(Product.is_active.is_(True))
    stmt = stmt.order_by(Product.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_product_by_id(
    session: AsyncSession, product_id: int
) -> Optional[Product]:
    """Mengambil detail 1 produk."""
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
    """Menambahkan produk baru ke database."""
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
# 4. PRODUCT ITEM & STOCK OPERATIONS
# ==========================================
async def count_available_stock(
    session: AsyncSession, product_id: int
) -> int:
    """Menghitung sisa stok yang belum terjual."""
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
    """Memasukkan banyak stok teks sekaligus."""
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
    """
    Atomic Stock Delivery:
    Mengambil 1 stok dan menguncinya dengan FOR UPDATE SKIP LOCKED
    untuk mencegah race condition saat banyak pembeli bayar bersamaan.
    """
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
# 5. TRANSACTION OPERATIONS
# ==========================================
async def create_transaction(
    session: AsyncSession,
    invoice_id: str,
    user_id: int,
    product_id: int,
    amount: float,
    qris_string: Optional[str] = None,
    qris_image_url: Optional[str] = None,
    gateway_reference: Optional[str] = None,
    expired_at: Optional[datetime] = None,
) -> Transaction:
    """Membuat invoice transaksi baru dengan status PENDING."""
    trx = Transaction(
        id=invoice_id,
        user_id=user_id,
        product_id=product_id,
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
    """Mengambil transaksi berdasarkan ID Invoice."""
    stmt = select(Transaction).where(Transaction.id == transaction_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def mark_transaction_paid(
    session: AsyncSession,
    transaction_id: str,
    delivered_content: Optional[str] = None,
) -> Optional[Transaction]:
    """Memperbarui status transaksi menjadi PAID."""
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
    """Mengambil riwayat transaksi milik user."""
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
