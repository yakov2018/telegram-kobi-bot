import os
import asyncio
import logging
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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8954258047:AAFVjP0kntKxD10Q2_a97-VyPwGJFrwSFqo")
ADMIN_IDS = [8644923212, 552821474]  # מנהלי המערכת הראשיים שלך ושל השותף
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

# מצבי רישום (4 שלבים)
class RegistrationStates(StatesGroup):
    waiting_fullname = State()
    waiting_phone = State()
    waiting_birthyear = State()
    waiting_car_make = State()
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

CAR_MAKES = ["יונדאי", "טויוטה", "קיה", "מאזדה", "סקודה", "פולקסווגן", "מרצדס", "ב.מ.וו", "מיצובישי", "ניסאן", "הונדה", "סיאט", "אחר"]

CITY_ALIASES = {
    "ים": "ירושלים",
    "פת": "פתח תקווה",
    "תא": "תל אביב",
    "שדה": "שדה תעופה",
    "סבא": "כפר סבא",
    "ראשון": "ראשון לציון",
    "רג": "רמת גן",
    "ירושלים": "ירושלים",
    "שמש": "בית שמש",
    "בית שמש": "בית שמש",
    "בב": "בני ברק",
    "בני ברק": "בני ברק",
    "רג'": "רמת גן",
    "רמת גן": "רמת גן",
    "ספר": "מודיעין עלית",
    "מודיעין עלית": "מודיעין עלית"
}

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                birth_year TEXT,
                car_make TEXT,
                car_model TEXT,
                car_year TEXT,
                car_seats TEXT,
                status TEXT DEFAULT 'busy',
                expiry_date TEXT,
                role TEXT DEFAULT 'user',
                station_id INTEGER,
                radius INTEGER DEFAULT 5,
                cities TEXT DEFAULT '',
                total_trips INTEGER DEFAULT 0,
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
        async with db.execute('SELECT full_name, phone, birth_year, car_make, car_model, car_year, car_seats, status, expiry_date, role, station_id, radius, cities, total_trips, rating, rating_count, is_blocked FROM users WHERE user_id = ?', (user_id,)) as cursor:
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
    
    if is_regular_user:
        kb.append([KeyboardButton(text="💳 חיובים"), KeyboardButton(text="💎 מצב מנוי ופרופיל")])
    else:
        kb.append([KeyboardButton(text="💎 מצב מנוי ופרופיל")])

    kb.append([KeyboardButton(text="ℹ️️ אודות ויצירת קשר")])
    
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
    
    # בדיקת חובה לשם משתמש (Username) בטלגרם
    if not message.from_user.username:
        await message.answer("⚠️ **שגיאה: אין לך שם משתמש (Username) בטלגרם!**\nחובה להגדיר שם משתמש בהגדרות הפרופיל שלך בטלגרם, ולאחר מכן לחץ שוב על /start.")
        return

    user = await get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)
    role_val = 'admin' if is_admin else 'user'
    current_status = user[7] if user else 'busy'
    is_blocked = user[16] if user and len(user) > 16 else 0

    if is_blocked:
        await message.answer("❌ חשבונך חסום במערכת.")
        return

    # יצירת מנהל מערכת אוטומטית לשנינו
    if is_admin and not user:
        async with aiosqlite.connect(DB_FILE) as db:
            expiry = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_year, car_make, car_model, car_year, car_seats, status, expiry_date, role, is_blocked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'busy', ?, 'admin', 0)
            ''', (user_id, "מנהל מערכת", "0000000000", "2000", "רכב מנהלים", "דגם ראשי", "2024", "4", expiry))
            await db.commit()
        user = await get_user(user_id)

    if message.text and message.text.startswith("/start lead_"):
        lead_id_str = message.text.replace("/start lead_", "").strip()
        try:
            lead_id = int(lead_id_str)
        except:
            lead_id = None

        if not user:
            await state.update_data(pending_lead=lead_id)
            await state.set_state(RegistrationStates.waiting_fullname)
            await message.answer("👋 שלום וברוכים הבאים!\nכדי לבקש קריאות חובה להשלים רישום קצר בן 4 שלבים.\n\nאנא שלח את **השם המלא** שלך (פרטי ומשפחה):")
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

    # אם המשתמש לא רשום - מתחילים רישום 4 שלבים
    if not user:
        await state.set_state(RegistrationStates.waiting_fullname)
        await message.answer("👋 שלום וברוכים הבאים לבוט השילוח והניהול! 🚀\n\nכדי להתחיל להשתמש במערכת, עליך לעבור רישום קצר.\nשלב 1 מתוך 4: אנא שלח את **השם המלא** שלך (פרטי ומשפחה):")
        return

    await state.clear()
    await message.answer("🎛️ **תפריט ראשי:** בחר אפשרות מהמקלדת למטה:", reply_markup=get_main_keyboard(user_id, role_val, current_status))

@dp.message()
async def handle_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    user = await get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)
    role_val = user[10] if user else ('admin' if is_admin else 'user')
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

    # --- תהליך רישום 4 שלבים ---
    if current_state == RegistrationStates.waiting_fullname.state:
        await state.update_data(reg_fullname=text)
        await state.set_state(RegistrationStates.waiting_phone)
        phone_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 שיתוף מספר טלפון", request_contact=True), KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True)
        await message.answer("שלב 2 מתוך 4: לחץ על הכפתור למטה כדי **לשתף את מספר הטלפון** שלך:", reply_markup=phone_kb)
        return

    if current_state == RegistrationStates.waiting_phone.state:
        phone = message.contact.phone_number if message.contact else text
        await state.update_data(reg_phone=phone)
        await state.set_state(RegistrationStates.waiting_birthyear)
        await message.answer("שלב 3 מתוך 4: אנא שלח את **שנת הלידה** שלך (למשל: 1995):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
        return

    if current_state == RegistrationStates.waiting_birthyear.state:
        await state.update_data(reg_birthyear=text)
        await state.set_state(RegistrationStates.waiting_car_make)
        
        # יצירת מקלדת יצרני רכב
        car_buttons = [[KeyboardButton(text=make)] for make in CAR_MAKES]
        car_buttons.append([KeyboardButton(text="⬅️ חזרה לתפריט הראשי")])
        car_kb = ReplyKeyboardMarkup(keyboard=car_buttons, resize_keyboard=True)
        
        await message.answer("שלב 4 מתוך 4 (פרטי רכב): בחר את **יצרן הרכב** שלך מהרשימה או הקלד:", reply_markup=car_kb)
        return

    if current_state == RegistrationStates.waiting_car_make.state:
        await state.update_data(reg_car_make=text)
        await state.set_state(RegistrationStates.waiting_car_model)
        await message.answer("🚗 מהו **דגם הרכב** שלך? (למשל: אלנטרה, קורולה, אוקטביה):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
        return

    if current_state == RegistrationStates.waiting_car_model.state:
        await state.update_data(reg_car_model=text)
        await state.set_state(RegistrationStates.waiting_car_year)
        await message.answer("📅 מהו **שנתון הרכב**? (למשל: 2021):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
        return

    if current_state == RegistrationStates.waiting_car_year.state:
        await state.update_data(reg_car_year=text)
        await state.set_state(RegistrationStates.waiting_car_seats)
        
        seats_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="4 מקומות"), KeyboardButton(text="5 מקומות"), KeyboardButton(text="6 מקומות")],
            [KeyboardButton(text="7 מקומות"), KeyboardButton(text="8 מקומות"), KeyboardButton(text="9+ מקומות")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        
        await message.answer("💺 כמה **מקומות ישיבה** יש ברכב (מלבד הנהג)?", reply_markup=seats_kb)
        return

    if current_state == RegistrationStates.waiting_car_seats.state:
        data = await state.get_data()
        fullname = data.get('reg_fullname')
        phone = data.get('reg_phone')
        birthyear = data.get('reg_birthyear')
        c_make = data.get('reg_car_make')
        c_model = data.get('reg_car_model')
        c_year = data.get('reg_car_year')
        c_seats = text

        async with aiosqlite.connect(DB_FILE) as db:
            expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_year, car_make, car_model, car_year, car_seats, status, expiry_date, role, radius, cities, total_trips, rating, rating_count, is_blocked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'busy', ?, ?, 5, '', 0, 0.0, 0, 0)
            ''', (user_id, fullname, phone, birthyear, c_make, c_model, c_year, c_seats, expiry, role_val))
            await db.commit()

        pending_lead = data.get('pending_lead')
        await state.clear()
        await message.answer("✅ **הרישום הושלם בהצלחה! כרטיסיית הנהג שלך נוצרה ונשמרה במערכת.**", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))
        
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

    # --- פקודות טקסט חופשיות לסטטוס "פנוי" (למשל: "פנוי ירושלים", "פ ירושלים", "פ א ירושלים") ---
    if text.startswith("פנוי ") or text.startswith("פ ") or text.startswith("פא ") or text.startswith("פ א "):
        city_input = text.replace("פנוי", "").replace("פ א", "").replace("פא", "").replace("פ", "").strip()
        if city_input:
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('UPDATE users SET cities = ?, status = "free" WHERE user_id = ?', (city_input, user_id))
                await db.commit()
            await message.answer(f"🟢 סטטוס שונה ל**פנוי**!\n📍 אזור פעילות: {city_input}", reply_markup=get_main_keyboard(user_id, role_val, 'free'))
            return

    # מענה לזמן הגעה מקריאה
    if current_state == BotStates.waiting_driver_time.state:
        data = await state.get_data()
        lead_id = data.get('active_lead_id')
        driver_time = text
        await state.clear()
        await message.answer("✅ בקשתך נשלחה בהצלחה למפרסם!", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        if lead_id:
            await process_lead_request_safe(message, user_id, lead_id, driver_time)
        return

    if current_state == BotStates.waiting_manual_price.state:
        data = await state.get_data()
        lead_id = data.get('lead_id')
        try:
            manual_price = float(text)
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("UPDATE leads SET price = ? WHERE lead_id = ?", (manual_price, lead_id))
                await db.commit()
            await state.clear()
            await message.answer(f"✅ המחיר ₪{manual_price} נקלט והוגדר לקריאה #{lead_id}.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            await finish_publishing_lead(message, lead_id)
        except:
            await message.answer("⚠️ נא להזין סכום מספרי תקין (או לחץ ביטול):")
        return

    if text == "🟢 פנוי לקריאות":
        await state.set_state(BotStates.waiting_add_city)
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True)
        await message.answer(
            "🟢 מעבר למצב פנוי לקריאות:\n"
            "שלח כעת את שם העיר/ישוב שבה אתה פנוי (או השתמש בקיצור כמו 'פ ירושלים'):",
            reply_markup=kb
        )
        return

    if text == "🔴 תפוס":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        await message.answer("🔴 הסטטוס שלך עודכן לתפוס וכל אזורי הפעילות שלך אופסו ונמחקו במערכת.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))
        return

    if current_state == BotStates.waiting_add_city.state:
        city_name = text
        await state.update_data(selected_city=city_name)
        await state.set_state(BotStates.waiting_new_radius)
        
        radius_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="3 ק\"מ"), KeyboardButton(text="5 ק\"מ"), KeyboardButton(text="10 ק\"מ")],
            [KeyboardButton(text="20 ק\"מ"), KeyboardButton(text="40 ק\"מ")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        
        await message.answer(f"📍 העיר **{city_name}** נקלטה.\nכעת בחר את **רדיוס הנסיעה** המבוקש (בין 3 ל-40 ק\"מ) או הקלד מספר חופשי:", reply_markup=radius_kb)
        return

    if current_state == BotStates.waiting_new_radius.state:
        radius_val = 5
        try:
            clean_rad = text.replace('ק"מ', '').replace('קמ', '').strip()
            radius_val = int(clean_rad)
            if radius_val < 3: radius_val = 3
            if radius_val > 40: radius_val = 40
        except:
            radius_val = 5

        data = await state.get_data()
        city_name = data.get('selected_city', 'ישראל')

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET cities = ?, radius = ?, status = "free" WHERE user_id = ?', (city_name, radius_val, user_id))
            await db.commit()

        await state.clear()
        await message.answer(f"✅ סטטוס שונה ל**פנוי**!\n📍 אזור: {city_name} | 📏 רדיוס: {radius_val} ק\"מ", reply_markup=get_main_keyboard(user_id, role_val, 'free'))
        return

    if text == "⚙️ הגדרת אזורים ורדיוס":
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="➕ הוסף עיר נוספת"), KeyboardButton(text="🗑️️ מחק את כל הערים (איפס הכל)")],
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
        await message.answer("🗑️ כל אזורי הפעילות שלך נמחקו והסטטוס שלך אופס לתפוס מלא.", reply_markup=get_main_keyboard(user_id, role_val, 'busy'))
        return

    # --- מצב קריאות (כולל הצגת סטטוס, סדרן, וכפתורי שליטה מלאים) ---
    if text == "📋 מצב קריאות":
        is_advertiser = is_admin or (role_val in ['advertiser', 'station_manager', 'dispatcher'])
        if not is_advertiser:
            await message.answer("⚠️ אין לך הרשאה לצפות במצב הקריאות.")
            return
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT lead_id, message_text, price, route_cities, status, publisher_id FROM leads ORDER BY lead_id DESC LIMIT 10") as cur:
                leads = await cur.fetchall()
        if not leads:
            await message.answer("📋 אין קריאות רשומות במערכת כרגע.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            return
        
        await message.answer("📋 **רשימת הקריאות האחרונות במערכת:**", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        for l_id, l_txt, l_pr, l_rt, l_st, pub_id in leads:
            pub_chat = await bot.get_chat(pub_id)
            pub_uname = f"@{pub_chat.username}" if pub_chat.username else f"ID: {pub_id}"
            
            lead_desc = (
                f"📌 **קריאה #{l_id}**\n"
                f"• סטטוס: `{l_st}`\n"
                f"• מסלול: {l_rt if l_rt else 'לא זוהה'}\n"
                f"• מחיר: ₪{l_pr}\n"
                f"• סדרן מפרסם: {pub_uname}\n"
                f"• תוכן: {l_txt[:50]}..."
            )
            
            kb_actions = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔒 סגור", callback_data=f"lead_action_close_{l_id}"),
                    InlineKeyboardButton(text="🔓 פתח", callback_data=f"lead_action_open_{l_id}"),
                    InlineKeyboardButton(text="🗑️ מחק", callback_data=f"lead_action_del_{l_id}")
                ]
            ])
            await message.answer(lead_desc, reply_markup=kb_actions)
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
            text_rep += f"🏢 **תחנה:** {st_display}\n"
            text_rep += f"💰 **סכום חיוב (עמלה):** ₪{amount:.2f}\n"
            text_rep += f"📅 **תאריך ושעה:** {d_date}\n"
            text_rep += f"👨‍💻 **סדרן:** {pub_name} ({pub_uname})\n"
            text_rep += f"📝 **פרטי קריאה:** {order_text[:60]}...\n"
            text_rep += "-----------------------------------\n"

        text_rep += f"💵 **סה\"כ לתשלום:** ₪{total_sum:.2f}"
        await message.answer(text_rep, reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    # --- מצב מנוי ופרופיל (עם הצגה מדויקת של שם העיר) ---
    if text == "💎 מצב מנוי ופרופיל":
        u_data = await get_user(user_id)
        u_name = u_data[0] if u_data else "לא ידוע"
        c_make = u_data[3] if u_data and len(u_data) > 3 else "לא מוגדר"
        c_model = u_data[4] if u_data and len(u_data) > 4 else ""
        c_year = u_data[5] if u_data and len(u_data) > 5 else ""
        c_seats = u_data[6] if u_data and len(u_data) > 6 else ""
        radius_val = u_data[12] if u_data and len(u_data) > 12 else 5
        cities_val = u_data[13] if u_data and len(u_data) > 13 else ""
        total_trips = u_data[14] if u_data and len(u_data) > 14 else 0
        u_rating = u_data[15] if u_data and len(u_data) > 15 else 0.0
        expiry_val = u_data[8] if u_data and len(u_data) > 8 else "לא מוגבל"

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT amount, is_paid FROM driver_debts WHERE user_id = ?", (user_id,)) as cursor:
                debts = await cursor.fetchall()
        total_debt = sum([d[0] for d in debts if not d[1]])

        car_full_desc = f"{c_make} {c_model} ({c_year}) | {c_seats} מקומות"

        await message.answer(
            f"💎 **האזור האישי והפרופיל שלך:**\n\n"
            f"👤 שם מלא: {u_name}\n"
            f"🚗 רכב: {car_full_desc}\n"
            f"🛡️ תפקיד במערכת: **{role_val}**\n"
            f"📅 תוקף מנוי עד: {expiry_val}\n"
            f"📦 סך נסיעות/משלוחים שבוצעו: {total_trips}\n"
            f"⭐ דירוג ממוצע: {u_rating:.1f} כוכבים\n"
            f"💳 סך חובות פתוחים לתחנות: ₪{total_debt:.2f}\n\n"
            f"📍 עיר פעילות מוגדרת: **{cities_val if cities_val else 'לא מוגדר (תפוס)'}**\n"
            f"📏 רדיוס: {radius_val} ק\"מ\n"
            f"🟢 סטטוס: {'פנוי' if current_status == 'free' else 'תפוס'}",
            reply_markup=get_main_keyboard(user_id, role_val, current_status)
        )
        return

    if text == "ℹ️ אודות ויצירת קשר":
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="ℹ️ אודות המערכת"), KeyboardButton(text="📞 יצירת קשר")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        await message.answer("ℹ️️ **אודות ויצירת קשר:**\nבחר את האפשרות הרצויה:", reply_markup=kb)
        return

    if text == "ℹ️ אודות המערכת":
        await message.answer("ℹ️ מערכת שילוח וניהול חכמה בטלגרם לניהול תחנות, סדרנים ושליחים.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    if text == "📞 יצירת קשר":
        await message.answer("📞 **יצירת קשר עם ההנהלה:**\nלפניות ותמיכה פנה למנהל המערכת.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
        return

    if text in ["🛠️ פאנל מנהל", "פאנל מנהל"] and is_admin:
        await message.answer("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())
        return

    if text == "👥 ניהול משתמשים" and is_admin:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 רשימת כל המשתמשים", callback_data="admin_list_users")],
            [InlineKeyboardButton(text="⬅️ חזרה לפאנל מנהל", callback_data="admin_back_main")]
        ])
        await message.answer("👥 **ניהול משתמשים במערכת:**\nבחר אפשרות:", reply_markup=kb)
        return

    if text == "📊 סטטיסטיקות מערכת" and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute('SELECT COUNT(*) FROM users') as cur:
                t_users = (await cur.fetchone())[0]
            async with db.execute('SELECT COUNT(*) FROM leads') as cur:
                t_leads = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM leads WHERE status='closed'") as cur:
                c_leads = (await cur.fetchone())[0]
        await message.answer(f"📊 סטטיסטיקות מערכת:\n• סך משתמשים: {t_users}\n• סך קריאות: {t_leads}\n• קריאות סגורות: {c_leads}", reply_markup=get_admin_keyboard())
        return

    if text == "📢 שידור הודעה לכולם" and is_admin:
        await state.set_state(BotStates.waiting_broadcast_all)
        await message.answer("📢 **שידור הודעה לכל משתמשים במערכת:**\nשלח כעת את טקסט ההודעה שתרצה לשדר:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️️ חזרה לתפריט הראשי")]], resize_keyboard=True))
        return

    if current_state == BotStates.waiting_broadcast_all.state and is_admin:
        await state.clear()
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id FROM users") as cur:
                all_u = await cur.fetchall()
        success_count = 0
        for (u_id,) in all_u:
            try:
                await bot.send_message(u_id, f"📢 **הודעת מערכת / שידור הנהלה:**\n\n{text}")
                success_count += 1
            except:
                pass
        await message.answer(f"✅ השידור נשלח בהצלחה ל-{success_count} משתמשים!", reply_markup=get_admin_keyboard())
        return

    if text == "🏢 ניהול תחנות וקבוצות" and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT station_id, station_name, commission_percent FROM stations") as cur:
                stations = await cur.fetchall()
        st_text = "🏢 **ניהול תחנות שילוח ועמלות:**\n\n"
        st_buttons = [
            [InlineKeyboardButton(text="➕ הוסף תחנה חדשה", callback_data="add_new_station")],
            [InlineKeyboardButton(text="⚙️ ניהול קבוצות בוט", callback_data="admin_manage_groups")]
        ]
        if not stations:
            st_text += "• אין תחנות רשומות."
        else:
            for s_id, s_name, s_comm in stations:
                st_text += f"• {s_name} | עמלה: {s_comm}%\n"
                st_buttons.append([InlineKeyboardButton(text=f"⚙️ ערוך תחנה: {s_name}", callback_data=f"edit_station_{s_id}")])
        await message.answer(st_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=st_buttons))
        return

    if text == "⚙️ ניהול קבוצות הבוט" and is_admin:
        await show_bot_groups_menu(message)
        return

    if text == "📢 פרסום הודעה":
        is_advertiser = is_admin or (role_val in ['advertiser', 'station_manager', 'dispatcher'])
        if not is_advertiser:
            await message.answer("⚠️ אין לך הרשאה לפרסם קריאות. תכונה זו פתוחה לסדרנים ומנהלים בלבד.")
            return
        await state.set_state(BotStates.waiting_lead_text)
        await message.answer("📢 פרסום קריאה חדשה:\nשלח כעת את **תוכן הקריאה** (מסלול ומחיר):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))
        return

    if current_state == BotStates.waiting_lead_text.state:
        if text == "❌ ביטול":
            await state.clear()
            await message.answer("❌ פעולת הפרסום בוטלה.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            return
        await state.update_data(lead_text=text)
        await state.set_state(BotStates.waiting_lead_phone)
        await message.answer("📞 אנא שלח את **מספר הטלפון של הלקוח** שיוצג בקריאה:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))
        return

    if current_state == BotStates.waiting_lead_phone.state:
        if text == "❌ ביטול":
            await state.clear()
            await message.answer("❌ פעולת הפרסום בוטלה.", reply_markup=get_main_keyboard(user_id, role_val, current_status))
            return
        phone_val = text
        await state.update_data(lead_phone=phone_val)
        
        data = await state.get_data()
        text_content = data.get('lead_text')
        cities, price, has_time = parse_order_text(text_content)

        # בדיקת חובה לזיהוי עיר מוצא
        if not cities:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ תקן את הודעת הקריאה", callback_data="retry_edit_lead")],
                [InlineKeyboardButton(text="🚀 המשך בכל זאת ללא מוצא", callback_data="force_publish_lead")],
                [InlineKeyboardButton(text="❌ ביטול", callback_data="dest_cancel")]
            ])
            await message.answer("⚠️ **לא נמצא מוצא** בשורות הראשונות של הקריאה!\nמוצא הוא שדה חובה. האם תרצה לתקן את ההודעה או להמשיך?", reply_markup=kb)
            return

        dest_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 למשתמשי הבוט הפרטיים בלבד", callback_data="dest_users")],
            [InlineKeyboardButton(text="🏢 לקבוצות הבוט בלבד", callback_data="dest_groups")],
            [InlineKeyboardButton(text="🚀 גם למשתמשים וגם לקבוצות", callback_data="dest_both")],
            [InlineKeyboardButton(text="❌ ביטול", callback_data="dest_cancel")]
        ])
        await message.answer("🎯 **בחר לאן לפרסם את הקריאה:**", reply_markup=dest_kb)
        return

@dp.callback_query(F.data == "retry_edit_lead")
async def cb_retry_edit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.editing_lead_content)
    await callback.message.edit_text("✍️ שלח כעת את נוסח הקריאה המתוקן:")

@dp.callback_query(F.data == "force_publish_lead")
async def cb_force_pub(callback: CallbackQuery, state: FSMContext):
    dest_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 למשתמשי הבוט הפרטיים בלבד", callback_data="dest_users")],
        [InlineKeyboardButton(text="🏢 לקבוצות הבוט בלבד", callback_data="dest_groups")],
        [InlineKeyboardButton(text="🚀 גם למשתמשים וגם לקבוצות", callback_data="dest_both")],
        [InlineKeyboardButton(text="❌ ביטול", callback_data="dest_cancel")]
    ])
    await callback.message.edit_text("🎯 **בחר לאן לפרסם את הקריאה:**", reply_markup=dest_kb)

async def show_bot_groups_menu(message_or_callback):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT group_id, group_title, is_active FROM bot_groups') as cursor:
            groups = await cursor.fetchall()
    if not groups:
        txt = "⚠️ הבוט עדיין אינו מחובר לאף קבוצה. הוסף את הבוט לקבוצות והפוך אותו למנהל."
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.edit_text(txt)
        else:
            await message_or_callback.answer(txt)
        return

    g_text = "🏢 **ניהול קבוצות מחוברות לבוט:**\nלחץ על קבוצה להפעלה או השבתה:\n\n"
    g_buttons = []
    for g_id, g_title, is_active in groups:
        status_icon = "🟢 פעילה" if is_active else "🔴 מושבתת"
        g_text += f"• {g_title} | {status_icon}\n"
        btn_txt = f"🔴 השבת: {g_title[:12]}" if is_active else f"🟢 הפעל: {g_title[:12]}"
        g_buttons.append([InlineKeyboardButton(text=btn_txt, callback_data=f"toggle_group_{g_id}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=g_buttons)
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(g_text, reply_markup=markup)
    else:
        await message_or_callback.answer(g_text, reply_markup=markup)

@dp.callback_query(F.data == "admin_manage_groups")
async def cb_admin_manage_groups(callback: CallbackQuery):
    await show_bot_groups_menu(callback)
    await callback.answer()

@dp.callback_query(F.data == "admin_back_main")
async def cb_admin_back(callback: CallbackQuery):
    await callback.message.edit_text("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "admin_list_users")
async def cb_admin_list_users(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, full_name, role, is_blocked FROM users LIMIT 20") as cur:
            users = await cur.fetchall()
    txt = "👥 **רשימת משתמשים אחרונים:**\n\n"
    buttons = []
    for uid, name, role, blocked in users:
        b_icon = "❌ חסום" if blocked else "🟢 פעיל"
        txt += f"• {name} (`{uid}`) | {role} | {b_icon}\n"
        buttons.append([InlineKeyboardButton(text=f"⚙️ ניהול: {name[:10]} ({uid})", callback_data=f"manage_user_{uid}")])
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
    name = u_data[0]
    phone = u_data[1]
    role = u_data[10]
    blocked = u_data[16]
    
    b_text = "🔓 בטל חסימה" if blocked else "❌ חסום משתמש"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡️ שנה תפקיד/הרשאה", callback_data=f"setrole_{uid}")],
        [InlineKeyboardButton(text=b_text, callback_data=f"toggle_block_{uid}")],
        [InlineKeyboardButton(text="⬅️ חזרה", callback_data="admin_list_users")]
    ])
    await callback.message.edit_text(f"👤 **ניהול משתמש:** {name}\n• ID: `{uid}`\n• טלפון: {phone}\n• תפקיד: {role}\n• חסום: {'כן' if blocked else 'לא'}", reply_markup=kb)

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
            await callback.answer("סטטוס חסימה עודכן בהצלחה!")
            await cb_manage_user(callback)

@dp.callback_query(F.data.startswith("setrole_"))
async def cb_setrole(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    uid = int(callback.data.replace("setrole_", ""))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 משתמש רגיל", callback_data=f"changerole_{uid}_user")],
        [InlineKeyboardButton(text="📢 סדרן", callback_data=f"changerole_{uid}_dispatcher")],
        [InlineKeyboardButton(text="🏢 מנהל תחנה", callback_data=f"changerole_{uid}_station_manager")],
        [InlineKeyboardButton(text="🛠️ מנהל מערכת", callback_data=f"changerole_{uid}_admin")],
        [InlineKeyboardButton(text="⬅️ חזרה", callback_data=f"manage_user_{uid}")]
    ])
    await callback.message.edit_text("🛡️ בחר הרשאה חדשה למשתמש:", reply_markup=kb)

@dp.callback_query(F.data.startswith("changerole_"))
async def cb_changerole(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    parts = callback.data.split("_")
    uid = int(parts[1])
    new_role = parts[2]
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, uid))
        await db.commit()
    await callback.answer("ההרשאה עודכנה בהצלחה!")
    await cb_manage_user(callback)

@dp.callback_query(F.data == "add_new_station")
async def cb_add_station(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(BotStates.waiting_station_name_input)
    await callback.message.edit_text("✍️ אנא שלח כעת את **השם** שתרצה לקבוע לתחנה החדשה:")

@dp.callback_query(F.data.startswith("edit_station_"))
async def cb_edit_station(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    st_id = int(callback.data.replace("edit_station_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT station_name, commission_percent FROM stations WHERE station_id = ?", (st_id,)) as cur:
            st = await cur.fetchone()
    if not st:
        await callback.answer("תחנה לא נמצאה.")
        return
    
    st_name, st_comm = st
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 עמלה 10%", callback_data=f"setcomm_{st_id}_10"), InlineKeyboardButton(text="💰 עמלה 15%", callback_data=f"setcomm_{st_id}_15"), InlineKeyboardButton(text="💰 עמלה 20%", callback_data=f"setcomm_{st_id}_20")],
        [InlineKeyboardButton(text="🗑️ מחק תחנה", callback_data=f"del_station_{st_id}")],
        [InlineKeyboardButton(text="⬅️️ חזרה", callback_data="back_to_stations")]
    ])
    await callback.message.edit_text(f"⚙️ **הגדרות תחנה: {st_name}**\nעמלה נוכחית: {st_comm}%\n\nבחר עמלה:", reply_markup=kb)

@dp.callback_query(F.data.startswith("setcomm_"))
async def cb_set_commission(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    parts = callback.data.split("_")
    st_id = int(parts[1])
    comm = float(parts[2])
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE stations SET commission_percent = ? WHERE station_id = ?", (comm, st_id))
        await db.commit()
    await callback.answer(f"העמלה עודכנה ל-{comm}% בהצלחה!")
    await cb_edit_station(callback)

@dp.callback_query(F.data.startswith("del_station_"))
async def cb_del_station(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    st_id = int(callback.data.replace("del_station_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM stations WHERE station_id = ?", (st_id,))
        await db.commit()
    await callback.answer("התחנה נמחקה!")
    await cb_back_stations(callback)

@dp.callback_query(F.data == "back_to_stations")
async def cb_back_stations(callback: CallbackQuery):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT station_id, station_name, commission_percent FROM stations") as cur:
            stations = await cur.fetchall()
    st_text = "🏢 **ניהול תחנות שילוח ועמלות:**\n\n"
    st_buttons = [
        [InlineKeyboardButton(text="➕ הוסף תחנה חדשה", callback_data="add_new_station")],
        [InlineKeyboardButton(text="⚙️ ניהול קבוצות בוט", callback_data="admin_manage_groups")]
    ]
    for s_id, s_name, s_comm in stations:
        st_text += f"• {s_name} | עמלה: {s_comm}%\n"
        st_buttons.append([InlineKeyboardButton(text=f"⚙️ ערוך תחנה: {s_name}", callback_data=f"edit_station_{s_id}")])
    await callback.message.edit_text(st_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=st_buttons))

@dp.callback_query(F.data.startswith("toggle_group_"))
async def toggle_group_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    g_id = int(callback.data.replace("toggle_group_", ""))
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT is_active, group_title FROM bot_groups WHERE group_id = ?', (g_id,)) as cursor:
            row = await cursor.fetchone()
        if row:
            new_status = 0 if row[0] == 1 else 1
            await db.execute('UPDATE bot_groups SET is_active = ? WHERE group_id = ?', (new_status, g_id))
            await db.commit()
            await callback.answer("סטטוס קבוצה עודכן בהצלחה!")
            await show_bot_groups_menu(callback)

# --- שליטה על קריאות ממצב קריאות (סגירה, פתיחה, מחיקה) ---
@dp.callback_query(F.data.startswith("lead_action_"))
async def cb_lead_action(callback: CallbackQuery):
    parts = callback.data.split("_")
    action = parts[2]
    lead_id = int(parts[3])

    async with aiosqlite.connect(DB_FILE) as db:
        if action == "close":
            await db.execute('UPDATE leads SET status = "closed" WHERE lead_id = ?', (lead_id,))
            await db.commit()
            await callback.answer(f"קריאה #{lead_id} נסגרה.")
        elif action == "open":
            await db.execute('UPDATE leads SET status = "active" WHERE lead_id = ?', (lead_id,))
            await db.commit()
            await callback.answer(f"קריאה #{lead_id} נפתחה מחדש.")
        elif action == "del":
            await db.execute('DELETE FROM leads WHERE lead_id = ?', (lead_id,))
            await db.commit()
            await callback.answer(f"קריאה #{lead_id} נמחקה מהמערכת.")
    
    await callback.message.edit_text(f"✅ פעולת {action} בוצעה בהצלחה על קריאה #{lead_id}.")

@dp.callback_query(F.data.startswith("dest_"))
async def destination_chosen(callback: CallbackQuery, state: FSMContext):
    action = callback.data.replace("dest_", "")
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ פרסום הקריאה בוטל.", reply_markup=get_main_keyboard(callback.from_user.id, 'admin', 'free'))
        return

    data = await state.get_data()
    text_content = data.get('lead_text')
    phone_content = data.get('lead_phone')
    user_id = callback.from_user.id

    pub_user_data = await get_user(user_id)
    st_id = pub_user_data[11] if pub_user_data and len(pub_user_data) > 11 else None

    cities, price, has_time = parse_order_text(text_content)

    async with aiosqlite.connect(DB_FILE) as db:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor = await db.execute('''
            INSERT INTO leads (publisher_id, message_text, phone_number, created_at, price, route_cities, station_id) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, text_content, phone_content, now_str, price if price else 0.0, " ➔ ".join(cities) if cities else "", st_id))
        lead_id = cursor.lastrowid
        await db.commit()

    await state.clear()

    if not price:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ כן, הקלד מחיר ידנית", callback_data=f"ask_price_{lead_id}")],
            [InlineKeyboardButton(text="❌ לא, פרסם בלי מחיר", callback_data=f"publish_noprice_{lead_id}")],
            [InlineKeyboardButton(text="❌ ביטול", callback_data="dest_cancel")]
        ])
        await callback.message.edit_text(f"⚠️ **לא זוהה מחיר עגול בקריאה #{lead_id}**\nהאם תרצה להקליד מחיר ידנית?", reply_markup=kb)
        return

    await callback.message.edit_text(f"✅ קריאה #{lead_id} נוצרה עם מחיר ₪{price} ונשלחת ליעדים!")
    await finish_publishing_lead(callback.message, lead_id, action)

@dp.callback_query(F.data.startswith("ask_price_"))
async def cb_ask_price(callback: CallbackQuery, state: FSMContext):
    lead_id = int(callback.data.replace("ask_price_", ""))
    await state.set_state(BotStates.waiting_manual_price)
    await state.update_data(lead_id=lead_id)
    await callback.message.edit_text("✍️ אנא שלח כעת את מספר המחיר הרצוי (למשל: 50):")

@dp.callback_query(F.data.startswith("publish_noprice_"))
async def cb_pub_noprice(callback: CallbackQuery):
    lead_id = int(callback.data.replace("publish_noprice_", ""))
    await callback.message.edit_text(f"✅ קריאה #{lead_id} מפורסמת ללא מחיר.")
    await finish_publishing_lead(callback.message, lead_id, "both")

# --- פרסום קריאה עם מד התקדמות (Progress Bar) דינמי ---
async def finish_publishing_lead(message_or_cb, lead_id: int, action="both"):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT publisher_id, message_text, phone_number, price, route_cities, station_id FROM leads WHERE lead_id = ?', (lead_id,)) as cur:
            lead = await cur.fetchone()
    if not lead:
        return
    publisher_id, text_content, phone_content, price, route_cities, st_id = lead
    cities = [c.strip() for c in route_cities.split('➔') if c.strip()]
    origin_city = cities[0] if cities else ""

    pub_user_data = await get_user(publisher_id)
    pub_fullname = pub_user_data[0] if pub_user_data else "סדרן"
    station_name = "כללי"
    if st_id:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute('SELECT station_name FROM stations WHERE station_id = ?', (st_id,)) as cur:
                st_row = await cur.fetchone()
                if st_row:
                    station_name = st_row[0]

    alert_msg = (
        f"🚀 **קריאה חדשה זמינה! (#{lead_id})**\n\n"
        f"📍 מסלול: {route_cities if route_cities else 'כללי'}\n"
        f"💰 מחיר: ₪{price if price > 0 else 'לא צוין'}\n\n"
        f"📝 **פרטים:**\n{text_content}\n\n"
        f"🏢 תחנה: {station_name} | סדרן: {pub_fullname}"
    )

    # הודעת מד התקדמות ראשונית
    progress_msg = await bot.send_message(publisher_id, "⏳ **מפרסם קריאה לקבוצות ולשליחים...**\n[░░░░░░░░░░] 0%")

    sent_users = 0
    sent_groups = 0

    target_users = []
    target_groups = []

    if action in ["users", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id, cities, radius FROM users WHERE status = 'free'") as cursor:
                free_users = await cursor.fetchall()
        for f_uid, f_cities, f_radius in free_users:
            matched = False
            if not origin_city:
                matched = True
            else:
                user_cities_list = [c.strip() for c in f_cities.split(',') if c.strip()]
                for u_c in user_cities_list:
                    if u_c in origin_city or origin_city in u_c:
                        matched = True
                        break
            if matched:
                target_users.append(f_uid)

    if action in ["groups", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT group_id FROM bot_groups WHERE is_active = 1") as cursor:
                active_groups = await cursor.fetchall()
        for (g_id,) in active_groups:
            target_groups.append(g_id)

    total_targets = len(target_users) + len(target_groups)
    current_sent = 0



    await progress_msg.edit_text("⏳ **מעדכן קבוצות ושליחים...**\n[████░░░░░░] 40%")

    for f_uid in target_users:
        try:
            link_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]])
            await bot.send_message(f_uid, alert_msg, reply_markup=link_btn)
            sent_users += 1
        except:
            pass

    await progress_msg.edit_text("⏳ **כמעט מסיים...**\n[████████░░] 80%")

    for g_id in target_groups:
        try:
            group_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 בקש קריאה", url=f"https://t.me/{(await bot.get_me()).username}?start=lead_{lead_id}")]])
            await bot.send_message(g_id, alert_msg, reply_markup=group_btn)
            sent_groups += 1
        except:
            pass

    # סיום מד התקדמות 100%
    await progress_msg.edit_text("✅ **הפרסום הושלם בהצלחה!**\n[██████████] 100%")

    pub_user_full = await get_user(publisher_id)
    pub_role = pub_user_full[10] if pub_user_full and len(pub_user_full) > 10 else 'admin'
    pub_status = pub_user_full[7] if pub_user_full and len(pub_user_full) > 7 else 'free'
    main_kb = get_main_keyboard(publisher_id, pub_role, pub_status)

    await bot.send_message(publisher_id, f"📢 הקריאה הופצה בהצלחה ל-{sent_users} שליחים פרטיים פנויים ו-{sent_groups} קבוצות ציבוריות!", reply_markup=main_kb)

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
    req_car = f"{requester_user[3]} {requester_user[4]} ({requester_user[5]}) | {requester_user[6]} מקומות" if requester_user and len(requester_user) > 6 else "לא מוגדר"
    req_username = f"@{requester.username}" if requester.username else "אין יוזר"
    req_rating = requester_user[15] if requester_user and len(requester_user) > 15 else 0.0

    alert_to_publisher = (
        f"🔔 **התקבלה בקשה לקריאה #{lead_id}**\n\n"
        f"📍 מסלול: {route_cities if route_cities else 'לא זוהה'}\n"
        f"💰 מחיר: ₪{price if price > 0 else 'לא צוין'}\n"
        f"⏱ זמן הגעה: {driver_time}\n"
        f"📝 **הודעה:** {message_text[:50]}...\n\n"
        f"👤 **כרטיסיית נהג / שליח מלאה:**\n"
        f"• שם: {req_name}\n"
        f"• יוזר: {req_username}\n"
        f"• טלפון: {req_phone}\n"
        f"• רכב: {req_car}\n"
        f"• דירוג: ⭐ {req_rating:.1f}\n\n"
        f"האם לאשר או לסגור את הפנייה?"
    )

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ אישור בלבד (פתיחת שיחה)", callback_data=f"app_only_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="✅ אישור + סגירת קריאה וחיוב עמלה", callback_data=f"app_close_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="❌ דחייה", callback_data=f"rej_lead_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="✏️ ערוך נסיעה ופרסם שוב", callback_data=f"edit_lead_{lead_id}")],
    ])

    await bot.send_message(publisher_id, alert_to_publisher, reply_markup=buttons)

@dp.callback_query(F.data.startswith("app_only_"))
async def cb_app_only(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id = int(parts[2])
    requester_id = int(parts[3])
    publisher_id = callback.from_user.id
    publisher = await bot.get_chat(publisher_id)
    pub_username = f"@{publisher.username}" if publisher.username else "סדרן"

    try:
        await bot.send_message(requester_id, f"✅ הבקשה שלך לקריאה #{lead_id} אושרה על ידי הסדרן ({pub_username})!")
    except:
        pass
    await callback.message.edit_text(f"✅ הבקשה לקריאה #{lead_id} אושרה (השיחה נפתחה מול השליח).")

@dp.callback_query(F.data.startswith("rej_lead_"))
async def cb_rej_lead(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id = int(parts[2])
    requester_id = int(parts[3])
    try:
        await bot.send_message(requester_id, f"❌ הבקשה שלך לקריאה #{lead_id} נדחתה על ידי המפרסם.")
    except:
        pass
    await callback.message.edit_text(f"❌ בקשת השליח לקריאה #{lead_id} נדחתה.")

@dp.callback_query(F.data.startswith("edit_lead_"))
async def cb_edit_lead(callback: CallbackQuery, state: FSMContext):
    lead_id = int(callback.data.replace("edit_lead_", ""))
    await state.set_state(BotStates.editing_lead_content)
    await state.update_data(editing_lead_id=lead_id)
    await callback.message.answer("✏️ שלח את הנוסח המעודכן לקריאה:")

@dp.callback_query(F.data.startswith("app_close_"))
async def app_close_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    lead_id = int(parts[2])
    requester_id = int(parts[3])
    publisher_id = callback.from_user.id

    pub_user = await get_user(publisher_id)
    pub_name = pub_user[0] if pub_user else "סדרן"
    st_id = pub_user[11] if pub_user and len(pub_user) > 11 else None
    publisher = await bot.get_chat(publisher_id)
    pub_username = f"@{publisher.username}" if publisher.username else f"מזהה: {publisher_id}"

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE leads SET status = "closed", closed_with = ? WHERE lead_id = ?', (pub_username, lead_id))
        await db.execute('UPDATE users SET total_trips = total_trips + 1 WHERE user_id = ?', (requester_id,))
        
        async with db.execute('SELECT message_text, phone_number, price, station_id FROM leads WHERE lead_id = ?', (lead_id,)) as cur:
            lead_data = await cur.fetchone()
        
        msg_text = lead_data[0] if lead_data else ""
        customer_phone = lead_data[1] if lead_data else "לא זמין"
        price_val = lead_data[2] if lead_data else 0.0
        lead_st_id = lead_data[3] if lead_data and lead_data[3] else st_id

        if price_val > 0 and lead_st_id:
            async with db.execute('SELECT commission_percent, station_name FROM stations WHERE station_id = ?', (lead_st_id,)) as s_cur:
                s_info = await s_cur.fetchone()
            if s_info:
                comm_pct = s_info[0]
                comm_amount = (price_val * comm_pct) / 100.0
                now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
                await db.execute('''
                    INSERT INTO driver_debts (user_id, station_id, amount, order_id, order_text, publisher_name, publisher_username, is_paid, date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                ''', (requester_id, lead_st_id, comm_amount, lead_id, msg_text, pub_name, pub_username, now_str))

        await db.commit()

    now_time = datetime.now().strftime('%d/%m/%Y בשעה %H:%M')

    try:
        await bot.send_message(
            requester_id,
            f"🎉 **עדכון משמח! הקריאה #{lead_id} נסגרה עליך!**\nבתאריך {now_time}.\n\n"
            f"📝 **תוכן:** {msg_text}\n📞 **טלפון הלקוח:** {customer_phone}\n👨‍💻 **סדרן:** {pub_name} ({pub_username})\n\n"
            f"💳 חויבת אוטומטית בדמי עמלת התחנה בכרטיס החיובים שלך."
        )
    except:
        pass

    rate_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{requester_id}_1"), InlineKeyboardButton(text="⭐⭐ 2", callback_data=f"rate_{requester_id}_2"), InlineKeyboardButton(text="⭐⭐⭐ 3", callback_data=f"rate_{requester_id}_3")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐ 4", callback_data=f"rate_{requester_id}_4"), InlineKeyboardButton(text="⭐⭐⭐⭐⭐ 5", callback_data=f"rate_{requester_id}_5")],
        [InlineKeyboardButton(text="⏭️ דלג על דירוג", callback_data=f"rate_{requester_id}_skip")]
    ])

    await callback.message.edit_text(f"✅ **הפנייה אושרה, קריאה #{lead_id} נסגרה על השליח!**\nהשליח חויב בעמלה. בחר דירוג כוכבים לשליח:", reply_markup=rate_kb)

@dp.callback_query(F.data.startswith("rate_"))
async def rate_driver_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    target_driver_id = int(parts[1])
    val_str = parts[2]

    if val_str != "skip":
        stars = int(val_str)
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT rating, rating_count FROM users WHERE user_id = ?", (target_driver_id,)) as cur:
                r_data = await cur.fetchone()
            if r_data:
                curr_rating, curr_count = r_data[0], r_data[1]
                new_count = curr_count + 1
                new_rating = ((curr_rating * curr_count) + stars) / new_count
                await db.execute("UPDATE users SET rating = ?, rating_count = ? WHERE user_id = ?", (new_rating, new_count, target_driver_id))
                await db.commit()
        await callback.message.edit_text(f"⭐ הדירוג ({stars} כוכבים) נקלט ונשמר בהצלחה!")
    else:
        await callback.message.edit_text("⏭️ דולג על דירוג השליח.")

async def main():
    await init_db()
    await start_web_server()
    print("✨ בוט השילוח והניהול פועל בהצלחה עם שרת Web פנימי!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
