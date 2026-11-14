"""
Aeternum PremiApp Bot - Start & General Handlers
"""

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.verification import (
    check_membership,
    mark_verified,
    verification_keyboard,
    verification_text,
)
from config import settings
from database import crud
from bot.handlers.catalog import render_product_detail
from bot.keyboards.user_kb import (
    NAV_HELP,
    NAV_HOW_TO_BUY,
    NAV_INTRO_TEXT,
    NAV_REFERRAL,
    back_to_main_kb,
    main_menu_kb,
    main_reply_kb,
    referral_menu_kb,
)

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

    # Gate verifikasi: user harus gabung channel + grup Peka + channel Aeternum dulu.
    # Admin lolos langsung; user yang sudah gabung ditandai terverifikasi.
    if not is_admin and not db_user.is_verified:
        in_channel, in_group, in_aeternum = await check_membership(bot, user.id)
        if in_channel and in_group and in_aeternum:
            await mark_verified(session, user.id)
        else:
            await message.answer(
                text=verification_text(not in_channel, not in_group, not in_aeternum),
                reply_markup=verification_keyboard(),
                parse_mode="HTML",
            )
            return

    # Deep-link dari broadcast: /start product_<id> (tombol Beli Sekarang)
    # atau /start remind_<id> (tombol pengingat di broadcast stok habis).
    # ref_<id> tetap ditangani seperti sebelumnya di atas.
    if len(args) > 1:
        arg = args[1]
        if arg.startswith("product_") or arg.startswith("remind_"):
            try:
                deep_pid = int(arg.split("_", 1)[1])
            except (ValueError, IndexError):
                deep_pid = None
            if deep_pid:
                if arg.startswith("remind_"):
                    product = await crud.get_product_by_id(
                        session=session, product_id=deep_pid
                    )
                    if product:
                        _ok, sub_msg = await crud.subscribe_restock_alert(
                            session=session, product_id=deep_pid, user_id=user.id
                        )
                        rendered = await render_product_detail(session, deep_pid, user.id)
                        if rendered:
                            dtext, dkb = rendered
                            await message.answer(
                                text=f"{sub_msg}\n\n{dtext}",
                                reply_markup=dkb,
                                parse_mode="HTML",
                            )
                            return
                else:
                    rendered = await render_product_detail(session, deep_pid, user.id)
                    if rendered:
                        dtext, dkb = rendered
                        await message.answer(
                            text=dtext, reply_markup=dkb, parse_mode="HTML"
                        )
                        return
                await message.answer(
                    "Produk tidak ditemukan.",
                    reply_markup=main_menu_kb(is_admin=is_admin),
                )
                return

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

    # Keyboard navigasi persisten: satu pesan tidak bisa membawa inline +
    # reply keyboard sekaligus, jadi keyboard dikirim sebagai pesan kedua.
    await message.answer(
        text=NAV_INTRO_TEXT,
        reply_markup=main_reply_kb(is_admin=is_admin),
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


@router.message(StateFilter(None), F.text == NAV_REFERRAL)
@router.callback_query(F.data == "user_referral")
async def cb_show_referral(
    event: Message | CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    user = event.from_user
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
        f"💰 <i>Saldo komisi tidak bisa ditarik tunai. Saldo dipakai otomatis sebagai <b>diskon 10%</b> di setiap pembelian produkmu.</i>"
    )

    if isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(
            text=text,
            reply_markup=referral_menu_kb(bot_username=bot_username, user_id=user.id),
            parse_mode="HTML",
        )
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(
            text=text,
            reply_markup=referral_menu_kb(bot_username=bot_username, user_id=user.id),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "user_withdraw_referral")
async def cb_withdraw_referral(callback: CallbackQuery, session: AsyncSession) -> None:
    """Penarikan tunai saldo komisi sudah tidak tersedia (aturan baru):
    saldo komisi hanya dipakai sebagai diskon 10% di tiap pembelian."""
    user = callback.from_user
    db_user = await crud.get_user_by_id(session=session, user_id=user.id)
    balance = float(db_user.referral_balance or 0.0) if db_user else 0.0
    text = (
        f"💳 <b>SALDO KOMISI TIDAK BISA DITARIK TUNAI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Saldo Komisi Anda:</b> <code>Rp {balance:,.0f}</code>\n\n"
        f"Saldo komisi tidak bisa dicairkan ke rekening / e-wallet. "
        f"Saldo dipakai <b>otomatis sebagai diskon 10%</b> di setiap pembelian produk "
        f"yang Anda lakukan di bot ini, selama saldo masih tersedia."
    ).replace(",", ".")
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(StateFilter(None), F.text == NAV_HOW_TO_BUY)
@router.callback_query(F.data == "user_how_to_buy")
async def cb_how_to_buy(event: Message | CallbackQuery) -> None:
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

    if isinstance(event, CallbackQuery) and event.message:
        await event.message.edit_text(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )


@router.message(StateFilter(None), F.text == NAV_HELP)
@router.callback_query(F.data == "user_help")
async def cb_help(event: Message | CallbackQuery) -> None:
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

    if isinstance(event, CallbackQuery) and event.message:
        if event.message.text:
            await event.message.edit_text(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        else:
            # Pesan media (mis. foto invoice QRIS) tidak punya teks:
            # edit_text gagal, kirim bantuan sebagai pesan baru.
            await event.message.answer(
                text=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML",
            )
        await event.answer()
    elif isinstance(event, Message):
        await event.answer(
            text=text,
            reply_markup=back_to_main_kb(),
            parse_mode="HTML",
        )
