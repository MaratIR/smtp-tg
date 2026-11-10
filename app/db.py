import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.crypto import FieldCrypto

EMAIL_CONFIRM_TTL_MINUTES = 15
MAX_EMAIL_RESENDS = 5


class Store:
    def __init__(
        self,
        uri: str,
        db_name: str,
        crypto: FieldCrypto,
        *,
        message_retention_hours: int = 72,
    ) -> None:
        self._client = MongoClient(uri)
        self._db: Database = self._client[db_name]
        self.users: Collection = self._db["users"]
        self.threads: Collection = self._db["threads"]
        self.email_pending: Collection = self._db["email_pending"]
        self.chats: Collection = self._db["chats"]
        self.crypto = crypto
        self.message_retention_hours = max(1, int(message_retention_hours))
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.users.create_index("tg_user_id", unique=True)
        self.users.create_index("email_hash", unique=True, sparse=True)
        self.users.create_index("username", sparse=True)
        self.chats.create_index("chat_id", unique=True)
        self.threads.create_index("email_message_id", unique=True, sparse=True)
        self.threads.create_index(
            [("tg_chat_id", ASCENDING), ("tg_message_id", ASCENDING)],
            unique=True,
        )
        self.email_pending.create_index("tg_user_id", unique=True)
        self.email_pending.create_index(
            "expires_at",
            expireAfterSeconds=0,
            name="expires_at_ttl",
        )
        self._ensure_thread_ttl()

    def _code_hash(self, tg_user_id: int, email: str, code: str) -> str:
        payload = f"{tg_user_id}:{email.lower().strip()}:{code.strip()}"
        return hmac.new(
            self.crypto.secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _ensure_thread_ttl(self) -> None:
        # Mongo сам чистит документы threads старше N часов по created_at
        seconds = self.message_retention_hours * 3600
        name = "created_at_ttl"
        for idx in self.threads.list_indexes():
            key = dict(idx.get("key") or {})
            if idx.get("name") == name or (list(key.keys()) == ["created_at"] and "expireAfterSeconds" in idx):
                if idx.get("expireAfterSeconds") == seconds:
                    return
                self.threads.drop_index(idx["name"])
                break
        self.threads.create_index(
            "created_at",
            expireAfterSeconds=seconds,
            name=name,
        )

    def _decode_user(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        out = dict(doc)
        if "email" in out:
            out["email"] = self.crypto.decrypt(out.get("email"))
        if "display_name" in out:
            out["display_name"] = self.crypto.decrypt(out.get("display_name"))
        return out

    def _decode_thread(self, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if not doc:
            return None
        out = dict(doc)
        if "to_email" in out:
            out["to_email"] = self.crypto.decrypt(out.get("to_email"))
        if "subject" in out:
            out["subject"] = self.crypto.decrypt(out.get("subject"))
        if "body" in out:
            out["body"] = self.crypto.decrypt(out.get("body"))
        return out

    def upsert_user(
        self,
        tg_user_id: int,
        *,
        email: str | None = None,
        username: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {"updated_at": now}
        if email is not None:
            normalized = email.lower().strip()
            update["email"] = self.crypto.encrypt(normalized)
            update["email_hash"] = self.crypto.email_hash(normalized)
            update["email_verified"] = True
        if username is not None:
            update["username"] = username.lower().lstrip("@") or None
        if display_name is not None:
            update["display_name"] = self.crypto.encrypt(display_name)

        self.users.update_one(
            {"tg_user_id": tg_user_id},
            {"$set": update, "$setOnInsert": {"created_at": now, "tg_user_id": tg_user_id}},
            upsert=True,
        )
        user = self._decode_user(self.users.find_one({"tg_user_id": tg_user_id}))
        assert user is not None
        return user

    def get_user_by_tg_id(self, tg_user_id: int) -> dict[str, Any] | None:
        return self._decode_user(self.users.find_one({"tg_user_id": tg_user_id}))

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self._decode_user(
            self.users.find_one({"username": username.lower().lstrip("@")})
        )

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized = email.lower().strip()
        doc = self.users.find_one({"email_hash": self.crypto.email_hash(normalized)})
        if doc:
            return self._decode_user(doc)
        # fallback: старые plaintext-записи
        return self._decode_user(self.users.find_one({"email": normalized}))

    def clear_email(self, tg_user_id: int) -> bool:
        result = self.users.update_one(
            {"tg_user_id": tg_user_id},
            {
                "$unset": {"email": "", "email_hash": "", "email_verified": ""},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )
        return result.matched_count > 0

    def delete_user(self, tg_user_id: int) -> bool:
        self.email_pending.delete_one({"tg_user_id": tg_user_id})
        result = self.users.delete_one({"tg_user_id": tg_user_id})
        return result.deleted_count > 0

    def set_email_pending(self, tg_user_id: int, email: str, code: str) -> None:
        normalized = email.lower().strip()
        now = datetime.now(timezone.utc)
        self.email_pending.update_one(
            {"tg_user_id": tg_user_id},
            {
                "$set": {
                    "tg_user_id": tg_user_id,
                    "email": self.crypto.encrypt(normalized),
                    "email_hash": self.crypto.email_hash(normalized),
                    "code_hash": self._code_hash(tg_user_id, normalized, code),
                    "resend_count": 0,
                    "created_at": now,
                    "expires_at": now + timedelta(minutes=EMAIL_CONFIRM_TTL_MINUTES),
                }
            },
            upsert=True,
        )

    def resend_email_pending(
        self, tg_user_id: int, code: str
    ) -> tuple[str | None, str | None]:
        """
        Новый код + +1 к resend_count.
        Returns: (email, error) где error: None | "missing" | "limit"
        """
        pending = self.get_email_pending(tg_user_id)
        if not pending or not pending.get("email"):
            return None, "missing"
        if int(pending.get("resend_count") or 0) >= MAX_EMAIL_RESENDS:
            return None, "limit"

        email = str(pending["email"])
        normalized = email.lower().strip()
        now = datetime.now(timezone.utc)
        self.email_pending.update_one(
            {"tg_user_id": tg_user_id},
            {
                "$set": {
                    "code_hash": self._code_hash(tg_user_id, normalized, code),
                    "expires_at": now + timedelta(minutes=EMAIL_CONFIRM_TTL_MINUTES),
                },
                "$inc": {"resend_count": 1},
            },
        )
        return email, None

    def get_email_pending(self, tg_user_id: int) -> dict[str, Any] | None:
        doc = self.email_pending.find_one({"tg_user_id": tg_user_id})
        if not doc:
            return None
        expires = doc.get("expires_at")
        if expires is not None:
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                self.email_pending.delete_one({"tg_user_id": tg_user_id})
                return None
        out = dict(doc)
        out["email"] = self.crypto.decrypt(out.get("email"))
        return out

    def confirm_email_pending(self, tg_user_id: int, code: str) -> str | None:
        pending = self.get_email_pending(tg_user_id)
        if not pending or not pending.get("email"):
            return None
        expected = pending.get("code_hash")
        got = self._code_hash(tg_user_id, pending["email"], code)
        if not expected or not hmac.compare_digest(str(expected), got):
            return None
        self.email_pending.delete_one({"tg_user_id": tg_user_id})
        return str(pending["email"])

    def clear_email_pending(self, tg_user_id: int) -> None:
        self.email_pending.delete_one({"tg_user_id": tg_user_id})

    def set_chat_lang(self, chat_id: int, lang: str) -> None:
        now = datetime.now(timezone.utc)
        self.chats.update_one(
            {"chat_id": chat_id},
            {
                "$set": {"lang": lang, "updated_at": now},
                "$setOnInsert": {"created_at": now, "chat_id": chat_id},
            },
            upsert=True,
        )

    def get_chat_lang(self, chat_id: int) -> str:
        doc = self.chats.find_one({"chat_id": chat_id})
        if not doc:
            return "en"
        lang = str(doc.get("lang") or "en").lower()
        return lang if lang in {"en", "ru"} else "en"

    def create_thread(
        self,
        *,
        email_message_id: str,
        tg_chat_id: int,
        tg_message_id: int,
        to_email: str,
        to_tg_user_id: int | None,
        subject: str,
        body: str | None = None,
    ) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "email_message_id": email_message_id,
            "tg_chat_id": tg_chat_id,
            "tg_message_id": tg_message_id,
            "to_email": self.crypto.encrypt(to_email.lower().strip()),
            "to_tg_user_id": to_tg_user_id,
            "subject": self.crypto.encrypt(subject),
            "created_at": datetime.now(timezone.utc),
        }
        if body is not None:
            doc["body"] = self.crypto.encrypt(body)
        self.threads.insert_one(doc)
        return self._decode_thread(doc)  # type: ignore[return-value]

    def get_thread_by_tg_message(
        self, tg_chat_id: int, tg_message_id: int
    ) -> dict[str, Any] | None:
        return self._decode_thread(
            self.threads.find_one(
                {"tg_chat_id": tg_chat_id, "tg_message_id": tg_message_id}
            )
        )

    def get_thread_by_email_message_id(
        self, email_message_id: str
    ) -> dict[str, Any] | None:
        return self._decode_thread(
            self.threads.find_one({"email_message_id": email_message_id})
        )

    def close(self) -> None:
        self._client.close()
