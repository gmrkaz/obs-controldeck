import asyncio
import html
import logging
import uuid

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery, TelegramObject

import bot as store


logger = logging.getLogger(__name__)
order_router = Router(name="unique_orders")


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

            CREATE TABLE IF NOT EXISTS payment_orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                stars INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'paid')),
                charge_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                paid_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_payment_orders_user_product
            ON payment_orders(user_id, product_id);
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


async def create_order(user_id: int, product_id: int, stars: int) -> str:
    order_id = uuid.uuid4().hex
    async with store.conn() as db:
        await db.execute(
            """
            INSERT INTO payment_orders(
                order_id, user_id, product_id, stars, status, created_at
            ) VALUES(?, ?, ?, ?, 'pending', ?)
            """,
            (order_id, user_id, product_id, stars, store.now()),
        )
        await db.commit()
    return order_id


async def get_order(order_id: str):
    async with store.conn() as db:
        return await (
            await db.execute(
                """
                SELECT order_id, user_id, product_id, stars, status, charge_id
                FROM payment_orders
                WHERE order_id = ?
                """,
                (order_id,),
            )
        ).fetchone()


async def claim_order_payment(
    order_id: str,
    charge_id: str,
    user_id: int,
    stars_paid: int,
) -> tuple[str, int | None]:
    if not charge_id:
        return "invalid_charge", None

    async with store.conn() as db:
        await db.execute("BEGIN IMMEDIATE")
        order = await (
            await db.execute(
                """
                SELECT user_id, product_id, stars, status, charge_id
                FROM payment_orders
                WHERE order_id = ?
                """,
                (order_id,),
            )
        ).fetchone()

        if not order:
            await db.rollback()
            return "missing_order", None

        product_id = int(order["product_id"])
        if int(order["user_id"]) != user_id or int(order["stars"]) != stars_paid:
            await db.rollback()
            return "order_mismatch", product_id

        current_charge = (order["charge_id"] or "").strip()
        if order["status"] == "paid":
            await db.rollback()
            return ("same_done" if current_charge == charge_id else "order_already_paid"), product_id

        if order["status"] == "processing":
            await db.rollback()
            return ("same_processing" if current_charge == charge_id else "order_collision"), product_id

        existing = await (
            await db.execute(
                "SELECT 1 FROM payment_events WHERE charge_id = ?",
                (charge_id,),
            )
        ).fetchone()
        if existing:
            await db.rollback()
            return "charge_collision", product_id

        await db.execute(
            """
            UPDATE payment_orders
            SET status = 'processing', charge_id = ?
            WHERE order_id = ? AND status = 'pending'
            """,
            (charge_id, order_id),
        )
        await db.execute(
            """
            INSERT INTO payment_events(
                charge_id, user_id, product_id, stars_paid, status, first_seen_at
            ) VALUES(?, ?, ?, ?, 'processing', ?)
            """,
            (charge_id, user_id, product_id, stars_paid, store.now()),
        )
        await db.commit()
        return "claimed", product_id


async def mark_order_paid(order_id: str, charge_id: str) -> None:
    async with store.conn() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            """
            UPDATE payment_orders
            SET status = 'paid', paid_at = ?
            WHERE order_id = ? AND charge_id = ? AND status = 'processing'
            """,
            (store.now(), order_id, charge_id),
        )
        await db.execute(
            "UPDATE payment_events SET status = 'done' WHERE charge_id = ?",
            (charge_id,),
        )
        await db.commit()


async def release_order_claim(order_id: str, charge_id: str) -> None:
    async with store.conn() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            """
            UPDATE payment_orders
            SET status = 'pending', charge_id = NULL
            WHERE order_id = ? AND charge_id = ? AND status = 'processing'
            """,
            (order_id, charge_id),
        )
        await db.execute(
            "DELETE FROM payment_events WHERE charge_id = ? AND status = 'processing'",
            (charge_id,),
        )
        await db.commit()


async def claim_legacy_payment(
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


async def mark_legacy_payment_done(charge_id: str) -> None:
    async with store.conn() as db:
        await db.execute(
            "UPDATE payment_events SET status = 'done' WHERE charge_id = ?",
            (charge_id,),
        )
        await db.commit()


async def release_legacy_payment_claim(charge_id: str) -> None:
    async with store.conn() as db:
        await db.execute(
            "DELETE FROM payment_events WHERE charge_id = ? AND status = 'processing'",
            (charge_id,),
        )
        await db.commit()


class LegacyPaymentGuardMiddleware(BaseMiddleware):
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
        status = await claim_legacy_payment(charge_id, user_id, product_id, stars_paid)

        if status == "invalid":
            await event.answer("⚠️ Не удалось проверить ID платежа. Напиши /paysupport")
            return None
        if status == "collision":
            logger.critical("Legacy charge ID collision: %s", charge_id)
            await event.answer(
                "⚠️ Этот ID транзакции уже зарегистрирован для другой покупки. Напиши /paysupport"
            )
            return None
        if status == "same_processing":
            return None
        if status == "same_done":
            item = await store.product(product_id)
            if item and await store.owns(user_id, product_id):
                await event.answer("ℹ️ Этот платёж уже обработан.")
                bot = data.get("bot")
                if isinstance(bot, Bot):
                    await store.send_video(bot, user_id, item)
            return None

        try:
            result = await handler(event, data)
        except Exception:
            await release_legacy_payment_claim(charge_id)
            raise
        else:
            await mark_legacy_payment_done(charge_id)
            return result


@order_router.callback_query(F.data.startswith("product:"))
async def create_unique_invoice(call: CallbackQuery, bot: Bot):
    await call.answer()
    try:
        product_id = int((call.data or "").split(":", 1)[1])
    except ValueError:
        return

    item = await store.product(product_id)
    if not item:
        await call.answer("Товар недоступен", show_alert=True)
        return

    if await store.owns(call.from_user.id, product_id):
        await store.send_video(bot, call.from_user.id, item)
        return

    stars = int(item["stars"])
    order_id = await create_order(call.from_user.id, product_id, stars)
    title = (item["title"] or "Видео")[:32]
    description = (
        item["description"] or f"Видео из категории {item['category_name']}"
    )[:255]

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=title,
        description=description,
        payload=f"order:{order_id}",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=stars)],
        reply_markup=await store.pay_kb(stars),
        protect_content=True,
    )


@order_router.pre_checkout_query(F.invoice_payload.startswith("order:"))
async def check_unique_order(query: PreCheckoutQuery):
    order_id = (query.invoice_payload or "").split(":", 1)[1]
    order = await get_order(order_id)
    if not order:
        await query.answer(ok=False, error_message="Заказ не найден. Открой товар заново.")
        return

    if int(order["user_id"]) != query.from_user.id:
        await query.answer(ok=False, error_message="Этот счёт создан для другого пользователя.")
        return
    if order["status"] != "pending":
        await query.answer(ok=False, error_message="Этот заказ уже обработан. Открой товар заново.")
        return
    if query.currency != "XTR" or query.total_amount != int(order["stars"]):
        await query.answer(ok=False, error_message="Сумма заказа не совпадает. Открой товар заново.")
        return

    product_id = int(order["product_id"])
    item = await store.product(product_id)
    if not item or int(item["stars"]) != int(order["stars"]):
        await query.answer(ok=False, error_message="Товар или цена изменились. Открой карточку заново.")
        return
    if await store.owns(query.from_user.id, product_id):
        await query.answer(ok=False, error_message="Ты уже покупал это видео. Открой «Мои покупки».")
        return

    await query.answer(ok=True)


@order_router.message(F.successful_payment.invoice_payload.startswith("order:"))
async def process_unique_order(message: Message, bot: Bot):
    payment = message.successful_payment
    if not payment or not message.from_user:
        return

    order_id = (payment.invoice_payload or "").split(":", 1)[1]
    charge_id = (payment.telegram_payment_charge_id or "").strip()
    status, product_id = await claim_order_payment(
        order_id,
        charge_id,
        message.from_user.id,
        int(payment.total_amount),
    )

    if status == "same_processing":
        return
    if status == "same_done":
        if product_id is not None:
            item = await store.product(product_id)
            if item and await store.owns(message.from_user.id, product_id):
                await message.answer("ℹ️ Этот заказ уже был обработан.")
                await store.send_video(bot, message.from_user.id, item)
        return
    if status != "claimed" or product_id is None:
        logger.critical(
            "Order payment rejected: status=%s order=%s charge=%s user=%s",
            status,
            order_id,
            charge_id,
            message.from_user.id,
        )
        await message.answer(
            "⚠️ Не удалось однозначно проверить транзакцию. Выдача остановлена. Напиши /paysupport"
        )
        return

    item = await store.product(product_id)
    if (
        not item
        or payment.currency != "XTR"
        or payment.total_amount != int(item["stars"])
    ):
        await release_order_claim(order_id, charge_id)
        await message.answer("⚠️ Ошибка проверки товара после оплаты. Напиши /paysupport")
        return

    try:
        if not await store.owns(message.from_user.id, product_id):
            await store.save_purchase(
                message.from_user.id,
                product_id,
                int(payment.total_amount),
                charge_id,
            )
        await mark_order_paid(order_id, charge_id)
    except Exception:
        await release_order_claim(order_id, charge_id)
        raise

    success_text = (await store.get_text("payment_success_text")).replace(
        "{stars}", str(payment.total_amount)
    )
    await message.answer(success_text)
    await store.send_video(bot, message.from_user.id, item)


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
    dp.message.outer_middleware(LegacyPaymentGuardMiddleware())
    dp.include_router(order_router)
    dp.include_router(store.router)

    await tg_bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(tg_bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
