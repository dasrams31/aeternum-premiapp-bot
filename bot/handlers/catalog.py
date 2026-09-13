"""
Aeternum PremiApp Bot - Catalog & Product Browsing Handlers
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from bot.keyboards.user_kb import (
    back_to_main_kb,
    categories_kb,
    product_detail_kb,
    products_kb,
)

router = Router(name="catalog_router")


@router.callback_query(F.data == "user_catalog")
async def cb_show_categories(callback: CallbackQuery, session: AsyncSession) -> None:
    """Menampilkan daftar kategori produk yang aktif."""
    categories = await crud.get_categories(session=session, only_active=True)

    if not categories:
        text = (
            "🛍️ <b>KATALOG PRODUK</b>\n\n"
            "Saat ini belum ada kategori produk yang tersedia. Silakan cek kembali beberapa saat lagi!"
        )
        if callback.message:
            await callback.message.edit_text(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        await callback.answer()
        return

    text = (
        "🛍️ <b>KATALOG PRODUK DIGITAL</b>\n\n"
        "Silakan pilih kategori produk di bawah ini untuk melihat daftar produk yang tersedia:"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=categories_kb(categories),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_"))
async def cb_show_category_products(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Menampilkan daftar produk dalam kategori tertentu beserta sisa stoknya."""
    category_id = int(callback.data.split("_")[1])
    products = await crud.get_products_by_category(
        session=session, category_id=category_id, only_active=True
    )

    if not products:
        text = (
            "📂 <b>DAFTAR PRODUK</b>\n\n"
            "Belum ada produk aktif dalam kategori ini."
        )
        if callback.message:
            await callback.message.edit_text(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        await callback.answer()
        return

    # Kumpulkan ketersediaan stok live untuk setiap produk
    products_with_stock = []
    for prod in products:
        if prod.product_type == "TEXT_STOCK":
            stock = await crud.count_available_stock(session=session, product_id=prod.id)
        else:
            stock = 999  # Stok tak terbatas untuk file/link/teks statis
        products_with_stock.append((prod, stock))

    text = (
        "📂 <b>PILIH PRODUK DIGITAL</b>\n\n"
        "Berikut adalah daftar produk yang tersedia. Ketuk salah satu untuk melihat deskripsi lengkap:"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=products_kb(products_with_stock),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("prod_"))
async def cb_show_product_detail(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Menampilkan detail produk, harga, deskripsi, dan tombol checkout."""
    product_id = int(callback.data.split("_")[1])
    product = await crud.get_product_by_id(session=session, product_id=product_id)

    if not product:
        await callback.answer("Produk tidak ditemukan!", show_alert=True)
        return

    # Cek ketersediaan stok
    is_available = True
    stock_info = "⚡ <b>Pengiriman:</b> Instan 24/7 (Teks / File)"

    if product.product_type == "TEXT_STOCK":
        stock_count = await crud.count_available_stock(session=session, product_id=product.id)
        if stock_count > 0:
            stock_info = f"🟢 <b>Stok Tersedia:</b> <code>{stock_count} Akun / Key</code>"
        else:
            stock_info = "🔴 <b>Stok Tersedia:</b> <i>Habis</i>"
            is_available = False

    formatted_price = f"Rp {product.price:,.0f}".replace(",", ".")
    desc_text = product.description or "Tidak ada deskripsi tambahan."

    text = (
        f"📦 <b>DETAIL PRODUK: {product.name.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Harga:</b> <code>{formatted_price}</code>\n"
        f"{stock_info}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Deskripsi & Ketentuan:</b>\n"
        f"{desc_text}\n\n"
        f"<i>💡 Tekan tombol di bawah untuk membuat QRIS pembayaran.</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=product_detail_kb(product, is_available),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "stock_empty_alert")
async def cb_stock_empty_alert(callback: CallbackQuery) -> None:
    """Alert saat user klik tombol beli pada produk yang stoknya habis."""
    await callback.answer(
        "Mohon maaf, stok produk ini sedang kosong. Admin akan segera melakukan restock!",
        show_alert=True,
    )
