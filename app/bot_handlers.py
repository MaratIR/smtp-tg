from __future__ import annotations

import secrets
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType, MessageEntityType
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from app.db import EMAIL_CONFIRM_TTL_MINUTES, MAX_EMAIL_RESENDS, Store
from app.i18n import DEFAULT_LANG, SUPPORTED_LANGS, t
from app.mail import MailService, has_mail_it, strip_mail_it, strip_reply_tail
from app.security import (
    InjectionError,
    sanitize_body,
    sanitize_display_name,
    sanitize_subject,
    validate_email,
)

router = Router()

RESEND_CODE_CB = "resend_email_code"


def _lang_from_user(user: User | None) -> str:
    raw = (user.language_code or "").lower().strip() if user else ""
    if not raw:
        return DEFAULT_LANG
    primary = raw.split("-", 1)[0]
    return primary if primary in SUPPORTED_LANGS else DEFAULT_LANG


def chat_lang(
    store: Store, message: Message, user: User | None = None
) -> str:
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return store.get_chat_lang(message.chat.id)
    return _lang_from_user(user or message.from_user)


def resend_code_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("resend_btn", lang),
                    callback_data=RESEND_CODE_CB,
                )
            ]
        ]
    )


async def _resend_verification_code(
    *,
    tg_user_id: int,
    store: Store,
    mail: MailService,
    lang: str,
) -> tuple[str, bool]:
    user = store.get_user_by_tg_id(tg_user_id)
    if user and user.get("email") and user.get("email_verified"):
        return t("resend_already_verified", lang), False

    code = f"{secrets.randbelow(1_000_000):06d}"
    email_addr, err = store.resend_email_pending(tg_user_id, code)
    if err == "missing":
        return t("resend_missing", lang), False
    if err == "limit":
        return t("resend_blocked", lang), False

    assert email_addr is not None
    try:
        await mail.send_verification_code(to_email=email_addr, code=code, lang=lang)
    except Exception as exc:
        return t("email_send_failed", lang, exc=exc), True

    pending = store.get_email_pending(tg_user_id)
    used = int((pending or {}).get("resend_count") or 0)
    left = max(0, MAX_EMAIL_RESENDS - used)
    return t("resend_ok", lang, left=left), left > 0


def display_name(user: User | dict[str, Any] | None, lang: str = DEFAULT_LANG) -> str:
    if user is None:
        return t("user_fallback", lang)
    if isinstance(user, dict):
        raw = user.get("display_name") or user.get("username") or str(user.get("tg_user_id"))
        return sanitize_display_name(str(raw))
    full = " ".join(x for x in [user.first_name, user.last_name] if x).strip()
    return sanitize_display_name(full or user.username or str(user.id))


def _message_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


def media_kind_key(message: Message) -> str | None:
    if message.photo:
        return "media_photo"
    if message.animation:
        return "media_gif"
    if message.video:
        return "media_video"
    if message.voice:
        return "media_voice"
    if message.video_note:
        return "media_video_note"
    if message.audio:
        return "media_audio"
    if message.sticker:
        return "media_sticker"
    if message.document:
        return "media_file"
    return None


def compose_bridge_body(message: Message, lang: str) -> str | None:
    kind_key = media_kind_key(message)
    raw = _message_text(message)
    parts: list[str] = []
    if kind_key:
        parts.append(t("media_sent", lang, kind=t(kind_key, lang)))
    if raw:
        parts.append(raw)
    if not parts:
        return None
    return "\n".join(parts)


def tg_message_link(message: Message) -> str | None:
    chat = message.chat
    if chat.username:
        return f"https://t.me/{chat.username}/{message.message_id}"
    chat_id = str(chat.id)
    if chat_id.startswith("-100"):
        return f"https://t.me/c/{chat_id[4:]}/{message.message_id}"
    return None


class HasMailTagFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return has_mail_it(message.text or "") or has_mail_it(message.caption or "")


def _mention_targets(message: Message) -> list[tuple[int | None, str | None]]:
    targets: list[tuple[int | None, str | None]] = []
    text = message.text or message.caption
    entities = message.entities or message.caption_entities
    if not entities or not text:
        return targets
    for ent in entities:
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
            targets.append((ent.user.id, ent.user.username))
        elif ent.type == MessageEntityType.MENTION:
            username = text[ent.offset : ent.offset + ent.length].lstrip("@")
            targets.append((None, username))
    return targets


async def _parse_group_lang_command(message: Message, bot: Bot) -> str | None:
    """@bot ru|en — returns lang code or None."""
    text = message.text
    if not text or not message.entities:
        return None
    me = await bot.get_me()
    bot_mentioned = False
    for ent in message.entities:
        if ent.type == MessageEntityType.TEXT_MENTION and ent.user and ent.user.id == me.id:
            bot_mentioned = True
        elif ent.type == MessageEntityType.MENTION:
            uname = text[ent.offset : ent.offset + ent.length].lstrip("@").lower()
            if me.username and uname == me.username.lower():
                bot_mentioned = True
    if not bot_mentioned:
        return None

    leftovers: list[str] = []
    for word in text.split():
        if me.username and word.lower() in {f"@{me.username.lower()}", me.username.lower()}:
            continue
        leftovers.append(word)
    if len(leftovers) != 1:
        return None
    lang = leftovers[0].lower().strip()
    return lang if lang in SUPPORTED_LANGS else None


async def _is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


@router.message(Command("start"))
async def cmd_start(message: Message, store: Store) -> None:
    lang = chat_lang(store, message)
    if message.from_user:
        store.upsert_user(
            message.from_user.id,
            username=message.from_user.username,
            display_name=display_name(message.from_user, lang),
        )
    await message.answer(t("start", lang))


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, store: Store) -> None:
    await message.answer(t("privacy", chat_lang(store, message)))


@router.message(Command("email"))
async def cmd_email(
    message: Message, command: CommandObject, store: Store, mail: MailService
) -> None:
    if not message.from_user:
        return
    lang = chat_lang(store, message)
    arg = (command.args or "").strip()
    try:
        email_addr = validate_email(arg)
    except InjectionError:
        await message.answer(t("email_usage", lang))
        return
    existing = store.get_user_by_email(email_addr)
    if existing and existing.get("tg_user_id") != message.from_user.id:
        await message.answer(t("email_taken", lang))
        return

    store.upsert_user(
        message.from_user.id,
        username=message.from_user.username,
        display_name=display_name(message.from_user, lang),
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    store.set_email_pending(message.from_user.id, email_addr, code)
    try:
        await mail.send_verification_code(to_email=email_addr, code=code, lang=lang)
    except Exception as exc:
        store.clear_email_pending(message.from_user.id)
        await message.answer(t("email_send_failed", lang, exc=exc))
        return

    await message.answer(
        t("email_code_sent", lang, minutes=EMAIL_CONFIRM_TTL_MINUTES),
        reply_markup=resend_code_keyboard(lang),
    )


@router.message(Command("resend_code"))
async def cmd_resend_code(
    message: Message, store: Store, mail: MailService
) -> None:
    if not message.from_user:
        return
    lang = chat_lang(store, message)
    text, show_kb = await _resend_verification_code(
        tg_user_id=message.from_user.id,
        store=store,
        mail=mail,
        lang=lang,
    )
    await message.answer(
        text,
        reply_markup=resend_code_keyboard(lang) if show_kb else None,
    )


@router.callback_query(F.data == RESEND_CODE_CB)
async def on_resend_code(
    callback: CallbackQuery, store: Store, mail: MailService
) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    if callback.message:
        lang = chat_lang(store, callback.message, callback.from_user)
    else:
        lang = _lang_from_user(callback.from_user)
    text, show_kb = await _resend_verification_code(
        tg_user_id=callback.from_user.id,
        store=store,
        mail=mail,
        lang=lang,
    )
    blocked = t("resend_blocked", lang)
    missing = t("resend_missing", lang)
    already = t("resend_already_verified", lang)
    if text == missing:
        await callback.answer(missing[:200], show_alert=True)
        return
    if text in {blocked, already}:
        await callback.answer(text[:200], show_alert=True)
        if callback.message:
            await callback.message.answer(text)
        return
    await callback.answer(t("resend_cb_ok", lang))
    if callback.message:
        await callback.message.answer(
            text,
            reply_markup=resend_code_keyboard(lang) if show_kb else None,
        )


@router.message(Command("confirm"))
async def cmd_confirm(message: Message, command: CommandObject, store: Store) -> None:
    if not message.from_user:
        return
    lang = chat_lang(store, message)
    code = (command.args or "").strip()
    if not code.isdigit() or len(code) != 6:
        await message.answer(t("confirm_usage", lang))
        return

    email_addr = store.confirm_email_pending(message.from_user.id, code)
    if not email_addr:
        await message.answer(t("confirm_bad", lang))
        return

    existing = store.get_user_by_email(email_addr)
    if existing and existing.get("tg_user_id") != message.from_user.id:
        await message.answer(t("email_taken", lang))
        return

    store.upsert_user(
        message.from_user.id,
        email=email_addr,
        username=message.from_user.username,
        display_name=display_name(message.from_user, lang),
    )
    await message.answer(t("confirm_ok", lang, email=email_addr))


@router.message(Command("delemail"))
async def cmd_delemail(message: Message, store: Store) -> None:
    if not message.from_user:
        return
    lang = chat_lang(store, message)
    store.clear_email_pending(message.from_user.id)
    if store.clear_email(message.from_user.id):
        await message.answer(t("delemail_ok", lang))
    else:
        await message.answer(t("delemail_missing", lang))


@router.message(Command("stop"))
async def cmd_stop(message: Message, store: Store) -> None:
    if not message.from_user:
        return
    lang = chat_lang(store, message)
    store.delete_user(message.from_user.id)
    await message.answer(t("stop_ok", lang))


@router.message(Command("whoami"))
async def cmd_whoami(message: Message, store: Store) -> None:
    if not message.from_user:
        return
    lang = chat_lang(store, message)
    user = store.get_user_by_tg_id(message.from_user.id)
    if not user:
        await message.answer(t("whoami_missing", lang))
        return
    email = user.get("email") or t("none_email", lang)
    verified = t("yes", lang) if user.get("email_verified") else t("no", lang)
    await message.answer(
        t("whoami", lang, tg_id=message.from_user.id, email=email, verified=verified)
    )


class GroupLangFilter(Filter):
    """Только `@bot ru|en`, иначе не перехватываем апдейт."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return False
        if has_mail_it(message.text or ""):
            return False
        return await _parse_group_lang_command(message, bot) is not None


@router.message(GroupLangFilter())
async def on_group_lang(message: Message, store: Store, bot: Bot) -> None:
    if not message.from_user:
        return
    lang_code = await _parse_group_lang_command(message, bot)
    if not lang_code:
        return
    current = store.get_chat_lang(message.chat.id)
    if not await _is_chat_admin(bot, message.chat.id, message.from_user.id):
        await message.reply(t("lang_admin_only", current))
        return
    store.set_chat_lang(message.chat.id, lang_code)
    await message.reply(t("lang_set", lang_code))


@router.message(F.reply_to_message, ~HasMailTagFilter())
async def on_reply_to_bridge(message: Message, store: Store, mail: MailService) -> None:
    if not message.reply_to_message:
        return
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.PRIVATE}:
        return

    lang = chat_lang(store, message)
    composed = compose_bridge_body(message, lang)
    if not composed:
        return

    thread = store.get_thread_by_tg_message(
        message.chat.id, message.reply_to_message.message_id
    )
    if not thread:
        return

    if (
        message.from_user
        and thread.get("to_tg_user_id") is not None
        and message.from_user.id == thread.get("to_tg_user_id")
    ):
        return

    try:
        to_email = validate_email(thread["to_email"])
        subject = sanitize_subject(thread.get("subject") or "Telegram")
        if not subject.lower().startswith("re:"):
            subject = sanitize_subject(f"Re: {subject}")
        body = sanitize_body(composed)
        link = tg_message_link(message)
        if link:
            body = sanitize_body(f"{body}\n\n{t('email_footer_link', lang, link=link)}")
        message_id = await mail.send(
            to_email=to_email,
            subject=subject,
            body=body,
            in_reply_to=thread["email_message_id"],
            references=thread["email_message_id"],
        )
    except InjectionError:
        await message.reply(t("rejected_security", lang))
        return
    except Exception as exc:
        await message.reply(t("mail_send_failed", lang, exc=exc))
        return

    await message.reply(t("mail_sent", lang))
    store.create_thread(
        email_message_id=message_id,
        tg_chat_id=message.chat.id,
        tg_message_id=message.message_id,
        to_email=to_email,
        to_tg_user_id=thread.get("to_tg_user_id"),
        subject=subject,
        body=body,
    )


@router.message(HasMailTagFilter())
async def on_mail_it(message: Message, store: Store, mail: MailService) -> None:
    lang = chat_lang(store, message)
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer(t("mail_it_groups_only", lang))
        return
    if not message.from_user:
        return

    store.upsert_user(
        message.from_user.id,
        username=message.from_user.username,
        display_name=display_name(message.from_user, lang),
    )

    targets = _mention_targets(message)
    if not targets:
        await message.reply(t("mail_it_need_mention", lang))
        return

    recipient: dict[str, Any] | None = None
    entities = message.entities or message.caption_entities or []
    for tg_id, username in targets:
        candidate = None
        if tg_id is not None:
            if tg_id == message.from_user.id:
                continue
            candidate = store.get_user_by_tg_id(tg_id)
            if candidate is None:
                mentioned = next(
                    (
                        e.user
                        for e in entities
                        if e.type == MessageEntityType.TEXT_MENTION
                        and e.user
                        and e.user.id == tg_id
                    ),
                    None,
                )
                candidate = store.upsert_user(
                    tg_id,
                    username=username or (mentioned.username if mentioned else None),
                    display_name=display_name(mentioned, lang) if mentioned else username,
                )
        elif username:
            me = (message.from_user.username or "").lower()
            if username.lower() == me:
                continue
            candidate = store.get_user_by_username(username)

        if candidate is not None:
            recipient = candidate
            break

    if recipient is None:
        await message.reply(t("mail_it_user_not_found", lang))
        return

    email_addr = recipient.get("email")
    name = display_name(recipient, lang)
    if not email_addr or not recipient.get("email_verified"):
        await message.reply(t("mail_it_no_verified", lang, name=name))
        return

    composed = compose_bridge_body(message, lang)
    if not composed:
        return

    try:
        email_addr = validate_email(email_addr)
        body = sanitize_body(strip_mail_it(composed))
        chat_title = sanitize_display_name(str(message.chat.title or message.chat.id))
        subject = sanitize_subject(t("subject_from_tg", lang, chat=chat_title))
        link = tg_message_link(message)
        footer = (
            f"\n\n---\n{t('email_footer_from', lang, name=display_name(message.from_user, lang))}"
            f"\n{t('email_footer_chat', lang, chat=chat_title)}"
        )
        if link:
            footer += f"\n{t('email_footer_link', lang, link=link)}"
        footer += f"\n{t('email_footer_reply', lang)}"
        message_id = await mail.send(
            to_email=email_addr,
            subject=subject,
            body=sanitize_body(f"{body}{footer}"),
        )
    except InjectionError:
        await message.reply(t("rejected_security", lang))
        return
    except Exception as exc:
        await message.reply(t("mail_send_failed", lang, exc=exc))
        return

    await message.reply(t("mail_sent", lang))
    store.create_thread(
        email_message_id=message_id,
        tg_chat_id=message.chat.id,
        tg_message_id=message.message_id,
        to_email=email_addr,
        to_tg_user_id=recipient.get("tg_user_id"),
        subject=subject,
        body=body,
    )


async def handle_incoming_mail(
    item,
    *,
    bot: Bot,
    store: Store,
    mail: MailService,
) -> None:
    thread = None
    candidates = []
    if item.in_reply_to:
        candidates.append(item.in_reply_to)
    candidates.extend(item.references or [])

    for mid in candidates:
        thread = store.get_thread_by_email_message_id(mid)
        if thread:
            break

    if thread is None:
        await mail.send_instruction_reply(
            to_email=item.from_email,
            original_subject=item.subject,
            in_reply_to=item.message_id,
            lang=DEFAULT_LANG,
        )
        return

    lang = store.get_chat_lang(thread["tg_chat_id"])
    user = store.get_user_by_email(item.from_email)
    name = (
        display_name(user, lang)
        if user
        else sanitize_display_name(item.from_email)
    )
    body = sanitize_body(strip_reply_tail(item.body))
    text = t("replied", lang, name=name, body=body)
    sent = await bot.send_message(
        chat_id=thread["tg_chat_id"],
        text=text,
        reply_to_message_id=thread["tg_message_id"],
    )
    store.create_thread(
        email_message_id=item.message_id,
        tg_chat_id=sent.chat.id,
        tg_message_id=sent.message_id,
        to_email=item.from_email,
        to_tg_user_id=(user or {}).get("tg_user_id"),
        subject=item.subject or thread.get("subject") or "Telegram",
        body=body,
    )
