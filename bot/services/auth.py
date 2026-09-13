"""
Aeternum PremiApp Bot - Telegram WebApp initData Signature Validator
Memvalidasi keaslian data sesi Telegram Mini App menggunakan HMAC-SHA256 bot token.
"""

import hashlib
import hmac
import json
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from config import settings


def validate_telegram_init_data(init_data: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Memvalidasi Telegram WebApp initData string:
    1. Parsing query string
    2. Menghitung data_check_string
    3. Membandingkan hash HMAC-SHA256 terhadap secret_key (b"WebAppData", BOT_TOKEN)
    Returns: (is_valid, user_data_dict)
    """
    if not init_data or not settings.BOT_TOKEN:
        return False, None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return False, None

        # Urutkan key alfabetis
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # Secret key = HMAC_SHA256("WebAppData", BOT_TOKEN)
        secret_key = hmac.new(
            b"WebAppData",
            settings.BOT_TOKEN.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        # Calculated hash = HMAC_SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(calculated_hash, received_hash):
            user_raw = parsed.get("user")
            user_data = json.loads(user_raw) if user_raw else {}
            return True, user_data

        return False, None
    except Exception:
        return False, None
