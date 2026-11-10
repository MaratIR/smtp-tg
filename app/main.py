from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from app.bot_handlers import handle_incoming_mail, router
from app.config import load_config
from app.crypto import FieldCrypto
from app.db import Store
from app.mail import MailService, mail_poll_loop


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    crypto = FieldCrypto(config.data_encryption_key)
    store = Store(
        config.mongo_uri,
        config.mongo_db,
        crypto,
        message_retention_hours=config.message_retention_hours,
    )
    mail = MailService(config)

    session = None
    if config.telegram_api_base:
        api = TelegramAPIServer.from_base(config.telegram_api_base.rstrip("/"))
        session = AiohttpSession(api=api)
        logging.info("Using custom Telegram API base: %s", config.telegram_api_base)
    bot = Bot(token=config.bot_token, session=session)
    dp = Dispatcher()
    dp["store"] = store
    dp["mail"] = mail
    dp.include_router(router)

    async def on_mail(item) -> None:
        await handle_incoming_mail(item, bot=bot, store=store, mail=mail)

    poll_task = asyncio.create_task(
        mail_poll_loop(mail, config.mail_poll_interval, on_mail)
    )
    try:
        await dp.start_polling(bot)
    finally:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task
        store.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
