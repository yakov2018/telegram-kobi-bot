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
    print("שגיאה קריטית: משתנה הסביבה BOT_TOKEN ריק או לא מוגדר!")
    sys.exit(1)

ADMIN_IDS = [8644923212, 552821474]
DB_FILE = 'bot_database_v5.db'

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

# מאגר רכבים מורחב
CAR_DATABASE = {
    "טויוטה (Toyota)": {"קורולה": list(range(1995, 2027)), "יאריס": list(range(1999, 2027)), "C-HR": list(range(2017, 2027)), "ראב 4": list(range(1995, 2027)), "קאמרי": list(range(1995, 2027)), "לנד קרוזר": list(range(1995, 2027)), "היילקס": list(range(1995, 2027))},
    "יונדאי (Hyundai)": {"אלנטרה": list(range(1995, 2027)), "איוניק": list(range(2016, 2023)), "איוניק 5": list(range(2021, 2027)), "טוסון": list(range(2004, 2027)), "סנטה פה": list(range(2001, 2027)), "i10": list(range(2008, 2027)), "סטאריה": list(range(2021, 2027))},
    "קיה (Kia)": {"פיקנטו": list(range(2011, 2027)), "ספורטאז'": list(range(1995, 2027)), "נירו": list(range(2016, 2027)), "סורנטו": list(range(2002, 2027)), "קרניבל": list(range(1998, 2027)), "סלטוס": list(range(2019, 2027))},
    "מאזדה (Mazda)": {"מאזדה 2": list(range(2007, 2027)), "מאזדה 3": list(range(2004, 2027)), "מאזדה 6": list(range(2003, 2027)), "CX-5": list(range(2012, 2027)), "CX-30": list(range(2019, 2027))},
    "סקודה (Skoda)": {"אוקטביה": list(range(1996, 2027)), "סופרב": list(range(2001, 2027)), "קודיאק": list(range(2016, 2027)), "קארוק": list(range(2017, 2027)), "פאביה": list(range(1999, 2027))},
    "BYD": {"אטו 3 (Atto 3)": list(range(2022, 2027)), "דולפין": list(range(2023, 2027)), "סיל": list(range(2023, 2027))},
    "טסלה (Tesla)": {"מודל 3": list(range(2017, 2027)), "מודל Y": list(range(2020, 2027))},
    "רנו (Renault)": {"קליאו": list(range(1990, 2027)), "מגאן": list(range(1995, 2027)), "טראפיק": list(range(2001, 2027))},
    "אחר (הקלדה ידנית)": {}
}

ISRAELI_CITIES = [
    "ירושלים", "תל אביב", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה", "בני ברק", "באר שבע", "חולון",
    "רמת גן", "אשקלון", "בת ים", "בית שמש", "הרצליה", "כפר סבא", "חדרה", "מודיעין", "מכבים", "רעות", "נצרת", "לוד",
    "רמלה", "רחובות", "מודיעין עילית", "ביתר עילית", "אלעד", "בית שאן", "אופקים", "אריאל", "אילת", "טבריה",
    "דימונה", "הוד השרון", "זכרון יעקב", "טירה", "טמרה", "יבנה", "יהוד", "מונוסון", "יקנעם עילית", "כפר יונה",
    "כפר קאסם", "כרמיאל", "מגדל העמק", "מעלה אדומים", "מעלות", "תרשיחא", "נהריה", "נס ציונה", "נשר", "נתיבות",
    "אור יהודה", "אזור", "אליכין", "אלפי מנשה", "אלקנה", "באר יעקב", "בני עייש", "ג'לג'וליה", "גבעת זאב"
]
CITY_ALIASES = {"ים": "ירושלים", "פת": "פתח תקווה", "תא": "תל אביב", "שדה": "שדה תעופה", "סבא": "כפר סבא", "ראשון": "ראשון לציון", "רג": "רמת גן", "שמש": "בית שמש", "בב": "בני ברק", "ספר": "מודיעין עילית"}

def create_keyboard(items, columns=3, add_back=True):
    kb, row = [], []
    for item in items:
        row.append(KeyboardButton(text=str(item)))
        if len(row) == columns:
            kb.append(row)
            row = []
    if row: kb.append(row)
    if add_back: kb.append([KeyboardButton(text="⬅️ חזרה לתפריט הראשי")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT, birth_date TEXT, car_brand TEXT, car_model TEXT, car_year TEXT, car_seats INTEGER DEFAULT 4, status TEXT DEFAULT 'busy', expiry_date TEXT, role TEXT DEFAULT 'user', station_id INTEGER DEFAULT 0, radius INTEGER DEFAULT 0, cities TEXT DEFAULT '', total_trips INTEGER DEFAULT 0, rating REAL DEFAULT 0.0, rating_count INTEGER DEFAULT 0, is_blocked INTEGER DEFAULT 0)''')
        await db.execute('CREATE TABLE IF NOT EXISTS stations (station_id INTEGER PRIMARY KEY AUTOINCREMENT, station_name TEXT, owner_id INTEGER, commission_percent REAL DEFAULT 10.0)')
        await db.execute('CREATE TABLE IF NOT EXISTS bot_groups (group_id INTEGER PRIMARY KEY, group_title TEXT, is_active INTEGER DEFAULT 1)')
        await db.execute('CREATE TABLE IF NOT EXISTS driver_debts (debt_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, station_id INTEGER, amount REAL, order_id INTEGER, order_text TEXT, publisher_name TEXT, publisher_username TEXT, is_paid INTEGER DEFAULT 0, date TEXT, publisher_id INTEGER DEFAULT 0, original_price REAL DEFAULT 0.0, comm_percent REAL DEFAULT 10.0)')
        await db.execute('CREATE TABLE IF NOT EXISTS leads (lead_id INTEGER PRIMARY KEY AUTOINCREMENT, publisher_id INTEGER, message_text TEXT, phone_number TEXT, status TEXT DEFAULT "active", closed_with TEXT DEFAULT NULL, created_at TEXT, price REAL DEFAULT 0.0, route_cities TEXT DEFAULT "", station_id INTEGER DEFAULT NULL, is_in_progress INTEGER DEFAULT 0)')
        
        try: await db.execute('ALTER TABLE driver_debts ADD COLUMN publisher_id INTEGER DEFAULT 0')
        except: pass
        try: await db.execute('ALTER TABLE driver_debts ADD COLUMN original_price REAL DEFAULT 0.0')
        except: pass
        try: await db.execute('ALTER TABLE driver_debts ADD COLUMN comm_percent REAL DEFAULT 10.0')
        except: pass

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

def parse_order_text(text: str):
    lines = text.strip().split('\n')
    found_cities = []
    price = None
    for line in lines[:2]:
        for alias, full_name in CITY_ALIASES.items():
            if alias in line and full_name not in found_cities: found_cities.append(full_name)
        for city in ISRAELI_CITIES:
            if city in line and city not in found_cities: found_cities.append(city)
    for line in lines[:3]:
        numbers = re.findall(r'\b\d+\b', line)
        for num_str in numbers:
            num = int(num_str)
            if num >= 30 and num % 10 == 0:
                price = float(num)
                break
        if price: break
    has_time = bool(re.search(r'זמנ[ן]{1,6}|זמני[ם]{1,6}', text) or re.search(r'זמן[ן]{1,6}', text))
    return found_cities, price, has_time

def validate_israeli_phone(phone: str):
    clean = re.sub(r'\D', '', phone)
    if len(clean) == 1 and clean.isdigit(): return True
    if len(clean) == 10 and clean.startswith('05'): return True
    if len(clean) == 9 and clean.startswith('0'): return True
    if clean.startswith('972') and len(clean) in [12, 13]: return True
    return False

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

def generate_lead_display(lead_text, lead_id, price, route_cities, pub_name, pub_station, pub_username=""):
    cities = [c.strip() for c in route_cities.split('➔') if c.strip()]
    origin = cities[0] if len(cities) > 0 else "לא זוהה"
    dest = cities[-1] if len(cities) > 1 else "לא זוהה"
    u_disp = f" ({pub_username})" if pub_username else ""
    
    return (
        f"{lead_text}\n\n"
        f"🔖 **מספר קריאה:** #{lead_id}\n"
        f"📍 **מוצא:** {origin}\n"
        f"🏁 **יעד:** {dest}\n"
        f"💰 **מחיר:** ₪{price if price > 0 else 'לא צוין'}\n"
        f"🏢 **תחנה:** {pub_station}\n"
        f"👨‍💻 **סדרן:** {pub_name}{u_disp}"
    )

@dp.my_chat_member()
async def bot_chat_member_handler(event: ChatMemberUpdated):
    chat = event.chat
    if chat.type in ["group", "supergroup"]:
        new_status = event.new_chat_member.status
        async with aiosqlite.connect(DB_FILE) as db:
            if new_status in ["member", "administrator"]:
                await db.execute('INSERT OR REPLACE INTO bot_groups (group_id, group_title, is_active) VALUES (?, ?, 1)', (chat.id, chat.title))
            elif new_status in ["left", "kicked"]:
                await db.execute('UPDATE bot_groups SET is_active = 0 WHERE group_id = ?', (chat.id,))
            await db.commit()

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
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

    if message.text and message.text.startswith("/start lead_"):
        try: lead_id = int(message.text.replace("/start lead_", "").strip())
        except: lead_id = None
        
        if auth_status == "new":
            if not message.from_user.username: return await message.answer("⚠️ חובה שם משתמש בטלגרם כדי לקבל קריאות.")
            await state.update_data(pending_lead=lead_id)
            await state.set_state(RegistrationStates.waiting_name)
            return await message.answer("👋 שלום! אנא שלח את **השם המלא** שלך להרשמה:")
        
        if lead_id:
            async with aiosqlite.connect(DB_FILE) as db:
                db.row_factory = aiosqlite.Row
                lead = await (await db.execute('SELECT status, is_in_progress, message_text FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
            
            if not lead or lead['status'] != 'active': return await message.answer("❌ הקריאה אינה זמינה.")
            _, _, has_time = parse_order_text(lead['message_text'])
            await state.update_data(active_lead_id=lead_id)
            
            msg_prefix = "⚠️ *הסדרן החל שיחה עם נהג אחר, אך בקשתך תועבר.*\n\n" if lead['is_in_progress'] else ""
            if has_time:
                await state.set_state(BotStates.waiting_driver_time)
                await message.answer(f"{msg_prefix}⏱️ **כמה זמן עד שתגיע לכתובת?**", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה")]], resize_keyboard=True))
            else:
                await state.clear()
                await message.answer(f"{msg_prefix}✅ בקשתך נשלחה לסדרן!", reply_markup=get_main_keyboard(user_id, role_val, current_status))
                await process_lead_request_safe(message, user_id, lead_id, "לא צוין זמן")
        return

    if auth_status == "new":
        if not message.from_user.username: return await message.answer("⚠️ חובה להגדיר שם משתמש.")
        await state.set_state(RegistrationStates.waiting_name)
        return await message.answer("👋 שלום! אנא שלח את **השם המלא** שלך:")

    await state.clear()
    await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(user_id, role_val, current_status))

@dp.message()
async def handle_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    auth_status = await check_user_auth(user_id)

    if auth_status == "blocked": return await message.answer("❌ חשבונך חסום.")
    if auth_status == "expired": return await message.answer("❌ **פג תוקף המנוי!**")

    user = await get_user_dict(user_id)
    is_admin = (user_id in ADMIN_IDS)
    role_val = user['role'] if user else ('admin' if is_admin else 'user')
    current_status = user['status'] if user else 'busy'
    text = message.text.strip() if message.text else ""

    if text in ["/start", "תפריט", "⬅️ חזרה לתפריט הראשי", "⬅ חזרה", "❌ ביטול"]:
        await state.clear()
        return await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    current_state = await state.get_state()

    # --- אבטחת הרשמה (18+ ושיתוף טלפון) ---
    if current_state == RegistrationStates.waiting_name.state:
        if text.startswith('/'): return await message.answer("⚠️ נא להזין שם תקין.")
        await state.update_data(reg_name=text)
        await state.set_state(RegistrationStates.waiting_birth_year)
        return await message.answer("📅 באיזו **שנת לידה** נולדת? (לדוגמה 1995):")

    if current_state == RegistrationStates.waiting_birth_year.state:
        if not text.isdigit() or not (1920 <= int(text) <= 2026): return await message.answer("⚠️ שנת לידה לא חוקית.")
        if 2026 - int(text) < 18:
            await state.clear()
            return await message.answer("❌ **המערכת מיועדת לגילאי 18 ומעלה בלבד.**", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True))
        await state.update_data(reg_birth_year=text)
        await state.set_state(RegistrationStates.waiting_phone)
        return await message.answer("📱 לחץ על הכפתור למטה כדי **לשתף את מספר הטלפון** (חובה):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 שיתוף מספר טלפון", request_contact=True), KeyboardButton(text="⬅️ חזרה")]], resize_keyboard=True))

    if current_state == RegistrationStates.waiting_phone.state:
        if not message.contact: return await message.answer("⚠️ חובה ללחוץ על כפתור השיתוף.")
        await state.update_data(reg_phone=message.contact.phone_number)
        await state.set_state(RegistrationStates.waiting_car_brand)
        return await message.answer("🚗 בחר **חברת רכב**:", reply_markup=create_keyboard(list(CAR_DATABASE.keys()), columns=2))

    if current_state == RegistrationStates.waiting_car_brand.state:
        if text.startswith('/'): return await message.answer("⚠️ קלט לא תקין.")
        await state.update_data(reg_car_brand=text)
        await state.set_state(RegistrationStates.waiting_car_model)
        if text in CAR_DATABASE and text != "אחר (הקלדה ידנית)":
            return await message.answer(f"בחר דגם עבור **{text}**:", reply_markup=create_keyboard(list(CAR_DATABASE[text].keys()), columns=2))
        return await message.answer("✍️ הקלד ידנית את **דגם הרכב**:")

    if current_state == RegistrationStates.waiting_car_model.state:
        if text.startswith('/'): return await message.answer("⚠️ קלט לא תקין.")
        await state.update_data(reg_car_model=text)
        await state.set_state(RegistrationStates.waiting_car_year)
        brand = (await state.get_data()).get('reg_car_brand')
        if brand in CAR_DATABASE and text in CAR_DATABASE[brand]:
            return await message.answer("📅 בחר **שנת ייצור**:", reply_markup=create_keyboard(sorted(CAR_DATABASE[brand][text], reverse=True), columns=4))
        return await message.answer("📅 הקלד את **שנת הרכב** (למשל 2020):")

    if current_state == RegistrationStates.waiting_car_year.state:
        if not text.isdigit() or not (1980 <= int(text) <= 2027): return await message.answer("⚠️ שנת רכב לא חוקית.")
        await state.update_data(reg_car_year=text)
        await state.set_state(RegistrationStates.waiting_car_seats)
        return await message.answer("💺 כמה **מקומות ישיבה** (4-50)?", reply_markup=create_keyboard(["4", "5", "6", "7", "10", "20", "50"], columns=4))

    if current_state == RegistrationStates.waiting_car_seats.state:
        seats_val = int(text) if text.isdigit() and 4 <= int(text) <= 50 else 4
        data = await state.get_data()
        expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('''INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'busy', ?, ?)''', 
                             (user_id, data.get('reg_name'), data.get('reg_phone'), data.get('reg_birth_year'), data.get('reg_car_brand'), data.get('reg_car_model'), data.get('reg_car_year'), seats_val, expiry, 'admin' if is_admin else 'user'))
            await db.commit()

        pending_lead = data.get('pending_lead')
        await state.clear()
        await message.answer("✅ **ההרשמה הושלמה!** מנוי הופעל.", reply_markup=get_main_keyboard(user_id, 'admin' if is_admin else 'user', 'busy'))
        if pending_lead:
            async with aiosqlite.connect(DB_FILE) as db:
                lead = await (await db.execute('SELECT status, is_in_progress, message_text FROM leads WHERE lead_id = ?', (pending_lead,))).fetchone()
            if lead and lead[0] == 'active':
                _, _, has_time = parse_order_text(lead[2])
                await state.update_data(active_lead_id=pending_lead)
                msg = "⚠️ *הסדרן בשיחה עם נהג אחר.*\n\n" if lead[1] else ""
                if has_time:
                    await state.set_state(BotStates.waiting_driver_time)
                    return await message.answer(f"{msg}⏱️ **כמה זמן עד שתגיע?**")
                else:
                    await state.clear()
                    await message.answer(f"{msg}✅ בקשתך נשלחה!")
                    await process_lead_request_safe(message, user_id, pending_lead, "לא צוין")
        return

    # --- מנגנון בקשת ביטול חיוב (נהג) ---
    if current_state == BotStates.waiting_debt_cancel_reason.state:
        debt_id = (await state.get_data()).get('cancel_debt_id')
        await state.clear()
        
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debt = await (await db.execute("SELECT * FROM driver_debts WHERE debt_id = ?", (debt_id,))).fetchone()
            if not debt: return await message.answer("חיוב לא נמצא.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            
            await db.execute("UPDATE driver_debts SET is_paid = 2, cancel_reason = ? WHERE debt_id = ?", (text, debt_id))
            await db.commit()
            
        await message.answer("✅ בקשת הביטול נשלחה לסדרן להחלטה.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        
        pub_id = debt['publisher_id']
        if pub_id:
            alert = (
                f"⚠️ **בקשה לביטול חיוב מנהג!**\n\n"
                f"👤 נהג: {user['full_name']} | טלפון: {user['phone']}\n"
                f"🔖 קריאה #{debt['order_id']} | עמלה: ₪{debt['amount']:.2f}\n"
                f"💬 **סיבת הביטול (דברי הנהג):**\n_{text}_\n\n"
                f"האם לאשר את ביטול החיוב או לסרב?"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ אשר ביטול (פטור מחיוב)", callback_data=f"app_cancel_{debt_id}")],
                [InlineKeyboardButton(text="❌ סרב לבקשה (החיוב נשאר)", callback_data=f"rej_cancel_{debt_id}")]
            ])
            try: await bot.send_message(pub_id, alert, reply_markup=kb)
            except: pass
        return

    # --- תפעול שוטף ---
    if text == "🟢 פנוי לקריאות":
        await state.set_state(BotStates.waiting_add_city)
        return await message.answer("🟢 שלח את **שם העיר/יישוב**:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅ חזרה")]], resize_keyboard=True))

    if text == "➕ הוסף עיר נוספת":
        await state.set_state(BotStates.waiting_append_city)
        return await message.answer("✍️ שלח שם עיר נוספת:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅ חזרה")]], resize_keyboard=True))

    if current_state in [BotStates.waiting_add_city.state, BotStates.waiting_append_city.state]:
        city_name = text.strip()
        is_append = (current_state == BotStates.waiting_append_city.state)
        await state.update_data(selected_city=city_name, is_append=is_append)
        await state.set_state(BotStates.waiting_new_radius)
        return await message.answer(f"📍 העיר **{city_name}** נקלטה.\nרדיוס מבוקש? (רשות)", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 ללא רדיוס")], [KeyboardButton(text="5 ק\"מ"), KeyboardButton(text="10 ק\"מ")], [KeyboardButton(text="⬅ חזרה")]], resize_keyboard=True))

    if current_state == BotStates.waiting_new_radius.state:
        rad = 0 if "ללא" in text else (int(text.replace('ק"מ', '').replace('קמ', '').strip()) if text.replace('ק"מ', '').replace('קמ', '').strip().isdigit() else 0)
        data = await state.get_data()
        new_cities = f"{user['cities']}, {data['selected_city']}" if data.get('is_append') and user['cities'] else data['selected_city']
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET cities = ?, radius = ?, status = "free" WHERE user_id = ?', (new_cities, rad, user_id))
            await db.commit()
        await state.clear()
        return await message.answer(f"✅ סטטוס **פנוי**!\n📍 {new_cities} | 📏 {rad} ק\"מ", reply_markup=get_main_keyboard(user_id, role_val, 'free'))

    if text == "🔴 תפוס":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        return await message.answer("🔴 עודכנת לתפוס.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))

    if text == "⚙️ הגדרת אזורים ורדיוס": return await message.answer("⚙️ ניהול אזורים:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ הוסף עיר נוספת"), KeyboardButton(text="🗑️ מחק את כל הערים (איפס הכל)")], [KeyboardButton(text="⬅ חזרה")]], resize_keyboard=True))
    
    if text == "🗑️ מחק את כל הערים (איפס הכל)":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        return await message.answer("🗑️ אזורים אופסו. סטטוס תפוס.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))

    if text == "💎 מצב מנוי ופרופיל":
        rat = f"{user['rating']:.1f} ⭐️ ({user['rating_count']})" if user['rating_count'] > 0 else "ללא"
        return await message.answer(f"💎 **הפרופיל שלך:**\n\n👤 שם: {user['full_name']}\n🚗 {user['car_brand']} {user['car_model']} ({user['car_year']})\n🛡️ תפקיד: **{user['role']}**\n📅 תוקף: {user['expiry_date']}\n🌟 דירוג: {rat}\n\n📍 אזורים: **{user['cities'] if user['cities'] else 'תפוס'}**", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    # --- תפריט חיובים מתקדם (הנהג קורא) ---
    if text == "💳 חיובים":
        async with aiosqlite.connect(DB_FILE) as db:
            debts = await (await db.execute("SELECT debt_id, amount, order_id, is_paid FROM driver_debts WHERE user_id = ? AND is_paid IN (0, 2) ORDER BY debt_id DESC", (user_id,))).fetchall()
        
        if not debts: return await message.answer("💳 אין לך חיובים פתוחים לתשלום.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        
        total_sum = sum(d[1] for d in debts if d[3] == 0) # סוכם רק את אלו שלא בערעור
        kb = []
        for d_id, amt, o_id, stat in debts:
            stat_icon = "⏳ בבדיקה" if stat == 2 else f"₪{amt:.1f}"
            kb.append([InlineKeyboardButton(text=f"קריאה #{o_id} | {stat_icon}", callback_data=f"v_debt_{d_id}")])
        
        return await message.answer(f"💳 **חיובים פתוחים (סה\"כ: ₪{total_sum:.2f}):**\nלחץ על חיוב לפירוט או ערעור:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    # ניהול והחלפת קריאה (סדרן)
    if current_state == BotStates.waiting_manual_close_driver.state:
        lead_id = (await state.get_data()).get('manual_lead_id')
        async with aiosqlite.connect(DB_FILE) as db:
            target = await (await db.execute("SELECT user_id, full_name FROM users WHERE phone = ? OR full_name LIKE ?", (text, f"%{text}%"))).fetchone()
        if not target: return await message.answer("⚠️ נהג לא נמצא.")
        
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            lead = await (await db.execute('SELECT * FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
            if lead['closed_with']: await db.execute("DELETE FROM driver_debts WHERE order_id = ?", (lead_id,))
            
            await db.execute('UPDATE leads SET status = "closed", closed_with = ? WHERE lead_id = ?', (target[1], lead_id))
            await db.execute('UPDATE users SET total_trips = total_trips + 1, status = "busy", cities = "" WHERE user_id = ?', (target[0],))
            
            if lead['price'] > 0:
                pub = await get_user_dict(user_id)
                st_id = pub['station_id'] if pub['station_id'] else 1
                st = await (await db.execute('SELECT commission_percent FROM stations WHERE station_id = ?', (st_id,))).fetchone()
                comm = st['commission_percent'] if st else 10.0
                await db.execute('INSERT INTO driver_debts (user_id, station_id, amount, order_id, order_text, publisher_name, publisher_username, is_paid, date, publisher_id, original_price, comm_percent) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)', 
                                 (target[0], st_id, (lead['price'] * comm) / 100.0, lead_id, lead['message_text'], message.from_user.full_name, f"@{message.from_user.username}", datetime.now().strftime('%d/%m/%Y %H:%M'), user_id, lead['price'], comm))
            await db.commit()

        try: await bot.send_message(target[0], f"🎉 **קריאה #{lead_id} נסגרה עליך ידנית! סטטוס: תפוס.**\n📞 טלפון: {lead['phone_number']}")
        except: pass
        await state.clear()
        
        rate_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐️", callback_data=f"rate_{target[0]}_1"), InlineKeyboardButton(text="⭐️⭐️⭐️", callback_data=f"rate_{target[0]}_3"), InlineKeyboardButton(text="⭐️⭐️⭐️⭐️⭐️", callback_data=f"rate_{target[0]}_5")],
            [InlineKeyboardButton(text="⏭️ דלג", callback_data="rate_skip")]
        ])
        return await message.answer(f"✅ נסגר על **{target[1]}**!\nנשמח אם תדרג:", reply_markup=rate_kb)

    if text == "📋 מצב קריאות":
        if role_val not in ['admin', 'advertiser', 'station_manager', 'dispatcher']: return
        st_id = user['station_id']
        async with aiosqlite.connect(DB_FILE) as db:
            if is_admin: leads = await (await db.execute("SELECT lead_id, route_cities, status FROM leads ORDER BY lead_id DESC LIMIT 10")).fetchall()
            else: leads = await (await db.execute("SELECT lead_id, route_cities, status FROM leads WHERE station_id = ? ORDER BY lead_id DESC LIMIT 10", (st_id,))).fetchall()
        if not leads: return await message.answer("📋 אין קריאות.")
        
        kb_buttons = []
        for l_id, l_rt, l_st in leads:
            status_emoji = "🟢" if l_st == "active" else ("🔴" if l_st == "closed" else "🗑️")
            kb_buttons.append([InlineKeyboardButton(text=f"{status_emoji} קריאה #{l_id} | {l_rt[:15]}", callback_data=f"view_lead_{l_id}")])
        kb_buttons.append([InlineKeyboardButton(text="❌ סגור תפריט", callback_data="dest_cancel")])
        return await message.answer("📋 **קריאות אחרונות:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))

    # --- בקרת איכות לפרסום קריאות ---
    if text == "📢 פרסום הודעה":
        if role_val not in ['admin', 'advertiser', 'station_manager', 'dispatcher']: return
        await state.set_state(BotStates.waiting_lead_text)
        return await message.answer("📢 פרסום קריאה:\nשלח את התוכן נקי ללא חצים:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))
    
    if current_state == BotStates.waiting_lead_text.state:
        cities, price, _ = parse_order_text(text)
        await state.update_data(lead_text=text)
        
        if len(cities) < 2 or not price:
            await state.set_state(BotStates.waiting_lead_phone)
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚀 המשך בכל זאת"), KeyboardButton(text="✏️ ערוך מחדש")]], resize_keyboard=True)
            return await message.answer(f"⚠️ **שים לב:** לא זוהו 2 ערים (מוצא ויעד) או לא זוהה מחיר.\nהאם תרצה להמשיך או לערוך?", reply_markup=kb)
        
        await state.set_state(BotStates.waiting_lead_phone)
        return await message.answer("📞 שלח מספר טלפון לקריאה:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))

    if current_state == BotStates.waiting_lead_phone.state:
        if text == "✏️ ערוך מחדש":
            await state.set_state(BotStates.waiting_lead_text)
            return await message.answer("אנא שלח את תוכן הקריאה מחדש:")
        if text == "🚀 המשך בכל זאת":
            return await message.answer("📞 שלח מספר טלפון לקריאה:")
            
        if not validate_israeli_phone(text) and text != "המשך עם מספר זה":
            await state.update_data(temp_phone=text)
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="המשך עם מספר זה"), KeyboardButton(text="✏️ אקליד שוב")]], resize_keyboard=True)
            return await message.answer("⚠️ **המספר נראה שגוי או חסר ספרות.**\nלהמשיך בכל זאת?", reply_markup=kb)
            
        if text == "✏️ אקליד שוב": return await message.answer("📞 הקלד את המספר מחדש:")
        
        phone_to_save = text if text != "המשך עם מספר זה" else (await state.get_data()).get('temp_phone')
        await state.update_data(lead_phone=phone_to_save)
        return await message.answer("🎯 **לאן לפרסם?**", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👥 לשליחים", callback_data="dest_users")], [InlineKeyboardButton(text="🏢 לקבוצות", callback_data="dest_groups")], [InlineKeyboardButton(text="🚀 גם וגם", callback_data="dest_both")]]))

# --- ניהול וערעור חיובים (Inline Callbacks) ---
@dp.callback_query(F.data.startswith("v_debt_"))
async def cb_view_debt(callback: CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.replace("v_debt_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        debt = await (await db.execute("SELECT d.*, s.station_name FROM driver_debts d LEFT JOIN stations s ON d.station_id = s.station_id WHERE d.debt_id = ?", (debt_id,))).fetchone()
    
    if not debt: return await callback.answer("חיוב לא נמצא.")
    
    st_name = debt['station_name'] if debt['station_name'] else "כללי"
    orig_price = debt['original_price'] if debt['original_price'] else 0.0
    pct = debt['comm_percent'] if debt['comm_percent'] else 10.0
    
    disp = (
        f"💳 **פירוט חיוב - קריאה #{debt['order_id']}**\n\n"
        f"📝 **תוכן הנסיעה:**\n_{debt['order_text']}_\n\n"
        f"🏢 **תחנה:** {st_name}\n"
        f"👨‍💻 **סדרן:** {debt['publisher_name']} ({debt['publisher_username']})\n"
        f"💵 **מחיר קריאה (ששולם לך):** ₪{orig_price:.2f}\n"
        f"📊 **אחוז עמלה:** {pct}%\n"
        f"🔴 **עמלה לתשלום:** ₪{debt['amount']:.2f}\n"
    )
    
    kb = []
    if debt['is_paid'] == 0:
        kb.append([InlineKeyboardButton(text="❌ בקשת ביטול חיוב (ערעור)", callback_data=f"ask_cancel_debt_{debt_id}")])
    elif debt['is_paid'] == 2:
        disp += "\n\n⏳ **סטטוס:** ממתין לאישור ביטול מהסדרן."
        
    kb.append([InlineKeyboardButton(text="⬅️ חזרה לחיובים", callback_data="dest_cancel")])
    
    try: await callback.message.edit_text(disp, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except: pass

@dp.callback_query(F.data.startswith("ask_cancel_debt_"))
async def cb_ask_cancel_debt(callback: CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.replace("ask_cancel_debt_", ""))
    await state.set_state(BotStates.waiting_debt_cancel_reason)
    await state.update_data(cancel_debt_id=debt_id)
    
    try: await callback.message.delete()
    except: pass
    await callback.message.answer("✍️ **בקשת ביטול חיוב:**\nאנא הקלד את הסיבה המפורטת לביטול החיוב (ההודעה תועבר לסדרן):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))

@dp.callback_query(F.data.startswith("app_cancel_"))
async def cb_approve_cancel(callback: CallbackQuery):
    debt_id = int(callback.data.replace("app_cancel_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        debt = await (await db.execute("SELECT user_id, order_id, amount FROM driver_debts WHERE debt_id = ?", (debt_id,))).fetchone()
        if debt:
            await db.execute("UPDATE driver_debts SET is_paid = 1 WHERE debt_id = ?", (debt_id,))
            await db.commit()
            try: await bot.send_message(debt[0], f"✅ **עדכון מהסדרן:** בקשתך לביטול העמלה (₪{debt[2]:.2f}) על קריאה #{debt[1]} **אושרה!** החיוב נמחק.")
            except: pass
    await callback.message.edit_text("✅ אישרת את הביטול. החיוב נמחק מהנהג.")

@dp.callback_query(F.data.startswith("rej_cancel_"))
async def cb_reject_cancel(callback: CallbackQuery):
    debt_id = int(callback.data.replace("rej_cancel_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        debt = await (await db.execute("SELECT user_id, order_id FROM driver_debts WHERE debt_id = ?", (debt_id,))).fetchone()
        if debt:
            await db.execute("UPDATE driver_debts SET is_paid = 0 WHERE debt_id = ?", (debt_id,))
            await db.commit()
            try: await bot.send_message(debt[0], f"❌ **עדכון מהסדרן:** בקשתך לביטול העמלה על קריאה #{debt[1]} **נדחתה**. החיוב הוחזר למצב פתוח.")
            except: pass
    await callback.message.edit_text("❌ סירבת לביטול. החיוב נשאר פעיל.")

# --- ניהול קריאות מתוך התפריט החכם ---
@dp.callback_query(F.data.startswith("view_lead_"))
async def cb_view_lead(callback: CallbackQuery):
    lead_id = int(callback.data.replace("view_lead_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        lead = await (await db.execute('SELECT * FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
    if not lead: return await callback.answer("קריאה לא נמצאה.")
    
    pub_user = await get_user_dict(lead['publisher_id'])
    pub_name = pub_user['full_name'] if pub_user else "סדרן"
    st_name = "כללי"
    if pub_user and pub_user['station_id']:
        async with aiosqlite.connect(DB_FILE) as db:
            st = await (await db.execute('SELECT station_name FROM stations WHERE station_id = ?', (pub_user['station_id'],))).fetchone()
            if st: st_name = st[0]
            
    lead_disp = generate_lead_display(lead['message_text'], lead_id, lead['price'], lead['route_cities'], pub_name, st_name)
    lead_disp += f"\n\nסטטוס: {'🟢 פעילה' if lead['status'] == 'active' else ('🔴 סגורה' if lead['status'] == 'closed' else '🗑️ נמחקה')}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 החלפת נהג (ידני)", callback_data=f"manual_close_{lead_id}"), InlineKeyboardButton(text="🗑️ מחיקה", callback_data=f"delete_lead_{lead_id}")],
        [InlineKeyboardButton(text="❌ סגור חלון", callback_data="dest_cancel")]
    ])
    try: await callback.message.edit_text(lead_disp, reply_markup=kb)
    except: await callback.message.answer(lead_disp, reply_markup=kb)

@dp.callback_query(F.data.startswith("rate_"))
async def cb_rate_driver(callback: CallbackQuery):
    if callback.data == "rate_skip":
        await callback.message.delete()
        return await callback.answer("דילגת על דירוג.")
    
    driver_id, stars = int(callback.data.split("_")[1]), int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        driver = await (await db.execute('SELECT rating, rating_count FROM users WHERE user_id = ?', (driver_id,))).fetchone()
        if driver:
            new_count = driver[1] + 1
            new_rating = ((driver[0] * driver[1]) + stars) / new_count
            await db.execute('UPDATE users SET rating = ?, rating_count = ? WHERE user_id = ?', (new_rating, new_count, driver_id))
            await db.commit()
    await callback.message.delete()

# --- פרסום קריאה מלאה ---
@dp.callback_query(F.data.startswith("dest_"))
async def destination_chosen(callback: CallbackQuery, state: FSMContext):
    action = callback.data.replace("dest_", "")
    if action == "cancel":
        await state.clear()
        try: await callback.message.delete()
        except: pass
        return

    data = await state.get_data()
    text_content, phone_content = data.get('lead_text'), data.get('lead_phone')
    user_id = callback.from_user.id
    cities, price, _ = parse_order_text(text_content)
    
    pub_user = await get_user_dict(user_id)
    st_id = pub_user['station_id'] if pub_user else 0

    async with aiosqlite.connect(DB_FILE) as db:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = await db.execute('INSERT INTO leads (publisher_id, message_text, phone_number, created_at, price, route_cities, station_id) VALUES (?, ?, ?, ?, ?, ?, ?)', (user_id, text_content, phone_content, now_str, price if price else 0.0, " ➔ ".join(cities) if cities else "", st_id))
        lead_id = cursor.lastrowid
        await db.commit()

    await state.clear()
    
    st_name = "כללי"
    if st_id:
        async with aiosqlite.connect(DB_FILE) as db:
            st = await (await db.execute('SELECT station_name FROM stations WHERE station_id = ?', (st_id,))).fetchone()
            if st: st_name = st[0]

    alert_msg = generate_lead_display(text_content, lead_id, price if price else 0.0, " ➔ ".join(cities), pub_user['full_name'], st_name)
    origin_city = [c.strip() for c in cities][0] if cities else ""
    
    await callback.message.edit_text(f"✅ קריאה #{lead_id} נשלחת לשליחים!")
    
    if action in ["users", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            free_users = await (await db.execute("SELECT user_id, cities, radius FROM users WHERE status = 'free'")).fetchall()
        for f_uid, f_cities, f_radius in free_users:
            if not origin_city or f_radius == 0 and origin_city in f_cities or f_radius > 0:
                try: await bot.send_message(f_uid, alert_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]]))
                except: pass

    if action in ["groups", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            active_groups = await (await db.execute("SELECT group_id FROM bot_groups WHERE is_active = 1")).fetchall()
        for (g_id,) in active_groups:
            try: await bot.send_message(g_id, alert_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]]))
            except: pass

async def process_lead_request_safe(message_or_callback, requester_id: int, lead_id: int, driver_time: str):
    async with aiosqlite.connect(DB_FILE) as db:
        lead = await (await db.execute('SELECT publisher_id, status FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
    if not lead or lead[1] != 'active': return

    requester_user = await get_user_dict(requester_id)
    req_chat = await bot.get_chat(requester_id)
    rad_text = "ללא" if requester_user['radius'] == 0 else f"{requester_user['radius']} ק\"מ"

    alert = (
        f"🔔 **בקשה לקריאה #{lead_id}**\n\n"
        f"⏱ זמן הגעה: {driver_time}\n"
        f"👤 **נהג:** {requester_user['full_name']} (@{req_chat.username})\n"
        f"• טלפון: {requester_user['phone']}\n"
        f"• רכב: {requester_user['car_brand']} {requester_user['car_model']}\n"
        f"• אזור: `{requester_user['cities']}` | {rad_text}\n\nלאשר או לסגור?"
    )

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ פתיחת שיחה", callback_data=f"app_only_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="✅ סגור עליו + עמלה", callback_data=f"app_close_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="❌ דחייה", callback_data=f"rej_lead_{lead_id}_{requester_id}")]
    ])
    await bot.send_message(lead[0], alert, reply_markup=buttons)

@dp.callback_query(F.data.startswith("app_only_"))
async def cb_app_only(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id, requester_id = int(parts[2]), int(parts[3])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE leads SET is_in_progress = 1 WHERE lead_id = ?", (lead_id,))
        await db.commit()
    try: await bot.send_message(requester_id, f"✅ הבקשה לקריאה #{lead_id} אושרה! פנה לסדרן להמשך טיפול: @{callback.from_user.username}")
    except: pass
    await callback.answer("סומן בטיפול.")

@dp.callback_query(F.data.startswith("rej_lead_"))
async def cb_rej_lead(callback: CallbackQuery):
    lead_id, requester_id = int(callback.data.split("_")[2]), int(callback.data.split("_")[3])
    try: await bot.send_message(requester_id, f"❌ בקשתך ל-#{lead_id} נדחתה.")
    except: pass
    await callback.message.edit_text(f"❌ נדחה.")

@dp.callback_query(F.data.startswith("delete_lead_"))
async def cb_delete_lead(callback: CallbackQuery):
    lead_id = int(callback.data.replace("delete_lead_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE leads SET status = 'deleted' WHERE lead_id = ?", (lead_id,))
        await db.commit()
    await callback.message.edit_text(f"🗑️ קריאה #{lead_id} נמחקה.")

@dp.callback_query(F.data.startswith("app_close_"))
async def app_close_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id, requester_id, publisher_id = int(parts[2]), int(parts[3]), callback.from_user.id
    
    pub_user = await get_user_dict(publisher_id)
    pub_st_id = pub_user['station_id'] if pub_user and pub_user['station_id'] else 1

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        st = await (await db.execute('SELECT commission_percent FROM stations WHERE station_id = ?', (pub_st_id,))).fetchone()
        comm = st['commission_percent'] if st else 10.0

        await db.execute('UPDATE leads SET status = "closed", closed_with = ? WHERE lead_id = ?', (f"@{callback.from_user.username}", lead_id))
        await db.execute('UPDATE users SET total_trips = total_trips + 1, status = "busy", cities = "" WHERE user_id = ?', (requester_id,))
        
        lead_data = await (await db.execute('SELECT message_text, phone_number, price FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
        if lead_data and lead_data['price'] > 0:
            await db.execute('INSERT INTO driver_debts (user_id, station_id, amount, order_id, order_text, publisher_name, publisher_username, is_paid, date, publisher_id, original_price, comm_percent) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)', 
                             (requester_id, pub_st_id, (lead_data['price'] * comm) / 100.0, lead_id, lead_data['message_text'], pub_user['full_name'], f"@{callback.from_user.username}", datetime.now().strftime('%d/%m/%Y %H:%M'), publisher_id, lead_data['price'], comm))
        await db.commit()

    try: await bot.send_message(requester_id, f"🎉 **קריאה #{lead_id} נסגרה עליך! שונה לתפוס.**\n📞 טלפון לקוח: {lead_data['phone_number']}\nסדרן: @{callback.from_user.username}")
    except: pass
    
    rate_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️⭐️⭐️⭐️⭐️", callback_data=f"rate_{requester_id}_5")],
        [InlineKeyboardButton(text="⏭️ דלג", callback_data="rate_skip")]
    ])
    await callback.message.edit_text(f"✅ קריאה #{lead_id} נסגרה בהצלחה!\nנשמח אם תדרג את הנהג:", reply_markup=rate_kb)

async def main():
    await init_db()
    await start_web_server()
    print("✨ ERP Bot 5.0 עובד: מערכת חיובים וערעורים אינטראקטיבית הוטמעה!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
