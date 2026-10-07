import os
import asyncio
import logging
import sys
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

# טעינה וניקוי אוטומטי של טוקן הבוט ממשתני הסביבה (שומר על הקיים במדויק)
RAW_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_TOKEN = RAW_TOKEN.strip().replace("[", "").replace("]", "").replace("'", "").replace('"', "").replace(" ", "")

print(f"DEBUG_CHECK -> Final Cleaned Token: '{BOT_TOKEN}'")

if not BOT_TOKEN:
    print("שגיאה קריטית: משתנה הסביבה BOT_TOKEN ריק או לא מוגדר!")
    sys.exit(1)

ADMIN_IDS = [8644923212, 552821474]  # מנהלי המערכת הראשיים
DB_FILE = 'bot_database_v3.db'

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# שרת HTTP פנימי לשמירת הבוט חי ב-Render בחינם
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
    waiting_phone = State()
    waiting_car_brand = State()
    waiting_car_model = State()
    waiting_car_year = State()
    waiting_car_seats = State()

class BotStates(StatesGroup):
    waiting_add_city = State()
    waiting_new_radius = State()
    waiting_broadcast_all = State()
    waiting_lead_text = State()
    waiting_lead_phone = State()
    waiting_manual_price = State()
    waiting_driver_time = State()
    waiting_station_name_input = State()
    editing_lead_content = State()

CAR_BRANDS = [
    "טיוטה (Toyota)", "הונדה (Honda)", "יונדאי (Hyundai)", "קיה (Kia)",
    "מזדה (Mazda)", "סקודה (Skoda)", "פולקסווגן (Volkswagen)", "מיצובישי (Mitsubishi)",
    "ניסאן (Nissan)", "סוזוקי (Suzuki)", "סובארו (Subaru)", "ביวיאדי (BYD)",
    "ג'ילי (Geely)", "שאופן (Xpeng)", "تسלה (Tesla)", "מרצדס (Mercedes)",
    "ב.מ.וו (BMW)", "אאודי (Audi)", "רנו (Renault)", "פיג'ו (Peugeot)", "סיטרואן (Citroen)", "אחר"
]

ISRAELI_CITIES = [
    "ירושלים", "תל אביב - יפו", "חיפה", "ראשון לציון", "פתח תקווה", "אשדוד", "נתניה", "בני ברק", "באר שבע", "חולון",
    "רמת גן", "אשקלון", "בת ים", "בית שמש", "הרצליה", "כפר סבא", "חדרה", "מודיעין-מכבים-רעות", "נצרת", "לוד",
    "רמלה", "רחובות", "מודיעין עילית", "ביתר עילית", "אלעד", "בית שאן", "אופקים", "אריאל", "אילת",
    "דימונה", "הוד השרון", "זכרון יעקב", "טבריה", "טירה", "טמרה", "יבנה", "יהוד-מונוסון", "יקנעם עילית",
    "כפר יונה", "כפר קאסם", "כרמיאל", "מגדל העמק", "מעלה אדומים", "מעלות-תרשיחא", "נהריה", "נס ציונה",
    "נשר", "נתיבות", "עכו", "עפולה", "ערד", "צפת", "קלנסווה",
    "קריית אונו", "קריית אתא", "קריית ביאליק", "קריית גת", "קריית ים", "קריית מוצקין", "קריית מלאכי", "קריית שמונה",
    "ראש העין", "רהט", "רמת השרון", "רעננה", "שדרות", "שפרעם", "אבו גוש", "בית דגן", "גבעת שמואל", "גבעתיים", "גָדֵרָה", "חריש", "מבשרת ציון",
    "מצפה רמון", "עומר", "פרדס חנה-כרכור", "קצרין", "אפרת", "בית אל", "גוש עציון", "חשמונאים"
]

CITY_ALIASES = {
    "ים": "ירושלים", "פת": "פתח תקווה", "תא": "תל אביב - יפו", "שדה": "שדה תעופה", "סבא": "כפר סבא",
    "ראשון": "ראשון לציון", "רג": "רמת גן", "ירושלים": "ירושלים", "שמש": "בית שמש", "בית שמש": "בית שמש",
    "בב": "בני ברק", "בני ברק": "בני ברק", "מודיעין": "מודיעין-מכבים-רעות", "ספר": "מודיעין עילית", "מודיעין עילית": "מודיעין עילית"
}

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
                station_id INTEGER,
                radius INTEGER DEFAULT 5,
                cities TEXT DEFAULT '',
                total_trips INTEGER DEFAULT 0,
                stars_silver INTEGER DEFAULT 0,
                stars_gold INTEGER DEFAULT 0,
                rating REAL DEFAULT 0.0,
                rating_count INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS stations (
                station_id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_name TEXT,
                owner_id INTEGER,
                commission_percent REAL DEFAULT 10.0
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_groups (
                group_id INTEGER PRIMARY KEY,
                group_title TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS driver_debts (
                debt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                station_id INTEGER,
                amount REAL,
                order_id INTEGER,
                order_text TEXT,
                publisher_name TEXT,
                publisher_username TEXT,
                is_paid BOOLEAN DEFAULT 0,
                date TEXT
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
                publisher_id INTEGER,
                message_text TEXT,
                phone_number TEXT,
                status TEXT DEFAULT 'active',
                closed_with TEXT DEFAULT NULL,
                created_at TEXT,
                price REAL DEFAULT 0.0,
                route_cities TEXT DEFAULT '',
                station_id INTEGER DEFAULT NULL
            )
        ''')
        await db.commit()

def parse_order_text(text: str):
    lines = text.strip().split('\n')
    found_cities = []
    price = None

    for line in lines[:2]:
        for alias, full_name in CITY_ALIASES.items():
            if alias in line and full_name not in found_cities:
                found_cities.append(full_name)
        for city in ISRAELI_CITIES:
            if city in line and city not in found_cities:
                found_cities.append(city)

    for line in lines[:3]:
        import re
        numbers = re.findall(r'\b\d+\b', line)
        for num_str in numbers:
            num = int(num_str)
            if num >= 30 and num % 10 == 0:
                price = float(num)
                break
        if price:
            break

    import re
    has_time_mention = bool(re.search(r'זמנ[ן]{1,6}|זמני[ם]{1,6}', text) or re.search(r'זמן[ן]{1,6}', text))
    return found_cities, price, has_time_mention

async def get_user(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role, station_id, radius, cities, total_trips, rating, rating_count, is_blocked FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

def get_main_keyboard(user_id, role='user', current_status='busy'):
    is_admin = (user_id in ADMIN_IDS or role == 'admin')
    is_advertiser = is_admin or (role in ['advertiser', 'station_manager', 'dispatcher'])
    is_regular_user = (role == 'user' and not is_admin)

    status_btn_text = "🟢 פנוי לקריאות" if current_status == 'free' else "🔴 תפוס"
    kb = []
    
    if is_admin or is_advertiser:
        kb.append([KeyboardButton(text="📢 פרסום הודעה"), KeyboardButton(text="📋 מצב קריאות")])
        
    kb.append([KeyboardButton(text=status_btn_text), KeyboardButton(text="⚙️ הגדרת אזורים ורדיוס")])
    
    if is_regular_user or role == 'user':
        kb.append([KeyboardButton(text="💳 חיובים"), KeyboardButton(text="💎 מצב מנוי ופרופיל")])
    else:
        kb.append([KeyboardButton(text="💎 מצב מנוי ופרופיל")])

    kb.append([KeyboardButton(text="ℹ️ אודות ויצירת קשר")])
    
    if is_admin:
        kb.append([KeyboardButton(text="🛠️ פאנל מנהל")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 ניהול משתמשים"), KeyboardButton(text="📊 סטטיסטיקות מערכת")],
        [KeyboardButton(text="📢 שידור הודעה לכולם"), KeyboardButton(text="🏢 ניהול תחנות וקבוצות")],
        [KeyboardButton(text="⚙️ ניהול קבוצות הבוט"), KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
    ], resize=True)

@dp.my_chat_member()
async def bot_chat_member_handler(event: ChatMemberUpdated):
    chat = event.chat
    if chat.type in ["group", "supergroup"]:
        new_status = event.new_chat_member.status
        async with aiosqlite.connect(DB_FILE) as db:
            if new_status in ["member", "administrator"]:
                await db.execute('INSERT OR REPLACE INTO bot_groups (group_id, group_title, is_active) VALUES (?, ?, 1)', (chat.id, chat.title))
                await db.commit()
            elif new_status in ["left", "kicked"]:
                await db.execute('UPDATE bot_groups SET is_active = 0 WHERE group_id = ?', (chat.id,))
                await db.commit()

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)
    
    if is_admin and not user:
        async with aiosqlite.connect(DB_FILE) as db:
            expiry = (datetime.now() + timedelta(days=3650)).strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role, is_blocked) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, "busy", ?, "admin", 0)
            ''', (user_id, "מנהל מערכת", "0000000000", "2000-01-01", "מרצדס", "S-Class", "2025", 4, expiry))
            await db.commit()
        user = await get_user(user_id)

    if user and not is_admin:
        expiry_str = user[8]
        try:
            expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
            if datetime.now() > expiry_dt:
                await message.answer("❌ **פג תוקף המנוי שלך (30 יום)!**\nאינך יכול להשתמש בבוט עד שמנהל המערכת יאריך את המנוי שלך דרך פאנל הניהול.")
                return
        except:
            pass

    role_val = user[9] if user else ('admin' if is_admin else 'user')
    current_status = user[7] if user else 'busy'
    is_blocked = user[16] if user and len(user) > 16 else 0

    if is_blocked:
        await message.answer("❌ חשבונך חסום במערכת.")
        return

    if message.text and message.text.startswith("/start lead_"):
        lead_id_str = message.text.replace("/start lead_", "").strip()
        try:
            lead_id = int(lead_id_str)
        except:
            lead_id = None

        if not user and not message.from_user.username:
            await message.answer("⚠️ **שגיאה: אין לך שם משתמש (Username) בטלגרם!**\nחובה להגדיר שם משתמש בהגדרות הפרופיל כדי לבקש קריאות.")
            return

        if not user:
            await state.update_data(pending_lead=lead_id)
            await state.set_state(RegistrationStates.waiting_name)
            await message.answer("👋 שלום וברוכים הבאים!\nכדי לבקש את הקריאה חובה להשלים רישום קצר.\n\nאנא שלח את **השם המלא** שלך:")
            return

        if lead_id:
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute('SELECT status, message_text FROM leads WHERE lead_id = ?', (lead_id,)) as cursor:
                    lead = await cursor.fetchone()
                    if lead and lead[0] == 'active':
                        _, _, has_time = parse_order_text(lead[1])
                        await state.update_data(active_lead_id=lead_id)
                        if has_time:
                            await state.set_state(BotStates.waiting_driver_time)
                            await message.answer("⏱️ **קריאה זו דורשת זמן הגעה!**\nאנא שלח כעת את **הזמן** שלך בכתובת (למשל: 15 דקות):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
                        else:
                            await state.clear()
                            await message.answer("✅ בקשתך נשלחה בהצלחה למפרסם!", reply_markup=get_main_keyboard(user_id, role_val, current_status))
                            await process_lead_request_safe(message, user_id, lead_id, "לא צוין זמן")
        return

    if not user:
        if not message.from_user.username:
            await message.answer("⚠️ **שגיאה: אין לך שם משתמש (Username) בטלגרם!**\nחובה להגדיר שם משתמש לפני תחילת השימוש.")
            return
        await state.set_state(RegistrationStates.waiting_name)
        await message.answer("👋 שלום וברוכים הבאים לבוט הניהול והשילוח המתקדם! 🚀\n\nכדי להתחיל, אנא שלח את **השם המלא** שלך:")
        return

    await state.clear()
    await message.answer("🎛️ **תפריט ראשי:** בחר אפשרות מהמקלדת למטה:", reply_markup=get_main_keyboard(user_id, role_val, current_status))

@dp.message()
async def handle_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    user = await get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)

    if user and not is_admin:
        expiry_str = user[8]
        try:
            if datetime.now() > datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S'):
                await message.answer("❌ **פג תוקף המנוי שלך (30 יום)!**\nאינך יכול להשתמש בבוט עד שמנהל המערכת יאריך את המנוי שלך.")
                return
        except:
            pass

    role_val = user[9] if user else ('admin' if is_admin else 'user')
    current_status = user[7] if user else 'busy'
    is_blocked = user[16] if user and len(user) > 16 else 0

    if is_blocked:
        await message.answer("❌ חשבונך חסום במערכת.")
        return

    if text in ["/start", "תפריט", "⬅️ חזרה לתפריט הראשי", "⬅ חזרה לתפריט הראשי", "❌ ביטול"]:
        await state.clear()
        await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    current_state = await state.get_state()

    if current_state == RegistrationStates.waiting_name.state:
        await state.update_data(reg_name=text)
        await state.set_state(RegistrationStates.waiting_phone)
        phone_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 שיתוף מספר טלפון", request_contact=True), KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True)
        await message.answer("תודה! כעת לחץ על הכפתור למטה כדי לשתף את **מספר הטלפון** שלך:", reply_markup=phone_kb)
        return

    if current_state == RegistrationStates.waiting_phone.state:
        phone = message.contact.phone_number if message.contact else text
        await state.update_data(reg_phone=phone)
        await state.set_state(RegistrationStates.waiting_car_brand)
        
        brand_buttons = [[KeyboardButton(text=b)] for b in CAR_BRANDS[:12]]
        brand_buttons.append([KeyboardButton(text="⬅️ חזרה לתפריט הראשי")])
        brand_kb = ReplyKeyboardMarkup(keyboard=brand_buttons, resize_keyboard=True)
        await message.answer("🚗 מעולה! כעת בחר את **חברת הרכב** שלך מהרשימה או הקלד אותה:", reply_markup=brand_kb)
        return

    if current_state == RegistrationStates.waiting_car_brand.state:
        await state.update_data(reg_car_brand=text)
        await state.set_state(RegistrationStates.waiting_car_model)
        await message.answer("✍️ שלח כעת את **דגם הרכב** שלך (למשל: קורולה, ספורטאז', אוקטביה):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
        return

    if current_state == RegistrationStates.waiting_car_model.state:
        await state.update_data(reg_car_model=text)
        await state.set_state(RegistrationStates.waiting_car_year)
        
        years_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="2026"), KeyboardButton(text="2025"), KeyboardButton(text="2024"), KeyboardButton(text="2023")],
            [KeyboardButton(text="2022"), KeyboardButton(text="2021"), KeyboardButton(text="2020"), KeyboardButton(text="2019")],
            [KeyboardButton(text="2018 ומטה"), KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        await message.answer("📅 בחר את **שנת הרכב**:", reply_markup=years_kb)
        return

    if current_state == RegistrationStates.waiting_car_year.state:
        await state.update_data(reg_car_year=text)
        await state.set_state(RegistrationStates.waiting_car_seats)
        
        seats_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="4"), KeyboardButton(text="5"), KeyboardButton(text="6"), KeyboardButton(text="7")],
            [KeyboardButton(text="10"), KeyboardButton(text="14"), KeyboardButton(text="20"), KeyboardButton(text="50")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        await message.answer("💺 כמה **מקומות ישיבה** יש ברכב שלך (ללא הנהג, בין 4 ל-50)?", reply_markup=seats_kb)
        return

    if current_state == RegistrationStates.waiting_car_seats.state:
        try:
            seats_val = int(text)
            if seats_val < 4: seats_val = 4
            if seats_val > 50: seats_val = 50
        except:
            seats_val = 4

        data = await state.get_data()
        name = data.get('reg_name')
        phone = data.get('reg_phone')
        brand = data.get('reg_car_brand')
        model = data.get('reg_car_model')
        car_year = data.get('reg_car_year')
        
        role = 'admin' if is_admin else 'user'
        expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, car_brand, car_model, car_year, car_seats, status, expiry_date, role, radius, cities, total_trips, rating, rating_count, is_blocked)
                VALUES (?, ?, ?, '2000-01-01', ?, ?, ?, ?, 'busy', ?, ?, 5, '', 0, 0.0, 0, 0)
            ''', (user_id, name, phone, brand, model, car_year, seats_val, expiry, role))
            await db.commit()

        pending_lead = data.get('pending_lead')
        await state.clear()
        await message.answer(
            f"✅ **ההרשמה הושלמה בהצלחה!**\n"
            f"🎁 קיבלת במתנה **מנוי חינמי ל-30 יום** (בתוקף עד: {expiry}).\n"
            f"🚗 רכב: {brand} {model} ({car_year}) | מקומות: {seats_val}",
            reply_markup=get_main_keyboard(user_id, role, 'busy')
        )
        if pending_lead:
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute('SELECT status, message_text FROM leads WHERE lead_id = ?', (pending_lead,)) as cursor:
                    lead = await cursor.fetchone()
                    if lead and lead[0] == 'active':
                        _, _, has_time = parse_order_text(lead[1])
                        await state.update_data(active_lead_id=pending_lead)
                        if has_time:
                            await state.set_state(BotStates.waiting_driver_time)
                            await message.answer("⏱️ **קריאה זו דורשת זמן הגעה!**\nאנא שלח כעת את **הזמן** שלך בכתובת:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
                        else:
                            await state.clear()
                            await message.answer("✅ בקשתך נשלחה בהצלחה למפרסם!")
                            await process_lead_request_safe(message, user_id, pending_lead, "לא צוין זמן")
        return

    if text == "🟢 פנוי לקריאות":
        await state.set_state(BotStates.waiting_add_city)
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True)
        await message.answer(
            "🟢 מעבר למצב פנוי לקריאות:\n"
            "שלח כעת את שם העיר/ישוב שבה אתה פנוי מתוך רשימת היישובים בישראל:",
            reply_markup=kb
        )
        return

    if text == "🔴 תפוס":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        await message.answer("🔴 הסטטוס שלך עודכן לתפוס וכל אזורי הפעילות שלך אופסו.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))
        return

    if current_state == BotStates.waiting_add_city.state:
        city_name = text.strip()
        await state.update_data(selected_city=city_name)
        await state.set_state(BotStates.waiting_new_radius)
        
        radius_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="3 ק\"מ"), KeyboardButton(text="5 ק\"מ"), KeyboardButton(text="10 ק\"מ")],
            [KeyboardButton(text="20 ק\"מ"), KeyboardButton(text="40 ק\"מ")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        
        await message.answer(f"📍 העיר **{city_name}** נקלטה.\nכעת בחר את **רדיוס הנסיעה** המבוקש:", reply_markup=radius_kb)
        return

    if current_state == BotStates.waiting_new_radius.state:
        radius_val = 5
        try:
            clean_rad = text.replace('ק"מ', '').replace('קמ', '').strip()
            radius_val = int(clean_rad)
        except:
            radius_val = 5

        data = await state.get_data()
        city_name = data.get('selected_city', 'ישראל')

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET cities = ?, radius = ?, status = "free" WHERE user_id = ?', (city_name, radius_val, user_id))
            await db.commit()

        await state.clear()
        await message.answer(f"✅ סטטוס שונה ל**פנוי**!\n📍 עיר מוגדרת: {city_name} | 📏 רדיוס: {radius_val} ק\"מ", reply_markup=get_main_keyboard(user_id, role_val, 'free'))
        return

    if text == "⚙️ הגדרת אזורים ורדיוס":
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="➕ הוסף עיר נוספת"), KeyboardButton(text="🗑️ מחק את כל הערים (איפס הכל)")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        await message.answer("⚙️ ניהול אזורים וערים:\nבחר את הפעולה הרצויה:", reply_markup=kb)
        return

    if text == "➕ הוסף עיר נוספת":
        await state.set_state(BotStates.waiting_add_city)
        await message.answer("✍️ שלח כעת את שם העיר הנוספת שתרצה להוסיף לרשימת הפעילות שלך:")
        return

    if text == "🗑️ מחק את כל הערים (איפס הכל)":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        await message.answer("🗑️ כל אזורי הפעילות שלך נמחקו והסטטוס אופס לתפוס.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))
        return

    if text == "💎 מצב מנוי ופרופיל":
        u_data = await get_user(user_id)
        if not u_data:
            await message.answer("⚠️ לא נמצאו נתוני פרופיל. שלח /start כדי להירשם.")
            return
            
        u_name = u_data[0] if u_data[0] else "לא ידוע"
        brand = u_data[3] if u_data[3] else "לא מוגדר"
        model = u_data[4] if u_data[4] else ""
        car_year = u_data[5] if u_data[5] else ""
        seats = u_data[6] if u_data[6] else 4
        expiry_val = u_data[8] if u_data[8] else "לא מוגבל"
        radius_val = u_data[11] if u_data[11] else 5
        cities_val = u_data[12] if u_data[12] else ""
        total_trips = u_data[13] if u_data[13] else 0

        await message.answer(
            f"💎 **האזור האישי והפרופיל שלך:**\n\n"
            f"👤 שם מלא: {u_name}\n"
            f"🚗 רכב: {brand} {model} ({car_year}) | מקומות: {seats}\n"
            f"🛡️ תפקיד במערכת: **{role_val}**\n"
            f"📅 תוקף מנוי עד: {expiry_val}\n"
            f"📦 נסיעות שבוצעו: {total_trips}\n\n"
            f"📍 עיר פנויה כעת: **{cities_val if cities_val else 'לא מוגדר (תפוס)'}**\n"
            f"📏 רדיוס: {radius_val} ק\"מ\n"
            f"🟢 סטטוס: {'פנוי' if current_status == 'free' else 'תפוס'}",
            reply_markup=get_main_keyboard(user_id, role_val, current_status)
        )
        return

    if text == "📋 מצב קריאות":
        is_advertiser = is_admin or (role_val in ['advertiser', 'station_manager', 'dispatcher'])
        if not is_advertiser:
            await message.answer("⚠️ אין לך הרשאה לצפות במצב הקריאות.")
            return
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT lead_id, message_text, price, route_cities, status FROM leads ORDER BY lead_id DESC LIMIT 10") as cur:
                leads = await cur.fetchall()
        if not leads:
            await message.answer("📋 אין קריאות רשומות במערכת כרגע.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            return
        rep = "📋 **10 הקריאות האחרונות במערכת:**\n\n"
        for l_id, l_txt, l_pr, l_rt, l_st in leads:
            rep += f"• **קריאה #{l_id}** | סטטוס: `{l_st}`\n"
            rep += f"  📍 מסלול: {l_rt if l_rt else 'לא זוהה'}\n"
            rep += f"  💰 מחיר: ₪{l_pr}\n"
            rep += f"  📝 {l_txt[:40]}...\n"
            rep += "-----------------------------------\n"
        await message.answer(rep, reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    if text == "💳 חיובים":
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT d.amount, d.order_text, d.publisher_name, d.publisher_username, d.date, s.station_name FROM driver_debts d LEFT JOIN stations s ON d.station_id = s.station_id WHERE d.user_id = ?", (user_id,)) as cur:
                debts = await cur.fetchall()
        if not debts:
            await message.answer("💳 אין לך חיובים פתוחים או היסטוריית חיובים במערכת.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            return
        text_rep = "💳 **החיובים והעמלות שלך לפי תחנות:**\n\n"
        total_sum = 0
        for amount, order_text, pub_name, pub_uname, d_date, st_name in debts:
            total_sum += amount
            st_display = st_name if st_name else "כללי"
            text_rep += f"🏢 תחנה: {st_display} | עמלה: ₪{amount:.2f} ({d_date})\n"
        text_rep += f"\n💵 **סה\"כ לתשלום:** ₪{total_sum:.2f}"
        await message.answer(text_rep, reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    if text == "ℹ️ אודות ויצירת קשר":
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="ℹ️ אודות המערכת"), KeyboardButton(text="📞 יצירת קשר")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        await message.answer("ℹ️ **אודות ויצירת קשר:**", reply_markup=kb)
        return

    if text == "ℹ️ אודות המערכת":
        await message.answer("ℹ️ מערכת שילוח וניהול חכמה בטלגרם.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    if text == "📞 יצירת קשר":
        await message.answer("📞 לפניות ותמיכה פנה למנהל המערכת.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    if text in ["🛠️ פאנל מנהל", "פאנל מנהל"] and is_admin:
        await message.answer("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())
        return

    if text == "👥 ניהול משתמשים" and is_admin:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 רשימת משתמשים מלאה", callback_data="admin_list_users")],
            [InlineKeyboardButton(text="⬅️ חזרה לפאנל", callback_data="admin_back_main")]
        ])
        await message.answer("👥 ניהול משתמשים:", reply_markup=kb)
        return

    if text == "📊 סטטיסטיקות מערכת" and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute('SELECT COUNT(*) FROM users') as cur:
                t_users = (await cur.fetchone())[0]
            async with db.execute('SELECT COUNT(*) FROM leads') as cur:
                t_leads = (await cur.fetchone())[0]
        await message.answer(f"📊 סטטיסטיקות:\n• סך משתמשים: {t_users}\n• סך קריאות: {t_leads}", reply_markup=get_admin_keyboard())
        return

    if text == "📢 שידור הודעה לכולם" and is_admin:
        await state.set_state(BotStates.waiting_broadcast_all)
        await message.answer("📢 שלח כעת את טקסט השידור לכל המשתמשים:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅ חזרה לתפריט הראשי")]], resize_keyboard=True))
        return

    if current_state == BotStates.waiting_broadcast_all.state and is_admin:
        await state.clear()
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id FROM users") as cur:
                all_u = await cur.fetchall()
        succ = 0
        for (u_id,) in all_u:
            try:
                await bot.send_message(u_id, f"📢 **שידור מההנהלה:**\n\n{text}")
                succ += 1
            except:
                pass
        await message.answer(f"✅ נשלח ל-{succ} משתמשים!", reply_markup=get_admin_keyboard())
        return

    if text == "📢 פרסום הודעה":
        is_advertiser = is_admin or (role_val in ['advertiser', 'station_manager', 'dispatcher'])
        if not is_advertiser:
            await message.answer("⚠️ אין לך הרשאה לפרסם.")
            return
        await state.set_state(BotStates.waiting_lead_text)
        await message.answer("📢 פרסום קריאה חדשה:\nשלח את תוכן הקריאה (מסלול ומחיר):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))
        return

    if current_state == BotStates.waiting_lead_text.state:
        if text == "❌ ביטול":
            await state.clear()
            await message.answer("❌ בוטל.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            return
        await state.update_data(lead_text=text)
        await state.set_state(BotStates.waiting_lead_phone)
        await message.answer("📞 שלח את מספר הטלפון של הלקוח לקריאה:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))
        return

    if current_state == BotStates.waiting_lead_phone.state:
        if text == "❌ ביטול":
            await state.clear()
            await message.answer("❌ בוטל.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            return
        phone_val = text
        await state.update_data(lead_phone=phone_val)
        
        dest_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 למשתמשי הבוט הפרטיים", callback_data="dest_users")],
            [InlineKeyboardButton(text="🏢 לקבוצות הבוט", callback_data="dest_groups")],
            [InlineKeyboardButton(text="🚀 גם וגם", callback_data="dest_both")],
            [InlineKeyboardButton(text="❌ ביטול", callback_data="dest_cancel")]
        ])
        await message.answer("🎯 **בחר לאן לפרסם:**", reply_markup=dest_kb)
        return

@dp.callback_query(F.data == "admin_list_users")
async def cb_admin_list_users(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, full_name, role, expiry_date FROM users LIMIT 25") as cur:
            users = await cur.fetchall()
    txt = "👥 **רשימת משתמשים וניהול מנויים:**\n\n"
    buttons = []
    for uid, name, role, exp in users:
        txt += f"• {name} (`{uid}`) | תוקף: {exp}\n"
        buttons.append([InlineKeyboardButton(text=f"⚙️ ערוך מנוי: {name[:10]}", callback_data=f"manage_user_{uid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ חזרה", callback_data="admin_back_main")])
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("manage_user_"))
async def cb_manage_user(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    uid = int(callback.data.replace("manage_user_", ""))
    u_data = await get_user(uid)
    if not u_data:
        await callback.answer("משתמש לא נמצא.")
        return
    name, phone, _, brand, model, year, seats, _, expiry, role, _, _, cities, trips, _, _, blocked = u_data
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ הארך מנוי ב-30 יום", callback_data=f"extend_sub_{uid}_30")],
        [InlineKeyboardButton(text="➕ הארך ב-365 יום (שנה)", callback_data=f"extend_sub_{uid}_365")],
        [InlineKeyboardButton(text="❌ חסום / בטל חסימה", callback_data=f"toggle_block_{uid}")],
        [InlineKeyboardButton(text="⬅️ חזרה לרשימה", callback_data="admin_list_users")]
    ])
    await callback.message.edit_text(
        f"👤 **ניהול משתמש:** {name}\n"
        f"• ID: `{uid}` | טלפון: {phone}\n"
        f"• רכב: {brand} {model} ({year}) | מקומות: {seats}\n"
        f"• תוקף מנוי נוכחי: **{expiry}**",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("extend_sub_"))
async def cb_extend_sub(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    parts = callback.data.split("_")
    uid = int(parts[2])
    days = int(parts[3])

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT expiry_date FROM users WHERE user_id = ?", (uid,)) as cur:
            row = await cur.fetchone()
        base_date = datetime.now()
        if row and row[0]:
            try:
                parsed_dt = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                if parsed_dt > base_date:
                    base_date = parsed_dt
            except:
                pass
        new_expiry = (base_date + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        await db.execute("UPDATE users SET expiry_date = ? WHERE user_id = ?", (new_expiry, uid))
        await db.commit()

    await callback.answer(f"המנוי הואריך עד {new_expiry}!")
    await cb_manage_user(callback)

@dp.callback_query(F.data.startswith("toggle_block_"))
async def cb_toggle_block(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    uid = int(callback.data.replace("toggle_block_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT is_blocked FROM users WHERE user_id = ?", (uid,)) as cur:
            row = await cur.fetchone()
        if row:
            new_b = 0 if row[0] == 1 else 1
            await db.execute("UPDATE users SET is_blocked = ? WHERE user_id = ?", (new_b, uid))
            await db.commit()
            await callback.answer("סטטוס חסימה עודכן!")
            await cb_manage_user(callback)

@dp.callback_query(F.data == "admin_back_main")
async def cb_admin_back(callback: CallbackQuery):
    await callback.message.edit_text("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data.startswith("dest_"))
async def destination_chosen(callback: CallbackQuery, state: FSMContext):
    action = callback.data.replace("dest_", "")
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ בוטל.", reply_markup=get_main_keyboard(callback.from_user.id, 'admin', 'free'))
        return

    data = await state.get_data()
    text_content = data.get('lead_text')
    phone_content = data.get('lead_phone')
    user_id = callback.from_user.id

    cities, price, has_time = parse_order_text(text_content)

    async with aiosqlite.connect(DB_FILE) as db:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = await db.execute('''
            INSERT INTO leads (publisher_id, message_text, phone_number, created_at, price, route_cities) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, text_content, phone_content, now_str, price if price else 0.0, " ➔ ".join(cities) if cities else ""))
        lead_id = cursor.lastrowid
        await db.commit()

    await state.clear()
    await callback.message.edit_text(f"✅ קריאה #{lead_id} נוצרה ונשלחת לשליחים המתאימים!")
    await finish_publishing_lead(callback.message, lead_id, action)

async def finish_publishing_lead(message_or_cb, lead_id: int, action="both"):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT publisher_id, message_text, phone_number, price, route_cities FROM leads WHERE lead_id = ?', (lead_id,)) as cur:
            lead = await cur.fetchone()
    if not lead:
        return
    publisher_id, text_content, phone_content, price, route_cities = lead
    cities = [c.strip() for c in route_cities.split('➔') if c.strip()]
    origin_city = cities[0] if cities else ""

    alert_msg = (
        f"🚀 **קריאה חדשה זמינה! (#{lead_id})**\n\n"
        f"📍 מסלול: {route_cities if route_cities else 'כללי'}\n"
        f"💰 מחיר: ₪{price if price > 0 else 'לא צוין'}\n\n"
        f"📝 **פרטים:**\n{text_content}"
    )

    sent_users = 0
    sent_groups = 0

    if action in ["users", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id, cities, radius FROM users WHERE status = 'free'") as cursor:
                free_users = await cursor.fetchall()
        for f_uid, f_cities, f_radius in free_users:
            matched = False
            if not origin_city:
                matched = True
            else:
                user_cities_list = [c.strip() for c in f_cities.split(',') if f_cities]
                for u_c in user_cities_list:
                    if u_c in origin_city or origin_city in u_c:
                        matched = True
                        break
            if matched:
                try:
                    link_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]])
                    await bot.send_message(f_uid, alert_msg, reply_markup=link_btn)
                    sent_users += 1
                except:
                    pass

    if action in ["groups", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT group_id FROM bot_groups WHERE is_active = 1") as cursor:
                active_groups = await cursor.fetchall()
        for (g_id,) in active_groups:
            try:
                group_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]])
                await bot.send_message(g_id, alert_msg, reply_markup=group_btn)
                sent_groups += 1
            except:
                pass

    pub_user_full = await get_user(publisher_id)
    pub_role = pub_user_full[9] if pub_user_full else 'admin'
    pub_status = pub_user_full[7] if pub_user_full else 'free'
    main_kb = get_main_keyboard(publisher_id, pub_role, pub_status)

    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(f"📢 הקריאה הופצה בהצלחה ל-{sent_users} שליחים פרטיים התואמים לאזור ו-{sent_groups} קבוצות!", reply_markup=main_kb)
    else:
        await bot.send_message(publisher_id, f"📢 הקריאה הופצה בהצלחה ל-{sent_users} שליחים פרטיים התואמים לאזור ו-{sent_groups} קבוצות!", reply_markup=main_kb)

async def process_lead_request_safe(message_or_callback, requester_id: int, lead_id: int, driver_time: str):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT publisher_id, message_text, phone_number, status, price, route_cities FROM leads WHERE lead_id = ?', (lead_id,)) as cursor:
            lead = await cursor.fetchone()

    if not lead or lead[3] != 'active':
        return

    publisher_id, message_text, phone_number, status, price, route_cities = lead
    requester_user = await get_user(requester_id)
    requester = await bot.get_chat(requester_id)

    req_name = requester_user[0] if requester_user else "לא ידוע"
    req_phone = requester_user[1] if requester_user else "לא זמין"
    req_brand, req_model, req_seats = requester_user[3], requester_user[4], requester_user[6]
    req_username = f"@{requester.username}" if requester.username else "אין יוזר"
    req_cities = requester_user[12] if requester_user else ""

    alert_to_publisher = (
        f"🔔 **התקבלה בקשה לקריאה #{lead_id}**\n\n"
        f"📍 מסלול: {route_cities if route_cities else 'לא זוהה'}\n"
        f"💰 מחיר: ₪{price if price > 0 else 'לא צוין'}\n"
        f"⏱ זמן הגעה: {driver_time}\n\n"
        f"👤 **פרטי הנהג והרכב:**\n"
        f"• שם: {req_name} ({req_username})\n"
        f"• טלפון: {req_phone}\n"
        f"• רכב: {req_brand} {req_model} | מקומות: {req_seats}\n"
        f"• עיר נוכחית: `{req_cities}`\n\n"
        f"האם לאשר או לסגור את הפנייה?"
    )

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ אישור בלבד", callback_data=f"app_only_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="✅ אישור + סגירת קריאה וחיוב", callback_data=f"app_close_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="❌ דחייה", callback_data=f"rej_lead_{lead_id}_{requester_id}")],
    ])

    await bot.send_message(publisher_id, alert_to_publisher, reply_markup=buttons)

@dp.callback_query(F.data.startswith("app_only_"))
async def cb_app_only(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id = int(parts[2])
    requester_id = int(parts[3])
    try:
        await bot.send_message(requester_id, f"✅ הבקשה שלך לקריאה #{lead_id} אושרה על ידי הסדרן!")
    except:
        pass
    await callback.message.edit_text(f"✅ הבקשה לקריאה #{lead_id} אושרה.")

@dp.callback_query(F.data.startswith("rej_lead_"))
async def cb_rej_lead(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id = int(parts[2])
    requester_id = int(parts[3])
    try:
        await bot.send_message(requester_id, f"❌ בקשתך לקריאה #{lead_id} נדחתה.")
    except:
        pass
    await callback.message.edit_text(f"❌ הבקשה נדחתה.")

@dp.callback_query(F.data.startswith("app_close_"))
async def app_close_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id = int(parts[2])
    requester_id = int(parts[3])
    publisher_id = callback.from_user.id

    pub_user = await get_user(publisher_id)
    pub_name = pub_user[0] if pub_user else "סדרן"
    publisher = await bot.get_chat(publisher_id)
    pub_username = f"@{publisher.username}" if publisher.username else f"מזהה: {publisher_id}"

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE leads SET status = "closed", closed_with = ? WHERE lead_id = ?', (pub_username, lead_id))
        await db.execute('UPDATE users SET total_trips = total_trips + 1 WHERE user_id = ?', (requester_id,))
        
        async with db.execute('SELECT message_text, phone_number, price FROM leads WHERE lead_id = ?', (lead_id,)) as cur:
            lead_data = await cur.fetchone()
        
        msg_text = lead_data[0] if lead_data else ""
        customer_phone = lead_data[1] if lead_data else "לא זמין"
        price_val = lead_data[2] if lead_data else 0.0

        if price_val > 0:
            comm_amount = (price_val * 10.0) / 100.0
            now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
            await db.execute('''
                INSERT INTO driver_debts (user_id, station_id, amount, order_id, order_text, publisher_name, publisher_username, is_paid, date)
                VALUES (?, 1, ?, ?, ?, ?, ?, 0, ?)
            ''', (requester_id, comm_amount, lead_id, msg_text, pub_name, pub_username, now_str))

        await db.commit()

    try:
        await bot.send_message(
            requester_id,
            f"🎉 **עדכון משמח! הקריאה #{lead_id} נסגרה עליך!**\n\n"
            f"📝 תוכן: {msg_text}\n📞 טלפון לקוח: {customer_phone}\n👨‍💻 סדרן: {pub_name}"
        )
    except:
        pass

    await callback.message.edit_text(f"✅ קריאה #{lead_id} נסגרה על הנהג בהצלחה!")

async def main():
    await init_db()
    await start_web_server()
    print("✨ בוט השילוח והניהול פועל בהצלחה עם שרת Web פנימי ופרופיל מתוקן!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
