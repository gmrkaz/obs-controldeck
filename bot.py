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

TEXT_FIELDS = {
    "start_text": (
        "👋 Приветствие",
        "🎬 <b>Видео-магазин</b>\n\nВыбери категорию и купи видео за Telegram Stars.",
    ),
    "home_text": ("🏠 Главное меню", "🎬 <b>Видео-магазин</b>"),
    "catalog_text": ("📚 Заголовок каталога", "📚 <b>Категории</b>"),
    "choose_video_text": ("🎬 Выбор видео", "🎬 <b>Выбери видео</b>"),
    "owned_text": ("🛍 Мои покупки", "🛍 <b>Мои покупки</b>"),
    "owned_empty_text": (
        "🛍 Покупок нет",
        "🛍 <b>Мои покупки</b>\n\nПока пусто.",
    ),
    "payment_success_text": (
        "✅ Успешная оплата",
        "✅ Оплата прошла — {stars} ⭐",
    ),
    "btn_catalog": ("🔘 Кнопка каталога", "🎬 Каталог"),
    "btn_owned": ("🔘 Кнопка покупок", "🛍 Мои покупки"),
    "btn_back_home": ("🔘 Назад в меню", "⬅️ Главное меню"),
    "btn_back_catalog": ("🔘 Назад в каталог", "⬅️ Категории"),
    "btn_pay": ("🔘 Кнопка оплаты", "⭐ Оплатить {stars} звёзд"),
}

pending_text_edit: dict[int, str] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id == ADMIN_ID)


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

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        await db.commit()


async def get_text(key: str) -> str:
    default = TEXT_FIELDS[key][1]
    async with conn() as db:
        row = await (
            await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        ).fetchone()
    return str(row["value"]) if row else default


async def set_text(key: str, value: str):
    if key not in TEXT_FIELDS:
        raise KeyError(key)
    async with conn() as db:
        await db.execute(
            """
            INSERT INTO settings(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await db.commit()


async def reset_text(key: str):
    async with conn() as db:
        await db.execute("DELETE FROM settings WHERE key = ?", (key,))
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


async def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await get_text("btn_catalog"), callback_data="catalog")],
            [InlineKeyboardButton(text=await get_text("btn_owned"), callback_data="owned")],
        ]
    )


async def cats_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in await categories():
        kb.button(
            text=f"📁 {item['name']} · {item['n']}",
            callback_data=f"cat:{item['id']}",
        )
    kb.button(text=await get_text("btn_owned"), callback_data="owned")
    kb.button(text=await get_text("btn_back_home"), callback_data="home")
    kb.adjust(1)
    return kb.as_markup()


async def products_kb(category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in await products(category_id):
        kb.button(
            text=f"▶️ {item['title']} · ⭐ {item['stars']}",
            callback_data=f"product:{item['id']}",
        )
    kb.button(text=await get_text("btn_back_catalog"), callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


async def pay_kb(stars: int) -> InlineKeyboardMarkup:
    label = (await get_text("btn_pay")).replace("{stars}", str(stars))
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, pay=True)]]
    )


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Сообщения и кнопки", callback_data="admin_texts")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="➕ Как добавить видео", callback_data="admin_add_help")],
        ]
    )


def admin_texts_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"edittext:{key}")]
        for key, (label, _) in TEXT_FIELDS.items()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Админка", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
        await get_text("start_text"),
        reply_markup=await main_kb(),
    )


@router.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.edit_text(
            await get_text("home_text"),
            reply_markup=await main_kb(),
        )


@router.callback_query(F.data == "catalog")
async def catalog(call: CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.edit_text(
            await get_text("catalog_text"),
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
        await get_text("choose_video_text"),
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
        reply_markup=await pay_kb(int(item["stars"])),
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

    success_text = (await get_text("payment_success_text")).replace(
        "{stars}", str(payment.total_amount)
    )
    await message.answer(success_text)
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
    kb.button(text=await get_text("btn_back_catalog"), callback_data="catalog")
    kb.adjust(1)

    if call.message:
        await call.message.edit_text(
            await get_text("owned_text") if rows else await get_text("owned_empty_text"),
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
    if not is_admin(message.from_user.id if message.from_user else None):
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
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await message.answer(
        "🛠 <b>Админ-панель</b>\n\nВыбери, что хочешь настроить:",
        reply_markup=admin_kb(),
    )


@router.callback_query(F.data == "admin_home")
async def admin_home(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    pending_text_edit.pop(call.from_user.id, None)
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "🛠 <b>Админ-панель</b>\n\nВыбери, что хочешь настроить:",
            reply_markup=admin_kb(),
        )


@router.callback_query(F.data == "admin_texts")
async def admin_texts(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "✏️ <b>Сообщения и кнопки</b>\n\nВыбери, что изменить:",
            reply_markup=admin_texts_kb(),
        )


@router.callback_query(F.data.startswith("edittext:"))
async def edit_text_start(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)

    key = (call.data or "").split(":", 1)[1]
    if key not in TEXT_FIELDS:
        return await call.answer("Неизвестное поле", show_alert=True)

    pending_text_edit[call.from_user.id] = key
    label = TEXT_FIELDS[key][0]
    current = await get_text(key)
    await call.answer()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="♻️ Сбросить по умолчанию", callback_data=f"resettext:{key}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_texts")],
        ]
    )
    if call.message:
        await call.message.edit_text(
            f"✏️ <b>{html.escape(label)}</b>\n\n"
            f"Сейчас:\n<code>{html.escape(current)}</code>\n\n"
            "Отправь мне новым сообщением новый текст.\n"
            "Можно использовать <code>{stars}</code> там, где показывается цена.",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("resettext:"))
async def reset_text_callback(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    key = (call.data or "").split(":", 1)[1]
    if key not in TEXT_FIELDS:
        return await call.answer("Неизвестное поле", show_alert=True)
    pending_text_edit.pop(call.from_user.id, None)
    await reset_text(key)
    await call.answer("Сброшено")
    if call.message:
        await call.message.edit_text(
            "✅ Значение сброшено по умолчанию.\n\nВыбери следующее поле:",
            reply_markup=admin_texts_kb(),
        )


@router.callback_query(F.data == "admin_add_help")
async def admin_add_help(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "➕ <b>Добавление видео</b>\n\n"
            "Отправь боту видео с подписью:\n"
            "<code>#add Категория | Название | 150 | Описание</code>\n\n"
            "Если категории ещё нет — она создастся автоматически.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Админка", callback_data="admin_home")]]
            ),
        )


async def stats_text() -> str:
    async with conn() as db:
        purchases_row = await (
            await db.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(stars_paid), 0) AS s FROM purchases"
            )
        ).fetchone()
        videos_row = await (
            await db.execute("SELECT COUNT(*) AS n FROM products WHERE active = 1")
        ).fetchone()
        cats_row = await (
            await db.execute("SELECT COUNT(*) AS n FROM categories WHERE active = 1")
        ).fetchone()

    return (
        f"📊 <b>Статистика</b>\n\n"
        f"Категорий: <b>{cats_row['n']}</b>\n"
        f"Видео: <b>{videos_row['n']}</b>\n"
        f"Покупок: <b>{purchases_row['n']}</b>\n"
        f"Получено: ⭐ <b>{purchases_row['s']}</b>"
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await call.answer()
    if call.message:
        await call.message.edit_text(
            await stats_text(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Админка", callback_data="admin_home")]]
            ),
        )


@router.message(Command("stats"))
async def stats(message: Message):
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await message.answer(await stats_text())


@router.message(Command("paysupport"))
async def support(message: Message):
    if SUPPORT:
        await message.answer(f"Поддержка: <b>{html.escape(SUPPORT)}</b>")
    else:
        await message.answer("Напиши владельцу магазина.")


@router.message(Command("cancel"))
async def cancel_edit(message: Message):
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    if message.from_user:
        pending_text_edit.pop(message.from_user.id, None)
    await message.answer("❌ Редактирование отменено.", reply_markup=admin_kb())


@router.message(F.text)
async def admin_text_value(message: Message):
    if not message.from_user or not is_admin(message.from_user.id):
        return

    key = pending_text_edit.get(message.from_user.id)
    if not key:
        return

    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ Текст не может быть пустым.")
        return
    if len(value) > 3500:
        await message.answer("❌ Слишком длинный текст. Максимум 3500 символов.")
        return

    await set_text(key, value)
    pending_text_edit.pop(message.from_user.id, None)
    await message.answer(
        f"✅ <b>{html.escape(TEXT_FIELDS[key][0])}</b> обновлено.",
        reply_markup=admin_texts_kb(),
    )


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
