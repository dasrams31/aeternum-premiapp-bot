"""
Aeternum PremiApp Bot - Encryption at Rest (AES-256 Fernet)
Mengenkripsi data kredensial, lisensi, dan akun sebelum disimpan ke database PostgreSQL.
"""

import base64
import hashlib
import logging
from cryptography.fernet import Fernet, InvalidToken

from config import settings

logger = logging.getLogger(__name__)


def _get_fernet_key() -> bytes:
    """Menghasilkan kunci 32-byte urlsafe base64 dari ENCRYPTION_KEY config."""
    secret = settings.ENCRYPTION_KEY
    if not secret:
        # Fallback deterministik menggunakan Bot Token & Admin ID jika key belum diset
        secret = f"{settings.BOT_TOKEN}:{settings.ADMIN_ID}:aeternum_fallback_salt"

    # SHA256 digest menghasilkan 32 bytes
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_cipher = Fernet(_get_fernet_key())


def encrypt_text(plain_text: str) -> str:
    """Mengenkripsi teks biasa menjadi ciphertext AES-256 terenkripsi."""
    if not plain_text:
        return ""
    try:
        encrypted_bytes = _cipher.encrypt(plain_text.encode("utf-8"))
        return f"ENC::{encrypted_bytes.decode('utf-8')}"
    except Exception as e:
        logger.error(f"Gagal mengenkripsi teks: {e}")
        return plain_text


def decrypt_text(cipher_text: str) -> str:
    """Mendekripsi ciphertext AES-256 kembali menjadi teks asli."""
    if not cipher_text:
        return ""
    if not cipher_text.startswith("ENC::"):
        # Jika bukan ciphertext terenkripsi (misal data lama), kembalikan teks langsung
        return cipher_text

    try:
        raw_token = cipher_text.replace("ENC::", "", 1)
        decrypted_bytes = _cipher.decrypt(raw_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.error("Gagal mendekripsi teks: Invalid Token atau Kunci Enkripsi Berubah!")
        return "[Error: Gagal Mendekripsi Kredensial]"
    except Exception as e:
        logger.error(f"Error saat dekripsi: {e}")
        return cipher_text
