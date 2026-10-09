import os
import asyncio
import logging
import sys
import re
from datetime import datetime
import aiosqlite
from aiohttp import web

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command


logging.basicConfig(level=logging.INFO)

# ----------------- תצורת שרת וטוקן -----------------
RAW_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_TOKEN = RAW_TOKEN.strip().replace(" ", "")

if not BOT_TOKEN:
    logging.error("No token provided!")
    sys.exit(1)

ADMIN_IDS = [8644923212, 552821474]
DB_FILE = 'erp_master_complete.db'

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
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

# ----------------- מסד נתונים -----------------
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT, birth_year INTEGER, 
            car_brand TEXT, car_model TEXT, car_year INTEGER, car_seats INTEGER, 
            status TEXT DEFAULT 'busy', role TEXT DEFAULT 'user', station_id INTEGER DEFAULT 0, 
            rating REAL DEFAULT 5.0, total_trips INTEGER DEFAULT 0, is_blocked INTEGER DEFAULT 0, 
            debt_balance REAL DEFAULT 0.0, sub_expiry TEXT)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS stations (
            station_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, commission_percent REAL DEFAULT 10.0)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, price REAL,
            publisher_id INTEGER, station_id INTEGER, driver_id INTEGER, status TEXT DEFAULT 'open', created_at TEXT)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS debts (
            debt_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, driver_id INTEGER,
            station_id INTEGER, amount REAL, status TEXT DEFAULT 'unpaid', reason TEXT)''')

        await db.execute('''CREATE TABLE IF NOT EXISTS driver_cities (
            user_id INTEGER, city_name TEXT, PRIMARY KEY(user_id, city_name))''')

        await db.execute('''CREATE TABLE IF NOT EXISTS bot_groups (
            group_id INTEGER PRIMARY KEY, group_name TEXT)''')
            
        await db.execute('INSERT OR IGNORE INTO stations (station_id, name, commission_percent) VALUES (1, "תחנה ראשית", 10.0)')
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))).fetchone()

# ----------------- Keep-Alive (UptimeRobot) -----------------
async def handle_ping(request):
    return web.Response(text="ERP Master Alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ----------------- מקלדות ועזרים -----------------
def get_main_kb(role='user', status='busy'):
    kb = []
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
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('''INSERT OR IGNORE INTO users 
                (user_id, full_name, phone, birth_year, car_brand, car_model, car_year, role, station_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                (user_id, "מנהל מערכת", "0500000000", 1990, "מנהל", "מנהל", 2024, "admin", 1))
            await db.execute('UPDATE users SET role = "admin" WHERE user_id = ?', (user_id,))
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
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_year, car_brand, car_model, car_year, car_seats, role) 
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
    async with aiosqlite.connect(DB_FILE) as db:
        cities = await (await db.execute("SELECT city_name FROM driver_cities WHERE user_id = ?", (message.from_user.id,))).fetchall()
    
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
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO driver_cities (user_id, city_name) VALUES (?, ?)", (message.from_user.id, message.text.strip()))
        await db.commit()
    await state.clear()
    user = await get_user(message.from_user.id)
    await message.answer(f"✅ העיר {message.text} נוספה בהצלחה.", reply_markup=get_main_kb(user['role'], user['status']))

@router.callback_query(F.data == "clear_cities")
async def clear_cities(call: CallbackQuery):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM driver_cities WHERE user_id = ?", (call.from_user.id,))
        await db.commit()
    await call.message.edit_text("✅ כל הערים נמחקו. לא תקבל קריאות עד שתוסיף ערים חדשות.")
    await call.answer()

@router.message(F.text.in_(["🟢 פנוי לעבודה", "🔴 תפוס (עצור קריאות)"]))
async def toggle_status(message: Message):
    user = await get_user(message.from_user.id)
    # אכיפת חובות Auto-Freeze
    if user['debt_balance'] > 500.0:
        return await message.answer("🚫 **חשבונך מוקפא עקב חובות (מעל 500 ש\"ח)!** לא תוכל לקבל קריאות עד הסדרת החוב.")
    
    new_status = 'free' if user['status'] == 'busy' else 'busy'
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE users SET status = ? WHERE user_id = ?', (new_status, message.from_user.id))
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
    
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('INSERT INTO orders (text, price, publisher_id, station_id, created_at) VALUES (?, ?, ?, ?, ?)', 
                                  (order_text, data['est_price'], user['user_id'], user['station_id'], datetime.now().isoformat()))
        order_id = cursor.lastrowid
        await db.commit()
        
    order_msg = f"🎫 **קריאה #{order_id}**\n🏢 סדרן: {user['full_name']}\n\n{order_text}\n\n💵 סכום: {data['est_price']} ש\"ח"
    
    if message.text == "לנהגים בפרטי":
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            # שליפת הנהגים הפנויים, ללא חסימות וללא חוב חריג
            all_drivers = await (await db.execute("SELECT user_id FROM users WHERE status = 'free' AND role = 'user' AND is_blocked = 0 AND debt_balance <= 500")).fetchall()
            
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚗 קח קריאה", callback_data=f"take_{order_id}")]])
        sent = 0
        for d in all_drivers:
            # סינון חכם לפי עיר (התאמת תוכן הקריאה לאזורי הנהג)
            async with aiosqlite.connect(DB_FILE) as db:
                driver_cities = await (await db.execute("SELECT city_name FROM driver_cities WHERE user_id = ?", (d['user_id'],))).fetchall()
            
            should_send = False
            if not driver_cities:
                should_send = True # אם לא הגדיר ערים, יקבל הכל
            else:
                for city_row in driver_cities:
                    if city_row[0] in order_text:
                        should_send = True
                        break
                        
            if should_send:
                try: 
                    await bot.send_message(d['user_id'], order_msg, reply_markup=kb)
                    sent += 1
                except: pass
        await message.answer(f"✅ שוגר ל-{sent} נהגים בפרטי (סונן לפי אזורי העבודה שלהם).", reply_markup=get_main_kb(user['role'], user['status']))
    
    elif message.text == "לקבוצות (חיצוני)":
        async with aiosqlite.connect(DB_FILE) as db:
            groups = await (await db.execute("SELECT group_id FROM bot_groups")).fetchall()
        sent = 0
        for g in groups:
            try:
                await bot.send_message(g[0], order_msg)
                sent += 1
            except: pass
        await message.answer(f"✅ שוגר ל-{sent} קבוצות מוגדרות במערכת.", reply_markup=get_main_kb(user['role'], user['status']))
    
    await state.clear()

# ----------------- ניהול מצב קריאות (לסדרן) -----------------
@router.message(F.text == "📋 מצב קריאות")
async def show_open_orders(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'station_manager', 'dispatcher']: return
    
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # מידור נתונים: הסדרן רואה אך ורק קריאות של התחנה שלו שעדיין פתוחות
        orders = await (await db.execute("SELECT * FROM orders WHERE station_id = ? AND status = 'open'", (user['station_id'],))).fetchall()
        
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
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE orders SET status = "deleted" WHERE order_id = ?', (order_id,))
        await db.commit()
    await call.message.edit_text(f"✅ קריאה #{order_id} נסגרה/נמחקה מהמערכת.")
    await call.answer()
    
# ----------------- קבלת קריאה, ETA ומיזוג -----------------
@router.callback_query(F.data.startswith("take_"))
async def take_order(call: CallbackQuery, state: FSMContext):
    order_id = call.data.split("_")[1]
    
    # נוודא שהנהג פנוי
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
    
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        order = await (await db.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))).fetchone()
        
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
    except:
        pass
        
    await state.clear()
    await message.answer("⏳ הבקשה נשלחה בהצלחה לסדרן. המתנה לאישור...", reply_markup=get_main_kb(driver['role'], driver['status']))

# ----------------- סדרן מאשר/דוחה, חיוב עמלה ודירוג -----------------
@router.callback_query(F.data.startswith("deny_"))
async def deny_driver(call: CallbackQuery):
    _, order_id, driver_id = call.data.split("_")
    await bot.send_message(driver_id, f"❌ לצערנו הסדרן דחה את בקשתך לקריאה #{order_id}. נסה קריאה אחרת.")
    await call.message.edit_text(f"❌ דחית את הנהג לקריאה #{order_id}. ההודעה נשלחה אליו.")
    await call.answer()

@router.callback_query(F.data.startswith("approve_"))
async def approve_driver(call: CallbackQuery):
    _, order_id, driver_id = call.data.split("_")
    
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        order = await (await db.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))).fetchone()
        
        if order['status'] != 'open':
            return await call.answer("⚠️ הקריאה כבר נסגרה!", show_alert=True)
            
        station = await (await db.execute('SELECT commission_percent FROM stations WHERE station_id = ?', (order['station_id'],))).fetchone()
        
        # עדכון סטטוס קריאה
        await db.execute('UPDATE orders SET status = "closed", driver_id = ? WHERE order_id = ?', (driver_id, order_id))
        
        # חישוב עמלה אוטומטי (סעיף 17)
        commission_rate = station['commission_percent'] if station else 10.0
        debt_amount = order['price'] * (commission_rate / 100)
        
        if debt_amount > 0:
            await db.execute('INSERT INTO debts (order_id, driver_id, station_id, amount, reason) VALUES (?, ?, ?, ?, ?)', 
                             (order_id, driver_id, order['station_id'], debt_amount, f"עמלה {commission_rate}%"))
            await db.execute('UPDATE users SET debt_balance = debt_balance + ?, total_trips = total_trips + 1 WHERE user_id = ?', (debt_amount, driver_id))
        else:
            await db.execute('UPDATE users SET total_trips = total_trips + 1 WHERE user_id = ?', (driver_id,))
            
        await db.commit()
        
    await bot.send_message(driver_id, f"🎉 **אושרת לקריאה #{order_id}!**\nסע בזהירות.\n(חויבת בעמלה של {debt_amount} ש\"ח לתחנה)")
    
    # בקשת דירוג לנהג (סעיף 20)
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
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        driver = await (await db.execute('SELECT rating, total_trips FROM users WHERE user_id = ?', (driver_id,))).fetchone()
        
        # חישוב ממוצע חדש
        current_trips = max(driver['total_trips'], 1)
        new_rating = round(((driver['rating'] * (current_trips - 1)) + stars) / current_trips, 1)
        
        await db.execute('UPDATE users SET rating = ? WHERE user_id = ?', (new_rating, driver_id))
        await db.commit()
        
    await call.message.edit_text(f"✅ דירגת את הנהג ב-{stars} כוכבים. המערכת עודכנה.")
    await call.answer()

# ----------------- מערכת ERP: ניהול חובות וערעורים (סעיף 5) -----------------
@router.message(F.text == "💳 חיובים וערעורים")
async def show_debts(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        debts = await (await db.execute("SELECT * FROM debts WHERE driver_id = ? AND status = 'unpaid'", (message.from_user.id,))).fetchall()
        
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
    
    # שלח למנהלי המערכת 
    for admin_id in ADMIN_IDS:
        try: await bot.send_message(admin_id, appeal_msg, reply_markup=admin_kb)
        except: pass
            
    await state.clear()
    await message.answer("✅ הערעור נשלח להנהלה לבדיקה. תקבל עדכון בקרוב.", reply_markup=get_main_kb(driver['role'], driver['status']))

@router.callback_query(F.data.startswith("deldebt_"))
async def admin_del_debt(call: CallbackQuery):
    _, debt_id, driver_id = call.data.split("_")
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        debt = await (await db.execute('SELECT amount, status FROM debts WHERE debt_id = ?', (debt_id,))).fetchone()
        
        if debt and debt['status'] == 'unpaid':
            await db.execute('UPDATE debts SET status = "cancelled" WHERE debt_id = ?', (debt_id,))
            await db.execute('UPDATE users SET debt_balance = debt_balance - ? WHERE user_id = ?', (debt['amount'], driver_id))
            await db.commit()
            await bot.send_message(driver_id, f"✅ **הערעור התקבל!** חוב של {debt['amount']} ש\"ח (עבור חיוב #{debt_id}) בוטל.")
            await call.message.edit_text(f"✅ אישרת את הערעור ומחקת את חוב #{debt_id}.")
        else:
            await call.message.edit_text(f"⚠️ החוב #{debt_id} כבר טופל או שולם.")
    await call.answer()

@router.callback_query(F.data.startswith("keepdebt_"))
async def admin_keep_debt(call: CallbackQuery):
    _, debt_id, driver_id = call.data.split("_")
    await bot.send_message(driver_id, f"❌ **הערעור נדחה!** חיוב #{debt_id} נשאר בעינו ויש להסדירו מול התחנה.")
    await call.message.edit_text(f"❌ דחית את הערעור על חוב #{debt_id}. החוב נשאר.")
    await call.answer()
# ----------------- God Mode וניהול תחנות (סעיפים 12, 19) -----------------
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
    except: return await message.answer("⚠️ נא להזין מספר.")
    
    data = await state.get_data()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('INSERT INTO stations (name, commission_percent) VALUES (?, ?)', (data['new_station_name'], comm))
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

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE users SET role = ?, station_id = ?, is_blocked = ? WHERE user_id = ?', 
                         (role_to_save, int(station_id), is_blocked, int(target_id)))
        await db.commit()
        
    await state.clear()
    await message.answer(f"✅ המשתמש {target_id} עודכן בהצלחה לתפקיד {new_role} בתחנה {station_id}.", reply_markup=get_main_kb('admin', 'busy'))
    
    try:
        await bot.send_message(int(target_id), f"🔄 **עדכון מערכת:**\nההרשאות שלך עודכנו על ידי ההנהלה.\nתפקיד נוכחי: {new_role}")
    except: pass

# --- שידור גלובלי (Broadcast) ---
@router.callback_query(F.data == "god_broadcast")
async def god_broadcast_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFlow.waiting_broadcast)
    await call.message.answer("📢 הקלד את ההודעה שתשודר **לכל המשתמשים במערכת** (נהגים, סדרנים ומנהלים):", reply_markup=cancel_kb())
    await call.answer()

@router.message(AdminFlow.waiting_broadcast)
async def god_broadcast_send(message: Message, state: FSMContext):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        users = await (await db.execute("SELECT user_id FROM users")).fetchall()
        
    sent = 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], f"📢 **הודעת הנהלה מיוחדת:**\n\n{message.text}")
            sent += 1
        except: pass
    await state.clear()
    await message.answer(f"✅ ההודעה שודרה בהצלחה ל-{sent} משתמשים.", reply_markup=get_main_kb('admin', 'busy'))

@router.callback_query(F.data == "mgr_dummy")
async def mgr_dummy(call: CallbackQuery):
    await call.answer("פעולה זו מבוצעת על ידי הנהלת המערכת.", show_alert=True)

# ----------------- הרצה (Main Loop) -----------------
async def main():
    await init_db()
    await start_web_server()
    print("🚀 MASTER ERP COMPLETE IS LIVE! ALL MODULES LOADED.")
    # השתקת שגיאות אם הבוט נסגר לא טוב בפעם הקודמת (Drop pending updates)
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped safely.")
