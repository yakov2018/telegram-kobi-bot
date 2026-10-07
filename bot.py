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

# טעינה וניקוי אוטומטי של טוקן הבוט ממשתני הסביבה
RAW_TOKEN = os.getenv("BOT_TOKEN", "")
TOKEN = RAW_TOKEN.strip().replace("[", "").replace("]", "").replace("'", "").replace('"', "")

print(f"DEBUG_CHECK -> Cleaned Token: '{TOKEN}'")

if not TOKEN:
    print("שגיאה קריטית: משתנה הסביבה BOT_TOKEN לא הוגדר או שהוא ריק לחלוטין!")
    sys.exit(1)

# הגדרת מזהה האדמין שלך
ADMIN_ID = 552821474

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

    # בסיס מקלדת למשתמש רגיל
    keyboard_buttons = [
        [types.KeyboardButton(text="🚗 הזמן נסיעה")],
        [types.KeyboardButton(text="👤 פרופיל אישי"), types.KeyboardButton(text="📞 צור קשר")]
    ]

    # הוספת פאנל אדמין אך ורק לך לפי ה-ID
    if message.from_user.id == ADMIN_ID:
        keyboard_buttons.append([types.KeyboardButton(text="🛠️ פאנל אדמין")])

    keyboard = types.ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    await message.answer(
        f"שלום {message.from_user.first_name}! ברוך הבא למערכת ניהול הנסיעות והלוגיסטיקה.\nבחר פעולה מהתפריט:",
        reply_markup=keyboard
    )

# --- פאנל ניהול לאדמין ---
@dp.message(F.text == "🛠️ פאנל אדמין")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("אין לך הרשאה לבצע פעולה זו.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            users_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM rides") as cursor:
            rides_count = (await cursor.fetchone())[0]

    admin_text = (
        f"🛠️ **פאנל ניהול מערכת (אדמין)**\n\n"
        f"👥 סך הכל משתמשים: <code>{users_count}</code>\n"
        f"🚗 סך הכל נסיעות במערכת: <code>{rides_count}</code>\n\n"
        f"בחר פעולה מהרשימה:"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="📋 צפה בכל הנסיעות האחרונות", callback_data="admin_view_rides")]
        ]
    )
    await message.answer(admin_text, reply_markup=keyboard)

# --- הצגת נסיעות דרך כפתור אינליין ---
@dp.callback_query(F.data == "admin_view_rides")
async def admin_view_rides_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("אין הרשאה!", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT ride_id, client_id, origin, destination, status FROM rides ORDER BY ride_id DESC LIMIT 5") as cursor:
            rides = await cursor.fetchall()

    if not rides:
        await callback.message.answer("אין עדיין נסיעות רשומות במערכת.")
        await callback.answer()
        return

    response_text = "📋 **5 הנסיעות האחרונות במערכת:**\n\n"
    for r in rides:
        response_text += f"🆔 מזהה נסיעה: <code>{r[0]}</code>\n👤 מזהה לקוח: <code>{r[1]}</code>\n📍 מוצא: {r[2]}\n🏁 יעד: {r[3]}\n📌 סטטוס: {r[4]}\n-------------------\n"

    await callback.message.answer(response_text)
    await callback.answer()

# --- טיפול בלחצני התפריט הרגילים ---
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
