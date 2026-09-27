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


class KlikQRISGateway:
    """
    Client resmi Payment Gateway KlikQRIS (https://klikqris.com/dokumentasi).
    Mendukung pembuatan QRIS Dinamis instan, cek status pembayaran real-time, dan verifikasi callback.
    """

    def __init__(self) -> None:
        self.api_key = (
            getattr(settings, "KLIKQRIS_API_KEY", "")
            or settings.GATEWAY_API_KEY
            or "rAqu7TOfO43WrZC1WFVF7fNqGQGlIAr0UvR0k6pg"
        )
        self.merchant_id = (
            getattr(settings, "KLIKQRIS_MERCHANT_ID", "")
            or settings.GATEWAY_MERCHANT_CODE
            or "179046112227"
        )
        self.base_url = (
            getattr(settings, "KLIKQRIS_BASE_URL", "")
            or "https://klikqris.com/api"
        ).rstrip("/")

    def verify_webhook_signature(
        self,
        json_data: str = "",
        received_signature: str = "",
        *args,
        **kwargs,
    ) -> bool:
        """Verifikasi signature callback KlikQRIS jika disediakan."""
        if not self.api_key or not received_signature:
            return True
        try:
            expected = hmac.new(
                self.api_key.encode("utf-8"),
                json_data.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, received_signature)
        except Exception:
            return True

    async def create_qris_transaction(
        self,
        merchant_ref: str,
        amount: int,
        customer_name: str = "Customer",
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Membuat transaksi QRIS Dinamis melalui API KlikQRIS (POST /api/qris/create).
        """
        if not self.api_key or not self.merchant_id:
            logger.warning("KlikQRIS API Key atau Merchant ID belum diatur.")
            return None

        url = f"{self.base_url}/qris/create"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "id_merchant": str(self.merchant_id),
            "User-Agent": "Aeternum-PremiApp/1.0",
        }

        payload = {
            "order_id": merchant_ref,
            "amount": int(amount),
            "id_merchant": str(self.merchant_id),
            "keterangan": description or f"Pesanan #{merchant_ref} - Aeternum PremiApp",
            "redirect_url": "https://t.me/aeternum_premibot",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                data = res.json()
                if res.status_code in [200, 201] and data.get("status"):
                    res_data = data.get("data", {})
                    logger.info(f"KlikQRIS QRIS dibuat: Order ID {res_data.get('order_id')}")

                    total_amount = float(res_data.get("total_amount") or res_data.get("amount") or amount)
                    raw_amount = float(res_data.get("amount") or amount)
                    amount_uniq = float(res_data.get("amount_uniq") or 0.0)

                    return {
                        "invoice_id": res_data.get("order_id") or merchant_ref,
                        "qris_string": "",
                        "qris_image": res_data.get("qris_image"),
                        "qris_url": res_data.get("qris_url"),
                        "amount": total_amount,
                        "raw_amount": raw_amount,
                        "amount_uniq": amount_uniq,
                        "payment_url": res_data.get("report_url") or res_data.get("qris_url"),
                        "method": "klikqris",
                        "signature": res_data.get("signature"),
                    }
                else:
                    logger.error(f"Gagal create payment KlikQRIS ({res.status_code}): {data}")
                    return None
        except Exception as e:
            logger.exception(f"Exception saat request KlikQRIS create: {e}")
            return None

    async def check_payment_status(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """
        Mengecek status pembayaran live ke server KlikQRIS (GET /api/qris/status/{order_id}).
        """
        if not self.api_key or not self.merchant_id or not invoice_id:
            return None

        url = f"{self.base_url}/qris/status/{invoice_id}"
        headers = {
            "x-api-key": self.api_key,
            "id_merchant": str(self.merchant_id),
            "User-Agent": "Aeternum-PremiApp/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get("status"):
                    res_data = data.get("data", {})
                    raw_status = (res_data.get("status") or "").upper()
                    return {
                        "status": raw_status,
                        "invoice_id": res_data.get("order_id") or invoice_id,
                        "amount": res_data.get("amount"),
                        "total_amount": res_data.get("total_amount"),
                        "paid_at": res_data.get("paid_at"),
                        "success": True,
                    }
                return None
        except Exception as e:
            logger.error(f"Error check payment KlikQRIS: {e}")
            return None


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

    async def create_qris_transaction(
        self,
        merchant_ref: str,
        amount: int,
        customer_name: str = "Customer",
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
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


class NirvaPayGateway:
    """
    Client resmi NirvaPay SaaS Payment Gateway (https://nirvapay.dasrams.biz.id).
    Mendukung dynamic QRIS EMVCo injection, instant auto-settlement, dan multi-wallet polling.
    """

    def __init__(self) -> None:
        self.base_url = (getattr(settings, "NIRVAPAY_BASE_URL", "") or "https://nirvapay.dasrams.biz.id").rstrip("/")
        self.secret_key = getattr(settings, "NIRVAPAY_SECRET_KEY", "")

    def verify_webhook_signature(self, *args, **kwargs) -> bool:
        return True

    async def create_qris_transaction(
        self,
        merchant_ref: str,
        amount: int,
        customer_name: str = "Customer",
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/invoices"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "amount": float(amount),
            "merchant_ref": merchant_ref,
            "customer_name": customer_name,
            "description": description or f"Pesanan #{merchant_ref}",
            "payment_channel": "QRIS",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get("success"):
                    inv = data.get("invoice", {})
                    return {
                        "invoice_id": inv.get("invoice_id"),
                        "qris_string": inv.get("qris_payload"),
                        "amount": inv.get("total_amount"),
                        "payment_url": f"{self.base_url}{inv.get('payment_url')}",
                        "method": "nirvapay_qris",
                    }
                else:
                    logger.error(f"NirvaPay create invoice error ({res.status_code}): {data}")
                    return None
        except Exception as e:
            logger.exception(f"Exception connecting to NirvaPay: {e}")
            return None

    async def check_payment_status(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/invoices/{invoice_id}/status"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "status": data.get("status"),
                        "invoice_id": data.get("invoice_id"),
                        "paid_at": data.get("paid_at"),
                    }
                return None
        except Exception as e:
            logger.warning(f"Error checking status with NirvaPay: {e}")
            return None


class GoPayDirectGateway:
    """
    Direct Merchant QRIS GoPay Engine dengan kalkulasi dynamic EMVCo & CRC16.
    Tidak memerlukan API pihak ketiga; nominal diinjeksi langsung ke raw QRIS payload.
    """

    def __init__(self) -> None:
        self.static_payload = getattr(settings, "STATIC_QRIS_PAYLOAD", "")

    def verify_webhook_signature(self, *args, **kwargs) -> bool:
        return True

    async def create_qris_transaction(
        self,
        merchant_ref: str,
        amount: int,
        customer_name: str = "Customer",
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        from bot.services.qris import make_dynamic_qris
        dynamic_payload = make_dynamic_qris(amount=int(amount), static_qris=self.static_payload)
        return {
            "invoice_id": merchant_ref,
            "qris_string": dynamic_payload,
            "amount": amount,
            "payment_url": None,
            "method": "gopay_qris",
        }

    async def check_payment_status(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        return None


def get_payment_gateway():
    gw = (settings.PAYMENT_GATEWAY or "klikqris").lower()
    if gw in ["klikqris", "klik_qris", "klik"]:
        return KlikQRISGateway()
    elif gw in ["nirvapay", "nirva", "nirva_pay"]:
        return NirvaPayGateway()
    elif gw in ["bayargg", "bayar_gg", "bayar"]:
        return BayarGGGateway()
    elif gw in ["tripay"]:
        return TripayGateway()
    return GoPayDirectGateway()
