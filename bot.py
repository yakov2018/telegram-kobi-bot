import asyncio
import logging
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import aiosqlite
import os

# הגדרת לוגים
logging.basicConfig(level=logging.INFO)

# טעינת טוקן הבוט ממשתני הסביבה
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN or TOKEN.strip() == "":
    print("שגיאה קריטית: משתנה הסביבה BOT_TOKEN לא הוגדר או שהוא ריק לחלוטין!")
    sys.exit(1)

# אתחול הבוט וה-Dispatcher
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

DB_PATH = "bot_database_v3.db"

# --- אתחול מסד הנתונים ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'client'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rides (
                ride_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                origin TEXT,
                destination TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        await db.commit()

# --- מצבי FSM לדוגמה ---
class RideState(StatesGroup):
    waiting_for_origin = State()
    waiting_for_destination = State()

# --- פקודת התחלה ---
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)",
            (message.from_user.id, message.from_user.full_name)
        )
        await db.commit()

    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🚗 הזמן נסיעה")],
            [types.KeyboardButton(text="👤 פרופיל אישי"), types.KeyboardButton(text="📞 צור קשר")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"שלום {message.from_user.first_name}! ברוך הבא למערכת ניהול הנסיעות והלוגיסטיקה.\nבחר פעולה מהתפריט:",
        reply_markup=keyboard
    )

# --- טיפול בלחצני התפריט ---
@dp.message(F.text == "🚗 הזמן נסיעה")
async def start_ride_process(message: types.Message, state: FSMContext):
    await state.set_state(RideState.waiting_for_origin)
    await message.answer("נא הזן את נקודת האיסוף (מוצא):")

@dp.message(RideState.waiting_for_origin)
async def process_origin(message: types.Message, state: FSMContext):
    await state.update_data(origin=message.text)
    await state.set_state(RideState.waiting_for_destination)
    await message.answer("לאן אתה רוצה לנסוע? (יעד):")

@dp.message(RideState.waiting_for_destination)
async def process_destination(message: types.Message, state: FSMContext):
    data = await state.get_data()
    origin = data.get("origin")
    destination = message.text
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO rides (client_id, origin, destination) VALUES (?, ?, ?)",
            (user_id, origin, destination)
        )
        await db.commit()

    await state.clear()
    await message.answer(f"✅ הנסיעה נקלטה בהצלחה!\nממוצא: {origin}\nליעד: {destination}\nמחפשים לך נהג...")

# --- שרת WEB קליל בשביל Render ---
async def handle(request):
    return web.Response(text="Bot is running smoothly!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server is running on port {port}")

# --- הפעלה ראשית ---
async def main():
    await init_db()
    
    asyncio.create_task(start_web_server())

    await bot.delete_webhook(drop_pending_updates=True)
    
    print("Bot is starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
