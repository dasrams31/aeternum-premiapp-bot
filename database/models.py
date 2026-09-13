"""
Aeternum PremiApp Bot - SQLAlchemy 2.0 Async ORM Models
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram User ID
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Afiliasi & Referral
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    referral_balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    total_referrals: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username='{self.username}'>"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    products: Mapped[List["Product"]] = relationship(
        "Product", back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name='{self.name}'>"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    
    # Types: 'TEXT_STOCK', 'TEXT_STATIC', 'FILE', 'INVITE_LINK'
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Delivery content attributes
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vip_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped[Optional["Category"]] = relationship(
        "Category", back_populates="products"
    )
    items: Mapped[List["ProductItem"]] = relationship(
        "ProductItem", back_populates="product", cascade="all, delete-orphan"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="product"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} name='{self.name}' price={self.price}>"


class ProductItem(Base):
    __tablename__ = "product_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sold_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["Product"] = relationship("Product", back_populates="items")

    def __repr__(self) -> str:
        return f"<ProductItem id={self.id} product_id={self.product_id} is_sold={self.is_sold}>"


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), default="PERCENT")  # 'PERCENT' or 'FIXED'
    discount_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    min_purchase: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    max_discount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    max_usage: Mapped[int] = mapped_column(Integer, default=100)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    usages: Mapped[List["PromoUsage"]] = relationship(
        "PromoUsage", back_populates="promo", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PromoCode code='{self.code}' value={self.discount_value}>"


class PromoUsage(Base):
    __tablename__ = "promo_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(String(50), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    promo: Mapped["PromoCode"] = relationship("PromoCode", back_populates="usages")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    original_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    promo_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # Final amount to pay
    
    qris_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qris_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gateway_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    delivered_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="transactions")
    product: Mapped["Product"] = relationship("Product", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Transaction id='{self.id}' amount={self.amount} status='{self.status}'>"
