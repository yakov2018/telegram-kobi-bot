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

print(f"DEBUG_CHECK -> Final Cleaned Token: '{BOT_TOKEN}'")

if not BOT_TOKEN:
    print("שגיאה קריטית: משתנה הסביבה BOT_TOKEN ריק או לא מוגדר!")
    sys.exit(1)

ADMIN_IDS = [8644923212, 552821474]
DB_FILE = 'bot_database_v4.db'

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
    logging.info(f"Web server started on port {port}")

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
    waiting_broadcast_all = State()
    waiting_lead_text = State()
    waiting_lead_phone = State()
    waiting_driver_time = State()
    waiting_station_name_input = State()
    waiting_manual_close_driver = State()
    waiting_edit_lead_text = State()
    waiting_edit_lead_price = State()

# מאגר רכבים מורחב ומקיף (ישראל)
CAR_DATABASE = {
    "טויוטה (Toyota)": {"קורולה": list(range(1995, 2027)), "יאריס": list(range(1999, 2027)), "C-HR": list(range(2017, 2027)), "ראב 4": list(range(1995, 2027)), "קאמרי": list(range(1995, 2027)), "לנד קרוזר": list(range(1995, 2027)), "היילקס": list(range(1995, 2027)), "אייגו": list(range(2005, 2027))},
    "יונדאי (Hyundai)": {"אלנטרה": list(range(1995, 2027)), "איוניק": list(range(2016, 2023)), "איוניק 5": list(range(2021, 2027)), "איוניק 6": list(range(2023, 2027)), "טוסון": list(range(2004, 2027)), "סנטה פה": list(range(2001, 2027)), "i10": list(range(2008, 2027)), "i20": list(range(2008, 2027)), "סטאריה": list(range(2021, 2027))},
    "קיה (Kia)": {"פיקנטו": list(range(2011, 2027)), "ספורטאז'": list(range(1995, 2027)), "נירו": list(range(2016, 2027)), "סורנטו": list(range(2002, 2027)), "סטוניק": list(range(2017, 2027)), "קרניבל": list(range(1998, 2027)), "סלטוס": list(range(2019, 2027))},
    "מאזדה (Mazda)": {"מאזדה 2": list(range(2007, 2027)), "מאזדה 3": list(range(2004, 2027)), "מאזדה 6": list(range(2003, 2027)), "CX-5": list(range(2012, 2027)), "CX-30": list(range(2019, 2027))},
    "סקודה (Skoda)": {"אוקטביה": list(range(1996, 2027)), "סופרב": list(range(2001, 2027)), "קודיאק": list(range(2016, 2027)), "קארוק": list(range(2017, 2027)), "קאמיק": list(range(2019, 2027)), "פאביה": list(range(1999, 2027))},
    "BYD": {"אטו 3 (Atto 3)": list(range(2022, 2027)), "דולפין": list(range(2023, 2027)), "סיל": list(range(2023, 2027)), "האן": list(range(2023, 2027))},
    "טסלה (Tesla)": {"מודל 3": list(range(2017, 2027)), "מודל Y": list(range(2020, 2027)), "מודל S": list(range(2012, 2027)), "מודל X": list(range(2015, 2027))},
    "מיצובישי (Mitsubishi)": {"אאוטלנדר": list(range(2003, 2027)), "ספייס סטאר": list(range(2013, 2027)), "אטראז'": list(range(2013, 2027)), "אקליפס קרוס": list(range(2018, 2027))},
    "פולקסווגן (VW)": {"גולף": list(range(1995, 2027)), "פולו": list(range(1995, 2027)), "טיגואן": list(range(2007, 2027)), "ID.4": list(range(2020, 2027)), "קראפטר / טרנספורטר": list(range(1990, 2027))},
    "שברולט (Chevrolet)": {"ספארק": list(range(2010, 2027)), "מאליבו": list(range(1997, 2027)), "אקווינוקס": list(range(2005, 2027)), "סוואנה": list(range(1996, 2027))},
    "רנו (Renault)": {"קליאו": list(range(1990, 2027)), "מגאן": list(range(1995, 2027)), "קפצ'ור": list(range(2013, 2027)), "טראפיק": list(range(2001, 2027))},
    "מרצדס (Mercedes)": {"C-Class": list(range(1993, 2027)), "E-Class": list(range(1993, 2027)), "S-Class": list(range(1993, 2027)), "ספרינטר": list(range(1995, 2027)), "ויטו": list(range(1996, 2027))},
    "ב.מ.וו (BMW)": {"סדרה 3": list(range(1990, 2027)), "סדרה 5": list(range(1990, 2027)), "X3": list(range(2003, 2027)), "X5": list(range(1999, 2027))},
    "אחר (הקלדה ידנית)": {}
}

ISRAELI_CITIES = [
    "ירושלים", "תל אביב", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה", "בני ברק", "באר שבע", "חולון",
    "רמת גן", "אשקלון", "בת ים", "בית שמש", "הרצליה", "כפר סבא", "חדרה", "מודיעין", "מכבים", "רעות", "נצרת", "לוד",
    "רמלה", "רחובות", "מודיעין עילית", "ביתר עילית", "אלעד", "בית שאן", "אופקים", "אריאל", "אילת", "טבריה",
    "דימונה", "הוד השרון", "זכרון יעקב", "טירה", "טמרה", "יבנה", "יהוד", "מונוסון", "יקנעם עילית", "כפר יונה",
    "כפר קאסם", "כרמיאל", "מגדל העמק", "מעלה אדומים", "מעלות", "תרשיחא", "נהריה", "נס ציונה", "נשר", "נתיבות",
    "עכו", "עפולה", "ערד", "צפת", "קלנסווה", "קריית אונו", "קריית אתא", "קריית ביאליק", "קריית גת", "קריית ים",
    "קריית מוצקין", "קריית מלאכי", "קריית שמונה", "ראש העין", "רהט", "רמת השרון", "רעננה", "שדרות", "שפרעם",
    "אבו גוש", "בית דגן", "גבעת שמואל", "גבעתיים", "גדרה", "חריש", "מבשרת ציון", "מצפה רמון", "עומר", "פרדס חנה",
    "כרכור", "קצרין", "אפרת", "בית אל", "גוש עציון", "חשמונאים", "אור יהודה", "אזור", "אליכין", "אלפי מנשה", "אלקנה",
    "באר יעקב", "בני עייש", "ג'לג'וליה", "גבעת זאב", "הר אדר", "זמר", "חצור הגלילית", "כאבול", "כוכב יאיר", "צור יגאל",
    "כפר ורדים", "כפר תבור", "להבים", "מזכרת בתיה", "מטולה", "מיתר", "מעלה אפרים", "סביון", "עמנואל", "עתלית",
    "קריית טבעון", "קריית יערים", "קריית עקרון", "קרני שומרון", "ראמה", "ראש פינה", "רכסים", "שלומי", "תל מונד",
    "אורנית", "אבן יהודה", "אום אל-פחם", "באקה אל-גרביה", "גני תקווה", "דאלית אל-כרמל", "יפיע", "כפר מנדא", "כפר שמריהו",
    "מג'דל שמס", "מגאר", "פוריידיס", "קציר", "ריינה", "שגב שלום", "תל שבע", "קדימה", "צורן"
]

CITY_ALIASES = {"ים": "ירושלים", "פת": "פתח תקווה", "תא": "תל אביב", "שדה": "שדה תעופה", "סבא": "כפר סבא", "ראשון": "ראשון לציון", "רג": "רמת גן", "שמש": "בית שמש", "בב": "בני ברק", "ספר": "מודיעין עילית"}

def create_keyboard(items, columns=3, add_back=True):
    kb = []
    row = []
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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                birth_date TEXT,
                car_brand TEXT,
                car_model TEXT,
                car_year TEXT,
                car_seats INTEGER DEFAULT 4,
                status TEXT DEFAULT 'busy',
                expiry_date TEXT,
                role TEXT DEFAULT 'user',
                station_id INTEGER DEFAULT 0,
                radius INTEGER DEFAULT 0,
                cities TEXT DEFAULT '',
                total_trips INTEGER DEFAULT 0,
                rating REAL DEFAULT 0.0,
                rating_count INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0
            )
        ''')
        await db.execute('CREATE TABLE IF NOT EXISTS stations (station_id INTEGER PRIMARY KEY AUTOINCREMENT, station_name TEXT, owner_id INTEGER, commission_percent REAL DEFAULT 10.0)')
        await db.execute('CREATE TABLE IF NOT EXISTS bot_groups (group_id INTEGER PRIMARY KEY, group_title TEXT, is_active INTEGER DEFAULT 1)')
        await db.execute('CREATE TABLE IF NOT EXISTS driver_debts (debt_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, station_id INTEGER, amount REAL, order_id INTEGER, order_text TEXT, publisher_name TEXT, publisher_username TEXT, is_paid BOOLEAN DEFAULT 0, date TEXT)')
        await db.execute('CREATE TABLE IF NOT EXISTS leads (lead_id INTEGER PRIMARY KEY AUTOINCREMENT, publisher_id INTEGER, message_text TEXT, phone_number TEXT, status TEXT DEFAULT "active", closed_with TEXT DEFAULT NULL, created_at TEXT, price REAL DEFAULT 0.0, route_cities TEXT DEFAULT "", station_id INTEGER DEFAULT NULL, is_in_progress INTEGER DEFAULT 0)')
        await db.commit()

async def get_user_dict(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

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
    has_time_mention = bool(re.search(r'זמנ[ן]{1,6}|זמני[ם]{1,6}', text) or re.search(r'זמן[ן]{1,6}', text))
    return found_cities, price, has_time_mention

def get_main_keyboard(user_id, role='user', current_status='busy'):
    is_admin = (user_id in ADMIN_IDS or role == 'admin')
    is_advertiser = is_admin or (role in ['advertiser', 'station_manager', 'dispatcher'])
    is_regular_user = (role == 'user' and not is_admin)
    status_btn_text = "🟢 פנוי לקריאות" if current_status == 'free' else "🔴 תפוס"
    kb = []
    if is_admin or is_advertiser: kb.append([KeyboardButton(text="📢 פרסום הודעה"), KeyboardButton(text="📋 מצב קריאות")])
    kb.append([KeyboardButton(text=status_btn_text), KeyboardButton(text="⚙️ הגדרת אזורים ורדיוס")])
    if is_regular_user or role == 'user': kb.append([KeyboardButton(text="💳 חיובים"), KeyboardButton(text="💎 מצב מנוי ופרופיל")])
    else: kb.append([KeyboardButton(text="💎 מצב מנוי ופרופיל")])
    kb.append([KeyboardButton(text="ℹ️ אודות ויצירת קשר")])
    if is_admin: kb.append([KeyboardButton(text="🛠️ פאנל מנהל")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 ניהול משתמשים"), KeyboardButton(text="📊 סטטיסטיקות מערכת")],
        [KeyboardButton(text="📢 שידור הודעה לכולם"), KeyboardButton(text="🏢 ניהול תחנות וקבוצות")],
        [KeyboardButton(text="⚙️ ניהול קבוצות הבוט"), KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
    ], resize=True)

# מבנה טקסט קריאה חכם
def generate_lead_display(lead_text, lead_id, price, route_cities, pub_name, pub_station):
    cities = [c.strip() for c in route_cities.split('➔') if c.strip()]
    origin = cities[0] if len(cities) > 0 else "לא זוהה"
    dest = cities[-1] if len(cities) > 1 else "לא זוהה"
    
    return (
        f"{lead_text}\n\n"
        f"\n\n"
        f"🔖 **מספר קריאה:** #{lead_id}\n"
        f"📍 **מוצא:** {origin}\n"
        f"🏁 **יעד:** {dest}\n"
        f"💰 **מחיר:** ₪{price if price > 0 else 'לא צוין'}\n"
        f"🏢 **תחנה:** {pub_station}\n"
        f"👨‍💻 **סדרן:** {pub_name}"
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
            await db.execute('INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role, is_blocked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, "busy", ?, "admin", 0)', 
                             (user_id, "מנהל מערכת", "0000000000", "2000-01-01", "מרצדס", "S-Class", "2025", 4, expiry))
            await db.commit()
        auth_status = "ok"

    if auth_status == "blocked": return await message.answer("❌ חשבונך חסום במערכת.")
    if auth_status == "expired": return await message.answer("❌ **פג תוקף המנוי שלך!**")

    user = await get_user_dict(user_id)
    role_val = user['role'] if user else ('admin' if is_admin else 'user')
    current_status = user['status'] if user else 'busy'

    if message.text and message.text.startswith("/start lead_"):
        try: lead_id = int(message.text.replace("/start lead_", "").strip())
        except: lead_id = None
        
        if auth_status == "new":
            if not message.from_user.username: return await message.answer("⚠️ חובה להגדיר שם משתמש בטלגרם כדי לבקש קריאות.")
            await state.update_data(pending_lead=lead_id)
            await state.set_state(RegistrationStates.waiting_name)
            return await message.answer("👋 שלום וברוכים הבאים!\nכדי לבקש קריאה חובה להשלים רישום קצר.\n\nאנא שלח את **השם המלא** שלך:")
        
        if lead_id:
            async with aiosqlite.connect(DB_FILE) as db:
                db.row_factory = aiosqlite.Row
                lead = await (await db.execute('SELECT status, is_in_progress, message_text FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
            
            if not lead or lead['status'] in ['closed', 'deleted']: return await message.answer("❌ הנסיעה נסגרה או נמחקה.")
            
            _, _, has_time = parse_order_text(lead['message_text'])
            await state.update_data(active_lead_id=lead_id)
            
            msg_prefix = "⚠️ *שים לב: הסדרן החל שיחה עם נהג אחר, אך בקשתך תועבר.*\n\n" if lead['is_in_progress'] else ""
            
            if has_time:
                await state.set_state(BotStates.waiting_driver_time)
                await message.answer(f"{msg_prefix}⏱️ **קריאה זו דורשת זמן הגעה!**\nשלח כעת את **הזמן** בכתובת:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
            else:
                await state.clear()
                await message.answer(f"{msg_prefix}✅ בקשתך נשלחה לסדרן!", reply_markup=get_main_keyboard(user_id, role_val, current_status))
                await process_lead_request_safe(message, user_id, lead_id, "לא צוין זמן")
        return

    if auth_status == "new":
        if not message.from_user.username: return await message.answer("⚠️ חובה להגדיר שם משתמש בטלגרם.")
        await state.set_state(RegistrationStates.waiting_name)
        return await message.answer("👋 שלום וברוכים הבאים לבוט! 🚀\nאנא שלח את **השם המלא** שלך:")

    await state.clear()
    await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(user_id, role_val, current_status))

@dp.message()
async def handle_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    auth_status = await check_user_auth(user_id)

    if auth_status == "blocked": return await message.answer("❌ חשבונך חסום במערכת.")
    if auth_status == "expired": return await message.answer("❌ **פג תוקף המנוי שלך!**")

    user = await get_user_dict(user_id)
    is_admin = (user_id in ADMIN_IDS)
    role_val = user['role'] if user else ('admin' if is_admin else 'user')
    current_status = user['status'] if user else 'busy'
    text = message.text.strip() if message.text else ""

    if text in ["/start", "תפריט", "⬅️ חזרה לתפריט הראשי", "⬅ חזרה לתפריט הראשי", "❌ ביטול"]:
        await state.clear()
        return await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    current_state = await state.get_state()

    # --- הרשמה מאובטחת ---
    if current_state == RegistrationStates.waiting_name.state:
        if text.startswith('/'): return await message.answer("⚠️ נא להזין שם תקין.")
        await state.update_data(reg_name=text)
        await state.set_state(RegistrationStates.waiting_birth_year)
        return await message.answer("📅 באיזו **שנת לידה** נולדת? (מספר בלבד, לדוגמה 1995):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))

    if current_state == RegistrationStates.waiting_birth_year.state:
        if not text.isdigit(): return await message.answer("⚠️ הקלד שנת לידה חוקית בספרות בלבד.")
        birth_year = int(text)
        if birth_year < 1920 or birth_year > 2026: return await message.answer("⚠️ שנת לידה לא הגיונית. נסה שוב.")
        if 2026 - birth_year < 18:
            await state.clear()
            return await message.answer("❌ **שגיאה:** המערכת מיועדת לגילאי 18 ומעלה בלבד. אינך מורשה להירשם.", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True))
        
        await state.update_data(reg_birth_year=text)
        await state.set_state(RegistrationStates.waiting_phone)
        return await message.answer("תודה! לחץ על הכפתור למטה כדי **לשתף את מספר הטלפון** (פעולה מאובטחת וחובה):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 שיתוף מספר טלפון", request_contact=True), KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))

    if current_state == RegistrationStates.waiting_phone.state:
        if not message.contact: return await message.answer("⚠️ חובה ללחוץ על הכפתור למטה כדי לשתף איש קשר. הקלדה ידנית חסומה.")
        await state.update_data(reg_phone=message.contact.phone_number)
        await state.set_state(RegistrationStates.waiting_car_brand)
        return await message.answer("🚗 בחר את **חברת הרכב** שלך:", reply_markup=create_keyboard(list(CAR_DATABASE.keys()), columns=2))

    if current_state == RegistrationStates.waiting_car_brand.state:
        if text.startswith('/'): return await message.answer("⚠️ קלט לא תקין.")
        await state.update_data(reg_car_brand=text)
        await state.set_state(RegistrationStates.waiting_car_model)
        if text in CAR_DATABASE and text != "אחר (הקלדה ידנית)":
            return await message.answer(f"בחר דגם עבור **{text}**:", reply_markup=create_keyboard(list(CAR_DATABASE[text].keys()), columns=2))
        return await message.answer("✍️ הקלד ידנית את **דגם הרכב** (ללא סימנים מיוחדים):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))

    if current_state == RegistrationStates.waiting_car_model.state:
        if text.startswith('/'): return await message.answer("⚠️ קלט לא תקין.")
        await state.update_data(reg_car_model=text)
        await state.set_state(RegistrationStates.waiting_car_year)
        data = await state.get_data()
        brand = data.get('reg_car_brand')
        if brand in CAR_DATABASE and text in CAR_DATABASE[brand]:
            return await message.answer("📅 בחר **שנת ייצור**:", reply_markup=create_keyboard(sorted(CAR_DATABASE[brand][text], reverse=True), columns=4))
        return await message.answer("📅 הקלד את **שנת הרכב** (מספר, למשל 2020):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))

    if current_state == RegistrationStates.waiting_car_year.state:
        if not text.isdigit() or not (1980 <= int(text) <= 2027): return await message.answer("⚠️ נא להזין שנת רכב חוקית במספרים בלבד.")
        await state.update_data(reg_car_year=text)
        await state.set_state(RegistrationStates.waiting_car_seats)
        return await message.answer("💺 כמה **מקומות ישיבה** (ללא נהג, 4-50)?", reply_markup=create_keyboard(["4", "5", "6", "7", "10", "14", "20", "50"], columns=4))

    if current_state == RegistrationStates.waiting_car_seats.state:
        seats_val = int(text) if text.isdigit() and 4 <= int(text) <= 50 else 4
        data = await state.get_data()
        expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('''INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role, radius, cities, total_trips, rating, rating_count, is_blocked)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'busy', ?, ?, 0, '', 0, 0.0, 0, 0)''', 
                             (user_id, data.get('reg_name'), data.get('reg_phone'), data.get('reg_birth_year'), data.get('reg_car_brand'), data.get('reg_car_model'), data.get('reg_car_year'), seats_val, expiry, 'admin' if is_admin else 'user'))
            await db.commit()

        pending_lead = data.get('pending_lead')
        await state.clear()
        await message.answer(f"✅ **ההרשמה הושלמה!**\n🎁 מנוי חינמי ל-30 יום הופעל.", reply_markup=get_main_keyboard(user_id, 'admin' if is_admin else 'user', 'busy'))
        
        if pending_lead:
            async with aiosqlite.connect(DB_FILE) as db:
                db.row_factory = aiosqlite.Row
                lead = await (await db.execute('SELECT status, is_in_progress, message_text FROM leads WHERE lead_id = ?', (pending_lead,))).fetchone()
            if lead and lead['status'] == 'active':
                _, _, has_time = parse_order_text(lead['message_text'])
                await state.update_data(active_lead_id=pending_lead)
                msg_prefix = "⚠️ *הסדרן החל שיחה עם נהג אחר.*\n\n" if lead['is_in_progress'] else ""
                if has_time:
                    await state.set_state(BotStates.waiting_driver_time)
                    return await message.answer(f"{msg_prefix}⏱️ **קריאה זו דורשת זמן הגעה!**\nשלח כעת זמן בכתובת:")
                else:
                    await state.clear()
                    await message.answer(f"{msg_prefix}✅ בקשתך נשלחה לסדרן!")
                    await process_lead_request_safe(message, user_id, pending_lead, "לא צוין זמן")
        return

    if current_state == BotStates.waiting_driver_time.state:
        lead_id = (await state.get_data()).get('active_lead_id')
        await state.clear()
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            lead = await (await db.execute('SELECT is_in_progress FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
        msg_prefix = "⚠️ *הסדרן החל שיחה עם נהג אחר.*\n\n" if (lead and lead['is_in_progress']) else ""
        await message.answer(f"{msg_prefix}✅ בקשתך נשלחה לסדרן!", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        if lead_id: await process_lead_request_safe(message, user_id, lead_id, text)
        return

    # --- תפריט ראשי ותפעול ---
    if text == "🟢 פנוי לקריאות":
        await state.set_state(BotStates.waiting_add_city)
        return await message.answer("🟢 מעבר למצב פנוי לקריאות:\nשלח את **שם העיר/יישוב**:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))

    if text == "➕ הוסף עיר נוספת":
        await state.set_state(BotStates.waiting_append_city)
        return await message.answer("✍️ שלח שם עיר נוספת (יתווסף לרשימה):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))

    if current_state in [BotStates.waiting_add_city.state, BotStates.waiting_append_city.state]:
        city_name = text.strip()
        is_append = (current_state == BotStates.waiting_append_city.state)
        await state.update_data(selected_city=city_name, is_append=is_append)
        await state.set_state(BotStates.waiting_new_radius)
        return await message.answer(f"📍 העיר **{city_name}** נקלטה.\nלהוסיף רדיוס נסיעה מסביב לעיר?", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📍 ללא רדיוס (רק בעיר עצמה)")], [KeyboardButton(text="5 ק\"מ"), KeyboardButton(text="10 ק\"מ"), KeyboardButton(text="20 ק\"מ")], [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))

    if current_state == BotStates.waiting_new_radius.state:
        radius_val = 0 if "ללא רדיוס" in text else (int(text.replace('ק"מ', '').replace('קמ', '').strip()) if text.replace('ק"מ', '').replace('קמ', '').strip().isdigit() else 0)
        data = await state.get_data()
        city_name = data.get('selected_city', '')
        is_append = data.get('is_append', False)

        async with aiosqlite.connect(DB_FILE) as db:
            new_cities = f"{user['cities']}, {city_name}" if is_append and user['cities'] else city_name
            await db.execute('UPDATE users SET cities = ?, radius = ?, status = "free" WHERE user_id = ?', (new_cities, radius_val, user_id))
            await db.commit()
        await state.clear()
        rad_txt = "מדויק בעיר בלבד" if radius_val == 0 else f"כולל המרחב ({radius_val} ק\"מ)"
        return await message.answer(f"✅ סטטוס שונה ל**פנוי**!\n📍 ערים: {new_cities} | 📏 {rad_txt}", reply_markup=get_main_keyboard(user_id, role_val, 'free'))

    if text == "🔴 תפוס":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        return await message.answer("🔴 עודכנת לתפוס. האזורים אופסו.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))

    if text == "⚙️ הגדרת אזורים ורדיוס": return await message.answer("⚙️ ניהול אזורים וערים:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ הוסף עיר נוספת"), KeyboardButton(text="🗑️ מחק את כל הערים (איפס הכל)")], [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
    if text == "🗑️ מחק את כל הערים (איפס הכל)":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        return await message.answer("🗑️ כל אזורי הפעילות נמחקו. סטטוס: תפוס.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))

    if text == "💎 מצב מנוי ופרופיל":
        u = await get_user_dict(user_id)
        if not u: return
        rad_display = f"{u['radius']} ק\"מ" if u['radius'] > 0 else "ללא"
        rating_disp = f"{u['rating']:.1f} ⭐️ ({u['rating_count']} דירוגים)" if u['rating_count'] > 0 else "אין עדיין דירוג"
        return await message.answer(f"💎 **הפרופיל שלך:**\n\n👤 שם: {u['full_name']}\n🚗 רכב: {u['car_brand']} {u['car_model']} ({u['car_year']}) | מקומות: {u['car_seats']}\n🛡️ תפקיד: **{u['role']}**\n📅 תוקף: {u['expiry_date']}\n📦 נסיעות: {u['total_trips']}\n🌟 דירוג: {rating_disp}\n\n📍 ערים פנויות: **{u['cities'] if u['cities'] else 'תפוס'}**\n📏 רדיוס: {rad_display}", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    # ניהול והחלפת קריאה (מצב עריכה)
    if current_state == BotStates.waiting_edit_lead_text.state:
        lead_id = (await state.get_data()).get('edit_lead_id')
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("UPDATE leads SET message_text = ? WHERE lead_id = ?", (text, lead_id))
            await db.commit()
        await state.clear()
        return await message.answer("✅ תוכן הקריאה עודכן!", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    if current_state == BotStates.waiting_edit_lead_price.state:
        lead_id = (await state.get_data()).get('edit_lead_id')
        new_price = float(text) if text.isdigit() else 0.0
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("UPDATE leads SET price = ? WHERE lead_id = ?", (new_price, lead_id))
            await db.commit()
        await state.clear()
        return await message.answer(f"✅ המחיר עודכן ל-₪{new_price}!", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    if current_state == BotStates.waiting_manual_close_driver.state:
        lead_id = (await state.get_data()).get('manual_lead_id')
        async with aiosqlite.connect(DB_FILE) as db:
            target_driver = await (await db.execute("SELECT user_id, full_name, phone FROM users WHERE phone = ? OR full_name LIKE ?", (text, f"%{text}%"))).fetchone()
        if not target_driver: return await message.answer("⚠️ נהג לא נמצא. נסה שוב או ביטול.")
        driver_id, driver_name = target_driver[0], target_driver[1]
        
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            lead = await (await db.execute('SELECT message_text, phone_number, price, closed_with FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
            
            # אם כבר סגור על מישהו אחר, מחק את החוב הקודם שלו (החלפת נהג)
            if lead['closed_with']:
                await db.execute("DELETE FROM driver_debts WHERE order_id = ?", (lead_id,))
            
            await db.execute('UPDATE leads SET status = "closed", closed_with = ? WHERE lead_id = ?', (driver_name, lead_id))
            await db.execute('UPDATE users SET total_trips = total_trips + 1, status = "busy", cities = "" WHERE user_id = ?', (driver_id,))
            
            if lead and lead['price'] > 0:
                pub = await get_user_dict(user_id)
                st_id = pub['station_id'] if pub['station_id'] else 1
                st_info = await (await db.execute('SELECT commission_percent FROM stations WHERE station_id = ?', (st_id,))).fetchone()
                comm_pct = st_info['commission_percent'] if st_info else 10.0
                await db.execute('INSERT INTO driver_debts (user_id, station_id, amount, order_id, order_text, publisher_name, publisher_username, is_paid, date) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)', 
                                 (driver_id, st_id, (lead['price'] * comm_pct) / 100.0, lead_id, lead['message_text'], message.from_user.full_name, f"@{message.from_user.username}", datetime.now().strftime('%d/%m/%Y %H:%M')))
            await db.commit()

        try: await bot.send_message(driver_id, f"🎉 **הקריאה #{lead_id} נסגרה עליך! שונה לתפוס.**\n📝 תוכן: {lead['message_text']}\n📞 טלפון: {lead['phone_number']}")
        except: pass
        await state.clear()
        
        # הקפצת דירוג לסדרן
        rate_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐️", callback_data=f"rate_{driver_id}_1"), InlineKeyboardButton(text="⭐️⭐️", callback_data=f"rate_{driver_id}_2"), InlineKeyboardButton(text="⭐️⭐️⭐️", callback_data=f"rate_{driver_id}_3")],
            [InlineKeyboardButton(text="⭐️⭐️⭐️⭐️", callback_data=f"rate_{driver_id}_4"), InlineKeyboardButton(text="⭐️⭐️⭐️⭐️⭐️", callback_data=f"rate_{driver_id}_5")],
            [InlineKeyboardButton(text="⏭️ דלג", callback_data="rate_skip")]
        ])
        await message.answer(f"✅ קריאה #{lead_id} נסגרה על **{driver_name}** בהצלחה!\nהאם תרצה לדרג את הנהג?", reply_markup=rate_kb)
        return

    # מצב קריאות חכם
    if text == "📋 מצב קריאות":
        if not (is_admin or role_val in ['advertiser', 'station_manager', 'dispatcher']): return
        async with aiosqlite.connect(DB_FILE) as db:
            leads = await (await db.execute("SELECT lead_id, route_cities, status FROM leads ORDER BY lead_id DESC LIMIT 10")).fetchall()
        if not leads: return await message.answer("📋 אין קריאות רשומות.")
        
        kb_buttons = []
        for l_id, l_rt, l_st in leads:
            status_emoji = "🟢" if l_st == "active" else ("🔴" if l_st == "closed" else "🗑️")
            kb_buttons.append([InlineKeyboardButton(text=f"{status_emoji} קריאה #{l_id} | {l_rt[:20]}", callback_data=f"view_lead_{l_id}")])
        kb_buttons.append([InlineKeyboardButton(text="❌ סגור תפריט", callback_data="dest_cancel")])
        
        return await message.answer("📋 **ניהול 10 הקריאות האחרונות:**\nבחר קריאה לניהול:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))

    if text == "💳 חיובים":
        async with aiosqlite.connect(DB_FILE) as db:
            debts = await (await db.execute("SELECT d.amount, d.date, s.station_name FROM driver_debts d LEFT JOIN stations s ON d.station_id = s.station_id WHERE d.user_id = ? AND d.is_paid = 0", (user_id,))).fetchall()
        if not debts: return await message.answer("💳 אין חיובים פתוחים.")
        text_rep = "💳 **חיובים פתוחים:**\n\n"
        for amount, d_date, st_name in debts: text_rep += f"🏢 {st_name if st_name else 'כללי'} | ₪{amount:.2f} ({d_date})\n"
        return await message.answer(f"{text_rep}\n💵 **סה\"כ:** ₪{sum(d[0] for d in debts):.2f}")

    if text == "ℹ️ אודות ויצירת קשר": return await message.answer("ℹ️ **אודות ויצירת קשר:**", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="ℹ️ אודות המערכת"), KeyboardButton(text="📞 יצירת קשר")], [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
    if text == "ℹ️ אודות המערכת": return await message.answer("ℹ️ מערכת שילוח וניהול חכמה בטלגרם.")
    if text == "📞 יצירת קשר": return await message.answer("📞 לפניות תמיכה פנה למנהל.")
    
    if text in ["🛠️ פאנל מנהל", "פאנל מנהל"] and is_admin: return await message.answer("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())
    if text == "👥 ניהול משתמשים" and is_admin: return await message.answer("👥 ניהול משתמשים:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 רשימת משתמשים מלאה", callback_data="admin_list_users")], [InlineKeyboardButton(text="⬅️ חזרה לפאנל", callback_data="admin_back_main")]]))
    if text == "🏢 ניהול תחנות וקבוצות" and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            stations = await (await db.execute("SELECT station_id, station_name, commission_percent FROM stations")).fetchall()
        st_text = "🏢 **ניהול תחנות שילוח ועמלות:**\n\n"
        st_buttons = [[InlineKeyboardButton(text="➕ הוסף תחנה חדשה", callback_data="add_new_station")]]
        if stations:
            for s_id, s_name, s_comm in stations:
                st_text += f"• {s_name} | עמלה: {s_comm}%\n"
                st_buttons.append([InlineKeyboardButton(text=f"⚙️ ערוך תחנה: {s_name}", callback_data=f"edit_station_{s_id}")])
        return await message.answer(st_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=st_buttons))
    if text == "⚙️ ניהול קבוצות הבוט" and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            groups = await (await db.execute('SELECT group_id, group_title, is_active FROM bot_groups')).fetchall()
        if not groups: return await message.answer("⚠️ אין קבוצות מחוברות.")
        g_buttons = [[InlineKeyboardButton(text=f"{'🔴 השבת' if active else '🟢 הפעל'}: {title[:12]}", callback_data=f"toggle_group_{gid}")] for gid, title, active in groups]
        return await message.answer("🏢 **ניהול קבוצות מחוברות:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=g_buttons))

    if text == "📢 שידור הודעה לכולם" and is_admin:
        await state.set_state(BotStates.waiting_broadcast_all)
        return await message.answer("📢 שלח את טקסט השידור:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅ חזרה לתפריט הראשי")]], resize_keyboard=True))
    if current_state == BotStates.waiting_broadcast_all.state and is_admin:
        await state.clear()
        async with aiosqlite.connect(DB_FILE) as db:
            all_u = await (await db.execute("SELECT user_id FROM users")).fetchall()
        for (u_id,) in all_u:
            try: await bot.send_message(u_id, f"📢 **שידור מההנהלה:**\n\n{text}")
            except: pass
        return await message.answer("✅ ההודעה שודרה בהצלחה!", reply_markup=get_admin_keyboard())

    if current_state == BotStates.waiting_station_name_input.state and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT INTO stations (station_name, owner_id, commission_percent) VALUES (?, ?, ?)", (text, user_id, 10.0))
            await db.commit()
        await state.clear()
        return await message.answer(f"✅ תחנה **{text}** נוספה בהצלחה!", reply_markup=get_main_keyboard(user_id, role_val, current_status))

    if text == "📊 סטטיסטיקות מערכת" and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            t_users = (await (await db.execute('SELECT COUNT(*) FROM users')).fetchone())[0]
            t_leads = (await (await db.execute('SELECT COUNT(*) FROM leads')).fetchone())[0]
        return await message.answer(f"📊 סטטיסטיקות:\n• סך משתמשים: {t_users}\n• סך קריאות: {t_leads}")

    if text == "📢 פרסום הודעה":
        if not (is_admin or role_val in ['advertiser', 'station_manager', 'dispatcher']): return
        await state.set_state(BotStates.waiting_lead_text)
        return await message.answer("📢 פרסום קריאה חדשה:\nשלח את התוכן:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))
    
    if current_state == BotStates.waiting_lead_text.state:
        await state.update_data(lead_text=text)
        await state.set_state(BotStates.waiting_lead_phone)
        return await message.answer("📞 שלח מספר טלפון לקריאה:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))

    if current_state == BotStates.waiting_lead_phone.state:
        await state.update_data(lead_phone=text)
        return await message.answer("🎯 **בחר לאן לפרסם:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👥 לשליחים פרטיים", callback_data="dest_users")], [InlineKeyboardButton(text="🏢 לקבוצות הבוט", callback_data="dest_groups")], [InlineKeyboardButton(text="🚀 גם וגם", callback_data="dest_both")], [InlineKeyboardButton(text="❌ ביטול", callback_data="dest_cancel")]]))

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
    lead_disp += f"\n\nסטטוס: {'🟢 פעילה' if lead['status'] == 'active' else ('🔴 סגורה על '+str(lead['closed_with']) if lead['status'] == 'closed' else '🗑️ נמחקה')}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ערוך תוכן", callback_data=f"editl_txt_{lead_id}"), InlineKeyboardButton(text="💰 ערוך מחיר", callback_data=f"editl_price_{lead_id}")],
        [InlineKeyboardButton(text="🔄 החלפת נהג / סגירה", callback_data=f"manual_close_{lead_id}")],
        [InlineKeyboardButton(text="🗑️ מחיקה וביטול קריאה", callback_data=f"delete_lead_{lead_id}")],
        [InlineKeyboardButton(text="❌ סגור חלון ניהול", callback_data="dest_cancel")]
    ])
    try: await callback.message.edit_text(lead_disp, reply_markup=kb)
    except: await callback.message.answer(lead_disp, reply_markup=kb)

@dp.callback_query(F.data.startswith("editl_txt_"))
async def cb_edit_lead_text(callback: CallbackQuery, state: FSMContext):
    lead_id = int(callback.data.replace("editl_txt_", ""))
    await state.set_state(BotStates.waiting_edit_lead_text)
    await state.update_data(edit_lead_id=lead_id)
    await callback.message.answer("✏️ שלח את התוכן החדש לקריאה:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))

@dp.callback_query(F.data.startswith("editl_price_"))
async def cb_edit_lead_price(callback: CallbackQuery, state: FSMContext):
    lead_id = int(callback.data.replace("editl_price_", ""))
    await state.set_state(BotStates.waiting_edit_lead_price)
    await state.update_data(edit_lead_id=lead_id)
    await callback.message.answer("💰 שלח את המחיר החדש לקריאה (בספרות בלבד):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))

@dp.callback_query(F.data.startswith("rate_"))
async def cb_rate_driver(callback: CallbackQuery):
    if callback.data == "rate_skip":
        await callback.message.delete()
        return await callback.answer("דילגת על דירוג הנהג.")
    
    parts = callback.data.split("_")
    driver_id, stars = int(parts[1]), int(parts[2])
    
    async with aiosqlite.connect(DB_FILE) as db:
        driver = await (await db.execute('SELECT rating, rating_count FROM users WHERE user_id = ?', (driver_id,))).fetchone()
        if driver:
            new_count = driver[1] + 1
            new_rating = ((driver[0] * driver[1]) + stars) / new_count
            await db.execute('UPDATE users SET rating = ?, rating_count = ? WHERE user_id = ?', (new_rating, new_count, driver_id))
            await db.commit()
    
    await callback.message.delete()
    await callback.answer(f"תודה! דירגת את הנהג ב-{stars} כוכבים.")

# --- אדמין מתקדם ---
@dp.callback_query(F.data == "admin_back_main")
async def cb_admin_back(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "admin_list_users")
async def cb_admin_list_users(callback: CallbackQuery):
    if await check_user_auth(callback.from_user.id) in ["blocked", "expired"] or callback.from_user.id not in ADMIN_IDS: return await callback.answer("אין גישה.")
    async with aiosqlite.connect(DB_FILE) as db:
        users = await (await db.execute("SELECT user_id, full_name, role, expiry_date FROM users LIMIT 30")).fetchall()
    txt = "👥 **רשימת משתמשים וניהול:**\n\n"
    buttons = [[InlineKeyboardButton(text=f"⚙️ נהל: {name[:10]} ({role})", callback_data=f"manage_user_{uid}")] for uid, name, role, exp in users]
    buttons.append([InlineKeyboardButton(text="⬅️ חזרה", callback_data="admin_back_main")])
    try: await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except:
        await callback.message.delete()
        await callback.message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("manage_user_"))
async def cb_manage_user(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    uid = int(callback.data.replace("manage_user_", ""))
    u = await get_user_dict(uid)
    if not u: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ הארך מנוי ב-30 יום", callback_data=f"extend_sub_{uid}_30")],
        [InlineKeyboardButton(text="🛡️ שנה תפקיד", callback_data=f"change_role_{uid}"), InlineKeyboardButton(text="🏢 שייך לתחנה", callback_data=f"assign_station_{uid}")],
        [InlineKeyboardButton(text="💸 איפוס חובות (שולם)", callback_data=f"clear_debts_{uid}")],
        [InlineKeyboardButton(text="❌ חסום / בטל", callback_data=f"toggle_block_{uid}")],
        [InlineKeyboardButton(text="⬅️ חזרה", callback_data="admin_list_users")]
    ])
    await callback.message.edit_text(f"👤 **ניהול:** {u['full_name']}\n• תפקיד: **{u['role']}**\n• דירוג: {u['rating']:.1f}⭐️\n• תוקף: {u['expiry_date']}\n• תחנה (לסדרן): {u['station_id']}", reply_markup=kb)

@dp.callback_query(F.data.startswith("change_role_"))
async def cb_change_role(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    uid = int(callback.data.replace("change_role_", ""))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👤 רגיל", callback_data=f"setrole_{uid}_user"), InlineKeyboardButton(text="📢 סדרן", callback_data=f"setrole_{uid}_dispatcher")], [InlineKeyboardButton(text="⬅️ חזרה", callback_data=f"manage_user_{uid}")]])
    await callback.message.edit_text("בחר הרשאה:", reply_markup=kb)

@dp.callback_query(F.data.startswith("setrole_"))
async def cb_setrole(callback: CallbackQuery):
    uid, new_role = int(callback.data.split("_")[1]), callback.data.split("_")[2]
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, uid))
        await db.commit()
    await cb_manage_user(callback)

@dp.callback_query(F.data.startswith("assign_station_"))
async def cb_assign_station(callback: CallbackQuery):
    uid = int(callback.data.replace("assign_station_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        stations = await (await db.execute("SELECT station_id, station_name FROM stations")).fetchall()
    kb = [[InlineKeyboardButton(text=s[1], callback_data=f"linkstation_{uid}_{s[0]}")] for s in stations]
    kb.append([InlineKeyboardButton(text="⬅️ חזרה", callback_data=f"manage_user_{uid}")])
    await callback.message.edit_text("🏢 בחר תחנה:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("linkstation_"))
async def cb_linkstation(callback: CallbackQuery):
    uid, st_id = int(callback.data.split("_")[1]), int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET station_id = ? WHERE user_id = ?", (st_id, uid))
        await db.commit()
    await cb_manage_user(callback)

@dp.callback_query(F.data.startswith("clear_debts_"))
async def cb_clear_debts(callback: CallbackQuery):
    uid = int(callback.data.replace("clear_debts_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE driver_debts SET is_paid = 1 WHERE user_id = ?", (uid,))
        await db.commit()
    await callback.answer("חובות אופסו!", show_alert=True)
    await cb_manage_user(callback)

@dp.callback_query(F.data.startswith("extend_sub_"))
async def cb_extend_sub(callback: CallbackQuery):
    uid, days = int(callback.data.split("_")[2]), int(callback.data.split("_")[3])
    async with aiosqlite.connect(DB_FILE) as db:
        row = await (await db.execute("SELECT expiry_date FROM users WHERE user_id = ?", (uid,))).fetchone()
        base = datetime.now()
        if row and row[0]:
            try:
                p_dt = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                if p_dt > base: base = p_dt
            except: pass
        await db.execute("UPDATE users SET expiry_date = ? WHERE user_id = ?", ((base + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S'), uid))
        await db.commit()
    await cb_manage_user(callback)

@dp.callback_query(F.data.startswith("toggle_block_"))
async def cb_toggle_block(callback: CallbackQuery):
    uid = int(callback.data.replace("toggle_block_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        row = await (await db.execute("SELECT is_blocked FROM users WHERE user_id = ?", (uid,))).fetchone()
        await db.execute("UPDATE users SET is_blocked = ? WHERE user_id = ?", (0 if row[0] == 1 else 1, uid))
        await db.commit()
    await cb_manage_user(callback)

# --- פרסום קריאה מלאה ---
@dp.callback_query(F.data.startswith("dest_"))
async def destination_chosen(callback: CallbackQuery, state: FSMContext):
    action = callback.data.replace("dest_", "")
    if action == "cancel":
        await state.clear()
        try: await callback.message.delete()
        except: pass
        return await callback.message.answer("❌ בוטל.", reply_markup=get_main_keyboard(callback.from_user.id))

    data = await state.get_data()
    text_content, phone_content = data.get('lead_text'), data.get('lead_phone')
    user_id = callback.from_user.id
    cities, price, _ = parse_order_text(text_content)

    async with aiosqlite.connect(DB_FILE) as db:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = await db.execute('INSERT INTO leads (publisher_id, message_text, phone_number, created_at, price, route_cities, is_in_progress) VALUES (?, ?, ?, ?, ?, ?, 0)', (user_id, text_content, phone_content, now_str, price if price else 0.0, " ➔ ".join(cities) if cities else ""))
        lead_id = cursor.lastrowid
        await db.commit()

    await state.clear()
    await callback.message.edit_text(f"✅ קריאה #{lead_id} נוצרה ונשלחת לשליחים!")
    
    pub_user = await get_user_dict(user_id)
    pub_name = pub_user['full_name'] if pub_user else "סדרן"
    st_name = "כללי"
    if pub_user and pub_user['station_id']:
        async with aiosqlite.connect(DB_FILE) as db:
            st = await (await db.execute('SELECT station_name FROM stations WHERE station_id = ?', (pub_user['station_id'],))).fetchone()
            if st: st_name = st[0]

    alert_msg = generate_lead_display(text_content, lead_id, price if price else 0.0, " ➔ ".join(cities), pub_name, st_name)
    origin_city = [c.strip() for c in cities][0] if cities else ""
    sent_users, sent_groups = 0, 0

    if action in ["users", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            free_users = await (await db.execute("SELECT user_id, cities, radius FROM users WHERE status = 'free'")).fetchall()
        for f_uid, f_cities, f_radius in free_users:
            matched = False
            if not origin_city: matched = True
            else:
                user_cities_list = [c.strip() for c in f_cities.split(',') if f_cities]
                for u_c in user_cities_list:
                    if (f_radius == 0 and u_c == origin_city) or (f_radius > 0 and (u_c in origin_city or origin_city in u_c)):
                        matched = True; break
            if matched:
                try:
                    await bot.send_message(f_uid, alert_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]]))
                    sent_users += 1
                except: pass

    if action in ["groups", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            active_groups = await (await db.execute("SELECT group_id FROM bot_groups WHERE is_active = 1")).fetchall()
        for (g_id,) in active_groups:
            try:
                await bot.send_message(g_id, alert_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]]))
                sent_groups += 1
            except: pass

    await callback.message.answer(f"📢 הופצה ל-{sent_users} שליחים פרטיים ו-{sent_groups} קבוצות!", reply_markup=get_main_keyboard(user_id, pub_user['role'] if pub_user else 'admin', pub_user['status'] if pub_user else 'free'))

async def process_lead_request_safe(message_or_callback, requester_id: int, lead_id: int, driver_time: str):
    async with aiosqlite.connect(DB_FILE) as db:
        lead = await (await db.execute('SELECT publisher_id, status FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
    if not lead or lead[1] != 'active': return

    requester_user = await get_user_dict(requester_id)
    req_chat = await bot.get_chat(requester_id)
    rad_text = "ללא" if requester_user['radius'] == 0 else f"{requester_user['radius']} ק\"מ"
    rating_disp = f"{requester_user['rating']:.1f} ⭐️" if requester_user['rating_count'] > 0 else "ללא דירוג"

    alert = (
        f"🔔 **בקשה לקריאה #{lead_id}**\n\n"
        f"⏱ זמן הגעה: {driver_time}\n\n"
        f"👤 **נהג:** {requester_user['full_name']} (@{req_chat.username})\n"
        f"🌟 דירוג: {rating_disp}\n"
        f"• טלפון: {requester_user['phone']}\n"
        f"• רכב: {requester_user['car_brand']} {requester_user['car_model']} | מקומות: {requester_user['car_seats']}\n"
        f"• אזור: `{requester_user['cities']}` | רדיוס: {rad_text}\n\nהאם לאשר או לסגור פנייה?"
    )

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ אישור פנייה (פתיחת שיחה)", callback_data=f"app_only_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="✅ סגור עליו + עמלה", callback_data=f"app_close_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="🔒 סגור ידנית אחר", callback_data=f"manual_close_{lead_id}")],
        [InlineKeyboardButton(text="🗑️ מחיקה", callback_data=f"delete_lead_{lead_id}")],
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
    try: await bot.send_message(requester_id, f"✅ הבקשה לקריאה #{lead_id} אושרה!")
    except: pass
    await callback.answer("סומן בטיפול.")

@dp.callback_query(F.data.startswith("rej_lead_"))
async def cb_rej_lead(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id, requester_id = int(parts[2]), int(parts[3])
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
    pub_name = pub_user['full_name'] if pub_user else "סדרן"
    pub_st_id = pub_user['station_id'] if pub_user and pub_user['station_id'] else 1

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        st_info = await (await db.execute('SELECT commission_percent FROM stations WHERE station_id = ?', (pub_st_id,))).fetchone()
        comm_pct = st_info['commission_percent'] if st_info else 10.0

        await db.execute('UPDATE leads SET status = "closed", closed_with = ? WHERE lead_id = ?', (f"@{callback.from_user.username}", lead_id))
        await db.execute('UPDATE users SET total_trips = total_trips + 1, status = "busy", cities = "" WHERE user_id = ?', (requester_id,))
        
        lead_data = await (await db.execute('SELECT message_text, phone_number, price FROM leads WHERE lead_id = ?', (lead_id,))).fetchone()
        if lead_data and lead_data['price'] > 0:
            now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
            await db.execute('INSERT INTO driver_debts (user_id, station_id, amount, order_id, order_text, publisher_name, publisher_username, is_paid, date) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)', 
                             (requester_id, pub_st_id, (lead_data['price'] * comm_pct) / 100.0, lead_id, lead_data['message_text'], pub_name, f"@{callback.from_user.username}", now_str))
        await db.commit()

    try: await bot.send_message(requester_id, f"🎉 **קריאה #{lead_id} נסגרה עליך! שונה לתפוס.**\n📝 תוכן: {lead_data['message_text']}\n📞 טלפון: {lead_data['phone_number']}")
    except: pass
    await callback.message.edit_text(f"✅ קריאה #{lead_id} נסגרה בהצלחה!")
    
    rate_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️", callback_data=f"rate_{requester_id}_1"), InlineKeyboardButton(text="⭐️⭐️", callback_data=f"rate_{requester_id}_2"), InlineKeyboardButton(text="⭐️⭐️⭐️", callback_data=f"rate_{requester_id}_3")],
        [InlineKeyboardButton(text="⭐️⭐️⭐️⭐️", callback_data=f"rate_{requester_id}_4"), InlineKeyboardButton(text="⭐️⭐️⭐️⭐️⭐️", callback_data=f"rate_{requester_id}_5")],
        [InlineKeyboardButton(text="⏭️ דלג", callback_data="rate_skip")]
    ])
    await callback.message.answer(f"נשמח אם תדרג את הנהג:", reply_markup=rate_kb)

async def main():
    await init_db()
    await start_web_server()
    print("✨ בוט גרסה 4.0: דירוגים, אבטחת הרשמה 18+, מאגר רכבים ותפריט חכם מוכנים!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
