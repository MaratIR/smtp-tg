from __future__ import annotations

import asyncio
import email
import imaplib
import re
import ssl
import uuid
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr
from typing import Callable, Awaitable

import aiosmtplib

from app.config import Config
from app.i18n import t
from app.security import (
    sanitize_body,
    sanitize_message_id,
    sanitize_subject,
    validate_email,
)

# Допускаем пробелы внутри скобок: [мыльни], [ мыльни ]
MAIL_IT_RE = re.compile(r"\[\s*(?:mail_it|мыльни)\s*\]", re.IGNORECASE | re.UNICODE)
ANGLE_ID_RE = re.compile(r"<[^>]+>")


@dataclass
class IncomingMail:
    message_id: str
    in_reply_to: str | None
    references: list[str]
    from_email: str
    subject: str
    body: str
    uid: str


def strip_mail_it(text: str) -> str:
    return MAIL_IT_RE.sub("", text).strip()


def has_mail_it(text: str) -> bool:
    return bool(MAIL_IT_RE.search(text or ""))


# Заголовки цитаты Gmail/клиентов + строки с >
_QUOTE_HEADER_RE = re.compile(
    r"^(?:"
    r"On .+ wrote:\s*"
    r"|[-_]{2,}\s*Original Message\s*[-_]{2,}\s*"
    r"|.+<[^>]+@[^>]+>\s*:\s*"
    r"|From:\s*.+"
    r"|От:\s*.+"
    r")$",
    re.IGNORECASE,
)


def strip_reply_tail(text: str) -> str:
    """Оставляет только новый текст ответа, без процитированного хвоста."""
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cut_at: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            cut_at = i
            break
        if _QUOTE_HEADER_RE.match(stripped):
            cut_at = i
            break
        # Наш разделитель в исходящих письмах, если клиент не поставил >
        if stripped == "---" and i + 1 < len(lines) and lines[i + 1].strip().startswith("От:"):
            cut_at = i
            break
    if cut_at is not None:
        # Убрать пустые строки перед цитатой
        while cut_at > 0 and not lines[cut_at - 1].strip():
            cut_at -= 1
        lines = lines[:cut_at]
    return "\n".join(lines).strip()


def normalize_message_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    match = ANGLE_ID_RE.search(value)
    if match:
        return match.group(0)
    if value.startswith("<") and value.endswith(">"):
        return value
    return f"<{value}>"


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    return str(make_header(decode_header(raw)))


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace").strip()
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip()


def _extract_from_email(msg: email.message.Message) -> str:
    raw = msg.get("From", "")
    parsed = email.utils.parseaddr(raw)[1]
    return parsed.lower().strip()


class MailService:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _make_message_id(self) -> str:
        domain = self.config.mail_address.split("@", 1)[-1]
        return f"<{uuid.uuid4()}@{domain}>"

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> str:
        to_email = validate_email(to_email)
        subject = sanitize_subject(subject)
        body = sanitize_body(body)
        in_reply_to = sanitize_message_id(in_reply_to)
        references = sanitize_message_id(references) if references else in_reply_to

        message_id = self._make_message_id()
        msg = EmailMessage()
        msg["From"] = formataddr(("TG Mail Bridge", self.config.mail_address))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references or in_reply_to
        msg.set_content(body)

        use_tls = self.config.smtp_use_ssl or self.config.smtp_port == 465
        await aiosmtplib.send(
            msg,
            hostname=self.config.smtp_host,
            port=self.config.smtp_port,
            username=self.config.smtp_username,
            password=self.config.mail_password,
            use_tls=use_tls,
            start_tls=not use_tls,
            validate_certs=self.config.smtp_validate_certs,
        )
        return message_id

    async def send_verification_code(
        self, *, to_email: str, code: str, lang: str | None = None
    ) -> str:
        return await self.send(
            to_email=to_email,
            subject=t("verify_subject", lang),
            body=t("verify_body", lang, code=code),
        )

    async def send_instruction_reply(
        self,
        *,
        to_email: str,
        original_subject: str,
        in_reply_to: str | None,
        lang: str | None = None,
    ) -> str:
        subject = (
            original_subject
            if original_subject.lower().startswith("re:")
            else f"Re: {original_subject or 'Telegram'}"
        )
        return await self.send(
            to_email=to_email,
            subject=subject,
            body=t("instruction_body", lang),
            in_reply_to=in_reply_to,
            references=in_reply_to,
        )

    def _imap_ssl_context(self) -> ssl.SSLContext:
        if self.config.smtp_validate_certs:
            return ssl.create_default_context()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _fetch_unseen_sync(self) -> list[IncomingMail]:
        results: list[IncomingMail] = []
        mail = imaplib.IMAP4_SSL(
            self.config.imap_host,
            self.config.imap_port,
            ssl_context=self._imap_ssl_context(),
        )
        try:
            mail.login(self.config.smtp_username, self.config.mail_password)
            mail.select("INBOX")
            status, data = mail.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return results

            for uid in data[0].split():
                status, msg_data = mail.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not isinstance(raw, (bytes, bytearray)):
                    continue
                msg = email.message_from_bytes(raw)
                message_id = normalize_message_id(msg.get("Message-ID"))
                if not message_id:
                    continue
                in_reply_to = normalize_message_id(msg.get("In-Reply-To"))
                refs_raw = msg.get("References", "") or ""
                references = [
                    rid for rid in (normalize_message_id(x) for x in refs_raw.split()) if rid
                ]
                results.append(
                    IncomingMail(
                        message_id=message_id,
                        in_reply_to=in_reply_to,
                        references=references,
                        from_email=_extract_from_email(msg),
                        subject=_decode_header_value(msg.get("Subject")),
                        body=_extract_body(msg),
                        uid=uid.decode() if isinstance(uid, bytes) else str(uid),
                    )
                )
        finally:
            try:
                mail.logout()
            except Exception:
                pass
        return results

    async def fetch_unseen(self) -> list[IncomingMail]:
        return await asyncio.to_thread(self._fetch_unseen_sync)


async def mail_poll_loop(
    mail: MailService,
    interval: int,
    on_mail: Callable[[IncomingMail], Awaitable[None]],
) -> None:
    while True:
        try:
            for item in await mail.fetch_unseen():
                await on_mail(item)
        except Exception:
            # Ошибки почты не роняют бота; следующий тик попробует снова.
            pass
        await asyncio.sleep(interval)
