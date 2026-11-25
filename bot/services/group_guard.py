"""Guard menu privat di grup (aturan terkunci 25 Nov 2026, perintah user).

Menu yang menampilkan data pribadi (saldo, riwayat + isi akun yang sudah
dibeli, afiliasi) dan semua langkah pembayaran HANYA boleh dibuka di DM
bot. Lihat-lihat katalog di grup tetap boleh.

Handler privat memanggil deny_group_private() di baris pertama: bila
event berasal dari grup/supergrup, pesan grup diganti pengalihan ke DM
dan handler berhenti sebelum data apa pun dibaca atau ditampilkan.
"""
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

BOT_DM_URL = "https://t.me/aeternum_premibot"


def is_group_chat(message: Message | None) -> bool:
    return bool(message) and message.chat.type in ("group", "supergroup")


async def deny_group_private(event: Message | CallbackQuery) -> bool:
    """True bila event berasal dari grup: pengalihan ke DM dikirim,
    pemanggil harus berhenti (return). False bila di DM: lanjut normal."""
    message = event.message if isinstance(event, CallbackQuery) else event
    if not is_group_chat(message):
        return False
    text = (
        "Menu ini hanya tersedia di DM bot.\n\n"
        "Ketuk tombol di bawah untuk buka DM bot, lalu pilih menu yang sama di sana."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Buka DM Bot", url=BOT_DM_URL)]
        ]
    )
    try:
        if isinstance(event, CallbackQuery) and event.message:
            await event.message.edit_text(text=text, reply_markup=kb)
            await event.answer(
                "Menu ini hanya bisa dibuka di DM bot.", show_alert=True
            )
        else:
            await event.answer(text=text, reply_markup=kb)
    except Exception:
        pass
    return True
