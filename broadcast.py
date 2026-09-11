import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import aiosqlite
from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    User,
)

DB_PATH = os.getenv("DB_PATH", "/app/data/store.db").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

broadcast_router = Router(name="broadcast")
logger = logging.getLogger(__name__)


class BroadcastState(StatesGroup):
    waiting_message = State()
    confirm = State()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id == ADMIN_ID)


async def open_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_broadcast_db():
    db = await open_db()
    try:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcast_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscribed INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )
        await db.commit()
    finally:
        await db.close()


async def upsert_user(user: User):
    stamp = now()
    db = await open_db()
    try:
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
    finally:
        await db.close()


async def set_subscription(user_id: int, subscribed: bool):
    db = await open_db()
    try:
        await db.execute(
            "UPDATE broadcast_users SET subscribed = ?, last_seen = ? WHERE user_id = ?",
            (1 if subscribed else 0, now(), user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def subscribed_user_ids() -> list[int]:
    db = await open_db()
    try:
        rows = await (
            await db.execute(
                "SELECT user_id FROM broadcast_users WHERE subscribed = 1 ORDER BY user_id"
            )
        ).fetchall()
        return [int(row["user_id"]) for row in rows]
    finally:
        await db.close()


async def broadcast_user_count() -> int:
    db = await open_db()
    try:
        row = await (
            await db.execute(
                "SELECT COUNT(*) AS n FROM broadcast_users WHERE subscribed = 1"
            )
        ).fetchone()
        return int(row["n"])
    finally:
        await db.close()


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


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
        ]
    )


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Отправить всем", callback_data="broadcast_send")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
        ]
    )


async def begin_broadcast_message(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(BroadcastState.waiting_message)
    count = await broadcast_user_count()
    await message.answer(
        "📣 <b>Новая рассылка</b>\n\n"
        "Отправь следующим сообщением то, что нужно разослать. "
        "Можно отправить обычный текст, фото или видео.\n\n"
        f"Сейчас подписано пользователей: <b>{count}</b>\n\n"
        "Перед отправкой бот ещё раз попросит подтверждение.",
        reply_markup=cancel_kb(),
    )


@broadcast_router.message(Command("broadcast"))
async def broadcast_command(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await begin_broadcast_message(message, state)


@broadcast_router.callback_query(F.data == "admin_broadcast")
async def broadcast_button(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()
    await state.clear()
    await state.set_state(BroadcastState.waiting_message)
    count = await broadcast_user_count()
    if call.message:
        await call.message.edit_text(
            "📣 <b>Новая рассылка</b>\n\n"
            "Отправь следующим сообщением то, что нужно разослать. "
            "Можно отправить обычный текст, фото или видео.\n\n"
            f"Сейчас подписано пользователей: <b>{count}</b>\n\n"
            "Перед отправкой бот ещё раз попросит подтверждение.",
            reply_markup=cancel_kb(),
        )


@broadcast_router.message(BroadcastState.waiting_message)
async def capture_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        await state.clear()
        return

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
        reply_markup=confirm_kb(),
    )


@broadcast_router.callback_query(BroadcastState.confirm, F.data == "broadcast_send")
async def send_broadcast(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    if not source_chat_id or not source_message_id:
        await state.clear()
        await call.answer("Сообщение для рассылки потеряно", show_alert=True)
        return

    await call.answer("Рассылка запущена")
    if call.message:
        await call.message.edit_text("📣 Рассылка запущена…")

    user_ids = await subscribed_user_ids()
    sent = 0
    failed = 0

    for user_id in user_ids:
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

        await asyncio.sleep(0.06)

    await state.clear()
    result = (
        "✅ <b>Рассылка завершена</b>\n\n"
        f"Отправлено: <b>{sent}</b>\n"
        f"Не доставлено: <b>{failed}</b>"
    )
    if call.message:
        await call.message.edit_text(result)
    else:
        await bot.send_message(ADMIN_ID, result)


@broadcast_router.callback_query(F.data == "broadcast_cancel")
async def cancel_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await call.answer("Отменено")
    if call.message:
        await call.message.edit_text("❌ Рассылка отменена.\n\nНапиши /admin, чтобы вернуться в админку.")


@broadcast_router.message(Command("unsubscribe"))
async def unsubscribe(message: Message):
    if not message.from_user:
        return
    await upsert_user(message.from_user)
    await set_subscription(message.from_user.id, False)
    await message.answer(
        "🔕 Рассылки отключены. Покупки и работа магазина продолжат работать.\n"
        "Чтобы включить их снова — /subscribe"
    )


@broadcast_router.message(Command("subscribe"))
async def subscribe(message: Message):
    if not message.from_user:
        return
    await upsert_user(message.from_user)
    await set_subscription(message.from_user.id, True)
    await message.answer("🔔 Рассылки снова включены. Чтобы отключить — /unsubscribe")
