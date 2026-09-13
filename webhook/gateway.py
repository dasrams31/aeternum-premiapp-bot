"""
Aeternum PremiApp Bot - Payment Gateway Integration
Mendukung pembuatan transaksi QRIS Dinamis dan verifikasi signature Webhook.
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, Optional
import httpx

from config import settings

logger = logging.getLogger(__name__)


class TripayGateway:
    """Client integrasi Payment Gateway Tripay (Closed Payment / QRIS Dinamis)."""

    def __init__(self) -> None:
        self.api_key = settings.GATEWAY_API_KEY
        self.private_key = settings.GATEWAY_PRIVATE_KEY
        self.merchant_code = settings.GATEWAY_MERCHANT_CODE
        # URL Endpoint Tripay (Sandbox / Production)
        self.base_url = "https://tripay.co.id/api-sandbox" if "sandbox" in self.api_key.lower() else "https://tripay.co.id/api"

    def create_signature(self, merchant_ref: str, amount: int) -> str:
        """Menghasilkan signature SHA256 HMAC untuk request transaksi."""
        payload = f"{self.merchant_code}{merchant_ref}{amount}"
        return hmac.new(
            self.private_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_webhook_signature(self, json_data: str, received_signature: str) -> bool:
        """Memverifikasi keaslian callback webhook dari Tripay."""
        expected_signature = hmac.new(
            self.private_key.encode("utf-8"),
            json_data.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected_signature, received_signature)

    async def create_qris_transaction(
        self,
        merchant_ref: str,
        amount: int,
        customer_name: str,
        customer_email: str = "customer@aeternum.local",
        order_items: Optional[list] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Memanggil API Tripay untuk membuat transaksi QRIS Dinamis.
        """
        if not self.api_key or not self.private_key:
            logger.warning("Tripay credentials belum diatur. Menggunakan mode QRIS simulasi.")
            return None

        url = f"{self.base_url}/transaction/create"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        signature = self.create_signature(merchant_ref, amount)

        payload = {
            "method": "QRIS2",  # Atau QRIS / QRIS_DANA
            "merchant_ref": merchant_ref,
            "amount": amount,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "order_items": order_items or [
                {"name": f"Produk Digital ({merchant_ref})", "price": amount, "quantity": 1}
            ],
            "callback_url": f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}",
            "expired_time": int((httpx._utils.get_environment_proxies() or 0)) + (15 * 60), # 15 menit
            "signature": signature,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                data = response.json()
                if response.status_code == 200 and data.get("success"):
                    return data.get("data")
                else:
                    logger.error(f"Tripay Error ({response.status_code}): {data}")
                    return None
        except Exception as e:
            logger.exception(f"Gagal request QRIS Tripay: {e}")
            return None


class PakasirGateway:
    """Client integrasi Payment Gateway Pakasir (QRIS Dinamis)."""

    def __init__(self) -> None:
        self.api_key = settings.GATEWAY_API_KEY
        self.base_url = "https://api.pakasir.com/v1"

    async def create_qris_transaction(
        self,
        order_id: str,
        amount: int,
    ) -> Optional[Dict[str, Any]]:
        """Membuat invoice QRIS Pakasir."""
        if not self.api_key:
            return None

        url = f"{self.base_url}/order/create"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "order_id": order_id,
            "amount": amount,
            "callback_url": f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get("status") == "success":
                    return data.get("data")
                return None
        except Exception as e:
            logger.exception(f"Gagal request QRIS Pakasir: {e}")
            return None


# Gateway Selector
def get_payment_gateway():
    if settings.PAYMENT_GATEWAY.lower() == "pakasir":
        return PakasirGateway()
    return TripayGateway()
