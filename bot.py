import asyncio, html, logging, os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
TOKEN=os.getenv('BOT_TOKEN','').strip(); ADMIN_ID=int(os.getenv('ADMIN_ID','0'))
DB_PATH=os.getenv('DB_PATH','/app/data/store.db').strip(); SUPPORT=os.getenv('SUPPORT_USERNAME','').strip()
if not TOKEN: raise RuntimeError('BOT_TOKEN is missing')
if not ADMIN_ID: raise RuntimeError('ADMIN_ID is missing')
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO)
r=Router()

def now(): return datetime.now(timezone.utc).isoformat()
async def conn():
    db=await aiosqlite.connect(DB_PATH); db.row_factory=aiosqlite.Row; await db.execute('PRAGMA foreign_keys=ON'); return db
async def init_db():
    async with await conn() as db:
        await db.executescript('''
        CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE COLLATE NOCASE,active INTEGER DEFAULT 1,created_at TEXT);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,category_id INTEGER,title TEXT,description TEXT DEFAULT '',stars INTEGER CHECK(stars BETWEEN 1 AND 25000),file_id TEXT,active INTEGER DEFAULT 1,created_at TEXT,FOREIGN KEY(category_id) REFERENCES categories(id));
        CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,product_id INTEGER,stars_paid INTEGER,charge_id TEXT,purchased_at TEXT,UNIQUE(user_id,product_id),FOREIGN KEY(product_id) REFERENCES products(id));
        '''); await db.commit()
async def get_cat(name):
    async with await conn() as db:
        row=await (await db.execute('SELECT id FROM categories WHERE name=? COLLATE NOCASE',(name,))).fetchone()
        if row: await db.execute('UPDATE categories SET active=1 WHERE id=?',(row['id'],)); await db.commit(); return row['id']
        cur=await db.execute('INSERT INTO categories(name,created_at) VALUES(?,?)',(name,now())); await db.commit(); return cur.lastrowid
async def categories():
    async with await conn() as db: return await (await db.execute('SELECT c.id,c.name,COUNT(p.id) n FROM categories c LEFT JOIN products p ON p.category_id=c.id AND p.active=1 WHERE c.active=1 GROUP BY c.id ORDER BY c.id')).fetchall()
async def products(cid):
    async with await conn() as db: return await (await db.execute('SELECT * FROM products WHERE category_id=? AND active=1 ORDER BY id DESC',(cid,))).fetchall()
async def product(pid):
    async with await conn() as db: return await (await db.execute('SELECT p.*,c.name category_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.id=? AND p.active=1 AND c.active=1',(pid,))).fetchone()
async def owns(uid,pid):
    async with await conn() as db: return bool(await (await db.execute('SELECT 1 FROM purchases WHERE user_id=? AND product_id=?',(uid,pid))).fetchone())
async def save_purchase(uid,pid,stars,charge):
    async with await conn() as db:
        await db.execute('INSERT INTO purchases(user_id,product_id,stars_paid,charge_id,purchased_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,product_id) DO UPDATE SET stars_paid=excluded.stars_paid,charge_id=excluded.charge_id',(uid,pid,stars,charge,now())); await db.commit()

def main_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🎬 Каталог',callback_data='catalog')],[InlineKeyboardButton(text='🛍 Мои покупки',callback_data='owned')]])
async def cats_kb():
    kb=InlineKeyboardBuilder()
    for x in await categories(): kb.button(text=f"📁 {x['name']} · {x['n']}",callback_data=f"cat:{x['id']}")
    kb.button(text='🛍 Мои покупки',callback_data='owned'); kb.button(text='⬅️ Главное меню',callback_data='home'); kb.adjust(1); return kb.as_markup()
async def products_kb(cid):
    kb=InlineKeyboardBuilder()
    for x in await products(cid): kb.button(text=f"▶️ {x['title']} · ⭐ {x['stars']}",callback_data=f"product:{x['id']}")
    kb.button(text='⬅️ Категории',callback_data='catalog'); kb.adjust(1); return kb.as_markup()
def pay_kb(n): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f'⭐ Оплатить {n} звёзд',pay=True)]])
async def send_video(bot,uid,p): await bot.send_video(uid,p['file_id'],caption=f"✅ <b>{html.escape(p['title'])}</b>\n📁 {html.escape(p['category_name'])}\n\n{html.escape(p['description'] or '')}",protect_content=True,supports_streaming=True)

@r.message(CommandStart())
async def start(m:Message): await m.answer('🎬 <b>Видео-магазин</b>\n\nВыбери категорию и купи видео за Telegram Stars.',reply_markup=main_kb())
@r.callback_query(F.data=='home')
async def home(c:CallbackQuery): await c.answer(); await c.message.edit_text('🎬 <b>Видео-магазин</b>',reply_markup=main_kb())
@r.callback_query(F.data=='catalog')
async def catalog(c:CallbackQuery): await c.answer(); await c.message.edit_text('📚 <b>Категории</b>',reply_markup=await cats_kb())
@r.callback_query(F.data.startswith('cat:'))
async def cat(c:CallbackQuery):
    await c.answer(); cid=int(c.data.split(':')[1]); await c.message.edit_text('🎬 <b>Выбери видео</b>',reply_markup=await products_kb(cid))
@r.callback_query(F.data.startswith('product:'))
async def buy(c:CallbackQuery,bot:Bot):
    await c.answer(); pid=int(c.data.split(':')[1]); p=await product(pid)
    if not p: return await c.answer('Товар недоступен',show_alert=True)
    if await owns(c.from_user.id,pid): return await send_video(bot,c.from_user.id,p)
    title=(p['title'] or 'Видео')[:32]; desc=(p['description'] or f"Видео из категории {p['category_name']}")[:255]
    await bot.send_invoice(c.from_user.id,title,desc,f'product:{pid}','XTR',[LabeledPrice(label=title,amount=p['stars'])],reply_markup=pay_kb(p['stars']),protect_content=True)
@r.pre_checkout_query()
async def checkout(q:PreCheckoutQuery):
    try: pid=int(q.invoice_payload.split(':',1)[1]); p=await product(pid)
    except Exception: p=None
    if q.currency!='XTR' or not p or q.total_amount!=p['stars']: return await q.answer(ok=False,error_message='Товар или цена изменились. Открой карточку заново.')
    if await owns(q.from_user.id,pid): return await q.answer(ok=False,error_message='Ты уже покупал это видео. Открой «Мои покупки».')
    await q.answer(ok=True)
@r.message(F.successful_payment)
async def paid(m:Message,bot:Bot):
    pay=m.successful_payment
    try: pid=int(pay.invoice_payload.split(':',1)[1]); p=await product(pid)
    except Exception: p=None
    if not p or pay.currency!='XTR' or pay.total_amount!=p['stars']: return await m.answer('Платёж получен, но возникла ошибка выдачи. Напиши /paysupport')
    await save_purchase(m.from_user.id,pid,pay.total_amount,pay.telegram_payment_charge_id); await m.answer(f'✅ Оплата прошла — {pay.total_amount} ⭐'); await send_video(bot,m.from_user.id,p)
@r.callback_query(F.data=='owned')
async def owned(c:CallbackQuery):
    await c.answer();
    async with await conn() as db: rows=await (await db.execute('SELECT p.id,p.title FROM purchases x JOIN products p ON p.id=x.product_id WHERE x.user_id=? AND p.active=1 ORDER BY x.id DESC',(c.from_user.id,))).fetchall()
    kb=InlineKeyboardBuilder()
    for x in rows: kb.button(text=f"✅ {x['title']}",callback_data=f"owned:{x['id']}")
    kb.button(text='⬅️ Каталог',callback_data='catalog'); kb.adjust(1)
    await c.message.edit_text('🛍 <b>Мои покупки</b>' if rows else '🛍 <b>Мои покупки</b>\n\nПока пусто.',reply_markup=kb.as_markup())
@r.callback_query(F.data.startswith('owned:'))
async def owned_item(c:CallbackQuery,bot:Bot):
    await c.answer(); pid=int(c.data.split(':')[1])
    if await owns(c.from_user.id,pid): await send_video(bot,c.from_user.id,await product(pid))

@r.message(F.video)
async def add_video(m:Message):
    if not m.from_user or m.from_user.id!=ADMIN_ID: return
    cap=(m.caption or '').strip()
    if not cap.lower().startswith('#add'): return await m.answer('Формат: <code>#add Категория | Название | 150 | Описание</code>')
    parts=[x.strip() for x in cap[4:].strip().split('|')]
    if len(parts)<3: return await m.answer('❌ Формат: <code>#add Категория | Название | 150 | Описание</code>')
    try: stars=int(parts[2])
    except: return await m.answer('❌ Цена должна быть числом.')
    if not 1<=stars<=25000: return await m.answer('❌ Цена: 1–25 000 Stars.')
    cid=await get_cat(parts[0]); desc=' | '.join(parts[3:]) if len(parts)>3 else ''
    async with await conn() as db:
        cur=await db.execute('INSERT INTO products(category_id,title,description,stars,file_id,created_at) VALUES(?,?,?,?,?,?)',(cid,parts[1],desc,stars,m.video.file_id,now())); await db.commit(); pid=cur.lastrowid
    await m.answer(f"✅ Добавлено. ID <code>{pid}</code>\nКнопка: <b>⭐ Оплатить {stars} звёзд</b>")
@r.message(Command('admin'))
async def admin(m:Message):
    if m.from_user and m.from_user.id==ADMIN_ID: await m.answer('🛠 Отправь видео с подписью:\n<code>#add Категория | Название | 150 | Описание</code>\n\n/stats — статистика\n/paysupport — поддержка')
@r.message(Command('stats'))
async def stats(m:Message):
    if not m.from_user or m.from_user.id!=ADMIN_ID: return
    async with await conn() as db:
        p=(await (await db.execute('SELECT COUNT(*) n,COALESCE(SUM(stars_paid),0) s FROM purchases')).fetchone()); v=(await (await db.execute('SELECT COUNT(*) n FROM products WHERE active=1')).fetchone())
    await m.answer(f"📊 Покупок: <b>{p['n']}</b>\nВидео: <b>{v['n']}</b>\nПолучено: ⭐ <b>{p['s']}</b>")
@r.message(Command('paysupport'))
async def support(m:Message): await m.answer(f"Поддержка: <b>{html.escape(SUPPORT)}</b>" if SUPPORT else 'Напиши владельцу магазина.')

async def main():
    await init_db(); bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML,protect_content=True)); dp=Dispatcher(); dp.include_router(r); await bot.delete_webhook(drop_pending_updates=False); await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
if __name__=='__main__': asyncio.run(main())
