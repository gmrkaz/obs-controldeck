import asyncio
import html
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    TelegramObject,
    User,
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
logger = logging.getLogger(__name__)
router = Router(name="video_store")


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


class TextEditState(StatesGroup):
    waiting_value = State()


class BroadcastState(StatesGroup):
    waiting_message = State()
    confirm = State()


class AdminEditState(StatesGroup):
    create_category = State()
    rename_category = State()
    edit_product_title = State()
    edit_product_price = State()
    edit_product_description = State()


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

            CREATE TABLE IF NOT EXISTS broadcast_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscribed INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            """
        )
        await db.commit()


async def upsert_user(user: User):
    stamp = now()
    async with conn() as db:
        await db.execute(
            """
            INSERT INTO broadcast_users(
                user_id, username, first_name, subscribed, created_at, last_seen
            ) VALUES(?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
            """,
            (user.id, user.username, user.first_name, stamp, stamp),
        )
        await db.commit()


async def set_subscription(user_id: int, subscribed: bool):
    async with conn() as db:
        await db.execute(
            "UPDATE broadcast_users SET subscribed = ?, last_seen = ? WHERE user_id = ?",
            (1 if subscribed else 0, now(), user_id),
        )
        await db.commit()


async def subscribed_user_ids() -> list[int]:
    async with conn() as db:
        rows = await (
            await db.execute(
                "SELECT user_id FROM broadcast_users WHERE subscribed = 1 ORDER BY user_id"
            )
        ).fetchall()
        return [int(row["user_id"]) for row in rows]


async def broadcast_user_count() -> int:
    async with conn() as db:
        row = await (
            await db.execute(
                "SELECT COUNT(*) AS n FROM broadcast_users WHERE subscribed = 1"
            )
        ).fetchone()
        return int(row["n"])


class UserTrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if isinstance(user, User) and not user.is_bot:
            try:
                await upsert_user(user)
            except Exception:
                logger.exception("Failed to track Telegram user %s", user.id)
        return await handler(event, data)


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
                LEFT JOIN products p ON p.category_id = c.id AND p.active = 1
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
        kb.button(text=f"📁 {item['name']} · {item['n']}", callback_data=f"cat:{item['id']}")
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
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast")],
            [
                InlineKeyboardButton(text="📁 Категории", callback_data="admin_categories"),
                InlineKeyboardButton(text="🎬 Видео", callback_data="admin_products"),
            ],
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


async def categories_admin_kb() -> InlineKeyboardMarkup:
    rows = []
    for item in await categories():
        rows.append([
            InlineKeyboardButton(
                text=f"📁 {item['name']} · {item['n']}",
                callback_data=f"admin_cat:{item['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="➕ Создать категорию", callback_data="admin_cat_create")])
    rows.append([InlineKeyboardButton(text="⬅️ Админка", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def products_admin_kb() -> InlineKeyboardMarkup:
    async with conn() as db:
        rows_db = await (
            await db.execute(
                """
                SELECT p.id, p.title, p.stars
                FROM products p
                WHERE p.active = 1
                ORDER BY p.id DESC
                LIMIT 50
                """
            )
        ).fetchall()
    rows = [
        [InlineKeyboardButton(
            text=f"🎬 {row['title']} · ⭐ {row['stars']}",
            callback_data=f"admin_product:{row['id']}",
        )]
        for row in rows_db
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
    await message.answer(await get_text("start_text"), reply_markup=await main_kb())


@router.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.edit_text(await get_text("home_text"), reply_markup=await main_kb())


@router.callback_query(F.data == "catalog")
async def catalog(call: CallbackQuery):
    await call.answer()
    if call.message:
        await call.message.edit_text(await get_text("catalog_text"), reply_markup=await cats_kb())


@router.callback_query(F.data.startswith("cat:"))
async def cat(call: CallbackQuery):
    await call.answer()
    if not call.message:
        return
    try:
        category_id = int((call.data or "").split(":", 1)[1])
    except ValueError:
        return
    await call.message.edit_text(
        await get_text("choose_video_text"),
        reply_markup=await products_kb(category_id),
    )


@router.callback_query(F.data.startswith("product:"))
async def buy(call: CallbackQuery, bot: Bot):
    await call.answer()
    try:
        product_id = int((call.data or "").split(":", 1)[1])
    except ValueError:
        return
    item = await product(product_id)
    if not item:
        await call.answer("Товар недоступен", show_alert=True)
        return
    if await owns(call.from_user.id, product_id):
        await send_video(bot, call.from_user.id, item)
        return

    title = (item["title"] or "Видео")[:32]
    description = (item["description"] or f"Видео из категории {item['category_name']}")[:255]
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
    if not item or payment.currency != "XTR" or payment.total_amount != int(item["stars"]):
        await message.answer("Платёж получен, но возникла ошибка выдачи. Напиши /paysupport")
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
        product_id = int((call.data or "").split(":", 1)[1])
    except ValueError:
        return
    if not await owns(call.from_user.id, product_id):
        await call.answer("Покупка не найдена", show_alert=True)
        return
    item = await product(product_id)
    if item:
        await send_video(bot, call.from_user.id, item)


@router.message(Command("admin"))
async def admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await message.answer(
        "🛠 <b>Админ-панель</b>\n\nВыбери, что хочешь настроить:",
        reply_markup=admin_kb(),
    )


@router.callback_query(F.data == "admin_home")
async def admin_home(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "🛠 <b>Админ-панель</b>\n\nВыбери, что хочешь настроить:",
            reply_markup=admin_kb(),
        )


@router.callback_query(F.data == "admin_texts")
async def admin_texts(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "✏️ <b>Сообщения и кнопки</b>\n\nВыбери, что изменить:",
            reply_markup=admin_texts_kb(),
        )


@router.callback_query(F.data.startswith("edittext:"))
async def edit_text_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    key = (call.data or "").split(":", 1)[1]
    if key not in TEXT_FIELDS:
        return await call.answer("Неизвестное поле", show_alert=True)
    await state.set_state(TextEditState.waiting_value)
    await state.update_data(text_key=key)
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
            "Отправь новым сообщением новый текст.\n"
            "Можно использовать <code>{stars}</code> там, где показывается цена.",
            reply_markup=kb,
        )


@router.message(TextEditState.waiting_value)
async def edit_text_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    data = await state.get_data()
    key = data.get("text_key")
    if key not in TEXT_FIELDS:
        await state.clear()
        return
    value = (message.text or "").strip()
    if not value:
        await message.answer("❌ Текст не может быть пустым.")
        return
    if len(value) > 3500:
        await message.answer("❌ Слишком длинный текст. Максимум 3500 символов.")
        return
    await set_text(str(key), value)
    await state.clear()
    await message.answer(
        f"✅ <b>{html.escape(TEXT_FIELDS[str(key)][0])}</b> обновлено.",
        reply_markup=admin_texts_kb(),
    )


@router.callback_query(F.data.startswith("resettext:"))
async def reset_text_callback(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    key = (call.data or "").split(":", 1)[1]
    if key not in TEXT_FIELDS:
        return await call.answer("Неизвестное поле", show_alert=True)
    await state.clear()
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


@router.message(F.video)
async def add_video(message: Message):
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    caption = (message.caption or "").strip()
    if not caption.lower().startswith("#add"):
        return
    parts = [part.strip() for part in caption[4:].strip().split("|")]
    if len(parts) < 3 or not parts[0] or not parts[1]:
        await message.answer("❌ Формат: <code>#add Категория | Название | 150 | Описание</code>")
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
            (category_id, parts[1], description, stars, message.video.file_id, now()),
        )
        await db.commit()
        product_id = int(cur.lastrowid)
    await message.answer(
        f"✅ Добавлено. ID <code>{product_id}</code>\n"
        f"Кнопка: <b>⭐ Оплатить {stars} звёзд</b>"
    )


@router.callback_query(F.data == "admin_categories")
async def admin_categories(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "📁 <b>Категории</b>\n\nВыбери категорию или создай новую:",
            reply_markup=await categories_admin_kb(),
        )


@router.callback_query(F.data == "admin_cat_create")
async def admin_cat_create(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(AdminEditState.create_category)
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "➕ <b>Новая категория</b>\n\nОтправь название новой категории.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_categories")]]
            ),
        )


@router.message(AdminEditState.create_category)
async def admin_cat_create_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer("❌ Название должно быть от 1 до 64 символов.")
        return
    await get_cat(name)
    await state.clear()
    await message.answer("✅ Категория создана.", reply_markup=await categories_admin_kb())


@router.callback_query(F.data.startswith("admin_cat:"))
async def admin_cat_detail(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    try:
        category_id = int((call.data or "").split(":", 1)[1])
    except ValueError:
        return await call.answer("Ошибка категории", show_alert=True)
    async with conn() as db:
        row = await (
            await db.execute(
                "SELECT id, name FROM categories WHERE id = ? AND active = 1",
                (category_id,),
            )
        ).fetchone()
        count = await (
            await db.execute(
                "SELECT COUNT(*) AS n FROM products WHERE category_id = ? AND active = 1",
                (category_id,),
            )
        ).fetchone()
    if not row:
        return await call.answer("Категория не найдена", show_alert=True)
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"admin_cat_rename:{category_id}")],
        [InlineKeyboardButton(text="🗑 Скрыть категорию", callback_data=f"admin_cat_delete:{category_id}")],
        [InlineKeyboardButton(text="⬅️ Категории", callback_data="admin_categories")],
    ])
    if call.message:
        await call.message.edit_text(
            f"📁 <b>{html.escape(row['name'])}</b>\nВидео: <b>{count['n']}</b>",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("admin_cat_rename:"))
async def admin_cat_rename(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    category_id = int((call.data or "").split(":", 1)[1])
    await state.set_state(AdminEditState.rename_category)
    await state.update_data(category_id=category_id)
    await call.answer()
    if call.message:
        await call.message.edit_text("✏️ Отправь новое название категории.")


@router.message(AdminEditState.rename_category)
async def admin_cat_rename_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    data = await state.get_data()
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer("❌ Название должно быть от 1 до 64 символов.")
        return
    try:
        async with conn() as db:
            await db.execute(
                "UPDATE categories SET name = ? WHERE id = ?",
                (name, int(data["category_id"])),
            )
            await db.commit()
    except aiosqlite.IntegrityError:
        await message.answer("❌ Такое название уже используется.")
        return
    await state.clear()
    await message.answer("✅ Категория переименована.", reply_markup=await categories_admin_kb())


@router.callback_query(F.data.startswith("admin_cat_delete:"))
async def admin_cat_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    category_id = int((call.data or "").split(":", 1)[1])
    async with conn() as db:
        await db.execute("UPDATE categories SET active = 0 WHERE id = ?", (category_id,))
        await db.execute("UPDATE products SET active = 0 WHERE category_id = ?", (category_id,))
        await db.commit()
    await call.answer("Категория скрыта")
    if call.message:
        await call.message.edit_text(
            "✅ Категория и её видео скрыты.",
            reply_markup=await categories_admin_kb(),
        )


@router.callback_query(F.data == "admin_products")
async def admin_products(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "🎬 <b>Видео</b>\n\nПоказаны последние 50 активных видео:",
            reply_markup=await products_admin_kb(),
        )


@router.callback_query(F.data.startswith("admin_product:"))
async def admin_product_detail(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    product_id = int((call.data or "").split(":", 1)[1])
    item = await product(product_id)
    if not item:
        return await call.answer("Видео не найдено", show_alert=True)
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_product_title:{product_id}"),
            InlineKeyboardButton(text="⭐ Цена", callback_data=f"admin_product_price:{product_id}"),
        ],
        [InlineKeyboardButton(text="📝 Описание", callback_data=f"admin_product_desc:{product_id}")],
        [InlineKeyboardButton(text="🗑 Скрыть видео", callback_data=f"admin_product_delete:{product_id}")],
        [InlineKeyboardButton(text="⬅️ Видео", callback_data="admin_products")],
    ])
    if call.message:
        await call.message.edit_text(
            f"🎬 <b>{html.escape(item['title'])}</b>\n"
            f"📁 {html.escape(item['category_name'])}\n"
            f"⭐ {item['stars']}\n\n"
            f"{html.escape(item['description'] or 'Без описания')}",
            reply_markup=kb,
        )


async def start_product_edit(
    call: CallbackQuery,
    state: FSMContext,
    state_value: State,
    product_id: int,
    prompt: str,
):
    await state.set_state(state_value)
    await state.update_data(product_id=product_id)
    await call.answer()
    if call.message:
        await call.message.edit_text(prompt)


@router.callback_query(F.data.startswith("admin_product_title:"))
async def edit_product_title(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await start_product_edit(
        call,
        state,
        AdminEditState.edit_product_title,
        int((call.data or "").split(":", 1)[1]),
        "✏️ Отправь новое название видео.",
    )


@router.callback_query(F.data.startswith("admin_product_price:"))
async def edit_product_price(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await start_product_edit(
        call,
        state,
        AdminEditState.edit_product_price,
        int((call.data or "").split(":", 1)[1]),
        "⭐ Отправь новую цену в Stars (1–25000).",
    )


@router.callback_query(F.data.startswith("admin_product_desc:"))
async def edit_product_desc(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await start_product_edit(
        call,
        state,
        AdminEditState.edit_product_description,
        int((call.data or "").split(":", 1)[1]),
        "📝 Отправь новое описание видео.",
    )


@router.message(AdminEditState.edit_product_title)
async def edit_product_title_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    data = await state.get_data()
    value = (message.text or "").strip()
    if not value or len(value) > 120:
        await message.answer("❌ Название: 1–120 символов.")
        return
    async with conn() as db:
        await db.execute(
            "UPDATE products SET title = ? WHERE id = ?",
            (value, int(data["product_id"])),
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Название изменено.", reply_markup=await products_admin_kb())


@router.message(AdminEditState.edit_product_price)
async def edit_product_price_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    data = await state.get_data()
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ Отправь число от 1 до 25000.")
        return
    if not 1 <= value <= 25000:
        await message.answer("❌ Цена должна быть от 1 до 25000 Stars.")
        return
    async with conn() as db:
        await db.execute(
            "UPDATE products SET stars = ? WHERE id = ?",
            (value, int(data["product_id"])),
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Цена изменена.", reply_markup=await products_admin_kb())


@router.message(AdminEditState.edit_product_description)
async def edit_product_desc_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    data = await state.get_data()
    value = (message.text or "").strip()
    if len(value) > 1000:
        await message.answer("❌ Описание максимум 1000 символов.")
        return
    async with conn() as db:
        await db.execute(
            "UPDATE products SET description = ? WHERE id = ?",
            (value, int(data["product_id"])),
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Описание изменено.", reply_markup=await products_admin_kb())


@router.callback_query(F.data.startswith("admin_product_delete:"))
async def admin_product_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    product_id = int((call.data or "").split(":", 1)[1])
    async with conn() as db:
        await db.execute("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
        await db.commit()
    await call.answer("Видео скрыто")
    if call.message:
        await call.message.edit_text(
            "✅ Видео скрыто из магазина.",
            reply_markup=await products_admin_kb(),
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
        users_row = await (
            await db.execute("SELECT COUNT(*) AS n FROM broadcast_users")
        ).fetchone()
        subscribed_row = await (
            await db.execute("SELECT COUNT(*) AS n FROM broadcast_users WHERE subscribed = 1")
        ).fetchone()
    return (
        f"📊 <b>Статистика</b>\n\n"
        f"Пользователей: <b>{users_row['n']}</b>\n"
        f"Подписаны на рассылку: <b>{subscribed_row['n']}</b>\n"
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


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    await state.set_state(BroadcastState.waiting_message)
    count = await broadcast_user_count()
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "📣 <b>Новая рассылка</b>\n\n"
            "Отправь следующим сообщением текст, фото или видео.\n\n"
            f"Получателей сейчас: <b>{count}</b>\n\n"
            "Перед отправкой бот попросит подтверждение.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]]
            ),
        )


@router.message(Command("broadcast"))
async def broadcast_command(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await state.clear()
    await state.set_state(BroadcastState.waiting_message)
    count = await broadcast_user_count()
    await message.answer(
        "📣 <b>Новая рассылка</b>\n\n"
        "Отправь следующим сообщением текст, фото или видео.\n\n"
        f"Получателей сейчас: <b>{count}</b>.",
    )


@router.message(BroadcastState.waiting_message)
async def capture_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    await state.update_data(
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
    )
    await state.set_state(BroadcastState.confirm)
    count = await broadcast_user_count()
    await message.answer(
        "✅ Сообщение сохранено для рассылки.\n\n"
        f"Получателей: <b>{count}</b>\n"
        "Нажми кнопку ниже, чтобы начать отправку.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Отправить всем", callback_data="broadcast_send")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
            ]
        ),
    )


@router.callback_query(BroadcastState.confirm, F.data == "broadcast_send")
async def send_broadcast(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    data = await state.get_data()
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    if not source_chat_id or not source_message_id:
        await state.clear()
        return await call.answer("Сообщение для рассылки потеряно", show_alert=True)

    await call.answer("Рассылка запущена")
    if call.message:
        await call.message.edit_text("📣 Рассылка запущена…")

    sent = 0
    failed = 0
    for user_id in await subscribed_user_ids():
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=int(source_chat_id),
                message_id=int(source_message_id),
            )
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 1.0)
            try:
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=int(source_chat_id),
                    message_id=int(source_message_id),
                )
                sent += 1
            except TelegramAPIError:
                failed += 1
        except TelegramForbiddenError:
            failed += 1
            await set_subscription(user_id, False)
        except TelegramAPIError:
            failed += 1
        await asyncio.sleep(0.04)

    await state.clear()
    text = f"✅ Рассылка завершена.\n\nОтправлено: <b>{sent}</b>\nОшибок: <b>{failed}</b>"
    if call.message:
        await call.message.edit_text(text, reply_markup=admin_kb())
    else:
        await bot.send_message(call.from_user.id, text, reply_markup=admin_kb())


@router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    await call.answer("Отменено")
    if call.message:
        await call.message.edit_text("❌ Рассылка отменена.", reply_markup=admin_kb())


@router.message(Command("unsubscribe"))
async def unsubscribe(message: Message):
    if message.from_user:
        await set_subscription(message.from_user.id, False)
        await message.answer("🔕 Рекламные и информационные рассылки отключены. Вернуть: /subscribe")


@router.message(Command("subscribe"))
async def subscribe(message: Message):
    if message.from_user:
        await set_subscription(message.from_user.id, True)
        await message.answer("🔔 Рассылки включены.")


@router.message(Command("paysupport"))
async def support(message: Message):
    if SUPPORT:
        await message.answer(f"Поддержка: <b>{html.escape(SUPPORT)}</b>")
    else:
        await message.answer("Напиши владельцу магазина.")


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id if message.from_user else None):
        await message.answer("❌ Действие отменено.", reply_markup=admin_kb())
    else:
        await message.answer("❌ Действие отменено.")


async def main():
    await init_db()
    tg_bot = Bot(
        TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            protect_content=True,
        ),
    )
    dp = Dispatcher()
    dp.update.outer_middleware(UserTrackingMiddleware())
    dp.include_router(router)
    await tg_bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(tg_bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
