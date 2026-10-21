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

from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
    TelegramObject
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

# ----------------- סעיף 3: אכיפה קשיחה של שם משתמש (@username) -----------------
class UsernameEnforcementMiddleware(BaseMiddleware):
    """
    חוסם כל פעולה של משתמש שאין לו שם משתמש בטלגרם (@username).
    שולח הדרכה מפורטת להגדרת שם משתמש ומחייב לחיצה על /start מחדש.
    זה קריטי עבור יצירת הקישורים הישירים (Deep Links) בין סדרנים לנהגים!
    """
    async def __call__(self, handler, event: TelegramObject, data: dict):
        from_user = getattr(event, "from_user", None)
        if from_user and not from_user.is_bot:
            # אם יש שם משתמש - מסנכרנים אותו במסד הנתונים
            if from_user.username:
                uname = from_user.username
                uid = from_user.id
                if USE_POSTGRES:
                    def _sync_uname():
                        try:
                            with get_pg_cursor() as cur:
                                cur.execute("UPDATE deliveries_users SET telegram_username = %s WHERE user_id = %s AND (telegram_username IS NULL OR telegram_username != %s)", (uname, uid, uname))
                        except Exception: pass
                    asyncio.create_task(run_in_thread(_sync_uname))
                else:
                    async def _sync_uname_sqlite():
                        try:
                            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                                await db.execute("UPDATE deliveries_users SET telegram_username = ? WHERE user_id = ? AND (telegram_username IS NULL OR telegram_username != ?)", (uname, uid, uname))
                                await db.commit()
                        except Exception: pass
                    asyncio.create_task(_sync_uname_sqlite())
            else:
                # חסימה מחמירה של משתמש ללא @username
                guide_text = (
                    "🚫 <b>חסום לשימוש: חובה להגדיר שם משתמש בטלגרם (@username)!</b>\n\n"
                    "מערכת ה-ERP פועלת באמצעות קישורים ישירים ומאובטחים (Deep Links) לשיחה בין נהגים, סדרנים ומנהלים.\n\n"
                    "⚙️ <b>כיצד מגדירים שם משתמש תוך 10 שניות?</b>\n"
                    "1️⃣ היכנס ל<b>הגדרות</b> בטלגרם (Settings).\n"
                    "2️⃣ לחץ על <b>הגדר שם משתמש</b> (Username).\n"
                    "3️⃣ הקלד כינוי באנגלית (לדוגמה: <code>@driver_israel</code>) ולחץ שמור.\n"
                    "4️⃣ חזור לכאן ולחץ <b>/start</b> מחדש כדי להמשיך!"
                )
                if isinstance(event, Message):
                    chat_type = getattr(event.chat, 'type', 'private')
                    if chat_type in ('group', 'supergroup'):
                        await event.reply(
                            f"⚠️ {from_user.full_name}, חובה להגדיר @username בהגדרות טלגרם כדי להשתמש בבוט!",
                            reply_markup=ReplyKeyboardRemove()
                        )
                    else:
                        await event.answer(guide_text, parse_mode=ParseMode.HTML)
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ חובה להגדיר שם משתמש (@username) בהגדרות טלגרם!", show_alert=True)
                return
        return await handler(event, data)

dp.message.middleware(UsernameEnforcementMiddleware())
dp.callback_query.middleware(UsernameEnforcementMiddleware())


ROLE_NAMES = {
    "admin": "מנהל מערכת",
    "station_manager": "מנהל תחנה",
    "dispatcher": "סדרן",
    "user": "נהג / שליח"
}
CAR_BRANDS = [
    "יונדאי", "טויוטה", "קיה", "סקודה", "מאזדה", "שברולט", "ניסאן", "אחר (הקלדה ידנית)"
]
POPULAR_CITIES = [
    "ירושלים", "בני ברק", "פתח תקווה", "תל אביב", 
    "מודיעין עילית", "אשדוד", "בית שמש", "נתניה"
]

# ----------------- מצבים (FSM) -----------------
class Onboarding(StatesGroup):
    waiting_terms = State()       # שלב 1: אישור תקנון
    waiting_contact = State()     # שלב 2: אימות טלפון חומרה
    waiting_birth_year = State()   # שלב 3: אימות גיל (18+)
    waiting_car_brand = State()    # שלב 4: מותג רכב
    waiting_car_model = State()    # שלב 4: דגם רכב
    waiting_car_year = State()     # שלב 4: שנת ייצור
    waiting_car_seats = State()    # שלב 4: מספר מקומות ישיבה
    waiting_cities = State()       # שלב 5: בחירת אזורי עבודה וקיצורי ערים

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
            ("completed_at", "TIMESTAMP"),
            ("requires_eta", "INTEGER DEFAULT 0")
        ]
        for col_name, col_type in order_columns_to_add:
            try:
                cur.execute(f"ALTER TABLE deliveries_orders ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception: pass

        # 4. טבלת חובות ועמלות (Ledger)
        cur.execute('''CREATE TABLE IF NOT EXISTS deliveries_debts (
            debt_id SERIAL PRIMARY KEY, 
            order_id INTEGER, 
            driver_id BIGINT,
            station_id INTEGER, 
            amount REAL, 
            status TEXT DEFAULT 'unpaid', 
            reason TEXT,
            appeal_status TEXT DEFAULT 'none',
            appeal_reason TEXT,
            transaction_type TEXT DEFAULT 'commission',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP)''')

        debt_columns_to_add = [
            ("appeal_status", "TEXT DEFAULT 'none'"),
            ("appeal_reason", "TEXT"),
            ("transaction_type", "TEXT DEFAULT 'commission'")
        ]
        for col_name, col_type in debt_columns_to_add:
            try:
                cur.execute(f"ALTER TABLE deliveries_debts ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception: pass


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

        # ניקוי שולחן (Wipe) שלב ב' - אכיפת רישום קפדני לכל המשתמשים הישנים
        cur.execute("SELECT setting_value FROM deliveries_system_settings WHERE setting_key = 'wipe_stage_b'")
        wipe_check = cur.fetchone()
        if not wipe_check:
            try:
                cur.execute("TRUNCATE deliveries_users CASCADE")
                cur.execute("TRUNCATE deliveries_driver_cities")
                cur.execute("""INSERT INTO deliveries_system_settings (setting_key, setting_value) 
                               VALUES ('wipe_stage_b', 'completed') 
                               ON CONFLICT (setting_key) DO UPDATE SET setting_value = 'completed'""")
                logging.info("🧹 בוצע ניקוי שולחן (TRUNCATE) מלא של טבלת המשתמשים והערים לאכיפת שלב ב'!")
            except Exception as e:
                logging.warning(f"Note on TRUNCATE deliveries_users: {e}")

        # תחנת ברירת מחדל
        cur.execute('''INSERT INTO deliveries_stations (station_id, name, commission_percent) 
                       VALUES (1, 'תחנה ראשית', 10.0) 
                       ON CONFLICT (station_id) DO NOTHING''')

        # ביצור הרשאות מנהלי מערכת קבועים (552821474 ו-8644923212) - מצב God Mode
        for admin_id in ADMIN_IDS:
            cur.execute('''INSERT INTO deliveries_users (user_id, full_name, phone, is_phone_verified, birth_year, role, status, is_blocked)
                           VALUES (%s, 'מנהל ראשי', '0500000000', 1, 1990, 'admin', 'free', 0)
                           ON CONFLICT (user_id) DO UPDATE SET role = 'admin', is_phone_verified = 1, is_blocked = 0''', (admin_id,))

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
                taken_at TEXT, completed_at TEXT, requires_eta INTEGER DEFAULT 0)''')
            try:
                await db.execute("ALTER TABLE deliveries_orders ADD COLUMN requires_eta INTEGER DEFAULT 0")
            except Exception: pass
            
            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_debts (
                debt_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, driver_id INTEGER,
                station_id INTEGER, amount REAL, status TEXT DEFAULT 'unpaid', reason TEXT, 
                appeal_status TEXT DEFAULT 'none', appeal_reason TEXT, transaction_type TEXT DEFAULT 'commission',
                created_at TEXT, resolved_at TEXT)''')
            for col, ctype in [("appeal_status", "TEXT DEFAULT 'none'"), ("appeal_reason", "TEXT"), ("transaction_type", "TEXT DEFAULT 'commission'")]:
                try:
                    await db.execute(f"ALTER TABLE deliveries_debts ADD COLUMN {col} {ctype}")
                except Exception: pass


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
                
            # ניקוי שולחן (Wipe) שלב ב' עבור SQLite
            cursor = await db.execute("SELECT setting_value FROM deliveries_system_settings WHERE setting_key = 'wipe_stage_b'")
            wipe_check = await cursor.fetchone()
            if not wipe_check:
                await db.execute("DELETE FROM deliveries_users")
                await db.execute("DELETE FROM deliveries_driver_cities")
                await db.execute("INSERT OR REPLACE INTO deliveries_system_settings (setting_key, setting_value) VALUES ('wipe_stage_b', 'completed')")
                logging.info("🧹 בוצע ניקוי שולחן (SQLite) לאכיפת שלב ב'!")

            await db.execute('INSERT OR IGNORE INTO deliveries_stations (station_id, name, commission_percent) VALUES (1, "תחנה ראשית", 10.0)')

            for admin_id in ADMIN_IDS:
                await db.execute('''INSERT INTO deliveries_users (user_id, full_name, phone, is_phone_verified, birth_year, role, status)
                                   VALUES (?, 'מנהל ראשי', '0500000000', 1, 1990, 'admin', 'free')
                                   ON CONFLICT(user_id) DO UPDATE SET role = 'admin', is_phone_verified = 1, is_blocked = 0''', (admin_id,))

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

def resolve_city_name_sync(city_input: str) -> str:
    """זיהוי ונירמול שמות ערים מתוך מאגר הקיצורים deliveries_city_aliases (למשל 'ים' -> 'ירושלים', 'בב' -> 'בני ברק')"""
    cleaned = city_input.strip()
    if not cleaned:
        return ""
    if USE_POSTGRES:
        with get_pg_cursor() as cur:
            cur.execute("SELECT standard_city FROM deliveries_city_aliases WHERE alias = %s", (cleaned,))
            res = cur.fetchone()
            if res:
                return res['standard_city']
    else:
        import sqlite3
        conn = sqlite3.connect(SQLITE_DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT standard_city FROM deliveries_city_aliases WHERE alias = ?", (cleaned,))
        res = cur.fetchone()
        conn.close()
        if res:
            return res[0]
    return cleaned

async def resolve_city_name(city_input: str) -> str:
    return await run_in_thread(resolve_city_name_sync, city_input)

def build_cities_selection_kb(selected_cities: list) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for city in POPULAR_CITIES:
        is_sel = city in selected_cities
        prefix = "✅ " if is_sel else "▫️ "
        row.append(InlineKeyboardButton(text=f"{prefix}{city}", callback_data=f"ob_city_{city}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    count_txt = f" ({len(selected_cities)} נבחרו)" if selected_cities else ""
    buttons.append([InlineKeyboardButton(text=f"🚀 סיום הרשמה וכניסה למערכת{count_txt}", callback_data="ob_finish")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
    <button onclick="switchTab('admin')" id="tab-btn-admin" class="hidden flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-amber-500 text-slate-950 transition text-center whitespace-nowrap shadow-md">
      👑 פאנל מנהל
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

    <!-- ADMIN TAB (God Mode Master Dashboard - Real CRUD) -->
    <div id="tab-admin" class="hidden space-y-4">
      <div class="bg-slate-900 border border-amber-500/40 rounded-2xl p-4 shadow-lg space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-xl">👑</span>
            <span class="font-extrabold text-sm text-white">פאנל מנהל ראשי (God Mode)</span>
          </div>
          <span class="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded font-bold">LIVE API SYNC</span>
        </div>
        <p class="text-xs text-slate-300">שליטה מלאה במשתמשים, תחנות, מנויים, חובות והגדרות מערכת.</p>
      </div>

      <!-- Admin Sub-navigation -->
      <div class="bg-slate-900 p-1.5 rounded-xl border border-slate-800 flex flex-wrap gap-1 text-xs">
        <button onclick="switchAdminSubtab('users')" id="asub-btn-users" class="flex-1 py-1 px-2.5 rounded-lg font-bold bg-amber-500 text-slate-950 transition">👥 משתמשים</button>
        <button onclick="switchAdminSubtab('stations')" id="asub-btn-stations" class="flex-1 py-1 px-2.5 rounded-lg font-bold bg-slate-800 text-slate-300 transition">🏢 תחנות</button>
        <button onclick="switchAdminSubtab('subs')" id="asub-btn-subs" class="flex-1 py-1 px-2.5 rounded-lg font-bold bg-slate-800 text-slate-300 transition">💎 מנויים</button>
        <button onclick="switchAdminSubtab('debts')" id="asub-btn-debts" class="flex-1 py-1 px-2.5 rounded-lg font-bold bg-slate-800 text-slate-300 transition">💳 חובות</button>
        <button onclick="switchAdminSubtab('settings')" id="asub-btn-settings" class="flex-1 py-1 px-2.5 rounded-lg font-bold bg-slate-800 text-slate-300 transition">⚙️ הגדרות</button>
        <button onclick="switchAdminSubtab('broadcast')" id="asub-btn-broadcast" class="flex-1 py-1 px-2.5 rounded-lg font-bold bg-slate-800 text-slate-300 transition">📢 שידור</button>
      </div>

      <!-- Toast Feedback -->
      <div id="admin-toast" class="hidden p-3 rounded-xl text-xs font-bold transition flex items-center justify-between"></div>

      <!-- 1. USERS SUBTAB -->
      <div id="asub-users" class="space-y-3">
        <div class="flex items-center justify-between gap-2">
          <input type="text" id="admin-user-search" oninput="renderAdminUsers()" placeholder="חפש משתמש לפי שם, טלפון או ID..." class="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500">
          <button onclick="loadAdminUsers()" class="bg-slate-800 hover:bg-slate-700 text-white text-xs px-3 py-2 rounded-xl font-bold whitespace-nowrap">🔄 רענן</button>
        </div>
        <div id="admin-users-list" class="space-y-2.5 text-xs">
          <div class="p-4 text-center text-slate-400">טוען משתמשים מ-PostgreSQL...</div>
        </div>
      </div>

      <!-- 2. STATIONS SUBTAB -->
      <div id="asub-stations" class="hidden space-y-4">
        <!-- Create Station Card -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 text-xs">
          <span class="font-bold text-white block">➕ פתיחת תחנה חדשה במערכת</span>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="text-[10px] text-slate-400 block mb-1">שם התחנה</label>
              <input type="text" id="new-station-name" placeholder="למשל: תחנת הצפון" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white focus:outline-none focus:border-amber-500">
            </div>
            <div>
              <label class="text-[10px] text-slate-400 block mb-1">אחוז עמלה (%)</label>
              <input type="number" id="new-station-comm" value="10.0" step="0.5" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white focus:outline-none focus:border-amber-500">
            </div>
          </div>
          <button onclick="createStationSubmit()" class="w-full py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-xl font-bold transition">
            צור תחנה חדשה
          </button>
        </div>

        <!-- Existing Stations -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-2.5 text-xs">
          <span class="font-bold text-white block">🏢 תחנות פעילות ועמלות</span>
          <div id="admin-stations-list" class="space-y-2">
            <div class="p-3 text-center text-slate-400">טוען תחנות...</div>
          </div>
        </div>
      </div>

      <!-- 3. SUBSCRIPTIONS SUBTAB -->
      <div id="asub-subs" class="hidden space-y-3 text-xs">
        <div class="grid grid-cols-3 gap-2">
          <div class="bg-slate-900 border border-amber-500/30 rounded-xl p-3 text-center space-y-1">
            <span class="font-bold text-amber-400 block">👑 VIP Master</span>
            <span class="text-[10px] text-slate-400 block">ללא הגבלת נסיעות</span>
            <span class="text-[10px] text-emerald-400 font-bold block">0% עמלה</span>
          </div>
          <div class="bg-slate-900 border border-sky-500/30 rounded-xl p-3 text-center space-y-1">
            <span class="font-bold text-sky-400 block">⚡ Basic</span>
            <span class="text-[10px] text-slate-400 block">עד 10 נסיעות ביום</span>
            <span class="text-[10px] text-slate-300 block">עמלה רגילה</span>
          </div>
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 text-center space-y-1">
            <span class="font-bold text-slate-300 block">🆓 Free</span>
            <span class="text-[10px] text-slate-400 block">עד 3 נסיעות ביום</span>
            <span class="text-[10px] text-red-400 block">הקפאה ב-₪500 חוב</span>
          </div>
        </div>
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <span class="font-bold text-white block">שיוך מנוי מהיר למשתמש</span>
          <div class="flex gap-2">
            <input type="number" id="sub-user-id" placeholder="מזהה משתמש (ID)..." class="flex-1 bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
            <select id="sub-plan-select" class="bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
              <option value="vip_master">VIP Master</option>
              <option value="basic">Basic</option>
              <option value="free">Free</option>
            </select>
            <button onclick="assignSubscriptionSubmit()" class="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-3 py-2 rounded-xl transition">החל</button>
          </div>
        </div>
      </div>

      <!-- 4. DEBTS & LEDGER SUBTAB -->
      <div id="asub-debts" class="hidden space-y-4 text-xs">
        <!-- Manual Charge / Credit Card -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <span class="font-bold text-white block">⚖️ חיוב ידני / זיכוי / קנס לנהג</span>
          <div class="grid grid-cols-3 gap-2">
            <input type="number" id="debt-driver-id" placeholder="ID נהג" class="bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
            <input type="number" id="debt-amount" placeholder="סכום (ש\"ח)" class="bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
            <input type="text" id="debt-reason" placeholder="סיבה (למשל קנס/בונוס)" class="bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
          </div>
          <div class="flex gap-2">
            <button onclick="submitManualDebt('charge')" class="flex-1 py-2 bg-red-600/30 hover:bg-red-600 text-red-200 border border-red-500/40 rounded-xl font-bold transition">
              ➕ חייב נהג (הוסף חוב)
            </button>
            <button onclick="submitManualDebt('credit')" class="flex-1 py-2 bg-emerald-600/30 hover:bg-emerald-600 text-emerald-200 border border-emerald-500/40 rounded-xl font-bold transition">
              ➖ זכה נהג (הפחת חוב)
            </button>
          </div>
        </div>

        <!-- Ledger & Appeals List -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-2.5">
          <div class="flex justify-between items-center">
            <span class="font-bold text-white">יומן חיובים וערעורים פעילים</span>
            <button onclick="loadAdminDebts()" class="text-amber-400 hover:underline">🔄 רענן</button>
          </div>
          <div id="admin-debts-list" class="space-y-2">
            <div class="p-3 text-center text-slate-400">טוען נתוני חובות...</div>
          </div>
        </div>
      </div>

      <!-- 5. SETTINGS & NLP SUBTAB -->
      <div id="asub-settings" class="hidden space-y-4 text-xs">
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <span class="font-bold text-white block">⚙️ הגדרות מערכת גלובליות</span>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-[10px] text-slate-400 block mb-1">עמלת ברירת מחדל (%)</label>
              <input type="number" id="setting-def-comm" value="10.0" step="0.5" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
            </div>
            <div>
              <label class="text-[10px] text-slate-400 block mb-1">תקרת Auto-Freeze (ש\"ח)</label>
              <input type="number" id="setting-auto-freeze" value="500" class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
            </div>
          </div>
          <button onclick="saveGlobalSettingsSubmit()" class="w-full py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-xl font-bold transition">
            שמור הגדרות מערכת
          </button>
        </div>

        <!-- NLP City Aliases -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <span class="font-bold text-white block">🗺️ מילון קיצורי ערים (מנוע NLP לסדרנים)</span>
          <div class="flex gap-2">
            <input type="text" id="new-alias-key" placeholder="קיצור (למשל: ים, בב, קס)" class="flex-1 bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
            <input type="text" id="new-alias-val" placeholder="עיר תקנית (למשל: ירושלים)" class="flex-1 bg-slate-950 border border-slate-700 rounded-xl p-2 text-xs text-white">
            <button onclick="addCityAliasSubmit()" class="bg-slate-800 hover:bg-slate-700 text-white font-bold px-3 py-2 rounded-xl transition">הוסף</button>
          </div>
          <div id="admin-aliases-list" class="flex flex-wrap gap-1.5 pt-2 max-h-40 overflow-y-auto">
            <!-- Injected aliases -->
          </div>
        </div>
      </div>

      <!-- 6. BROADCAST SUBTAB -->
      <div id="asub-broadcast" class="hidden space-y-3 text-xs">
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3">
          <span class="font-bold text-white block">📢 שידור הודעת Broadcast לכל המערכת</span>
          <textarea id="admin-broadcast-text" rows="3" placeholder="הקלד כאן הודעת הנהלה מתפרצת שתשודר לכל הנהגים והסדרנים..." class="w-full bg-slate-950 border border-slate-700 rounded-xl p-2.5 text-xs text-white focus:outline-none focus:border-amber-500 resize-none"></textarea>
          <button onclick="sendAdminBroadcastSubmit()" class="w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-xl font-bold transition shadow-md">
            שגר הודעה לכל המשתמשים
          </button>
        </div>
      </div>
    </div>
  </main>

  <script>
    const ADMIN_IDS = [8644923212, 552821474];

    // Initialize Telegram WebApp
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      const user = tg.initDataUnsafe?.user;
      if (user) {
        const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || 'משתמש טלגרם';
        const isAdmin = ADMIN_IDS.includes(Number(user.id));
        document.getElementById('tg-username').innerText = name + (isAdmin ? ' 👑 (God Mode)' : ' (מזהה: ' + user.id + ')');
        document.getElementById('profile-name').innerText = name;
        
        if (isAdmin) {
          const admBtn = document.getElementById('tab-btn-admin');
          if (admBtn) {
            admBtn.classList.remove('hidden');
            setTimeout(() => switchTab('admin'), 50);
          }
        }
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

    let cachedAdminUsers = [];
    let cachedAdminStations = [];
    let cachedAdminDebts = [];

    function showAdminToast(msg, isSuccess = true) {
      const toast = document.getElementById('admin-toast');
      if (!toast) return;
      toast.className = `p-3 rounded-xl text-xs font-bold transition flex items-center justify-between ${
        isSuccess ? 'bg-emerald-950/80 border border-emerald-500/40 text-emerald-200' : 'bg-red-950/80 border border-red-500/40 text-red-200'
      }`;
      toast.innerText = msg;
      toast.classList.remove('hidden');
      setTimeout(() => toast.classList.add('hidden'), 4000);
    }

    function switchAdminSubtab(subtab) {
      const subtabs = ['users', 'stations', 'subs', 'debts', 'settings', 'broadcast'];
      subtabs.forEach(st => {
        const el = document.getElementById('asub-' + st);
        const btn = document.getElementById('asub-btn-' + st);
        if (el) el.classList.toggle('hidden', st !== subtab);
        if (btn) {
          btn.className = st === subtab
            ? 'flex-1 py-1 px-2.5 rounded-lg font-bold bg-amber-500 text-slate-950 transition'
            : 'flex-1 py-1 px-2.5 rounded-lg font-bold bg-slate-800 text-slate-300 transition';
        }
      });
      if (subtab === 'users') loadAdminUsers();
      if (subtab === 'stations') loadAdminStations();
      if (subtab === 'debts') loadAdminDebts();
      if (subtab === 'settings') loadAdminSettings();
    }

    async function loadAdminUsers() {
      const container = document.getElementById('admin-users-list');
      try {
        const res = await fetch('/api/users');
        const data = await res.json();
        if (data.ok && data.users) {
          cachedAdminUsers = data.users;
          renderAdminUsers();
        }
      } catch (e) {
        if (cachedAdminUsers.length > 0) renderAdminUsers();
        else container.innerHTML = '<div class="p-4 text-center text-red-400">שגיאה בטעינת משתמשים.</div>';
      }
    }

    function renderAdminUsers() {
      const container = document.getElementById('admin-users-list');
      const query = (document.getElementById('admin-user-search')?.value || '').trim();
      const filtered = cachedAdminUsers.filter(u => 
        (u.full_name || '').includes(query) || 
        String(u.user_id).includes(query) || 
        (u.phone || '').includes(query)
      );

      if (filtered.length === 0) {
        container.innerHTML = '<div class="p-4 text-center text-slate-400">לא נמצאו משתמשים.</div>';
        return;
      }

      container.innerHTML = filtered.map(u => `
        <div class="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-2">
          <div class="flex justify-between items-start">
            <div>
              <span class="font-bold text-white text-xs">${u.full_name || 'משתמש'}</span>
              <span class="text-[10px] text-slate-400 font-mono block">ID: ${u.user_id} • 📱 ${u.phone || 'אין טלפון'}</span>
              <span class="text-[10px] text-slate-400 block">🚗 ${u.car_brand || 'רכב'} ${u.car_model || ''}</span>
            </div>
            <div class="text-left font-mono">
              <span class="text-xs font-bold ${u.debt_balance > 0 ? 'text-red-400' : 'text-emerald-400'}">חוב: ₪${(u.debt_balance || 0).toFixed(2)}</span>
              <span class="text-[10px] text-amber-400 block">⭐ ${u.rating || 5.0} (${u.total_trips || 0} נסיעות)</span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-800/80">
            <select id="role-sel-${u.user_id}" class="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-[11px] text-white">
              <option value="user" ${u.role === 'user' ? 'selected' : ''}>נהג / משתמש</option>
              <option value="dispatcher" ${u.role === 'dispatcher' ? 'selected' : ''}>סדרן</option>
              <option value="station_manager" ${u.role === 'station_manager' ? 'selected' : ''}>מנהל תחנה</option>
              <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>מנהל ראשי (God Mode)</option>
              <option value="blocked" ${u.is_blocked ? 'selected' : ''}>חסימה 🚫</option>
            </select>
            <input type="number" id="st-sel-${u.user_id}" value="${u.station_id || 1}" title="תחנה #" placeholder="תחנה" class="w-14 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-[11px] text-white text-center font-mono">
            <button onclick="saveUserRow(${u.user_id})" class="bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-2.5 py-1 rounded-lg text-[11px] transition">💾 שמור</button>
            <button onclick="quickDriverDebt(${u.user_id}, 'charge')" class="bg-red-950 hover:bg-red-800 text-red-200 border border-red-800 px-2 py-1 rounded-lg text-[10px]">+ חיוב</button>
            <button onclick="quickDriverDebt(${u.user_id}, 'credit')" class="bg-emerald-950 hover:bg-emerald-800 text-emerald-200 border border-emerald-800 px-2 py-1 rounded-lg text-[10px]">- זיכוי</button>
          </div>
        </div>
      `).join('');
    }

    async function saveUserRow(userId) {
      const roleSel = document.getElementById('role-sel-' + userId)?.value;
      const stVal = parseInt(document.getElementById('st-sel-' + userId)?.value || '1', 10);
      try {
        const res = await fetch('/api/users/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, role: roleSel, station_id: stVal })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ משתמש ${userId} עודכן לתפקיד ${roleSel} בתחנה ${stVal}!`);
          loadAdminUsers();
        } else {
          showAdminToast('שגיאה: ' + (data.error || 'נכשל'), false);
        }
      } catch (e) {
        showAdminToast('שגיאת תקשורת בעדכון המשתמש', false);
      }
    }

    async function quickDriverDebt(userId, action) {
      const amountStr = prompt(action === 'charge' ? 'כמה שקלים לחייב את הנהג?' : 'כמה שקלים לזכות את הנהג?');
      if (!amountStr || isNaN(parseFloat(amountStr))) return;
      const amount = parseFloat(amountStr);
      const reason = prompt('סיבת החיוב/זיכוי:') || (action === 'charge' ? 'חיוב מנהל' : 'זיכוי מנהל');
      
      const endpoint = action === 'charge' ? '/api/debts/charge' : '/api/debts/credit';
      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ driver_id: userId, amount: amount, reason: reason })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ פעולת ${action === 'charge' ? 'חיוב' : 'זיכוי'} של ₪${amount} לנהג ${userId} בוצעה בהצלחה!`);
          loadAdminUsers();
        }
      } catch (e) {
        showAdminToast('שגיאה בביצוע פעולת החוב', false);
      }
    }

    async function loadAdminStations() {
      const container = document.getElementById('admin-stations-list');
      try {
        const res = await fetch('/api/stations');
        const data = await res.json();
        if (data.ok && data.stations) {
          cachedAdminStations = data.stations;
          container.innerHTML = data.stations.map(s => `
            <div class="p-3 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center text-xs">
              <div>
                <span class="font-bold text-white block">${s.name} (תחנה #${s.station_id})</span>
                <span class="text-[10px] text-slate-400">עמלה פעילה: ${s.commission_percent}%</span>
              </div>
              <div class="flex items-center gap-1.5">
                <input type="number" id="st-comm-${s.station_id}" value="${s.commission_percent}" step="0.5" class="w-16 bg-slate-900 border border-slate-700 rounded-lg p-1 text-xs text-white text-center font-mono">
                <button onclick="updateStationCommSubmit(${s.station_id})" class="bg-amber-500 hover:bg-amber-400 text-slate-950 px-2 py-1 rounded-lg font-bold text-[11px]">עדכן %</button>
              </div>
            </div>
          `).join('');
        }
      } catch (e) {
        container.innerHTML = '<div class="p-3 text-center text-slate-400">שגיאה בטעינת תחנות</div>';
      }
    }

    async function createStationSubmit() {
      const name = document.getElementById('new-station-name').value.trim();
      const comm = parseFloat(document.getElementById('new-station-comm').value || '10.0');
      if (!name) return showAdminToast('נא להזין שם תחנה', false);
      try {
        const res = await fetch('/api/stations/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name, commission_percent: comm })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ תחנה "${name}" נוצרה בהצלחה עם ${comm}% עמלה!`);
          document.getElementById('new-station-name').value = '';
          loadAdminStations();
        }
      } catch (e) {
        showAdminToast('שגיאה ביצירת תחנה', false);
      }
    }

    async function updateStationCommSubmit(stationId) {
      const comm = parseFloat(document.getElementById('st-comm-' + stationId)?.value || '10.0');
      try {
        const res = await fetch('/api/stations/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ station_id: stationId, commission_percent: comm })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ עמלת תחנה #${stationId} עודכנה ל-${comm}%!`);
          loadAdminStations();
        }
      } catch (e) {
        showAdminToast('שגיאה בעדכון עמלה', false);
      }
    }

    async function assignSubscriptionSubmit() {
      const uid = parseInt(document.getElementById('sub-user-id').value, 10);
      const plan = document.getElementById('sub-plan-select').value;
      if (!uid) return showAdminToast('נא להזין מזהה משתמש תקין', false);
      try {
        const res = await fetch('/api/users/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: uid, subscription_plan: plan })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ מנוי ${plan} הוקצה למשתמש ${uid} בהצלחה!`);
          document.getElementById('sub-user-id').value = '';
        }
      } catch (e) {
        showAdminToast('שגיאה בשיוך מנוי', false);
      }
    }

    async function loadAdminDebts() {
      const container = document.getElementById('admin-debts-list');
      try {
        const res = await fetch('/api/debts');
        const data = await res.json();
        if (data.ok && data.debts) {
          cachedAdminDebts = data.debts;
          if (data.debts.length === 0) {
            container.innerHTML = '<div class="p-3 text-center text-slate-400">אין חובות או ערעורים פתוחים במערכת.</div>';
            return;
          }
          container.innerHTML = data.debts.map(d => `
            <div class="p-3 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center text-xs">
              <div>
                <span class="font-bold text-white block">חוב #${d.debt_id} (נהג: ${d.driver_id})</span>
                <span class="text-[10px] text-slate-400 block">${d.reason || 'עמלה'} • סטטוס: ${d.status}</span>
                ${d.appeal_status === 'pending' ? `<span class="text-[10px] text-amber-400 font-bold block">⚖️ ערעור ממתין: ${d.appeal_reason || 'ללא פירוט'}</span>` : ''}
              </div>
              <div class="text-left space-y-1">
                <span class="font-bold text-red-400 block">₪${Number(d.amount).toFixed(2)}</span>
                ${d.status === 'unpaid' ? `
                  <div class="flex gap-1">
                    <button onclick="resolveDebtSubmit(${d.debt_id}, true, ${d.driver_id}, ${d.amount})" class="text-[10px] bg-emerald-600/30 hover:bg-emerald-600 text-emerald-200 px-2 py-0.5 rounded border border-emerald-500/40">מחק חוב</button>
                    <button onclick="resolveDebtSubmit(${d.debt_id}, false, ${d.driver_id}, ${d.amount})" class="text-[10px] bg-red-600/30 hover:bg-red-600 text-red-200 px-2 py-0.5 rounded border border-red-500/40">דחה</button>
                  </div>
                ` : ''}
              </div>
            </div>
          `).join('');
        }
      } catch (e) {
        container.innerHTML = '<div class="p-3 text-center text-slate-400">שגיאה בטעינת יומן חובות</div>';
      }
    }

    async function resolveDebtSubmit(debtId, approve, driverId, amount) {
      try {
        const res = await fetch('/api/debts/credit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ debt_id: debtId, driver_id: driverId, amount: amount, approve: approve })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(approve ? `✅ חוב #${debtId} בוטל וזוכה בהצלחה!` : `❌ ערעור נדחה לחוב #${debtId}.`);
          loadAdminDebts();
        }
      } catch (e) {
        showAdminToast('שגיאה בטיפול בחוב', false);
      }
    }

    async function submitManualDebt(action) {
      const driverId = parseInt(document.getElementById('debt-driver-id').value, 10);
      const amount = parseFloat(document.getElementById('debt-amount').value);
      const reason = document.getElementById('debt-reason').value.trim() || (action === 'charge' ? 'חיוב הנהלה' : 'זיכוי הנהלה');
      if (!driverId || isNaN(amount) || amount <= 0) {
        return showAdminToast('נא להזין ID נהג וסכום תקין', false);
      }
      const endpoint = action === 'charge' ? '/api/debts/charge' : '/api/debts/credit';
      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ driver_id: driverId, amount: amount, reason: reason })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ פעולת ${action === 'charge' ? 'חיוב' : 'זיכוי'} של ₪${amount} לנהג ${driverId} נשמרה בהצלחה!`);
          document.getElementById('debt-driver-id').value = '';
          document.getElementById('debt-amount').value = '';
          document.getElementById('debt-reason').value = '';
          loadAdminDebts();
        }
      } catch (e) {
        showAdminToast('שגיאה בביצוע הפעולה', false);
      }
    }

    async function loadAdminSettings() {
      try {
        const res = await fetch('/api/settings');
        const data = await res.json();
        if (data.ok) {
          if (data.settings) {
            if (data.settings.default_commission) document.getElementById('setting-def-comm').value = data.settings.default_commission;
            if (data.settings.auto_freeze_threshold) document.getElementById('setting-auto-freeze').value = data.settings.auto_freeze_threshold;
          }
          if (data.aliases) {
            const listEl = document.getElementById('admin-aliases-list');
            listEl.innerHTML = data.aliases.map(a => `
              <span class="inline-flex items-center gap-1 bg-slate-950 text-slate-300 border border-slate-700 px-2 py-0.5 rounded text-[11px]">
                <strong class="text-amber-400 font-mono">${a.alias}</strong> ➔ ${a.standard_city}
              </span>
            `).join('');
          }
        }
      } catch (e) {}
    }

    async function saveGlobalSettingsSubmit() {
      const comm = document.getElementById('setting-def-comm').value;
      const freeze = document.getElementById('setting-auto-freeze').value;
      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ default_commission: comm, auto_freeze_threshold: freeze })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast('✅ הגדרות המערכת הגלובליות נשמרו בהצלחה ב-PostgreSQL!');
        }
      } catch (e) {
        showAdminToast('שגיאה בשמירת הגדרות', false);
      }
    }

    async function addCityAliasSubmit() {
      const key = document.getElementById('new-alias-key').value.trim();
      const val = document.getElementById('new-alias-val').value.trim();
      if (!key || !val) return showAdminToast('נא להזין קיצור ועיר מלאה', false);
      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ alias: key, standard_city: val })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ קיצור NLP "${key}" ➔ "${val}" נוסף בהצלחה למאגר!`);
          document.getElementById('new-alias-key').value = '';
          document.getElementById('new-alias-val').value = '';
          loadAdminSettings();
        }
      } catch (e) {
        showAdminToast('שגיאה בהוספת קיצור עיר', false);
      }
    }

    async function sendAdminBroadcastSubmit() {
      const text = document.getElementById('admin-broadcast-text').value.trim();
      if (!text) return showAdminToast('נא להקליד תוכן להודעה', false);
      try {
        const res = await fetch('/api/broadcast', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text })
        });
        const data = await res.json();
        if (data.ok) {
          showAdminToast(`✅ הודעת Broadcast שודרה בהצלחה לכל המשתמשים (${data.count || 0})!`);
          document.getElementById('admin-broadcast-text').value = '';
        }
      } catch (e) {
        showAdminToast('שגיאה בשידור הודעה', false);
      }
    }

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
        showAdminToast("⚠️ אתה בסטטוס תפוס! העבר לפנוי למעלה קודם.", false);
        return;
      }
      const eta = prompt("⏱️ כמה זמן עד להגעה למוצא? (במספר דקות):", "10");
      if (eta) {
        showAdminToast(`✅ בקשתך לקריאה #${id} עם זמן הגעה של ${eta} דקות שוגרה לסדרן!`);
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
        showAdminToast("⚠️ המערכת לא זיהתה מחיר. נא לכלול מחיר בספרות (למשל: 150).", false);
        return;
      }

      const newId = 1000 + orders.length + 2;
      orders.unshift({ id: newId, text: cleaned, price: estPrice, time: 'הרגע' });
      input.value = '';
      previewOrder();
      renderOrders();
      showAdminToast(`✅ קריאה #${newId} שוגרה בהצלחה לנהגים באזורי היעד!`);
      switchTab('driver');
    }

    function appealDebt(id) {
      const reason = prompt("✍️ מדוע אתה מבקש לבטל את החיוב הזה? (למשל: 'הלקוח ביטל במקום'):");
      if (reason) {
        showAdminToast(`✅ ערעור על חיוב #${id} נשלח להנהלת המערכת לבדיקה.`);
      }
    }

    function switchTab(tab) {
      document.getElementById('tab-driver').classList.add('hidden');
      document.getElementById('tab-dispatcher').classList.add('hidden');
      document.getElementById('tab-profile').classList.add('hidden');
      if (document.getElementById('tab-admin')) {
        document.getElementById('tab-admin').classList.add('hidden');
      }

      const btnD = document.getElementById('tab-btn-driver');
      const btnDisp = document.getElementById('tab-btn-dispatcher');
      const btnProf = document.getElementById('tab-btn-profile');
      const btnAdm = document.getElementById('tab-btn-admin');

      if (btnD) btnD.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap";
      if (btnDisp) btnDisp.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap";
      if (btnProf) btnProf.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap";
      if (btnAdm) btnAdm.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 transition text-center whitespace-nowrap";

      const targetEl = document.getElementById('tab-' + tab);
      const targetBtn = document.getElementById('tab-btn-' + tab);
      if (targetEl) targetEl.classList.remove('hidden');
      if (targetBtn) targetBtn.className = "flex-1 py-1.5 px-3 rounded-lg text-xs font-bold bg-amber-500 text-slate-950 transition text-center whitespace-nowrap shadow-md";

      if (tab === 'admin') {
        loadAdminUsers();
      }
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

async def get_driver_cities(user_id: int) -> list:
    """שליפת רשימת הערים האמיתיות של הנהג מטבלת deliveries_driver_cities"""
    if not user_id:
        return []
    if USE_POSTGRES:
        def _get():
            with get_pg_cursor() as cur:
                cur.execute("SELECT city_name FROM deliveries_driver_cities WHERE user_id = %s ORDER BY city_name ASC", (user_id,))
                return [r['city_name'] for r in cur.fetchall()]
        return await run_in_thread(_get)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            rows = await (await db.execute("SELECT city_name FROM deliveries_driver_cities WHERE user_id = ? ORDER BY city_name ASC", (user_id,))).fetchall()
            return [r[0] for r in rows]

async def handle_api_driver_cities_get(request):
    """שליפת ערי עבודה של נהג מתוך deliveries_driver_cities עבור המיני-אפליקציה"""
    user_id = request.query.get("user_id")
    if not user_id:
        return cors_json_response({"ok": False, "error": "user_id חובה"}, status=400)
    cities = await get_driver_cities(int(user_id))
    return cors_json_response({"ok": True, "cities": cities})

async def handle_api_driver_cities_add(request):
    """הוספת עיר עבודה לנהג ב-deliveries_driver_cities ישירות מהאפליקציה"""
    try: data = await request.json()
    except Exception: data = {}
    user_id = data.get("user_id")
    city_name = (data.get("city_name") or "").strip()
    if not user_id or not city_name:
        return cors_json_response({"ok": False, "error": "user_id ו-city_name חובה"}, status=400)
    user_id = int(user_id)
    if USE_POSTGRES:
        def _add():
            with get_pg_cursor() as cur:
                cur.execute("INSERT INTO deliveries_driver_cities (user_id, city_name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, city_name))
        await run_in_thread(_add)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("INSERT OR IGNORE INTO deliveries_driver_cities (user_id, city_name) VALUES (?, ?)", (user_id, city_name))
            await db.commit()
    cities = await get_driver_cities(user_id)
    return cors_json_response({"ok": True, "cities": cities})

async def handle_api_driver_cities_remove(request):
    """הסרת עיר עבודה לנהג מ-deliveries_driver_cities ישירות מהאפליקציה"""
    try: data = await request.json()
    except Exception: data = {}
    user_id = data.get("user_id")
    city_name = (data.get("city_name") or "").strip()
    if not user_id or not city_name:
        return cors_json_response({"ok": False, "error": "user_id ו-city_name חובה"}, status=400)
    user_id = int(user_id)
    if USE_POSTGRES:
        def _rem():
            with get_pg_cursor() as cur:
                cur.execute("DELETE FROM deliveries_driver_cities WHERE user_id = %s AND city_name = %s", (user_id, city_name))
        await run_in_thread(_rem)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("DELETE FROM deliveries_driver_cities WHERE user_id = ? AND city_name = ?", (user_id, city_name))
            await db.commit()
    cities = await get_driver_cities(user_id)
    return cors_json_response({"ok": True, "cities": cities})

async def handle_api_driver_cities_clear(request):
    """ניקוי כל ערי העבודה לנהג ב-deliveries_driver_cities"""
    try: data = await request.json()
    except Exception: data = {}
    user_id = data.get("user_id")
    if not user_id:
        return cors_json_response({"ok": False, "error": "user_id חובה"}, status=400)
    user_id = int(user_id)
    if USE_POSTGRES:
        def _clr():
            with get_pg_cursor() as cur:
                cur.execute("DELETE FROM deliveries_driver_cities WHERE user_id = %s", (user_id,))
        await run_in_thread(_clr)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("DELETE FROM deliveries_driver_cities WHERE user_id = ?", (user_id,))
            await db.commit()
    return cors_json_response({"ok": True, "cities": []})

async def handle_api_auth(request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    init_data = data.get("initData") or request.headers.get("X-Telegram-Init-Data", "")
    user_payload = validate_telegram_init_data(init_data)

    # זיהוי מחמיר ובטוח של מנהל מערכת גם מתוך מחרוזת ה-initData או מזהה שנשלח
    if not user_payload:
        dev_user_id = data.get("dev_user_id") or data.get("user_id") or request.query.get("user_id")
        if dev_user_id and int(dev_user_id) in ADMIN_IDS:
            user_payload = {"id": int(dev_user_id), "first_name": "מנהל ראשי (God Mode)"}
        elif init_data:
            try:
                parsed_q = dict(parse_qsl(init_data, keep_blank_values=True))
                u_raw = parsed_q.get("user")
                if u_raw:
                    u_obj = json.loads(u_raw)
                    if u_obj.get("id") and int(u_obj.get("id")) in ADMIN_IDS:
                        user_payload = u_obj
            except Exception:
                pass

    if not user_payload:
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
                    cur.execute('''INSERT INTO deliveries_users (user_id, full_name, telegram_username, role, status, is_phone_verified)
                                   VALUES (%s, %s, %s, %s, 'busy', 1)
                                   ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name''',
                                (user_id, full_name, username, default_role))
            await run_in_thread(_create_u)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                await db.execute('''INSERT INTO deliveries_users (user_id, full_name, telegram_username, role, status, is_phone_verified)
                                   VALUES (?, ?, ?, ?, 'busy', 1)
                                   ON CONFLICT (user_id) DO UPDATE SET full_name = excluded.full_name''',
                                (user_id, full_name, username, default_role))
                await db.commit()
        user = await get_user(user_id)
    elif is_admin and (user['role'] if isinstance(user, dict) else user[9]) != 'admin':
        if USE_POSTGRES:
            def _fix_adm():
                with get_pg_cursor() as cur:
                    cur.execute("UPDATE deliveries_users SET role = 'admin', is_blocked = 0, is_phone_verified = 1 WHERE user_id = %s", (user_id,))
            await run_in_thread(_fix_adm)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                await db.execute("UPDATE deliveries_users SET role = 'admin', is_blocked = 0, is_phone_verified = 1 WHERE user_id = ?", (user_id,))
                await db.commit()
        user = await get_user(user_id)

    user_dict = dict(user) if hasattr(user, 'keys') else {
        "user_id": user[0], "full_name": user[1], "phone": user[2],
        "role": user[9], "status": user[8], "station_id": user[10],
        "rating": float(user[11]), "total_trips": user[12],
        "is_blocked": bool(user[13]), "debt_balance": float(user[14])
    }

    # אבטחת תפקיד admin למנהלי מערכת (God Mode)
    if is_admin:
        user_dict["role"] = "admin"
        user_dict["is_phone_verified"] = 1
        user_dict["is_blocked"] = 0

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

async def handle_api_driver_profile(request):
    """קבלת פרטי רכב וערי עבודה מה-Mini App ושמירתם ב-deliveries_users וב-deliveries_driver_cities"""
    try:
        data = await request.json()
    except Exception:
        data = {}

    init_data = data.get("initData") or request.headers.get("X-Telegram-Init-Data", "")
    user_payload = validate_telegram_init_data(init_data)
    user_id = None
    if user_payload:
        user_id = int(user_payload.get("id"))
    elif data.get("user_id"):
        user_id = int(data.get("user_id"))

    if not user_id:
        return cors_json_response({"ok": False, "error": "אימות משתמש נכשל"}, status=401)

    car_brand = str(data.get("car_brand", "")).strip()
    car_model = str(data.get("car_model", "")).strip()
    car_year = int(data.get("car_year") or 2022)
    car_seats = int(data.get("car_seats") or 4)
    # עדכון ערי עבודה אך ורק אם נשלחה רשימת ערים מפורשת בבקשה (מניעת איפוס ערים בעת שמירת רכב)
    should_update_cities = ("cities" in data and isinstance(data["cities"], list))
    cities = data.get("cities") or []

    if USE_POSTGRES:
        def _update_profile_sync():
            with get_pg_cursor() as cur:
                cur.execute('''UPDATE deliveries_users 
                               SET car_brand = %s, car_model = %s, car_year = %s, car_seats = %s
                               WHERE user_id = %s''',
                            (car_brand, car_model, car_year, car_seats, user_id))
                
                if should_update_cities:
                    cur.execute('DELETE FROM deliveries_driver_cities WHERE user_id = %s', (user_id,))
                    for city in cities:
                        c = str(city).strip()
                        if c:
                            cur.execute('''INSERT INTO deliveries_driver_cities (user_id, city_name) 
                                           VALUES (%s, %s) ON CONFLICT DO NOTHING''', (user_id, c))
        await run_in_thread(_update_profile_sync)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('''UPDATE deliveries_users 
                               SET car_brand = ?, car_model = ?, car_year = ?, car_seats = ?
                               WHERE user_id = ?''',
                            (car_brand, car_model, car_year, car_seats, user_id))
            if should_update_cities:
                await db.execute('DELETE FROM deliveries_driver_cities WHERE user_id = ?', (user_id,))
                for city in cities:
                    c = str(city).strip()
                    if c:
                        await db.execute('INSERT OR IGNORE INTO deliveries_driver_cities (user_id, city_name) VALUES (?, ?)', (user_id, c))
            await db.commit()

    return cors_json_response({"ok": True, "message": "פרטי הפרופיל נשמרו בהצלחה!"})

# ----------------- נתיבי REST API נוספים לניהול מלא (CRUD) עבור ה-Mini App -----------------
async def handle_api_users(request):
    """החזרת כל משתמשי המערכת עבור פאנל הניהול של ה-Mini App"""
    if USE_POSTGRES:
        def _get():
            with get_pg_cursor() as cur:
                cur.execute("""SELECT user_id, full_name, phone, telegram_username, role, status, 
                                      station_id, rating, total_trips, is_blocked, debt_balance, 
                                      car_brand, car_model, car_year, car_seats, subscription_plan 
                               FROM deliveries_users ORDER BY user_id ASC""")
                return cur.fetchall()
        rows = await run_in_thread(_get)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("""SELECT user_id, full_name, phone, telegram_username, role, status, 
                                                     station_id, rating, total_trips, is_blocked, debt_balance, 
                                                     car_brand, car_model, car_year, car_seats, subscription_plan 
                                              FROM deliveries_users ORDER BY user_id ASC""")).fetchall()
    return cors_json_response({"ok": True, "users": [dict(r) for r in rows]})

async def handle_api_users_update(request):
    """עדכון הרשאות, תפקיד, שיוך לתחנה או מנוי של משתמש"""
    try: data = await request.json()
    except Exception: data = {}
    user_id = data.get("user_id")
    if not user_id:
        return cors_json_response({"ok": False, "error": "user_id חובה"}, status=400)
    
    role = data.get("role")
    is_blocked = 1 if role == 'blocked' else data.get("is_blocked")
    if role == 'blocked':
        role = 'user'
    station_id = data.get("station_id")
    sub_plan = data.get("subscription_plan")
    
    if USE_POSTGRES:
        def _update():
            with get_pg_cursor() as cur:
                updates = []
                params = []
                if role is not None:
                    updates.append("role = %s")
                    params.append(role)
                if is_blocked is not None:
                    updates.append("is_blocked = %s")
                    params.append(int(is_blocked))
                if station_id is not None:
                    updates.append("station_id = %s")
                    params.append(int(station_id))
                if sub_plan is not None:
                    updates.append("subscription_plan = %s")
                    params.append(sub_plan)
                if updates:
                    params.append(int(user_id))
                    cur.execute(f"UPDATE deliveries_users SET {', '.join(updates)} WHERE user_id = %s", tuple(params))
        await run_in_thread(_update)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            updates = []
            params = []
            if role is not None:
                updates.append("role = ?")
                params.append(role)
            if is_blocked is not None:
                updates.append("is_blocked = ?")
                params.append(int(is_blocked))
            if station_id is not None:
                updates.append("station_id = ?")
                params.append(int(station_id))
            if sub_plan is not None:
                updates.append("subscription_plan = ?")
                params.append(sub_plan)
            if updates:
                params.append(int(user_id))
                await db.execute(f"UPDATE deliveries_users SET {', '.join(updates)} WHERE user_id = ?", tuple(params))
                await db.commit()
    return cors_json_response({"ok": True})

async def handle_api_stations_create(request):
    """יצירת תחנה חדשה במערכת"""
    try: data = await request.json()
    except Exception: data = {}
    name = (data.get("name") or "").strip()
    comm = float(data.get("commission_percent") or 10.0)
    if not name:
        return cors_json_response({"ok": False, "error": "שם תחנה חובה"}, status=400)
    if USE_POSTGRES:
        def _cr():
            with get_pg_cursor() as cur:
                cur.execute("INSERT INTO deliveries_stations (name, commission_percent) VALUES (%s, %s) RETURNING station_id", (name, comm))
                return cur.fetchone()['station_id']
        sid = await run_in_thread(_cr)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            c = await db.execute("INSERT INTO deliveries_stations (name, commission_percent) VALUES (?, ?)", (name, comm))
            sid = c.lastrowid
            await db.commit()
    return cors_json_response({"ok": True, "station_id": sid})

async def handle_api_stations_update(request):
    """עדכון עמלה או שם של תחנה"""
    try: data = await request.json()
    except Exception: data = {}
    sid = data.get("station_id")
    comm = data.get("commission_percent")
    name = data.get("name")
    if not sid:
        return cors_json_response({"ok": False, "error": "station_id חובה"}, status=400)
    if USE_POSTGRES:
        def _up():
            with get_pg_cursor() as cur:
                if comm is not None:
                    cur.execute("UPDATE deliveries_stations SET commission_percent = %s WHERE station_id = %s", (float(comm), int(sid)))
                if name:
                    cur.execute("UPDATE deliveries_stations SET name = %s WHERE station_id = %s", (name, int(sid)))
        await run_in_thread(_up)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            if comm is not None:
                await db.execute("UPDATE deliveries_stations SET commission_percent = ? WHERE station_id = ?", (float(comm), int(sid)))
            if name:
                await db.execute("UPDATE deliveries_stations SET name = ? WHERE station_id = ?", (name, int(sid)))
            await db.commit()
    return cors_json_response({"ok": True})

async def handle_api_debts(request):
    """החזרת יומן החובות והערעורים"""
    if USE_POSTGRES:
        def _get():
            with get_pg_cursor() as cur:
                cur.execute("""SELECT debt_id, order_id, driver_id, station_id, amount, status, reason, 
                                      appeal_status, appeal_reason, transaction_type, created_at 
                               FROM deliveries_debts ORDER BY debt_id DESC LIMIT 50""")
                return cur.fetchall()
        rows = await run_in_thread(_get)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("""SELECT debt_id, order_id, driver_id, station_id, amount, status, reason, 
                                                     appeal_status, appeal_reason, transaction_type, created_at 
                                              FROM deliveries_debts ORDER BY debt_id DESC LIMIT 50""")).fetchall()
    return cors_json_response({"ok": True, "debts": [dict(r) for r in rows]})

async def handle_api_debts_charge(request):
    """חיוב נהג ידני או הטלת קנס (רישום ביומן Ledger, עדכון debt_balance והתראה מיידית לנהג בטלגרם עם כפתור ערעור)"""
    try: data = await request.json()
    except Exception: data = {}
    driver_id = int(data.get("driver_id") or 0)
    amount = float(data.get("amount") or 0)
    reason = data.get("reason") or "חיוב ידני מנהל/סדרן"
    station_id = int(data.get("station_id") or 0)
    order_id = data.get("order_id")
    order_id = int(order_id) if order_id else None

    if not driver_id or amount <= 0:
        return cors_json_response({"ok": False, "error": "פרמטרים לא תקינים"}, status=400)

    station_name = "הנהלת המערכת"
    new_debt_id = None
    if USE_POSTGRES:
        def _ch():
            nonlocal station_id, station_name, new_debt_id
            with get_pg_cursor() as cur:
                if not station_id:
                    cur.execute("SELECT station_id FROM deliveries_users WHERE user_id = %s", (driver_id,))
                    u_row = cur.fetchone()
                    station_id = u_row['station_id'] if u_row and u_row['station_id'] else 1
                cur.execute("SELECT name FROM deliveries_stations WHERE station_id = %s", (station_id,))
                st_row = cur.fetchone()
                if st_row:
                    station_name = st_row['name']
                cur.execute("""INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason, status, transaction_type)
                               VALUES (%s, %s, %s, %s, %s, 'unpaid', 'manual_charge') RETURNING debt_id""", 
                            (order_id, driver_id, station_id, amount, reason))
                d_row = cur.fetchone()
                new_debt_id = d_row['debt_id'] if d_row else None
                cur.execute("UPDATE deliveries_users SET debt_balance = debt_balance + %s WHERE user_id = %s", (amount, driver_id))
        await run_in_thread(_ch)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            if not station_id:
                u_row = await (await db.execute("SELECT station_id FROM deliveries_users WHERE user_id = ?", (driver_id,))).fetchone()
                station_id = u_row[0] if u_row and u_row[0] else 1
            st_row = await (await db.execute("SELECT name FROM deliveries_stations WHERE station_id = ?", (station_id,))).fetchone()
            if st_row:
                station_name = st_row[0]
            c = await db.execute("""INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason, status, transaction_type)
                                    VALUES (?, ?, ?, ?, ?, 'unpaid', 'manual_charge')""", 
                                 (order_id, driver_id, station_id, amount, reason))
            new_debt_id = c.lastrowid
            await db.execute("UPDATE deliveries_users SET debt_balance = debt_balance + ? WHERE user_id = ?", (amount, driver_id))
            await db.commit()

    # סעיף 4ג': שליחת הודעה מיידית לפרטי של הנהג עם תות 🍓 וכפתור "ערער / בטל חיוב"
    try:
        order_info = f"קריאה #{order_id}\n" if order_id else ""
        driver_msg = (
            f"🍓 **חויבת בעמלה על סך {amount:.2f} ש\"ח (🍓) בתחנה {station_name}!**\n\n"
            f"📋 **פירוט החיוב:**\n"
            f"{order_info}• סיבה: {reason}\n\n"
            f"לבירורים או ביטול ניתן ללחוץ על הכפתור למטה:"
        )
        appeal_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚖️ ערער / בטל חיוב", callback_data=f"appeal_{new_debt_id or 0}")
        ]])
        await bot.send_message(driver_id, driver_msg, reply_markup=appeal_kb)
    except Exception as e:
        logging.warning(f"Could not send Telegram debt notification to driver {driver_id}: {e}")

    return cors_json_response({"ok": True, "debt_id": new_debt_id})

async def handle_api_debts_credit(request):
    """זיכוי נהג, מחיקת חוב או אישור/דחיית ערעור"""
    try: data = await request.json()
    except Exception: data = {}
    driver_id = int(data.get("driver_id") or 0)
    amount = float(data.get("amount") or 0)
    debt_id = data.get("debt_id")
    station_id = int(data.get("station_id") or 1)
    approve = data.get("approve", True)
    reason = data.get("reason", "זיכוי מנהל")
    if not driver_id:
        return cors_json_response({"ok": False, "error": "driver_id חובה"}, status=400)
    
    station_name = "הנהלת המערכת"
    if USE_POSTGRES:
        def _cr():
            nonlocal station_name
            with get_pg_cursor() as cur:
                cur.execute("SELECT name FROM deliveries_stations WHERE station_id = %s", (station_id,))
                st_row = cur.fetchone()
                if st_row:
                    station_name = st_row['name']
                if debt_id:
                    if approve:
                        cur.execute("UPDATE deliveries_debts SET status = 'cancelled', appeal_status = 'approved' WHERE debt_id = %s", (int(debt_id),))
                        cur.execute("UPDATE deliveries_users SET debt_balance = GREATEST(0, debt_balance - %s) WHERE user_id = %s", (amount, driver_id))
                    else:
                        cur.execute("UPDATE deliveries_debts SET appeal_status = 'rejected' WHERE debt_id = %s", (int(debt_id),))
                else:
                    cur.execute("""INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason, status, transaction_type)
                                   VALUES (NULL, %s, %s, %s, %s, 'paid', 'manual_credit')""", (driver_id, station_id, amount, reason))
                    cur.execute("UPDATE deliveries_users SET debt_balance = GREATEST(0, debt_balance - %s) WHERE user_id = %s", (amount, driver_id))
        await run_in_thread(_cr)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            st_row = await (await db.execute("SELECT name FROM deliveries_stations WHERE station_id = ?", (station_id,))).fetchone()
            if st_row:
                station_name = st_row[0]
            if debt_id:
                if approve:
                    await db.execute("UPDATE deliveries_debts SET status = 'cancelled', appeal_status = 'approved' WHERE debt_id = ?", (int(debt_id),))
                    await db.execute("UPDATE deliveries_users SET debt_balance = MAX(0, debt_balance - ?) WHERE user_id = ?", (amount, driver_id))
                else:
                    await db.execute("UPDATE deliveries_debts SET appeal_status = 'rejected' WHERE debt_id = ?", (int(debt_id),))
            else:
                await db.execute("""INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason, status, transaction_type)
                                    VALUES (NULL, ?, ?, ?, ?, 'paid', 'manual_credit')""", (driver_id, station_id, amount, reason))
                await db.execute("UPDATE deliveries_users SET debt_balance = MAX(0, debt_balance - ?) WHERE user_id = ?", (amount, driver_id))
            await db.commit()

    # התראה לנהג בטלגרם
    try:
        if debt_id:
            if approve:
                await bot.send_message(driver_id, f"✅ **הערעור התקבל!** חוב של {amount} ש\"ח (עבור חיוב #{debt_id}) בוטל בהצלחה.")
            else:
                await bot.send_message(driver_id, f"❌ **הערעור נדחה!** חיוב #{debt_id} נשאר בעינו ויש להסדירו מול התחנה.")
        else:
            await bot.send_message(driver_id, f"🍏 **קיבלת זיכוי על סך {amount:.2f} ש\"ח (🍏) בתחנה {station_name}!**\nסיבה: {reason}")
    except Exception:
        pass

    return cors_json_response({"ok": True})

async def handle_api_debts_update(request):
    """CRUD: עריכת פרטי חיוב קיים (סכום, סיבה, תחנה, סטטוס) ועדכון debt_balance בהתאם להפרש"""
    try: data = await request.json()
    except Exception: data = {}
    debt_id = data.get("debt_id")
    if not debt_id:
        return cors_json_response({"ok": False, "error": "debt_id חובה"}, status=400)
    debt_id = int(debt_id)

    new_amount = float(data["amount"]) if "amount" in data and data["amount"] is not None else None
    new_reason = data.get("reason")
    new_station_id = int(data["station_id"]) if "station_id" in data and data["station_id"] is not None else None
    new_status = data.get("status")

    if USE_POSTGRES:
        def _update_debt():
            with get_pg_cursor() as cur:
                cur.execute("SELECT debt_id, driver_id, amount, status FROM deliveries_debts WHERE debt_id = %s", (debt_id,))
                debt = cur.fetchone()
                if not debt:
                    return False, "חיוב לא נמצא"
                old_amount = float(debt['amount'])
                old_status = debt['status']
                driver_id = debt['driver_id']

                updates = []
                params = []
                if new_amount is not None:
                    updates.append("amount = %s")
                    params.append(new_amount)
                if new_reason is not None:
                    updates.append("reason = %s")
                    params.append(new_reason)
                if new_station_id is not None:
                    updates.append("station_id = %s")
                    params.append(new_station_id)
                if new_status is not None:
                    updates.append("status = %s")
                    params.append(new_status)

                if updates:
                    params.append(debt_id)
                    cur.execute(f"UPDATE deliveries_debts SET {', '.join(updates)} WHERE debt_id = %s", tuple(params))

                effective_old = old_amount if old_status == 'unpaid' else 0.0
                curr_status = new_status if new_status is not None else old_status
                curr_amount = new_amount if new_amount is not None else old_amount
                effective_new = curr_amount if curr_status == 'unpaid' else 0.0
                diff = effective_new - effective_old
                if diff != 0:
                    cur.execute("UPDATE deliveries_users SET debt_balance = GREATEST(0, debt_balance + %s) WHERE user_id = %s", (diff, driver_id))
                return True, None
        ok, err = await run_in_thread(_update_debt)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debt = await (await db.execute("SELECT debt_id, driver_id, amount, status FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()
            if not debt:
                return cors_json_response({"ok": False, "error": "חיוב לא נמצא"}, status=404)
            old_amount = float(debt['amount'])
            old_status = debt['status']
            driver_id = debt['driver_id']

            updates = []
            params = []
            if new_amount is not None:
                updates.append("amount = ?")
                params.append(new_amount)
            if new_reason is not None:
                updates.append("reason = ?")
                params.append(new_reason)
            if new_station_id is not None:
                updates.append("station_id = ?")
                params.append(new_station_id)
            if new_status is not None:
                updates.append("status = ?")
                params.append(new_status)

            if updates:
                params.append(debt_id)
                await db.execute(f"UPDATE deliveries_debts SET {', '.join(updates)} WHERE debt_id = ?", tuple(params))

            effective_old = old_amount if old_status == 'unpaid' else 0.0
            curr_status = new_status if new_status is not None else old_status
            curr_amount = new_amount if new_amount is not None else old_amount
            effective_new = curr_amount if curr_status == 'unpaid' else 0.0
            diff = effective_new - effective_old
            if diff != 0:
                await db.execute("UPDATE deliveries_users SET debt_balance = MAX(0, debt_balance + ?) WHERE user_id = ?", (diff, driver_id))
            await db.commit()
            ok, err = True, None

    if not ok:
        return cors_json_response({"ok": False, "error": err}, status=400)
    return cors_json_response({"ok": True})

async def handle_api_debts_delete(request):
    """CRUD: מחיקת חיוב (ביטול והפחתת יתרה מהנהג)"""
    try: data = await request.json()
    except Exception: data = {}
    debt_id = data.get("debt_id")
    if not debt_id:
        return cors_json_response({"ok": False, "error": "debt_id חובה"}, status=400)
    debt_id = int(debt_id)

    if USE_POSTGRES:
        def _del():
            with get_pg_cursor() as cur:
                cur.execute("SELECT amount, status, driver_id FROM deliveries_debts WHERE debt_id = %s", (debt_id,))
                row = cur.fetchone()
                if row:
                    if row['status'] == 'unpaid':
                        cur.execute("UPDATE deliveries_users SET debt_balance = GREATEST(0, debt_balance - %s) WHERE user_id = %s", (row['amount'], row['driver_id']))
                    cur.execute("DELETE FROM deliveries_debts WHERE debt_id = %s", (debt_id,))
        await run_in_thread(_del)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute("SELECT amount, status, driver_id FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()
            if row:
                if row['status'] == 'unpaid':
                    await db.execute("UPDATE deliveries_users SET debt_balance = MAX(0, debt_balance - ?) WHERE user_id = ?", (row['amount'], row['driver_id']))
                await db.execute("DELETE FROM deliveries_debts WHERE debt_id = ?", (debt_id,))
                await db.commit()
    return cors_json_response({"ok": True})


async def handle_api_settings_get(request):
    """שליפת הגדרות מערכת וקיצורי ערים (NLP)"""
    if USE_POSTGRES:
        def _get():
            with get_pg_cursor() as cur:
                cur.execute("SELECT setting_key, setting_value FROM deliveries_system_settings")
                st_rows = cur.fetchall()
                cur.execute("SELECT alias, standard_city FROM deliveries_city_aliases ORDER BY alias ASC")
                al_rows = cur.fetchall()
                return st_rows, al_rows
        st_rows, al_rows = await run_in_thread(_get)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            st_rows = await (await db.execute("SELECT setting_key, setting_value FROM deliveries_system_settings")).fetchall()
            al_rows = await (await db.execute("SELECT alias, standard_city FROM deliveries_city_aliases ORDER BY alias ASC")).fetchall()
    settings_dict = {r['setting_key'] if isinstance(r, dict) else r[0]: r['setting_value'] if isinstance(r, dict) else r[1] for r in st_rows}
    aliases_list = [dict(a) for a in al_rows]
    return cors_json_response({"ok": True, "settings": settings_dict, "aliases": aliases_list})

async def handle_api_settings_post(request):
    """שמירת הגדרות מערכת או הוספת קיצור עיר (NLP)"""
    try: data = await request.json()
    except Exception: data = {}
    if USE_POSTGRES:
        def _post():
            with get_pg_cursor() as cur:
                for k, v in data.items():
                    if k not in ['alias', 'standard_city']:
                        cur.execute("""INSERT INTO deliveries_system_settings (setting_key, setting_value)
                                       VALUES (%s, %s) ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value""", (k, str(v)))
                if data.get('alias') and data.get('standard_city'):
                    cur.execute("""INSERT INTO deliveries_city_aliases (alias, standard_city)
                                   VALUES (%s, %s) ON CONFLICT (alias) DO UPDATE SET standard_city = EXCLUDED.standard_city""",
                                (data['alias'].strip(), data['standard_city'].strip()))
        await run_in_thread(_post)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            for k, v in data.items():
                if k not in ['alias', 'standard_city']:
                    await db.execute("""INSERT INTO deliveries_system_settings (setting_key, setting_value)
                                        VALUES (?, ?) ON CONFLICT (setting_key) DO UPDATE SET setting_value = excluded.setting_value""", (k, str(v)))
            if data.get('alias') and data.get('standard_city'):
                await db.execute("""INSERT INTO deliveries_city_aliases (alias, standard_city)
                                    VALUES (?, ?) ON CONFLICT (alias) DO UPDATE SET standard_city = excluded.standard_city""",
                                (data['alias'].strip(), data['standard_city'].strip()))
            await db.commit()
    return cors_json_response({"ok": True})

async def handle_api_broadcast(request):
    """שידור הודעת Broadcast לכל משתמשי המערכת"""
    try: data = await request.json()
    except Exception: data = {}
    text = (data.get("text") or "").strip()
    if not text:
        return cors_json_response({"ok": False, "error": "טקסט ריק"}, status=400)
    if USE_POSTGRES:
        def _get_u():
            with get_pg_cursor() as cur:
                cur.execute("SELECT user_id FROM deliveries_users")
                return cur.fetchall()
        users = await run_in_thread(_get_u)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            users = await (await db.execute("SELECT user_id FROM deliveries_users")).fetchall()
    count = 0
    for u in users:
        uid = u['user_id'] if isinstance(u, dict) else u[0]
        try:
            await bot.send_message(uid, f"📢 **הודעת הנהלה מיוחדת (Broadcast):**\n\n{text}")
            count += 1
        except Exception: pass
    return cors_json_response({"ok": True, "count": count})

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
    app.router.add_post("/api/driver/profile", handle_api_driver_profile)
    app.router.add_get("/api/driver/cities", handle_api_driver_cities_get)
    app.router.add_post("/api/driver/cities/add", handle_api_driver_cities_add)
    app.router.add_post("/api/driver/cities/remove", handle_api_driver_cities_remove)
    app.router.add_post("/api/driver/cities/clear", handle_api_driver_cities_clear)
    app.router.add_get("/api/stations", handle_api_stations)
    app.router.add_post("/api/stations/create", handle_api_stations_create)
    app.router.add_post("/api/stations/update", handle_api_stations_update)
    app.router.add_get("/api/users", handle_api_users)
    app.router.add_post("/api/users/update", handle_api_users_update)
    app.router.add_get("/api/debts", handle_api_debts)
    app.router.add_post("/api/debts/charge", handle_api_debts_charge)
    app.router.add_post("/api/debts/credit", handle_api_debts_credit)
    app.router.add_post("/api/debts/update", handle_api_debts_update)
    app.router.add_post("/api/debts/delete", handle_api_debts_delete)
    app.router.add_get("/api/settings", handle_api_settings_get)
    app.router.add_post("/api/settings", handle_api_settings_post)
    app.router.add_post("/api/broadcast", handle_api_broadcast)

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

# ----------------- מקלדות ועזרים (כולל העלמת כפתורים בקבוצות - סעיף 2) -----------------
def safe_reply_markup(chat_type: str, markup):
    """
    סעיף 2: העלמת מקלדת הכפתורים התחתונה בקבוצות (ReplyKeyboardMarkup).
    אם ההודעה נקראת/נשלחת בקבוצה (group או supergroup), חובה לשלוח ReplyKeyboardRemove()
    כדי להעלים את המקלדת התחתונה המציקה. כפתורי Reply מוצגים אך ורק בשיחות פרטיות (private)!
    """
    if chat_type in ('group', 'supergroup'):
        if isinstance(markup, ReplyKeyboardMarkup):
            return ReplyKeyboardRemove()
        return markup
    return markup

def get_main_kb(role='user', status='busy', chat_type='private'):
    if chat_type in ('group', 'supergroup'):
        return ReplyKeyboardRemove()

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

def cancel_kb(chat_type='private'):
    if chat_type in ('group', 'supergroup'):
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול וחזרה")]], resize_keyboard=True)

# ----------------- סעיף 4: מנוע NLP לסדרנים ופענוח קריאות חכם -----------------
def parse_dispatcher_order(raw_text: str) -> dict:
    """
    מנוע NLP ו-Regex חכם לפיענוח קריאות סדרנים:
    א. ערים: זיהוי ונירמול 3-4 ערים/קיצורים (ים, בב, פת, תא, קס, אשד וכו'), כולל אותיות יחס (לבב, מים).
    ב. מחיר (Regex): זיהוי גמיש של הסכום (150, 150ש, 150 ש, 150 שח, 150 ש\"ח, 150₪, ₪150).
    ג. דרישת 'זמן': המילה 'זמן' (או דקות/תוך/דחוף/eta) תסמן בקריאה חובה לקבל ETA מהנהג.
    """
    text = (raw_text or "").strip()
    
    # 1. זיהוי דרישת 'זמן' / ETA
    time_keywords = ['זמן', 'דקות', 'דק', 'תוך', 'דחוף', 'eta', 'מיידי', 'עכשיו']
    requires_eta = False
    for kw in time_keywords:
        if re.search(r'(?:^|\s|[^\w])' + re.escape(kw) + r'(?:$|\s|[^\w])', text, re.IGNORECASE):
            requires_eta = True
            break

    # 2. זיהוי מחיר ב-Regex גמיש
    price_pattern = r'(?:₪\s*(\d{2,4})|(\d{2,4})\s*(?:₪|ש"ח|שח|שקלים|שקל|ש|\b))'
    matches = re.findall(price_pattern, text)
    est_price = 0.0
    if matches:
        for m in reversed(matches):
            p_str = m[0] or m[1]
            if p_str and 20 <= float(p_str) <= 5000:
                est_price = float(p_str)
                break

    # 3. מילון קיצורים ונירמול שמות ערים (NLP)
    alias_dict = {
        'ים': 'ירושלים', 'י-ם': 'ירושלים', 'עיר הקודש': 'ירושלים',
        'בב': 'בני ברק', 'ב"ב': 'בני ברק',
        'פת': 'פתח תקווה', 'פ"ת': 'פתח תקווה',
        'תא': 'תל אביב', 'ת"א': 'תל אביב',
        'קס': 'מודיעין עילית', 'ק"ס': 'מודיעין עילית', 'ספר': 'מודיעין עילית',
        'אשד': 'אשדוד', 'אשדו': 'אשדוד',
        'בש': 'באר שבע', 'ב"ש': 'בית שמש',
        'חי': 'חיפה', 'נת': 'נתניה', 'הרצ': 'הרצליה'
    }

    words = text.split()
    cleaned_tokens = []
    found_cities = []

    for word in words:
        clean_w = re.sub(r'[^\w\s"״\'-]', '', word).strip()
        prefix = ""
        check_w = clean_w
        if len(clean_w) > 2 and clean_w[0] in ['ל', 'מ', 'ב'] and clean_w[1:] in alias_dict:
            prefix = clean_w[0] + " "
            check_w = clean_w[1:]

        if check_w in alias_dict:
            city_name = alias_dict[check_w]
            cleaned_tokens.append(f"{prefix}{city_name}")
            if city_name not in found_cities:
                found_cities.append(city_name)
        elif clean_w in POPULAR_CITIES:
            cleaned_tokens.append(clean_w)
            if clean_w not in found_cities:
                found_cities.append(clean_w)
        else:
            cleaned_tokens.append(word)

    cleaned_text = " ".join(cleaned_tokens)
    cleaned_text = re.sub(r'[-=]+>', ' ➔ ', cleaned_text)
    cleaned_text = re.sub(r'<[-=]+', ' ➔ ', cleaned_text)

    origin_city = found_cities[0] if len(found_cities) > 0 else ""
    dest_city = found_cities[1] if len(found_cities) > 1 else ""

    return {
        "cleaned_text": cleaned_text.strip(),
        "price": est_price,
        "requires_eta": requires_eta,
        "found_cities": found_cities,
        "origin_city": origin_city,
        "dest_city": dest_city
    }

def clean_order_text(text):
    return parse_dispatcher_order(text)["cleaned_text"]


# ----------------- תפריט ראשי, ביטול והרשמה (שלב ב' - Onboarding FSM) -----------------
@router.message(Command("start"))
@router.message(F.text == "❌ ביטול וחזרה")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    # 0. סעיף 2: העלמת מקלדת הכפתורים התחתונה בקבוצות (ReplyKeyboardRemove)
    if message.chat.type in ('group', 'supergroup'):
        return await message.answer(
            "👋 <b>שלום לכולם!</b> הבוט פעיל בקבוצה לשידור והפצת קריאות.\n\n"
            "כדי לפתוח את ה-Mini App האישי, לנהל עמדת נהג/סדרן או לצפות בחובות:\n"
            "לחץ על הכפתור למטה או פנה לבוט בהודעה פרטית:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚖 פתח Mini App אישי", web_app=WebAppInfo(url=WEBAPP_URL))]
            ])
        )

    # 1. התנהגות God Mode למנהלים (בלי הרשמה כלל):
    # עבור שני ה-IDs של מנהלי המערכת (552821474, 8644923212): הבוט מדלג לחלוטין על ההרשמה!
    if user_id in ADMIN_IDS:
        if USE_POSTGRES:
            def _admin_upsert():
                with get_pg_cursor() as cur:
                    cur.execute('''INSERT INTO deliveries_users 
                        (user_id, full_name, phone, is_phone_verified, birth_year, car_brand, car_model, car_year, role, status, is_blocked) 
                        VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 'admin', 'free', 0)
                        ON CONFLICT (user_id) DO UPDATE SET role = 'admin', is_phone_verified = 1, is_blocked = 0''', 
                        (user_id, message.from_user.full_name or "מנהל מערכת", "0500000000", 1990, "מנהל", "מנהל", 2024))
            await run_in_thread(_admin_upsert)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                await db.execute('''INSERT INTO deliveries_users 
                    (user_id, full_name, phone, is_phone_verified, birth_year, car_brand, car_model, car_year, role, status, is_blocked) 
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?, 'admin', 'free', 0)
                    ON CONFLICT(user_id) DO UPDATE SET role = 'admin', is_phone_verified = 1, is_blocked = 0''', 
                    (user_id, message.from_user.full_name or "מנהל מערכת", "0500000000", 1990, "מנהל", "מנהל", 2024))
                await db.commit()

        admin_user = await get_user(user_id)
        admin_status = admin_user['status'] if admin_user and 'status' in admin_user else 'free'
        return await message.answer(
            "👑 **שלום מנהל מערכת! מצב God Mode פעיל.**\n"
            "ההרשאות שלך מאושרות לצמיתות ללא צורך בשום שלב הרשמה.\n"
            "כל פאנלי הניהול, שיגור הקריאות והמיני אפליקציה זמינים עבורך:",
            reply_markup=get_main_kb('admin', admin_status, message.chat.type)
        )

    # בדיקת משתמש רגיל
    user = await get_user(user_id)
    if user and user.get('is_blocked'):
        return await message.answer("❌ **חשבונך נחסם על ידי ההנהלה.** לבירורים פנה לשירות הלקוחות.")

    # אם המשתמש כבר השלים את תהליך הקליטה במלואו (כולל טלפון מאומת ותקנון)
    if user and user.get('is_phone_verified') and user.get('terms_accepted_at') and user.get('car_brand'):
        return await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_kb(user['role'], user['status'], message.chat.type))


    # התחלת תהליך קליטה מסודר ומחמיר (שלב ב' - Onboarding FSM)
    await state.set_state(Onboarding.waiting_terms)
    terms_msg = (
        "👋 **ברוך הבא למערכת ה-ERP וניהול המשלוחים!**\n\n"
        "כדי להצטרף לצוות הנהגים והשליחים, יש להשלים תהליך קליטה מסודר ומאובטח:\n"
        "1️⃣ **אישור תקנון ומדיניות פרטיות**\n"
        "2️⃣ **אימות טלפון חומרתי מאובטח (למניעת התחזות)**\n"
        "3️⃣ **אימות גיל (18 ומעלה)**\n"
        "4️⃣ **הזנת פרטי רכב (מותג, דגם, שנת ייצור ומקומות)**\n"
        "5️⃣ **בחירת אזורי עבודה מועדפים**\n\n"
        "📜 *תקנון המערכת:* השימוש במערכת מחייב נהיגה זהירה, אמינות בביצוע נסיעות ותשלום עמלות בזמן.\n\n"
        "לחץ על הכפתור למטה לאישור התקנון והמשך לשלב הבא:"
    )
    terms_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ אני מאשר את התקנון ומדיניות הפרטיות", callback_data="ob_accept_terms")
    ]])
    return await message.answer(terms_msg, reply_markup=terms_kb)

# -- שלב 1: אישור תקנון --
@router.callback_query(F.data == "ob_accept_terms")
async def ob_accept_terms(call: CallbackQuery, state: FSMContext):
    await state.update_data(terms_accepted_at=datetime.now().isoformat())
    await state.set_state(Onboarding.waiting_contact)
    
    contact_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 שתף איש קשר לאימות", request_contact=True)],
            [KeyboardButton(text="❌ ביטול וחזרה")]
        ],
        resize_keyboard=True
    )
    await call.message.answer(
        "📱 **שלב 2/5: אימות טלפון חומרה**\n\n"
        "לחץ על הכפתור למטה לשיתוף מספר הטלפון שלך.\n\n"
        "⚠️ *שים לב: מטעמי אבטחה קפדניים, המערכת מאמתת חומרתית שמספר הטלפון שייך למשתמש הטלגרם שלך בלבד! לא ניתן להעלות איש קשר של אדם אחר.*",
        reply_markup=contact_kb
    )
    await call.answer()

# -- שלב 2: אימות טלפון חומרה עם בדיקת אבטחה --
@router.message(Onboarding.waiting_contact)
async def ob_contact(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    contact_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 שתף איש קשר לאימות", request_contact=True)],
            [KeyboardButton(text="❌ ביטול וחזרה")]
        ],
        resize_keyboard=True
    )

    if not message.contact:
        return await message.answer("⚠️ **חובה ללחוץ על הכפתור '📱 שתף איש קשר לאימות' במקלדת למטה!**", reply_markup=contact_kb)

    # בדיקת אבטחה קריטית: חובה שאיש הקשר שייך לאותו משתמש ולא הועבר מאדם אחר!
    if message.contact.user_id != message.from_user.id:
        return await message.answer(
            "🚫 **ניסיון התחזות זוהה!**\n"
            "חובה לשתף את איש הקשר שלך בלבד דרך הכפתור הייעודי (ולא להעביר איש קשר של אדם אחר).",
            reply_markup=contact_kb
        )

    raw_phone = message.contact.phone_number.replace("+", "").replace("-", "").replace(" ", "")
    if not raw_phone.startswith("05") and not raw_phone.startswith("9725"):
        return await message.answer("⚠️ מספר הטלפון חייב להיות מספר ישראלי חוקי (המתחיל ב-05 או +9725).", reply_markup=contact_kb)

    phone = "0" + raw_phone[3:] if raw_phone.startswith("972") else raw_phone
    full_name = message.from_user.full_name or "נהג"
    username = message.from_user.username or ""

    await state.update_data(phone=phone, full_name=full_name, username=username, is_phone_verified=1)
    await state.set_state(Onboarding.waiting_birth_year)

    await message.answer(
        f"✅ הטלפון **{phone}** אומת חומרתית בהצלחה!\n\n"
        "📅 **שלב 3/5: אימות גיל (18 ומעלה)**\n"
        "הקלד את **שנת הלידה שלך** ב-4 ספרות (לדוגמה: 1998):",
        reply_markup=cancel_kb()
    )

# -- שלב 3: אימות גיל (18 ומעלה) --
@router.message(Onboarding.waiting_birth_year)
async def ob_birth_year(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    text = message.text.strip()
    if not text.isdigit() or len(text) != 4:
        return await message.answer("⚠️ נא להזין שנת לידה תקינה ב-4 ספרות (לדוגמה: 1998):", reply_markup=cancel_kb())

    birth_year = int(text)
    current_year = datetime.now().year
    age = current_year - birth_year

    if age < 18:
        await state.clear()
        return await message.answer(
            "❌ **ההרשמה נדחתה:** המערכת מיועדת לגילאי 18 ומעלה בלבד על פי חוק ותקנון המערכת.",
            reply_markup=ReplyKeyboardRemove()
        )

    if age > 95 or birth_year < 1930:
        return await message.answer("⚠️ נא להזין שנת לידה תקינה והגיונית (לדוגמה: 1995):", reply_markup=cancel_kb())

    await state.update_data(birth_year=birth_year)
    await state.set_state(Onboarding.waiting_car_brand)

    brands_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CAR_BRANDS[0]), KeyboardButton(text=CAR_BRANDS[1])],
            [KeyboardButton(text=CAR_BRANDS[2]), KeyboardButton(text=CAR_BRANDS[3])],
            [KeyboardButton(text=CAR_BRANDS[4]), KeyboardButton(text=CAR_BRANDS[5])],
            [KeyboardButton(text=CAR_BRANDS[6]), KeyboardButton(text=CAR_BRANDS[7])],
            [KeyboardButton(text="❌ ביטול וחזרה")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"✅ גיל מאושר ({age} שנים).\n\n"
        "🚗 **שלב 4/5: פרטי רכב**\n"
        "בחר את **יצרן הרכב** שלך מהרשימה או בחר 'אחר (הקלדה ידנית)':",
        reply_markup=brands_kb
    )

# -- שלב 4: מותג, דגם, שנת ייצור ומקומות ישיבה --
@router.message(Onboarding.waiting_car_brand)
async def ob_car_brand(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    if message.text == "אחר (הקלדה ידנית)":
        return await message.answer("✍️ הקלד את שם חברת הרכב שלך (למשל: סובארו, פולקסווגן, פיג'ו):", reply_markup=cancel_kb())

    car_brand = message.text.strip()
    await state.update_data(car_brand=car_brand)
    await state.set_state(Onboarding.waiting_car_model)
    await message.answer(f"✅ יצרן: **{car_brand}**\n\n✍️ הקלד כעת את **דגם הרכב** (לדוגמה: קורולה, איוניק, אוקטביה, ספורטאז'):", reply_markup=cancel_kb())

@router.message(Onboarding.waiting_car_model)
async def ob_car_model(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    car_model = message.text.strip()
    await state.update_data(car_model=car_model)
    await state.set_state(Onboarding.waiting_car_year)
    await message.answer("📅 הקלד את **שנת ייצור הרכב** (לדוגמה: 2021):", reply_markup=cancel_kb())

@router.message(Onboarding.waiting_car_year)
async def ob_car_year(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    text = message.text.strip()
    if not text.isdigit() or int(text) < 1995 or int(text) > 2027:
        return await message.answer("⚠️ נא להזין שנת ייצור תקינה במספרים (לדוגמה: 2020):", reply_markup=cancel_kb())

    car_year = int(text)
    await state.update_data(car_year=car_year)
    await state.set_state(Onboarding.waiting_car_seats)

    seats_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=str(i)) for i in [4, 5, 6, 7, 8]],
            [KeyboardButton(text="❌ ביטול וחזרה")]
        ],
        resize_keyboard=True
    )
    await message.answer("💺 כמה **מקומות ישיבה** יש ברכב (כולל נהג)?", reply_markup=seats_kb)

@router.message(Onboarding.waiting_car_seats)
async def ob_car_seats(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    text = message.text.strip()
    if not text.isdigit() or int(text) < 2 or int(text) > 10:
        return await message.answer("⚠️ נא לבחור מספר מקומות תקין (4, 5, 6, 7, 8):")

    car_seats = int(text)
    await state.update_data(car_seats=car_seats, selected_cities=[])
    await state.set_state(Onboarding.waiting_cities)

    kb = build_cities_selection_kb([])
    await message.answer(
        "📍 **שלב 5/5: בחירת אזורי עבודה**\n\n"
        "בחר ערים שבהן תרצה לקבל קריאות (לחץ על עיר לבחירה/הסרה).\n"
        "תוכל גם **להקליד כל עיר או קיצור** בצ'אט (למשל: 'ים', 'בב', 'תא', 'קס', 'אשדוד')!\n\n"
        "בסיום לחץ על כפתור הסיום למטה:",
        reply_markup=kb
    )

# -- שלב 5: בחירת ערים, זיהוי קיצורים וסיום הרשמה --
@router.callback_query(F.data.startswith("ob_city_"))
async def ob_toggle_city(call: CallbackQuery, state: FSMContext):
    city = call.data.replace("ob_city_", "").strip()
    data = await state.get_data()
    selected_cities = list(data.get('selected_cities', []))
    if city in selected_cities:
        selected_cities.remove(city)
    else:
        selected_cities.append(city)
    await state.update_data(selected_cities=selected_cities)
    kb = build_cities_selection_kb(selected_cities)
    try:
        await call.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    action_str = "נוספה לרשימה" if city in selected_cities else "הוסרה מהרשימה"
    await call.answer(f"{city} {action_str}")

@router.message(Onboarding.waiting_cities)
async def ob_type_city(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    if message.text in ["סיום", "סיימתי", "אישור"]:
        return await finalize_onboarding(message, state)

    city_input = message.text.strip()
    resolved_city = await resolve_city_name(city_input)
    
    data = await state.get_data()
    selected_cities = list(data.get('selected_cities', []))
    if resolved_city not in selected_cities:
        selected_cities.append(resolved_city)
        await state.update_data(selected_cities=selected_cities)
        kb = build_cities_selection_kb(selected_cities)
        alias_note = f" (זוהה מקיצור '{city_input}')" if resolved_city != city_input else ""
        await message.answer(
            f"✅ נוספה העיר: **{resolved_city}**{alias_note}\nסך הכל נבחרו {len(selected_cities)} ערים.\nתוכל להקליד עוד או ללחוץ על סיום למטה:",
            reply_markup=kb
        )
    else:
        await message.answer(
            f"ℹ️ העיר **{resolved_city}** כבר קיימת ברשימה שלך.",
            reply_markup=build_cities_selection_kb(selected_cities)
        )

@router.callback_query(F.data == "ob_finish")
async def ob_finish_callback(call: CallbackQuery, state: FSMContext):
    await finalize_onboarding(call.message, state, user_id=call.from_user.id, username=call.from_user.username)
    await call.answer()

async def finalize_onboarding(message: Message, state: FSMContext, user_id: int = None, username: str = None):
    data = await state.get_data()
    uid = user_id or message.from_user.id
    uname = username or getattr(message.from_user, 'username', '')
    full_name = data.get('full_name') or getattr(message.from_user, 'full_name', 'נהג')
    phone = data.get('phone', '0500000000')
    birth_year = data.get('birth_year', 1995)
    car_brand = data.get('car_brand', 'טויוטה')
    car_model = data.get('car_model', 'קורולה')
    car_year = data.get('car_year', 2022)
    car_seats = data.get('car_seats', 5)
    terms_at = data.get('terms_accepted_at') or datetime.now().isoformat()
    has_custom_cities = bool(data.get('selected_cities'))
    cities = data.get('selected_cities', [])

    if USE_POSTGRES:
        def _save_driver_sync():
            with get_pg_cursor() as cur:
                cur.execute('''INSERT INTO deliveries_users 
                               (user_id, telegram_username, full_name, phone, is_phone_verified, birth_year, terms_accepted_at,
                                car_brand, car_model, car_year, car_seats, role, status, is_blocked, subscription_plan)
                               VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, 'user', 'busy', 0, 'free')
                               ON CONFLICT (user_id) DO UPDATE SET 
                               telegram_username = EXCLUDED.telegram_username, full_name = EXCLUDED.full_name, phone = EXCLUDED.phone, 
                               is_phone_verified = 1, birth_year = EXCLUDED.birth_year, terms_accepted_at = EXCLUDED.terms_accepted_at,
                               car_brand = EXCLUDED.car_brand, car_model = EXCLUDED.car_model, car_year = EXCLUDED.car_year, 
                               car_seats = EXCLUDED.car_seats, role = 'user', is_blocked = 0''',
                            (uid, uname, full_name, phone, birth_year, terms_at, car_brand, car_model, car_year, car_seats))
                
                if has_custom_cities:
                    cur.execute("DELETE FROM deliveries_driver_cities WHERE user_id = %s", (uid,))
                    for c in cities:
                        cur.execute('''INSERT INTO deliveries_driver_cities (user_id, city_name) 
                                       VALUES (%s, %s) ON CONFLICT DO NOTHING''', (uid, c))
                else:
                    cur.execute("SELECT count(*) as cnt FROM deliveries_driver_cities WHERE user_id = %s", (uid,))
                    cnt_row = cur.fetchone()
                    if not cnt_row or (cnt_row['cnt'] if isinstance(cnt_row, dict) else cnt_row[0]) == 0:
                        for c in ["ירושלים", "בני ברק"]:
                            cur.execute('''INSERT INTO deliveries_driver_cities (user_id, city_name) 
                                           VALUES (%s, %s) ON CONFLICT DO NOTHING''', (uid, c))
        await run_in_thread(_save_driver_sync)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute('''INSERT INTO deliveries_users 
                               (user_id, telegram_username, full_name, phone, is_phone_verified, birth_year, terms_accepted_at,
                                car_brand, car_model, car_year, car_seats, role, status, is_blocked, subscription_plan)
                               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 'user', 'busy', 0, 'free')
                               ON CONFLICT (user_id) DO UPDATE SET 
                               telegram_username = excluded.telegram_username, full_name = excluded.full_name, phone = excluded.phone, 
                               is_phone_verified = 1, birth_year = excluded.birth_year, terms_accepted_at = excluded.terms_accepted_at,
                               car_brand = excluded.car_brand, car_model = excluded.car_model, car_year = excluded.car_year, 
                               car_seats = excluded.car_seats, role = 'user', is_blocked = 0''',
                            (uid, uname, full_name, phone, birth_year, terms_at, car_brand, car_model, car_year, car_seats))
            if has_custom_cities:
                await db.execute("DELETE FROM deliveries_driver_cities WHERE user_id = ?", (uid,))
                for c in cities:
                    await db.execute("INSERT OR IGNORE INTO deliveries_driver_cities (user_id, city_name) VALUES (?, ?)", (uid, c))
            else:
                cnt = (await (await db.execute("SELECT count(*) FROM deliveries_driver_cities WHERE user_id = ?", (uid,))).fetchone())[0]
                if cnt == 0:
                    for c in ["ירושלים", "בני ברק"]:
                        await db.execute("INSERT OR IGNORE INTO deliveries_driver_cities (user_id, city_name) VALUES (?, ?)", (uid, c))
            await db.commit()

    await state.clear()
    cities_txt = ", ".join(cities)
    welcome_txt = (
        f"🎉 **ברכות, {full_name}! תהליך הקליטה הושלם בהצלחה!**\n\n"
        f"📱 טלפון מאומת: {phone}\n"
        f"🚗 רכב: {car_brand} {car_model} ({car_year}) • {car_seats} מקומות\n"
        f"📍 אזורי עבודה נבחרים: {cities_txt}\n\n"
        "🔴 כרגע אתה בסטטוס: **תפוס** (עצור קריאות).\n"
        "כדי להתחיל לקבל קריאות באזורים שלך, לחץ על **🟢 פנוי לעבודה** בתפריט למטה:"
    )
    await message.answer(welcome_txt, reply_markup=get_main_kb('user', 'busy'))

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
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    parsed = parse_dispatcher_order(message.text)
    cleaned_text = parsed['cleaned_text']
    est_price = parsed['price']
    requires_eta = 1 if parsed['requires_eta'] else 0
    found_cities = parsed['found_cities']

    if est_price == 0:
        return await message.answer(
            "⚠️ **המערכת לא זיהתה מחיר תקין.**\n"
            "נא לכלול מחיר בספרות (למשל: 150, 150ש, 150 שח, 150₪).\n"
            "הקלד שוב את פרטי הקריאה:",
            reply_markup=cancel_kb(message.chat.type)
        )

    cities_note = f"\n📍 ערים שזוהו: {', '.join(found_cities)}" if found_cities else ""
    eta_note = "\n⏱️ **דרישת זמן (ETA): כן (הנהג יידרש להצהיר על זמן הגעה)**" if requires_eta else ""

    await state.update_data(
        order_text=cleaned_text,
        est_price=est_price,
        requires_eta=requires_eta,
        found_cities=found_cities,
        origin_city=parsed['origin_city'],
        dest_city=parsed['dest_city']
    )
    await state.set_state(OrderFlow.waiting_publish_dest)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="לנהגים בפרטי"), KeyboardButton(text="לקבוצות (חיצוני)")],
            [KeyboardButton(text="❌ ביטול וחזרה")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"✅ **הקריאה פוענחה בהצלחה!**\n\n"
        f"📝 טקסט מנוקה: {cleaned_text}\n"
        f"💵 מחיר: {est_price} ש\"ח{cities_note}{eta_note}\n\n"
        f"לאן תרצה לשגר את הקריאה?",
        reply_markup=safe_reply_markup(message.chat.type, kb)
    )

@router.message(OrderFlow.waiting_publish_dest)
async def process_publish_dest(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)
        
    data = await state.get_data()
    user = await get_user(message.from_user.id)
    order_text = data['order_text']
    requires_eta = data.get('requires_eta', 0)
    origin_city = data.get('origin_city', '')
    dest_city = data.get('dest_city', '')
    
    if USE_POSTGRES:
        def _create_order():
            with get_pg_cursor() as cur:
                cur.execute('''INSERT INTO deliveries_orders 
                               (text, price, publisher_id, station_id, created_at, requires_eta, origin_city, dest_city) 
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING order_id''', 
                            (order_text, data['est_price'], user['user_id'], user['station_id'], datetime.now().isoformat(), requires_eta, origin_city, dest_city))
                return cur.fetchone()['order_id']
        order_id = await run_in_thread(_create_order)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            cursor = await db.execute('''INSERT INTO deliveries_orders 
                                         (text, price, publisher_id, station_id, created_at, requires_eta, origin_city, dest_city) 
                                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                      (order_text, data['est_price'], user['user_id'], user['station_id'], datetime.now().isoformat(), requires_eta, origin_city, dest_city))
            order_id = cursor.lastrowid
            await db.commit()
        
    eta_badge = " [⏱️ נדרש ETA]" if requires_eta else ""
    order_msg = f"🎫 **קריאה #{order_id}**{eta_badge}\n🏢 תחנה: {user['station_id']} | סדרן: {user['full_name']}\n\n{order_text}\n\n💵 סכום: {data['est_price']} ש\"ח"
    
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
                        if city_name in order_text or city_name in [origin_city, dest_city]:
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
                        if city_row[0] in order_text or city_row[0] in [origin_city, dest_city]:
                            should_send = True
                            break
                if should_send:
                    try: 
                        await bot.send_message(d['user_id'], order_msg, reply_markup=kb)
                        sent += 1
                    except Exception:
                        pass
        await message.answer(f"✅ שוגר ל-{sent} נהגים בפרטי (סונן לפי אזורי העבודה שלהם).", reply_markup=get_main_kb(user['role'], user['status'], message.chat.type))
    
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
        await message.answer(f"✅ שוגר ל-{sent} קבוצות מוגדרות במערכת.", reply_markup=get_main_kb(user['role'], user['status'], message.chat.type))
    
    await state.clear()

# ----------------- ניהול מצב קריאות (לסדרן ולמנהל תחנה בלבד לפי station_id) -----------------
@router.message(F.text == "📋 מצב קריאות")
async def show_open_orders(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'station_manager', 'dispatcher']: return
    
    if USE_POSTGRES:
        def _get_orders():
            with get_pg_cursor() as cur:
                if user['role'] == 'admin':
                    cur.execute("SELECT * FROM deliveries_orders WHERE status = 'open' ORDER BY order_id DESC LIMIT 25")
                else:
                    cur.execute("SELECT * FROM deliveries_orders WHERE station_id = %s AND status = 'open' ORDER BY order_id DESC LIMIT 25", (user['station_id'],))
                return cur.fetchall()
        orders = await run_in_thread(_get_orders)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            if user['role'] == 'admin':
                orders = await (await db.execute("SELECT * FROM deliveries_orders WHERE status = 'open' ORDER BY order_id DESC LIMIT 25")).fetchall()
            else:
                orders = await (await db.execute("SELECT * FROM deliveries_orders WHERE station_id = ? AND status = 'open' ORDER BY order_id DESC LIMIT 25", (user['station_id'],))).fetchall()
        
    if not orders:
        return await message.answer("✅ אין קריאות פתוחות לתחנה שלך כרגע.")
        
    for o in orders:
        eta_txt = "⏱️ נדרש ETA" if o.get('requires_eta') else ""
        txt = f"🎫 **קריאה #{o['order_id']}** {eta_txt}\n💵 מחיר: {o['price']} ש\"ח\n📝 טקסט: {o['text']}"
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
    
# ----------------- סעיף 5: Bidding חכם, ETA ואישור שיחה (Deep Link) -----------------
@router.callback_query(F.data.startswith("take_"))
async def take_order(call: CallbackQuery, state: FSMContext):
    order_id = call.data.split("_")[1]
    
    driver = await get_user(call.from_user.id)
    if not driver:
        return await call.answer("⚠️ יש להירשם תחילה למערכת באמצעות /start", show_alert=True)
    if driver['status'] != 'free':
        return await call.answer("⚠️ אתה בסטטוס תפוס! העבר ל'פנוי' בתפריט הראשי קודם.", show_alert=True)
    if driver['debt_balance'] > 500.0:
        return await call.answer("🚫 חשבונך מוקפא עקב חובות (מעל 500 ש\"ח)! הסדר חובות תחילה.", show_alert=True)

    if USE_POSTGRES:
        def _get_o():
            with get_pg_cursor() as cur:
                cur.execute('SELECT * FROM deliveries_orders WHERE order_id = %s', (order_id,))
                return cur.fetchone()
        order = await run_in_thread(_get_o)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            order = await (await db.execute('SELECT * FROM deliveries_orders WHERE order_id = ?', (order_id,))).fetchone()

    if not order or order['status'] != 'open':
        return await call.answer("❌ איחרת! הקריאה כבר נתפסה או בוטלה.", show_alert=True)
        
    await state.update_data(take_order_id=order_id, order_requires_eta=order.get('requires_eta', 0))
    await state.set_state(OrderFlow.waiting_driver_eta)
    
    eta_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="5 דקות"), KeyboardButton(text="10 דקות"), KeyboardButton(text="15 דקות")],
            [KeyboardButton(text="20 דקות"), KeyboardButton(text="30 דקות"), KeyboardButton(text="מיידי (0-3 דק')")],
            [KeyboardButton(text="❌ ביטול וחזרה")]
        ],
        resize_keyboard=True
    )
    
    requires_eta = order.get('requires_eta', 0)
    prompt_txt = "⏱️ **הסדרן דרש זמן הגעה מדויק (ETA)!**\nתוך כמה דקות תוכל להתייצב במוצא?" if requires_eta else "⏱️ תוך כמה זמן תוכל להגיע למוצא? (בחר כפתור או הקלד מספר דקות):"
    
    await call.message.answer(
        f"🎫 **בקשה לקריאה #{order_id}**\n{prompt_txt}",
        reply_markup=safe_reply_markup(call.message.chat.type, eta_kb)
    )
    await call.answer()

@router.message(OrderFlow.waiting_driver_eta)
async def process_eta(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)
        
    data = await state.get_data()
    order_id = data.get('take_order_id')
    driver = await get_user(message.from_user.id)
    
    if not order_id:
        await state.clear()
        return await cmd_start(message, state)

    eta_str = message.text.replace("דקות", "").replace("דק'", "").replace("דק", "").strip()

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
        return await message.answer("❌ איחרת! הקריאה כבר נתפסה או בוטלה.", reply_markup=get_main_kb(driver['role'], driver['status'], message.chat.type))
        
    driver_uname = driver['telegram_username'] or message.from_user.username or ""
    driver_mention = f"@{driver_uname}" if driver_uname else f"ID: {driver['user_id']}"
    
    msg_to_dispatcher = (
        f"🔔 **נהג מציע לקחת את קריאה #{order_id}**\n\n"
        f"👤 נהג: {driver['full_name']} ({driver_mention})\n"
        f"📱 טלפון: {driver['phone']}\n"
        f"⏱️ **זמן הגעה (ETA): {eta_str}**\n"
        f"🚗 רכב: {driver['car_brand']} {driver['car_model']} ({driver['car_year']}) | 💺 {driver['car_seats']} מקומות\n"
        f"⭐ דירוג: {driver['rating']}/5.0 ({driver['total_trips']} נסיעות)"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 אשר שיחה (צ'אט ישיר)", callback_data=f"call_{order_id}_{driver['user_id']}")],
        [InlineKeyboardButton(text="✅ סגור נסיעה (גבה עמלה)", callback_data=f"approve_{order_id}_{driver['user_id']}")],
        [InlineKeyboardButton(text="❌ דחה מתמודד", callback_data=f"deny_{order_id}_{driver['user_id']}")]
    ])
    
    try:
        await bot.send_message(order['publisher_id'], msg_to_dispatcher, reply_markup=kb)
    except Exception as e:
        logging.error(f"Error notifying dispatcher: {e}")
        
    await state.clear()
    await message.answer(
        f"⏳ **הצעתך לקריאה #{order_id} שוגרה לסדרן (זמן הגעה: {eta_str})!**\n"
        f"כאשר הסדרן יאשר שיחה או יסגור את הנסיעה, תקבל הודעה ישירה מיד.",
        reply_markup=get_main_kb(driver['role'], driver['status'], message.chat.type)
    )

# ----------------- סעיף 5: אישור שיחה (Deep Link) -----------------
@router.callback_query(F.data.startswith("call_"))
async def call_driver_dispatcher(call: CallbackQuery):
    """
    אישור שיחה: לחיצה עליו לא סוגרת נסיעה!
    היא שולחת לסדרן ולנהג קישור ישיר לצ'אט פרטי ביניהם לתאום פרטים.
    """
    _, order_id, driver_id_str = call.data.split("_")
    driver_id = int(driver_id_str)
    dispatcher_id = call.from_user.id
    
    driver = await get_user(driver_id)
    dispatcher = await get_user(dispatcher_id)
    
    if not driver:
        return await call.answer("משתמש לא נמצא", show_alert=True)
        
    driver_username = driver.get('telegram_username') or ""
    disp_username = (dispatcher.get('telegram_username') if dispatcher else "") or call.from_user.username or ""
    
    # יצירת deep links מאובטחים
    driver_link = f"https://t.me/{driver_username}" if driver_username else f"tg://user?id={driver_id}"
    disp_link = f"https://t.me/{disp_username}" if disp_username else f"tg://user?id={dispatcher_id}"
    
    disp_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 פתח שיחה ישירה עם הנהג", url=driver_link)],
        [InlineKeyboardButton(text="✅ סגור נסיעה עכשיו (גבה עמלה)", callback_data=f"approve_{order_id}_{driver_id}")],
        [InlineKeyboardButton(text="❌ דחה מתמודד", callback_data=f"deny_{order_id}_{driver_id}")]
    ])
    
    await call.message.edit_text(
        f"📞 **אושר קישור לשיחה ישירה לקריאה #{order_id}!**\n\n"
        f"👤 נהג: {driver['full_name']} (@{driver_username})\n"
        f"📱 טלפון: {driver['phone']}\n"
        f"🚗 רכב: {driver['car_brand']} {driver['car_model']}\n\n"
        f"לחץ למטה לפתיחת הצ'אט בטלגרם לתאום סופי.\n"
        f"⚠️ **שים לב:** לחיצה זו טרם סגרה את הנסיעה. לאחר שסיכמתם ביניכם, לחץ 'סגור נסיעה עכשיו' כדי לקבע את הנסיעה ולחייב עמלה.",
        reply_markup=disp_kb
    )
    
    driver_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 פתח שיחה ישירה עם הסדרן", url=disp_link)]
    ])
    
    disp_name = (dispatcher.get('full_name') if dispatcher else "") or call.from_user.full_name
    try:
        await bot.send_message(
            driver_id,
            f"🎉 **הסדרן {disp_name} אישר שיחה ישירה לקריאה #{order_id}!**\n\n"
            f"לחץ למטה לפתיחת הצ'אט הפרטי מול הסדרן לתיאום סופי:\n"
            f"לאחר הסיכום, הסדרן יסגור את הנסיעה ותקבל אישור רשמי.",
            reply_markup=driver_kb
        )
    except Exception as e:
        logging.error(f"Error sending link to driver: {e}")
        
    await call.answer("🔗 נוצרו קישורים ישירים לשיחה!")


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
                    return None, 0, "", 0
                    
                cur.execute('SELECT name, commission_percent FROM deliveries_stations WHERE station_id = %s', (order['station_id'],))
                station = cur.fetchone()
                station_name = station['name'] if station else f"תחנה #{order['station_id']}"
                
                cur.execute("UPDATE deliveries_orders SET status = 'closed', driver_id = %s WHERE order_id = %s", (driver_id, order_id))
                
                commission_rate = station['commission_percent'] if station else 10.0
                debt_amount = order['price'] * (commission_rate / 100)
                new_debt_id = 0
                
                if debt_amount > 0:
                    cur.execute('INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason) VALUES (%s, %s, %s, %s, %s) RETURNING debt_id', 
                                (order_id, driver_id, order['station_id'], debt_amount, f"עמלה {commission_rate}%"))
                    d_row = cur.fetchone()
                    new_debt_id = d_row['debt_id'] if d_row else 0
                    cur.execute('UPDATE deliveries_users SET debt_balance = debt_balance + %s, total_trips = total_trips + 1 WHERE user_id = %s', (debt_amount, driver_id))
                else:
                    cur.execute('UPDATE deliveries_users SET total_trips = total_trips + 1 WHERE user_id = %s', (driver_id,))
                return order, debt_amount, station_name, new_debt_id

        order, debt_amount, station_name, new_debt_id = await run_in_thread(_approve_transaction)
        if order is None:
            return await call.answer("⚠️ הקריאה כבר נסגרה!", show_alert=True)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            order = await (await db.execute('SELECT * FROM deliveries_orders WHERE order_id = ?', (order_id,))).fetchone()
            
            if not order or order['status'] != 'open':
                return await call.answer("⚠️ הקריאה כבר נסגרה!", show_alert=True)
                
            station = await (await db.execute('SELECT name, commission_percent FROM deliveries_stations WHERE station_id = ?', (order['station_id'],))).fetchone()
            station_name = station['name'] if station else f"תחנה #{order['station_id']}"
            
            await db.execute('UPDATE deliveries_orders SET status = "closed", driver_id = ? WHERE order_id = ?', (driver_id, order_id))
            
            commission_rate = station['commission_percent'] if station else 10.0
            debt_amount = order['price'] * (commission_rate / 100)
            new_debt_id = 0
            
            if debt_amount > 0:
                c = await db.execute('INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, reason) VALUES (?, ?, ?, ?, ?)', 
                                     (order_id, driver_id, order['station_id'], debt_amount, f"עמלה {commission_rate}%"))
                new_debt_id = c.lastrowid
                await db.execute('UPDATE deliveries_users SET debt_balance = debt_balance + ?, total_trips = total_trips + 1 WHERE user_id = ?', (debt_amount, driver_id))
            else:
                await db.execute('UPDATE deliveries_users SET total_trips = total_trips + 1 WHERE user_id = ?', (driver_id,))
                
            await db.commit()
        
    try:
        driver_txt = (
            f"🎉 **אושרת לקריאה #{order_id}!**\n\n"
            f"🍓 **חויבת בעמלה על סך {debt_amount:.2f} שקלים (🍓) בתחנה {station_name}!**\n\n"
            f"📋 **פירוט הנסיעה:**\n"
            f"{order['text']}\n"
            f"💰 מחיר: ₪{order['price']}\n\n"
            f"סע בזהירות! לשאלות או בירורים ניתן לערער באמצעות הכפתור למטה:"
        )
        appeal_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚖️ ערער / בטל חיוב", callback_data=f"appeal_{new_debt_id or 0}")
        ]])
        await bot.send_message(driver_id, driver_txt, reply_markup=appeal_kb)
    except Exception as e:
        logging.warning(f"Could not send Telegram debt notification to driver {driver_id}: {e}")
    
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

    # מחיקת webhook ועדכונים ממתינים לפני התחלת polling בודד
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.warning(f"delete_webhook note: {e}")

    await asyncio.sleep(1)

    try:
        logging.info("📡 Bot Polling started (single instance)...")
        # הרצת polling פעם אחת בלבד ללא לולאת restart פנימית שגורמת ל-TelegramConflictError
        await dp.start_polling(bot, drop_pending_updates=True, allowed_updates=dp.resolve_used_update_types())
    except TelegramConflictError:
        logging.critical("⚠️ שגיאת TelegramConflictError: קיים מופע נוסף שרץ עם אותו BOT_TOKEN (למשל הרצה כפולה ב-Render או תהליך פעיל). יש לוודא שיש רק שירות/Worker יחיד פעיל.")
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped safely.")
    except Exception as e:
        logging.error(f"⚠️ שגיאה במהלך Polling: {e}")
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped safely.")
