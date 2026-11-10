import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    bot_token: str
    mongo_uri: str
    mongo_db: str
    mail_address: str
    mail_password: str
    smtp_username: str
    smtp_use_ssl: bool
    smtp_validate_certs: bool
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    mail_poll_interval: int
    data_encryption_key: str
    message_retention_hours: int


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    mail_address = os.getenv("MAIL_ADDRESS", "").strip()
    mail_password = os.getenv("MAIL_PASSWORD", "").strip()
    data_encryption_key = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    if not mail_address or not mail_password:
        raise RuntimeError("MAIL_ADDRESS and MAIL_PASSWORD are required")
    if not data_encryption_key:
        raise RuntimeError("DATA_ENCRYPTION_KEY is required")

    smtp_username = os.getenv("SMTP_USERNAME", mail_address).strip() or mail_address

    return Config(
        bot_token=bot_token,
        mongo_uri=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip(),
        mongo_db=os.getenv("MONGO_DB", "smtp_message").strip(),
        mail_address=mail_address,
        mail_password=mail_password,
        smtp_username=smtp_username,
        smtp_use_ssl=_as_bool(os.getenv("SMTP_USE_SSL"), default=True),
        # reg.ru часто отдаёт сертификат не на mail.домен — по умолчанию не валим коннект
        smtp_validate_certs=_as_bool(os.getenv("SMTP_VALIDATE_CERTS"), default=False),
        imap_host=os.getenv("IMAP_HOST", "mail.example.com").strip(),
        imap_port=int(os.getenv("IMAP_PORT", "993")),
        smtp_host=os.getenv("SMTP_HOST", "mail.example.com").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        mail_poll_interval=int(os.getenv("MAIL_POLL_INTERVAL", "30")),
        data_encryption_key=data_encryption_key,
        message_retention_hours=int(os.getenv("MESSAGE_RETENTION_HOURS", "72")),
    )
