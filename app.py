import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import bot as store
from admin_manage import admin_manage_router, full_admin_kb
from broadcast import UserTrackingMiddleware, broadcast_router, init_broadcast_db


store.admin_kb = full_admin_kb


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
    dp.include_router(admin_manage_router)
    dp.include_router(store.router)

    await tg_bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(tg_bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
