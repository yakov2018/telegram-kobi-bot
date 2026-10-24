import os
import asyncio
import logging
import sys
import re
import json
import hmac
import hashlib
from urllib.parse import parse_qsl, unquote
from datetime import datetime, date
from decimal import Decimal
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
env_admin_ids = os.environ.get("ADMIN_IDS", "").strip()
if env_admin_ids:
    for aid in env_admin_ids.split(","):
        aid = aid.strip()
        if aid.isdigit():
            val = int(aid)
            if val not in ADMIN_IDS:
                ADMIN_IDS.append(val)

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
    waiting_price_choice = State()
    waiting_edit_text = State()
    waiting_manual_driver = State()

class DriverBidFlow(StatesGroup):
    waiting_eta = State()

class DebtFlow(StatesGroup):
    waiting_dispute_reason = State()
    waiting_appeal_reason = State()

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

def validate_telegram_init_data(init_data: str, bot_token: str = BOT_TOKEN) -> tuple[dict | None, bool]:
    """
    אימות קריפטוגרפי תקני של Telegram WebApp initData לפי מפרט הטלגרם הרשמי.
    מחזיר (user_payload, is_hmac_valid).
    """
    if not init_data:
        return None, False
    
    clean_token = (bot_token or "").strip().replace(" ", "")
    user_payload = None
    is_valid = False

    try:
        # פריסת הנתונים באמצעות parse_qsl
        parsed_items = parse_qsl(init_data, keep_blank_values=True)
        data_dict = dict(parsed_items)
        received_hash = data_dict.pop("hash", None)

        user_raw = data_dict.get("user")
        if user_raw:
            try:
                user_payload = json.loads(user_raw)
            except Exception:
                pass

        if received_hash and clean_token and clean_token != "DUMMY_TOKEN_PLEASE_SET_BOT_TOKEN":
            # יצירת ה-Secret Key: HMAC-SHA256 של הטוקן מול המפתח הקבוע "WebAppData"
            secret_key = hmac.new(b"WebAppData", clean_token.encode("utf-8"), hashlib.sha256).digest()

            # וריאנט 1: data_check_string עם ערכים מפוענחים (Standard Telegram)
            data_check_string_1 = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()))
            calc_hash_1 = hmac.new(secret_key, data_check_string_1.encode("utf-8"), hashlib.sha256).hexdigest()
            if hmac.compare_digest(calc_hash_1, received_hash):
                is_valid = True

            if not is_valid:
                # וריאנט 2: מחרוזת גולמית עם unquote (למקרה של קידוד תווים מיוחדים)
                raw_pairs = []
                for part in init_data.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        if k != "hash":
                            raw_pairs.append((unquote(k), unquote(v)))
                data_check_string_2 = "\n".join(f"{k}={v}" for k, v in sorted(dict(raw_pairs).items()))
                calc_hash_2 = hmac.new(secret_key, data_check_string_2.encode("utf-8"), hashlib.sha256).hexdigest()
                if hmac.compare_digest(calc_hash_2, received_hash):
                    is_valid = True

    except Exception as e:
        logging.warning(f"⚠️ הערה בבדיקת initData: {e}")

    return user_payload, is_valid

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
            ("requires_eta", "INTEGER DEFAULT 0"),
            ("client_phone", "TEXT"),
            ("eta_text", "TEXT"),
            ("assigned_driver_id", "BIGINT"),
            ("raw_text", "TEXT"),
            ("signature", "TEXT")
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
            is_locked INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP)''')

        debt_columns_to_add = [
            ("appeal_status", "TEXT DEFAULT 'none'"),
            ("appeal_reason", "TEXT"),
            ("transaction_type", "TEXT DEFAULT 'commission'"),
            ("is_locked", "INTEGER DEFAULT 0")
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

        # איפוס נתוני משתמשים לבקשת המשתמש לבדיקת מודל הרשאות חדש (שימור מנהלי מערכת בלבד)
        cur.execute("SELECT setting_value FROM deliveries_system_settings WHERE setting_key = 'wipe_rbac_reset_v4'")
        wipe_rbac = cur.fetchone()
        if not wipe_rbac:
          try:
            admin_tuple = tuple(ADMIN_IDS)
            cur.execute("DELETE FROM deliveries_order_bids")
            cur.execute("DELETE FROM deliveries_debts")
            cur.execute("DELETE FROM deliveries_orders")
            cur.execute(f"DELETE FROM deliveries_driver_cities WHERE user_id NOT IN {admin_tuple}")
            cur.execute(f"DELETE FROM deliveries_users WHERE user_id NOT IN {admin_tuple}")
            cur.execute("""INSERT INTO deliveries_system_settings (setting_key, setting_value)
                           VALUES ('wipe_rbac_reset_v4', 'completed')
                           ON CONFLICT (setting_key) DO UPDATE SET setting_value = 'completed'""")
            logging.info("איפוס משתמשים לבדיקת RBAC בוצע בהצלחה")
          except Exception as e:
            conn.rollback()
            logging.warning(f"Note on wipe_rbac_reset_v4: {e}")

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
            for col, ctype in [("requires_eta", "INTEGER DEFAULT 0"), ("client_phone", "TEXT"), ("eta_text", "TEXT"), ("assigned_driver_id", "INTEGER"), ("raw_text", "TEXT"), ("signature", "TEXT")]:
                try:
                    await db.execute(f"ALTER TABLE deliveries_orders ADD COLUMN {col} {ctype}")
                except Exception: pass
            
            await db.execute('''CREATE TABLE IF NOT EXISTS deliveries_debts (
                debt_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, driver_id INTEGER,
                station_id INTEGER, amount REAL, status TEXT DEFAULT 'unpaid', reason TEXT, 
                appeal_status TEXT DEFAULT 'none', appeal_reason TEXT, transaction_type TEXT DEFAULT 'commission',
                is_locked INTEGER DEFAULT 0, created_at TEXT, resolved_at TEXT)''')
            for col, ctype in [("appeal_status", "TEXT DEFAULT 'none'"), ("appeal_reason", "TEXT"), ("transaction_type", "TEXT DEFAULT 'commission'"), ("is_locked", "INTEGER DEFAULT 0")]:
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

            # איפוס נתוני משתמשים (SQLite) לבדיקת מודל הרשאות חדש (שימור מנהלי מערכת בלבד)
            c_rbac = await db.execute("SELECT setting_value FROM deliveries_system_settings WHERE setting_key = 'wipe_rbac_reset_v4'")
            wipe_rbac = await c_rbac.fetchone()
            if not wipe_rbac:
                admin_ids_str = ",".join(str(aid) for aid in ADMIN_IDS)
                await db.execute(f"DELETE FROM deliveries_users WHERE user_id NOT IN ({admin_ids_str})")
                await db.execute(f"DELETE FROM deliveries_driver_cities WHERE user_id NOT IN ({admin_ids_str})")
                await db.execute("DELETE FROM deliveries_order_bids")
                await db.execute("INSERT OR REPLACE INTO deliveries_system_settings (setting_key, setting_value) VALUES ('wipe_rbac_reset_v4', 'completed')")
                logging.info("🧹 בוצע איפוס משתמשים (SQLite) לבדיקת מודל הרשאות חדש!")

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

    // Initialize Telegram WebApp with cryptographic server authentication
    const tg = window.Telegram?.WebApp;
    let currentUserRole = 'user';
    let isFree = true;
    let debtBalance = 0.0;
    let myCities = [];
    let orders = [];

    if (tg) {
      tg.ready();
      tg.expand();
      const initDataStr = tg.initData || '';
      const tgUser = tg.initDataUnsafe?.user;
      
      // אימות קריפטוגרפי מול השרת
      fetch('/api/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          initData: initDataStr,
          user_id: tgUser?.id,
          user: tgUser
        })
      })
      .then(r => r.json())
      .then(data => {
        const sUser = (data && (data.user_data || data.user)) ? (data.user_data || data.user) : null;
        if (sUser) {
          currentUserRole = data.role || sUser.role;
          document.getElementById('tg-username').innerText = sUser.full_name + (currentUserRole === 'admin' ? ' 👑 (God Mode)' : ' (מזהה: ' + sUser.user_id + ')');
          const pName = document.getElementById('profile-name');
          if (pName) pName.innerText = sUser.full_name;

          if (Array.isArray(data.cities)) {
            myCities = data.cities;
            renderCities();
          }
        }

        // הסרת אלמנטים מה-DOM למי שאינו מורשה
        if (currentUserRole !== 'admin') {
          const admTab = document.getElementById('tab-btn-admin');
          if (admTab) admTab.remove();
          const admContent = document.getElementById('tab-admin');
          if (admContent) admContent.remove();
        } else {
          const admBtn = document.getElementById('tab-btn-admin');
          if (admBtn) {
            admBtn.classList.remove('hidden');
            setTimeout(() => switchTab('admin'), 50);
          }
        }

        if (currentUserRole !== 'admin' && currentUserRole !== 'dispatcher' && currentUserRole !== 'station_manager') {
          const dispTab = document.getElementById('tab-btn-dispatcher');
          if (dispTab) dispTab.remove();
          const dispContent = document.getElementById('tab-dispatcher');
          if (dispContent) dispContent.remove();
        }
      })
      .catch(() => {
        // Fallback: פתיחה בטוחה בעמדת נהג
        const admTab = document.getElementById('tab-btn-admin');
        if (admTab) admTab.remove();
        const dispTab = document.getElementById('tab-btn-dispatcher');
        if (dispTab) dispTab.remove();
      });
    } else {
      // Fallback: פתיחה בטוחה בעמדת נהג
      const admTab = document.getElementById('tab-btn-admin');
      if (admTab) admTab.remove();
      const dispTab = document.getElementById('tab-btn-dispatcher');
      if (dispTab) dispTab.remove();
    }
    let orders = [];

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
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

def cors_json_response(data, status=200):
    return web.json_response(
        data,
        status=status,
        dumps=lambda o: json.dumps(o, default=json_serial, ensure_ascii=False),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, PUT, DELETE",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Telegram-Init-Data, Accept"
        }
    )

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
    """הוספת עיר עבודה לנהג ב-deliveries_driver_cities ישירות מהאפליקציה וסנכרון מקלדת טלגרם"""
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

    # סנכרון מקלדת והודעה בטלגרם
    try:
        user = await get_user(user_id)
        if user:
            current_role = user['role'] if isinstance(user, dict) else user[9]
            current_status = user['status'] if isinstance(user, dict) else user[8]
            sync_txt = f"📍 **עיר עבודה נוספה מהאפליקציה:** {city_name}\nערים פעילות: {', '.join(cities)}"
            await bot.send_message(user_id, sync_txt, reply_markup=get_main_kb(current_role, current_status))
    except Exception as e:
        logging.warning(f"Could not send sync Telegram message to user {user_id}: {e}")

    return cors_json_response({"ok": True, "cities": cities})

async def handle_api_driver_cities_remove(request):
    """הסרת עיר עבודה לנהג מ-deliveries_driver_cities ישירות מהאפליקציה וסנכרון מקלדת טלגרם"""
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

    # סנכרון מקלדת והודעה בטלגרם
    try:
        user = await get_user(user_id)
        if user:
            current_role = user['role'] if isinstance(user, dict) else user[9]
            current_status = user['status'] if isinstance(user, dict) else user[8]
            sync_txt = f"🗑️ **עיר עבודה הוסרה מהאפליקציה:** {city_name}\nערים פעילות: {', '.join(cities) if cities else 'כל הארץ'}"
            await bot.send_message(user_id, sync_txt, reply_markup=get_main_kb(current_role, current_status))
    except Exception as e:
        logging.warning(f"Could not send sync Telegram message to user {user_id}: {e}")

    return cors_json_response({"ok": True, "cities": cities})

async def handle_api_driver_cities_clear(request):
    """ניקוי כל ערי העבודה לנהג ב-deliveries_driver_cities וסנכרון מקלדת טלגרם"""
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

    # סנכרון מקלדת והודעה בטלגרם
    try:
        user = await get_user(user_id)
        if user:
            current_role = user['role'] if isinstance(user, dict) else user[9]
            current_status = user['status'] if isinstance(user, dict) else user[8]
            sync_txt = "🗑️ **כל ערי העבודה נמחקו מהאפליקציה.**\nכעת תקבל קריאות מכל הארץ."
            await bot.send_message(user_id, sync_txt, reply_markup=get_main_kb(current_role, current_status))
    except Exception as e:
        logging.warning(f"Could not send sync Telegram message to user {user_id}: {e}")

    return cors_json_response({"ok": True, "cities": []})

async def handle_api_driver_all_cities(request):
    """החזרת כל ערי העבודה של כל הנהגים מ-deliveries_driver_cities"""
    if USE_POSTGRES:
        def _get():
            with get_pg_cursor() as cur:
                cur.execute("SELECT user_id, city_name FROM deliveries_driver_cities")
                return cur.fetchall()
        rows = await run_in_thread(_get)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            rows = await (await db.execute("SELECT user_id, city_name FROM deliveries_driver_cities")).fetchall()
    return cors_json_response({
        "ok": True, 
        "cities": [dict(r) if isinstance(r, dict) else {"user_id": r[0], "city_name": r[1]} for r in rows]
    })

async def handle_api_driver_status_check(request):
    """בדיקת סטטוס חי עבור ה-Mini App לסנכרון מיידי עם מקלדת הבוט בטלגרם"""
    user_id = request.query.get("user_id")
    if not user_id:
        return cors_json_response({"ok": False, "error": "user_id חובה"}, status=400)
    try:
        uid = int(user_id)
        user = await get_user(uid)
        if not user:
            return cors_json_response({"ok": False, "error": "משתמש לא נמצא"}, status=404)
        status = user['status'] if isinstance(user, dict) else user[8]
        role = user['role'] if isinstance(user, dict) else user[9]
        debt = user['debt_balance'] if isinstance(user, dict) else user[14]
        return cors_json_response({
            "ok": True,
            "status": status,
            "role": role,
            "debt_balance": float(debt or 0)
        })
    except Exception as e:
        return cors_json_response({"ok": False, "error": str(e)}, status=500)

async def handle_api_auth(request):
    """
    נקודת קצה לאימות משתמש Mini App מול Telegram ומסד הנתונים בענן:
    - מפענחת את initData של טלגרם (קריפטוגרפי + חילוץ fallback אטום)
    - בודקת האם המזהה שייך ל-ADMIN_IDS
    - מאחזרת או יוצרת את המשתמש ב-deliveries_users ללא שום קריסה
    - מחזירה { ok: True, role: actual_role, user_data: user_dict, user: user_dict, stations: stations, cities: cities }
    """
    user_id = None
    full_name = ""
    username = ""
    is_admin = False
    actual_role = "user"

    try:
        try:
            data = await request.json()
        except Exception:
            data = {}

        init_data = data.get("initData") or request.headers.get("X-Telegram-Init-Data") or request.query.get("initData") or ""
        
        user_payload = None
        is_hmac_valid = False

        if init_data:
            try:
                user_payload, is_hmac_valid = validate_telegram_init_data(init_data, BOT_TOKEN)
            except Exception as e_val:
                logging.warning(f"⚠️ validate_telegram_init_data note: {e_val}")

            # חילוץ נתוני משתמש מפוענחים מתוך מחרוזת ה-initData
            if not user_payload:
                try:
                    parsed_q = dict(parse_qsl(init_data, keep_blank_values=True))
                    u_raw = parsed_q.get("user")
                    if u_raw:
                        user_payload = json.loads(u_raw)
                except Exception:
                    pass

            if not user_payload:
                try:
                    # בדיקת unquote נוספת למקרה של קידוד כפול
                    unquoted_init = unquote(init_data)
                    parsed_q = dict(parse_qsl(unquoted_init, keep_blank_values=True))
                    u_raw = parsed_q.get("user")
                    if u_raw:
                        user_payload = json.loads(u_raw)
                except Exception:
                    pass

            if not user_payload:
                try:
                    # חילוץ ישיר בעזרת Regex של מזהה המשתמש מתוך initData
                    m = re.search(r'["\']?id["\']?\s*:\s*(\d+)', unquote(init_data))
                    if m:
                        user_payload = {"id": int(m.group(1))}
                except Exception:
                    pass

        # חילוץ ישיר מגוף הבקשה או מהפרמטרים
        if not user_payload:
            dev_user_id = (
                data.get("user_id")
                or (data.get("user") and data.get("user", {}).get("id"))
                or request.query.get("user_id")
                or request.headers.get("X-Telegram-User-Id")
            )
            if dev_user_id:
                try:
                    uid_int = int(dev_user_id)
                    user_payload = {"id": uid_int}
                    u_body = data.get("user")
                    if isinstance(u_body, dict):
                        user_payload.update(u_body)
                except Exception:
                    pass

        # אם אין שום נתון מזהה משתמש
        if not user_payload or not user_payload.get("id"):
            return cors_json_response({
                "ok": False,
                "error": "אימות טלגרם נכשל: לא התקבלו נתוני משתמש (initData חסר). יש לפתוח את האפליקציה ישירות מכפתור התפריט בבוט הטלגרם."
            }, status=401)

        user_id = int(user_payload.get("id"))
        full_name = (user_payload.get("first_name") or "").strip()
        if user_payload.get("last_name"):
            full_name = f"{full_name} {user_payload.get('last_name').strip()}".strip()
        username = (user_payload.get("username") or "").strip()
        if not full_name:
            full_name = username or f"משתמש {user_id}"

        # בדיקה קשיחה האם המזהה שייך לרשימת ה-Super Admins
        is_admin = (user_id in ADMIN_IDS)
        logging.info(f"🔑 אימות Mini App עבור משתמש {user_id} ({full_name}) | is_admin={is_admin} | hmac_valid={is_hmac_valid}")

        # שליפה ממסד הנתונים
        user = await get_user(user_id)

        if not user:
            # משתמש חדש: אך ורק אם הוא ב-ADMIN_IDS הוא מקבל 'admin', אחרת 'user'
            default_role = 'admin' if is_admin else 'user'
            if USE_POSTGRES:
                def _create_u():
                    with get_pg_cursor() as cur:
                        cur.execute('''INSERT INTO deliveries_users (user_id, full_name, telegram_username, role, status, is_phone_verified, is_blocked)
                                       VALUES (%s, %s, %s, %s, 'busy', %s, 0)
                                       ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name, role = EXCLUDED.role''',
                                    (user_id, full_name, username, default_role, 1 if is_admin else 0))
                await run_in_thread(_create_u)
            else:
                async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                    await db.execute('''INSERT INTO deliveries_users (user_id, full_name, telegram_username, role, status, is_phone_verified, is_blocked)
                                       VALUES (?, ?, ?, ?, 'busy', ?, 0)
                                       ON CONFLICT (user_id) DO UPDATE SET full_name = excluded.full_name, role = excluded.role''',
                                    (user_id, full_name, username, default_role, 1 if is_admin else 0))
                    await db.commit()
            user = await get_user(user_id)
        elif is_admin:
            # וידוא ש-Admin אמיתי מקבל הרשאת admin ולא חסום
            current_r = user['role'] if isinstance(user, dict) else user[9]
            if current_r != 'admin':
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
        elif not is_admin:
            # סעיף אבטחה: אם משתמש רגיל רשום בטעות כ-admin אך אינו ב-ADMIN_IDS, הורד מיידית ל-'user'!
            current_r = user['role'] if isinstance(user, dict) else user[9]
            if current_r == 'admin':
                if USE_POSTGRES:
                    def _demote_u():
                        with get_pg_cursor() as cur:
                            cur.execute("UPDATE deliveries_users SET role = 'user' WHERE user_id = %s", (user_id,))
                    await run_in_thread(_demote_u)
                else:
                    async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                        await db.execute("UPDATE deliveries_users SET role = 'user' WHERE user_id = ?", (user_id,))
                        await db.commit()
                user = await get_user(user_id)

        # קביעת התפקיד האמיתי
        raw_role = user['role'] if isinstance(user, dict) else user[9] if user else 'user'
        actual_role = 'admin' if is_admin else ('user' if raw_role == 'admin' else (raw_role or 'user'))

        # המרת שדות בטוחה לטיפוסים פרימיטיביים (למניעת שגיאות סיריאליזציה)
        def _val(k, idx, default):
            if isinstance(user, dict):
                v = user.get(k)
                return v if v is not None else default
            if isinstance(user, (tuple, list)) and len(user) > idx:
                v = user[idx]
                return v if v is not None else default
            return default

        user_dict = {
            "user_id": int(_val("user_id", 0, user_id)),
            "full_name": str(_val("full_name", 1, full_name)),
            "telegram_username": str(_val("telegram_username", 2, username)),
            "phone": str(_val("phone", 3, "") or ""),
            "birth_year": int(_val("birth_year", 4, 1995) or 1995),
            "car_brand": str(_val("car_brand", 5, "") or ""),
            "car_model": str(_val("car_model", 6, "") or ""),
            "car_year": int(_val("car_year", 7, 0) or 0),
            "car_seats": int(_val("car_seats", 8, 4) or 4),
            "status": str(_val("status", 9, "busy") or "busy"),
            "role": actual_role,
            "station_id": int(_val("station_id", 10, 1) or 1),
            "rating": float(_val("rating", 11, 5.0) or 5.0),
            "total_trips": int(_val("total_trips", 12, 0) or 0),
            "is_blocked": 0 if is_admin else int(_val("is_blocked", 13, 0) or 0),
            "debt_balance": float(_val("debt_balance", 14, 0.0) or 0.0),
            "subscription_plan": str(_val("subscription_plan", 15, "free") or "free"),
        }

        # טעינת תחנות
        stations = []
        try:
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

            for s in stations_raw:
                s_id = s['station_id'] if isinstance(s, dict) else s[0]
                s_name = s['name'] if isinstance(s, dict) else s[1]
                s_com = s['commission_percent'] if isinstance(s, dict) else s[2]
                stations.append({
                    "station_id": int(s_id),
                    "name": str(s_name),
                    "commission_percent": float(s_com or 10.0)
                })
        except Exception as e_st:
            logging.warning(f"⚠️ הערה בטעינת תחנות: {e_st}")
            stations = []

        # טעינת ערי נהג
        cities = []
        try:
            cities = await get_driver_cities(user_id)
        except Exception as e_c:
            logging.warning(f"⚠️ הערה בטעינת ערי נהג: {e_c}")
            cities = []

        logging.info(f"✅ אימות /api/auth הסתיים בהצלחה: role={actual_role}, stations_count={len(stations)}, cities_count={len(cities)}")

        return cors_json_response({
            "ok": True,
            "role": actual_role,
            "user_data": user_dict,
            "user": user_dict,
            "stations": stations,
            "cities": cities
        })

    except Exception as e:
        logging.exception(f"❌ שגיאה כללית ב-handle_api_auth: {e}")
        return cors_json_response({
            "ok": False,
            "error": f"שגיאת שרת פנימית בטעינת נתונים: {str(e)}"
        }, status=500)

async def handle_api_orders(request):
    """החזרת רשימת קריאות פתוחות עבור ה-Mini App"""
    try:
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
        orders = [dict(o) for o in (orders_raw or [])]
        return cors_json_response({"ok": True, "orders": orders})
    except Exception as e:
        logging.error(f"❌ שגיאה ב-handle_api_orders: {e}")
        return cors_json_response({"ok": True, "orders": []})


async def find_matching_drivers(cleaned_text: str, raw_text: str, origin_city: str, dest_city: str) -> list:
    """
    סעיף 2: אלגוריתם שידור ובדיקת SQL מדויקת מול deliveries_users ו-deliveries_driver_cities:
    מאתר נהגים עם status='free', is_blocked=0, debt_balance <= 500 (כולל סדרנים/מנהלים שפנויים לקבלת נסיעות!).
    עושה JOIN / EXISTS מול deliveries_driver_cities לוודא שהעיר (למשל 'ירושלים' או 'בני ברק') מוגדרת אצלם,
    או שנהג ללא הגבלת ערים כלל מקבל את הקריאה.
    """
    matched_uids = set()
    
    if USE_POSTGRES:
        def _query_pg():
            with get_pg_cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT u.user_id 
                    FROM deliveries_users u
                    WHERE u.status = 'free'
                      AND (u.is_blocked IS NULL OR u.is_blocked = 0)
                      AND (u.debt_balance IS NULL OR u.debt_balance <= 500)
                      AND (
                        -- נהג שלא הגדיר ערי סינון כלל מקבל את כל הקריאות
                        NOT EXISTS (SELECT 1 FROM deliveries_driver_cities dc_empty WHERE dc_empty.user_id = u.user_id)
                        -- או שנהג הגדיר עיר שמופיעה בטקסט הקריאה או בערי המקור/יעד
                        OR EXISTS (
                          SELECT 1 FROM deliveries_driver_cities dc
                          WHERE dc.user_id = u.user_id
                            AND (
                              %s ILIKE ('%%' || dc.city_name || '%%')
                              OR %s ILIKE ('%%' || dc.city_name || '%%')
                              OR (length(%s) > 0 AND (dc.city_name = %s OR %s ILIKE ('%%' || dc.city_name || '%%') OR dc.city_name ILIKE ('%%' || %s || '%%')))
                              OR (length(%s) > 0 AND (dc.city_name = %s OR %s ILIKE ('%%' || dc.city_name || '%%') OR dc.city_name ILIKE ('%%' || %s || '%%')))
                            )
                        )
                      )
                """, (raw_text, cleaned_text, origin_city, origin_city, origin_city, origin_city, dest_city, dest_city, dest_city, dest_city))
                rows = cur.fetchall()
                return [r['user_id'] for r in rows]
        try:
            sql_uids = await run_in_thread(_query_pg)
            matched_uids.update(sql_uids)
        except Exception as e:
            logging.warning(f"Error in find_matching_drivers PG query: {e}")
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            rows = await (await db.execute("""
                SELECT DISTINCT u.user_id 
                FROM deliveries_users u
                WHERE u.status = 'free'
                  AND (u.is_blocked IS NULL OR u.is_blocked = 0)
                  AND (u.debt_balance IS NULL OR u.debt_balance <= 500)
                  AND (
                    NOT EXISTS (SELECT 1 FROM deliveries_driver_cities dc_empty WHERE dc_empty.user_id = u.user_id)
                    OR EXISTS (
                      SELECT 1 FROM deliveries_driver_cities dc
                      WHERE dc.user_id = u.user_id
                        AND (
                          INSTR(?, dc.city_name) > 0
                          OR INSTR(?, dc.city_name) > 0
                          OR (? != '' AND (dc.city_name = ? OR INSTR(?, dc.city_name) > 0 OR INSTR(dc.city_name, ?) > 0))
                          OR (? != '' AND (dc.city_name = ? OR INSTR(?, dc.city_name) > 0 OR INSTR(dc.city_name, ?) > 0))
                        )
                    )
                  )
            """, (raw_text, cleaned_text, origin_city, origin_city, origin_city, origin_city, dest_city, dest_city, dest_city, dest_city))).fetchall()
            matched_uids.update([r[0] for r in rows])

    # שכבת בדיקה נוספת ב-Python לוודא שלא מתפספס אף נהג עם שמות ערים וקיצורים (ים, בב, פת, תא, קס וכו')
    try:
        if USE_POSTGRES:
            def _get_fallback():
                with get_pg_cursor() as cur:
                    cur.execute("""SELECT user_id FROM deliveries_users 
                                   WHERE status = 'free' AND (is_blocked IS NULL OR is_blocked = 0)
                                     AND (debt_balance IS NULL OR debt_balance <= 500)""")
                    free_users = [r['user_id'] for r in cur.fetchall()]
                    cur.execute("SELECT user_id, city_name FROM deliveries_driver_cities")
                    all_cities = cur.fetchall()
                    return free_users, all_cities
            free_users, all_cities = await run_in_thread(_get_fallback)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                free_users = [r[0] for r in await (await db.execute("""SELECT user_id FROM deliveries_users 
                                                                       WHERE status = 'free' AND (is_blocked IS NULL OR is_blocked = 0)
                                                                         AND (debt_balance IS NULL OR debt_balance <= 500)""")).fetchall()]
                all_cities = await (await db.execute("SELECT user_id, city_name FROM deliveries_driver_cities")).fetchall()

        driver_cities_map = {}
        for c in all_cities:
            uid = c['user_id'] if isinstance(c, dict) else c[0]
            cname = c['city_name'] if isinstance(c, dict) else c[1]
            driver_cities_map.setdefault(uid, []).append(cname)

        alias_map = {
            'ירושלים': ['ים', 'י-ם', 'עיר הקודש', 'ירושלים'],
            'בני ברק': ['בב', 'ב"ב', 'בני ברק'],
            'פתח תקווה': ['פת', 'פ"ת', 'פתח תקוה', 'פתח תקווה'],
            'תל אביב': ['תא', 'ת"א', 'תל אביב'],
            'מודיעין עילית': ['קס', 'ק"ס', 'ספר', 'מודיעין עילית'],
            'בית שמש': ['בש', 'ב"ש', 'בית שמש'],
            'אשדוד': ['אשד', 'אשדוד'],
            'חיפה': ['חי', 'חיפה'],
            'נתניה': ['נת', 'נתניה'],
        }

        order_search_space = f"{raw_text} {cleaned_text} {origin_city} {dest_city}".lower()

        for uid in free_users:
            user_c = driver_cities_map.get(uid, [])
            if not user_c:
                matched_uids.add(uid)
                continue
            for uc in user_c:
                uc_str = uc.strip()
                if not uc_str:
                    continue
                if uc_str.lower() in order_search_space:
                    matched_uids.add(uid)
                    break
                aliases = alias_map.get(uc_str, [])
                if any(a.lower() in order_search_space for a in aliases):
                    matched_uids.add(uid)
                    break
    except Exception as e:
        logging.warning(f"Error in find_matching_drivers fallback: {e}")

    return list(matched_uids)

async def handle_api_orders_publish(request):
    """
    סעיף 2: פרסום קריאה מתוך המיני-אפליקציה, שמירה ב-deliveries_orders ושידור מיידי
    לנהגים פנויים באזורי העבודה בטלגרם!
    """
    try: data = await request.json()
    except Exception: data = {}

    raw_text = (data.get("text") or data.get("raw_text") or "").strip()
    price = float(data.get("price") or 0)
    publisher_id = int(data.get("publisher_id") or 0)
    station_id = int(data.get("station_id") or 1)
    destination_type = data.get("destination_type") or "private"
    requires_eta = 1 if data.get("requires_eta") else 0

    if not raw_text:
        return cors_json_response({"ok": False, "error": "טקסט קריאה הינו חובה"}, status=400)

    parsed = parse_dispatcher_order(raw_text)
    cleaned_text = parsed["cleaned_text"]
    if price <= 0:
        price = parsed["price"] or 100.0

    origin_city = parsed.get("origin_city") or data.get("origin_city") or ""
    dest_city = parsed.get("dest_city") or data.get("dest_city") or ""
    now_iso = datetime.now().isoformat()

    new_order_id = 0
    if USE_POSTGRES:
        def _ins_order():
            with get_pg_cursor() as cur:
                cur.execute('''INSERT INTO deliveries_orders 
                               (text, price, publisher_id, station_id, created_at, requires_eta, origin_city, dest_city, status) 
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open') RETURNING order_id''', 
                            (cleaned_text, price, publisher_id, station_id, now_iso, requires_eta, origin_city, dest_city))
                return cur.fetchone()['order_id']
        new_order_id = await run_in_thread(_ins_order)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            c = await db.execute('''INSERT INTO deliveries_orders 
                                   (text, price, publisher_id, station_id, created_at, requires_eta, origin_city, dest_city, status) 
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')''', 
                                (cleaned_text, price, publisher_id, station_id, now_iso, requires_eta, origin_city, dest_city))
            new_order_id = c.lastrowid
            await db.commit()

    eta_badge = " [⏱️ נדרש ETA]" if requires_eta else ""
    order_msg = f"🎫 **קריאה #{new_order_id}**{eta_badge}\n🏢 תחנה: #{station_id}\n\n{cleaned_text}\n\n💵 סכום: {price:.2f} ש\"ח"
    sent_count = 0

    if destination_type == 'private':
        # סעיף 2: איתור כל הנהגים הפנויים התואמים לקריאה באמצעות בדיקת SQL וערים
        matched_driver_ids = await find_matching_drivers(cleaned_text, raw_text, origin_city, dest_city)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚗 קח קריאה", callback_data=f"take_{new_order_id}")]])

        for uid in matched_driver_ids:
            try:
                await bot.send_message(uid, order_msg, reply_markup=kb)
                sent_count += 1
                logging.info(f"Broadcast order #{new_order_id} delivered to driver {uid}")
            except Exception as e:
                logging.warning(f"Could not send order #{new_order_id} to driver {uid}: {e}")
    else:
        # שיגור לקבוצות
        if USE_POSTGRES:
            def _get_groups():
                with get_pg_cursor() as cur:
                    cur.execute("SELECT group_id FROM deliveries_bot_groups")
                    return cur.fetchall()
            groups = await run_in_thread(_get_groups)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                groups = await (await db.execute("SELECT group_id FROM deliveries_bot_groups")).fetchall()
        for g in groups:
            gid = g['group_id'] if isinstance(g, dict) else g[0]
            try:
                await bot.send_message(gid, order_msg)
                sent_count += 1
            except Exception:
                pass

    return cors_json_response({"ok": True, "order_id": new_order_id, "eligible_drivers": sent_count})

async def handle_api_driver_status(request):
    """
    סעיף 3: עדכון סטטוס נהג (פנוי / תפוס) ישירות מתוך ה-Mini App 
    וסנכרון מיידי של מקלדת הטלגרם בצ'אט (ReplyKeyboard) באמצעות bot.send_message!
    """
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
    if new_status == 'free' and float(debt or 0) > 500.0:
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

    # סעיף 3: סנכרון מיידי של מקלדת הטלגרם בצ'אט (ReplyKeyboard) עם הסטטוס החדש
    try:
        current_role = user['role'] if isinstance(user, dict) else user[9]
        status_hebrew = "🟢 פנוי לעבודה" if new_status == 'free' else "🔴 תפוס (עצור קריאות)"
        sync_txt = (
            f"🔄 **סטטוס המשתמש עודכן מהמיני-אפליקציה:** {status_hebrew}\n\n"
            f"המקלדת בצ'אט סונכרנה בהתאם."
        )
        await bot.send_message(int(user_id), sync_txt, reply_markup=get_main_kb(current_role, new_status))
    except Exception as e:
        logging.warning(f"Could not send sync Telegram keyboard to user {user_id}: {e}")

    return cors_json_response({"ok": True, "new_status": new_status})

async def handle_api_stations(request):
    """החזרת רשימת התחנות והעמלות"""
    try:
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
        return cors_json_response({"ok": True, "stations": [dict(r) for r in (rows or [])]})
    except Exception as e:
        logging.error(f"❌ שגיאה ב-handle_api_stations: {e}")
        return cors_json_response({"ok": True, "stations": []})


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
    try:
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
        return cors_json_response({"ok": True, "users": [dict(r) for r in (rows or [])]})
    except Exception as e:
        logging.error(f"❌ שגיאה ב-handle_api_users: {e}")
        return cors_json_response({"ok": True, "users": []})


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
    try:
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
        return cors_json_response({"ok": True, "debts": [dict(r) for r in (rows or [])]})
    except Exception as e:
        logging.error(f"❌ שגיאה ב-handle_api_debts: {e}")
        return cors_json_response({"ok": True, "debts": []})


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

async def handle_api_debts_resolve_appeal(request):
    """טיפול בערעור מתוך פאנל ניהול תחנה ב-Mini App: אישור (זיכוי 🍏) או דחייה ❌"""
    try: data = await request.json()
    except Exception: data = {}
    debt_id = data.get("debt_id")
    approve = data.get("approved", True)
    if not debt_id:
        return cors_json_response({"ok": False, "error": "debt_id חובה"}, status=400)
    debt_id = int(debt_id)

    debt = None
    if USE_POSTGRES:
        def _get_d():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_debts WHERE debt_id = %s", (debt_id,))
                return cur.fetchone()
        debt = await run_in_thread(_get_d)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debt = await (await db.execute("SELECT * FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()

    if not debt:
        return cors_json_response({"ok": False, "error": "חיוב לא נמצא"}, status=404)

    debt_dict = dict(debt)
    driver_id = debt_dict['driver_id']
    amount = float(debt_dict['amount'] or 0)
    order_id = debt_dict.get('order_id') or 0

    if USE_POSTGRES:
        def _resolve_pg():
            with get_pg_cursor() as cur:
                if approve:
                    cur.execute("UPDATE deliveries_debts SET status = 'cancelled', appeal_status = 'approved', resolved_at = CURRENT_TIMESTAMP WHERE debt_id = %s", (debt_id,))
                    cur.execute("UPDATE deliveries_users SET debt_balance = GREATEST(0, debt_balance - %s) WHERE user_id = %s", (amount, driver_id))
                else:
                    cur.execute("UPDATE deliveries_debts SET appeal_status = 'rejected', resolved_at = CURRENT_TIMESTAMP WHERE debt_id = %s", (debt_id,))
        await run_in_thread(_resolve_pg)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            if approve:
                await db.execute("UPDATE deliveries_debts SET status = 'cancelled', appeal_status = 'approved', resolved_at = ? WHERE debt_id = ?", (datetime.now().isoformat(), debt_id))
                await db.execute("UPDATE deliveries_users SET debt_balance = MAX(0, debt_balance - ?) WHERE user_id = ?", (amount, driver_id))
            else:
                await db.execute("UPDATE deliveries_debts SET appeal_status = 'rejected', resolved_at = ? WHERE debt_id = ?", (datetime.now().isoformat(), debt_id))
            await db.commit()

    # הודעה ישירה לנהג בטלגרם
    try:
        if approve:
            await bot.send_message(driver_id, f"🍏 **הערעור התקבל בהצלחה!**\nהחיוב על סך ₪{amount:.2f} עבור קריאה #{order_id} בוטל וזוכה במלואו (🍏)! יתרת החוב שלך בתחנה עודכנה.")
        else:
            await bot.send_message(driver_id, f"❌ **הבקשה לביטול חיוב נדחתה.**\nהחיוב על סך ₪{amount:.2f} עבור קריאה #{order_id} נותר בעינו ויש להסדירו מול התחנה.")
    except Exception as e:
        logging.warning(f"Could not notify driver on appeal resolve: {e}")

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
    app.router.add_post("/api/orders/publish", handle_api_orders_publish)
    app.router.add_post("/api/driver/status", handle_api_driver_status)
    app.router.add_post("/api/driver/profile", handle_api_driver_profile)
    app.router.add_get("/api/driver/cities", handle_api_driver_cities_get)
    app.router.add_get("/api/driver/all_cities", handle_api_driver_all_cities)
    app.router.add_get("/api/driver/status_check", handle_api_driver_status_check)
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
    app.router.add_post("/api/debts/resolve_appeal", handle_api_debts_resolve_appeal)
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
    root_index = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(root_index):
        return web.FileResponse(root_index)
    return web.Response(text="מערכת בטעינה...", content_type="text/html", charset="utf-8")

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
    kb.append([KeyboardButton(text="🚗 קריאות זמינות"), KeyboardButton(text=status_btn)])
    kb.append([KeyboardButton(text="📍 אזורי עבודה"), KeyboardButton(text="💎 הפרופיל שלי")])
    kb.append([KeyboardButton(text="💳 חיובים וערעורים")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_kb(chat_type='private'):
    if chat_type in ('group', 'supergroup'):
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול וחזרה")]], resize_keyboard=True)

# ----------------- סעיף 2: מנוע NLP לסדרנים, פענוח קריאות חכם וחתימת תחנה -----------------
def extract_order_phone(text: str) -> str:
    """
    זיהוי מספר טלפון לקוח ב-Regex קפדני:
    - טלפון ישראלי מלא (05X, 02, 03, 04, 08, 09, 07X, או קידומת +972)
    - מספרי פנים כגון '0' או '1' בלבד (שלוחה/קוד פנים)
    - מתעלם לחלוטין מסתם 2-3 ספרות רצופות (כמו 20, 50, 100, 150)
    """
    if not text:
        return ""
        
    # 1. טלפון ישראלי מלא
    full_pattern = r'(?:\+?972[- ]?0?|0)(?:5[0-9]|[23489]|7[2-9])[- ]?\d{3}[- ]?\d{4}\b'
    m_full = re.search(full_pattern, text)
    if m_full:
        return re.sub(r'[^\d+]', '', m_full.group(0))

    # 2. שלוחה/פנים '0' או '1' מפורש לפי תיוג
    lbl_pattern = r'(?:טלפון|טל|פלאפון|נייד|שלוחה|קוד)[:\s]*([01])\b'
    m_lbl = re.search(lbl_pattern, text)
    if m_lbl:
        return m_lbl.group(1)

    # 3. ספרה 0 או 1 מבודדת לחלוטין (Isolated token) שאינה חלק ממחיר
    iso_pattern = r'(?:^|\s)([01])(?:\s|$)'
    m_iso = re.search(iso_pattern, text)
    if m_iso:
        sub_before = text[:m_iso.start(1)]
        if not re.search(r'[₪ש]\s*$', sub_before):
            return m_iso.group(1)

    return ""

def build_order_signature(station_name: str = "תחנה ראשית", publisher_name: str = "") -> str:
    """
    הטמעת חתימה בסוף ההודעה: שם התחנה ושם המפרסם (ללא ה-@username שלו, רק שם פרטי/מלא)
    """
    clean_pub = re.sub(r'@[A-Za-z0-9_]+', '', publisher_name or "").strip()
    if not clean_pub:
        clean_pub = "סדרן המערכת"
    clean_st = station_name or "תחנה ראשית"
    return f"\n\n🏢 תחנה: {clean_st} | 👤 סדרן: {clean_pub}"

def parse_dispatcher_order(raw_text: str, station_name: str = "תחנה ראשית", publisher_name: str = "") -> dict:
    """
    מנוע NLP ו-Regex חכם לפיענוח קריאות סדרנים:
    1. עיר מוצא ועיר יעד (לפי מאגר הקיצורים והערים הפופולריות).
    2. מחיר + זיהוי התנגשות מחירים (Price Collision) אם קיימות מספר אפשרויות.
    3. מילת המפתח 'זמן'/'זמנים'/דקות (requires_eta=True).
    4. מספר טלפון לקוח (ישראלי מלא או 0/1 בלבד, תוך התעלמות מ-2-3 ספרות רצופות).
    5. הטמעת חתימה בסוף הקריאה (ללא @username).
    """
    text = (raw_text or "").strip()
    
    # 1. זיהוי דרישת 'זמן' / ETA
    time_keywords = ['זמן', 'זמנים', 'דקות', 'דק\'', 'דק', 'תוך', 'דחוף', 'eta', 'מיידי', 'עכשיו']
    requires_eta = False
    for kw in time_keywords:
        if re.search(r'(?:^|\s|[^\w])' + re.escape(kw) + r'(?:$|\s|[^\w])', text, re.IGNORECASE):
            requires_eta = True
            break

    # 2. זיהוי טלפון לקוח
    client_phone = extract_order_phone(text)

    # 3. זיהוי מחירים ובדיקת התנגשות (Price Collision)
    # א. מחירים עם סימן מטבע מפורש
    explicit_price_pattern = r'(?:₪\s*(\d{2,4})|(\d{2,4})\s*(?:₪|ש"ח|שח|שקלים|שקל|ש\b))'
    explicit_matches = re.findall(explicit_price_pattern, text)
    candidate_prices = []
    for em in explicit_matches:
        p_val = em[0] or em[1]
        if p_val and 20 <= float(p_val) <= 5000:
            candidate_prices.append(float(p_val))

    # ב. אם לא נמצאו מפורשים, חילוץ מספרים עצמאיים בטווח מחירי מוניות (20-5000)
    # תוך סינון שנים (1950-2030) ומספר הטלפון שנלכד
    if not candidate_prices:
        number_tokens = re.findall(r'\b\d{2,4}\b', text)
        for token in number_tokens:
            num = float(token)
            if 20 <= num <= 5000:
                if 1950 <= num <= 2030:
                    continue
                if client_phone and token in client_phone:
                    continue
                candidate_prices.append(num)

    # הסרת כפילויות תוך שימור סדר
    unique_prices = []
    for p in candidate_prices:
        if p not in unique_prices:
            unique_prices.append(p)

    has_price_collision = len(unique_prices) > 1
    selected_price = unique_prices[0] if unique_prices else 0.0

    # 4. מילון קיצורים ונירמול שמות ערים (NLP)
    alias_dict = {
        'ים': 'ירושלים', 'י-ם': 'ירושלים', 'עיר הקודש': 'ירושלים',
        'בב': 'בני ברק', 'ב"ב': 'בני ברק',
        'פת': 'פתח תקווה', 'פ"ת': 'פתח תקווה',
        'תא': 'תל אביב', 'ת"א': 'תל אביב',
        'קס': 'מודיעין עילית', 'ק"ס': 'מודיעין עילית', 'ספר': 'מודיעין עילית',
        'אשד': 'אשדוד', 'אשדו': 'אשדוד',
        'בש': 'באר שבע', 'ב"ש': 'בית שמש',
        'חי': 'חיפה', 'נת': 'נתניה', 'הרצ': 'הרצליה',
        'ראשלצ': 'ראשון לציון', 'ראשל"צ': 'ראשון לציון', 'חולון': 'חולון', 'בת ים': 'בת ים'
    }

    words = text.split()
    cleaned_tokens = []
    found_cities = []

    for word in words:
        clean_w = re.sub(r'[^\w\s"״\'-]', '', word).strip()
        prefix = ""
        check_w = clean_w
        if len(clean_w) > 2 and clean_w[0] in ['ל', 'מ', 'ב'] and (clean_w[1:] in alias_dict or clean_w[1:] in POPULAR_CITIES):
            prefix = clean_w[0] + " "
            check_w = clean_w[1:]
        elif len(clean_w) > 3 and clean_w[:2] in ['מה', 'לה', 'בה'] and (clean_w[2:] in alias_dict or clean_w[2:] in POPULAR_CITIES):
            prefix = clean_w[:2] + " "
            check_w = clean_w[2:]

        if check_w in alias_dict:
            city_name = alias_dict[check_w]
            cleaned_tokens.append(f"{prefix}{city_name}")
            if city_name not in found_cities:
                found_cities.append(city_name)
        elif check_w in POPULAR_CITIES:
            cleaned_tokens.append(f"{prefix}{check_w}")
            if check_w not in found_cities:
                found_cities.append(check_w)
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

    # 5. הטמעת חתימה נקייה
    signature = build_order_signature(station_name, publisher_name)
    cleaned_with_sig = f"{cleaned_text.strip()}{signature}"

    return {
        "cleaned_text": cleaned_with_sig,
        "raw_text": text,
        "base_text": cleaned_text.strip(),
        "price": selected_price,
        "price_candidates": unique_prices,
        "has_price_collision": has_price_collision,
        "requires_eta": requires_eta,
        "client_phone": client_phone,
        "found_cities": found_cities,
        "origin_city": origin_city,
        "dest_city": dest_city,
        "signature": signature
    }

def clean_order_text(text: str, station_name: str = "תחנה ראשית", publisher_name: str = "") -> str:
    return parse_dispatcher_order(text, station_name, publisher_name)["cleaned_text"]


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

    assigned_role = 'admin' if int(uid) in ADMIN_IDS else 'user'

    if USE_POSTGRES:
        def _save_driver_sync():
            with get_pg_cursor() as cur:
                cur.execute('''INSERT INTO deliveries_users 
                               (user_id, telegram_username, full_name, phone, is_phone_verified, birth_year, terms_accepted_at,
                                car_brand, car_model, car_year, car_seats, role, status, is_blocked, subscription_plan)
                               VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, 'busy', 0, 'free')
                               ON CONFLICT (user_id) DO UPDATE SET 
                               telegram_username = EXCLUDED.telegram_username, full_name = EXCLUDED.full_name, phone = EXCLUDED.phone, 
                               is_phone_verified = 1, birth_year = EXCLUDED.birth_year, terms_accepted_at = EXCLUDED.terms_accepted_at,
                               car_brand = EXCLUDED.car_brand, car_model = EXCLUDED.car_model, car_year = EXCLUDED.car_year, 
                               car_seats = EXCLUDED.car_seats, role = EXCLUDED.role, is_blocked = 0''',
                            (uid, uname, full_name, phone, birth_year, terms_at, car_brand, car_model, car_year, car_seats, assigned_role))
                
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
                               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 'busy', 0, 'free')
                               ON CONFLICT (user_id) DO UPDATE SET 
                               telegram_username = excluded.telegram_username, full_name = excluded.full_name, phone = excluded.phone, 
                               is_phone_verified = 1, birth_year = excluded.birth_year, terms_accepted_at = excluded.terms_accepted_at,
                               car_brand = excluded.car_brand, car_model = excluded.car_model, car_year = excluded.car_year, 
                               car_seats = excluded.car_seats, role = excluded.role, is_blocked = 0''',
                            (uid, uname, full_name, phone, birth_year, terms_at, car_brand, car_model, car_year, car_seats, assigned_role))
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

# ----------------- זרימת פרסום קריאה (Preview & Publish Flow) - עמודים 2 ו-3 -----------------
def make_order_preview_kb(draft_id: str) -> InlineKeyboardMarkup:
    """7 כפתורי פעולה לתצוגה מקדימה לפי סעיף 3 המדויק"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ערוך הודעה", callback_data=f"pubopt_edit_{draft_id}")],
        [InlineKeyboardButton(text="📢 פרסם לכולם", callback_data=f"pubopt_all_{draft_id}")],
        [InlineKeyboardButton(text="📍🌐 פרסם לפנויים באזור + קבוצות", callback_data=f"pubopt_area_groups_{draft_id}")],
        [InlineKeyboardButton(text="👥 פרסם רק בקבוצות", callback_data=f"pubopt_groups_{draft_id}")],
        [InlineKeyboardButton(text="🚗 פרסם רק לפנויים באזור", callback_data=f"pubopt_area_{draft_id}")],
        [InlineKeyboardButton(text="🤝 סגירה ידנית על נהג", callback_data=f"pubopt_manual_{draft_id}")],
        [InlineKeyboardButton(text="❌ ביטול ומחיקה", callback_data=f"pubopt_cancel_{draft_id}")]
    ])

# זיכרון טיוטות זמני לפי מזהה מפרסם
ORDER_DRAFTS = {}

@router.message(F.text == "📢 פרסם קריאה")
async def cmd_publish(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if not user or user['role'] not in ['admin', 'station_manager', 'dispatcher']: 
        return await message.answer("❌ אין לך הרשאת סדרן או מנהל לפרסום קריאות.")
    await state.set_state(OrderFlow.waiting_publish_text)
    await message.answer(
        "📝 **הדבק את פרטי הקריאה לפרסום:**\n\n"
        "💡 המערכת מזהה אוטומטית:\n"
        "• ערי מוצא ויעד (כולל קיצורים: ים, בב, פת, תא, קס, אשד וכו')\n"
        "• מחיר (במקרה של מספר מחירים יוקפץ בורר לבחירה)\n"
        "• דרישת זמן הגעה (מילים: 'זמן', 'דקות', 'דחוף')\n"
        "• טלפון לקוח (ישראלי מלא או שלוחה 0/1)\n"
        "• חתימת התחנה והסדרן תוטמע אוטומטית בסיום ההודעה.",
        reply_markup=cancel_kb(message.chat.type)
    )

@router.message(OrderFlow.waiting_publish_text)
async def process_publish_text(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    user = await get_user(message.from_user.id)
    station_name = "תחנה ראשית"
    if USE_POSTGRES:
        def _get_st():
            with get_pg_cursor() as cur:
                cur.execute("SELECT name FROM deliveries_stations WHERE station_id = %s", (user.get('station_id', 1),))
                row = cur.fetchone()
                return row['name'] if row else "תחנה ראשית"
        station_name = await run_in_thread(_get_st)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            row = await (await db.execute("SELECT name FROM deliveries_stations WHERE station_id = ?", (user.get('station_id', 1),))).fetchone()
            if row:
                station_name = row[0]

    parsed = parse_dispatcher_order(message.text, station_name, user['full_name'])
    candidate_prices = parsed.get('price_candidates', [])

    if not candidate_prices and parsed['price'] <= 0:
        return await message.answer(
            "⚠️ **המערכת לא זיהתה מחיר תקין בטקסט.**\n"
            "נא לכלול סכום בשקלים (לדוגמה: 150, 150 ש\"ח, ₪150).\n"
            "הקלד שוב את פרטי הקריאה:",
            reply_markup=cancel_kb(message.chat.type)
        )

    draft_id = f"{message.from_user.id}_{int(datetime.now().timestamp())}"
    draft_data = {
        "draft_id": draft_id,
        "publisher_id": message.from_user.id,
        "publisher_name": user['full_name'],
        "station_id": user.get('station_id', 1),
        "station_name": station_name,
        "raw_text": message.text,
        "base_text": parsed['base_text'],
        "cleaned_text": parsed['cleaned_text'],
        "signature": parsed['signature'],
        "origin_city": parsed['origin_city'],
        "dest_city": parsed['dest_city'],
        "client_phone": parsed['client_phone'],
        "requires_eta": 1 if parsed['requires_eta'] else 0,
        "price": parsed['price'],
        "price_candidates": candidate_prices
    }
    ORDER_DRAFTS[draft_id] = draft_data
    await state.update_data(current_draft_id=draft_id)

    # התנגשות מחירים (Price Collision)
    if parsed.get('has_price_collision') and len(candidate_prices) > 1:
        await state.set_state(OrderFlow.waiting_price_choice)
        price_btns = [
            [InlineKeyboardButton(text=f"💰 ₪{int(p) if p.is_integer() else p}", callback_data=f"chooseprice_{draft_id}_{int(p) if p.is_integer() else p}")]
            for p in candidate_prices
        ]
        price_btns.append([InlineKeyboardButton(text="❌ ביטול קריאה", callback_data=f"pubopt_cancel_{draft_id}")])
        return await message.answer(
            "🤔 **זוהו מספר אפשרויות מחיר בטקסט הקריאה.**\n"
            "באיזה מחיר לבחור עבור פרסום הנסיעה?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=price_btns)
        )

    # מעבר ישיר לתצוגה מקדימה
    await show_order_preview(message, draft_data, is_callback=False)

@router.callback_query(F.data.startswith("chooseprice_"))
async def handle_price_choice(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    draft_id = parts[1]
    chosen_price = float(parts[2])

    draft = ORDER_DRAFTS.get(draft_id)
    if not draft:
        return await call.answer("טיוטת הקריאה פגה, נא להזין מחדש.", show_alert=True)

    draft['price'] = chosen_price
    ORDER_DRAFTS[draft_id] = draft

    await call.answer(f"נבחר מחיר: ₪{chosen_price}")
    await show_order_preview(call.message, draft, is_callback=True)

async def show_order_preview(target_msg: Message, draft: dict, is_callback: bool = False):
    """הצגת תצוגה מקדימה עשירה עם 7 הכפתורים"""
    eta_text = "כן (הנהג יידרש לציין זמן הגעה)" if draft['requires_eta'] else "לא"
    phone_line = f"📱 **טלפון לקוח:** {draft['client_phone']}\n" if draft['client_phone'] else ""
    route_line = f"📍 **מסלול משוער:** {draft['origin_city'] or 'לא זוהה'} ➔ {draft['dest_city'] or 'לא זוהה'}\n"

    preview_text = (
        f"📋 **תצוגה מקדימה של הקריאה:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{draft['cleaned_text']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **מחיר שנבחר:** ₪{draft['price']}\n"
        f"{route_line}"
        f"{phone_line}"
        f"⏱️ **דרישת זמן (ETA):** {eta_text}\n\n"
        f"בחר לאן לשגר את הקריאה או פעולה רצויה:"
    )

    kb = make_order_preview_kb(draft['draft_id'])
    if is_callback:
        await target_msg.edit_text(preview_text, reply_markup=kb)
    else:
        await target_msg.answer(preview_text, reply_markup=kb)

# 1. ערוך הודעה
@router.callback_query(F.data.startswith("pubopt_edit_"))
async def handle_pubopt_edit(call: CallbackQuery, state: FSMContext):
    draft_id = call.data.replace("pubopt_edit_", "")
    await state.set_state(OrderFlow.waiting_publish_text)
    await call.message.edit_text("✏️ **הקלד את נוסח הקריאה המעודכן במלואו:**")
    await call.answer()

# 7. ביטול ומחיקה
@router.callback_query(F.data.startswith("pubopt_cancel_"))
async def handle_pubopt_cancel(call: CallbackQuery, state: FSMContext):
    draft_id = call.data.replace("pubopt_cancel_", "")
    ORDER_DRAFTS.pop(draft_id, None)
    await state.clear()
    await call.message.edit_text("❌ יצירת הקריאה בוטלה ונמחקה.")
    await call.answer()

# 6. סגירה ידנית על נהג (ללא פרסום)
@router.callback_query(F.data.startswith("pubopt_manual_"))
async def handle_pubopt_manual(call: CallbackQuery, state: FSMContext):
    draft_id = call.data.replace("pubopt_manual_", "")
    draft = ORDER_DRAFTS.get(draft_id)
    if not draft:
        return await call.answer("טיוטה פגה", show_alert=True)
    await state.update_data(manual_draft_id=draft_id)
    await state.set_state(OrderFlow.waiting_manual_driver)
    await call.message.answer(
        "🤝 **סגירה ידנית על נהג (ללא פרסום):**\n\n"
        "הקלד את מזהה הנהג (User ID), מספר טלפון, או @username:",
        reply_markup=cancel_kb()
    )
    await call.answer()

@router.message(OrderFlow.waiting_manual_driver)
async def process_manual_driver_input(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    data = await state.get_data()
    draft_id = data.get('manual_draft_id')
    draft = ORDER_DRAFTS.get(draft_id)
    if not draft:
        await state.clear()
        return await message.answer("טיוטת הקריאה פגה.", reply_markup=get_main_kb())

    query = message.text.strip().replace("@", "")
    target_driver = None

    if USE_POSTGRES:
        def _find_driver():
            with get_pg_cursor() as cur:
                cur.execute("""SELECT * FROM deliveries_users 
                               WHERE telegram_username = %s 
                                  OR phone = %s 
                                  OR CAST(user_id AS TEXT) = %s 
                               LIMIT 1""", (query, query, query))
                return cur.fetchone()
        target_driver = await run_in_thread(_find_driver)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            target_driver = await (await db.execute("""SELECT * FROM deliveries_users 
                                                       WHERE telegram_username = ? 
                                                          OR phone = ? 
                                                          OR CAST(user_id AS TEXT) = ? 
                                                       LIMIT 1""", (query, query, query))).fetchone()

    if not target_driver:
        return await message.answer(
            f"❌ לא נמצא נהג התואם ל-'{query}'.\n"
            "נסה שוב עם מספר טלפון, מזהה מספרי או @username, או לחץ ביטול:",
            reply_markup=cancel_kb(message.chat.type)
        )

    driver_id = target_driver['user_id']
    driver_name = target_driver['full_name']

    # יצירת קריאה סגורה במסד הנתונים
    order_id = await create_db_order(
        text=draft['cleaned_text'],
        price=draft['price'],
        publisher_id=draft['publisher_id'],
        station_id=draft['station_id'],
        requires_eta=draft['requires_eta'],
        origin_city=draft['origin_city'],
        dest_city=draft['dest_city'],
        client_phone=draft['client_phone'],
        raw_text=draft['raw_text'],
        status='closed',
        driver_id=driver_id
    )

    # ביצוע חיוב עמלה
    debt_amount, station_name, new_debt_id = await charge_driver_order(order_id, driver_id, draft['station_id'], draft['price'])

    # שליחת הודעת 🍓 לנהג
    disp = await get_user(draft['publisher_id'])
    disp_uname = (disp.get('telegram_username') if disp else "") or message.from_user.username or ""
    await send_private_debt_notice(
        driver_id=driver_id,
        order_id=order_id,
        order_text=draft['cleaned_text'],
        order_price=draft['price'],
        debt_amount=debt_amount,
        station_name=station_name,
        dispatcher_name=draft['publisher_name'],
        dispatcher_username=disp_uname,
        debt_id=new_debt_id
    )

    ORDER_DRAFTS.pop(draft_id, None)
    await state.clear()

    rate_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{driver_id}_1"), 
         InlineKeyboardButton(text="⭐⭐ 2", callback_data=f"rate_{driver_id}_2"), 
         InlineKeyboardButton(text="⭐⭐⭐ 3", callback_data=f"rate_{driver_id}_3")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐ 4", callback_data=f"rate_{driver_id}_4"), 
         InlineKeyboardButton(text="⭐⭐⭐⭐⭐ 5", callback_data=f"rate_{driver_id}_5")]
    ])

    await message.answer(
        f"🤝 **הנסיעה נסגרה ידנית בהצלחה!**\n\n"
        f"🎫 קריאה #{order_id} שויכה לנהג: **{driver_name}**\n"
        f"🍓 נרשמה עמלת תחנה: ₪{debt_amount:.2f}\n"
        f"הודעת חיוב בפרטי נשלחה לנהג כעת.\n\n"
        f"דרג את הנהג:",
        reply_markup=rate_kb
    )

# פונקציית עזר ליצירת קריאה ב-DB
async def create_db_order(text, price, publisher_id, station_id, requires_eta, origin_city, dest_city, client_phone, raw_text, status='open', driver_id=None):
    now_iso = datetime.now().isoformat()
    if USE_POSTGRES:
        def _insert():
            with get_pg_cursor() as cur:
                cur.execute("""INSERT INTO deliveries_orders 
                               (text, price, publisher_id, station_id, requires_eta, origin_city, dest_city, 
                                client_phone, raw_text, status, driver_id, created_at)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               RETURNING order_id""",
                            (text, price, publisher_id, station_id, requires_eta, origin_city, dest_city, 
                             client_phone, raw_text, status, driver_id, now_iso))
                return cur.fetchone()['order_id']
        return await run_in_thread(_insert)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            cursor = await db.execute("""INSERT INTO deliveries_orders 
                                         (text, price, publisher_id, station_id, requires_eta, origin_city, dest_city, 
                                          client_phone, raw_text, status, driver_id, created_at)
                                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                      (text, price, publisher_id, station_id, requires_eta, origin_city, dest_city, 
                                       client_phone, raw_text, status, driver_id, now_iso))
            await db.commit()
            return cursor.lastrowid

# 2, 3, 4, 5: ערוצי שידור
@router.callback_query(F.data.startswith("pubopt_all_"))
@router.callback_query(F.data.startswith("pubopt_area_groups_"))
@router.callback_query(F.data.startswith("pubopt_groups_"))
@router.callback_query(F.data.startswith("pubopt_area_"))
async def handle_publish_channels(call: CallbackQuery, state: FSMContext):
    data_parts = call.data.split("_")
    action = data_parts[1]
    if action == "area" and len(data_parts) > 2 and data_parts[2] == "groups":
        mode = "area_groups"
        draft_id = "_".join(data_parts[3:])
    else:
        mode = action
        draft_id = "_".join(data_parts[2:])

    draft = ORDER_DRAFTS.get(draft_id)
    if not draft:
        return await call.answer("טיוטת הקריאה פגה.", show_alert=True)

    order_id = await create_db_order(
        text=draft['cleaned_text'],
        price=draft['price'],
        publisher_id=draft['publisher_id'],
        station_id=draft['station_id'],
        requires_eta=draft['requires_eta'],
        origin_city=draft['origin_city'],
        dest_city=draft['dest_city'],
        client_phone=draft['client_phone'],
        raw_text=draft['raw_text']
    )

    # הכנת כפתורי נהג לקריאה מפורסמת
    disp = await get_user(draft['publisher_id'])
    disp_uname = (disp.get('telegram_username') if disp else "") or call.from_user.username or ""
    disp_url = f"https://t.me/{disp_uname}" if disp_uname else f"tg://user?id={draft['publisher_id']}"

    driver_card_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚗 בקשת הנסיעה", callback_data=f"bid_{order_id}"),
            InlineKeyboardButton(text="💬 לשאלות בפרטי", url=disp_url)
        ]
    ])

    eta_badge = " [⏱️ נדרש ETA]" if draft['requires_eta'] else ""
    broadcast_msg = (
        f"🎫 **קריאה חדשה #{order_id}**{eta_badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{draft['cleaned_text']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **מחיר:** ₪{draft['price']}"
    )

    sent_drivers = 0
    sent_groups = 0

    # קבוצות
    if mode in ['all', 'area_groups', 'groups']:
        groups = []
        if USE_POSTGRES:
            def _get_groups():
                with get_pg_cursor() as cur:
                    cur.execute("SELECT group_id FROM deliveries_bot_groups")
                    return cur.fetchall()
            groups = await run_in_thread(_get_groups)
        else:
            async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                groups = await (await db.execute("SELECT group_id FROM deliveries_bot_groups")).fetchall()
        for g in groups:
            gid = g['group_id'] if isinstance(g, dict) else g[0]
            try:
                await bot.send_message(gid, broadcast_msg, reply_markup=driver_card_kb)
                sent_groups += 1
            except Exception:
                pass

    # נהגים בפרטי
    if mode in ['all', 'area_groups', 'area']:
        if mode == 'all':
            # כל הנהגים הפנויים
            uids = []
            if USE_POSTGRES:
                def _get_all_free():
                    with get_pg_cursor() as cur:
                        cur.execute("SELECT user_id FROM deliveries_users WHERE status = 'free' AND (is_blocked IS NULL OR is_blocked = 0) AND debt_balance <= 500")
                        return [r['user_id'] for r in cur.fetchall()]
                uids = await run_in_thread(_get_all_free)
            else:
                async with aiosqlite.connect(SQLITE_DB_FILE) as db:
                    rows = await (await db.execute("SELECT user_id FROM deliveries_users WHERE status = 'free' AND (is_blocked IS NULL OR is_blocked = 0) AND debt_balance <= 500")).fetchall()
                    uids = [r[0] for r in rows]
        else:
            # לפי אזור וערי עבודה
            uids = await find_matching_drivers(draft['cleaned_text'], draft['raw_text'], draft['origin_city'], draft['dest_city'])

        for uid in uids:
            try:
                await bot.send_message(uid, broadcast_msg, reply_markup=driver_card_kb)
                sent_drivers += 1
            except Exception:
                pass

    ORDER_DRAFTS.pop(draft_id, None)
    await state.clear()

    summary_targets = []
    if sent_drivers > 0:
        summary_targets.append(f"🚗 {sent_drivers} נהגים פנויים")
    if sent_groups > 0:
        summary_targets.append(f"👥 {sent_groups} קבוצות")
    targets_str = " + ".join(summary_targets) if summary_targets else "המערכת"

    await call.message.edit_text(
        f"🚀 **קריאה #{order_id} שוגרה בהצלחה!**\n\n"
        f"🎯 נשלחה אל: {targets_str}\n"
        f"כשנהגים יגישו הצעה, תקבל כרטיסייה מלאה עם זמני הגעה והצעות מחיר."
    )
    await call.answer()

# ----------------- צד הנהג: הגשת בקשה והצעות (Bidding) - עמוד 4 -----------------
@router.callback_query(F.data.startswith("bid_"))
async def handle_driver_bid_click(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.replace("bid_", ""))

    # בדיקת סטטוס קריאה
    order = await get_db_order(order_id)
    if not order:
        return await call.answer("קריאה לא נמצאה.", show_alert=True)
    if order['status'] in ['assigned', 'closed']:
        return await call.answer("❌ הנסיעה נמכרה!", show_alert=True)
    if order['status'] == 'cancelled':
        return await call.answer("❌ הנסיעה בוטלה!", show_alert=True)

    driver = await get_user(call.from_user.id)
    if not driver:
        return await call.answer("⚠️ יש להירשם תחילה באמצעות /start", show_alert=True)
    if driver['is_blocked']:
        return await call.answer("🚫 חשבונך חסום במערכת.", show_alert=True)
    if driver['debt_balance'] > 500.0:
        return await call.answer("🚫 חשבונך מוקפא עקב חובות (מעל 500 ש\"ח)! הסדר חוב תחילה.", show_alert=True)

    # בדיקת דרישת זמן
    if order.get('requires_eta'):
        await state.update_data(bid_order_id=order_id)
        await state.set_state(DriverBidFlow.waiting_eta)
        await call.message.answer(
            f"⏱️ **הסדרן דרש זמן הגעה (ETA) לקריאה #{order_id}!**\n\n"
            f"תוך כמה זמן תוכל להגיע למוצא?\n"
            f"(הקלד טקסט חופשי, לדוגמה: '10 דקות', 'מיידי 3 דק', 'רבע שעה'):",
            reply_markup=cancel_kb(call.message.chat.type)
        )
        return await call.answer()

    # אם לא נדרש זמן הגעה מדויק
    await submit_driver_bid_to_dispatcher(call.message, driver, order, eta_text="מיידי / לא צוין")
    await call.answer("הצעתך נשלחה בהצלחה!")

@router.message(DriverBidFlow.waiting_eta)
async def process_driver_eta_input(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    data = await state.get_data()
    order_id = data.get('bid_order_id')
    if not order_id:
        await state.clear()
        return await cmd_start(message, state)

    order = await get_db_order(order_id)
    driver = await get_user(message.from_user.id)
    if not order or order['status'] in ['assigned', 'closed']:
        await state.clear()
        return await message.answer("❌ הנסיעה נמכרה!", reply_markup=get_main_kb(driver['role'], driver['status'], message.chat.type))
    if order['status'] == 'cancelled':
        await state.clear()
        return await message.answer("❌ הנסיעה בוטלה!", reply_markup=get_main_kb(driver['role'], driver['status'], message.chat.type))

    eta_text = message.text.strip()
    await state.clear()
    await submit_driver_bid_to_dispatcher(message, driver, order, eta_text=eta_text)

async def submit_driver_bid_to_dispatcher(target_msg: Message, driver: dict, order: dict, eta_text: str):
    order_id = order['order_id']
    driver_id = driver['user_id']

    # רישום הצעה בטבלה
    if USE_POSTGRES:
        def _reg_bid():
            with get_pg_cursor() as cur:
                cur.execute("""INSERT INTO deliveries_order_bids (order_id, driver_id, eta_minutes, status)
                               VALUES (%s, %s, 0, 'pending')""", (order_id, driver_id))
        await run_in_thread(_reg_bid)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("""INSERT INTO deliveries_order_bids (order_id, driver_id, eta_minutes, status)
                                 VALUES (?, ?, 0, 'pending')""", (order_id, driver_id))
            await db.commit()

    driver_uname = driver.get('telegram_username') or ""
    driver_mention = f"@{driver_uname}" if driver_uname else f"ID: {driver_id}"

    proposal_card = (
        f"🔔 **בקשת נהג חדשה לקריאה #{order_id}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 **פרטי הנסיעה:**\n"
        f"{order['text']}\n"
        f"💵 **מחיר:** ₪{order['price']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **כרטיסיית נהג מלאה:**\n"
        f"• **שם:** {driver['full_name']}\n"
        f"• **טלגרם:** {driver_mention}\n"
        f"• **טלפון:** {driver['phone']}\n"
        f"• **רכב:** {driver.get('car_brand', 'לא צוין')} {driver.get('car_model', '')} ({driver.get('car_year', '')}) | 💺 {driver.get('car_seats', 4)} מקומות\n"
        f"• **דירוג:** ⭐ {driver['rating']}/5.0 ({driver['total_trips']} נסיעות)\n"
        f"• **יתרת חוב בתחנה:** ₪{driver['debt_balance']:.2f}\n"
        f"⏱️ **זמן הגעה שהוצהר: {eta_text}**"
    )

    action_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 אישור הנסיעה לנהג", callback_data=f"assign_{order_id}_{driver_id}")],
        [InlineKeyboardButton(text="🍓 סגירה/חיוב הנסיעה", callback_data=f"charge_{order_id}_{driver_id}")],
        [InlineKeyboardButton(text="🔄 פרסם שוב", callback_data=f"repub_{order_id}")],
        [InlineKeyboardButton(text="🚫 ביטול הנסיעה", callback_data=f"cancelord_{order_id}")]
    ])

    try:
        await bot.send_message(order['publisher_id'], proposal_card, reply_markup=action_kb)
    except Exception as e:
        logging.error(f"Error sending bid card to dispatcher: {e}")

    await target_msg.answer(
        f"⏳ **הצעתך לקריאה #{order_id} שוגרה לסדרן (זמן הגעה: {eta_text})!**\n"
        f"ברגע שהסדרן יאשר, תקבל הודעה ישירה מיד.",
        reply_markup=get_main_kb(driver['role'], driver['status'], target_msg.chat.type)
    )

# פונקציית עזר לשליפת קריאה
async def get_db_order(order_id: int):
    if USE_POSTGRES:
        def _get():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_orders WHERE order_id = %s", (order_id,))
                return cur.fetchone()
        row = await run_in_thread(_get)
        return dict(row) if row else None
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute("SELECT * FROM deliveries_orders WHERE order_id = ?", (order_id,))).fetchone()
            return dict(row) if row else None

# ----------------- צד הסדרן: טיפול בבקשות נהגים - עמוד 5 -----------------
# 1. אישור הנסיעה לנהג (שיוך ללא חיוב עמלה עדיין)
@router.callback_query(F.data.startswith("assign_"))
async def handle_assign_driver(call: CallbackQuery):
    _, order_id_str, driver_id_str = call.data.split("_")
    order_id = int(order_id_str)
    driver_id = int(driver_id_str)

    order = await get_db_order(order_id)
    if not order or order['status'] in ['closed', 'cancelled']:
        return await call.answer("הקריאה כבר נסגרה או בוטלה.", show_alert=True)

    driver = await get_user(driver_id)
    dispatcher = await get_user(call.from_user.id)

    # עדכון סטטוס ל-assigned
    if USE_POSTGRES:
        def _set_assigned():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_orders SET status = 'assigned', assigned_driver_id = %s WHERE order_id = %s", (driver_id, order_id))
        await run_in_thread(_set_assigned)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE deliveries_orders SET status = 'assigned', assigned_driver_id = ? WHERE order_id = ?", (driver_id, order_id))
            await db.commit()

    # הודעה לנהג עם קישור ישיר לסדרן
    disp_uname = (dispatcher.get('telegram_username') if dispatcher else "") or call.from_user.username or ""
    disp_url = f"https://t.me/{disp_uname}" if disp_uname else f"tg://user?id={call.from_user.id}"
    driver_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 פתח שיחה עם הסדרן", url=disp_url)]
    ])

    try:
        await bot.send_message(
            driver_id,
            f"🎉 **הסדרן אישר אותך לקריאה #{order_id}!**\n\n"
            f"הנסיעה שוריינה עבורך (טרם חויבת בעמלה).\n"
            f"צור קשר עם הסדרן לתחילת הביצוע:",
            reply_markup=driver_kb
        )
    except Exception as e:
        logging.warning(f"Could not notify assigned driver: {e}")

    # עדכון הודעת הסדרן עם כפתורי סגירה/פרסום שוב/ביטול
    sub_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍓 סגירה/חיוב הנסיעה", callback_data=f"charge_{order_id}_{driver_id}")],
        [InlineKeyboardButton(text="🔄 פרסם שוב", callback_data=f"repub_{order_id}")],
        [InlineKeyboardButton(text="🚫 ביטול הנסיעה", callback_data=f"cancelord_{order_id}")]
    ])

    await call.message.edit_text(
        f"🟢 **הנסיעה שוייכה לנהג {driver['full_name']}!**\n\n"
        f"הנסיעה שוריינה עבורו מבלי לחייב עמלה כעת.\n"
        f"כל נהג אחר שילחץ על הקריאה יקבל מעתה: 'הנסיעה נמכרה'.\n\n"
        f"כאשר תרצה לגבות עמלה ולנעול סופית, לחץ 'סגירה/חיוב':",
        reply_markup=sub_kb
    )
    await call.answer("הנסיעה שויכה לנהג בהצלחה!")

# 2. סגירה/חיוב הנסיעה (גביית עמלה, 🍓, נעילת קריאה)
@router.callback_query(F.data.startswith("charge_"))
async def handle_charge_order(call: CallbackQuery):
    _, order_id_str, driver_id_str = call.data.split("_")
    order_id = int(order_id_str)
    driver_id = int(driver_id_str)

    order = await get_db_order(order_id)
    if not order or order['status'] == 'closed':
        return await call.answer("הקריאה כבר נסגרה וחויבה.", show_alert=True)

    driver = await get_user(driver_id)
    dispatcher = await get_user(call.from_user.id)

    # עדכון סטטוס ל-closed
    if USE_POSTGRES:
        def _set_closed():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_orders SET status = 'closed', driver_id = %s, completed_at = CURRENT_TIMESTAMP WHERE order_id = %s", (driver_id, order_id))
        await run_in_thread(_set_closed)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE deliveries_orders SET status = 'closed', driver_id = ?, completed_at = ? WHERE order_id = ?", (driver_id, datetime.now().isoformat(), order_id))
            await db.commit()

    debt_amount, station_name, new_debt_id = await charge_driver_order(order_id, driver_id, order['station_id'], order['price'])

    disp_uname = (dispatcher.get('telegram_username') if dispatcher else "") or call.from_user.username or ""
    await send_private_debt_notice(
        driver_id=driver_id,
        order_id=order_id,
        order_text=order['text'],
        order_price=order['price'],
        debt_amount=debt_amount,
        station_name=station_name,
        dispatcher_name=dispatcher['full_name'] if dispatcher else "סדרן התחנה",
        dispatcher_username=disp_uname,
        debt_id=new_debt_id
    )

    rate_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{driver_id}_1"), 
         InlineKeyboardButton(text="⭐⭐ 2", callback_data=f"rate_{driver_id}_2"), 
         InlineKeyboardButton(text="⭐⭐⭐ 3", callback_data=f"rate_{driver_id}_3")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐ 4", callback_data=f"rate_{driver_id}_4"), 
         InlineKeyboardButton(text="⭐⭐⭐⭐⭐ 5", callback_data=f"rate_{driver_id}_5")]
    ])

    await call.message.edit_text(
        f"🍓 **קריאה #{order_id} נסגרה וחויבה בהצלחה!**\n\n"
        f"👤 נהג: {driver['full_name']}\n"
        f"💰 סכום נסיעה: ₪{order['price']}\n"
        f"🍓 עמלה שנרשמה: ₪{debt_amount:.2f} בתחנה {station_name}\n"
        f"הודעת 🍓 נשלחה לנהג בפרטי עם אפשרות אישור/ערעור.\n\n"
        f"איך הנהג/הרכב? דרג כעת:",
        reply_markup=rate_kb
    )
    await call.answer("הנסיעה נסגרה וחויבה בהצלחה!")

# 3. פרסם שוב (פתיחה מחדש של זרימת הפרסום עם 7 הכפתורים)
@router.callback_query(F.data.startswith("repub_"))
async def handle_republish_order(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.replace("repub_", ""))
    order = await get_db_order(order_id)
    if not order:
        return await call.answer("קריאה לא נמצאה.", show_alert=True)

    # איפוס סטטוס ל-open
    if USE_POSTGRES:
        def _reopen():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_orders SET status = 'open', assigned_driver_id = NULL WHERE order_id = %s", (order_id,))
        await run_in_thread(_reopen)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE deliveries_orders SET status = 'open', assigned_driver_id = NULL WHERE order_id = ?", (order_id,))
            await db.commit()

    user = await get_user(call.from_user.id)
    draft_id = f"{call.from_user.id}_{int(datetime.now().timestamp())}"
    draft_data = {
        "draft_id": draft_id,
        "publisher_id": call.from_user.id,
        "publisher_name": user['full_name'],
        "station_id": order['station_id'],
        "cleaned_text": order['text'],
        "origin_city": order.get('origin_city', ''),
        "dest_city": order.get('dest_city', ''),
        "client_phone": order.get('client_phone', ''),
        "requires_eta": order.get('requires_eta', 0),
        "price": order['price'],
        "raw_text": order['text']
    }
    ORDER_DRAFTS[draft_id] = draft_data
    await state.update_data(current_draft_id=draft_id)

    await call.answer("פתיחת זרימת פרסום מחדש...")
    await show_order_preview(call.message, draft_data, is_callback=True)

# 4. ביטול הנסיעה
@router.callback_query(F.data.startswith("cancelord_"))
async def handle_cancel_order(call: CallbackQuery):
    order_id = int(call.data.replace("cancelord_", ""))
    if USE_POSTGRES:
        def _cancel():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_orders SET status = 'cancelled' WHERE order_id = %s", (order_id,))
        await run_in_thread(_cancel)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            await db.execute("UPDATE deliveries_orders SET status = 'cancelled' WHERE order_id = ?", (order_id,))
            await db.commit()

    await call.message.edit_text(f"🚫 **קריאה #{order_id} בוטלה לחלוטין!**\nהקריאה נרשמה בסטטיסטיקות התחנה כ'בוטלה'. נהגים שלוחצים יקבלו 'הנסיעה בוטלה'.")
    await call.answer("הנסיעה בוטלה.")

# פונקציית עזר לחיוב עמלה
async def charge_driver_order(order_id: int, driver_id: int, station_id: int, price: float):
    station_name = "תחנה ראשית"
    commission_rate = 10.0

    if USE_POSTGRES:
        def _calc():
            nonlocal station_name, commission_rate
            with get_pg_cursor() as cur:
                cur.execute("SELECT name, commission_percent FROM deliveries_stations WHERE station_id = %s", (station_id,))
                st = cur.fetchone()
                if st:
                    station_name = st['name']
                    commission_rate = st['commission_percent']
                debt_amount = price * (commission_rate / 100)
                cur.execute("""INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, status, reason, appeal_status, transaction_type)
                               VALUES (%s, %s, %s, %s, 'unpaid', %s, 'none', 'commission')
                               RETURNING debt_id""",
                            (order_id, driver_id, station_id, debt_amount, f"עמלה {commission_rate}%"))
                d_row = cur.fetchone()
                debt_id = d_row['debt_id'] if d_row else 0
                cur.execute("UPDATE deliveries_users SET debt_balance = debt_balance + %s, total_trips = total_trips + 1 WHERE user_id = %s", (debt_amount, driver_id))
                return debt_amount, station_name, debt_id
        return await run_in_thread(_calc)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            st = await (await db.execute("SELECT name, commission_percent FROM deliveries_stations WHERE station_id = ?", (station_id,))).fetchone()
            if st:
                station_name = st[0]
                commission_rate = st[1]
            debt_amount = price * (commission_rate / 100)
            c = await db.execute("""INSERT INTO deliveries_debts (order_id, driver_id, station_id, amount, status, reason, appeal_status, transaction_type)
                                     VALUES (?, ?, ?, ?, 'unpaid', ?, 'none', 'commission')""",
                                 (order_id, driver_id, station_id, debt_amount, f"עמלה {commission_rate}%"))
            debt_id = c.lastrowid
            await db.execute("UPDATE deliveries_users SET debt_balance = debt_balance + ?, total_trips = total_trips + 1 WHERE user_id = ?", (debt_amount, driver_id))
            await db.commit()
            return debt_amount, station_name, debt_id

# פונקציית עזר לשליחת הודעת 🍓 בפרטי לנהג עם כפתורי אישור וערעור
async def send_private_debt_notice(driver_id, order_id, order_text, order_price, debt_amount, station_name, dispatcher_name, dispatcher_username, debt_id):
    disp_mention = f"@{dispatcher_username}" if dispatcher_username else "סדרן התחנה"
    txt = (
        f"🍓 **הודעת חיוב עמלה חדשה!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 **תחנה:** {station_name}\n"
        f"🎫 **קריאה:** #{order_id}\n"
        f"💰 **סכום הנסיעה:** ₪{order_price}\n"
        f"🍓 **עמלה לתשלום:** ₪{debt_amount:.2f}\n"
        f"👤 **מפרסם הקריאה:** {dispatcher_name} ({disp_mention})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 **פירוט הנסיעה:**\n"
        f"{order_text}\n\n"
        f"באפשרותך לאשר את החיוב או להגיש בקשה לביטול (ערעור):"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ אישור חיוב", callback_data=f"ackdebt_{debt_id}")],
        [InlineKeyboardButton(text="⚖️ בקשה לביטול חיוב", callback_data=f"appeal_{debt_id}")]
    ])

    try:
        await bot.send_message(driver_id, txt, reply_markup=kb)
    except Exception as e:
        logging.warning(f"Could not send 🍓 debt notice to driver {driver_id}: {e}")

# ----------------- מערכת החיובים, זיכויים וערעורים - עמוד 6 -----------------
# 1. אישור חיוב (נועל את הקבלה ומונע ערעור עתידי)
@router.callback_query(F.data.startswith("ackdebt_"))
async def handle_ack_debt(call: CallbackQuery):
    debt_id = int(call.data.replace("ackdebt_", ""))
    if USE_POSTGRES:
        def _lock():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_debts SET is_locked = 1 WHERE debt_id = %s RETURNING amount", (debt_id,))
                row = cur.fetchone()
                return row['amount'] if row else 0
        amt = await run_in_thread(_lock)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            row = await (await db.execute("SELECT amount FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()
            amt = row[0] if row else 0
            await db.execute("UPDATE deliveries_debts SET is_locked = 1 WHERE debt_id = ?", (debt_id,))
            await db.commit()

    await call.message.edit_text(
        f"✅ **אישור חיוב נרשם בהצלחה!**\n\n"
        f"אישרת את החיוב על סך ₪{amt:.2f}.\n"
        f"הקבלה ננעלה במערכת ולא ניתן לערער עליה בעתיד."
    )
    await call.answer("החיוב אושר וננעל בהצלחה.")

# 2. בקשה לביטול חיוב (מפעיל FSM, מבקש סיבה ושולח למפרסם הקריאה)
@router.callback_query(F.data.startswith("appeal_"))
async def handle_appeal_start(call: CallbackQuery, state: FSMContext):
    debt_id = int(call.data.replace("appeal_", ""))

    debt = None
    if USE_POSTGRES:
        def _get():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_debts WHERE debt_id = %s", (debt_id,))
                return cur.fetchone()
        debt = await run_in_thread(_get)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debt = await (await db.execute("SELECT * FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()

    if not debt:
        return await call.answer("חיוב לא נמצא.", show_alert=True)
    if debt.get('is_locked'):
        return await call.answer("🚫 חיוב זה כבר אושר וננעל, לא ניתן להגיש ערעור.", show_alert=True)
    if debt.get('appeal_status') not in ['none', None]:
        return await call.answer("⚠️ כבר הוגשה בקשת ביטול עבור חיוב זה.", show_alert=True)

    await state.update_data(appeal_debt_id=debt_id)
    await state.set_state(DebtFlow.waiting_appeal_reason)
    await call.message.answer(
        f"✍️ **בקשה לביטול חיוב (ערעור) #{debt_id}:**\n\n"
        f"אנא הקלד את הסיבה לבקשת הביטול (למשל: 'הלקוח ביטל במקום', 'הנסיעה לא יצאה לפועל'):",
        reply_markup=cancel_kb(call.message.chat.type)
    )
    await call.answer()

@router.message(DebtFlow.waiting_appeal_reason)
async def process_appeal_reason_input(message: Message, state: FSMContext):
    if message.text == "❌ ביטול וחזרה":
        return await cmd_start(message, state)

    data = await state.get_data()
    debt_id = data.get('appeal_debt_id')
    if not debt_id:
        await state.clear()
        return await cmd_start(message, state)

    reason = message.text.strip()
    driver = await get_user(message.from_user.id)

    # עדכון סטטוס ערעור ב-DB
    if USE_POSTGRES:
        def _set_pend():
            with get_pg_cursor() as cur:
                cur.execute("UPDATE deliveries_debts SET appeal_status = 'pending', appeal_reason = %s WHERE debt_id = %s RETURNING order_id, amount, station_id", (reason, debt_id))
                return cur.fetchone()
        debt_row = await run_in_thread(_set_pend)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debt_row = await (await db.execute("SELECT order_id, amount, station_id FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()
            await db.execute("UPDATE deliveries_debts SET appeal_status = 'pending', appeal_reason = ? WHERE debt_id = ?", (reason, debt_id))
            await db.commit()

    order_id = debt_row['order_id'] if debt_row else 0
    amount = float(debt_row['amount'] or 0) if debt_row else 0.0

    # איתור המפרסם של הקריאה
    order = await get_db_order(order_id)
    publisher_id = order.get('publisher_id') if order else None

    driver_uname = driver.get('telegram_username') or ""
    driver_mention = f"@{driver_uname}" if driver_uname else f"ID: {driver['user_id']}"

    appeal_card = (
        f"⚖️ **בקשה חדשה לביטול חיוב #{debt_id}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎫 **קריאה:** #{order_id}\n"
        f"🍓 **סכום החיוב:** ₪{amount:.2f}\n"
        f"👤 **נהג מבקש:** {driver['full_name']} ({driver_mention} | טל: {driver['phone']})\n"
        f"📝 **סיבת הבקשה שהוקלדה:**\n"
        f"\"{reason}\"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"האם לאשר את ביטול החיוב (זיכוי 🍏) או לסרב?"
    )

    action_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍏 אשר ביטול חיוב", callback_data=f"appr_cancel_debt_{debt_id}"),
            InlineKeyboardButton(text="❌ סרב", callback_data=f"deny_cancel_debt_{debt_id}")
        ]
    ])

    # שליחה למפרסם הקריאה, ואם אין - למנהלי המערכת
    recipients = [publisher_id] if publisher_id else ADMIN_IDS
    for r_id in recipients:
        if r_id:
            try:
                await bot.send_message(r_id, appeal_card, reply_markup=action_kb)
            except Exception:
                pass

    await state.clear()
    await message.answer(
        f"✅ **בקשת הביטול נשלחה לסדרן לבדיקה.**\n"
        f"תקבל הודעה ישירה מיד כשתתקבל החלטה.",
        reply_markup=get_main_kb(driver['role'], driver['status'], message.chat.type)
    )

# אשר ביטול חיוב (מזכה את הנהג ב-🍏 ומוחק את העמלה)
@router.callback_query(F.data.startswith("appr_cancel_debt_"))
async def handle_approve_cancel_debt(call: CallbackQuery):
    debt_id = int(call.data.replace("appr_cancel_debt_", ""))

    if USE_POSTGRES:
        def _approve_cancel():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_debts WHERE debt_id = %s", (debt_id,))
                d = cur.fetchone()
                if not d or d['status'] == 'cancelled':
                    return None, 0, 0
                cur.execute("UPDATE deliveries_debts SET status = 'cancelled', appeal_status = 'approved', resolved_at = CURRENT_TIMESTAMP WHERE debt_id = %s", (debt_id,))
                cur.execute("UPDATE deliveries_users SET debt_balance = GREATEST(0, debt_balance - %s) WHERE user_id = %s", (d['amount'], d['driver_id']))
                return d['driver_id'], d['amount'], d['order_id']
        driver_id, amount, order_id = await run_in_thread(_approve_cancel)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            d = await (await db.execute("SELECT * FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()
            if not d or d['status'] == 'cancelled':
                driver_id, amount, order_id = None, 0, 0
            else:
                driver_id = d['driver_id']
                amount = d['amount']
                order_id = d['order_id']
                await db.execute("UPDATE deliveries_debts SET status = 'cancelled', appeal_status = 'approved', resolved_at = ? WHERE debt_id = ?", (datetime.now().isoformat(), debt_id))
                await db.execute("UPDATE deliveries_users SET debt_balance = MAX(0, debt_balance - ?) WHERE user_id = ?", (amount, driver_id))
                await db.commit()

    if not driver_id:
        return await call.answer("החיוב כבר בוטל או טופל.", show_alert=True)

    try:
        await bot.send_message(
            driver_id,
            f"🍏 **הערעור התקבל בהצלחה!**\n\n"
            f"החיוב על סך ₪{amount:.2f} עבור קריאה #{order_id} בוטל וזוכה במלואו (🍏)!\n"
            f"מאזן החוב שלך בתחנה עודכן כעת."
        )
    except Exception as e:
        logging.warning(f"Could not notify driver of credit: {e}")

    await call.message.edit_text(
        f"🍏 **אישרת את ביטול החיוב #{debt_id}!**\n\n"
        f"הנהג זוכה ב-₪{amount:.2f} והעמלה נמחקה מהמאזן שלו."
    )
    await call.answer("ביטול החיוב אושר והנהג זוכה!")

# סרב לביטול חיוב
@router.callback_query(F.data.startswith("deny_cancel_debt_"))
async def handle_deny_cancel_debt(call: CallbackQuery):
    debt_id = int(call.data.replace("deny_cancel_debt_", ""))

    if USE_POSTGRES:
        def _deny_cancel():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_debts WHERE debt_id = %s", (debt_id,))
                d = cur.fetchone()
                if not d:
                    return None, 0, 0
                cur.execute("UPDATE deliveries_debts SET appeal_status = 'rejected', resolved_at = CURRENT_TIMESTAMP WHERE debt_id = %s", (debt_id,))
                return d['driver_id'], d['amount'], d['order_id']
        driver_id, amount, order_id = await run_in_thread(_deny_cancel)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            d = await (await db.execute("SELECT * FROM deliveries_debts WHERE debt_id = ?", (debt_id,))).fetchone()
            if not d:
                driver_id, amount, order_id = None, 0, 0
            else:
                driver_id = d['driver_id']
                amount = d['amount']
                order_id = d['order_id']
                await db.execute("UPDATE deliveries_debts SET appeal_status = 'rejected', resolved_at = ? WHERE debt_id = ?", (datetime.now().isoformat(), debt_id))
                await db.commit()

    if not driver_id:
        return await call.answer("חיוב לא נמצא.", show_alert=True)

    try:
        await bot.send_message(
            driver_id,
            f"❌ **הבקשה לביטול חיוב נדחתה.**\n\n"
            f"החיוב על סך ₪{amount:.2f} עבור קריאה #{order_id} נותר בעינו ויש להסדירו מול התחנה."
        )
    except Exception as e:
        logging.warning(f"Could not notify driver of debt denial: {e}")

    await call.message.edit_text(
        f"❌ **דחית את בקשת הביטול על חיוב #{debt_id}.**\n\n"
        f"החיוב על סך ₪{amount:.2f} נותר פעיל במאזן הנהג."
    )
    await call.answer("הבקשה נדחתה.")

# דירוג נהג
@router.callback_query(F.data.startswith("rate_"))
async def rate_driver(call: CallbackQuery):
    _, driver_id_str, stars_str = call.data.split("_")
    driver_id = int(driver_id_str)
    stars = int(stars_str)

    if USE_POSTGRES:
        def _rate_sync():
            with get_pg_cursor() as cur:
                cur.execute('SELECT rating, total_trips FROM deliveries_users WHERE user_id = %s', (driver_id,))
                d = cur.fetchone()
                if d:
                    current_trips = max(d['total_trips'], 1)
                    new_rating = round(((d['rating'] * (current_trips - 1)) + stars) / current_trips, 1)
                    cur.execute('UPDATE deliveries_users SET rating = %s WHERE user_id = %s', (new_rating, driver_id))
        await run_in_thread(_rate_sync)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            d = await (await db.execute('SELECT rating, total_trips FROM deliveries_users WHERE user_id = ?', (driver_id,))).fetchone()
            if d:
                current_trips = max(d['total_trips'], 1)
                new_rating = round(((d['rating'] * (current_trips - 1)) + stars) / current_trips, 1)
                await db.execute('UPDATE deliveries_users SET rating = ? WHERE user_id = ?', (new_rating, driver_id))
                await db.commit()

    await call.message.edit_text(f"⭐ **דירגת את הנהג ב-{stars} כוכבים.** תודה!")
    await call.answer("הדירוג נשמר בהצלחה.")

# תפריט חיובים וערעורים לנהג
@router.message(F.text == "💳 חיובים וערעורים")
async def show_debts(message: Message):
    if USE_POSTGRES:
        def _get_debts():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_debts WHERE driver_id = %s AND status = 'unpaid' ORDER BY debt_id DESC LIMIT 15", (message.from_user.id,))
                return cur.fetchall()
        debts = await run_in_thread(_get_debts)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            debts = await (await db.execute("SELECT * FROM deliveries_debts WHERE driver_id = ? AND status = 'unpaid' ORDER BY debt_id DESC LIMIT 15", (message.from_user.id,))).fetchall()

    if not debts:
        return await message.answer("✅ **אין לך חובות פתוחים במערכת.** כל הכבוד!")

    await message.answer(f"💳 **רשימת החיובים הפתוחים שלך ({len(debts)}):**")
    for d in debts:
        d_dict = dict(d)
        is_locked = bool(d_dict.get('is_locked'))
        appeal_status = d_dict.get('appeal_status', 'none')

        status_lbl = ""
        if is_locked:
            status_lbl = " (🔒 ננעל ואושר)"
        elif appeal_status == 'pending':
            status_lbl = " (⏳ ערעור בבדיקה)"
        elif appeal_status == 'rejected':
            status_lbl = " (❌ ערעור נדחה)"

        txt = (
            f"🧾 **חיוב מתחנה #{d_dict['station_id']}**{status_lbl}\n"
            f"🎫 עבור קריאה #{d_dict.get('order_id') or 'ידני'}\n"
            f"💰 סכום: ₪{d_dict['amount']:.2f}\n"
            f"📝 סיבה: {d_dict.get('reason', 'עמלה')}"
        )

        buttons = []
        if not is_locked:
            buttons.append(InlineKeyboardButton(text="✅ אישור חיוב", callback_data=f"ackdebt_{d_dict['debt_id']}"))
            if appeal_status == 'none':
                buttons.append(InlineKeyboardButton(text="⚖️ בקשה לביטול", callback_data=f"appeal_{d_dict['debt_id']}"))

        kb = InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None
        await message.answer(txt, reply_markup=kb)

# קריאות זמינות לנהג (לפי ערי העבודה שלו)
@router.message(F.text == "🚗 קריאות זמינות")
async def show_available_orders_for_driver(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("יש להירשם תחילה למערכת באמצעות /start")

    my_cities = await get_driver_cities(message.from_user.id)

    if USE_POSTGRES:
        def _get_orders():
            with get_pg_cursor() as cur:
                cur.execute("SELECT * FROM deliveries_orders WHERE status = 'open' ORDER BY order_id DESC LIMIT 25")
                return cur.fetchall()
        open_orders = await run_in_thread(_get_orders)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            open_orders = await (await db.execute("SELECT * FROM deliveries_orders WHERE status = 'open' ORDER BY order_id DESC LIMIT 25")).fetchall()

    matching_orders = []
    for o in open_orders:
        o_dict = dict(o)
        o_text = o_dict.get('text', '')
        orig = o_dict.get('origin_city', '')
        dest = o_dict.get('dest_city', '')
        if not my_cities:
            matching_orders.append(o_dict)
        else:
            if any(c in o_text or c in [orig, dest] for c in my_cities):
                matching_orders.append(o_dict)

    if not matching_orders:
        cities_str = ", ".join(my_cities) if my_cities else "כל הארץ"
        return await message.answer(
            f"ℹ️ **אין כרגע קריאות פתוחות באזורי העבודה שלך ({cities_str}).**\n"
            f"ודא שאתה במצב '🟢 פנוי לעבודה' כדי לקבל התראות מיידיות כשיש קריאה חדשה!",
            reply_markup=get_main_kb(user['role'], user['status'], message.chat.type)
        )

    await message.answer(f"🚗 **נמצאו {len(matching_orders)} קריאות זמינות באזורי העבודה שלך:**")
    for o in matching_orders:
        eta_txt = " [⏱️ נדרש ETA]" if o.get('requires_eta') else ""
        txt = (
            f"🎫 **קריאה #{o['order_id']}**{eta_txt}\n"
            f"💵 מחיר: ₪{o['price']}\n"
            f"📝 {o['text']}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚗 בקשת הנסיעה", callback_data=f"bid_{o['order_id']}")]
        ])
        await message.answer(txt, reply_markup=kb)

# מצב קריאות (לסדרן ולמנהל תחנה בלבד לפי station_id)
@router.message(F.text.in_(["📋 מצב קריאות", "📋 קריאות התחנה שלי"]))
async def show_open_orders(message: Message):
    user = await get_user(message.from_user.id)
    if not user or user['role'] not in ['admin', 'station_manager', 'dispatcher']: 
        return
    
    if USE_POSTGRES:
        def _get_orders():
            with get_pg_cursor() as cur:
                if user['role'] == 'admin':
                    cur.execute("SELECT * FROM deliveries_orders WHERE status IN ('open', 'assigned') ORDER BY order_id DESC LIMIT 25")
                else:
                    cur.execute("SELECT * FROM deliveries_orders WHERE station_id = %s AND status IN ('open', 'assigned') ORDER BY order_id DESC LIMIT 25", (user['station_id'],))
                return cur.fetchall()
        orders = await run_in_thread(_get_orders)
    else:
        async with aiosqlite.connect(SQLITE_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            if user['role'] == 'admin':
                orders = await (await db.execute("SELECT * FROM deliveries_orders WHERE status IN ('open', 'assigned') ORDER BY order_id DESC LIMIT 25")).fetchall()
            else:
                orders = await (await db.execute("SELECT * FROM deliveries_orders WHERE station_id = ? AND status IN ('open', 'assigned') ORDER BY order_id DESC LIMIT 25", (user['station_id'],))).fetchall()
        
    if not orders:
        return await message.answer("✅ אין קריאות פתוחות לתחנה שלך כרגע.")
        
    for o in orders:
        o_dict = dict(o)
        status_heb = "משוריינת לנהג" if o_dict['status'] == 'assigned' else "פתוחה"
        eta_txt = "⏱️ נדרש ETA" if o_dict.get('requires_eta') else ""
        txt = (
            f"🎫 **קריאה #{o_dict['order_id']}** ({status_heb}) {eta_txt}\n"
            f"💵 מחיר: ₪{o_dict['price']}\n"
            f"📝 {o_dict['text']}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 פרסם שוב", callback_data=f"repub_{o_dict['order_id']}"),
                InlineKeyboardButton(text="🚫 ביטול נסיעה", callback_data=f"cancelord_{o_dict['order_id']}")
            ]
        ])
        await message.answer(txt, reply_markup=kb)

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
