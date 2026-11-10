from __future__ import annotations

DEFAULT_LANG = "en"
SUPPORTED_LANGS = frozenset({"en", "ru"})

_TEXTS: dict[str, dict[str, str]] = {
    "start": {
        "en": (
            "Email ↔ Telegram bridge bot.\n\n"
            "Link email: /email you@example.com\n"
            "Confirm code: /confirm 123456\n"
            "Resend code: /resend_code (max 5)\n"
            "Remove email: /delemail\n"
            "Show binding: /whoami\n"
            "Stop: /stop\n"
            "Privacy: /privacy\n\n"
            "In a group: mention a user and add [mail_it] or [мыльни] — the bot sends email.\n"
            "Email replies appear in chat; reply in TG goes back to email "
            "(except when the recipient replies to their own bridged message).\n\n"
            "Group language (admins): mention the bot and write the code, e.g.\n"
            "@email_itbot ru — Russian\n"
            "@email_itbot en — English (default)\n"
            "This applies to bot replies and outbound emails in that group."
        ),
        "ru": (
            "Бот-мост email ↔ Telegram.\n\n"
            "Привязать почту: /email you@example.com\n"
            "Подтвердить код: /confirm 123456\n"
            "Отправить код снова: /resend_code (макс. 5)\n"
            "Удалить почту: /delemail\n"
            "Привязка: /whoami\n"
            "Стоп: /stop\n"
            "Конфиденциальность: /privacy\n\n"
            "В группе: тегни человека и добавь [mail_it] или [мыльни] — бот отправит письмо.\n"
            "Ответ на письмо попадёт в чат; reply уйдёт обратно на почту "
            "(кроме случая, когда адресат отвечает на свой же bridged-ответ).\n\n"
            "Язык группы (админы): тегни бота и напиши код, например\n"
            "@email_itbot ru — русский\n"
            "@email_itbot en — английский (по умолчанию)\n"
            "Так бот отвечает и оформляет письма в этой группе."
        ),
    },
    "privacy": {
        "en": (
            "Privacy\n\n"
            "This bot helps you stay reachable (e.g. when VPN/Telegram access is unstable) "
            "via an email ↔ Telegram bridge.\n"
            "We do not collect extra data: essentially only the Telegram ID ↔ email binding "
            "(plus temporary delivery threads for replies).\n"
            "Data is not used for commercial purposes.\n"
            "Email, names and message texts are stored encrypted; "
            "message threads are auto-deleted after 72 hours.\n"
            "Remove email: /delemail. Full stop: /stop.\n"
            "Contact: @netpregrad"
        ),
        "ru": (
            "Конфиденциальность\n\n"
            "Идея бота — помочь оставаться на связи (например, когда VPN/доступ к Telegram нестабилен), "
            "через мост email ↔ Telegram.\n"
            "Мы не собираем лишние данные: по сути только связка Telegram ID и ваш email "
            "(плюс служебные треды для доставки ответов).\n"
            "Данные не используются в коммерческих целях.\n"
            "Email, имена и тексты сообщений в базе хранятся в зашифрованном виде; "
            "треды сообщений автоматически удаляются через 72 часа.\n"
            "Удалить почту: /delemail. Полностью остановиться: /stop.\n"
            "По вопросам связи: @netpregrad"
        ),
    },
    "email_usage": {
        "en": "Usage: /email you@example.com",
        "ru": "Использование: /email you@example.com",
    },
    "email_taken": {
        "en": "This email is already linked to another account.",
        "ru": "Эта почта уже привязана к другому аккаунту.",
    },
    "email_send_failed": {
        "en": "Failed to send code to email: {exc}",
        "ru": "Не удалось отправить код на почту: {exc}",
    },
    "email_code_sent": {
        "en": (
            "Code was sent to your email (not shown here).\n"
            "Enter in the bot: /confirm <code from email>\n"
            "TTL: {minutes} min."
        ),
        "ru": (
            "Код отправлен на вашу почту (в чат код не приходит).\n"
            "Введите в боте: /confirm <код из письма>\n"
            "Срок: {minutes} мин."
        ),
    },
    "resend_missing": {
        "en": "No pending request. First use /email you@example.com",
        "ru": "Нет активного запроса. Сначала /email you@example.com",
    },
    "resend_already_verified": {
        "en": "Email is already verified. Resend is not needed.",
        "ru": "Почта уже подтверждена. Повторная отправка кода не нужна.",
    },
    "resend_blocked": {
        "en": (
            "It looks like your mail provider is blocking our emails. "
            "Please try another email service."
        ),
        "ru": (
            "Похоже, ваш почтовик блокирует наши письма. "
            "Попробуйте другой почтовый сервис."
        ),
    },
    "resend_ok": {
        "en": (
            "New code sent to email.\n"
            "Enter: /confirm <code>\n"
            "Resends left: {left}"
        ),
        "ru": (
            "Новый код отправлен на почту.\n"
            "Введите: /confirm <код>\n"
            "Повторных отправок осталось: {left}"
        ),
    },
    "resend_btn": {
        "en": "Resend code",
        "ru": "Отправить код снова",
    },
    "resend_cb_ok": {
        "en": "Code resent",
        "ru": "Код отправлен снова",
    },
    "confirm_usage": {
        "en": "Usage: /confirm 123456",
        "ru": "Использование: /confirm 123456",
    },
    "confirm_bad": {
        "en": "Invalid or expired code. Request a new one: /email you@example.com",
        "ru": "Неверный или просроченный код. Запросите новый: /email you@example.com",
    },
    "confirm_ok": {
        "en": "Email confirmed and linked: {email}",
        "ru": "Почта подтверждена и привязана: {email}",
    },
    "delemail_ok": {
        "en": "Email removed from the bot.",
        "ru": "Почта удалена из бота.",
    },
    "delemail_missing": {
        "en": "You are not in the database yet. /start and /email if needed.",
        "ru": "Ты ещё не был в базе. /start и при необходимости /email.",
    },
    "stop_ok": {
        "en": "Stopped. Profile deleted. Use /start and /email again if needed.",
        "ru": "Стоп. Профиль удалён из бота. Снова: /start и /email.",
    },
    "whoami_missing": {
        "en": "You are not in the database. /start and /email.",
        "ru": "Тебя нет в базе. /start и /email.",
    },
    "whoami": {
        "en": "TG id: {tg_id}\nemail: {email}\nverified: {verified}",
        "ru": "TG id: {tg_id}\nemail: {email}\nподтверждена: {verified}",
    },
    "yes": {"en": "yes", "ru": "да"},
    "no": {"en": "no", "ru": "нет"},
    "none_email": {"en": "not set", "ru": "не указана"},
    "user_fallback": {"en": "User", "ru": "Пользователь"},
    "rejected_security": {
        "en": "Message rejected by security check.",
        "ru": "Сообщение отклонено проверкой безопасности.",
    },
    "mail_send_failed": {
        "en": "Failed to send email: {exc}",
        "ru": "Не удалось отправить письмо: {exc}",
    },
    "mail_sent": {
        "en": "Email sent.",
        "ru": "Мыло отправлено.",
    },
    "mail_it_groups_only": {
        "en": "[mail_it] / [мыльни] work in group chats.",
        "ru": "[mail_it] / [мыльни] работают в групповых чатах.",
    },
    "mail_it_need_mention": {
        "en": "Mention the recipient with @username and add [mail_it] or [мыльни].",
        "ru": "Укажи получателя через @username или mention и добавь [mail_it] или [мыльни].",
    },
    "mail_it_user_not_found": {
        "en": (
            "Recipient not found. They should /start the bot once "
            "and link email with /email."
        ),
        "ru": (
            "Не нашёл получателя в базе. Пусть человек хотя бы раз напишет боту /start "
            "или привяжет почту через /email."
        ),
    },
    "mail_it_no_verified": {
        "en": "User {name} has no verified email.",
        "ru": "У пользователя {name} нет подтверждённой почты.",
    },
    "subject_from_tg": {
        "en": "Message from Telegram ({chat})",
        "ru": "Сообщение из Telegram ({chat})",
    },
    "email_footer_from": {"en": "From: {name}", "ru": "От: {name}"},
    "email_footer_chat": {"en": "Chat: {chat}", "ru": "Чат: {chat}"},
    "email_footer_link": {
        "en": "Message link:\n{link}",
        "ru": "Ссылка на сообщение:\n{link}",
    },
    "email_footer_reply": {
        "en": "Reply to this email so the message appears in Telegram.",
        "ru": "Ответьте Reply на это письмо, чтобы сообщение попало в Telegram.",
    },
    "media_sent": {
        "en": "You were sent {kind}.",
        "ru": "Вам отправили {kind}.",
    },
    "media_photo": {"en": "a photo", "ru": "картинку"},
    "media_gif": {"en": "a GIF", "ru": "гифку"},
    "media_video": {"en": "a video", "ru": "видео"},
    "media_voice": {"en": "a voice message", "ru": "голосовое"},
    "media_video_note": {"en": "a video note", "ru": "видеосообщение"},
    "media_audio": {"en": "an audio file", "ru": "аудио"},
    "media_sticker": {"en": "a sticker", "ru": "стикер"},
    "media_file": {"en": "a file", "ru": "файл"},
    "replied": {
        "en": '[{name} replied]: "{body}"',
        "ru": '[{name} ответил]: "{body}"',
    },
    "lang_set": {
        "en": "Group language set to English.",
        "ru": "Язык группы: русский.",
    },
    "lang_admin_only": {
        "en": "Only chat admins can change the language.",
        "ru": "Менять язык может только админ чата.",
    },
    "verify_subject": {
        "en": "Verification code",
        "ru": "Код подтверждения",
    },
    "verify_body": {
        "en": (
            "Verification code\n\n"
            "/confirm {code}\n\n"
            "Enter in Telegram: /confirm CODE\n\n"
            "Code is valid for 15 minutes.\n"
        ),
        "ru": (
            "Код подтверждения\n\n"
            "/confirm {code}\n\n"
            "Введите в Telegram: /confirm КОД\n\n"
            "Код действует 15 минут.\n"
        ),
    },
    "instruction_body": {
        "en": (
            "This is an automatic reply.\n\n"
            "To deliver a message to Telegram, reply to the original email "
            "from the conversation (Reply), do not start a new one.\n"
        ),
        "ru": (
            "Это автоматический ответ.\n\n"
            "Чтобы сообщение попало в Telegram, ответьте на исходное письмо "
            "из переписки (Reply), а не создавайте новое.\n"
        ),
    },
}


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    lang = lang.lower().strip()
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def t(key: str, lang: str | None = None, **kwargs: object) -> str:
    lang = normalize_lang(lang)
    catalog = _TEXTS.get(key) or {}
    template = catalog.get(lang) or catalog.get(DEFAULT_LANG) or key
    if kwargs:
        return template.format(**kwargs)
    return template
