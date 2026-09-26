"""
Aeternum PremiApp Bot - Dynamic QRIS Engine (EMVCo & CRC16-CCITT)
Mendukung konversi QRIS Statis Merchant (GoPay / GoBiz / Bank) menjadi QRIS Dinamis
dengan injeksi nominal otomatis dan proteksi kode unik (Unique Amount).
"""

import io
import logging
import random
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


def generate_qr_image_bytes(payload: str) -> io.BytesIO:
    """Menghasilkan buffer gambar PNG dari string QRIS."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_qr_input_file(payload: str, filename: str = "qris_payment.png") -> BufferedInputFile:
    """Menghasilkan BufferedInputFile untuk dikirim melalui aiogram."""
    buf = generate_qr_image_bytes(payload)
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
