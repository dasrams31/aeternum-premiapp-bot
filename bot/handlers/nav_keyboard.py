"""
Aeternum PremiApp Bot - Persistent navigation keyboard handlers.

Reply-keyboard buttons send their label as a plain text message. The
handlers here cover only the buttons that have no screen of their own yet
(Voucher, Informasi, Web Store). The other buttons (Katalog, Deposit,
Riwayat, Cara Pembelian, Afiliasi, Bantuan, Panel Admin) reuse the existing
callback handlers, which were made dual Message | CallbackQuery.

Every handler uses StateFilter(None): it only fires when the user has no
active FSM state, so a tap never hijacks an in-progress flow (promo code,
warranty claim, custom top-up amount, review comment, payment proof,
order chat).
"""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from bot.keyboards.user_kb import (
    NAV_INFO,
    NAV_VOUCHER,
    NAV_WEBSTORE,
    webstore_kb,
)

router = Router(name="nav_keyboard_router")

VOUCHER_TEXT = (
    "🎟️ <b>VOUCHER & KODE PROMO</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "Punya kode promo? Masukkan saat checkout: buka produk di <b>🛍️ Katalog Produk</b>, "
    "lalu tekan tombol <b>🎟️ Pakai Kode Diskon / Voucher</b> sebelum membayar.\n\n"
    "Diskon langsung memotong total bayar."
)

INFO_TEXT = (
    "ℹ️ <b>TENTANG AETERNUM PREMIAPP BOT</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "Bot belanja akun premium & produk digital otomatis 24 jam.\n\n"
    "💳 <b>Pembayaran:</b> QRIS Instan (BCA, Mandiri, BRI, BNI, GoPay, OVO, DANA, ShopeePay) & Saldo Dompet\n"
    "🚀 <b>Pengiriman:</b> Langsung ke chat ini setelah bayar\n"
    "🛡️ <b>Garansi:</b> Sesuai ketentuan tiap produk\n"
    "👑 <b>Owner & Admin:</b> @dasrams\n"
    "📣 <b>Channel:</b> @aeternum_premich"
)


@router.message(StateFilter(None), F.text == NAV_VOUCHER)
async def nav_voucher(message: Message) -> None:
    await message.answer(text=VOUCHER_TEXT, parse_mode="HTML")


@router.message(StateFilter(None), F.text == NAV_INFO)
async def nav_info(message: Message) -> None:
    await message.answer(text=INFO_TEXT, parse_mode="HTML")


@router.message(StateFilter(None), F.text == NAV_WEBSTORE)
async def nav_webstore(message: Message) -> None:
    await message.answer(
        text="🚀 <b>WEB STORE AETERNUM</b>\n\nBelanja lewat website di sini:",
        reply_markup=webstore_kb(),
        parse_mode="HTML",
    )
