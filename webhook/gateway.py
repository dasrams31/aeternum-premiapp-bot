"""
Aeternum PremiApp Bot - Payment Gateway Integration
Mendukung integrasi resmi BAYAR GG (QRIS Dinamis API), Tripay, dan Pakasir.
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, Optional
import httpx

from config import settings

logger = logging.getLogger(__name__)


class BayarGGGateway:
    """
    Client resmi Payment Gateway BAYAR GG (https://www.bayar.gg/api-docs)
    Mendukung pembuatan QRIS Dinamis instan, cek status pembayaran, dan verifikasi webhook.
    """

    def __init__(self) -> None:
        self.api_key = settings.GATEWAY_API_KEY
        self.webhook_secret = settings.GATEWAY_PRIVATE_KEY # Webhook secret key whsec_xxx
        self.base_url = "https://www.bayar.gg/api"

    def verify_webhook_signature(
        self,
        invoice_id: str,
        status: str,
        final_amount: Any,
        timestamp: Any,
        received_signature: str,
    ) -> bool:
        """
        Verifikasi signature callback Webhook BAYAR GG:
        $signatureData = $payload['invoice_id'] . '|' . $payload['status'] . '|' . $payload['final_amount'] . '|' . $timestamp;
        hash_hmac('sha256', $signatureData, 'YOUR_WEBHOOK_SECRET');
        """
        if not self.webhook_secret:
            return True # Jika secret belum diset di .env, izinkan dengan verifikasi invoice_id

        signature_data = f"{invoice_id}|{status}|{final_amount}|{timestamp}"
        expected_signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            signature_data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected_signature, received_signature)

    async def create_qris_transaction(
        self,
        merchant_ref: str,
        amount: int,
        customer_name: str = "Customer",
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Membuat transaksi QRIS Dinamis melalui API BAYAR GG.
        """
        if not self.api_key:
            logger.warning("BAYAR GG API Key belum diatur.")
            return None

        url = f"{self.base_url}/create-payment.php"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

        payload = {
            "amount": int(amount),
            "description": description or f"Pesanan #{merchant_ref} - Aeternum Store",
            "customer_name": customer_name,
            "payment_url": "https://www.bayar.gg/pay",
            "payment_method": "qris",
        }

        # Hanya sertakan callback_url jika menggunakan protokol HTTPS valid
        if settings.WEBHOOK_HOST and settings.WEBHOOK_HOST.startswith("https://"):
            payload["callback_url"] = f"{settings.WEBHOOK_HOST.rstrip('/')}{settings.WEBHOOK_PATH}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get("success"):
                    logger.info(f"BAYAR GG QRIS dibuat: Invoice {data['data'].get('invoice_id')}")
                    return data.get("data")
                else:
                    logger.error(f"Gagal create payment BAYAR GG ({res.status_code}): {data}")
                    return None
        except Exception as e:
            logger.exception(f"Exception saat request BAYAR GG: {e}")
            return None

    async def check_payment_status(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """
        Mengecek status pembayaran live ke server BAYAR GG.
        """
        if not self.api_key or not invoice_id:
            return None

        url = f"{self.base_url}/check-payment.php?invoice={invoice_id}"
        headers = {"X-API-Key": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get("success"):
                    return data
                return None
        except Exception as e:
            logger.error(f"Error check payment BAYAR GG: {e}")
            return None


class TripayGateway:
    def __init__(self) -> None:
        self.api_key = settings.GATEWAY_API_KEY
        self.private_key = settings.GATEWAY_PRIVATE_KEY
        self.merchant_code = settings.GATEWAY_MERCHANT_CODE
        self.base_url = "https://tripay.co.id/api-sandbox" if "sandbox" in self.api_key.lower() else "https://tripay.co.id/api"

    def verify_webhook_signature(self, json_data: str, received_signature: str) -> bool:
        if not self.private_key:
            return True
        expected_signature = hmac.new(
            self.private_key.encode("utf-8"),
            json_data.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected_signature, received_signature)

    async def check_payment_status(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        url = f"{self.base_url}/transaction/detail?reference={invoice_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get("success"):
                    return data.get("data")
                return None
        except Exception:
            return None
        if not self.api_key or not self.private_key:
            return None

        url = f"{self.base_url}/transaction/create"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "method": "QRIS2",
            "merchant_ref": merchant_ref,
            "amount": amount,
            "customer_name": customer_name,
            "order_items": [{"name": f"Produk ({merchant_ref})", "price": amount, "quantity": 1}],
            "callback_url": f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                data = response.json()
                if response.status_code == 200 and data.get("success"):
                    return data.get("data")
                return None
        except Exception as e:
            logger.exception(f"Tripay error: {e}")
            return None


def get_payment_gateway():
    gw = settings.PAYMENT_GATEWAY.lower()
    if gw in ["bayargg", "bayar_gg", "bayar"]:
        return BayarGGGateway()
    return TripayGateway()
