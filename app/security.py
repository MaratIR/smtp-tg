from __future__ import annotations

import re

# SMTP header injection: CR/LF и прочие control-символы в заголовках
_HEADER_FORBIDDEN_RE = re.compile(r"[\r\n\x00-\x1f\x7f]")
_TEXT_CONTROLS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9._%+-]{0,62}[a-z0-9])?@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$",
    re.IGNORECASE,
)

MAX_EMAIL_LEN = 254
MAX_SUBJECT_LEN = 200
MAX_NAME_LEN = 100
MAX_BODY_LEN = 8000
MAX_MESSAGE_ID_LEN = 200


class InjectionError(ValueError):
    pass


def _reject_header_injection(value: str, field: str) -> None:
    if _HEADER_FORBIDDEN_RE.search(value):
        raise InjectionError(f"запрещённые символы в {field}")


def sanitize_header(value: str, *, field: str, max_len: int) -> str:
    text = (value or "").strip()
    if not text:
        raise InjectionError(f"пустое значение {field}")
    _reject_header_injection(text, field)
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


def validate_email(value: str) -> str:
    text = (value or "").strip()
    _reject_header_injection(text, "email")
    if len(text) > MAX_EMAIL_LEN or not _EMAIL_RE.match(text):
        raise InjectionError("некорректный email")
    # отсечь очевидные header-injection маскировки
    if any(x in text for x in (":", ",", ";", '"', "<", ">", "\\")):
        raise InjectionError("некорректный email")
    return text.lower()


def sanitize_subject(value: str) -> str:
    return sanitize_header(value or "Telegram", field="subject", max_len=MAX_SUBJECT_LEN)


def sanitize_display_name(value: str) -> str:
    text = _TEXT_CONTROLS_RE.sub("", value or "").strip()
    text = text.replace("\r", " ").replace("\n", " ")
    if not text:
        return "Пользователь"
    return text[:MAX_NAME_LEN]


def sanitize_body(value: str) -> str:
    text = _TEXT_CONTROLS_RE.sub("", value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > MAX_BODY_LEN:
        text = text[:MAX_BODY_LEN].rstrip() + "\n…"
    return text.strip()


def sanitize_message_id(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    _reject_header_injection(text, "message-id")
    if len(text) > MAX_MESSAGE_ID_LEN:
        raise InjectionError("слишком длинный Message-ID")
    if not (text.startswith("<") and text.endswith(">")):
        raise InjectionError("некорректный Message-ID")
    return text
