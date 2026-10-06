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
    waiting_birth = State()

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
                birth_date TEXT,
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
        async with db.execute('SELECT full_name, phone, birth_date, status, expiry_date, role, station_id, radius, cities, total_trips, rating, rating_count, is_blocked FROM users WHERE user_id = ?', (user_id,)) as cursor:
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
    user = await get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)
    role_val = user[5] if user else ('admin' if is_admin else 'user')
    current_status = user[3] if user else 'busy'
    is_blocked = user[12] if user and len(user) > 12 else 0

    if is_blocked:
        await message.answer("❌ חשבונך חסום במערכת.")
        return

    if is_admin and not user:
        async with aiosqlite.connect(DB_FILE) as db:
            expiry = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, status, expiry_date, role, is_blocked) VALUES (?, ?, ?, ?, "busy", ?, "admin", 0)', 
                             (user_id, "מנהל מערכת", "0000000000", "2000-01-01", expiry))
            await db.commit()
        user = await get_user(user_id)
        role_val = 'admin'

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
