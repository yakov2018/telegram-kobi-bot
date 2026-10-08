import os
import asyncio
import logging
import sys
import re
from datetime import datetime, timedelta
import aiosqlite
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

RAW_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_TOKEN = RAW_TOKEN.strip().replace("[", "").replace("]", "").replace("'", "").replace('"', "").replace(" ", "")

if not BOT_TOKEN:
    sys.exit(1)

ADMIN_IDS = [8644923212, 552821474]
DB_FILE = 'bot_database_v6.db'

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

async def handle_ping(request):
    return web.Response(text="Bot is running and alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_birth_year = State()
    waiting_phone = State()
    waiting_car_brand = State()
    waiting_car_model = State()
    waiting_car_year = State()
    waiting_car_seats = State()

class BotStates(StatesGroup):
    waiting_add_city = State()
    waiting_append_city = State()
    waiting_new_radius = State()
    waiting_lead_text = State()
    waiting_lead_phone = State()
    waiting_driver_time = State()
    waiting_station_name_input = State()
    waiting_manual_close_driver = State()
    waiting_edit_lead_text = State()
    waiting_edit_lead_price = State()
    waiting_broadcast_text = State()
    waiting_debt_cancel_reason = State()

CAR_DATABASE = {
    "טויוטה (Toyota)": {"קורולה": list(range(1995, 2027)), "יאריס": list(range(1999, 2027)), "C-HR": list(range(2017, 2027)), "ראב 4": list(range(1995, 2027))},
    "יונדאי (Hyundai)": {"אלנטרה": list(range(1995, 2027)), "איוניק": list(range(2016, 2023)), "טוסון": list(range(2004, 2027))},
    "קיה (Kia)": {"פיקנטו": list(range(2011, 2027)), "ספורטאז'": list(range(1995, 2027)), "נירו": list(range(2016, 2027))},
    "אחר (הקלדה ידנית)": {}
}

ISRAELI_CITIES = ["ירושלים", "תל אביב", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה", "בני ברק", "באר שבע", "חולון", "רמת גן", "מודיעין עילית"]
CITY_ALIASES = {"ים": "ירושלים", "פת": "פתח תקווה", "תא": "תל אביב", "סבא": "כפר סבא", "ראשון": "ראשון לציון", "רג": "רמת גן", "שמש": "בית שמש", "בב": "בני ברק", "ספר": "מודיעין עילית"}

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT, birth_date TEXT, car_brand TEXT, car_model TEXT, car_year TEXT, car_seats INTEGER DEFAULT 4, status TEXT DEFAULT 'busy', expiry_date TEXT, role TEXT DEFAULT 'user', station_id INTEGER DEFAULT 0, radius INTEGER DEFAULT 0, cities TEXT DEFAULT '', total_trips INTEGER DEFAULT 0, rating REAL DEFAULT 0.0, rating_count INTEGER DEFAULT 0, is_blocked INTEGER DEFAULT 0)''')
        await db.execute('CREATE TABLE IF NOT EXISTS stations (station_id INTEGER PRIMARY KEY AUTOINCREMENT, station_name TEXT, owner_id INTEGER, commission_percent REAL DEFAULT 10.0)')
        await db.execute('CREATE TABLE IF NOT EXISTS bot_groups (group_id INTEGER PRIMARY KEY, group_title TEXT, is_active INTEGER DEFAULT 1)')
        await db.execute('CREATE TABLE IF NOT EXISTS driver_debts (debt_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, station_id INTEGER, amount REAL, order_id INTEGER, order_text TEXT, publisher_name TEXT, publisher_username TEXT, is_paid INTEGER DEFAULT 0, date TEXT, publisher_id INTEGER DEFAULT 0, original_price REAL DEFAULT 0.0, comm_percent REAL DEFAULT 10.0)')
        await db.execute('CREATE TABLE IF NOT EXISTS leads (lead_id INTEGER PRIMARY KEY AUTOINCREMENT, publisher_id INTEGER, message_text TEXT, phone_number TEXT, status TEXT DEFAULT "active", closed_with TEXT DEFAULT NULL, created_at TEXT, price REAL DEFAULT 0.0, route_cities TEXT DEFAULT "", station_id INTEGER DEFAULT NULL, is_in_progress INTEGER DEFAULT 0)')
        await db.commit()

async def get_user_dict(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))).fetchone()

async def check_user_auth(user_id):
    user = await get_user_dict(user_id)
    if not user: return "new"
    if user['is_blocked']: return "blocked"
    if user['role'] != 'admin':
        try:
            if datetime.now() > datetime.strptime(user['expiry_date'], '%Y-%m-%d %H:%M:%S'): return "expired"
        except: pass
    return "ok"

def get_main_keyboard(user_id, role='user', current_status='busy'):
    is_admin = (user_id in ADMIN_IDS or role == 'admin')
    is_station_mgr = is_admin or role == 'station_manager'
    is_dispatcher = is_station_mgr or role == 'dispatcher'
    
    kb = []
    if is_dispatcher: kb.append([KeyboardButton(text="📢 פרסום הודעה"), KeyboardButton(text="📋 מצב קריאות")])
    if is_station_mgr and not is_admin: kb.append([KeyboardButton(text="🏢 ניהול התחנה שלי")])
    kb.append([KeyboardButton(text="🟢 פנוי לקריאות" if current_status == 'free' else "🔴 תפוס"), KeyboardButton(text="⚙️ הגדרת אזורים ורדיוס")])
    kb.append([KeyboardButton(text="💳 חיובים"), KeyboardButton(text="💎 מצב מנוי ופרופיל")])
    kb.append([KeyboardButton(text="ℹ️ אודות ויצירת קשר")])
    if is_admin: kb.append([KeyboardButton(text="🛠️ פאנל מנהל")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    auth_status = await check_user_auth(user_id)
    is_admin = (user_id in ADMIN_IDS)
    
    if is_admin and auth_status == "new":
        async with aiosqlite.connect(DB_FILE) as db:
            expiry = (datetime.now() + timedelta(days=3650)).strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, "busy", ?, "admin")', 
                             (user_id, "מנהל מערכת", "0000000000", "2000-01-01", "מרצדס", "S-Class", "2025", 4, expiry))
            await db.commit()
        auth_status = "ok"

    if auth_status == "blocked": return await message.answer("❌ חשבונך חסום.")
    if auth_status == "expired": return await message.answer("❌ **פג תוקף המנוי!**")

    user = await get_user_dict(user_id)
    role_val = user['role'] if user else ('admin' if is_admin else 'user')
    current_status = user['status'] if user else 'busy'

    if auth_status == "new":
        if not message.from_user.username: return await message.answer("⚠️ חובה להגדיר שם משתמש בטלגרם.")
        await state.set_state(RegistrationStates.waiting_name)
        return await message.answer("👋 שלום וברוכים הבאים!\nאנא שלח את **השם המלא** שלך:")

    await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(user_id, role_val, current_status))

@dp.message()
async def handle_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    current_state = await state.get_state()

    if text in ["/start", "תפריט", "⬅️ חזרה לתפריט הראשי", "⬅ חזרה", "❌ ביטול"]:
        await state.clear()
        user = await get_user_dict(user_id)
        if user:
            return await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(user_id, user['role'], user['status']))
        else:
            await state.set_state(RegistrationStates.waiting_name)
            return await message.answer("👋 אנא שלח את **השם המלא** שלך:")

    # --- ניהול שלבי ההרשמה ---
    if current_state == RegistrationStates.waiting_name.state:
        await state.update_data(reg_name=text)
        await state.set_state(RegistrationStates.waiting_birth_year)
        return await message.answer("📅 באיזו **שנת לידה** נולדת? (מספר בלבד, למשל 1995):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה")]], resize_keyboard=True))

    if current_state == RegistrationStates.waiting_birth_year.state:
        if not text.isdigit() or not (1920 <= int(text) <= 2026):
            return await message.answer("⚠️ נא להזין שנת לידה חוקית במספרים בלבד.")
        if 2026 - int(text) < 18:
            await state.clear()
            return await message.answer("❌ **שגיאה:** המערכת מיועדת לגילאי 18 ומעלה בלבד.")
        
        await state.update_data(reg_birth_year=text)
        await state.set_state(RegistrationStates.waiting_phone)
        return await message.answer("📱 לחץ על הכפתור למטה כדי **לשתף את מספר הטלפון** (חובה):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 שיתוף מספר טלפון", request_contact=True), KeyboardButton(text="⬅️ חזרה")]], resize_keyboard=True))

    if current_state == RegistrationStates.waiting_phone.state:
        if not message.contact:
            return await message.answer("⚠️ חובה ללחוץ על כפתור שיתוף מספר הטלפון למטה.")
        await state.update_data(reg_phone=message.contact.phone_number)
        await state.set_state(RegistrationStates.waiting_car_brand)
        return await message.answer("🚗 בחר **חברת רכב**:", reply_markup=create_keyboard(list(CAR_DATABASE.keys()), columns=2))

    if current_state == RegistrationStates.waiting_car_brand.state:
        await state.update_data(reg_car_brand=text)
        await state.set_state(RegistrationStates.waiting_car_model)
        if text in CAR_DATABASE and text != "אחר (הקלדה ידנית)":
            return await message.answer(f"בחר דגם עבור **{text}**:", reply_markup=create_keyboard(list(CAR_DATABASE[text].keys()), columns=2))
        return await message.answer("✍️ הקלד ידנית את **דגם הרכב**:")

    if current_state == RegistrationStates.waiting_car_model.state:
        await state.update_data(reg_car_model=text)
        await state.set_state(RegistrationStates.waiting_car_year)
        return await message.answer("📅 הקלד את **שנת הרכב** (למשל 2020):")

    if current_state == RegistrationStates.waiting_car_year.state:
        if not text.isdigit(): return await message.answer("⚠️ נא להזין מספר שנת רכב.")
        await state.update_data(reg_car_year=text)
        await state.set_state(RegistrationStates.waiting_car_seats)
        return await message.answer("💺 כמה **מקומות ישיבה** (4-50)?", reply_markup=create_keyboard(["4", "5", "6", "7", "10"], columns=3))

    if current_state == RegistrationStates.waiting_car_seats.state:
        seats_val = int(text) if text.isdigit() and 4 <= int(text) <= 50 else 4
        data = await state.get_data()
        expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('''INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'busy', ?, 'admin')''', 
                             (user_id, data.get('reg_name'), data.get('reg_phone'), data.get('reg_birth_year'), data.get('reg_car_brand'), data.get('reg_car_model'), data.get('reg_car_year'), seats_val, expiry))
            await db.commit()

        await state.clear()
        user = await get_user_dict(user_id)
        return await message.answer("✅ **ההרשמה הושלמה בהצלחה!** מנוי הופעל.", reply_markup=get_main_keyboard(user_id, user['role'], user['status']))

    # --- משתמש רשום לחלוטין ---
    user = await get_user_dict(user_id)
    if not user:
        await state.set_state(RegistrationStates.waiting_name)
        return await message.answer("👋 אנא שלח את **השם המלא** שלך:")

    is_admin = (user_id in ADMIN_IDS)
    role_val = user['role']
    current_status = user['status']

    if text == "ℹ️ אודות ויצירת קשר":
        return await message.answer("ℹ️ מערכת ניהול ושילוח חכמה בטלגרם.\nלפניות תמיכה פנה למנהל.", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    if text in ["🛠️ פאנל מנהל", "פאנל מנהל"] and is_admin:
        return await message.answer("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())

    if text == "💎 מצב מנוי ופרופיל":
        return await message.answer(f"💎 **הפרופיל שלך:**\n\n👤 שם: {user['full_name']}\n🛡️ תפקיד: **{role_val}**\n📅 תוקף: {user['expiry_date']}", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    if text == "💳 חיובים":
        return await message.answer("💳 אין לך חיובים פתוחים לתשלום.", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    await message.answer("🎛️ בחר אפשרות מהתפריט:", reply_markup=get_main_keyboard(user_id, role_val, current_status))

def create_keyboard(items, columns=3, add_back=True):
    kb, row = [], []
    for item in items:
        row.append(KeyboardButton(text=str(item)))
        if len(row) == columns:
            kb.append(row)
            row = []
    if row: kb.append(row)
    if add_back: kb.append([KeyboardButton(text="⬅️ חזרה")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 ניהול משתמשים"), KeyboardButton(text="📊 סטטיסטיקות מערכת")],
        [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
    ], resize=True)

async def main():
    await init_db()
    await start_web_server()
    print("✨ בוט פועל בצורה מושלמת!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
