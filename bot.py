import os
import sqlite3
import asyncio
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.custom import Button

api_id = int(os.environ.get("API_ID", "36364878"))
api_hash = os.environ.get("API_HASH", "c9d51bb77653adefd4e5092581145cb3")
bot_token = os.environ.get("BOT_TOKEN")
from telethon.sessions import StringSession
string_session = os.environ.get("STRING_SESSION")
client = TelegramClient(StringSession(string_session), api_id, api_hash)

ADMIN_IDS = [8644923212, 552821474]
DB_FILE = 'bot_database_v2.db'

active_broadcasts = {}

CITY_ALIASES = {
    "ים": "ירושלים",
    "פת" : "פתח תקווה",
    "תא" : "תל אביב",
    "שדה" : "שדה תעופה",
    "סבא" : "כפר סבא",
    "ראשון" : "ראשון לציון",
    "רג" : "רמת גן",
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

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            birth_date TEXT,
            status TEXT DEFAULT 'busy',
            expiry_date TEXT,
            role TEXT DEFAULT 'user'
        )
    ''')
    
    existing_columns = [col[1] for col in cursor.execute("PRAGMA table_info(users)").fetchall()]
    if 'station_id' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN station_id INTEGER")
    if 'radius' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN radius INTEGER DEFAULT 5")
    if 'cities' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN cities TEXT DEFAULT ''")
    if 'total_trips' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN total_trips INTEGER DEFAULT 0")
    if 'stars_silver' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN stars_silver INTEGER DEFAULT 0")
    if 'stars_gold' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN stars_gold INTEGER DEFAULT 0")
    if 'rating' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN rating REAL DEFAULT 0.0")
    if 'rating_count' not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN rating_count INTEGER DEFAULT 0")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stations (
            station_id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_name TEXT,
            owner_id INTEGER,
            commission_percent REAL DEFAULT 10.0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS allowed_groups (
            group_id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_identifier TEXT,
            group_name TEXT
        )
    ''')

    cursor.execute('''
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            user_id INTEGER,
            word TEXT
        )
    ''')
    
    cursor.execute('''
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
    
    lead_columns = [col[1] for col in cursor.execute("PRAGMA table_info(leads)").fetchall()]
    if 'station_id' not in lead_columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN station_id INTEGER DEFAULT NULL")

    conn.commit()
    conn.close()

init_db()

# שני הלקוחות נשמרים במלואם כפי שהיו:
client = TelegramClient(StringSession(string_session), api_id, api_hash)
bot_client = TelegramClient(StringSession(), api_id, api_hash)

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
            numbers = re.findall(r'\b\d+\b', line)
            for num_str in numbers:
                num = int(num_str)
                if num >= 30 and num % 10 == 0:
                    price = float(num)
                    break
            if price:
                break

    has_time_mention = bool(re.search(r'זמנ[ן]{1,6}|זמני[ם]{1,6}', text) or re.search(r'זמן[ן]{1,6}', text))
    return found_cities, price, has_time_mention

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT full_name, phone, birth_date, status, expiry_date, role, station_id, radius, cities, total_trips, rating, rating_count FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def register_user(user_id, full_name, phone, birth_date, role='user', station_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, full_name, phone, birth_date, status, expiry_date, role, station_id, radius, cities, total_trips, rating, rating_count)
        VALUES (?, ?, ?, ?, 'busy', ?, ?, ?, 5, '', 0, 0.0, 0)
    ''', (user_id, full_name, phone, birth_date, expiry, role, station_id))
    conn.commit()
    conn.close()

def update_user_status(user_id, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if status == 'busy':
        cursor.execute('UPDATE users SET status = ?, cities = "" WHERE user_id = ?', (status, user_id))
    else:
        cursor.execute('UPDATE users SET status = ? WHERE user_id = ?', (status, user_id))
    conn.commit()
    conn.close()

def update_user_radius(user_id, radius):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET radius = ? WHERE user_id = ?', (radius, user_id))
    conn.commit()
    conn.close()

def add_user_city(user_id, new_city):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT cities FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    current_cities_str = row[0] if row and row[0] else ""
    
    cities_list = [c.strip() for c in current_cities_str.split(',') if c.strip()]
    if new_city not in cities_list:
        if len(cities_list) >= 6:
            conn.close()
            return False, "הגעת למקסימום המותר של 6 מיקומים במקביל."
        cities_list.append(new_city)
    
    updated_str = ", ".join(cities_list)
    cursor.execute('UPDATE users SET cities = ?, status = "free" WHERE user_id = ?', (updated_str, user_id))
    conn.commit()
    conn.close()
    return True, updated_str

def remove_user_city(user_id, city_to_remove):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT cities FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    current_cities_str = row[0] if row and row[0] else ""
    
    cities_list = [c.strip() for c in current_cities_str.split(',') if c.strip()]
    if city_to_remove in cities_list:
        cities_list.remove(city_to_remove)
    
    updated_str = ", ".join(cities_list)
    cursor.execute('UPDATE users SET cities = ? WHERE user_id = ?', (updated_str, user_id))
    conn.commit()
    conn.close()
    return updated_str

def update_user_role_and_expiry(user_id, role, expiry_date, station_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if station_id is not None:
        cursor.execute('UPDATE users SET role = ?, expiry_date = ?, station_id = ? WHERE user_id = ?', (role, expiry_date, station_id, user_id))
    else:
        cursor.execute('UPDATE users SET role = ?, expiry_date = ? WHERE user_id = ?', (role, expiry_date, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, full_name, phone, role, expiry_date, station_id FROM users')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_keywords(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT word FROM keywords WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def add_user_keyword(user_id, word):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO keywords (user_id, word) VALUES (?, ?)', (user_id, word))
    conn.commit()
    conn.close()

def clear_user_keywords(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM keywords WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def delete_specific_keyword(user_id, word):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM keywords WHERE user_id = ? AND word = ?', (user_id, word))
    conn.commit()
    conn.close()

def save_lead(publisher_id, message_text, phone_number, station_id=None):
    cities, price, has_time = parse_order_text(message_text)
    route_str = " ➔ ".join(cities) if cities else ""
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO leads (publisher_id, message_text, phone_number, created_at, price, route_cities, station_id) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (publisher_id, message_text, phone_number, now_str, price if price else 0.0, route_str, station_id))
    lead_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return lead_id, cities, price, has_time

def get_lead(lead_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT publisher_id, message_text, phone_number, status, closed_with, price, route_cities, station_id FROM leads WHERE lead_id = ?', (lead_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_lead_status(lead_id, status, closed_with=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE leads SET status = ?, closed_with = ? WHERE lead_id = ?', (status, closed_with, lead_id))
    conn.commit()
    conn.close()

def get_all_system_leads():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT lead_id, publisher_id, message_text, phone_number, status, closed_with FROM leads ORDER BY lead_id DESC LIMIT 20')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_system_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM leads")
    total_leads = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM leads WHERE status='closed'")
    closed_leads = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM leads WHERE status='deleted'")
    deleted_leads = cursor.fetchone()[0]

    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM leads WHERE created_at LIKE ?", (f"{today_str}%",))
    today_leads = cursor.fetchone()[0]

    conn.close()
    return total_users, total_leads, closed_leads, deleted_leads, today_leads

user_states = {}
broadcast_data = {}
group_broadcast_data = {}
station_creation_data = {}

def get_main_keyboard(is_admin=False, is_advertiser=False, current_status='busy'):
    status_btn_text = "🟢 פנוי" if current_status == 'free' else "🔴 תפוס"
    kb = []
    
    if is_admin or is_advertiser:
        kb.append([Button.text("📢 פרסום הודעה", resize=True), Button.text("📋 מצב קריאות", resize=True)])
        
    kb.append([Button.text(status_btn_text, resize=True), Button.text("⚙️ הגדרת אזורים ורדיוס", resize=True)])
    kb.append([Button.text("🔍 ניטור קבוצות ומילים", resize=True), Button.text("💎 מצב מנוי ופרופיל", resize=True)])
    kb.append([Button.text("ℹ️ אודות ויצירת קשר", resize=True)])
    
    if is_admin:
        kb.append([Button.text("🛠️ פאנל מנהל", resize=True)])
    return kb

def get_admin_keyboard():
    return [
        [Button.text("👥 ניהול משתמשים", resize=True), Button.text("📊 סטטיסטיקות מערכת", resize=True)],
        [Button.text("📢 שידור הודעה לכולם", resize=True), Button.text("🏢 ניהול תחנות וקבוצות", resize=True)],
        [Button.text("⬅ חזרה לתפריט הראשי", resize=True)]
    ]

@bot_client.on(events.NewMessage(incoming=True))
async def bot_listener(event):
    user_id = event.sender_id
    text = event.message.text.strip() if event.message.text else ""
    user = get_user(user_id)
    is_admin = (user_id in ADMIN_IDS)
    role_val = user[5] if user else 'user'
    is_advertiser = is_admin or (role_val in ['admin', 'advertiser', 'station_manager', 'dispatcher'])
    current_status = user[3] if user else 'busy'

    if is_admin and not user:
        register_user(user_id, "מנהל מערכת", "0000000000", "2000-01-01", role='admin')
        user = get_user(user_id)
        is_advertiser = True

    if text in ["/start", "תפריט", "⬅️ חזרה לתפריט הראשי", "⬅ חזרה לתפריט הראשי"]:
        user_states.pop(user_id, None)
        await event.respond("🎛️ **תפריט ראשי:** בחר אפשרות מהמקלדת למטה:", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    if text.startswith("/start lead_"):
        lead_id_str = text.replace("/start lead_", "").strip()
        try:
            lead_id = int(lead_id_str)
        except:
            lead_id = None

        sender_entity = await event.get_sender()
        if not user and (not hasattr(sender_entity, 'username') or not sender_entity.username):
            await event.respond(
                "⚠️ **שגיאה: אין לך שם משתמש (Username) בטלגרם!**\n\n"
                "כדי להשתמש במערכת השילוח שלנו חובה להגדיר שם משתמש בהגדרות הפרופיל שלך בטלגרם.\n"
                "אנא צור שם משתמש, חזור לכאן ולחץ שוב על הקישור לקריאה."
            )
            return

        if not user:
            user_states[user_id] = {'step': 'waiting_name', 'pending_lead': lead_id}
            await event.respond(
                "👋 שלום וברוכים הבאים! זיהינו שיש לך שם משתמש תקין ✅\n"
                "כדי לבקש את הקריאה חובה להשלים רישום קצר במערכת.\n\n"
                "אנא שלח לי את **השם המלא** שלך (שם פרטי ושם משפחה):"
            )
            return

        if lead_id:
            lead = get_lead(lead_id)
            if lead and lead[3] == 'active':
                user_states[user_id] = {'state': f'waiting_driver_time_{lead_id}'}
                await event.respond("⏱️ **קריאה זו נקלטה!**\nאנא שלח כעת את **הזמן** שלך בכתובת (למשל: 15 דקות):")
        return

    if not user:
        sender_entity = await event.get_sender()
        if not hasattr(sender_entity, 'username') or not sender_entity.username:
            await event.respond(
                "⚠️ **שגיאה: אין לך שם משתמש (Username) בטלגרם!**\n\n"
                "כדי להשתמש במערכת השילוח שלנו חובה להגדיר שם משתמש בהגדרות הפרופיל שלך בטלגרם.\n"
                "אנא צור שם משתמש ולאחר מכן שלח לי שוב `/start`."
            )
            return

        state = user_states.get(user_id, {}).get('step')

        if not state:
            user_states[user_id] = {'step': 'waiting_name'}
            await event.respond(
                "👋 שלום וברוכים הבאים לבוט הניהול והשילוח המתקדם שלנו! 🚀\n"
                "זיהינו שיש לך שם משתמש תקין ✅\n\n"
                "כדי להתחיל, אנא שלח לי את **השם המלא** שלך (שם פרטי ושם משפחה):"
            )
            return

        elif state == 'waiting_name':
            user_states[user_id]['name'] = text
            user_states[user_id]['step'] = 'waiting_phone'
            phone_button = [[Button.request_phone("📱 לחץ כאן לשיתוף מספר הטלפון שלך", resize=True)]]
            await event.respond("תודה! כעת לחץ על הכפתור למטה כדי לשתף את מספר הטלפון שלך:", buttons=phone_button)
            return

        elif state == 'waiting_phone':
            phone = event.message.contact.phone_number if event.message.contact else text
            user_states[user_id]['phone'] = phone
            user_states[user_id]['step'] = 'waiting_birth'
            await event.respond("מעולה! דבר אחרון: מהו **תאריך הלידה** שלך? (למשל: 15/05/1995):", buttons=None)
            return

        elif state == 'waiting_birth':
            birth_date = text
            data = user_states[user_id]
            role = 'admin' if is_admin else 'user'
            register_user(user_id, data['name'], data['phone'], birth_date, role=role)
            
            pending_lead = data.get('pending_lead')
            del user_states[user_id]

            await event.respond(
                "✅ **הרישום הושלם בהצלחה!**\nמערכת הניהול פתוחה בפניך.",
                buttons=get_main_keyboard(is_admin, is_admin or role == 'advertiser', 'busy')
            )
            
            if pending_lead:
                lead = get_lead(pending_lead)
                if lead and lead[3] == 'active':
                    user_states[user_id] = {'state': f'waiting_driver_time_{pending_lead}'}
                    await event.respond("⏱️ **קריאה זו נקלטה!**\nאנא שלח כעת את **הזמן** שלך בכתובת (למשל: 15 דקות):")
            return

    current_state = user_states.get(user_id, {}).get('state')

    if is_admin and current_state and current_state.startswith('editing_station_name_'):
        st_id = int(current_state.replace('editing_station_name_', ''))
        new_name = text.strip()
        user_states.pop(user_id, None)
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE stations SET station_name = ? WHERE station_id = ?", (new_name, st_id))
        conn.commit()
        conn.close()
        await event.respond(f"✅ שם התחנה עודכן בהצלחה ל-**{new_name}**!", buttons=get_admin_keyboard())
        return

    if is_admin and current_state and current_state.startswith('editing_station_comm_'):
        st_id = int(current_state.replace('editing_station_comm_', ''))
        user_states.pop(user_id, None)
        try:
            new_comm = float(text)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE stations SET commission_percent = ? WHERE station_id = ?", (new_comm, st_id))
            conn.commit()
            conn.close()
            await event.respond(f"✅ אחוז העמלה לתחנה עודכן בהצלחה ל-**{new_comm}%**!", buttons=get_admin_keyboard())
        except:
            await event.respond("⚠️ נא להזין מספר אחוזי עמלה תקין (למשל: 10):", buttons=get_admin_keyboard())
        return

    if is_admin and current_state == 'waiting_broadcast_message_all':
        broadcast_text = text
        user_states.pop(user_id, None)
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        all_u = cursor.fetchall()
        conn.close()

        success_count = 0
        for (u_id,) in all_u:
            try:
                await bot_client.send_message(u_id, f"📢 **הודעת מערכת / שידור הנהלה:**\n\n{broadcast_text}")
                success_count += 1
            except:
                pass

        await event.respond(f"✅ השידור נשלח בהצלחה ל-{success_count} משתמשים במערכת!", buttons=get_admin_keyboard())
        return

    if is_admin and current_state == 'waiting_new_allowed_group':
        group_input = text.strip()
        user_states.pop(user_id, None)
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO allowed_groups (group_identifier, group_name) VALUES (?, ?)", (group_input, group_input))
        conn.commit()
        conn.close()
        
        await event.respond(f"✅ הקבוצה/ערוץ **{group_input}** נוספה בהצלחה לרשימת קבוצות הפרסום המורשות!", buttons=get_admin_keyboard())
        return

    if is_admin and current_state and current_state.startswith('waiting_station_manager_'):
        st_id = int(current_state.replace('waiting_station_manager_', ''))
        identifier = text.strip()
        user_states.pop(user_id, None)
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name FROM users WHERE phone = ? OR full_name LIKE ?", (identifier, f"%{identifier}%"))
        found_u = cursor.fetchone()
        
        if found_u:
            target_uid = found_u[0]
            cursor.execute("UPDATE users SET role = 'station_manager', station_id = ? WHERE user_id = ?", (st_id, target_uid))
            conn.commit()
            conn.close()
            await event.respond(f"✅ המשתמש הוגדר בהצלחה כמנהל תחנה!", buttons=get_admin_keyboard())
        else:
            conn.close()
            await event.respond("⚠️️ לא נמצא משתמש רשום במערכת עם הנתון הזה.", buttons=get_admin_keyboard())
        return

    if current_state and current_state.startswith('waiting_driver_time_'):
        lead_id = int(current_state.replace('waiting_driver_time_', ''))
        driver_time_input = text.strip()
        user_states.pop(user_id, None)
        await event.respond("✅ בקשתך נשלחה בהצלחה למפרסם!")
        await process_lead_request_final(event, user_id, lead_id, driver_time=driver_time_input)
        return

    if text == "ℹ️ אודות ויצירת קשר":
        about_contact_buttons = [
            [Button.text("ℹ אודות המערכת", resize=True), Button.text("📞 יצירת קשר", resize=True)],
            [Button.text("⬅ חזרה לתפריט הראשי", resize=True)]
        ]
        await event.respond("ℹ️ **אודות ויצירת קשר:**\nבחר את האפשרות הרצויה מהמקלדת:", buttons=about_contact_buttons)
        return

    if text == "ℹ️ אודות המערכת":
        await event.respond("ℹ️ banana bot - מערכת שילוח וניהול חכמה בטלגרם לניהול תחנות, סדרנים ושליחים.", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    if text == "📞 יצירת קשר":
        await event.respond("📞 **יצירת קשר עם ההנהלה:**\nלפניות, תמיכה ובירורים ניתן לפנות למנהל המערכת.", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    if text == "🔍 ניטור קבוצות ומילים":
        monitor_buttons = [
            [Button.text("➕ מילה חדשה", resize=True), Button.text("📋 הצגת המילים שלי", resize=True)],
            [Button.text("🗑 מחיקת מילה", resize=True), Button.text("🧹 מחיקת כל המילים", resize=True)],
            [Button.text("⬅ חזרה לתפריט הראשי", resize=True)]
        ]
        await event.respond("🔍 **ניהול ניטור קבוצות ומילים:**\nבחר את הפעולה הרצויה:", buttons=monitor_buttons)
        return

    if is_advertiser and current_state in ['editing_bot_lead_price', 'editing_group_lead_price']:
        try:
            new_price = float(text)
            flow_key = 'group_broadcast_data' if current_state == 'editing_group_lead_price' else 'broadcast_data'
            target_data = broadcast_data if flow_key == 'broadcast_data' else group_broadcast_data
            
            msg_data = target_data.get(user_id, {})
            old_text = msg_data.get('text', '')
            
            _, old_price, _ = parse_order_text(old_text)
            if old_price:
                updated_text = old_text.replace(str(int(old_price)), str(int(new_price)))
            else:
                updated_text = old_text + f"\nמחיר: ₪{int(new_price)}"
                
            target_data[user_id]['text'] = updated_text
            next_state = 'group_lead_preview' if flow_key == 'group_broadcast_data' else 'bot_lead_preview'
            user_states[user_id]['state'] = next_state
            
            cities, price, has_time = parse_order_text(updated_text)
            preview_text = (
                f"📋 **סיכום קריאה לפרסום ({'קבוצות' if flow_key == 'group_broadcast_data' else 'בוט'} - עודכן):**\n\n"
                f"📝 **תוכן:** {updated_text}\n"
                f"📞 **טלפון הלקוח:** {msg_data.get('phone', '')}\n"
                f"📍 **מסלול שזוהה:** {' ➔ '.join(cities) if cities else 'לא זוהה'}\n"
                f"💰 **מחיר שזוהה:** ₪{price if price else 'לא זוהה'}\n\n"
                f"האם לאשר ולפרסם כעת?"
            )
            confirm_cb = b"confirm_group_lead" if flow_key == 'group_broadcast_data' else b"confirm_bot_lead"
            edit_price_cb = b"edit_group_price" if flow_key == 'group_broadcast_data' else b"edit_bot_price"
            edit_text_cb = b"edit_group_text" if flow_key == 'group_broadcast_data' else b"edit_bot_text"
            edit_phone_cb = b"edit_group_phone" if flow_key == 'group_broadcast_data' else b"edit_bot_phone"

            buttons = [
                [Button.inline("✅ אישור ופרסם", confirm_cb), Button.inline("✏️ ערוך מחיר", edit_price_cb)],
                [Button.inline("✏️ ערוך טקסט", edit_text_cb), Button.inline("✏️ ערוך טלפון", edit_phone_cb)],
                [Button.inline("❌ ביטול", b"cancel_bot_flow")]
            ]
            await event.respond(preview_text, buttons=buttons)
        except:
            await event.respond("⚠️ נא להזין מחיר מספרי תקין:")
        return

    if is_advertiser and current_state in ['editing_bot_lead_text', 'editing_group_lead_text']:
        flow_key = 'group_broadcast_data' if current_state == 'editing_group_lead_text' else 'broadcast_data'
        target_data = broadcast_data if flow_key == 'broadcast_data' else group_broadcast_data
        
        target_data[user_id]['text'] = text
        next_state = 'group_lead_preview' if flow_key == 'group_broadcast_data' else 'bot_lead_preview'
        user_states[user_id]['state'] = next_state
        
        msg_data = target_data[user_id]
        cities, price, has_time = parse_order_text(text)
        preview_text = (
            f"📋 **סיכום קריאה לפרסום ({'קבוצות' if flow_key == 'group_broadcast_data' else 'בוט'} - עודכן):**\n\n"
            f"📝 **תוכן:** {text}\n"
            f"📞 **טלפון הלקוח:** {msg_data.get('phone', '')}\n"
            f"📍 **מסלול שזוהה:** {' ➔ '.join(cities) if cities else 'לא זוהה'}\n"
            f"💰 **מחיר שזוהה:** ₪{price if price else 'לא זוהה'}\n\n"
            f"האם לאשר ולפרסם כעת?"
        )
        confirm_cb = b"confirm_group_lead" if flow_key == 'group_broadcast_data' else b"confirm_bot_lead"
        edit_price_cb = b"edit_group_price" if flow_key == 'group_broadcast_data' else b"edit_bot_price"
        edit_text_cb = b"edit_group_text" if flow_key == 'group_broadcast_data' else b"edit_bot_text"
        edit_phone_cb = b"edit_group_phone" if flow_key == 'group_broadcast_data' else b"edit_bot_phone"

        buttons = [
            [Button.inline("✅ אישור ופרסם", confirm_cb), Button.inline("✏️ ערוך מחיר", edit_price_cb)],
            [Button.inline("✏️️ ערוך טקסט", edit_text_cb), Button.inline("✏️ ערוך טלפון", edit_phone_cb)],
            [Button.inline("❌ ביטול", b"cancel_bot_flow")]
        ]
        await event.respond(preview_text, buttons=buttons)
        return

    if is_advertiser and current_state in ['editing_bot_lead_phone', 'editing_group_lead_phone']:
        flow_key = 'group_broadcast_data' if current_state == 'editing_group_lead_phone' else 'broadcast_data'
        target_data = broadcast_data if flow_key == 'broadcast_data' else group_broadcast_data
        
        target_data[user_id]['phone'] = text
        next_state = 'group_lead_preview' if flow_key == 'group_broadcast_data' else 'bot_lead_preview'
        user_states[user_id]['state'] = next_state
        
        msg_data = target_data[user_id]
        cities, price, has_time = parse_order_text(msg_data['text'])
        preview_text = (
            f"📋 **סיכום קריאה לפרסום ({'קבוצות' if flow_key == 'group_broadcast_data' else 'בוט'} - עודכן):**\n\n"
            f"📝 **תוכן:** {msg_data['text']}\n"
            f"📞 **טלפון הלקוח:** {text}\n"
            f"📍 **מסלול שזוהה:** {' ➔ '.join(cities) if cities else 'לא זוהה'}\n"
            f"💰 **מחיר שזוהה:** ₪{price if price else 'לא זוהה'}\n\n"
            f"האם לאשר ולפרסם כעת?"
        )
        confirm_cb = b"confirm_group_lead" if flow_key == 'group_broadcast_data' else b"confirm_bot_lead"
        edit_price_cb = b"edit_group_price" if flow_key == 'group_broadcast_data' else b"edit_bot_price"
        edit_text_cb = b"edit_group_text" if flow_key == 'group_broadcast_data' else b"edit_bot_text"
        edit_phone_cb = b"edit_group_phone" if flow_key == 'group_broadcast_data' else b"edit_bot_phone"

        buttons = [
            [Button.inline("✅ אישור ופרסם", confirm_cb), Button.inline("✏️ ערוך מחיר", edit_price_cb)],
            [Button.inline("✏️ ערוך טקסט", edit_text_cb), Button.inline("✏️ ערוך טלפון", edit_phone_cb)],
            [Button.inline("❌ ביטול", b"cancel_bot_flow")]
        ]
        await event.respond(preview_text, buttons=buttons)
        return

    if is_advertiser and current_state == 'waiting_group_lead_text':
        group_broadcast_data[user_id] = {'text': text}
        user_states[user_id]['state'] = 'waiting_group_lead_phone'
        cancel_btn = [[Button.inline("❌ ביטול וחזרה", b"cancel_bot_flow")]]
        await event.respond("📞 אנא שלח כעת את **מספר הטלפון של הלקוח** שיוצג בקריאה לקבוצות (או לחץ ביטול):", buttons=cancel_btn)
        return

    if is_advertiser and current_state == 'waiting_group_lead_phone':
        group_broadcast_data[user_id]['phone'] = text
        user_states[user_id]['state'] = 'group_lead_preview'
        
        msg_data = group_broadcast_data[user_id]
        cities, price, has_time = parse_order_text(msg_data['text'])
        preview_text = (
            f"📋 **סיכום קריאה לפרסום בקבוצות המורשות:**\n\n"
            f"📝 **תוכן:** {msg_data['text']}\n"
            f"📞 **טלפון הלקוח:** {text}\n"
            f"📍 **מסלול שזוהה:** {' ➔ '.join(cities) if cities else 'לא זוהה'}\n"
            f"💰 **מחיר שזוהה:** ₪{price if price else 'לא זוהה'}\n\n"
            f"האם לאשר ולפרסם כעת לקבוצות שהוגדרו?"
        )
        buttons = [
            [Button.inline("✅ אישור ופרסם לקבוצות", b"confirm_group_lead"), Button.inline("✏️ ערוך מחיר", b"edit_group_price")],
            [Button.inline("✏️ ערוך טקסט", b"edit_group_text"), Button.inline("✏️ ערוך טלפון", b"edit_group_phone")],
            [Button.inline("❌ ביטול", b"cancel_bot_flow")]
        ]
        await event.respond(preview_text, buttons=buttons)
        return

    if is_admin and current_state == 'waiting_station_name':
        station_creation_data[user_id] = {'name': text}
        user_states[user_id]['state'] = 'waiting_station_commission'
        
        comm_buttons = [
            [Button.inline("0%", b"comm_0"), Button.inline("5%", b"comm_5"), Button.inline("10%", b"comm_10")],
            [Button.inline("12%", b"comm_12"), Button.inline("15%", b"comm_15")],
            [Button.inline("❌ ביטול", b"cancel_bot_flow")]
        ]
        await event.respond(f"🏢 שם התחנה נקלט: **{text}**\n\nכעת בחר את **אחוז העמלה** שהתחנה גובה מעל 50 ש\"ח:", buttons=comm_buttons)
        return

    if is_admin and current_state and current_state.startswith('selecting_role_for_'):
        target_uid = int(current_state.replace('selecting_role_for_', ''))
        role_map = {
            "משתמש רגיל": "user",
            "סדרן": "advertiser",
            "מנהל תחנה": "station_manager",
            "מנהל מערכת": "admin"
        }
        chosen_role = role_map.get(text, "user")
        user_states[user_id] = {'state': f'selecting_expiry_for_{target_uid}', 'pending_role': chosen_role}
        
        expiry_buttons = [
            [Button.text("3 ימים", resize=True), Button.text("שבוע", resize=True)],
            [Button.text("חודש", resize=True), Button.text("3 חודשים", resize=True)],
            [Button.text("חצי שנה", resize=True), Button.text("שנה", resize=True)],
            [Button.text("⬅ חזרה לתפריט הראשי", resize=True)]
        ]
        await event.respond(f"📅 בחר את **תוקף המנוי** עבור המשתמש לכמה זמן קדימה להעניק לו:", buttons=expiry_buttons)
        return

    if is_admin and current_state and current_state.startswith('selecting_expiry_for_'):
        target_uid = int(current_state.replace('selecting_expiry_for_', ''))
        chosen_role = user_states[user_id].get('pending_role', 'user')
        
        days_map = {
            "3 ימים": 3,
            "שבוע": 7,
            "חודש": 30,
            "3 חודשים": 90,
            "חצי שנה": 180,
            "שנה": 365
        }
        days = days_map.get(text, 30)
        new_expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        
        update_user_role_and_expiry(target_uid, chosen_role, new_expiry)
        user_states.pop(user_id, None)
        
        await event.respond(f"✅ פרטי המשתמש עודכנו בהצלחה!\nתפקיד: {chosen_role}\nתוקף עד: {new_expiry}", buttons=get_admin_keyboard())
        return

    if is_advertiser and current_state and current_state.startswith('closing_lead_'):
        lead_id = int(current_state.replace('closing_lead_', ''))
        closed_info = text.strip()
        update_lead_status(lead_id, 'closed', closed_with=closed_info)
        user_states.pop(user_id, None)
        await event.respond(f"✅ קריאה #{lead_id} נסגרה בהצלחה ותועדה עם הפרטים: **{closed_info}**", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    if is_advertiser and current_state and current_state.startswith('editing_lead_'):
        lead_id = int(current_state.replace('editing_lead_', ''))
        update_lead_status(lead_id, 'active')
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE leads SET message_text = ? WHERE lead_id = ?", (text, lead_id))
        conn.commit()
        conn.close()
        user_states.pop(user_id, None)
        await event.respond(f"✅ תוכן קריאה #{lead_id} עודכן בהצלחה!", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

    if is_advertiser:
        if current_state == 'waiting_bot_lead_text':
            broadcast_data[user_id] = {'text': text}
            user_states[user_id]['state'] = 'waiting_bot_lead_phone'
            cancel_btn = [[Button.inline("❌ ביטול וחזרה", b"cancel_bot_flow")]]
            await event.respond("📞 אנא שלח כעת את **מספר הטלפון של הלקוח** שיוצג בקריאה (או לחץ ביטול):", buttons=cancel_btn)
            return

        elif current_state == 'waiting_bot_lead_phone':
            broadcast_data[user_id]['phone'] = text
            user_states[user_id]['state'] = 'bot_lead_preview'
            
            msg_data = broadcast_data[user_id]
            cities, price, has_time = parse_order_text(msg_data['text'])
            
            preview_text = (
                f"📋 **סיכום קריאה לפרסום פנימי בבוט:**\n\n"
                f"📝 **תוכן:** {msg_data['text']}\n"
                f"📞 **טלפון הלקוח:** {text}\n"
                f"📍 **מסלול שזוהה:** {' ➔ '.join(cities) if cities else 'לא זוהה (יופץ לכל הפנויים)'}\n"
                f"💰 **מחיר שזוהה:** ₪{price if price else 'לא זוהה'}\n"
                f"⏱️ **דרישת זמן בקריאה:** {'נדרש (זוהה זמן/זמנים)' if has_time else 'לא נדרש (לא זוהה זמן)'}\n\n"
                f"האם לאשר ולפרסם כעת?"
            )
            buttons = [
                [Button.inline("✅ אישור ופרסם", b"confirm_bot_lead"), Button.inline("✏️ ערוך מחיר", b"edit_bot_price")],
                [Button.inline("✏️ ערוך טקסט", b"edit_bot_text"), Button.inline("✏️ ערוך טלפון", b"edit_bot_phone")],
                [Button.inline("❌ ביטול", b"cancel_bot_flow")]
            ]
            await event.respond(preview_text, buttons=buttons)
            return

    if current_state == 'waiting_add_city':
        city_name = text.strip()
        success, msg = add_user_city(user_id, city_name)
        user_states.pop(user_id, None)
        updated_user = get_user(user_id)
        new_status = updated_user[3]
        if success:
            await event.respond(f"✅ נוספת בהצלחה כפנוי!\n📍 הערים שלך כעת: {msg}", buttons=get_main_keyboard(is_admin, is_advertiser, new_status))
        else:
            await event.respond(f"⚠ {msg}", buttons=get_main_keyboard(is_admin, is_advertiser, new_status))
        return

    if text.startswith("פ א ") or text.startswith("פא "):
        city_part = text.replace("פ א ", "").replace("פא ", "").strip()
        if city_part:
            success, msg = add_user_city(user_id, city_part)
            updated_user = get_user(user_id)
            new_status = updated_user[3]
            if success:
                await event.respond(f"✅ זוהה אזור פעילות!\n📍 הערים שלך כעת: {msg}\n\nכעת בחר את רדיוס הקילומטרים הרצוי:", buttons=[
                    [Button.inline("2 ק\"מ", b"radius_2"), Button.inline("5 ק\"מ", b"radius_5"), Button.inline("10 ק\"מ", b"radius_10")],
                    [Button.inline("20 ק\"מ", b"radius_20"), Button.inline("40 ק\"מ", b"radius_40")]
                ])
            else:
                await event.respond(f"⚠️ {msg}")
            return

    if text == "🟢 פנוי לקריאות":
        user_states[user_id] = {'state': 'waiting_add_city'}
        await event.respond(
            "🟢 מעבר למצב פנוי לקריאות:\n"
            "שלח כעת את שם העיר שבה אתה פנוי (למשל: ירושלים, או השתמש בקיצור 'פ א ירושלים').\n"
            "ניתן להוסיף עד 6 ערים במקביל ע\"י הוספה חוזרת.",
            buttons=get_main_keyboard(is_admin, is_advertiser, current_status)
        )
        return

    elif text == "🔴 תפוס":
        update_user_status(user_id, 'busy')
        await event.respond("🔴 הסטטוס שלך עודכן לתפוס וכל אזורי הפעילות שלך אופסו במערכת.", buttons=get_main_keyboard(is_admin, is_advertiser, 'busy'))
        return

    elif text == "⚙️ הגדרת אזורים ורדיוס":
        keyboard = [
            [Button.text("➕ הוסף עיר נוספת", resize=True), Button.text("🗑️ מחק עיר ספציפית", resize=True)],
            [Button.text("🗑️ מחק את כל הערים (איפס הכל)", resize=True)],
            [Button.text("📏 שנה רדיוס קילומטרים", resize=True)],
            [Button.text("⬅ חזרה לתפריט הראשי", resize=True)]
        ]
        await event.respond("⚙️ ניהול אזורים וערים:\nבחר את הפעולה הרצויה:", buttons=keyboard)
        return

    elif text == "➕ הוסף עיר נוספת":
        user_states[user_id] = {'state': 'waiting_add_city'}
        await event.respond("✍️ שלח כעת את שם העיר הנוספת שתרצה להוסיף לרשימת הפעילות שלך:")
        return

    elif text == "🗑️ מחק עיר ספציפית":
        cities_str = user[8] if user and user[8] else ""
        cities_list = [c.strip() for c in cities_str.split(',') if c.strip()]
        
        if not cities_list:
            await event.respond("⚠️ אין לך ערים רשומות כרגע, אתה לא פנוי באף עיר.", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
            return
        
        inline_buttons = [[Button.inline(f"❌ מחק את {c}", f"del_city_{c}".encode('utf-8'))] for c in cities_list]
        inline_buttons.append([Button.inline("↩️ ביטול וחזרה", b"cancel_del_city")])
        
        await event.respond("🗑️ **בחר את העיר שתרצה למחוק מרשימת הפעילות שלך:**", buttons=inline_buttons)
        return

    elif text == "🗑️ מחק את כל הערים (איפס הכל)":
        update_user_status(user_id, 'busy')
        await event.respond("🗑️ כל אזורי הפעילות שלך נמחקו והסטטוס שלך אופס לתפוס מלא.", buttons=get_main_keyboard(is_admin, is_advertiser, 'busy'))
        return

    elif text == "📏 שנה רדיוס קילומטרים":
        user_states[user_id] = {'state': 'waiting_new_radius'}
        await event.respond("📏 שלח כעת את מספר הקילומטרים הרצוי לרדיוס הנסיעה (למשל: 10):")
        return

    if current_state == 'waiting_new_radius':
        try:
            new_rad = int(text)
            update_user_radius(user_id, new_rad)
            user_states.pop(user_id, None)
            updated_user = get_user(user_id)
            curr_rad = updated_user[7] if updated_user else new_rad
            await event.respond(f"✅ רדיוס הנסיעה שלך עודכן וסונכרן ל-{curr_rad} ק\"מ.", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        except:
            await event.respond("⚠️ נא להזין מספר שלם תקין:")
        return

    if text == "📢 פרסום הודעה" and is_advertiser:
        buttons = [
            [Button.inline("🤖 פרסום פנימי בבוט", b"pub_mode_bot")],
            [Button.inline("🌐 פרסום בקבוצות", b"pub_mode_groups")],
            [Button.inline("❌ ביטול וחזרה", b"cancel_bot_flow")]
        ]
        await event.respond("📢 בחר היכן תרצה לפרסם את הקריאה:", buttons=buttons)
        return

    elif text == "📋 מצב קריאות" and is_advertiser:
        leads = get_all_system_leads()
        if not leads:
            await event.respond("📋 אין קריאות רשומות במערכת כרגע.", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
            return
        
        await event.respond("📋 **הנה רשימת כל הקריאות המערכתיות:**", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        
        for l_id, pub_id, l_text, l_phone, l_status, l_closed in leads:
            if l_status == 'active':
                status_icon = "🟢 פעילה"
            elif l_status == 'closed':
                status_icon = "✅ סגורה"
            else:
                status_icon = "🗑️ מחוקה/בוטלה"
            
            closed_info_str = f"\n🔒 **נסגר עם:** {l_closed}" if l_closed else ""
            phone_str = f"\n📞 **טלפון בקריאה:** {l_phone}" if l_phone else ""
            pub_str = f"\n👤 **מפרסם (מזהה):** `{pub_id}`"

            buttons = [
                [Button.inline(f"🔒 סגור קריאה", f"ask_close_{l_id}".encode('utf-8')),
                 Button.inline(f"🔄 פרסם שוב", f"repost_lead_{l_id}".encode('utf-8'))],
                [Button.inline(f"✏️ ערוך ושנה", f"edit_lead_{l_id}".encode('utf-8')),
                 Button.inline(f"❌ מחק", f"delete_lead_{l_id}".encode('utf-8'))]
            ]

            await event.respond(
                f"📌 **קריאה #{l_id}**"
                f"{pub_str}\n"
                f"📊 **סטטוס:** {status_icon}\n"
                f"📝 **טקסט:** {l_text[:40]}..."
                f"{phone_str}"
                f"{closed_info_str}",
                buttons=buttons
            )
        return

    elif text in ["🛠️ פאנל מנהל", "פאנל מנהל"] and is_admin:
        await event.respond("🛠️ פאנל ניהול ראשי:", buttons=get_admin_keyboard())
        return

    elif text == "📊 סטטיסטיקות מערכת" and is_admin:
        t_users, t_leads, c_leads, d_leads, today_l = get_system_stats()
        await event.respond(f"📊 סטטיסטיקות:\nמשתמשים: {t_users} | סך קריאות: {t_leads} | סגורות: {c_leads}", buttons=get_admin_keyboard())
        return

    elif text == "📢 שידור הודעה לכולם" and is_admin:
        user_states[user_id] = {'state': 'waiting_broadcast_message_all'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.respond("📢 **שידור הודעה לכל משתמשים במערכת:**\nשלח כעת את טקסט ההודעה שתרצה לשדר:", buttons=cancel_btn)
        return

    elif text == "🏢 ניהול תחנות וקבוצות" and is_admin:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT station_id, station_name, commission_percent FROM stations")
        stations = cursor.fetchall()
        
        cursor.execute("SELECT group_id, group_identifier FROM allowed_groups")
        groups = cursor.fetchall()
        conn.close()
        
        st_text = "🏢 **ניהול תחנות וקבוצות פרסום מורשות:**\n\n"
        st_text += "📍 **קבוצות פרסום מוגדרות:**\n"
        if not groups:
            st_text += "• אין קבוצות מוגדרות עדיין.\n"
        else:
            for g_id, g_name in groups:
                st_text += f"• `{g_name}` (מזהה: {g_id})\n"
                
        st_text += "\n🏢 **תחנות שילוח:**\n"
        st_buttons = [
            [Button.inline("➕ הוסף קבוצת פרסום", b"add_allowed_group"), Button.inline("🗑️ הסר קבוצה", b"remove_allowed_group")],
            [Button.inline("➕ הוסף תחנה חדשה", b"add_new_station")],
            [Button.inline("🏢 הוסף מנהל לתחנה", b"add_station_manager")],
            [Button.inline("📊 סטטיסטיקות תחנות", b"station_stats")]
        ]
        
        if not stations:
            st_text += "• אין תחנות רשומות."
        else:
            for s_id, s_name, s_comm in stations:
                st_text += f"• {s_name} (עמלה: {s_comm}%)\n"
                st_buttons.append([Button.inline(f"⚙️ ע/מ תחנה: {s_name}", f"manage_station_{s_id}".encode('utf-8'))])
        
        st_buttons.append([Button.inline("↩️ חזרה לפאנל מנהל", b"back_to_admin_cb")])
        await event.respond(st_text, buttons=st_buttons)
        return

    elif text == "👥 ניהול משתמשים" and is_admin:
        all_u = get_all_users()
        if not all_u:
            await event.respond("👥 אין משתמשים רשומים במערכת כרגע.", buttons=get_admin_keyboard())
            return
        
        summary_text = "👥 **רשימת משתמשים רשומים במערכת:**\nלחץ על משתמש לניהול פרטני:\n\n"
        u_buttons = []
        for u_id, u_name, u_phone, u_role, u_exp, u_stat in all_u:
            summary_text += f"• **{u_name}** | תפקיד: `{u_role}` | טלפון: `{u_phone}`\n"
            u_buttons.append([Button.inline(f"⚙️ ניהול: {u_name} ({u_role})", f"manage_user_{u_id}".encode('utf-8'))])
        
        u_buttons.append([Button.inline("↩️ חזרה לפאנל מנהל", b"back_to_admin_cb")])
        await event.respond(summary_text, buttons=u_buttons)
        return

    elif text == "💎 מצב מנוי ופרופיל":
        u_data = get_user(user_id)
        u_name = u_data[0] if u_data else "לא ידוע"
        u_role = u_data[5] if u_data else "user"
        radius_val = u_data[7] if u_data else 5
        cities_val = u_data[8] if u_data else ""
        total_trips = u_data[9] if u_data and len(u_data) > 9 else 0
        u_rating = u_data[10] if u_data and len(u_data) > 10 else 0.0
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT amount, is_paid FROM driver_debts WHERE user_id = ?", (user_id,))
        debts = cursor.fetchall()
        total_debt = sum([d[0] for d in debts if not d[1]])
        conn.close()

        await event.respond(
            f"💎 **האזור האישי והפרופיל שלך:**\n\n"
            f"👤 שם מלא: {u_name}\n"
            f"🛡️ תפקיד במערכת: **{u_role}**\n"
            f"📦 סך נסיעות/משלוחים שבוצעו: {total_trips}\n"
            f"⭐ דירוג ממוצע: {u_rating:.1f} כוכבים\n"
            f"💳 סך חובות פתוחים לתחנות: ₪{total_debt:.2f}\n\n"
            f"📍 ערים פעילות: {cities_val if cities_val else 'לא הוגדר'}\n"
            f"📏 רדיוס: {radius_val} ק\"מ\n"
            f"🟢 סטטוס: {'פנוי' if current_status == 'free' else 'תפוס'}",
            buttons=get_main_keyboard(is_admin, is_advertiser, current_status)
        )
        return

    if getattr(bot_client, f'waiting_word_{user_id}', False):
        add_user_keyword(user_id, text)
        await event.respond(f"✅ המילה '{text}' נוספה בהצלחה!", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        setattr(bot_client, f'waiting_word_{user_id}', False)
        return

    if text == "➕ מילה חדשה":
        setattr(bot_client, f'waiting_word_{user_id}', True)
        await event.respond("✍ שלח את המילה לניטור:")

    elif text == "📋 הצגת המילים שלי":
        words = get_user_keywords(user_id)
        await event.respond("📋 המילים שלי:\n" + ("\n".join([f"• {w}" for w in words]) if words else "אין מילים"), buttons=get_main_keyboard(is_admin, is_advertiser, current_status))

    elif text == "🧹 מחיקת כל המילים":
        clear_user_keywords(user_id)
        await event.respond("🧹 כל המילים שלך בניטור נמחקו בהצלחה!", buttons=get_main_keyboard(is_admin, is_advertiser, current_status))
        return

@bot_client.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    user_id = event.sender_id

    if data == "cancel_bot_flow":
        user_states.pop(user_id, None)
        await event.edit("❌ הפעולה בוטלה. חזרת למצב רגיל.")
        return

    if data == "back_to_admin_cb":
        await event.edit("🛠️ פאנל ניהול ראשי:", buttons=get_admin_keyboard())
        return

    if data.startswith("del_city_"):
        city_to_del = data.replace("del_city_", "")
        remaining = remove_user_city(user_id, city_to_del)
        await event.edit(f"🗑 העיר '{city_to_del}' הוסרה בהצלחה!\n📍 הערים שנותרו ברשימה: `{remaining if remaining else 'אין ערים מוגדרות'}`")
        return

    elif data == "cancel_del_city":
        await event.edit("❌ פעולת מחיקת העיר בוטלה.")
        return

    elif data.startswith("manage_station_"):
        st_id = int(data.replace("manage_station_", ""))
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT station_name, commission_percent FROM stations WHERE station_id = ?", (st_id,))
        st_row = cursor.fetchone()
        conn.close()
        
        if st_row:
            s_name, s_comm = st_row
            txt = f"🏢 **ניהול תחנה: {s_name}**\nעמלה נוכחית מעל 50₪: {s_comm}%\n\nבחר פעולה רצויה:"
            btns = [
                [Button.inline("✏️ שנה שם תחנה", f"edit_st_name_{st_id}".encode('utf-8'))],
                [Button.inline("💰 שנה אחוז עמלה", f"edit_st_comm_{st_id}".encode('utf-8'))],
                [Button.inline("🗑️ מחק תחנה זו לצמיתות", f"delete_station_{st_id}".encode('utf-8'))],
                [Button.inline("↩️ חזרה לניהול תחנות", b"back_to_stations")]
            ]
            await event.edit(txt, buttons=btns)
        return

    elif data.startswith("edit_st_name_"):
        st_id = int(data.replace("edit_st_name_", ""))
        user_states[user_id] = {'state': f'editing_station_name_{st_id}'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("✏️ שלח כעת את **שם התחנה החדש**:", buttons=cancel_btn)
        return

    elif data.startswith("edit_st_comm_"):
        st_id = int(data.replace("edit_st_comm_", ""))
        user_states[user_id] = {'state': f'editing_station_comm_{st_id}'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("💰 שלח כעת את **אחוז העמלה החדש** (מספר בלבד, למשל: 12):", buttons=cancel_btn)
        return

    elif data.startswith("delete_station_"):
        st_id = int(data.replace("delete_station_", ""))
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stations WHERE station_id = ?", (st_id,))
        cursor.execute("UPDATE users SET station_id = NULL WHERE station_id = ?", (st_id,))
        conn.commit()
        conn.close()
        await event.edit("🗑️ התחנה נמחקה בהצלחה מהמערכת!", buttons=[[Button.inline("↩️ חזרה לניהול תחנות", b"back_to_stations")]])
        return

    elif data == "add_station_manager":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT station_id, station_name FROM stations")
        st_list = cursor.fetchall()
        conn.close()
        
        if not st_list:
            await event.edit("⚠️ אין תחנות רשומות. הקם תחנה חדשה קודם.")
            return
            
        st_btns = [[Button.inline(f"🏢 {s_name}", f"pick_st_mgr_{s_id}".encode('utf-8'))] for s_id, s_name in st_list]
        st_btns.append([Button.inline("↩️ ביטול", b"cancel_bot_flow")])
        await event.edit("🏢 **בחר את התחנה שאליה תרצה למנות מנהל:**", buttons=st_btns)
        return

    elif data.startswith("pick_st_mgr_"):
        st_id = int(data.replace("pick_st_mgr_", ""))
        user_states[user_id] = {'state': f'waiting_station_manager_{st_id}'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("👤 שלח כעת את **מספר הטלפון** או **שם המשתמש (Username)** של המשתמש שאותו תרצה להגדיר כמנהל תחנה זו:", buttons=cancel_btn)
        return

    elif data == "station_stats":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT station_id, station_name FROM stations")
        stations = cursor.fetchall()
        
        stat_text = "📊 **סטטיסטיקות תחנות שילוח:**\n\n"
        for s_id, s_name in stations:
            cursor.execute("SELECT COUNT(*), SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END), SUM(CASE WHEN status='deleted' THEN 1 ELSE 0 END) FROM leads WHERE station_id = ?", (s_id,))
            res = cursor.fetchone()
            total, closed, deleted = res[0] or 0, res[1] or 0, res[2] or 0
            stat_text += f"🏢 **{s_name}:**\n• סך קריאות: {total} | סגורות: {closed} | מבוטלות/נמחקו: {deleted}\n\n"
        conn.close()
        
        await event.edit(stat_text, buttons=[[Button.inline("↩️ חזרה לניהול תחנות", b"back_to_stations")]])
        return

    elif data == "back_to_stations":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT station_id, station_name, commission_percent FROM stations")
        stations = cursor.fetchall()
        cursor.execute("SELECT group_id, group_identifier FROM allowed_groups")
        groups = cursor.fetchall()
        conn.close()
        
        st_text = "🏢 **ניהול תחנות וקבוצות פרסום מורשות:**\n\n"
        for g_id, g_name in groups:
            st_text += f"• קבוצה: `{g_name}`\n"
            
        st_buttons = [
            [Button.inline("➕ הוסף קבוצת פרסום", b"add_allowed_group"), Button.inline("🗑️ הסר קבוצה", b"remove_allowed_group")],
            [Button.inline("➕ הוסף תחנה חדשה", b"add_new_station")],
            [Button.inline("🏢 הוסף מנהל לתחנה", b"add_station_manager")],
            [Button.inline("📊 סטטיסטיקות תחנות", b"station_stats")]
        ]
        for s_id, s_name, s_comm in stations:
            st_buttons.append([Button.inline(f"⚙️ ע/מ תחנה: {s_name}", f"manage_station_{s_id}".encode('utf-8'))])
            
        st_buttons.append([Button.inline("↩️ חזרה לפאנל מנהל", b"back_to_admin_cb")])
        await event.edit(st_text, buttons=st_buttons)
        return

    elif data == "add_allowed_group":
        user_states[user_id] = {'state': 'waiting_new_allowed_group'}
        cancel_btn = [[Button.inline("❌ ביטול וחזרה", b"cancel_bot_flow")]]
        await event.edit("➕ **הוספת קבוצת פרסום מורשית:**\nשלח כעת את מזהה הקבוצה, ה-Username (למשל `@group_name`) או הקישור שלה:", buttons=cancel_btn)
        return

    elif data == "remove_allowed_group":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT group_id, group_identifier FROM allowed_groups")
        groups = cursor.fetchall()
        conn.close()
        
        if not groups:
            await event.edit("⚠️ אין קבוצות מוגדרות להסרה.")
            return
            
        g_buttons = [[Button.inline(f"🗑️ הסר את {g_ident}", f"del_group_{g_id}".encode('utf-8'))] for g_id, g_ident in groups]
        g_buttons.append([Button.inline("↩️ ביטול", b"cancel_bot_flow")])
        await event.edit("🗑️ **בחר את הקבוצה שתרצה להסיר מרשימת הפרסום:**", buttons=g_buttons)
        return

    elif data.startswith("del_group_"):
        g_id = int(data.replace("del_group_", ""))
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM allowed_groups WHERE group_id = ?", (g_id,))
        conn.commit()
        conn.close()
        await event.edit("✅ הקבוצה הוסרה בהצלחה מרשימת הפרסום!")
        return

    elif data == "add_new_station":
        user_states[user_id] = {'state': 'waiting_station_name'}
        cancel_btn = [[Button.inline("❌ ביטול וחזרה", b"cancel_bot_flow")]]
        await event.edit("🏢 **הקמת תחנה חדשה:**\nשלח כעת בהודעה את **שם התחנה** החדשה:", buttons=cancel_btn)
        return

    elif data.startswith("comm_"):
        comm_val = float(data.replace("comm_", ""))
        s_data = station_creation_data.get(user_id, {})
        s_name = s_data.get('name', 'תחנה חדשה')
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO stations (station_name, owner_id, commission_percent) VALUES (?, ?, ?)", (s_name, user_id, comm_val))
        conn.commit()
        conn.close()
        
        user_states.pop(user_id, None)
        station_creation_data.pop(user_id, None)
        
        await event.edit(f"✅ התחנה **'{s_name}'** הוקמה בהצלחה!\nעמלה מעל 50 ש\"ח: **{comm_val}%** (עד 50 ש\"ח: 0%).")
        return

    elif data.startswith("manage_user_"):
        target_uid = int(data.replace("manage_user_", ""))
        t_data = get_user(target_uid)
        if t_data:
            card_text = (
                f"⚙️️ **כרטיסיית ניהול משתמש:**\n\n"
                f"👤 שם: {t_data[0]}\n"
                f"📱 טלפון: {t_data[1]}\n"
                f"🛡️ תפקיד נוכחי: `{t_data[5]}`\n"
                f"⭐ דירוג: {t_data[10]:.1f} | נסיעות: {t_data[9]}\n\n"
                f"בחר את הפעולה הרצויה לשינוי הרשאות המשתמש:"
            )
            card_buttons = [
                [Button.inline("👑 הפוך למנהל מערכת", f"set_role_{target_uid}_admin".encode('utf-8'))],
                [Button.inline("👔 הפוך לסדרן", f"set_role_{target_uid}_advertiser".encode('utf-8'))],
                [Button.inline("🚗 הפוך לשליח רגיל", f"set_role_{target_uid}_user".encode('utf-8'))],
                [Button.inline("↩️ חזרה לרשימת משתמשים", b"back_to_users_list")]
            ]
            await event.edit(card_text, buttons=card_buttons)
        return

    elif data == "back_to_users_list":
        all_u = get_all_users()
        summary_text = "👥 **רשימת משתמשים רשומים במערכת:**\nלחץ על משתמש לניהול פרטני:\n\n"
        u_buttons = []
        for u_id, u_name, u_phone, u_role, u_exp, u_stat in all_u:
            summary_text += f"• **{u_name}** | תפקיד: `{u_role}` | טלפון: `{u_phone}`\n"
            u_buttons.append([Button.inline(f"⚙️ ניהול: {u_name} ({u_role})", f"manage_user_{u_id}".encode('utf-8'))])
        u_buttons.append([Button.inline("↩ חזרה לפאנל מנהל", b"back_to_admin_cb")])
        await event.edit(summary_text, buttons=u_buttons)
        return

    elif data.startswith("set_role_"):
        parts = data.split("_")
        t_uid = int(parts[2])
        new_role = parts[3]
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, t_uid))
        conn.commit()
        conn.close()
        
        await event.edit(f"✅ הרשאות המשתמש עודכנו בהצלחה לתפקיד: **{new_role}**", buttons=[[Button.inline("↩️ חזרה לרשימת משתמשים", b"back_to_users_list")]])
        return

    elif data == "edit_bot_price":
        user_states[user_id] = {'state': 'editing_bot_lead_price'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("💰 שלח כעת את **המחיר החדש** (מספר בלבד, למשל: 220):", buttons=cancel_btn)
        return

    elif data == "edit_bot_text":
        user_states[user_id] = {'state': 'editing_bot_lead_text'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("✏️ שלח כעת את **טקסט הקריאה החדש** המלא:", buttons=cancel_btn)
        return

    elif data == "edit_bot_phone":
        user_states[user_id] = {'state': 'editing_bot_lead_phone'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("📞 שלח כעת את **מספר הטלפון החדש של הלקוח**:", buttons=cancel_btn)
        return

    elif data == "edit_group_price":
        user_states[user_id] = {'state': 'editing_group_lead_price'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("💰 שלח כעת את **המחיר החדש** (מספר בלבד):", buttons=cancel_btn)
        return

    elif data == "edit_group_text":
        user_states[user_id] = {'state': 'editing_group_lead_text'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("✏️ שלח כעת את **הטקסט החדש** לקבוצות:", buttons=cancel_btn)
        return

    elif data == "edit_group_phone":
        user_states[user_id] = {'state': 'editing_group_lead_phone'}
        cancel_btn = [[Button.inline("❌ ביטול", b"cancel_bot_flow")]]
        await event.edit("📞 שלח כעת את **מספר הטלפון החדש של הלקוח** לקבוצות:", buttons=cancel_btn)
        return

    if data == "pub_mode_bot":
        user_states[user_id] = {'pub_mode': 'bot', 'state': 'waiting_bot_lead_text'}
        cancel_btn = [[Button.inline("❌ ביטול וחזרה", b"cancel_bot_flow")]]
        await event.edit("🤖 פרסום פנימי בבוט:\nשלח כעת את טקסט הקריאה (מסלול ומחיר):", buttons=cancel_btn)
        return

    elif data == "pub_mode_groups":
        user_states[user_id] = {'pub_mode': 'groups', 'state': 'waiting_group_lead_text'}
        cancel_btn = [[Button.inline("❌ ביטול וחזרה", b"cancel_bot_flow")]]
        await event.edit("🌐 פרסום בקבוצות המורשות:\nשלח כעת את תוכן ההודעה לפרסום:", buttons=cancel_btn)
        return

    elif data == "confirm_group_lead":
        msg_data = group_broadcast_data.get(user_id, {})
        text_content = msg_data.get('text', '')
        phone_content = msg_data.get('phone', '')
        
        pub_user_data = get_user(user_id)
        st_id = pub_user_data[6] if pub_user_data and len(pub_user_data) > 6 else None
        
        lead_id, lead_cities, lead_price, has_time = save_lead(user_id, text_content, phone_content, station_id=st_id)
        user_states.pop(user_id, None)
        
        me = await bot_client.get_me()
        bot_username = me.username
        lead_link = f"https://t.me/{bot_username}?start=lead_{lead_id}"
        
        pub_fullname = pub_user_data[0] if pub_user_data and pub_user_data[0] else "סדרן"
        
        station_name = "כללי"
        if st_id:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT station_name FROM stations WHERE station_id = ?", (st_id,))
            st_row = cursor.fetchone()
            if st_row:
                station_name = st_row[0]
            conn.close()

        group_post_text = (
            f"🚀 **קריאת שילוח חדשה! (#{lead_id})**\n\n"
            f"{text_content}\n\n"
            f"🏢 תחנה: {station_name} | סדרן: {pub_fullname}\n\n"
            f"👉 [👉 בקש את הקריאה לחץ כאן 👈]({lead_link})"
        )
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT group_identifier FROM allowed_groups")
        allowed_groups = cursor.fetchall()
        conn.close()

        published_count = 0
        for (g_ident,) in allowed_groups:
            try:
                await client.send_message(g_ident, group_post_text, parse_mode='markdown')
                published_count += 1
            except Exception as e:
                print(f"Error sending to group {g_ident}: {e}")

        await event.edit(
            f"✅ **קריאה #{lead_id} נוצרה והופצה אוטומטית ל-{published_count} קבוצות מורשות עם קישור מוטמע ישירות בהודעה!**\n\n"
            f"🔗 קישור ישיר לבוט: `{lead_link}`"
        )
        return

    elif data == "confirm_bot_lead":
        msg_data = broadcast_data.get(user_id, {})
        text_content = msg_data.get('text', '')
        phone_content = msg_data.get('phone', '')
        
        pub_user_data = get_user(user_id)
        st_id = pub_user_data[6] if pub_user_data and len(pub_user_data) > 6 else None
        
        lead_id, lead_cities, lead_price, has_time = save_lead(user_id, text_content, phone_content, station_id=st_id)
        user_states.pop(user_id, None)
        
        await event.edit(f"✅ קריאה #{lead_id} נוצרה ונשלחת כעת לשליחים הפנויים באזור המתאים!")
        
        pub_fullname = pub_user_data[0] if pub_user_data and pub_user_data[0] else "סדרן"
        
        station_name = "כללי"
        if st_id:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT station_name FROM stations WHERE station_id = ?", (st_id,))
            st_row = cursor.fetchone()
            if st_row:
                station_name = st_row[0]
            conn.close()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, status, cities, radius FROM users WHERE status = 'free'")
        all_free_users = cursor.fetchall()
        conn.close()

        sent_count = 0
        for f_user in all_free_users:
            f_uid, f_status, f_cities, f_radius = f_user
            
            matched = False
            if not lead_cities:
                matched = True
            else:
                user_cities_list = [c.strip() for c in f_cities.split(',') if c.strip()]
                for l_city in lead_cities:
                    if l_city in user_cities_list:
                        matched = True
                        break

            if matched:
                alert_msg = (
                    f"🚀 **קריאה חדשה זמינה! (#{lead_id})**\n\n"
                    f"📍 מסלול: {' ➔ '.join(lead_cities) if lead_cities else 'כללי'}\n"
                    f"💰 מחיר: ₪{lead_price if lead_price else 'לא זוהה'}\n\n"
                    f"📝 **פרטים:**\n{text_content}\n\n"
                    f"🏢 תחנה: {station_name} | סדרן: {pub_fullname}"
                )
                req_btn = [[Button.inline("👉 תן את הקריאה", f"request_lead_btn_{lead_id}".encode('utf-8'))]]
                try:
                    await bot_client.send_message(f_uid, alert_msg, buttons=req_btn)
                    sent_count += 1
                except:
                    pass

        await bot_client.send_message(user_id, f"📢 הקריאה הופצה בהצלחה ל-{sent_count} שליחים פנויים התואמים לאזור!")
        return

    elif data == "cancel_bot_lead":
        user_states.pop(user_id, None)
        await event.edit("❌ הפרסום בבוט בוטל.")
        return

    elif data.startswith("request_lead_btn_"):
        lead_id = int(data.replace("request_lead_btn_", ""))
        lead = get_lead(lead_id)
        if not lead or lead[3] != 'active':
            await event.edit("⚠️ קריאה זו אינה פעילה עוד או סגורה.")
            return
        
        _, _, has_time = parse_order_text(lead[1])
        if has_time:
            user_states[user_id] = {'state': f'waiting_driver_time_{lead_id}'}
            await event.respond("⏱️ נא לרשום כמה זמן אתה בכתובת:")
            await event.answer("אנא שלח את הזמן בצ'אט הפרטי")
        else:
            await process_lead_request_final(event, user_id, lead_id, driver_time="לא צוין זמן")
            await event.answer("הבקשה נשלחה למפרסם")
        return

    elif data.startswith("ask_close_"):
        lead_id = int(data.replace("ask_close_", ""))
        user_states[user_id] = {'state': f'closing_lead_{lead_id}'}
        await event.respond(f"🔒 אנא שלח כעת בהודעה את **מספר הטלפון או ה-User** של מי שקיבל את קריאה #{lead_id}:")
        return

    elif data.startswith("edit_lead_"):
        lead_id = int(data.replace("edit_lead_", ""))
        user_states[user_id] = {'state': f'editing_lead_{lead_id}'}
        await event.respond(f"✏️ שלח כעת את **הטקסט החדש** שתרצה לעדכן לקריאה #{lead_id}:")
        return

    elif data.startswith("delete_lead_"):
        lead_id = int(data.replace("delete_lead_", ""))
        update_lead_status(lead_id, 'deleted', closed_with='נמחק')
        await event.edit(f"🗑️ קריאה #{lead_id} הוסרה/נמחקה בהצלחה.")
        return

    elif data == "back_to_admin":
        await event.respond("🛠️ פאנל ניהול ראשי:", buttons=get_admin_keyboard())
        return

    elif data.startswith("approve_and_close_"):
        parts = data.split("_")
        lead_id = int(parts[3])
        requester_id = int(parts[4])
        
        publisher_id = user_id
        pub_user = get_user(publisher_id)
        pub_name = pub_user[0] if pub_user and pub_user[0] else "סדרן"
        publisher_entity = await bot_client.get_entity(publisher_id)
        
        pub_username = f"@{publisher_entity.username}" if hasattr(publisher_entity, 'username') and publisher_entity.username else f"מזהה: {publisher_id}"

        update_lead_status(lead_id, 'closed', closed_with=pub_username)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET total_trips = total_trips + 1 WHERE user_id = ?", (requester_id,))
        conn.commit()
        conn.close()

        lead_data = get_lead(lead_id)
        customer_phone = lead_data[2] if lead_data else "לא זמין"
        msg_text = lead_data[1] if lead_data else ""
        now_time = datetime.now().strftime('%d/%m/%Y בשעה %H:%M')

        try:
            rate_buttons = [
                [Button.inline("⭐ 1", f"rate_{requester_id}_1"), Button.inline("⭐⭐ 2", f"rate_{requester_id}_2"), Button.inline("⭐⭐⭐ 3", f"rate_{requester_id}_3")],
                [Button.inline("⭐⭐⭐⭐ 4", f"rate_{requester_id}_4"), Button.inline("⭐⭐⭐⭐⭐ 5", f"rate_{requester_id}_5")],
                [Button.inline("⏭️ דלג על דירוג", f"rate_{requester_id}_skip")]
            ]
            
            await bot_client.send_message(
                requester_id,
                f"🎉 **עדכון משמח! הקריאה #{lead_id} נסגרה עליך!**\n"
                f"בתאריך {now_time}.\n\n"
                f"📝 **תוכן הקריאה:** {msg_text}\n"
                f"📞 **מספר טלפון של הלקוח:** {customer_phone}\n\n"
                f"👨‍💻 **סדרן שסגר עליך:** {pub_name} ({pub_username})"
            )
            
            await event.edit(
                f"✅ **הפנייה אושרה, קריאה #{lead_id} נסגרה על השליח!**\n"
                f"האם תרצה לדרג את השליח כעת?",
                buttons=rate_buttons
            )
        except Exception as e:
            await event.edit(f"⚠️ שגיאה בשליחת הודעה לשליח: {e}")
        return

    elif data.startswith("rate_"):
        parts = data.split("_")
        target_driver_id = int(parts[1])
        val_str = parts[2]
        
        if val_str != "skip":
            stars = int(val_str)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT rating, rating_count FROM users WHERE user_id = ?", (target_driver_id,))
            r_data = cursor.fetchone()
            if r_data:
                curr_rating, curr_count = r_data[0], r_data[1]
                new_count = curr_count + 1
                new_rating = ((curr_rating * curr_count) + stars) / new_count
                cursor.execute("UPDATE users SET rating = ?, rating_count = ? WHERE user_id = ?", (new_rating, new_count, target_driver_id))
                conn.commit()
            conn.close()
            await event.edit(f"⭐ הדירוג ({stars} כוכבים) נקלט ונשמר בהצלחה!")
        else:
            await event.edit("⏭️ דולג על דירוג השליח.")
        return

    elif data.startswith("approve_only_"):
        parts = data.split("_")
        lead_id = int(parts[2])
        requester_id = int(parts[3])
        
        publisher_entity = await bot_client.get_entity(user_id)
        pub_username = f"@{publisher_entity.username}" if hasattr(publisher_entity, 'username') and publisher_entity.username else f"מזהה: {user_id}"

        req_entity = await bot_client.get_entity(requester_id)
        req_uname = f"@{req_entity.username}" if hasattr(req_entity, 'username') and req_entity.username else f"מזהה: {requester_id}"

        try:
            await bot_client.send_message(
                requester_id,
                f"🎉 **הפנייה שלך לקריאה #{lead_id} אושרה!**\nצור קשר עם המפרסם: {pub_username}"
            )
            
            follow_up_buttons = [
                [Button.inline(f"🔒 סגור קריאה על {req_uname}", f"approve_and_close_{lead_id}_{requester_id}".encode('utf-8'))],
                [Button.inline("❌ מחק/ביטול", f"delete_lead_{lead_id}".encode('utf-8'))]
            ]

            await event.edit(
                f"✅ **הפנייה של {req_uname} אושרה!** (הקריאה עדיין פתוחה).\n"
                f"מה ברצונך לעשות כעת עם קריאה #{lead_id}?",
                buttons=follow_up_buttons
            )
        except Exception as e:
            await event.edit(f"⚠️️ שגיאה: {e}")
        return

    elif data.startswith("reject_lead_"):
        parts = data.split("_")
        try:
            await bot_client.send_message(int(parts[3]), f"❌ מצטערים, הבקשה לקריאה #{parts[2]} נדחתה.")
            await event.edit("❌ הפנייה נדחתה.")
        except:
            pass
        return

    if data.startswith("radius_"):
        rad = data.replace("radius_", "")
        update_user_radius(user_id, int(rad))
        await event.edit(f"✅ רדיוס הנסיעה עודכן ל-{rad} ק\"מ בהצלחה!")
        return

async def process_lead_request_final(event, requester_id, lead_id, driver_time):
    lead = get_lead(lead_id)
    if not lead or lead[3] != 'active':
        if hasattr(event, 'respond'):
            await event.respond("⚠️ קריאה זו אינה פעילה עוד או סגורה.")
        else:
            await event.edit("⚠️ קריאה זו אינה פעילה עוד או סגורה.")
        return

    publisher_id, message_text, phone_number, status, closed_with, price, route_cities, st_id = lead
    requester_user = get_user(requester_id)
    requester_entity = await bot_client.get_entity(requester_id)
    
    req_name = requester_user[0] if requester_user else "לא ידוע"
    req_phone = requester_user[1] if requester_user else "לא זמין"
    req_username = f"@{requester_entity.username}" if hasattr(requester_entity, 'username') and requester_entity.username else "אין יוזר"
    
    req_radius = requester_user[7] if requester_user else 5
    req_cities = requester_user[8] if requester_user else ""
    req_silver = requester_user[9] if requester_user and len(requester_user) > 9 else 0
    req_gold = requester_user[10] if requester_user and len(requester_user) > 10 else 0
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

    buttons = [
        [Button.inline("✅ אישור וסגירת קריאה על המבקש", f"approve_and_close_{lead_id}_{requester_id}".encode('utf-8'))],
        [Button.inline("✅ אישור בלבד (השאר פתוח)", f"approve_only_{lead_id}_{requester_id}".encode('utf-8'))],
        [Button.inline("❌ דחייה", f"reject_lead_{lead_id}_{requester_id}".encode('utf-8'))]
    ]

    try:
        await bot_client.send_message(publisher_id, alert_to_publisher, buttons=buttons)
        if hasattr(event, 'respond'):
            await event.respond("✅ **בקשתך לקריאה נשלחה בהצלחה למפרסם!**")
        else:
            await event.edit("✅ **בקשתך לקריאה נשלחה בהצלחה למפרסם!**")
    except:
        if hasattr(event, 'respond'):
            await event.respond("⚠️ שגיאה בשליחת הבקשה למפרסם.")
        else:
            await event.edit("⚠️ שגיאה בשליחת הבקשה למפרסם.")

# החלק הסופי המתוקן שמאפשר לשניהם לרוץ ביחד בלי קריסות של חלון קלט בענן:
async def main():
    print("✨ בוט השילוח והניהול פועל בהצלחה!")
    # מפעילים את שתי הלקוחות יחד (הלקוח האישי לסריקה והבוט לניהול)
    await client.start()
    print("🤖 שני הלקוחות מחוברים ופעילים בענן!")
    
    # ממתינים ששניהם ירוצו יחד ברקע
    await asyncio.gather(
        client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )

if __name__ == '__main__':
    asyncio.run(main())
