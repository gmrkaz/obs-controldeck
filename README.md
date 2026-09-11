# Telegram Video Store

BotHost-ready Telegram video store with Telegram Stars payments.

Branch: `video-store-bot`

Required env vars:
- `BOT_TOKEN`
- `ADMIN_ID=6296843729`
- `DB_PATH=/app/data/store.db`
- `SUPPORT_USERNAME=@your_username`

Start file: `bot.py`

Add a product by sending a video to the bot with caption:

`#add Category | Title | 150 | Description`

CI: installs dependencies on Python 3.11, compiles `bot.py`, and runs a SQLite smoke test.
