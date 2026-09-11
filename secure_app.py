import asyncio
import logging

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, TelegramObject

import bot as store


logger = logging.getLogger(__name__)


async def init_payment_guard() -> None:
    async with store.conn() as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS payment_events (
                charge_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                stars_paid INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('processing', 'done')),
                first_seen_at TEXT NOT NULL
            );
            """
        )

        await db.execute(
            """
            INSERT OR IGNORE INTO payment_events(
                charge_id, user_id, product_id, stars_paid, status, first_seen_at
            )
            SELECT charge_id, user_id, product_id, stars_paid, 'done', purchased_at
            FROM purchases
            WHERE charge_id IS NOT NULL AND TRIM(charge_id) <> ''
            ORDER BY id
            """
        )

        duplicates = await (
            await db.execute(
                """
                SELECT charge_id, COUNT(*) AS n
                FROM purchases
                WHERE charge_id IS NOT NULL AND TRIM(charge_id) <> ''
                GROUP BY charge_id
                HAVING COUNT(*) > 1
                """
            )
        ).fetchall()
        await db.commit()

    if duplicates:
        logger.warning(
            "Found %s duplicated historical Telegram payment charge IDs in purchases",
            len(duplicates),
        )


async def claim_payment(
    charge_id: str,
    user_id: int,
    product_id: int,
    stars_paid: int,
) -> str:
    if not charge_id:
        return "invalid"

    async with store.conn() as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await (
            await db.execute(
                """
                SELECT user_id, product_id, stars_paid, status
                FROM payment_events
                WHERE charge_id = ?
                """,
                (charge_id,),
            )
        ).fetchone()

        if row:
            await db.rollback()
            same_payment = (
                int(row["user_id"]) == user_id
                and int(row["product_id"]) == product_id
                and int(row["stars_paid"]) == stars_paid
            )
            if not same_payment:
                return "collision"
            return "same_done" if row["status"] == "done" else "same_processing"

        await db.execute(
            """
            INSERT INTO payment_events(
                charge_id, user_id, product_id, stars_paid, status, first_seen_at
            ) VALUES(?, ?, ?, ?, 'processing', ?)
            """,
            (charge_id, user_id, product_id, stars_paid, store.now()),
        )
        await db.commit()
        return "claimed"


async def mark_payment_done(charge_id: str) -> None:
    async with store.conn() as db:
        await db.execute(
            "UPDATE payment_events SET status = 'done' WHERE charge_id = ?",
            (charge_id,),
        )
        await db.commit()


async def release_payment_claim(charge_id: str) -> None:
    async with store.conn() as db:
        await db.execute(
            "DELETE FROM payment_events WHERE charge_id = ? AND status = 'processing'",
            (charge_id,),
        )
        await db.commit()


class PaymentGuardMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data):
        if not isinstance(event, Message) or not event.successful_payment or not event.from_user:
            return await handler(event, data)

        payment = event.successful_payment
        payload = payment.invoice_payload or ""
        if not payload.startswith("product:"):
            return await handler(event, data)

        try:
            product_id = int(payload.split(":", 1)[1])
        except ValueError:
            return await handler(event, data)

        charge_id = (payment.telegram_payment_charge_id or "").strip()
        user_id = event.from_user.id
        stars_paid = int(payment.total_amount)

        status = await claim_payment(charge_id, user_id, product_id, stars_paid)

        if status == "invalid":
            logger.error("Successful payment arrived without telegram_payment_charge_id")
            await event.answer("⚠️ Не удалось проверить ID платежа. Напиши /paysupport")
            return None

        if status == "collision":
            logger.critical(
                "Payment charge ID collision: charge_id=%s user_id=%s product_id=%s stars=%s",
                charge_id,
                user_id,
                product_id,
                stars_paid,
            )
            await event.answer(
                "⚠️ Этот ID транзакции уже зарегистрирован для другой покупки. "
                "Выдача остановлена. Напиши /paysupport"
            )
            return None

        if status == "same_processing":
            logger.info("Duplicate payment update while processing: %s", charge_id)
            return None

        if status == "same_done":
            logger.info("Duplicate successful_payment ignored: %s", charge_id)
            item = await store.product(product_id)
            if item and await store.owns(user_id, product_id):
                await event.answer("ℹ️ Этот платёж уже был обработан. Повторно не списываю.")
                bot = data.get("bot")
                if isinstance(bot, Bot):
                    await store.send_video(bot, user_id, item)
            else:
                await event.answer(
                    "⚠️ Платёж уже зарегистрирован, но покупка не найдена. Напиши /paysupport"
                )
            return None

        try:
            result = await handler(event, data)
        except Exception:
            await release_payment_claim(charge_id)
            raise
        else:
            await mark_payment_done(charge_id)
            return result


async def main() -> None:
    await store.init_db()
    await init_payment_guard()

    tg_bot = Bot(
        store.TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            protect_content=True,
        ),
    )

    dp = Dispatcher()
    dp.update.outer_middleware(store.UserTrackingMiddleware())
    dp.message.outer_middleware(PaymentGuardMiddleware())
    dp.include_router(store.router)

    await tg_bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(tg_bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
