"""
Aeternum PremiApp Bot - Dynamic QRIS Engine (EMVCo & CRC16-CCITT)
Mendukung konversi QRIS Statis Merchant (GoPay / GoBiz / Bank) menjadi QRIS Dinamis
dengan injeksi nominal otomatis dan proteksi kode unik (Unique Amount).

QR yang dikirim ke pembeli dibungkus canvas gaya Peka (kuning/hitam/krem +
maskot Piko) di generate_qr_image_bytes. Modul QR-nya sendiri tidak disentuh:
tetap hitam di atas putih, ditempel pixel-perfect, jadi tetap ke-scan.
Kalau styling gagal karena alasan apa pun, fungsi jatuh kembali ke QR polos
supaya pembayaran tidak pernah rusak karena masalah tampilan.
"""

import io
import logging
import random
from pathlib import Path
from typing import Optional
import qrcode
from aiogram.types import BufferedInputFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Transaction

logger = logging.getLogger(__name__)

# Default raw static QRIS GoPay Merchant Aeternum
DEFAULT_STATIC_QRIS = (
    "00020101021126610014COM.GO-JEK.WWW01189360091433293320900210G3293320900303UMI"
    "51440014ID.CO.QRIS.WWW0215ID10265450816590303UMI5204899953033605802ID"
    "5925Aeternum Kreasikan Bersam6006SLEMAN61055558462140703A0111036216304D2F5"
)

# Aset gaya Peka (maskot + font Poppins) di-upload ke data/peka/.
_PEKA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "peka"


def crc16_ccitt(data: str) -> str:
    """
    Menghitung checksum CRC16-CCITT (Polynomial: 0x1021, Initial: 0xFFFF).
    Sesuai standar EMVCo QR Code Specification.
    """
    crc = 0xFFFF
    for ch in data:
        crc ^= ord(ch) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def make_dynamic_qris(amount: int, static_qris: Optional[str] = None) -> str:
    """
    Mengubah payload QRIS Statis menjadi QRIS Dinamis dengan menginjeksi:
    1. Tag 01 -> 12 (Point of Initiation Method: Dynamic)
    2. Tag 54 -> Transaction Amount
    3. Tag 63 -> Recalculated CRC16 Checksum
    """
    raw = static_qris or getattr(settings, "STATIC_QRIS_PAYLOAD", DEFAULT_STATIC_QRIS) or DEFAULT_STATIC_QRIS
    raw = raw.strip()

    # 1. Hapus Tag 63 lama (8 karakter terakhir: "6304XXXX")
    if len(raw) > 8 and raw[-8:-4] == "6304":
        base = raw[:-8]
    else:
        base = raw

    # 2. Ubah Tag 01 (Point of Initiation Method) dari 11 (statis) ke 12 (dinamis)
    if base.startswith("000201010211"):
        base = "000201010212" + base[12:]

    # 3. Format Tag 54 (Transaction Amount)
    amt_str = str(int(amount))
    tag54 = f"54{len(amt_str):02d}{amt_str}"

    # Sisipkan Tag 54 sebelum Tag 58 (Country Code '5802ID')
    pos_58 = base.find("5802")
    if pos_58 != -1:
        dynamic_payload = base[:pos_58] + tag54 + base[pos_58:]
    else:
        dynamic_payload = base + tag54

    # 4. Tambahkan header Tag 63 lalu hitung CRC16
    payload_to_sign = dynamic_payload + "6304"
    crc = crc16_ccitt(payload_to_sign)
    return payload_to_sign + crc


def _parse_qris_amount(payload: str) -> Optional[int]:
    """Baca tag 54 (transaction amount) dari payload EMVCo, kalau ada."""
    try:
        i = 0
        while i + 4 <= len(payload):
            tag = payload[i:i + 2]
            ln = int(payload[i + 2:i + 4])
            val = payload[i + 4:i + 4 + ln]
            if tag == "54":
                return int(val)
            i += 4 + ln
    except (ValueError, IndexError):
        return None
    return None


def _peka_font(name: str, size: int):
    """Font Poppins dari data/peka/fonts, jatuh ke DejaVu bila tidak ada."""
    from PIL import ImageFont

    for path in (
        _PEKA_DIR / "fonts" / name,
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _style_qr_canvas(qr_img, amount: Optional[int]):
    """Bungkus QR polos (PIL Image RGB) dalam canvas poster Peka 1080x1350.

    QR ditempel dengan NEAREST supaya modulnya pixel-perfect; kartu putih
    memberi quiet zone bersih. Nominal ditampilkan hanya kalau amount diketahui.
    """
    from PIL import Image, ImageDraw

    CREAM = (245, 241, 232)
    BLACK = (20, 18, 16)
    YELLOW = (255, 214, 10)
    MUTED = (120, 110, 95)
    WHITE = (255, 255, 255)
    SHADOW = (0, 0, 0, 60)

    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(canvas, "RGBA")

    def text_center(y, text, fnt, fill):
        w = draw.textlength(text, font=fnt)
        draw.text(((W - w) / 2, y), text, font=fnt, fill=fill)

    # Header band hitam + garis kuning.
    draw.rectangle([0, 0, W, 292], fill=BLACK)
    draw.rectangle([0, 292, W, 300], fill=YELLOW)
    text_center(42, "A E T E R N U M   P R E M I B O T",
                _peka_font("Poppins-SemiBold.ttf", 30), YELLOW)
    text_center(92, "SCAN BUAT BAYAR",
                _peka_font("Poppins-ExtraBold.ttf", 86), YELLOW)
    text_center(208, "Aeternum Kreasikan Bersama",
                _peka_font("Poppins-SemiBold.ttf", 40), (245, 241, 232))

    # Kartu QR putih + bayangan lembut.
    card = (140, 350, 940, 1180)
    draw.rounded_rectangle([card[0] + 10, card[1] + 12, card[2] + 10, card[3] + 12],
                           radius=36, fill=SHADOW)
    draw.rounded_rectangle(card, radius=36, fill=WHITE,
                           outline=(230, 222, 205), width=2)

    qr_side = 620
    qr_big = qr_img.resize((qr_side, qr_side), Image.NEAREST)
    qx = 230
    qy = 380 if amount is not None else 455
    canvas.paste(qr_big, (qx, qy))

    if amount is not None:
        text_center(1022, "Rp" + f"{int(amount):,}".replace(",", "."),
                    _peka_font("Poppins-ExtraBold.ttf", 66), BLACK)
        text_center(1112, "nominal + kode unik, beda tiap invoice",
                    _peka_font("Poppins-SemiBold.ttf", 28), MUTED)

    # Footer band hitam (cermin header) + garis kuning.
    draw.rectangle([0, 1196, W, 1202], fill=YELLOW)
    draw.rectangle([0, 1202, W, H], fill=BLACK)
    draw.text((60, 1255), "Bayar pakai QRIS apa saja",
              font=_peka_font("Poppins-Bold.ttf", 36), fill=YELLOW)

    # Lockup Piko + peka.ai.id, rata kanan (maskot tetap di data/peka/).
    mascot = Image.open(_PEKA_DIR / "mascot-p.png").convert("RGB")
    glyph = mascot.crop((440, 170, 750, 830))  # rapat di huruf P + antena
    glyph_h = 104
    glyph_w = round(glyph_h * glyph.width / glyph.height)
    glyph = glyph.resize((glyph_w, glyph_h), Image.LANCZOS)
    f_lockup = _peka_font("Poppins-Bold.ttf", 40)
    text_w = draw.textlength("peka.ai.id", font=f_lockup)
    gx = 1020 - (glyph_w + 16 + text_w)
    canvas.paste(glyph, (round(gx), 1224))
    draw.text((gx + glyph_w + 16, 1248), "peka.ai.id", font=f_lockup, fill=YELLOW)

    return canvas


def generate_qr_image_bytes(payload: str, amount: Optional[int] = None) -> io.BytesIO:
    """Menghasilkan buffer gambar PNG dari string QRIS, gaya Peka.

    amount: nominal rupiah untuk dicetak di bawah QR. Kalau None, dibaca dari
    tag 54 payload; kalau tidak ada juga, nominal tidak dicetak. Kalau styling
    gagal, jatuh kembali ke QR polos (perilaku lama) supaya pembayaran aman.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    plain_buf = io.BytesIO()
    img.save(plain_buf, format="PNG")
    plain_buf.seek(0)

    try:
        from PIL import Image

        qr_img = Image.open(plain_buf).convert("RGB")
        shown_amount = amount if amount is not None else _parse_qris_amount(payload)
        styled = _style_qr_canvas(qr_img, shown_amount)
        buf = io.BytesIO()
        styled.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception as e:
        logger.warning(f"Gagal styling QR Peka, pakai QR polos: {e}")
        plain_buf.seek(0)
        return plain_buf


def generate_qr_input_file(payload: str, filename: str = "qris_payment.png",
                           amount: Optional[int] = None) -> BufferedInputFile:
    """Menghasilkan BufferedInputFile untuk dikirim melalui aiogram."""
    buf = generate_qr_image_bytes(payload, amount=amount)
    return BufferedInputFile(buf.getvalue(), filename=filename)


async def find_available_unique_amount(
    session: AsyncSession,
    base_amount: int,
    min_code: int = 1,
    max_code: int = 499,
) -> int:
    """
    Menghitung nominal akhir dengan kode unik (base_amount + random code)
    dan memastikan tidak ada transaksi PENDING lain dengan nominal yang persis sama.
    """
    stmt = select(Transaction.amount).where(Transaction.status == "PENDING")
    res = await session.execute(stmt)
    pending_amounts = set(res.scalars().all())

    # Coba hingga 30 kali untuk mendapatkan kode unik bebas tabrakan
    for _ in range(30):
        unique_code = random.randint(min_code, max_code)
        target_amount = base_amount + unique_code
        if target_amount not in pending_amounts:
            return target_amount

    # Fallback deterministik jika rentang padat
    for code in range(min_code, max_code + 1):
        target_amount = base_amount + code
        if target_amount not in pending_amounts:
            return target_amount

    return base_amount
