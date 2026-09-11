import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import bot as store
from broadcast import UserTrackingMiddleware, broadcast_router, init_broadcast_db


def admin_kb_with_broadcast() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Сообщения и кнопки", callback_data="admin_texts")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="➕ Как добавить видео", callback_data="admin_add_help")],
        ]
    )


store.admin_kb = admin_kb_with_broadcast


async def main():
    await store.init_db()
    await init_broadcast_db()

    tg_bot = Bot(
        store.TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            protect_content=True,
        ),
    )

    dp = Dispatcher()
    dp.update.outer_middleware(UserTrackingMiddleware())
    dp.include_router(broadcast_router)
    dp.include_router(store.router)

    await tg_bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(tg_bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
