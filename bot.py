import asyncio
import html
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "/app/data/store.db").strip()
SUPPORT = os.getenv("SUPPORT_USERNAME", "").strip()

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is missing")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

router = Router()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def conn():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with conn() as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 25000),
                file_id TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(category_id) REFERENCES categories(id)
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                stars_paid INTEGER NOT NULL,
                charge_id TEXT,
                purchased_at TEXT NOT NULL,
                UNIQUE(user_id, product_id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            );
            """
        )
        await db.commit()


async def get_cat(name: str) -> int:
    async with conn() as db:
        row = await (
            await db.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE",
                (name,),
            )
        ).fetchone()

        if row:
            await db.execute("UPDATE categories SET active = 1 WHERE id = ?", (row["id"],))
            await db.commit()
            return int(row["id"])

        cur = await db.execute(
            "INSERT INTO categories(name, created_at) VALUES(?, ?)",
            (name, now()),
        )
        await db.commit()
        return int(cur.lastrowid)


async def categories():
    async with conn() as db:
        return await (
            await db.execute(
                """
                SELECT c.id, c.name, COUNT(p.id) AS n
                FROM categories c
                LEFT JOIN products p
                    ON p.category_id = c.id AND p.active = 1
                WHERE c.active = 1
                GROUP BY c.id
                ORDER BY c.id
                """
            )
        ).fetchall()


async def products(category_id: int):
    async with conn() as db:
        return await (
            await db.execute(
                "SELECT * FROM products WHERE category_id = ? AND active = 1 ORDER BY id DESC",
                (category_id,),
            )
        ).fetchall()


async def product(product_id: int):
    async with conn() as db:
        return await (
            await db.execute(
                """
                SELECT p.*, c.name AS category_name
                FROM products p
                JOIN categories c ON c.id = p.category_id
                WHERE p.id = ? AND p.active = 1 AND c.active = 1
                """,
                (product_id,),
            )
        ).fetchone()


async def owns(user_id: int, product_id: int) -> bool:
    async with conn() as db:
        row = await (
            await db.execute(
                "SELECT 1 FROM purchases WHERE user_id = ? AND product_id = ?",
                (user_id, product_id),
            )
        ).fetchone()
        return bool(row)


async def save_purchase(user_id: int, product_id: int, stars: int, charge_id: str):
    async with conn() as db:
        await db.execute(
            """
            INSERT INTO purchases(user_id, product_id, stars_paid, charge_id, purchased_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(user_id, product_id) DO UPDATE SET
                stars_paid = excluded.stars_paid,
                charge_id = excluded.charge_id
            """,
            (user_id, product_id, stars, charge_id, now()),
        )
        await db.commit()


def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Каталог", callback_data="catalog")],
            [InlineKeyboardButton(text="🛍 Мои покупки", callback_data="owned")],
        ]
    )


async def cats_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in await categories():
        kb.button(
            text=f"📁 {item['name']} · {item['n']}",
            callback_data=f"cat:{item['id']}",
        )
    kb.button(text="🛍 Мои покупки", callback_data="owned")
    kb.button(text="⬅️ Главное меню", callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


async def products_kb(category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in await products(category_id):
        kb.button(
            text=f"▶️ {item['title']} · ⭐ {item['stars']}",
            callback_data=f"product:{item['id']}",
        )
    kb.button(text="⬅️ Категории", callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


def pay_kb(stars: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Оплатить {stars} звёзд", pay=True)]
        ]
    )


async def send_video(bot: Bot, user_id: int, item):
    await bot.send_video(
        chat_id=user_id,
        video=item["file_id"],
        caption=(
            f"✅ <b>{html.escape(item['title'])}</b>\n"
            f"📁 {html.escape(item['category_name'])}\n\n"
            f"{html.escape(item['description'] or '')}"
        ),
        protect_content=True,
        supports_streaming=True,
    )


@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "🎬 <b>Видео-магазин</b>\n\n"
        "Выбери категорию и купи видео за Telegram Stars.",
        reply_markup=main_kb(),
    )


@router.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "🎬 <b>Видео-магазин</b>",
            reply_markup=main_kb(),
        )


@router.callback_query(F.data == "catalog")
async def catalog(call: CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "📚 <b>Категории</b>",
            reply_markup=await cats_kb(),
        )


@router.callback_query(F.data.startswith("cat:"))
async def cat(call: CallbackQuery):
    await call.answer()
    if not call.message:
        return

    try:
        category_id = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError):
        return

    await call.message.edit_text(
        "🎬 <b>Выбери видео</b>",
        reply_markup=await products_kb(category_id),
    )


@router.callback_query(F.data.startswith("product:"))
async def buy(call: CallbackQuery, bot: Bot):
    await call.answer()

    try:
        product_id = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError):
        return

    item = await product(product_id)
    if not item:
        await call.answer("Товар недоступен", show_alert=True)
        return

    if await owns(call.from_user.id, product_id):
        await send_video(bot, call.from_user.id, item)
        return

    title = (item["title"] or "Видео")[:32]
    description = (
        item["description"] or f"Видео из категории {item['category_name']}"
    )[:255]

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=title,
        description=description,
        payload=f"product:{product_id}",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=int(item["stars"]))],
        provider_token="",
        reply_markup=pay_kb(int(item["stars"])),
        protect_content=True,
    )


@router.pre_checkout_query()
async def checkout(query: PreCheckoutQuery):
    payload = query.invoice_payload or ""
    if not payload.startswith("product:"):
        await query.answer(ok=False, error_message="Некорректный товар.")
        return

    try:
        product_id = int(payload.split(":", 1)[1])
    except ValueError:
        await query.answer(ok=False, error_message="Некорректный товар.")
        return

    item = await product(product_id)
    if query.currency != "XTR" or not item or query.total_amount != int(item["stars"]):
        await query.answer(
            ok=False,
            error_message="Товар или цена изменились. Открой карточку заново.",
        )
        return

    if await owns(query.from_user.id, product_id):
        await query.answer(
            ok=False,
            error_message="Ты уже покупал это видео. Открой «Мои покупки».",
        )
        return

    await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(message: Message, bot: Bot):
    payment = message.successful_payment
    if not payment or not message.from_user:
        return

    payload = payment.invoice_payload or ""
    if not payload.startswith("product:"):
        return

    try:
        product_id = int(payload.split(":", 1)[1])
    except ValueError:
        return

    item = await product(product_id)
    if (
        not item
        or payment.currency != "XTR"
        or payment.total_amount != int(item["stars"])
    ):
        await message.answer(
            "Платёж получен, но возникла ошибка выдачи. Напиши /paysupport"
        )
        return

    await save_purchase(
        message.from_user.id,
        product_id,
        int(payment.total_amount),
        payment.telegram_payment_charge_id,
    )

    await message.answer(f"✅ Оплата прошла — {payment.total_amount} ⭐")
    await send_video(bot, message.from_user.id, item)


@router.callback_query(F.data == "owned")
async def owned(call: CallbackQuery):
    await call.answer()

    async with conn() as db:
        rows = await (
            await db.execute(
                """
                SELECT p.id, p.title
                FROM purchases x
                JOIN products p ON p.id = x.product_id
                WHERE x.user_id = ? AND p.active = 1
                ORDER BY x.id DESC
                """,
                (call.from_user.id,),
            )
        ).fetchall()

    kb = InlineKeyboardBuilder()
    for item in rows:
        kb.button(text=f"✅ {item['title']}", callback_data=f"owned:{item['id']}")
    kb.button(text="⬅️ Каталог", callback_data="catalog")
    kb.adjust(1)

    if call.message:
        await call.message.edit_text(
            "🛍 <b>Мои покупки</b>"
            if rows
            else "🛍 <b>Мои покупки</b>\n\nПока пусто.",
            reply_markup=kb.as_markup(),
        )


@router.callback_query(F.data.startswith("owned:"))
async def owned_item(call: CallbackQuery, bot: Bot):
    await call.answer()

    try:
        product_id = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError):
        return

    if not await owns(call.from_user.id, product_id):
        await call.answer("Покупка не найдена", show_alert=True)
        return

    item = await product(product_id)
    if item:
        await send_video(bot, call.from_user.id, item)


@router.message(F.video)
async def add_video(message: Message):
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    caption = (message.caption or "").strip()
    if not caption.lower().startswith("#add"):
        await message.answer(
            "Формат: <code>#add Категория | Название | 150 | Описание</code>"
        )
        return

    parts = [part.strip() for part in caption[4:].strip().split("|")]
    if len(parts) < 3 or not parts[0] or not parts[1]:
        await message.answer(
            "❌ Формат: <code>#add Категория | Название | 150 | Описание</code>"
        )
        return

    try:
        stars = int(parts[2])
    except ValueError:
        await message.answer("❌ Цена должна быть числом.")
        return

    if not 1 <= stars <= 25000:
        await message.answer("❌ Цена: 1–25 000 Stars.")
        return

    category_id = await get_cat(parts[0])
    description = " | ".join(parts[3:]) if len(parts) > 3 else ""

    async with conn() as db:
        cur = await db.execute(
            """
            INSERT INTO products(category_id, title, description, stars, file_id, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                category_id,
                parts[1],
                description,
                stars,
                message.video.file_id,
                now(),
            ),
        )
        await db.commit()
        product_id = int(cur.lastrowid)

    await message.answer(
        f"✅ Добавлено. ID <code>{product_id}</code>\n"
        f"Кнопка: <b>⭐ Оплатить {stars} звёзд</b>"
    )


@router.message(Command("admin"))
async def admin(message: Message):
    if message.from_user and message.from_user.id == ADMIN_ID:
        await message.answer(
            "🛠 Отправь видео с подписью:\n"
            "<code>#add Категория | Название | 150 | Описание</code>\n\n"
            "/stats — статистика\n"
            "/paysupport — поддержка"
        )


@router.message(Command("stats"))
async def stats(message: Message):
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    async with conn() as db:
        purchases_row = await (
            await db.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(stars_paid), 0) AS s FROM purchases"
            )
        ).fetchone()
        videos_row = await (
            await db.execute("SELECT COUNT(*) AS n FROM products WHERE active = 1")
        ).fetchone()

    await message.answer(
        f"📊 Покупок: <b>{purchases_row['n']}</b>\n"
        f"Видео: <b>{videos_row['n']}</b>\n"
        f"Получено: ⭐ <b>{purchases_row['s']}</b>"
    )


@router.message(Command("paysupport"))
async def support(message: Message):
    if SUPPORT:
        await message.answer(f"Поддержка: <b>{html.escape(SUPPORT)}</b>")
    else:
        await message.answer("Напиши владельцу магазина.")


async def main():
    await init_db()

    bot = Bot(
        TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            protect_content=True,
        ),
    )

    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
