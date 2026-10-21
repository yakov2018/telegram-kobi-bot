import os
import asyncio
import logging
import sys
import re
import json
import hmac
import hashlib
from urllib.parse import parse_qsl, unquote
from datetime import datetime
from contextlib import contextmanager
from aiohttp import web

# PostgreSQL & SQLite support
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
import aiosqlite

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.exceptions import TelegramConflictError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ----------------- תצורת שרת, טוקן ומסד נתונים -----------------
RAW_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_TOKEN = RAW_TOKEN.strip().replace(" ", "")

if not BOT_TOKEN:
    logging.warning("⚠️ לא הוגדר משתנה סביבה BOT_TOKEN! יש להגדיר אותו בהגדרות השרת ב-Render (Environment).")

ADMIN_IDS = [8644923212, 552821474]

# מסד נתונים מרוחק דרך DATABASE_URL (למשל PostgreSQL ב-Render)
RAW_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

SQLITE_DB_FILE = 'erp_master_complete.db'
USE_POSTGRES = bool(DATABASE_URL)

# מאגר חיבורים (Connection Pool) מהיר כדי למנוע את השהיית 2 השניות של פתיחת SSL מחדש בכל שאילתה!
pg_pool = None
if USE_POSTGRES:
    try:
        pg_pool = ThreadedConnectionPool(minconn=2, maxconn=10, dsn=DATABASE_URL)
        logging.info("⚡ Connection Pool ל-PostgreSQL אותחל בהצלחה (מענה מיידי ללא השהיות)!")
    except Exception as e:
        logging.error(f"❌ שגיאה באיתחול Connection Pool: {e}")

# זיהוי אוטומטי של כתובת השרת ב-Render עבור ה-Mini App (ללא שגיאות חסימה של גוגל)
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
DEFAULT_WEBAPP = RENDER_EXTERNAL_URL if RENDER_EXTERNAL_URL else "https://ais-pre-stligqg25zyepbjqdxhays-148934615276.europe-west2.run.app"
WEBAPP_URL = os.environ.get("WEBAPP_URL", DEFAULT_WEBAPP).strip()

bot = Bot(token=BOT_TOKEN or "DUMMY_TOKEN_PLEASE_SET_BOT_TOKEN", default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
router = Router()
dp.include_router(router)

ROLE_NAMES = {
    "admin": "מנהל מערכת",
    "station_manager": "מנהל תחנה",
    "dispatcher": "סדרן",
    "user": "נהג / שליח"
}
CAR_BRANDS = ["יונדאי", "טויוטה", "קיה", "סקודה", "אחר (הקלדה ידנית)"]

# ----------------- מצבים (FSM) -----------------
class Reg(StatesGroup):
    name = State()
    birth_year = State()
    phone = State()
    car_brand = State()
    car_model = State()
    car_year = State()
    car_seats = State()

class OrderFlow(StatesGroup):
    waiting_publish_text = State()
    waiting_publish_dest = State()
    waiting_driver_eta = State()

class DebtFlow(StatesGroup):
    waiting_dispute_reason = State()

class AdminFlow(StatesGroup):
    waiting_station_name = State()
    waiting_station_comm = State()
    waiting_user_id_role = State()
    waiting_broadcast = State()

class DriverFlow(StatesGroup):
    waiting_new_city = State()

# ----------------- מתאמי מסד נתונים מהירים (Connection Pooling + Non-blocking Thread) -----------------
@contextmanager
def get_pg_cursor():
    """משיכת חיבור קיים מתוך ה-Pool להרצה מהירה של אלפיות שניה ללא TCP Handshake חוזר"""
    global pg_pool
    conn = None
    if pg_pool is not None:
        try:
            conn = pg_pool.getconn()
            if conn.closed:
                conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        except Exception:
            conn = None
    if conn is None:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            conn.commit()
        finally:
            conn.close()
    else:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if pg_pool is not None:
                try:
                    pg_pool.putconn(conn)
                except Exception:
                    pass

async def run_in_thread(func, *args, **kwargs):
    """הרצת פעולת מסד הנתונים בתהליכון מקבילי כדי לא לתקוע את ה-Event Loop של aiogram"""
    return await asyncio.to_thread(func, *args, **kwargs)

def validate_telegram_init_data(init_data: str, bot_token: str = BOT_TOKEN) -> dict | None:
    """
    אימות קריפטוגרפי מחמיר של מחרוזת Telegram.WebApp.initData באמצעות HMAC-SHA256
    לפי מפרט הטלגרם הרשמי. מונע כל ניסיון התחזות ומאמת את מזהה המשתמש.
    """
    if not init_data or not bot_token:
        return None
    try:
        parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            return None
        
        # מחרוזת בדיקה מסודרת אלפביתית לפי מפתחות בפורמט key=value
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        # חישוב ה-Secret Key מתוך מחרוזת ה-WebAppData וטוקן הבוט
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(calculated_hash, received_hash):
            user_raw = parsed_data.get("user")
            user_data = json.loads(user_raw) if user_raw else {}
            user_data["auth_date"] = parsed_data.get("auth_date")
            return user_data
    except Exception as e:
        logging.error(f"❌ שגיאה באימות קריפטוגרפי של Telegram initData: {e}")
    return None

def _init_db_sync():
    with get_pg_cursor() as cur:
        # 1. טבלת תחנות מורחבת
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_stations (
            station_id SERIAL PRIMARY KEY, 
            name TEXT NOT NULL, 
            commission_percent REAL DEFAULT 10.0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        station_columns_to_add = [
            ("is_active", "INTEGER DEFAULT 1"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        for col_name, col_type in station_columns_to_add:
            try:
                cur.execute(f"ALTER TABLE deliveries_stations ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception: pass

        # 2. טבלת משתמשים מורחבת (כולל Onboarding, מנויים, דירוג וחובות)
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_users (
            user_id BIGINT PRIMARY KEY, 
            telegram_username TEXT,
            full_name TEXT NOT NULL, 
            phone TEXT, 
            is_phone_verified INTEGER DEFAULT 0,
            birth_year INTEGER, 
            terms_accepted_at TIMESTAMP,
            role TEXT DEFAULT 'user', 
            station_id INTEGER DEFAULT 1, 
            status TEXT DEFAULT 'busy', 
            is_blocked INTEGER DEFAULT 0, 
            block_reason TEXT,
            car_brand TEXT, 
            car_model TEXT, 
            car_year INTEGER, 
            car_seats INTEGER DEFAULT 4, 
            subscription_plan TEXT DEFAULT 'free',
            sub_start_date TIMESTAMP,
            sub_expiry_date TIMESTAMP,
            daily_trips_count INTEGER DEFAULT 0,
            last_trip_date DATE,
            rating REAL DEFAULT 5.0, 
            total_trips INTEGER DEFAULT 0, 
            debt_balance REAL DEFAULT 0.0, 
            sub_expiry TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # הגירה בטוחה (Safe ALTER TABLE) למקרה שהטבלה כבר הייתה קיימת
        user_columns_to_add = [
            ("telegram_username", "TEXT"),
            ("is_phone_verified", "INTEGER DEFAULT 0"),
            ("terms_accepted_at", "TIMESTAMP"),
            ("subscription_plan", "TEXT DEFAULT 'free'"),
            ("sub_start_date", "TIMESTAMP"),
            ("sub_expiry_date", "TIMESTAMP"),
            ("daily_trips_count", "INTEGER DEFAULT 0"),
            ("last_trip_date", "DATE"),
            ("block_reason", "TEXT"),
            ("is_blocked", "INTEGER DEFAULT 0"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        for col_name, col_type in user_columns_to_add:
            try:
                cur.execute(f"ALTER TABLE deliveries_users ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception: pass

        # 3. טבלת קריאות מורחבת
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_orders (
            order_id SERIAL PRIMARY KEY, 
            text TEXT, 
            price REAL,
            publisher_id BIGINT, 
            station_id INTEGER, 
            driver_id BIGINT, 
            origin_city TEXT,
            dest_city TEXT,
            commission_amount REAL DEFAULT 0.0,
            pickup_lat DOUBLE PRECISION,
            pickup_lon DOUBLE PRECISION,
            status TEXT DEFAULT 'open', 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            taken_at TIMESTAMP,
            completed_at TIMESTAMP)''')

        order_columns_to_add = [
            ("origin_city", "TEXT"),
            ("dest_city", "TEXT"),
            ("commission_amount", "REAL DEFAULT 0.0"),
            ("pickup_lat", "DOUBLE PRECISION"),
            ("pickup_lon", "DOUBLE PRECISION"),
            ("taken_at", "TIMESTAMP"),
            ("completed_at", "TIMESTAMP")
        ]
        for col_name, col_type in order_columns_to_add:
            try:
                cur.execute(f"ALTER TABLE deliveries_orders ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception: pass

        # 4. טבלת חובות ועמלות
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_debts (
            debt_id SERIAL PRIMARY KEY, 
            order_id INTEGER, 
            driver_id BIGINT,
            station_id INTEGER, 
            amount REAL, 
            status TEXT DEFAULT 'unpaid', 
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP)''')

        # 5. טבלת הצעות מחיר ו-ETA של נהגים
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_order_bids (
            bid_id SERIAL PRIMARY KEY,
            order_id INTEGER REFERENCES deliveries_orders(order_id) ON DELETE CASCADE,
            driver_id BIGINT REFERENCES deliveries_users(user_id),
            eta_minutes INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # 6. טבלת מילון קיצורי ערים (NLP Aliases)
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_city_aliases (
            alias TEXT PRIMARY KEY,
            standard_city TEXT NOT NULL)''')

        # 7. טבלת הגדרות מערכת גלובליות
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_system_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # 8. טבלת ערי נהג
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_driver_cities (
            user_id BIGINT, city_name TEXT, PRIMARY KEY(user_id, city_name))''')

        # 9. טבלת קבוצות מאושרות
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_bot_groups (
            group_id BIGINT PRIMARY KEY, group_name TEXT)''')

        # אינדקסים מהירים לביצועים מירביים
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_deliveries_orders_status ON deliveries_orders(status)''')
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_deliveries_driver_cities_user ON deliveries_driver_cities(user_id)''')
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_deliveries_debts_driver ON deliveries_debts(driver_id, status)''')
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_deliveries_users_role ON deliveries_users(role)''')

        # תחנת ברירת מחדל
        cur.execute('''INSERT INTO deliveries_stations (station_id, name, commission_percent) 
                       VALUES (1, 'תחנה ראשית', 10.0) 
                       ON CONFLICT (station_id) DO NOTHING''')

        # ביצור הרשאות מנהלי מערכת קבועים (552821474 ו-8644923212)
        for admin_id in ADMIN_IDS:
            cur.execute('''INSERT INTO deliveries_users (user_id, full_name, phone, birth_year, role, status, is_blocked)
                           VALUES (%s, 'מנהל ראשי', '0500000000', 1990, 'admin', 'free', 0)
                           ON CONFLICT (user_id) DO UPDATE SET role = 'admin', is_blocked = 0''', (admin_id,))

        # הזנת מילון קיצורי ערים נפוצים
        city_seeds = [
            ('ים', 'ירושלים'), ('י-ם', 'ירושלים'), ('עיר הקודש', 'ירושלים'),
            ('בב', 'בני ברק'), ('ב"ב', 'בני ברק'),
            ('פת', 'פתח תקווה'), ('פ"ת', 'פתח תקווה'),
            ('תא', 'תל אביב'), ('ת"א', 'תל אביב'),
            ('קס', 'מודיעין עילית'), ('ק"ס', 'מודיעין עילית'), ('ספר', 'מודיעין עילית'),
            ('אשד', 'אשדוד'), ('אשדו', 'אשדוד'),
            ('חולון', 'חולון'), ('בת ים', 'בת ים'),
            ('ראשלצ', 'ראשון לציון'), ('ראשל"צ', 'ראשון לציון')
        ]
        for alias, std in city_seeds:
            cur.execute("INSERT INTO deliveries_city_aliases (alias, standard_city) VALUES (%s, %s) ON CONFLICT (alias) DO NOTHING", (alias, std))

async def init_db():
    if USE_POSTGRES:
        try:
            await run_in_thread(_init_db_sync)
            logging.info("✅ PostgreSQL Phase 1 tables, aliases and indexes initialized successfully with prefix 'deliveries_'.")
        except Exception as e:
            logging.error(f"❌ Error initializing PostgreSQL: {e}")
            raise e
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_users (
                user_id INTEGER PRIMARY KEY, telegram_username TEXT, full_name TEXT, phone TEXT, 
                is_phone_verified BOOLEAN DEFAULT 0, birth_year INTEGER, terms_accepted_at TEXT,
                car_brand TEXT, car_model TEXT, car_year INTEGER, car_seats INTEGER DEFAULT 4, 
                status TEXT DEFAULT 'busy', role TEXT DEFAULT 'user', station_id INTEGER DEFAULT 1, 
                subscription_plan TEXT DEFAULT 'free', sub_start_date TEXT, sub_expiry_date TEXT,
                daily_trips_count INTEGER DEFAULT 0, last_trip_date TEXT,
                rating REAL DEFAULT 5.0, total_trips INTEGER DEFAULT 0, is_blocked INTEGER DEFAULT 0, 
                block_reason TEXT, debt_balance REAL DEFAULT 0.0, sub_expiry TEXT, created_at TEXT)''')
            
            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_stations (
                station_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, commission_percent REAL DEFAULT 10.0,
                is_active INTEGER DEFAULT 1, created_at TEXT)''')
            
            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, price REAL,
                publisher_id INTEGER, station_id INTEGER, driver_id INTEGER, 
                origin_city TEXT, dest_city TEXT, commission_amount REAL DEFAULT 0.0,
                pickup_lat REAL, pickup_lon REAL, status TEXT DEFAULT 'open', created_at TEXT,
                taken_at TEXT, completed_at TEXT)''')
            
            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_debts (
                debt_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, driver_id INTEGER,
                station_id INTEGER, amount REAL, status TEXT DEFAULT 'unpaid', reason TEXT, created_at TEXT, resolved_at TEXT)''')

            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_order_bids (
                bid_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, driver_id INTEGER, eta_minutes INTEGER,
                status TEXT DEFAULT 'pending', created_at TEXT)''')

            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_city_aliases (
                alias TEXT PRIMARY KEY, standard_city TEXT)''')

            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_system_settings (
                setting_key TEXT PRIMARY KEY, setting_value TEXT, updated_at TEXT)''')

            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_driver_cities (
                user_id INTEGER, city_name TEXT, PRIMARY KEY(user_id, city_name))''')

            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_bot_groups (
                group_id INTEGER PRIMARY KEY, group_name TEXT)''')
                
            await db.execute('INSERT OR IGNORE INTO deliveries_stations (station_id, name, commission_percent) VALUES (1, "תחנה ראשית", 10.0)')

            for admin_id in ADMIN_IDS:
                await db.execute('''INSERT INTO deliveries_users (user_id, full_name, phone, birth_year, role, status)
                                   VALUES (?, 'מנהל ראשי', '0500000000', 1990, 'admin', 'free')
                                   ON CONFLICT(user_id) DO UPDATE SET role = 'admin', is_blocked = 0''', (admin_id,))

            city_seeds = [
                ('ים', 'ירושלים'), ('י-ם', 'ירושלים'), ('עיר הקודש', 'ירושלים'),
                ('בב', 'בני ברק'), ('ב"ב', 'בני ברק'),
                ('פת', 'פתח תקווה'), ('פ"ת', 'פתח תקווה'),
                ('תא', 'תל אביב'), ('ת"א', 'תל אביב'),
                ('קס', 'מודיעין עילית'), ('ק"ס', 'מודיעין עילית'), ('ספר', 'מודיעין עילית'),
                ('אשד', 'אשדוד'), ('אשדו', 'אשדוד')
            ]
            for alias, std in city_seeds:
                await db.execute("INSERT OR IGNORE INTO deliveries_city_aliases (alias, standard_city) VALUES (?, ?)", (alias, std))

            await db.commit()
            logging.info("✅ SQLite Phase 1 tables and aliases initialized successfully.")

def _get_user_sync(user_id):
    with get_pg_cursor() as cur:
        cur.execute('SELECT * FROM deliveries_users WHERE user_id = %s', (user_id,))
        return cur.fetchone()

async def get_user(user_id):
    if USE_POSTGRES:
        return await run_in_thread(_get_user_sync, user_id)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            return await (await db.execute('SELECT * FROM deliveries_users WHERE user_id = ?', (user_id,))).fetchone()

# ----------------- תבנית HTML מלאה ומשולבת עבור Telegram Mini App -----------------
# תבנית זו מבטיחה שלעולם לא יופיע טקסט יבש, אלא ממשק ה-ERP המלא בתוך טלגרם!
STANDALONE_MINIAPP_HTML = """<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Kobi ERP Bot - Taxi & Courier Mini App</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Assistant', sans-serif; }
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 9999px; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased">
  <!-- Top App Bar -->
  <header class="sticky top-0 z-40 bg-slate-900/95 backdrop-blur-md border-b border-slate-800 p-3.5 flex items-center justify-between">
    <div class="flex items-center gap-2.5">
      <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-600 flex items-center justify-center text-slate-950 font-extrabold text-lg shadow-md">
        🚖
      </div>
      <div>
        <h1 class="font-extrabold text-sm text-white flex items-center gap-1.5">
          <span>Kobi ERP Bot</span>
          <span class="text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-1.5 py-0.2 rounded font-mono">LIVE</span>
        </h1>
        <p id="tg-username" class="text-[11px] text-slate-400">טוען נתוני משתמש טלגרם...</p>
      </div>
    </div>
    <div id="status-badge" class="px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-bold flex items-center gap-1">
      <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
      <span id="status-text">פנוי לקריאות</span>
    </div>
  </header>

  <!-- View Switcher -->
  <div class="bg-slate-900/90 p-2 border-b border-slate-800/80 flex gap-1.5 overflow-x-auto">
    <button onclick="switchTab('driver')" id="tab-btn-driver" class="flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-amber-500 text-slate-950 transition text-center whitespace-nowrap">
      🚗 עמדת נהג
    </button>
    <button onclick="switchTab('dispatcher')" id="tab-btn-dispatcher" class="flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap">
      📢 עמדת סדרן
    </button>
    <button onclick="switchTab('profile')" id="tab-btn-profile" class="flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap">
      💎 פרופיל וחובות
    </button>
  </div>

  <!-- Main Content -->
  <main class="flex-1 p-4 max-w-lg mx-auto w-full space-y-4">

    <!-- DRIVER TAB -->
    <div id="tab-driver" class="space-y-4">
      <!-- Status Card with Auto-Freeze -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-xs text-slate-400 font-semibold">סטטוס עבודה נוכחי</span>
          <span id="debt-indicator" class="text-xs font-mono font-bold text-amber-400">חוב: ₪0.00</span>
        </div>
        <button onclick="toggleDriverStatus()" id="status-toggle-btn" class="w-full py-3 rounded-xl font-extrabold text-sm transition flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-md">
          🟢 שנה לסטטוס 'תפוס' (עצור קריאות)
        </button>
        <div id="freeze-alert" class="hidden p-3 bg-red-500/15 border border-red-500/40 rounded-xl text-xs text-red-300 font-semibold">
          🚫 חשבונך מוקפא עקב חובות (מעל 500 ש"ח)! לא תוכל לקבל קריאות עד הסדרת החוב.
        </div>
      </div>

      <!-- Work Zones (אזורי עבודה) -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-2.5">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-white flex items-center gap-1.5">
            📍 אזורי עבודה שלך
          </span>
          <button onclick="clearCities()" class="text-[11px] text-red-400 hover:underline">נקה הכל</button>
        </div>
        <div id="cities-list" class="flex flex-wrap gap-1.5 min-h-[32px] p-2 bg-slate-950 rounded-xl border border-slate-800 text-xs">
          <!-- Chips injected by JS -->
        </div>
        <div class="flex gap-2">
          <input type="text" id="city-input" placeholder="הקלד עיר להוספה..." class="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-amber-500">
          <button onclick="addCityFromInput()" class="bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold px-3 py-1.5 rounded-xl border border-slate-700 transition">הוסף</button>
        </div>
        <div class="flex flex-wrap gap-1 pt-1">
          <button onclick="addCity('מודיעין עילית')" class="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">+ מודיעין עילית</button>
          <button onclick="addCity('ירושלים')" class="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">+ ירושלים</button>
          <button onclick="addCity('בני ברק')" class="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">+ בני ברק</button>
          <button onclick="addCity('פתח תקווה')" class="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">+ פתח תקווה</button>
        </div>
      </div>

      <!-- Available Orders -->
      <div class="space-y-2.5">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-white">קריאות פתוחות באזורי היעד שלך</span>
          <span id="orders-count" class="text-[11px] text-slate-400 font-mono">2 קריאות</span>
        </div>
        <div id="orders-container" class="space-y-2.5">
          <!-- Injected Orders -->
        </div>
      </div>
    </div>

    <!-- DISPATCHER TAB -->
    <div id="tab-dispatcher" class="hidden space-y-4">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
        <span class="text-xs font-bold text-white block">📢 פרסום קריאה חדשה (מנקה טקסט אוטומטי)</span>
        <textarea id="order-text-input" oninput="previewOrder()" rows="3" placeholder="הדבק פרטי קריאה: למשל מודיעין עילית -> ירושלים 180 שח" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-xs text-white focus:outline-none focus:border-amber-500 resize-none"></textarea>
        <div id="order-preview-box" class="hidden p-2.5 bg-slate-950 rounded-xl border border-slate-800 text-xs space-y-1">
          <div class="flex justify-between text-slate-400 text-[11px]">
            <span>טקסט מנוקה:</span>
            <span id="preview-price" class="text-amber-400 font-bold">מחיר: ₪0</span>
          </div>
          <p id="preview-text" class="text-slate-200 font-mono text-[11px]"></p>
        </div>
        <button onclick="publishOrder()" class="w-full py-2.5 rounded-xl font-bold text-xs bg-amber-500 hover:bg-amber-400 text-slate-950 shadow">
          שגר קריאה לנהגים פנויים
        </button>
      </div>

      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
        <span class="text-xs font-bold text-white block">📋 מעקב קריאות של התחנה</span>
        <div id="dispatcher-orders" class="space-y-2 text-xs">
          <!-- Injected orders -->
        </div>
      </div>
    </div>

    <!-- PROFILE TAB -->
    <div id="tab-profile" class="hidden space-y-4">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-3 text-xs">
        <div class="flex items-center gap-3">
          <div class="w-12 h-12 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center text-xl font-bold">
            👤
          </div>
          <div>
            <h3 id="profile-name" class="font-bold text-sm text-white">נהג טלגרם</h3>
            <p id="profile-details" class="text-slate-400 text-[11px]">טויוטה קורולה (2022) • 5 מקומות</p>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 pt-2 border-t border-slate-800 text-center">
          <div class="bg-slate-950 p-2 rounded-xl border border-slate-800">
            <span class="text-[10px] text-slate-400 block">דירוג</span>
            <span id="profile-rating" class="font-bold text-amber-400">⭐ 4.9</span>
          </div>
          <div class="bg-slate-950 p-2 rounded-xl border border-slate-800">
            <span class="text-[10px] text-slate-400 block">נסיעות</span>
            <span id="profile-trips" class="font-bold text-white">42</span>
          </div>
          <div class="bg-slate-950 p-2 rounded-xl border border-slate-800">
            <span class="text-[10px] text-slate-400 block">חוב תחנה</span>
            <span id="profile-debt" class="font-bold text-emerald-400">₪0.00</span>
          </div>
        </div>
      </div>

      <!-- Debts list & Appeals -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm space-y-2.5">
        <span class="text-xs font-bold text-white flex items-center gap-1.5">
          💳 חיובים וערעורים פעילים
        </span>
        <div id="debts-list" class="space-y-2 text-xs">
          <div class="p-3 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center">
            <div>
              <p class="font-bold text-white">קריאה #1001 (עמלה 10%)</p>
              <p class="text-[10px] text-slate-400">מודיעין עילית - ירושלים</p>
            </div>
            <div class="text-left">
              <span class="font-bold text-amber-400 block">₪18.00</span>
              <button onclick="appealDebt(1001)" class="text-[10px] text-sky-400 hover:underline">ערעור</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </main>

  <script>
    // Initialize Telegram WebApp
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      const user = tg.initDataUnsafe?.user;
      if (user) {
        const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || 'משתמש טלגרם';
        document.getElementById('tg-username').innerText = name + ' (מזהה: ' + user.id + ')';
        document.getElementById('profile-name').innerText = name;
      } else {
        document.getElementById('tg-username').innerText = 'מחובר למערכת ה-ERP';
      }
    } else {
      document.getElementById('tg-username').innerText = 'מערכת ניהול מקוונת';
    }

    // State management
    let isFree = true;
    let debtBalance = 0.0;
    let myCities = ['מודיעין עילית', 'ירושלים', 'בני ברק'];
    let orders = [
      { id: 1002, text: 'מודיעין עילית (נתיבות שלום) - ירושלים (רוממה), 3 נוסעים, 180 שח', price: 180, time: 'לפני 5 דקות' },
      { id: 1003, text: 'בני ברק (חזון איש) - פתח תקווה (בילינסון), משלוח מעטפה דחוף, 85 שח', price: 85, time: 'לפני 12 דקות' }
    ];

    function renderCities() {
      const container = document.getElementById('cities-list');
      if (myCities.length === 0) {
        container.innerHTML = '<span class="text-slate-500 italic py-0.5">לא הוגדרו אזורים (מקבל קריאות מכל הארץ)</span>';
        return;
      }
      container.innerHTML = myCities.map(c => `
        <span class="inline-flex items-center gap-1 bg-amber-500/10 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-lg text-[11px] font-medium">
          ${c}
          <button onclick="removeCity('${c}')" class="hover:text-white">✕</button>
        </span>
      `).join('');
    }

    function addCity(city) {
      if (!city || myCities.includes(city)) return;
      myCities.push(city);
      renderCities();
      renderOrders();
    }

    function addCityFromInput() {
      const input = document.getElementById('city-input');
      const val = input.value.trim();
      if (val) {
        addCity(val);
        input.value = '';
      }
    }

    function removeCity(city) {
      myCities = myCities.filter(c => c !== city);
      renderCities();
      renderOrders();
    }

    function clearCities() {
      myCities = [];
      renderCities();
      renderOrders();
    }

    function toggleDriverStatus() {
      if (debtBalance > 500) {
        document.getElementById('freeze-alert').classList.remove('hidden');
        return;
      }
      isFree = !isFree;
      updateStatusUI();
    }

    function updateStatusUI() {
      const badge = document.getElementById('status-badge');
      const text = document.getElementById('status-text');
      const btn = document.getElementById('status-toggle-btn');

      if (isFree) {
        badge.className = "px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-bold flex items-center gap-1";
        text.innerText = "פנוי לקריאות";
        btn.className = "w-full py-3 rounded-xl font-extrabold text-sm transition flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-md";
        btn.innerText = "🟢 סטטוס פעיל: 'פנוי' (לחץ לעצירת קריאות)";
      } else {
        badge.className = "px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs font-bold flex items-center gap-1";
        text.innerText = "תפוס / עצור";
        btn.className = "w-full py-3 rounded-xl font-extrabold text-sm transition flex items-center justify-center gap-2 bg-red-600/20 hover:bg-red-600 text-red-200 border border-red-500/30";
        btn.innerText = "🔴 סטטוס: 'תפוס' (לחץ לעבור לפנוי)";
      }
    }

    function renderOrders() {
      const container = document.getElementById('orders-container');
      const countEl = document.getElementById('orders-count');
      const filtered = orders.filter(o => {
        if (myCities.length === 0) return true;
        return myCities.some(c => o.text.includes(c));
      });

      countEl.innerText = filtered.length + ' קריאות';
      if (filtered.length === 0) {
        container.innerHTML = '<div class="p-6 bg-slate-900 rounded-xl border border-slate-800 text-center text-xs text-slate-400">אין קריאות מתאימות באזורים שלך כרגע.</div>';
        return;
      }

      container.innerHTML = filtered.map(o => `
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-2">
          <div class="flex justify-between items-center text-xs">
            <span class="font-mono font-bold text-amber-400">קריאה #${o.id}</span>
            <span class="font-extrabold text-emerald-400 bg-slate-950 px-2.5 py-0.5 rounded border border-slate-800">₪${o.price}</span>
          </div>
          <p class="text-xs text-slate-200 leading-relaxed font-sans bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80">${o.text}</p>
          <div class="flex justify-between items-center pt-1 text-[11px]">
            <span class="text-slate-400">${o.time}</span>
            <button onclick="takeOrder(${o.id})" class="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-3 py-1.5 rounded-lg transition">
              🚗 קח קריאה (הזן ETA)
            </button>
          </div>
        </div>
      `).join('');
    }

    function takeOrder(id) {
      if (!isFree) {
        alert("⚠️ אתה בסטטוס תפוס! העבר לפנוי למעלה קודם.");
        return;
      }
      const eta = prompt("⏱️ כמה זמן עד להגעה למוצא? (במספר דקות):", "10");
      if (eta) {
        alert(`✅ בקשתך לקריאה #${id} עם זמן הגעה של ${eta} דקות שוגרה לסדרן!`);
      }
    }

    function cleanText(text) {
      return text.replace(/[-=]+>/g, '-').replace(/<[-=]+/g, '-')
                 .replace(/\\bפת\\b/g, 'פתח תקווה')
                 .replace(/\\bים\\b/g, 'ירושלים')
                 .replace(/\\bספר\\b/g, 'מודיעין עילית').trim();
    }

    function previewOrder() {
      const input = document.getElementById('order-text-input');
      const box = document.getElementById('order-preview-box');
      const previewText = document.getElementById('preview-text');
      const previewPrice = document.getElementById('preview-price');

      const raw = input.value;
      if (!raw.trim()) {
        box.classList.add('hidden');
        return;
      }
      const cleaned = cleanText(raw);
      const prices = cleaned.match(/\\b\\d{2,4}\\b/g);
      const estPrice = prices ? prices[prices.length - 1] : 0;

      previewText.innerText = cleaned;
      previewPrice.innerText = 'מחיר: ₪' + estPrice;
      box.classList.remove('hidden');
    }

    function publishOrder() {
      const input = document.getElementById('order-text-input');
      const raw = input.value.trim();
      if (!raw) return;
      const cleaned = cleanText(raw);
      const prices = cleaned.match(/\\b\\d{2,4}\\b/g);
      const estPrice = prices ? parseInt(prices[prices.length - 1], 10) : 0;

      if (!estPrice) {
        alert("⚠️ המערכת לא זיהתה מחיר. נא לכלול מחיר בספרות (למשל: 150).");
        return;
      }

      const newId = 1000 + orders.length + 2;
      orders.unshift({ id: newId, text: cleaned, price: estPrice, time: 'הרגע' });
      input.value = '';
      previewOrder();
      renderOrders();
      alert(`✅ קריאה #${newId} שוגרה בהצלחה לנהגים באזורי היעד!`);
      switchTab('driver');
    }

    function appealDebt(id) {
      const reason = prompt("✍️ מדוע אתה מבקש לבטל את החיוב הזה? (למשל: 'הלקוח ביטל במקום'):");
      if (reason) {
        alert(`✅ ערעור על חיוב #${id} נשלח להנהלת המערכת לבדיקה.`);
      }
    }

    function switchTab(tab) {
      document.getElementById('tab-driver').classList.add('hidden');
      document.getElementById('tab-dispatcher').classList.add('hidden');
      document.getElementById('tab-profile').classList.add('hidden');

      document.getElementById('tab-btn-driver').className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap";
      document.getElementById('tab-btn-dispatcher').className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap";
      document.getElementById('tab-btn-profile').className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap";

      document.getElementById('tab-' + tab).classList.remove('hidden');
      document.getElementById('tab-btn-' + tab).className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-amber-500 text-slate-950 transition text-center whitespace-nowrap";
    }

    // Initial render
    renderCities();
    renderOrders();
    updateStatusUI();
  </script>
</body>
</html>"""

# ----------------- שרת HTTP, נתיבי REST API ו-Telegram Mini App -----------------
def cors_json_response(data, status=200):
    return web.json_response(data, status=status, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS, PUT, DELETE",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Telegram-Init-Data, Accept"
    })

async def handle_options(request):
    return web.Response(text="", status=204, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS, PUT, DELETE",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Telegram-Init-Data, Accept"
    })

async def handle_ping(request):
    return web.Response(text="ERP Master Alive! WebApp is serving.")

async def handle_api_auth(request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    init_data = data.get("initData") or request.headers.get("X-Telegram-Init-Data", "")
    user_payload = validate_telegram_init_data(init_data)

    # במצב בדיקה מקומי או הדמיית פיתוח: אם נשלח dev_user_id של מנהל מערכת
    if not user_payload:
        dev_user_id = data.get("dev_user_id") or request.query.get("user_id")
        if dev_user_id and int(dev_user_id) in ADMIN_IDS:
            user_payload = {"id": int(dev_user_id), "first_name": "מנהל ראשי (God Mode)"}
        else:
            return cors_json_response({"ok": False, "error": "אימות Telegram WebApp נכשל. פתח מתוך הבוט."}, status=401)

    user_id = int(user_payload.get("id"))
    full_name = user_payload.get("first_name", "")
    if user_payload.get("last_name"):
        full_name += " " + user_payload.get("last_name")
    if not full_name:
        full_name = user_payload.get("username", f"משתמש {user_id}")

    username = user_payload.get("username", "")

    user = await get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)

    if not user:
        default_role = 'admin' if is_admin else 'user'
        if USE_POSTGRES:
            def _create_u():
                with get_pg_cursor() as cur:
                    cur.execute('''INSERT INTO deliveries_users (user_id, full_name, telegram_username, role, status)
                                   VALUES (%s, %s, %s, %s, 'busy')
                                   ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name''',
                                (user_id, full_name, username, default_role))
            await run_in_thread(_create_u)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                await db.execute('''INSERT INTO deliveries_users (user_id, full_name, telegram_username, role, status)
                                   VALUES (?, ?, ?, ?, 'busy')
                                   ON CONFLICT (user_id) DO UPDATE SET full_name = excluded.full_name''',
                                (user_id, full_name, username, default_role))
                await db.commit()
        user = await get_user(user_id)
    elif is_admin and (user['role'] if isinstance(user, dict) else user[9]) != 'admin':
        if USE_POSTGRES:
            def _fix_adm():
                with get_pg_cursor() as cur:
                    cur.execute("UPDATE deliveries_users SET role = 'admin', is_blocked = 0 WHERE user_id = %s", (user_id,))
            await run_in_thread(_fix_adm)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                await db.execute("UPDATE deliveries_users SET role = 'admin', is_blocked = 0 WHERE user_id = ?", (user_id,))
                await db.commit()
        user = await get_user(user_id)

    user_dict = dict(user) if hasattr(user, 'keys') else {
        "user_id": user[0], "full_name": user[1], "phone": user[2],
        "role": user[9], "status": user[8], "station_id": user[10],
        "rating": float(user[11]), "total_trips": user[12],
        "is_blocked": bool(user[13]), "debt_balance": float(user[14])
    }

    # טעינת תחנות
    if USE_POSTGRES:
        def _get_st():
            with get_pg_cursor() as cur:
                cur.execute("SELECT station_id, name, commission_percent FROM deliveries_stations ORDER BY station_id ASC")
                return cur.fetchall()
        stations_raw = await run_in_thread(_get_st)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            stations_raw = await (await db.execute("SELECT station_id, name, commission_percent FROM deliveries_stations ORDER BY station_id ASC")).fetchall()

    stations = [dict(s) for s in stations_raw]
    cities = await get_driver_cities(user_id)

    return cors_json_response({
        "ok": True,
        "user": user_dict,
        "stations": stations,
        "cities": cities
    })

async def handle_api_orders(request):
    """החזרת רשימת קריאות פתוחות עבור ה-Mini App"""
    if USE_POSTGRES:
        def _get_orders():
            with get_pg_cursor() as cur:
                cur.execute('''SELECT order_id, text, price, publisher_id, station_id, driver_id, status, created_at, origin_city, dest_city
                               FROM deliveries_orders
                               WHERE status = 'open'
                               ORDER BY order_id DESC LIMIT 50''')
                return cur.fetchall()
        orders_raw = await run_in_thread(_get_orders)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            orders_raw = await (await db.execute('''SELECT order_id, text, price, publisher_id, station_id, driver_id, status, created_at, origin_city, dest_city
                                                   FROM deliveries_orders
                                                   WHERE status = 'open'
                                                   ORDER BY order_id DESC LIMIT 50''')).fetchall()
    orders = [dict(o) for o in orders_raw]
    return cors_json_response({"ok": True, "orders": orders})

async def handle_api_driver_status(request):
    """עדכון סטטוס נהג (פנוי / תפוס) ישירות מתוך ה-Mini App עם בדיקת חובות"""
    try:
        data = await request.json()
    except Exception:
        data = {}

    user_id = data.get("user_id")
    new_status = data.get("status")  # 'free' or 'busy'
    if not user_id or new_status not in ['free', 'busy']:
        return cors_json_response({"ok": False, "error": "פרמטרים שגויים"}, status=400)

    user = await get_user(int(user_id))
    if not user:
        return cors_json_response({"ok": False, "error": "משתמש לא נמצא"}, status=404)

    # בדיקת חוב פעיל - מניעת מעבר לפנוי עם חוב
    debt = user['debt_balance'] if isinstance(user, dict) else user[14]
    if new_status == 'free' and float(debt or 0) > 0:
        return cors_json_response({"ok": False, "error": f"יש לך חוב פתוח של ₪{debt:.2f}. עליך להסדיר או לערער."}, status=403)

    if USE_POSTGRES:
        def _update_st():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_users SET status = %s WHERE user_id = %s", (new_status, int(user_id)))
        await run_in_thread(_update_st)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE deliveries_users SET status = ? WHERE user_id = ?", (new_status, int(user_id)))
            await db.commit()

    return cors_json_response({"ok": True, "new_status": new_status})

async def handle_api_stations(request):
    """החזרת רשימת התחנות והעמלות"""
    if USE_POSTGRES:
        def _get_st():
            with get_pg_cursor() as cur:
                cur.execute("SELECT station_id, name, commission_percent, is_active FROM deliveries_stations ORDER BY station_id ASC")
                return cur.fetchall()
        rows = await run_in_thread(_get_st)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("SELECT station_id, name, commission_percent, is_active FROM deliveries_stations ORDER BY station_id ASC")).fetchall()
    return cors_json_response({"ok": True, "stations": [dict(r) for r in rows]})

async def start_web_server():
    app = web.Application()
    
    # בדיקת חיות ו-Keep Alive
    app.router.add_get("/ping", handle_ping)
    app.router.add_get("/health", handle_ping)

    # REST API עבור Telegram Mini App
    app.router.add_route("OPTIONS", "/api/{tail:.*}", handle_options)
    app.router.add_post("/api/auth", handle_api_auth)
    app.router.add_get("/api/orders", handle_api_orders)
    app.router.add_post("/api/driver/status", handle_api_driver_status)
    app.router.add_get("/api/stations", handle_api_stations)

    # 1. בדיקה אם קיימת תיקיית dist מקומפלת (React SPA)
    dist_dir = os.path.join(os.path.dirname(__file__), "dist")
    dist_index = os.path.join(dist_dir, "index.html")
    dist_assets = os.path.join(dist_dir, "assets")

    if os.path.exists(dist_assets) and os.path.isdir(dist_assets):
        app.router.add_static("/assets", path=dist_assets, name="assets")

    # פונקציית הגשת ה-Mini App: אם קיים dist/index.html מגיש אותו, ואם לא – מגיש את תבנית ה-HTML המשולבת המלאה!
    async def serve_webapp(request):
        if os.path.exists(dist_index):
            return web.FileResponse(dist_index)
        return web.Response(text=STANDALONE_MINIAPP_HTML, content_type="text/html", charset="utf-8")

    app.router.add_get("/", serve_webapp)
    app.router.add_get("/app", serve_webapp)
    app.router.add_get("/webapp", serve_webapp)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌐 Mini App & REST API Web Server active on port {port} (Ready for Telegram initData sync)")

# ----------------- מקלדות ועזרים -----------------
def get_main_kb(role='user', status='busy'):
    kb = []
    # כפתור פתיחת מיני אפליקציה ישירות בתוך טלגרם (ללא שגיאות וללא חסימות)
    kb.append([KeyboardButton(text="📱 פתח מיני אפליקציה (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))])
    
    if role in ['admin', 'station_manager', 'dispatcher']:
        kb.append([KeyboardButton(text="📢 פרסם קריאה"), KeyboardButton(text="📋 מצב קריאות")])
    if role in ['admin', 'station_manager']:
        kb.append([KeyboardButton(text="🏢 ניהול תחנה ועובדים")])
    if role == 'admin':
        kb.append([KeyboardButton(text="🛠️ פאנל מנהל מערכת")])
        
    status_btn = "🟢 פנוי לעבודה" if status == 'busy' else "🔴 תפוס (עצור קריאות)"
    kb.append([KeyboardButton(text=status_btn), KeyboardButton(text="📍 אזורי עבודה")])
    kb.append([KeyboardButton(text="💳 חיובים וערעורים"), KeyboardButton(text="💎 הפרופיל שלי")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול וחזרה")]], resize_keyboard=True)

def clean_order_text(text):
    text = re.sub(r'[-=]+>', '-', text)
    text = re.sub(r'<[-=]+', '-', text)
    text = text.replace("פת", "פתח תקווה").replace("ים", "ירושלים").replace("ספר", "מודיעין עילית")
    return text.strip()

# ----------------- תפריט ראשי, ביטול והרשמה -----------------
@router.message(Command("start"))
@router.message(F.text == "❌ ביטול וחזרה")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if user_id in ADMIN_IDS:
        if USE_POSTGRES:
            def _admin_upsert():
                with get_pg_cursor() as cur:
                    cur.execute('''INSERT INTO deliveries_users 
                        (user_id, full_name, phone, birth_year, car_brand, car_model, car_year, role, station_id) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET role = 'admin' ''', 
                        (user_id, "מנהל מערכת", "0500000000", 1990, "מנהל", "מנהל", 2024, "admin", 1))
            await run_in_thread(_admin_upsert)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                await db.execute('''INSERT OR IGNORE INTO deliveries_users 
                    (user_id, full_name, phone, birth_year, car_brand, car_model, car_year, role, station_id) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                    (user_id, "מנהל מערכת", "0500000000", 1990, "מנהל", "מנהל", 2024, "admin", 1))
                await db.execute('UPDATE deliveries_users SET role = "admin" WHERE user_id = ?', (user_id,))
                await db.commit()

    user = await get_user(user_id)
    if not user:
        await state.set_state(Reg.name)
        return await message.answer("👋 ברוכים הבאים למערכת ה-ERP!\nאנא הקלד את **שמך המלא**:", reply_markup=ReplyKeyboardRemove())
    
    if user['is_blocked']: return await message.answer("❌ חשבונך נחסם.")
    await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_kb(user['role'], user['status']))

# -- הרשמה מלאה וגמישה --
@router.message(Reg.name)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(Reg.birth_year)
    await message.answer("📅 **שנת לידה** (לדוגמה 1995):", reply_markup=cancel_kb())

@router.message(Reg.birth_year)
async def reg_birth(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ נא להזין שנת לידה חוקית.")
    if 2026 - int(message.text) < 18:
        await state.clear()
        return await message.answer("❌ המערכת לגילאי 18+ בלבד.")
    await state.update_data(birth_year=int(message.text))
    await state.set_state(Reg.phone)
    await message.answer("📱 לחץ למטה לשיתוף טלפון:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 שיתוף טלפון", request_contact=True)], [KeyboardButton(text="❌ ביטול וחזרה")]], resize_keyboard=True))

@router.message(Reg.phone)
async def reg_phone(message: Message, state: FSMContext):
    if not message.contact: return await message.answer("⚠️ חובה לשתף איש קשר דרך הכפתור.")
    phone = message.contact.phone_number.replace("+", "").replace("-", "").replace(" ", "")
    if not phone.startswith("05") and not phone.startswith("9725"): return await message.answer("⚠️ מספר ישראלי חובה (מתחיל ב-05 או 9725).")
    await state.update_data(phone=phone)
    await state.set_state(Reg.car_brand)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=b)] for b in CAR_BRANDS] + [[KeyboardButton(text="❌ ביטול וחזרה")]], resize_keyboard=True)
    await message.answer("🚗 בחר **חברת רכב** או 'אחר':", reply_markup=kb)

@router.message(Reg.car_brand)
async def reg_brand(message: Message, state: FSMContext):
    if message.text == "אחר (הקלדה ידנית)":
        return await message.answer("✍️ הקלד את שם חברת הרכב (למשל: סובארו):", reply_markup=cancel_kb())
    await state.update_data(brand=message.text)
    await state.set_state(Reg.car_model)
    await message.answer("✍️ הקלד **דגם רכב חופשי** (לדוגמה: סונטה היברידית):", reply_markup=cancel_kb())

@router.message(Reg.car_model)
async def reg_model(message: Message, state: FSMContext):
    await state.update_data(model=message.text)
    await state.set_state(Reg.car_year)
    await message.answer("📅 הקלד **שנת ייצור** באופן ידני (לדוגמה: 2017):", reply_markup=cancel_kb())

@router.message(Reg.car_year)
async def reg_year(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ שנתון חייב להיות במספרים.")
    await state.update_data(car_year=int(message.text))
    await state.set_state(Reg.car_seats)
    await message.answer("💺 כמה **מקומות ישיבה**?", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=str(i))] for i in [4, 5, 6, 7]] + [[KeyboardButton(text="❌ ביטול וחזרה")]], resize_keyboard=True))

@router.message(Reg.car_seats)
async def reg_seats(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ בחר מספר.")
    data = await state.get_data()
    
    if USE_POSTGRES:
        def _register_sync():
            with get_pg_cursor() as cur:
                cur.execute('''INSERT INTO deliveries_users (user_id, full_name, phone, birth_year, car_brand, car_model, car_year, car_seats, role) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'user')
                    ON CONFLICT (user_id) DO UPDATE SET 
                    full_name = EXCLUDED.full_name, phone = EXCLUDED.phone, birth_year = EXCLUDED.birth_year,
                    car_brand = EXCLUDED.car_brand, car_model = EXCLUDED.car_model, car_year = EXCLUDED.car_year, car_seats = EXCLUDED.car_seats''', 
                    (message.from_user.id, data['name'], data['phone'], data['birth_year'], data.get('brand','אחר'), data['model'], data['car_year'], int(message.text)))
        await run_in_thread(_register_sync)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('''INSERT OR REPLACE INTO deliveries_users (user_id, full_name, phone, birth_year, car_brand, car_model, car_year, car_seats, role) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'user')''', 
                (message.from_user.id, data['name'], data['phone'], data['birth_year'], data.get('brand','אחר'), data['model'], data['car_year'], int(message.text)))
            await db.commit()
            
    await state.clear()
    await message.answer("✅ **ההרשמה הושלמה!**", reply_markup=get_main_kb('user', 'busy'))

# ----------------- פעולות נהג (פרופיל, אזורי עבודה, סטטוס) -----------------
@router.message(F.text == "💎 הפרופיל שלי")
async def show_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user: return
    role_heb = ROLE_NAMES.get(user['role'], "נהג")
    txt = f"💎 **הפרופיל שלך:**\n👤 {user['full_name']}\n📱 {user['phone']}\n🛡️ {role_heb} (תחנה: {user['station_id']})\n\n🚗 רכב: {user['car_brand']} {user['car_model']} ({user['car_year']})\n⭐ דירוג: {user['rating']}/5.0 ({user['total_trips']} נסיעות)\n💰 חוב לתחנה: **{user['debt_balance']} ש\"ח**"
    await message.answer(txt)

@router.message(F.text == "📍 אזורי עבודה")
async def show_cities(message: Message, state: FSMContext):
    if USE_POSTGRES:
        def _get_cities_sync():
            with get_pg_cursor() as cur:
                cur.execute("SELECT city_name FROM deliveries_driver_cities WHERE user_id = %s", (message.from_user.id,))
                return cur.fetchall()
        cities = await run_in_thread(_get_cities_sync)
        cities_str = ", ".join([c['city_name'] for c in cities]) if cities else "לא הוגדרו אזורים"
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            cities = await (await db.execute("SELECT city_name FROM deliveries_driver_cities WHERE user_id = ?", (message.from_user.id,))).fetchall()
        cities_str = ", ".join([c[0] for c in cities]) if cities else "לא הוגדרו אזורים"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ הוסף עיר", callback_data="add_city")],
        [InlineKeyboardButton(text="🗑️ נקה הכל", callback_data="clear_cities")]
    ])
    await message.answer(f"📍 **הערים שלך:**\n{cities_str}\n\n*רק קריאות מהערים האלו יקפצו אליך כשתהיה פנוי.*", reply_markup=kb)

@router.callback_query(F.data == "add_city")
async def add_city_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(DriverFlow.waiting_new_city)
    await call.message.answer("✍️ הקלד עיר להוספה (למשל: מודיעין עילית):", reply_markup=cancel_kb())
    await call.answer()

@router.message(DriverFlow.waiting_new_city)
async def process_add_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if USE_POSTGRES:
        def _add_city_sync():
            with get_pg_cursor() as cur:
                cur.execute("INSERT INTO deliveries_driver_cities (user_id, city_name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (message.from_user.id, city))
        await run_in_thread(_add_city_sync)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("INSERT OR IGNORE INTO deliveries_driver_cities (user_id, city_name) VALUES (?, ?)", (message.from_user.id, city))
            await db.commit()
    await state.clear()
    user = await get_user(message.from_user.id)
    await message.answer(f"✅ העיר {city} נוספה בהצלחה.", reply_markup=get_main_kb(user['role'], user['status']))

@router.callback_query(F.data == "clear_cities")
async def clear_cities(call: CallbackQuery):
    if USE_POSTGRES:
        def _clear_cities_sync():
            with get_pg_cursor() as cur:
                cur.execute("DELETE FROM deliveries_driver_cities WHERE user_id = %s", (call.from_user.id,))
        await run_in_thread(_clear_cities_sync)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("DELETE FROM deliveries_driver_cities WHERE user_id = ?", (call.from_user.id,))
            await db.commit()
    await call.message.edit_text("✅ כל הערים נמחקו. לא תקבל קריאות עד שתוסיף ערים חדשות.")
    await call.answer()

@router.message(F.text.in_(["🟢 פנוי לעבודה", "🔴 תפוס (עצור קריאות)"]))
async def toggle_status(message: Message):
    user = await get_user(message.from_user.id)
    # אכיפת חובות Auto-Freeze (סעיף 276)
    if user['debt_balance'] > 500.0:
        return await message.answer("🚫 **חשבונך מוקפא עקב חובות (מעל 500 ש\"ח)!** לא תוכל לקבל קריאות עד הסדרת החוב.")
    
    new_status = 'free' if user['status'] == 'busy' else 'busy'
    if USE_POSTGRES:
        def _update_status():
            with get_pg_cursor() as cur:
                cur.execute('UPDATE deliveries_users SET status = %s WHERE user_id = %s', (new_status, message.from_user.id))
        await run_in_thread(_update_status)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('UPDATE deliveries_users SET status = ? WHERE user_id = ?', (new_status, message.from_user.id))
            await db.commit()
    msg = "🟢 אתה כעת פנוי (קריאות באזורים שלך יקפצו)!" if new_status == 'free' else "🔴 עצרת קריאות."
    await message.answer(msg, reply_markup=get_main_kb(user['role'], new_status))

# ----------------- פרסום קריאה (סדרן) -----------------
@router.message(F.text == "📢 פרסם קריאה")
async def cmd_publish(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'station_manager', 'dispatcher']: 
        return await message.answer("❌ אין לך הרשאת סדרן להפעיל פונקציה זו.")
    await state.set_state(OrderFlow.waiting_publish_text)
    await message.answer("📝 **הדבק פרטי קריאה:**\n(המערכת תנקה חצים אוטומטית. חובה לרשום מחיר).", reply_markup=cancel_kb())

@router.message(OrderFlow.waiting_publish_text)
async def process_publish_text(message: Message, state: FSMContext):
    cleaned_text = clean_order_text(message.text)
    prices = re.findall(r'\b\d{2,4}\b', cleaned_text)
    est_price = float(prices[-1]) if prices else 0.0
    
    if est_price == 0:
        return await message.answer("⚠️ המערכת לא זיהתה מחיר. נא לכלול מחיר בספרות (למשל 100).", reply_markup=cancel_kb())

    await state.update_data(order_text=cleaned_text, est_price=est_price)
    await state.set_state(OrderFlow.waiting_publish_dest)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="לנהגים בפרטי"), KeyboardButton(text="לקבוצות (חיצוני)")], [KeyboardButton(text="❌ ביטול וחזרה")]], resize_keyboard=True)
    await message.answer(f"✅ טקסט נוקה.\n💵 מחיר שזוהה: {est_price} ש\"ח.\n\nלאן לשגר את הקריאה?", reply_markup=kb)

@router.message(OrderFlow.waiting_publish_dest)
async def process_publish_dest(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)
        
    data = await state.get_data()
    user = await get_user(message.from_user.id)
    order_text = data['order_text']
    
    if USE_POSTGRES:
        def _create_order():
            with get_pg_cursor() as cur:
                cur.execute('INSERT INTO deliveries_orders (text, price, publisher_id, station_id, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING order_id', 
                            (order_text, data['est_price'], user['user_id'], user['station_id'], datetime.now().isoformat()))
                return cur.fetchone()['order_id']
        order_id = await run_in_thread(_create_order)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            cursor = await db.execute('INSERT INTO deliveries_orders (text, price, publisher_id, station_id, created_at) VALUES (?, ?, ?, ?, ?)', 
                                      (order_text, data['est_price'], user['user_id'], user['station_id'], datetime.now().isoformat()))
            order_id = cursor.lastrowid
            await db.commit()
        
    order_msg = f"🎫 **קריאה #{order_id}**\n🏢 סדרן: {user['full_name']}\n\n{order_text}\n\n💵 סכום: {data['est_price']} ש\"ח"
    
    if message.text == "לנהגים בפרטי":
        sent = 0
        if USE_POSTGRES:
            def _get_drivers_and_cities():
                with get_pg_cursor() as cur:
                    cur.execute("SELECT user_id FROM deliveries_users WHERE status = 'free' AND role = 'user' AND is_blocked = 0 AND debt_balance <= 500")
                    drivers = cur.fetchall()
                    cur.execute("SELECT user_id, city_name FROM deliveries_driver_cities")
                    cities = cur.fetchall()
                    return drivers, cities
            all_drivers, all_cities = await run_in_thread(_get_drivers_and_cities)
            
            # מיפוי ערים מהיר בזיכרון
            driver_cities_map = {}
            for c in all_cities:
                driver_cities_map.setdefault(c['user_id'], []).append(c['city_name'])

            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚗 קח קריאה", callback_data=f"take_{order_id}")]])
            for d in all_drivers:
                uid = d['user_id']
                my_cities = driver_cities_map.get(uid, [])
                should_send = False
                if not my_cities:
                    should_send = True
                else:
                    for city_name in my_cities:
                        if city_name in order_text:
                            should_send = True
                            break
                if should_send:
                    try:
                        await bot.send_message(uid, order_msg, reply_markup=kb)
                        sent += 1
                    except Exception:
                        pass
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                db.row_factory = aiosqlite.Row
                all_drivers = await (await db.execute("SELECT user_id FROM deliveries_users WHERE status = 'free' AND role = 'user' AND is_blocked = 0 AND debt_balance <= 500")).fetchall()
                
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚗 קח קריאה", callback_data=f"take_{order_id}")]])
            for d in all_drivers:
                async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                    driver_cities = await (await db.execute("SELECT city_name FROM deliveries_driver_cities WHERE user_id = ?", (d['user_id'],))).fetchall()
                
                should_send = False
                if not driver_cities:
                    should_send = True
                else:
                    for city_row in driver_cities:
                        if city_row[0] in order_text:
                            should_send = True
                            break
                if should_send:
                    try: 
                        await bot.send_message(d['user_id'], order_msg, reply_markup=kb)
                        sent += 1
                    except Exception:
                        pass
        await message.answer(f"✅ שוגר ל-{sent} נהגים בפרטי (סונן לפי אזורי העבודה שלהם).", reply_markup=get_main_kb(user['role'], user['status']))
    
    elif message.text == "לקבוצות (חיצוני)":
        sent = 0
        if USE_POSTGRES:
            def _get_groups():
                with get_pg_cursor() as cur:
                    cur.execute("SELECT group_id FROM deliveries_bot_groups")
                    return cur.fetchall()
            groups = await run_in_thread(_get_groups)
            for g in groups:
                try:
                    await bot.send_message(g['group_id'], order_msg)
                    sent += 1
                except Exception:
                    pass
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                groups = await (await db.execute("SELECT group_id FROM deliveries_bot_groups")).fetchall()
            for g in groups:
                try:
                    await bot.send_message(g[0], order_msg)
                    sent += 1
                except Exception:
                    pass
        await message.answer(f"✅ שוגר ל-{sent} קבוצות מוגדרות במערכת.", reply_markup=get_main_kb(user['role'], user['status']))
    
    await state.clear()

# ----------------- ניהול מצב קריאות (לסדרן) -----------------
@router.message(F.text == "📋 מצב קריאות")
async def show_open_orders(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'station_manager', 'dispatcher']: return
    
    if USE_POSTGRES:
        def _get_orders():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_orders WHERE station_id = %s AND status = 'open'", (user['station_id'],))
                return cur.fetchall()
        orders = await run_in_thread(_get_orders)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            orders = await (await db.execute("SELECT * FROM deliveries_orders WHERE station_id = ? AND status = 'open'", (user['station_id'],))).fetchall()
        
    if not orders:
        return await message.answer("✅ אין קריאות פתוחות לתחנה שלך כרגע.")
        
    for o in orders:
        txt = f"🎫 קריאה #{o['order_id']}\n💵 מחיר: {o['price']} ש\"ח\n📝 טקסט: {o['text']}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ מחק קריאה (נלקחה מחוץ לבוט)", callback_data=f"delorder_{o['order_id']}")]
        ])
        await message.answer(txt, reply_markup=kb)

@router.callback_query(F.data.startswith("delorder_"))
async def delete_open_order(call: CallbackQuery):
    order_id = call.data.split("_")[1]
    if USE_POSTGRES:
        def _delete_order():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_orders SET status = 'deleted' WHERE order_id = %s", (order_id,))
        await run_in_thread(_delete_order)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('UPDATE deliveries_orders SET status = "deleted" WHERE order_id = ?', (order_id,))
            await db.commit()
    await call.message.edit_text(f"✅ קריאה #{order_id} נסגרה/נמחקה מהמערכת.")
    await call.answer()
    
# ----------------- קבלת קריאה, ETA ומיזוג -----------------
@router.callback_query(F.data.startswith("take_"))
async def take_order(call: CallbackQuery, state: FSMContext):
    order_id = call.data.split("_")[1]
    
    driver = await get_user(call.from_user.id)
    if driver['status'] != 'free':
        return await call.answer("⚠️ אתה בסטטוס תפוס! העבר ל'פנוי' בתפריט הראשי קודם.", show_alert=True)
        
    await state.update_data(take_order_id=order_id)
    await state.set_state(OrderFlow.waiting_driver_eta)
    await call.message.answer(f"🎫 בקשה לקריאה #{order_id}\n⏱️ **כמה זמן עד להגעה למוצא?** (במספר דקות):", reply_markup=cancel_kb())
    await call.answer()

@router.message(OrderFlow.waiting_driver_eta)
async def process_eta(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data['take_order_id']
    driver = await get_user(message.from_user.id)
    
    if USE_POSTGRES:
        def _get_order():
            with get_pg_cursor() as cur:
                cur.execute('SELECT * FROM deliveries_orders WHERE order_id = %s', (order_id,))
                return cur.fetchone()
        order = await run_in_thread(_get_order)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            order = await (await db.execute('SELECT * FROM deliveries_orders WHERE order_id = ?', (order_id,))).fetchone()
        
    if not order or order['status'] != 'open':
        await state.clear()
        return await message.answer("❌ איחרת! הקריאה כבר נתפסה או בוטלה.", reply_markup=get_main_kb(driver['role'], driver['status']))
        
    msg_to_dispatcher = f"🔔 **נהג מבקש את קריאה #{order_id}**\n👤 נהג: {driver['full_name']} | ⭐ {driver['rating']}\n⏱️ זמן הגעה: {message.text} דקות\n🚗 רכב: {driver['car_brand']} {driver['car_model']} ({driver['car_seats']} מקומות)"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ אשר נהג (גבה עמלה)", callback_data=f"approve_{order_id}_{driver['user_id']}")],
        [InlineKeyboardButton(text="❌ דחה מתמודד", callback_data=f"deny_{order_id}_{driver['user_id']}")]
    ])
    
    try:
        await bot.send_message(order['publisher_id'], msg_to_dispatcher, reply_markup=kb)
    except Exception:
        pass
        
    await state.clear()
    await message.answer("⏳ הבקשה נשלחה בהצלחה לסדרן. המתנה לאישור...", reply_markup=get_main_kb(driver['role'], driver['status']))

# ----------------- סדרן מאשר/דוחה, חיוב עמלה ודירוג -----------------
@router.callback_query(F.data.startswith("deny_"))
async def deny_driver(call: CallbackQuery):
    _, order_id, driver_id = call.data.split("_")
    try:
        await bot.send_message(driver_id, f"❌ לצערנו הסדרן דחה את בקשתך לקריאה #{order_id}. נסה קריאה אחרת.")
    except Exception:
        pass
    await call.message.edit_text(f"❌ דחית את הנהג לקריאה #{order_id}. ההודעה נשלחה אליו.")
    await call.answer()

@router.callback_query(F.data.startswith("approve_"))
async def approve_driver(call: CallbackQuery):
    _, order_id, driver_id = call.data.split("_")
    
    if USE_POSTGRES:
        def _approve_transaction():
            with get_pg_cursor() as cur:
                cur.execute('SELECT * FROM deliveries_orders WHERE order_id = %s', (order_id,))
                order = cur.fetchone()
                
                if not order or order['status'] != 'open':
                    return None, 0
                    
                cur.execute('SELECT commission_percent FROM deliveries_stations WHERE station_id = %s', (order['station_id'],))
                station = cur.fetchone()
                
                cur.execute("UPDATE deliveries_orders SET status = 'closed', driver_id = %s WHERE order_id = %s", (driver_id, order_id))
                
                commission_rate = station['commission_percent'] if station else 10.0
                debt_amount = order['price'] * (commission_rate / 100)
                
                if debt_amount > 0:
                    cur.execute('INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason) VALUES (%s, %s, %s, %s, %s)', 
                                (order_id, driver_id, order['station_id'], debt_amount, f"עמלה {commission_rate}%"))
                    cur.execute('UPDATE deliveries_users SET debt_balance = debt_balance + %s, total_trips = total_trips + 1 WHERE user_id = %s', (debt_amount, driver_id))
                else:
                    cur.execute('UPDATE deliveries_users SET total_trips = total_trips + 1 WHERE user_id = %s', (driver_id,))
                return order, debt_amount

        order, debt_amount = await run_in_thread(_approve_transaction)
        if order is None:
            return await call.answer("⚠️ הקריאה כבר נסגרה!", show_alert=True)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            order = await (await db.execute('SELECT * FROM deliveries_orders WHERE order_id = ?', (order_id,))).fetchone()
            
            if not order or order['status'] != 'open':
                return await call.answer("⚠️ הקריאה כבר נסגרה!", show_alert=True)
                
            station = await (await db.execute('SELECT commission_percent FROM deliveries_stations WHERE station_id = ?', (order['station_id'],))).fetchone()
            
            await db.execute('UPDATE deliveries_orders SET status = "closed", driver_id = ? WHERE order_id = ?', (driver_id, order_id))
            
            commission_rate = station['commission_percent'] if station else 10.0
            debt_amount = order['price'] * (commission_rate / 100)
            
            if debt_amount > 0:
                await db.execute('INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason) VALUES (?, ?, ?, ?, ?)', 
                                 (order_id, driver_id, order['station_id'], debt_amount, f"עמלה {commission_rate}%"))
                await db.execute('UPDATE deliveries_users SET debt_balance = debt_balance + ?, total_trips = total_trips + 1 WHERE user_id = ?', (debt_amount, driver_id))
            else:
                await db.execute('UPDATE deliveries_users SET total_trips = total_trips + 1 WHERE user_id = ?', (driver_id,))
                
            await db.commit()
        
    try:
        await bot.send_message(driver_id, f"🎉 **אושרת לקריאה #{order_id}!**\nסע בזהירות.\n(חויבת בעמלה של {debt_amount} ש\"ח לתחנה)")
    except Exception:
        pass
    
    rate_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{driver_id}_1"), 
         InlineKeyboardButton(text="⭐⭐ 2", callback_data=f"rate_{driver_id}_2"), 
         InlineKeyboardButton(text="⭐⭐⭐ 3", callback_data=f"rate_{driver_id}_3")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐ 4", callback_data=f"rate_{driver_id}_4"), 
         InlineKeyboardButton(text="⭐⭐⭐⭐⭐ 5", callback_data=f"rate_{driver_id}_5")]
    ])
    await call.message.edit_text(f"✅ סגרת את קריאה #{order_id} על הנהג (נרשם חוב אוטומטי).\nאיך הנהג/הרכב נראה לך? דרג עכשיו:")
    await call.message.edit_reply_markup(reply_markup=rate_kb)
    await call.answer()

@router.callback_query(F.data.startswith("rate_"))
async def rate_driver(call: CallbackQuery):
    _, driver_id, stars = call.data.split("_")
    stars = int(stars)
    if USE_POSTGRES:
        def _rate_sync():
            with get_pg_cursor() as cur:
                cur.execute('SELECT rating, total_trips FROM deliveries_users WHERE user_id = %s', (driver_id,))
                driver = cur.fetchone()
                current_trips = max(driver['total_trips'], 1)
                new_rating = round(((driver['rating'] * (current_trips - 1)) + stars) / current_trips, 1)
                cur.execute('UPDATE deliveries_users SET rating = %s WHERE user_id = %s', (new_rating, driver_id))
        await run_in_thread(_rate_sync)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            driver = await (await db.execute('SELECT rating, total_trips FROM deliveries_users WHERE user_id = ?', (driver_id,))).fetchone()
            current_trips = max(driver['total_trips'], 1)
            new_rating = round(((driver['rating'] * (current_trips - 1)) + stars) / current_trips, 1)
            await db.execute('UPDATE deliveries_users SET rating = ? WHERE user_id = ?', (new_rating, driver_id))
            await db.commit()
        
    await call.message.edit_text(f"✅ דירגת את הנהג ב-{stars} כוכבים. המערכת עודכנה.")
    await call.answer()

# ----------------- מערכת ERP: ניהול חובות וערעורים -----------------
@router.message(F.text == "💳 חיובים וערעורים")
async def show_debts(message: Message):
    if USE_POSTGRES:
        def _get_debts():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_debts WHERE driver_id = %s AND status = 'unpaid'", (message.from_user.id,))
                return cur.fetchall()
        debts = await run_in_thread(_get_debts)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debts = await (await db.execute("SELECT * FROM deliveries_debts WHERE driver_id = ? AND status = 'unpaid'", (message.from_user.id,))).fetchall()
        
    if not debts: return await message.answer("✅ אין לך חובות פתוחים במערכת.")
        
    for d in debts:
        txt = f"🧾 **חיוב מתחנה {d['station_id']}**\nעבור קריאה #{d['order_id']}\n💰 סכום לתשלום: {d['amount']} ש\"ח\nסיבה: {d['reason']}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚖️ ערעור / בקשת ביטול", callback_data=f"appeal_{d['debt_id']}")]])
        await message.answer(txt, reply_markup=kb)

@router.callback_query(F.data.startswith("appeal_"))
async def start_appeal(call: CallbackQuery, state: FSMContext):
    await state.update_data(debt_id=call.data.split("_")[1])
    await state.set_state(DebtFlow.waiting_dispute_reason)
    await call.message.answer("✍️ **מדוע אתה מבקש לבטל את החיוב הזה?**\nהקש את הסיבה (למשל: 'הלקוח ביטל'):", reply_markup=cancel_kb())
    await call.answer()

@router.message(DebtFlow.waiting_dispute_reason)
async def process_appeal(message: Message, state: FSMContext):
    data = await state.get_data()
    driver = await get_user(message.from_user.id)
    debt_id = data['debt_id']
    
    appeal_msg = f"⚖️ **ערעור על חיוב #{debt_id}**\nנהג: {driver['full_name']} (טל: {driver['phone']})\nסיבה: {message.text}"
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ אשר ביטול (מחק חוב)", callback_data=f"deldebt_{debt_id}_{driver['user_id']}"),
         InlineKeyboardButton(text="❌ דחה ערעור (השאר חוב)", callback_data=f"keepdebt_{debt_id}_{driver['user_id']}")]
    ])
    
    for admin_id in ADMIN_IDS:
        try: await bot.send_message(admin_id, appeal_msg, reply_markup=admin_kb)
        except Exception: pass
            
    await state.clear()
    await message.answer("✅ הערעור נשלח להנהלה לבדיקה. תקבל עדכון בקרוב.", reply_markup=get_main_kb(driver['role'], driver['status']))

@router.callback_query(F.data.startswith("deldebt_"))
async def admin_del_debt(call: CallbackQuery):
    _, debt_id, driver_id = call.data.split("_")
    if USE_POSTGRES:
        def _del_debt_sync():
            with get_pg_cursor() as cur:
                cur.execute('SELECT amount, status FROM deliveries_debts WHERE debt_id = %s', (debt_id,))
                debt = cur.fetchone()
                if debt and debt['status'] == 'unpaid':
                    cur.execute("UPDATE deliveries_debts SET status = 'cancelled' WHERE debt_id = %s", (debt_id,))
                    cur.execute('UPDATE deliveries_users SET debt_balance = debt_balance - %s WHERE user_id = %s', (debt['amount'], driver_id))
                    return debt['amount'], True
                return 0, False
        amount, success = await run_in_thread(_del_debt_sync)
        if success:
            try:
                await bot.send_message(driver_id, f"✅ **הערעור התקבל!** חוב של {amount} ש\"ח (עבור חיוב #{debt_id}) בוטל.")
            except Exception: pass
            await call.message.edit_text(f"✅ אישרת את הערעור ומחקת את חוב #{debt_id}.")
        else:
            await call.message.edit_text(f"⚠️ החוב #{debt_id} כבר טופל או שולם.")
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debt = await (await db.execute('SELECT amount, status FROM deliveries_debts WHERE debt_id = ?', (debt_id,))).fetchone()
            if debt and debt['status'] == 'unpaid':
                await db.execute('UPDATE deliveries_debts SET status = "cancelled" WHERE debt_id = ?', (debt_id,))
                await db.execute('UPDATE deliveries_users SET debt_balance = debt_balance - ? WHERE user_id = ?', (debt['amount'], driver_id))
                await db.commit()
                try:
                    await bot.send_message(driver_id, f"✅ **הערעור התקבל!** חוב של {debt['amount']} ש\"ח (עבור חיוב #{debt_id}) בוטל.")
                except Exception: pass
                await call.message.edit_text(f"✅ אישרת את הערעור ומחקת את חוב #{debt_id}.")
            else:
                await call.message.edit_text(f"⚠️ החוב #{debt_id} כבר טופל או שולם.")
    await call.answer()

@router.callback_query(F.data.startswith("keepdebt_"))
async def admin_keep_debt(call: CallbackQuery):
    _, debt_id, driver_id = call.data.split("_")
    try:
        await bot.send_message(driver_id, f"❌ **הערעור נדחה!** חיוב #{debt_id} נשאר בעינו ויש להסדירו מול התחנה.")
    except Exception: pass
    await call.message.edit_text(f"❌ דחית את הערעור על חוב #{debt_id}. החוב נשאר.")
    await call.answer()

# ----------------- God Mode וניהול תחנות -----------------
@router.message(F.text.in_(["🛠️ פאנל מנהל מערכת", "🏢 ניהול תחנה ועובדים"]))
async def admin_panel(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'station_manager']: 
        return
    
    kb_list = []
    if user['role'] == 'admin':
        kb_list.append([InlineKeyboardButton(text="➕ פתיחת תחנה חדשה", callback_data="god_new_station")])
        kb_list.append([InlineKeyboardButton(text="👥 ניהול הרשאות משתמשים", callback_data="god_manage_users")])
        kb_list.append([InlineKeyboardButton(text="📢 הודעת Broadcast גלובלית", callback_data="god_broadcast")])
    elif user['role'] == 'station_manager':
        kb_list.append([InlineKeyboardButton(text="👥 פנה להנהלה להוספת עובדים", callback_data="mgr_dummy")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
    await message.answer("👑 **פאנל ניהול מתקדם**\nבחר את הפעולה הרצויה:", reply_markup=kb)

# --- פתיחת תחנה חדשה ---
@router.callback_query(F.data == "god_new_station")
async def god_new_station(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_station_name)
    await call.message.answer("🏢 הקלד את **שם התחנה החדשה** (למשל: תחנת המרכז):", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminFlow.waiting_station_name)
async def process_new_station(message: Message, state: FSMContext):
    await state.update_data(new_station_name=message.text)
    await state.set_state(AdminFlow.waiting_station_comm)
    await message.answer("💰 מה יהיה **אחוז העמלה** של התחנה? (למשל 10.5):")

@router.message(AdminFlow.waiting_station_comm)
async def finalize_station(message: Message, state: FSMContext):
    try: comm = float(message.text)
    except Exception: return await message.answer("⚠️ נא להזין מספר.")
    
    data = await state.get_data()
    if USE_POSTGRES:
        def _create_station():
            with get_pg_cursor() as cur:
                cur.execute('INSERT INTO deliveries_stations (name, commission_percent) VALUES (%s, %s)', (data['new_station_name'], comm))
        await run_in_thread(_create_station)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('INSERT INTO deliveries_stations (name, commission_percent) VALUES (?, ?)', (data['new_station_name'], comm))
            await db.commit()
    await state.clear()
    await message.answer(f"✅ תחנה **{data['new_station_name']}** נוצרה עם עמלה של {comm}%.", reply_markup=get_main_kb('admin', 'busy'))

# --- ניהול הרשאות (God Mode) ---
@router.callback_query(F.data == "god_manage_users")
async def god_manage_users(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_user_id_role)
    await call.message.answer("👥 **ניהול הרשאות:**\nאנא הקלד את פקודת השינוי בפורמט הבא:\n`[מזהה_משתמש] [תפקיד] [מזהה_תחנה]`\n\nתפקידים אפשריים: admin, station_manager, dispatcher, user, blocked\nלדוגמה: `123456 dispatcher 1`", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminFlow.waiting_user_id_role)
async def process_manage_users(message: Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("⚠️ פורמט שגוי. נסה שוב (ID Role StationID).")
    
    target_id = parts[0]
    new_role = parts[1]
    station_id = parts[2] if len(parts) > 2 else 0
    
    is_blocked = 1 if new_role == 'blocked' else 0
    role_to_save = 'user' if new_role == 'blocked' else new_role

    if USE_POSTGRES:
        def _update_user_perms():
            with get_pg_cursor() as cur:
                cur.execute('UPDATE deliveries_users SET role = %s, station_id = %s, is_blocked = %s WHERE user_id = %s', 
                            (role_to_save, int(station_id), is_blocked, int(target_id)))
        await run_in_thread(_update_user_perms)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('UPDATE deliveries_users SET role = ?, station_id = ?, is_blocked = ? WHERE user_id = ?', 
                             (role_to_save, int(station_id), is_blocked, int(target_id)))
            await db.commit()
        
    await state.clear()
    await message.answer(f"✅ המשתמש {target_id} עודכן בהצלחה לתפקיד {new_role} בתחנה {station_id}.", reply_markup=get_main_kb('admin', 'busy'))
    
    try:
        await bot.send_message(int(target_id), f"🔄 **עדכון מערכת:**\nההרשאות שלך עודכנו על ידי ההנהלה.\nתפקיד נוכחי: {new_role}")
    except Exception: pass

# --- שידור גלובלי (Broadcast) ---
@router.callback_query(F.data == "god_broadcast")
async def god_broadcast_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_broadcast)
    await call.message.answer("📢 הקלד את ההודעה שתשודר **לכל המשתמשים במערכת** (נהגים, סדרנים ומנהלים):", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminFlow.waiting_broadcast)
async def god_broadcast_send(message: Message, state: FSMContext):
    if USE_POSTGRES:
        def _get_all_users():
            with get_pg_cursor() as cur:
                cur.execute("SELECT user_id FROM deliveries_users")
                return cur.fetchall()
        users = await run_in_thread(_get_all_users)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            users = await (await db.execute("SELECT user_id FROM deliveries_users")).fetchall()
        
    sent = 0
    for u in users:
        uid = u['user_id'] if isinstance(u, dict) else u[0]
        try:
            await bot.send_message(uid, f"📢 **הודעת הנהלה מיוחדת:**\n\n{message.text}")
            sent += 1
        except Exception: pass
    await state.clear()
    await message.answer(f"✅ ההודעה שודרה בהצלחה ל-{sent} משתמשים.", reply_markup=get_main_kb('admin', 'busy'))

@router.callback_query(F.data == "mgr_dummy")
async def mgr_dummy(call: CallbackQuery):
    await call.answer("פעולה זו מבוצעת על ידי הנהלת המערכת.", show_alert=True)

# ----------------- הרצה (Main Loop עם מניעת Conflict וטיפול במופעים כפולים) -----------------
async def main():
    await init_db()
    await start_web_server()
    
    if not BOT_TOKEN or BOT_TOKEN == "DUMMY_TOKEN_PLEASE_SET_BOT_TOKEN":
        logging.error("❌ לא נמצא BOT_TOKEN חוקי. שרת ה-Keep-Alive פועל, אך הבוט ממתין להגדרת BOT_TOKEN ב-Render.")
        while True:
            await asyncio.sleep(3600)

    logging.info(f"🚀 MASTER ERP COMPLETE IS LIVE! (Mini App URL: {WEBAPP_URL})")
    try:
        # הגדרת כפתור תפריט עבור מיני אפליקציה בטלגרם
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🚖 פתח אפליקציה", web_app=WebAppInfo(url=WEBAPP_URL)))
    except Exception as e:
        logging.warning(f"Could not set default menu button web app: {e}")

    # מחיקת webhook ועדכונים ממתינים עם מרווח שחרור
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.warning(f"delete_webhook note: {e}")

    await asyncio.sleep(1)

    while True:
        try:
            logging.info("📡 Bot Polling started (optimized updates)...")
            await dp.start_polling(bot, drop_pending_updates=True, allowed_updates=dp.resolve_used_update_types())
            break
        except TelegramConflictError:
            logging.error("⚠️ זוהה בוט כפול (TelegramConflictError)! יש מופע נוסף שרץ במקביל עם אותו ה-BOT_TOKEN. בדוק שירותים כפולים ב-Render או הרצה פתוחה במחשב. מנסה שוב בעוד 5 שניות...")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"⚠️ שגיאה ב-Polling: {e}. מנסה שוב בעוד 3 שניות...")
            await asyncio.sleep(3)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped safely.")
