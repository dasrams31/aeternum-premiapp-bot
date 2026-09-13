"""
Aeternum PremiApp Bot - Start & General Handlers
"""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from bot.keyboards.user_kb import back_to_main_kb, main_menu_kb

router = Router(name="start_router")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Handler saat pengguna mengirim perintah /start."""
    user = message.from_user
    if not user:
        return

    is_admin = user.id == settings.ADMIN_ID
    await crud.get_or_create_user(
        session=session,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        is_admin=is_admin,
    )

    welcome_text = (
        f"👋 Halo <b>{user.first_name}</b>, selamat datang di\n"
        f"🌟 <b>Aeternum PremiApp Bot</b> 🌟\n\n"
        f"Layanan penyedia produk digital & akun premium otomatis 24/7.\n"
        f"Pembayaran instan via <b>QRIS</b> (Semua Bank & E-Wallet) dan produk langsung dikirim ke chat ini dalam hitungan detik!\n\n"
        f"Silakan pilih menu di bawah untuk mulai berbelanja 👇"
    )

    await message.answer(
        text=welcome_text,
        reply_markup=main_menu_kb(is_admin=is_admin),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery, session: AsyncSession) -> None:
    """Navigasi kembali ke menu utama."""
    user = callback.from_user
    is_admin = user.id == settings.ADMIN_ID

    text = (
        f"🏠 <b>MENU UTAMA - Aeternum PremiApp Bot</b>\n\n"
        f"Silakan pilih layanan yang Anda inginkan:"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=main_menu_kb(is_admin=is_admin),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "user_how_to_buy")
async def cb_how_to_buy(callback: CallbackQuery) -> None:
    """Petunjuk cara pembelian."""
    text = (
        "💎 <b>PANDUAN CARA PEMBELIAN:</b>\n\n"
        "1. Pilih menu <b>🛍️ Katalog Produk</b>.\n"
        "2. Pilih Kategori & Produk yang Anda inginkan.\n"
        "3. Tekan tombol <b>⚡ Beli Sekarang via QRIS</b>.\n"
        "4. Bot akan mengirimkan gambar & string QRIS Dinamis.\n"
        "5. Scan dan bayar melalui aplikasi E-Wallet (GoPay, OVO, DANA, ShopeePay) atau Mobile Banking favorit Anda.\n"
        "6. Setelah pembayaran berhasil, bot akan <b>langsung mengirimkan akun / file / teks</b> Anda secara otomatis!\n\n"
        "⚡ <i>Proses 100% otomatis tanpa perlu menunggu konfirmasi admin.</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "user_help")
async def cb_help(callback: CallbackQuery) -> None:
    """Informasi Bantuan & Customer Service."""
    text = (
        "💬 <b>PUSAT BANTUAN & CS</b>\n\n"
        "Mengalami kendala saat transaksi atau pertanyaan seputar garansi akun?\n\n"
        "Silakan hubungi admin kami melalui kontak berikut:\n"
        "👤 <b>Customer Service:</b> @dasrams\n"
        "⏰ <b>Jam Operasional:</b> 24 Jam (Sistem Otomatis) | CS Response (08:00 - 22:00 WIB)\n\n"
        "<i>Harap sertakan ID Invoice (contoh: <code>#AP-2026xxxx</code>) saat mengajukan pertanyaan transaksi.</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()
