import os
import asyncio
import logging
from datetime import datetime, timedelta
import aiosqlite

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8954258047:AAGTBHGEPOe9MTfQkvB4_gVGlY6nA1v9KPo")
ADMIN_IDS = [8644923212, 552821474]
DB_FILE = 'bot_database_v3.db'

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_birth = State()

class BotStates(StatesGroup):
    waiting_add_city = State()
    waiting_new_radius = State()
    waiting_broadcast_all = State()
    waiting_station_name = State()
    waiting_station_commission = State()
    waiting_station_manager = State()
    waiting_lead_text = State()
    waiting_lead_phone = State()
    editing_lead_price = State()
    editing_lead_text = State()
    editing_lead_phone = State()
    closing_lead = State()
    editing_lead_content = State()
    waiting_driver_time = State()
    editing_station_name = State()
    editing_station_comm = State()
    selecting_role = State()
    selecting_expiry = State()

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
                rating_count INTEGER DEFAULT 0
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

    for line in lines[:3]:
        for alias, full_name in CITY_ALIASES.items():
            if alias in line and full_name not in found_cities:
                found_cities.append(full_name)

    if found_cities:
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
        async with db.execute('SELECT full_name, phone, birth_date, status, expiry_date, role, station_id, radius, cities, total_trips, rating, rating_count FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

def get_main_keyboard(is_admin=False, is_advertiser=False, current_status='busy'):
    status_btn_text = "🟢 פנוי לקריאות" if current_status == 'free' else "🔴 תפוס"
    kb = []
    
    if is_admin or is_advertiser:
        kb.append([KeyboardButton(text="📢 פרסום הודעה"), KeyboardButton(text="📋 מצב קריאות")])
        
    kb.append([KeyboardButton(text=status_btn_text), KeyboardButton(text="⚙️ הגדרת אזורים ורדיוס")])
    kb.append([KeyboardButton(text="💎 מצב מנוי ופרופיל"), KeyboardButton(text="ℹ️ אודות ויצירת קשר")])
    
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
    role_val = user[5] if user else 'user'
    is_advertiser = is_admin or (role_val in ['admin', 'advertiser', 'station_manager', 'dispatcher'])
    current_status = user[3] if user else 'busy'

    if is_admin and not user:
        async with aiosqlite.connect(DB_FILE) as db:
            expiry = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, status, expiry_date, role) VALUES (?, ?, ?, ?, "busy", ?, "admin")', 
                             (user_id, "מנהל מערכת", "0000000000", "2000-01-01", expiry))
            await db.commit()
        user = await get_user(user_id)
        is_advertiser = True

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
                async with db.execute('SELECT status FROM leads WHERE lead_id = ?', (lead_id,)) as cursor:
                    lead = await cursor.fetchone()
                    if lead and lead[0] == 'active':
                        await state.update_data(active_lead_id=lead_id)
                        await state.set_state(BotStates.waiting_driver_time)
                        await message.answer("⏱️ **קריאה זו נקלטה!**\nאנא שלח כעת את **הזמן** שלך בכתובת (למשל: 15 דקות):")
        return

    if not user:
        if not message.from_user.username:
            await message.answer("⚠️ **שגיאה: אין לך שם משתמש (Username) בטלגרם!**\nחובה להגדיר שם משתמש לפני תחילת השימוש.")
            return
        await state.set_state(RegistrationStates.waiting_name)
        await message.answer("👋 שלום וברוכים הבאים לבוט הניהול והשילוח המתקדם! 🚀\n\nכדי להתחיל, אנא שלח את **השם המלא** שלך:")
        return

    if message.text in ["/start", "תפריט", "⬅️ חזרה לתפריט הראשי", "⬅ חזרה לתפריט הראשי"]:
        await state.clear()
        await message.answer("🎛️ **תפריט ראשי:** בחר אפשרות מהמקלדת למטה:", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    await message.answer("🎛️ **תפריט ראשי:** בחר אפשרות מהמקלדת למטה:", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))

# ניהול הודעות טקסט רגילות ומקלדות
@dp.message()
async def handle_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    user = await get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)
    role_val = user[5] if user else 'user'
    is_advertiser = is_admin or (role_val in ['admin', 'advertiser', 'station_manager', 'dispatcher'])
    current_status = user[3] if user else 'busy'
    current_state = await state.get_state()

    if text in ["/start", "תפריט", "⬅️ חזרה לתפריט הראשי", "⬅ חזרה לתפריט הראשי"]:
        await state.clear()
        await message.answer("🎛️ **תפריט ראשי:**", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    # מצבי רישום
    if current_state == RegistrationStates.waiting_name.state:
        await state.update_data(name=text)
        await state.set_state(RegistrationStates.waiting_phone)
        phone_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 שיתוף מספר טלפון", request_contact=True)]], resize_keyboard=True)
        await message.answer("תודה! כעת לחץ על הכפתור למטה כדי לשתף את מספר הטלפון שלך:", reply_markup=phone_kb)
        return

    if current_state == RegistrationStates.waiting_phone.state:
        phone = message.contact.phone_number if message.contact else text
        await state.update_data(phone=phone)
        await state.set_state(RegistrationStates.waiting_birth)
        await message.answer("מעולה! דבר אחרון: מהו **תאריך הלידה** שלך? (למשל: 15/05/1995):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]], resize_keyboard=True))
        return

    if current_state == RegistrationStates.waiting_birth.state:
        data = await state.get_data()
        role = 'admin' if is_admin else 'user'
        expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, status, expiry_date, role, radius, cities, total_trips, rating, rating_count)
                VALUES (?, ?, ?, ?, 'busy', ?, ?, 5, '', 0, 0.0, 0)
            ''', (user_id, data['name'], data['phone'], text, expiry, role))
            await db.commit()

        pending_lead = data.get('pending_lead')
        await state.clear()
        await message.answer("✅ **הרישום הושלם בהצלחה!**", reply_markup=get_main_keyboard(is_admin, is_admin or role == 'advertiser', 'busy'))
        if pending_lead:
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute('SELECT status FROM leads WHERE lead_id = ?', (pending_lead,)) as cursor:
                    lead = await cursor.fetchone()
                    if lead and lead[0] == 'active':
                        await state.update_data(active_lead_id=pending_lead)
                        await state.set_state(BotStates.waiting_driver_time)
                        await message.answer("⏱️ **קריאה זו נקלטה!**\nאנא שלח כעת את **הזמן** שלך בכתובת:")
        return

    # סטטוס פנוי / תפוס
    if text == "🟢 פנוי לקריאות":
        await state.set_state(BotStates.waiting_add_city)
        await message.answer(
            "🟢 מעבר למצב פנוי לקריאות:\n"
            "שלח כעת את שם העיר שבה אתה פנוי (למשל: ירושלים, או השתמש בקיצור 'פ א ירושלים').\n"
            "ניתן להוסיף עד 6 ערים במקביל ע\"י הוספה חוזרת.",
            reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status)
        )
        return

    if text == "🔴 תפוס":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET status = "busy", cities = "" WHERE user_id = ?', (user_id,))
            await db.commit()
        await message.answer("🔴 הסטטוס שלך עודכן לתפוס וכל אזורי הפעילות שלך אופסו במערכת.", reply_markup=get_main_keyboard(is_admin, is_advertiser, 'busy'))
        return

    if current_state == BotStates.waiting_add_city.state or text.startswith("פ א ") or text.startswith("פא "):
        city_name = text.replace("פ א ", "").replace("פא ", "").strip() if (text.startswith("פ א ") or text.startswith("פא ")) else text
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute('SELECT cities FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
            current_cities_str = row[0] if row and row[0] else ""
            cities_list = [c.strip() for c in current_cities_str.split(',') if c.strip()]
            if city_name not in cities_list:
                cities_list.append(city_name)
            updated_str = ", ".join(cities_list)
            await db.execute('UPDATE users SET cities = ?, status = "free" WHERE user_id = ?', (updated_str, user_id))
            await db.commit()
        await state.clear()
        await message.answer(f"✅ זוהה אזור פעילות!\n📍 הערים שלך כעת: {updated_str}", reply_markup=get_main_keyboard(is_admin, is_advertiser, 'free'))
        return

    # אזורים ורדיוס
    if text == "⚙️ הגדרת אזורים ורדיוס":
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="➕ הוסף עיר נוספת"), KeyboardButton(text="🗑️ מחק עיר ספציפית")],
            [KeyboardButton(text="🗑️ מחק את כל הערים (איפס הכל)"), KeyboardButton(text="📏 שנה רדיוס קילומטרים")],
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
        await message.answer("🗑️ כל אזורי הפעילות שלך נמחקו והסטטוס שלך אופס לתפוס מלא.", reply_markup=get_main_keyboard(is_admin, is_advertiser, 'busy'))
        return

    if text == "📏 שנה רדיוס קילומטרים":
        await state.set_state(BotStates.waiting_new_radius)
        await message.answer("📏 שלח כעת את מספר הקילומטרים הרצוי לרדיוס הנסיעה (למשל: 10):")
        return

    if current_state == BotStates.waiting_new_radius.state:
        try:
            new_rad = int(text)
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('UPDATE users SET radius = ? WHERE user_id = ?', (new_rad, user_id))
                await db.commit()
            await state.clear()
            await message.answer(f"✅ רדיוס הנסיעה שלך עודכן וסונכרן ל-{new_rad} ק\"מ.", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))
        except:
            await message.answer("⚠️ נא להזין מספר שלם תקין:")
        return

    # פרופיל ומנוי
    if text == "💎 מצב מנוי ופרופיל":
        u_data = await get_user(user_id)
        u_name = u_data[0] if u_data else "לא ידוע"
        u_role = u_data[5] if u_data else "user"
        radius_val = u_data[7] if u_data else 5
        cities_val = u_data[8] if u_data else ""
        total_trips = u_data[9] if u_data and len(u_data) > 9 else 0
        u_rating = u_data[10] if u_data and len(u_data) > 10 else 0.0

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT amount, is_paid FROM driver_debts WHERE user_id = ?", (user_id,)) as cursor:
                debts = await cursor.fetchall()
        total_debt = sum([d[0] for d in debts if not d[1]])

        await message.answer(
            f"💎 **האזור האישי והפרופיל שלך:**\n\n"
            f"👤 שם מלא: {u_name}\n"
            f"🛡️ תפקיד במערכת: **{u_role}**\n"
            f"📦 סך נסיעות/משלוחים שבוצעו: {total_trips}\n"
            f"⭐ דירוג ממוצע: {u_rating:.1f} כוכבים\n"
            f"💳 סך חובות פתוחים לתחנות: ₪{total_debt:.2f}\n\n"
            f"📍 ערים פעילות: {cities_val if cities_val else 'לא הוגדר'}\n"
            f"📏 רדיוס: {radius_val} ק\"מ\n"
            f"🟢 סטטוס: {'פנוי' if current_status == 'free' else 'תפוס'}",
            reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status)
        )
        return

    # אודות ויצירת קשר
    if text == "ℹ️ אודות ויצירת קשר":
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="ℹ️ אודות המערכת"), KeyboardButton(text="📞 יצירת קשר")],
            [KeyboardButton(text="⬅️ חזרה לתפריט הראשי")]
        ], resize_keyboard=True)
        await message.answer("ℹ️ **אודות ויצירת קשר:**\nבחר את האפשרות הרצויה:", reply_markup=kb)
        return

    if text == "ℹ️ אודות המערכת":
        await message.answer("ℹ️ מערכת שילוח וניהול חכמה בטלגרם לניהול תחנות, סדרנים ושליחים.", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    if text == "📞 יצירת קשר":
        await message.answer("📞 **יצירת קשר עם ההנהלה:**\nלפניות ותמיכה פנה למנהל המערכת.", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    # פאנל מנהל וקריאות
    if text in ["🛠️ פאנל מנהל", "פאנל מנהל"] and is_admin:
        await message.answer("🛠️ פאנל ניהול ראשי:", reply_markup=get_admin_keyboard())
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
        await message.answer("📢 **שידור הודעה לכל משתמשים במערכת:**\nשלח כעת את טקסט ההודעה שתרצה לשדר:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ חזרה לפאנל מנהל")]], resize_keyboard=True))
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
        st_text = "🏢 **ניהול תחנות שילוח:**\n\n"
        st_buttons = [
            [InlineKeyboardButton(text="➕ הוסף תחנה חדשה", callback_data="add_new_station")],
            [InlineKeyboardButton(text="📊 סטטיסטיקות תחנות", callback_data="station_stats")]
        ]
        if not stations:
            st_text += "• אין תחנות רשומות."
        else:
            for s_id, s_name, s_comm in stations:
                st_text += f"• {s_name} (עמלה: {s_comm}%)\n"
                st_buttons.append([InlineKeyboardButton(text=f"⚙️ ע/מ תחנה: {s_name}", callback_data=f"manage_station_{s_id}")])
        await message.answer(st_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=st_buttons))
        return

    # ניהול קבוצות הבוט
    if text == "⚙️ ניהול קבוצות הבוט" and is_admin:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute('SELECT group_id, group_title, is_active FROM bot_groups') as cursor:
                groups = await cursor.fetchall()
        if not groups:
            await message.answer("⚠️ הבוט עדיין אינו מחובר לאף קבוצה. הוסף את הבוט לקבוצות טלגרם והפוך אותו למנהל.")
            return
        g_text = "🏢 **ניהול קבוצות מחוברות לבוט:**\n\n"
        g_buttons = []
        for g_id, g_title, is_active in groups:
            status_icon = "🟢 פעילה" if is_active else "🔴 מושבתת"
            g_text += f"• {g_title} | {status_icon}\n"
            btn_txt = f"🔴 השבת: {g_title[:12]}" if is_active else f"🟢 הפעל: {g_title[:12]}"
            g_buttons.append([InlineKeyboardButton(text=btn_txt, callback_data=f"toggle_group_{g_id}")])
        await message.answer(g_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=g_buttons))
        return

    # פרסום הודעה (סדרנים ומנהלים)
    if text == "📢 פרסום הודעה" and is_advertiser:
        await state.set_state(BotStates.waiting_lead_text)
        await message.answer("📢 פרסום קריאה חדשה:\nשלח כעת את **תוכן הקריאה** (מסלול ומחיר):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ ביטול")]], resize_keyboard=True))
        return

    if current_state == BotStates.waiting_lead_text.state and is_advertiser:
        if text == "❌ ביטול":
            await state.clear()
            await message.answer("❌ פעולת הפרסום בוטלה.", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))
            return
        await state.update_data(lead_text=text)
        await state.set_state(BotStates.waiting_lead_phone)
        await message.answer("📞 אנא שלח את **מספר הטלפון של הלקוח** שיוצג בקריאה:")
        return

    if current_state == BotStates.waiting_lead_phone.state and is_advertiser:
        if text == "❌ ביטול":
            await state.clear()
            await message.answer("❌ פעולת הפרסום בוטלה.", reply_markup=get_main_keyboard(is_admin, is_advertiser, current_status))
            return
        await state.update_data(lead_phone=text)
        
        dest_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 למשתמשי הבוט הפרטיים בלבד", callback_data="dest_users")],
            [InlineKeyboardButton(text="🏢 לקבוצות הבוט בלבד", callback_data="dest_groups")],
            [InlineKeyboardButton(text="🚀 גם למשתמשים וגם לקבוצות", callback_data="dest_both")],
            [InlineKeyboardButton(text="❌ ביטול", callback_data="dest_cancel")]
        ])
        await message.answer("🎯 **בחר לאן לפרסם את הקריאה:**", reply_markup=dest_kb)
        return

# קולבק קבוצות בוט
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
            async with db.execute('SELECT group_id, group_title, is_active FROM bot_groups') as cursor:
                groups = await cursor.fetchall()
            text = "🏢 **ניהול קבוצות מחוברות לבוט:**\n\n"
            buttons = []
            for gid, gtitle, iactive in groups:
                s_icon = "🟢 פעילה" if iactive else "🔴 מושבתת"
                text += f"• {gtitle} | {s_icon}\n"
                b_txt = f"🔴 השבת: {gtitle[:12]}" if iactive else f"🟢 הפעל: {gtitle[:12]}"
                buttons.append([InlineKeyboardButton(text=b_txt, callback_data=f"toggle_group_{gid}")])
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# קולבק בחירת יעדי פרסום
@dp.callback_query(F.data.startswith("dest_"))
async def destination_chosen(callback: CallbackQuery, state: FSMContext):
    action = callback.data.replace("dest_", "")
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ פרסום הקריאה בוטל.")
        return

    data = await state.get_data()
    text_content = data.get('lead_text')
    phone_content = data.get('lead_phone')
    user_id = callback.from_user.id

    pub_user_data = await get_user(user_id)
    st_id = pub_user_data[6] if pub_user_data else None

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
    await callback.message.edit_text(f"✅ קריאה #{lead_id} נוצרה ונשלחת ליעדים שנבחרו!")

    pub_fullname = pub_user_data[0] if pub_user_data else "סדרן"
    station_name = "כללי"
    if st_id:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute('SELECT station_name FROM stations WHERE station_id = ?', (st_id,)) as cursor:
                st_row = await cursor.fetchone()
                if st_row:
                    station_name = st_row[0]

    alert_msg = (
        f"🚀 **קריאה חדשה זמינה! (#{lead_id})**\n\n"
        f"📍 מסלול: {' ➔ '.join(cities) if cities else 'כללי'}\n"
        f"💰 מחיר: ₪{price if price else 'לא זוהה'}\n\n"
        f"📝 **פרטים:**\n{text_content}\n\n"
        f"🏢 תחנה: {station_name} | סדרן: {pub_fullname}"
    )

    sent_users = 0
    sent_groups = 0

    if action in ["users", "both"]:
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id, cities FROM users WHERE status = 'free'") as cursor:
                free_users = await cursor.fetchall()
        for f_uid, f_cities in free_users:
            matched = False
            if not cities:
                matched = True
            else:
                user_cities_list = [c.strip() for c in f_cities.split(',') if c.strip()]
                for l_city in cities:
                    if l_city in user_cities_list:
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

    await bot.send_message(user_id, f"📢 הקריאה הופצה בהצלחה ל-{sent_users} שליחים פרטיים ו-{sent_groups} קבוצות ציבוריות!")

# בקשת קריאה
@dp.callback_query(F.data.startswith("req_lead_"))
async def request_lead_callback(callback: CallbackQuery, state: FSMContext):
    lead_id = int(callback.data.replace("req_lead_", ""))
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT publisher_id, message_text, phone_number, status, price, route_cities FROM leads WHERE lead_id = ?', (lead_id,)) as cursor:
            lead = await cursor.fetchone()

    if not lead or lead[3] != 'active':
        await callback.answer("⚠️ קריאה זו אינה פעילה עוד או סגורה.", show_alert=True)
        return

    _, _, _, _, _, has_time = parse_order_text(lead[1])
    if has_time:
        await state.update_data(active_lead_id=lead_id)
        await state.set_state(BotStates.waiting_driver_time)
        await callback.message.answer("⏱️ קריאה זו דורשת זמן הגעה. אנא שלח בצ'אט את הזמן שלך בכתובת (למשל: 15 דקות):")
        await callback.answer()
    else:
        await process_lead_request(callback.message, user_id, lead_id, "לא צוין זמן")
        await callback.answer("הבקשה נשלחה למפרסם בהצלחה!")

@dp.message(BotStates.waiting_driver_time)
async def receive_driver_time(message: Message, state: FSMContext):
    data = await state.get_data()
    lead_id = data.get('active_lead_id')
    driver_time = message.text.strip()
    await state.clear()
    await message.answer("✅ בקשתך נשלחה בהצלחה למפרסם!")
    await process_lead_request(message, message.from_user.id, lead_id, driver_time)

async def process_lead_request(message: Message, requester_id: int, lead_id: int, driver_time: str):
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
    req_username = f"@{requester.username}" if requester.username else "אין יוזר"
    req_radius = requester_user[7] if requester_user else 5
    req_cities = requester_user[8] if requester_user else ""
    req_rating = requester_user[10] if requester_user and len(requester_user) > 10 else 0.0

    alert_to_publisher = (
        f"🔔 **התקבלה בקשה לקריאה #{lead_id}**\n\n"
        f"📍 מסלול: {route_cities if route_cities else 'לא זוהה'}\n"
        f"💰 מחיר: ₪{price if price else 'לא זוהה'}\n"
        f"⏱️ זמן: {driver_time}\n"
        f"📝 **הודעה:** {message_text[:50]}...\n\n"
        f"👤 **פרטי המבקש ומוניטין:**\n"
        f"• שם: {req_name}\n"
        f"• יוזר: {req_username}\n"
        f"• טלפון: {req_phone}\n"
        f"• ערים מוגדרות: `{req_cities}`\n"
        f"• רדיוס נסיעה: {req_radius} ק\"מ\n"
        f"• דירוג: ⭐ {req_rating:.1f}\n\n"
        f"האם לאשר את הפנייה?"
    )

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ אישור וסגירת קריאה", callback_data=f"app_close_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="✅ אישור בלבד", callback_data=f"app_only_{lead_id}_{requester_id}")],
        [InlineKeyboardButton(text="❌ דחייה", callback_data=f"rej_lead_{lead_id}_{requester_id}")]
    ])

    await bot.send_message(publisher_id, alert_to_publisher, reply_markup=buttons)

async def main():
    await init_db()
    print("✨ בוט השילוח והניהול (גרסת aiogram המלאה) פועל בהצלחה!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
