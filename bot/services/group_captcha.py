"""
Aeternum PremiApp Bot - verifikasi anti-bot untuk member baru grup Peka.

Alur (perintah user 21 Nov 2026, diubah jadi soal matematika):
- Member baru masuk grup Peka -> langsung di-restrict (tidak bisa chat)
  dan menerima pesan verifikasi berisi soal penjumlahan atau perkalian
  dengan 4 pilihan jawaban berupa tombol.
- Klik jawaban benar -> restrict dibuka, pesan verifikasi dihapus,
  pesan "Verifikasi berhasil" dikirim lalu dihapus setelah 5 detik.
- Klik jawaban salah -> soal baru dibuat (pesan diedit), kesempatan
  berkurang. Maksimal 3 kali salah: pesan dihapus, user tetap
  dibisukan selamanya.
- Pesan verifikasi hilang sendiri dalam 5 menit. Bila sampai 5 menit
  tidak dijawab, pesan dihapus dan user tetap dibisukan selamanya
  (perintah user 21 Nov 2026: jangan dikeluarkan). Jalan keluarnya:
  keluar lalu masuk lagi, soal baru dikirim.

Hanya berlaku di grup Peka. Admin/creator yang bergabung tidak kena
captcha (status mereka "administrator", bukan "member"). Member lama
tidak terpengaruh.

Pending verifikasi disimpan juga di data/group_captcha_pending.json
supaya bila bot restart di tengah jendela 5 menit, timeout tetap
dihidupkan lagi saat start (restore_pending_captchas).
"""

import asyncio
import html
import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Tuple

from aiogram import Bot
from aiogram.types import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

CAPTCHA_TIMEOUT_S = 300  # 5 menit: pesan permintaan verifikasi hilang
CONFIRMED_DELETE_S = 5  # pesan "terkonfirmasi" hilang setelah 5 detik
MAX_WRONG_ATTEMPTS = 3  # 3 kali salah -> pesan dihapus, tetap dibisukan

PENDING_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "group_captcha_pending.json"
)

# (chat_id, user_id) -> {"message_id": int, "deadline": float,
#   "task": asyncio.Task, "correct": int, "attempts": int,
#   "first_name": str}
_PENDING: Dict[Tuple[int, int], dict] = {}
# (chat_id, user_id) -> verified_at epoch; supaya klik kedua tidak
# dibilang "sudah tidak berlaku" padahal sudah terverifikasi.
_VERIFIED: Dict[Tuple[int, int], float] = {}
_VERIFIED_TTL_S = 600


def _restrict_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )


async def _default_member_permissions(bot: Bot, chat_id: int) -> ChatPermissions:
    """Izin default member grup (dipakai untuk membuka restrict)."""
    try:
        chat = await bot.get_chat(chat_id)
        if chat.permissions is not None:
            return chat.permissions
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal baca izin default grup %s: %s", chat_id, exc)
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=False,
        can_invite_users=True,
        can_pin_messages=False,
        can_manage_topics=False,
    )


def _prune_verified() -> None:
    now = time.time()
    stale = [k for k, v in _VERIFIED.items() if now - v >= _VERIFIED_TTL_S]
    for key in stale:
        _VERIFIED.pop(key, None)


def _make_question() -> Tuple[str, int, List[int]]:
    """Soal acak: penjumlahan atau perkalian + 4 pilihan jawaban."""
    if random.random() < 0.5:
        a = random.randint(3, 25)
        b = random.randint(3, 25)
        question = f"Berapa {a} + {b}?"
        correct = a + b
    else:
        a = random.randint(2, 9)
        b = random.randint(2, 9)
        question = f"Berapa {a} × {b}?"
        correct = a * b
    options = {correct}
    while len(options) < 4:
        delta = random.choice([-10, -5, -3, -2, -1, 1, 2, 3, 5, 10])
        candidate = correct + delta
        if candidate > 0:
            options.add(candidate)
    options_list = list(options)
    random.shuffle(options_list)
    return question, correct, options_list


def _options_keyboard(user_id: int, options: List[int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=str(options[0]),
                    callback_data=f"captcha:{user_id}:{options[0]}",
                ),
                InlineKeyboardButton(
                    text=str(options[1]),
                    callback_data=f"captcha:{user_id}:{options[1]}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=str(options[2]),
                    callback_data=f"captcha:{user_id}:{options[2]}",
                ),
                InlineKeyboardButton(
                    text=str(options[3]),
                    callback_data=f"captcha:{user_id}:{options[3]}",
                ),
            ],
        ]
    )


def _captcha_text(
    user_id: int, first_name: str, question: str, attempts_left: int, wrong: bool
) -> str:
    name = html.escape(first_name or "teman baru")
    head = (
        f"Halo <a href=\"tg://user?id={user_id}\">{name}</a>, "
        "selamat datang di grup Peka.\n\n"
    )
    if wrong:
        head += f"Salah. Coba soal baru ini, sisa {attempts_left} kesempatan:\n\n"
    else:
        head += "Sebelum bisa chat di sini, jawab soal ini:\n\n"
    return (
        head
        + f"<b>{question}</b>\n\n"
        + "Pesan ini hilang dalam 5 menit. Kalau tidak dijawab, kamu "
        "dibisukan selamanya. Keluar lalu masuk lagi kalau mau coba "
        "verifikasi ulang."
    )


def _load_pending_file() -> dict:
    try:
        return json.loads(PENDING_FILE.read_text())
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tidak bisa baca %s: %s", PENDING_FILE, exc)
        return {}


def _save_pending_file() -> None:
    try:
        PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            f"{chat_id}:{user_id}": {
                "message_id": entry["message_id"],
                "deadline": entry["deadline"],
                "correct": entry["correct"],
                "attempts": entry["attempts"],
            }
            for (chat_id, user_id), entry in _PENDING.items()
        }
        PENDING_FILE.write_text(json.dumps(data))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tidak bisa tulis %s: %s", PENDING_FILE, exc)


async def _delete_message(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:  # noqa: BLE001 - pesan mungkin sudah dihapus
        logger.debug("Gagal hapus pesan %s di %s: %s", message_id, chat_id, exc)


async def _delete_after(bot: Bot, chat_id: int, message_id: int, delay: float) -> None:
    await asyncio.sleep(delay)
    await _delete_message(bot, chat_id, message_id)


async def _timeout_worker(bot: Bot, chat_id: int, user_id: int) -> None:
    """Tunggu sampai deadline: hapus pesan verifikasi, user tetap bisu."""
    entry = _PENDING.get((chat_id, user_id))
    if entry is None:
        return
    delay = max(0.0, entry["deadline"] - time.time())
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    entry = _PENDING.pop((chat_id, user_id), None)
    if entry is None:
        return
    _save_pending_file()
    await _delete_message(bot, chat_id, entry["message_id"])
    logger.info(
        "Captcha timeout: user %s tetap dibisukan di grup %s "
        "(tidak verifikasi dalam 5 menit)",
        user_id,
        chat_id,
    )


async def start_captcha(bot: Bot, chat_id: int, user_id: int, first_name: str) -> bool:
    """Restrict member baru + kirim soal matematika. Tidak pernah raise."""
    _prune_verified()
    key = (chat_id, user_id)
    old = _PENDING.pop(key, None)
    if old is not None:
        task = old.get("task")
        if task is not None:
            task.cancel()
        await _delete_message(bot, chat_id, old["message_id"])
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id, permissions=_restrict_permissions()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal restrict user %s di %s: %s", user_id, chat_id, exc)
        return False
    question, correct, options = _make_question()
    text = _captcha_text(
        user_id, first_name, question, MAX_WRONG_ATTEMPTS, wrong=False
    )
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=_options_keyboard(user_id, options),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal kirim soal captcha ke %s: %s", chat_id, exc)
        return False
    deadline = time.time() + CAPTCHA_TIMEOUT_S
    _PENDING[key] = {
        "message_id": sent.message_id,
        "deadline": deadline,
        "task": asyncio.create_task(_timeout_worker(bot, chat_id, user_id)),
        "correct": correct,
        "attempts": 0,
        "first_name": first_name,
    }
    _save_pending_file()
    logger.info(
        "Captcha matematika dikirim: user %s grup %s msg %s soal %s",
        user_id,
        chat_id,
        sent.message_id,
        question,
    )
    return True


async def verify_captcha(bot: Bot, chat_id: int, user_id: int, choice: int) -> str:
    """Proses klik jawaban. Return: ok | wrong | failed | expired | already."""
    _prune_verified()
    key = (chat_id, user_id)
    if key in _VERIFIED:
        return "already"
    entry = _PENDING.get(key)
    if entry is None or "correct" not in entry:
        return "expired"
    if choice == entry["correct"]:
        _PENDING.pop(key, None)
        task = entry.get("task")
        if task is not None:
            task.cancel()
        _save_pending_file()
        try:
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=await _default_member_permissions(bot, chat_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Gagal buka restrict user %s di %s: %s", user_id, chat_id, exc
            )
            return "expired"
        _VERIFIED[key] = time.time()
        await _delete_message(bot, chat_id, entry["message_id"])
        try:
            sent = await bot.send_message(
                chat_id=chat_id,
                text="Verifikasi berhasil. Selamat datang di grup Peka!",
            )
            asyncio.create_task(
                _delete_after(bot, chat_id, sent.message_id, CONFIRMED_DELETE_S)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gagal kirim pesan konfirmasi ke %s: %s", chat_id, exc)
        logger.info("Captcha terverifikasi: user %s grup %s", user_id, chat_id)
        return "ok"
    entry["attempts"] = entry.get("attempts", 0) + 1
    if entry["attempts"] >= MAX_WRONG_ATTEMPTS:
        _PENDING.pop(key, None)
        task = entry.get("task")
        if task is not None:
            task.cancel()
        _save_pending_file()
        await _delete_message(bot, chat_id, entry["message_id"])
        logger.info(
            "Captcha gagal: user %s tetap dibisukan di grup %s "
            "(3 jawaban salah)",
            user_id,
            chat_id,
        )
        return "failed"
    question, correct, options = _make_question()
    entry["correct"] = correct
    _save_pending_file()
    attempts_left = MAX_WRONG_ATTEMPTS - entry["attempts"]
    text = _captcha_text(
        user_id,
        entry.get("first_name", "teman baru"),
        question,
        attempts_left,
        wrong=True,
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=entry["message_id"],
            text=text,
            reply_markup=_options_keyboard(user_id, options),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal edit soal captcha di %s: %s", chat_id, exc)
    return "wrong"


async def cancel_captcha(bot: Bot, chat_id: int, user_id: int) -> None:
    """User keluar sebelum verifikasi: batalkan timeout + hapus pesan."""
    key = (chat_id, user_id)
    entry = _PENDING.pop(key, None)
    if entry is None:
        return
    task = entry.get("task")
    if task is not None:
        task.cancel()
    _save_pending_file()
    await _delete_message(bot, chat_id, entry["message_id"])
    logger.info("Captcha dibatalkan: user %s keluar dari grup %s", user_id, chat_id)


async def restore_pending_captchas(bot: Bot) -> None:
    """Hidupkan lagi timeout untuk pending yang tersimpan (habis restart)."""
    stored = _load_pending_file()
    now = time.time()
    for raw_key, item in stored.items():
        try:
            chat_id, user_id = (int(x) for x in raw_key.split(":", 1))
            message_id = int(item["message_id"])
            deadline = float(item["deadline"])
            correct = int(item["correct"])
            attempts = int(item.get("attempts", 0))
        except (ValueError, KeyError, TypeError):
            # Entri format lama (tombol "Saya bukan robot", tanpa jawaban):
            # hapus pesannya, user tetap bisu dan bisa masuk lagi.
            try:
                chat_id, user_id = (int(x) for x in raw_key.split(":", 1))
                await _delete_message(bot, chat_id, int(item["message_id"]))
            except (ValueError, KeyError, TypeError):
                pass
            continue
        if deadline <= now:
            # Sudah lewat deadline saat bot start: hapus pesan saja,
            # user tetap dibisukan (tidak dikeluarkan).
            await _delete_message(bot, chat_id, message_id)
            continue
        _PENDING[(chat_id, user_id)] = {
            "message_id": message_id,
            "deadline": deadline,
            "task": asyncio.create_task(_timeout_worker(bot, chat_id, user_id)),
            "correct": correct,
            "attempts": attempts,
            "first_name": "teman baru",
        }
    _save_pending_file()
    if _PENDING:
        logger.info("Captcha dipulihkan: %d pending", len(_PENDING))
