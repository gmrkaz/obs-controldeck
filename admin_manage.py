import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import bot as store

admin_manage_router = Router(name="admin_manage")


class AdminEditState(StatesGroup):
    create_category = State()
    rename_category = State()
    edit_product_title = State()
    edit_product_price = State()
    edit_product_description = State()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id == store.ADMIN_ID)


def full_admin_kb() -> InlineKeyboardMarkup:
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


async def categories_admin_kb() -> InlineKeyboardMarkup:
    rows = []
    for item in await store.categories():
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
    async with store.conn() as db:
        rows_db = await (
            await db.execute(
                """
                SELECT p.id, p.title, p.stars, c.name AS category_name
                FROM products p
                JOIN categories c ON c.id = p.category_id
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


@admin_manage_router.callback_query(F.data == "admin_categories")
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


@admin_manage_router.callback_query(F.data == "admin_cat_create")
async def admin_cat_create(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(AdminEditState.create_category)
    await call.answer()
    if call.message:
        await call.message.edit_text(
            "➕ <b>Новая категория</b>\n\nОтправь название новой категории.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_categories")
            ]]),
        )


@admin_manage_router.message(AdminEditState.create_category)
async def admin_cat_create_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        return await message.answer("❌ Название должно быть от 1 до 64 символов.")
    await store.get_cat(name)
    await state.clear()
    await message.answer("✅ Категория создана.", reply_markup=await categories_admin_kb())


@admin_manage_router.callback_query(F.data.startswith("admin_cat:"))
async def admin_cat_detail(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    try:
        category_id = int((call.data or "").split(":", 1)[1])
    except ValueError:
        return await call.answer("Ошибка категории", show_alert=True)
    async with store.conn() as db:
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


@admin_manage_router.callback_query(F.data.startswith("admin_cat_rename:"))
async def admin_cat_rename(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    category_id = int((call.data or "").split(":", 1)[1])
    await state.set_state(AdminEditState.rename_category)
    await state.update_data(category_id=category_id)
    await call.answer()
    if call.message:
        await call.message.edit_text("✏️ Отправь новое название категории.")


@admin_manage_router.message(AdminEditState.rename_category)
async def admin_cat_rename_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id if message.from_user else None):
        return await state.clear()
    data = await state.get_data()
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        return await message.answer("❌ Название должно быть от 1 до 64 символов.")
    try:
        async with store.conn() as db:
            await db.execute("UPDATE categories SET name = ? WHERE id = ?", (name, int(data['category_id'])))
            await db.commit()
    except Exception:
        return await message.answer("❌ Такое название уже используется.")
    await state.clear()
    await message.answer("✅ Категория переименована.", reply_markup=await categories_admin_kb())


@admin_manage_router.callback_query(F.data.startswith("admin_cat_delete:"))
async def admin_cat_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    category_id = int((call.data or "").split(":", 1)[1])
    async with store.conn() as db:
        await db.execute("UPDATE categories SET active = 0 WHERE id = ?", (category_id,))
        await db.execute("UPDATE products SET active = 0 WHERE category_id = ?", (category_id,))
        await db.commit()
    await call.answer("Категория скрыта")
    if call.message:
        await call.message.edit_text("✅ Категория и её видео скрыты.", reply_markup=await categories_admin_kb())


@admin_manage_router.callback_query(F.data == "admin_products")
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


@admin_manage_router.callback_query(F.data.startswith("admin_product:"))
async def admin_product_detail(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    product_id = int((call.data or "").split(":", 1)[1])
    item = await store.product(product_id)
    if not item:
        return await call.answer("Видео не найдено", show_alert=True)
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"admin_product_title:{product_id}"), InlineKeyboardButton(text="⭐ Цена", callback_data=f"admin_product_price:{product_id}")],
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


async def start_product_edit(call: CallbackQuery, state: FSMContext, state_value: State, product_id: int, prompt: str):
    await state.set_state(state_value)
    await state.update_data(product_id=product_id)
    await call.answer()
    if call.message:
        await call.message.edit_text(prompt)


@admin_manage_router.callback_query(F.data.startswith("admin_product_title:"))
async def edit_product_title(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await start_product_edit(call, state, AdminEditState.edit_product_title, int((call.data or '').split(':',1)[1]), "✏️ Отправь новое название видео.")


@admin_manage_router.callback_query(F.data.startswith("admin_product_price:"))
async def edit_product_price(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await start_product_edit(call, state, AdminEditState.edit_product_price, int((call.data or '').split(':',1)[1]), "⭐ Отправь новую цену в Stars (1–25000).")


@admin_manage_router.callback_query(F.data.startswith("admin_product_desc:"))
async def edit_product_desc(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await start_product_edit(call, state, AdminEditState.edit_product_description, int((call.data or '').split(':',1)[1]), "📝 Отправь новое описание видео.")


@admin_manage_router.message(AdminEditState.edit_product_title)
async def edit_product_title_value(message: Message, state: FSMContext):
    data = await state.get_data(); value = (message.text or '').strip()
    if not is_admin(message.from_user.id if message.from_user else None): return await state.clear()
    if not value or len(value) > 120: return await message.answer("❌ Название: 1–120 символов.")
    async with store.conn() as db:
        await db.execute("UPDATE products SET title = ? WHERE id = ?", (value, int(data['product_id']))); await db.commit()
    await state.clear(); await message.answer("✅ Название изменено.", reply_markup=await products_admin_kb())


@admin_manage_router.message(AdminEditState.edit_product_price)
async def edit_product_price_value(message: Message, state: FSMContext):
    data = await state.get_data()
    if not is_admin(message.from_user.id if message.from_user else None): return await state.clear()
    try: value = int((message.text or '').strip())
    except ValueError: return await message.answer("❌ Отправь число от 1 до 25000.")
    if not 1 <= value <= 25000: return await message.answer("❌ Цена должна быть от 1 до 25000 Stars.")
    async with store.conn() as db:
        await db.execute("UPDATE products SET stars = ? WHERE id = ?", (value, int(data['product_id']))); await db.commit()
    await state.clear(); await message.answer("✅ Цена изменена.", reply_markup=await products_admin_kb())


@admin_manage_router.message(AdminEditState.edit_product_description)
async def edit_product_desc_value(message: Message, state: FSMContext):
    data = await state.get_data(); value = (message.text or '').strip()
    if not is_admin(message.from_user.id if message.from_user else None): return await state.clear()
    if len(value) > 1000: return await message.answer("❌ Описание максимум 1000 символов.")
    async with store.conn() as db:
        await db.execute("UPDATE products SET description = ? WHERE id = ?", (value, int(data['product_id']))); await db.commit()
    await state.clear(); await message.answer("✅ Описание изменено.", reply_markup=await products_admin_kb())


@admin_manage_router.callback_query(F.data.startswith("admin_product_delete:"))
async def admin_product_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа", show_alert=True)
    product_id = int((call.data or "").split(":", 1)[1])
    async with store.conn() as db:
        await db.execute("UPDATE products SET active = 0 WHERE id = ?", (product_id,))
        await db.commit()
    await call.answer("Видео скрыто")
    if call.message:
        await call.message.edit_text("✅ Видео скрыто из магазина.", reply_markup=await products_admin_kb())
