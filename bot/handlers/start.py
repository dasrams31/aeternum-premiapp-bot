"""
Aeternum PremiApp Bot - Start & General Handlers
"""

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import crud
from bot.keyboards.user_kb import back_to_main_kb, main_menu_kb, referral_menu_kb

router = Router(name="start_router")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Handler saat pengguna mengirim perintah /start (termasuk via referral link)."""
    user = message.from_user
    if not user:
        return

    # Cek apakah ada parameter referral di /start ref_XXXX
    referrer_id = None
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", ""))
        except ValueError:
            referrer_id = None

    is_admin = user.id == settings.ADMIN_ID
    db_user, is_new = await crud.get_or_create_user(
        session=session,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        is_admin=is_admin,
        referrer_id=referrer_id,
    )

    # Kirim notifikasi ke pengundang jika user baru bergabung lewat referralnya
    if is_new and referrer_id and referrer_id != user.id:
        try:
            await bot.send_message(
                chat_id=referrer_id,
                text=(
                    f"🎉 <b>TEMAN BARU BERGABUNG LEWAT LINK ANDA!</b>\n\n"
                    f"Pengguna <b>{user.first_name}</b> baru saja bergabung menggunakan tautan referral Anda.\n"
                    f"Anda akan mendapatkan <b>komisi 5%</b> dari setiap transaksi pembelian mereka!"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

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


@router.callback_query(F.data == "user_referral")
async def cb_show_referral(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    """Menampilkan Dasbor Program Afiliasi & Referral Pengguna."""
    user = callback.from_user
    db_user = await crud.get_user_by_id(session=session, user_id=user.id)
    if not db_user:
        return

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "AeternumPremiAppBot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    commission = float(db_user.referral_balance or 0.0)
    total_ref = db_user.total_referrals or 0
    formatted_commission = f"Rp {commission:,.0f}".replace(",", ".")

    text = (
        f"👥 <b>PROGRAM AFILIASI & REFERRAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Dapatkan <b>komisi 5%</b> dari setiap transaksi sukses yang dilakukan oleh teman yang Anda undang ke bot ini!\n\n"
        f"📊 <b>STATISTIK ANDA:</b>\n"
        f"• <b>Total Teman Bergabung:</b> <code>{total_ref} Orang</code>\n"
        f"• <b>Saldo Komisi Tersedia:</b> <code>{formatted_commission}</code>\n\n"
        f"🔗 <b>Tautan Undangan Anda:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>(Ketuk link di atas untuk menyalin, lalu bagikan ke teman/grup Anda)</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=referral_menu_kb(bot_username=bot_username, user_id=user.id),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "user_withdraw_referral")
async def cb_withdraw_referral(callback: CallbackQuery, session: AsyncSession) -> None:
    """Permintaan penarikan komisi referral."""
    user = callback.from_user
    db_user = await crud.get_user_by_id(session=session, user_id=user.id)
    balance = float(db_user.referral_balance or 0.0) if db_user else 0.0

    if balance < 10000:
        await callback.answer(
            f"Minimal penarikan komisi adalah Rp 10.000. Saldo Anda saat ini: Rp {balance:,.0f}.".replace(",", "."),
            show_alert=True,
        )
        return

    text = (
        f"💳 <b>PENARIKAN KOMISI REFERRAL</b>\n\n"
        f"Saldo komisi Anda: <b>Rp {balance:,.0f}</b>\n\n"
        f"Untuk mencairkan saldo ke Rekening / E-Wallet (DANA, GoPay, OVO), silakan hubungi CS kami di @dasrams dengan format:\n"
        f"<code>Penarikan Komisi - ID: {user.id} - Nominal: Rp {balance:,.0f} - Rekening/E-Wallet: [Nomor Anda]</code>"
    ).replace(",", ".")

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
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
        "3. (Opsional) Tekan tombol <b>🎟️ Pakai Kode Diskon</b> jika memiliki voucher promo.\n"
        "4. Tekan tombol <b>⚡ Beli Sekarang via QRIS</b>.\n"
        "5. Bot akan mengirimkan gambar & string QRIS Dinamis.\n"
        "6. Scan dan bayar melalui aplikasi E-Wallet (GoPay, OVO, DANA, ShopeePay) atau Mobile Banking favorit Anda.\n"
        "7. Setelah pembayaran berhasil, bot akan <b>langsung mengirimkan akun / file / teks</b> Anda secara otomatis!\n\n"
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
