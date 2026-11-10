from __future__ import annotations

import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PREFIX = "enc:v1:"


@lru_cache(maxsize=4)
def _fernet(secret: str) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"smtp_message_field_v1",
        iterations=390_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))
    return Fernet(key)


class FieldCrypto:
    """Шифрование полей at-rest. В письме/чате всегда plaintext через decrypt()."""

    def __init__(self, secret: str) -> None:
        if not secret or not secret.strip():
            raise RuntimeError("DATA_ENCRYPTION_KEY is required")
        self.secret = secret.strip()
        self._f = _fernet(self.secret)

    def encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith(PREFIX):
            return value
        token = self._f.encrypt(value.encode("utf-8")).decode("ascii")
        return PREFIX + token

    def decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(PREFIX):
            # Старые plaintext-записи до шифрования
            return value
        token = value[len(PREFIX) :].encode("ascii")
        try:
            return self._f.decrypt(token).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Не удалось расшифровать поле — проверь DATA_ENCRYPTION_KEY") from exc

    def email_hash(self, email: str) -> str:
        normalized = email.lower().strip()
        return hmac.new(
            self.secret.encode("utf-8"),
            normalized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
