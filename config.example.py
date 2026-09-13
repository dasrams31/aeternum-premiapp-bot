import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str = "YOUR_TELEGRAM_BOT_TOKEN"
    ADMIN_ID: int = 606533609
    
    # Security: Database AES-256 Encryption Key
    ENCRYPTION_KEY: str = "AeternumSecretKey2026AES256SecureSalt"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/aeternum_premiapp_db"
    
    # Payment Gateway
    PAYMENT_GATEWAY: str = "tripay"
    GATEWAY_API_KEY: str = "YOUR_API_KEY"
    GATEWAY_PRIVATE_KEY: str = "YOUR_PRIVATE_KEY"
    GATEWAY_MERCHANT_CODE: str = "YOUR_MERCHANT_CODE"
    
    # Security: IP Whitelisting
    VERIFY_GATEWAY_IP: bool = False
    GATEWAY_ALLOWED_IPS: str = "103.150.190.1,103.150.190.2"

    # Channel Testimoni
    TESTIMONIAL_CHANNEL_ID: Optional[str] = "@AeternumTesti"

    # Webhook
    WEBHOOK_HOST: str = "https://yourdomain.com"
    WEBHOOK_PATH: str = "/webhook/payment"
    PORT: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()
