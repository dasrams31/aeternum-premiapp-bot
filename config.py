import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "606533609"))

    # Database PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:password@localhost:5432/aeternum_premiapp_db",
    )

    # Payment Gateway
    PAYMENT_GATEWAY: str = os.getenv("PAYMENT_GATEWAY", "tripay")
    GATEWAY_API_KEY: str = os.getenv("GATEWAY_API_KEY", "")
    GATEWAY_PRIVATE_KEY: str = os.getenv("GATEWAY_PRIVATE_KEY", "")
    GATEWAY_MERCHANT_CODE: str = os.getenv("GATEWAY_MERCHANT_CODE", "")

    # Security: IP Whitelisting Webhook Gateway
    VERIFY_GATEWAY_IP: bool = os.getenv("VERIFY_GATEWAY_IP", "False").lower() in ("true", "1", "yes")
    # Daftar IP resmi gateway dipisahkan koma (Contoh: 103.150.190.1,103.150.190.2)
    GATEWAY_ALLOWED_IPS: str = os.getenv("GATEWAY_ALLOWED_IPS", "")

    # Channel Testimoni (Username @channel atau ID)
    TESTIMONIAL_CHANNEL_ID: Optional[str] = os.getenv("TESTIMONIAL_CHANNEL_ID", None)

    # Webhook
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "https://yourdomain.com")
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook/payment")
    PORT: int = int(os.getenv("PORT", "8000"))

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
