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
    user = message.from_user
    if not user:
        return

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
        f"🌟 <b>Aeternum PremiApp Bot</b> 🌟\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Owner & Admin Utama:</b> @dasrams\n"
        f"⚡ <b>Sistem Operasional:</b> Otomatis 24 Jam Non-Stop\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Layanan penyedia produk digital, akun premium, lisensi software, dan konten VIP terpercaya.\n\n"
        f"💳 <b>Metode Pembayaran:</b> QRIS Instan (BCA, Mandiri, BRI, BNI, GoPay, OVO, DANA, ShopeePay) & Saldo Dompet.\n"
        f"🚀 <b>Pengiriman:</b> Langsung dikirim ke chat ini dalam hitungan detik setelah bayar!\n\n"
        f"Silakan pilih menu di bawah ini untuk mulai berbelanja 👇"
    )

    await message.answer(
        text=welcome_text,
        reply_markup=main_menu_kb(is_admin=is_admin),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery, session: AsyncSession) -> None:
    user = callback.from_user
    is_admin = user.id == settings.ADMIN_ID

    text = (
        f"🏠 <b>MENU UTAMA — Aeternum PremiApp Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Admin Utama:</b> @dasrams\n\n"
        f"Silakan pilih layanan yang Anda butuhkan:"
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
    user = callback.from_user
    db_user = await crud.get_user_by_id(session=session, user_id=user.id)
    if not db_user:
        return

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "aeternum_premibot"
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
        f"<i>(Ketuk link di atas untuk menyalin, lalu bagikan ke teman/grup Anda)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <i>Pencairan saldo diproses langsung oleh Admin Utama @dasrams.</i>"
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
        f"💳 <b>PENARIKAN KOMISI REFERRAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Saldo Komisi Anda:</b> <code>Rp {balance:,.0f}</code>\n\n"
        f"Untuk mencairkan saldo ke Rekening Bank / E-Wallet (DANA, GoPay, OVO, ShopeePay), silakan hubungi <b>Admin Utama @dasrams</b> dengan format:\n\n"
        f"<code>Halo Admin @dasrams, saya ingin tarik komisi referral:\n"
        f"- ID Telegram: {user.id}\n"
        f"- Nominal: Rp {balance:,.0f}\n"
        f"- Metode: [BCA / DANA / GoPay / OVO]\n"
        f"- Nomor Rekening/E-Wallet: [Nomor Anda]\n"
        f"- Atas Nama: [Nama Pemilik]</code>"
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
    text = (
        "💎 <b>PANDUAN LENGKAP CARA PEMBELIAN:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        "1. Buka menu <b>🛍️ Katalog Produk</b>.\n"
        "2. Pilih Kategori & varian produk yang Anda inginkan.\n"
        "3. (Opsional) Tekan tombol <b>🎟️ Pakai Kode Diskon</b> jika memiliki voucher promo.\n"
        "4. Pilih metode checkout:\n"
        "   • <b>⚡ Bayar Pakai Saldo:</b> Instan 1 detik tanpa scan.\n"
        "   • <b>⚡ Beli Sekarang via QRIS:</b> Scan kode QR via BCA, DANA, GoPay, OVO, dll.\n"
        "5. Setelah pembayaran berhasil, bot akan <b>langsung mengirimkan kredensial akun / file</b> ke chat ini secara otomatis!\n\n"
        "🛡️ <b>KETENTUAN GARANSI & KENDALA:</b>\n"
        "• Seluruh akun dilindungi garansi resmi sesuai durasi paket.\n"
        "• Jika ada kendala, Anda dapat mengajukan klaim di menu <b>📜 Riwayat Pesanan</b> atau langsung hubungi <b>Admin Utama @dasrams</b>.\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <i>Sistem otomatis 24 Jam didukung penuh oleh @dasrams.</i>"
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
    text = (
        "💬 <b>PUSAT BANTUAN & CUSTOMER SERVICE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        "Mengalami kendala transaksi, pertanyaan stok, atau klaim garansi akun?\n\n"
        "👤 <b>Admin Utama & Owner:</b> @dasrams\n"
        "⚡ <b>Sistem Bot:</b> Otomatis 24 Jam Non-Stop\n"
        "⏰ <b>Respon CS Admin:</b> 08:00 – 23:00 WIB Setiap Hari\n\n"
        "📌 <b>Tips Cepat Dilayani:</b>\n"
        "Harap sertakan <b>No. Invoice</b> (contoh: <code>#AP-2026xxxx</code>) saat menghubungi admin agar kendala Anda dapat langsung dicek di database.\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        "🤝 <i>Aeternum PremiApp Bot — Kepuasan dan Keamanan Transaksi Anda adalah Prioritas Kami.</i>"
    )

    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()
