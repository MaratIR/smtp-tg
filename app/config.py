import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    mongo_uri: str
    mongo_db: str
    mail_address: str
    mail_password: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    mail_poll_interval: int


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    mail_address = os.getenv("MAIL_ADDRESS", "").strip()
    mail_password = os.getenv("MAIL_PASSWORD", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    if not mail_address or not mail_password:
        raise RuntimeError("MAIL_ADDRESS and MAIL_PASSWORD are required")

    return Config(
        bot_token=bot_token,
        mongo_uri=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017").strip(),
        mongo_db=os.getenv("MONGO_DB", "smtp_message").strip(),
        mail_address=mail_address,
        mail_password=mail_password,
        imap_host=os.getenv("IMAP_HOST", "imap.gmail.com").strip(),
        imap_port=int(os.getenv("IMAP_PORT", "993")),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        mail_poll_interval=int(os.getenv("MAIL_POLL_INTERVAL", "30")),
    )
