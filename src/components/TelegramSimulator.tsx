import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { ROLE_NAMES, Role } from '../types';
import { cleanOrderText, extractOrderPrice, calculateCommission, calculateNewRating } from '../utils/orderUtils';
import { Send, Bot, Check, CheckCheck, Sparkles, RefreshCw, X } from 'lucide-react';

interface TelegramMessage {
  id: string;
  sender: 'bot' | 'user';
  text: string;
  timestamp: string;
  replyMarkup?: {
    inline_keyboard?: Array<Array<{ text: string; callback_data: string }>>;
  };
}

export const TelegramSimulator: React.FC = () => {
  const {
    currentUser,
    users,
    stations,
    orders,
    debts,
    driverCities,
    botGroups,
    publishOrder,
    submitOrderBid,
    approveDriverOrder,
    denyDriverOrder,
    rateDriver,
    deleteOrder,
    submitDebtAppeal,
    resolveDebtAppeal,
    createStation,
    updateUserRoleAndStation,
    sendBroadcast,
    toggleDriverStatus,
    addDriverCity,
    clearDriverCities,
    switchUser,
  } = useApp();

  const [messages, setMessages] = useState<TelegramMessage[]>([
    {
      id: 'm1',
      sender: 'bot',
      text: `👋 ברוכים הבאים למערכת ה-ERP!\nהנך מחובר כעת בתור **${currentUser.full_name}** (${ROLE_NAMES[currentUser.role] || currentUser.role}).\nשלח /start בכל עת לחזרה לתפריט הראשי.`,
      timestamp: new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }),
    },
  ]);

  const [inputText, setInputText] = useState('');
  const [fsmState, setFsmState] = useState<string>('idle');
  const [fsmData, setFsmData] = useState<Record<string, any>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Generate Reply Keyboard matching bot.py get_main_kb
  const getMainKeyboardButtons = (): string[][] => {
    const kb: string[][] = [];
    const role = currentUser.role;
    const status = currentUser.status;

    if (['admin', 'station_manager', 'dispatcher'].includes(role)) {
      kb.push(['📢 פרסם קריאה', '📋 מצב קריאות']);
    }
    if (['admin', 'station_manager'].includes(role)) {
      kb.push(['🏢 ניהול תחנה ועובדים']);
    }
    if (role === 'admin') {
      kb.push(['🛠️ פאנל מנהל מערכת']);
    }

    const statusBtn = status === 'busy' ? '🟢 פנוי לעבודה' : '🔴 תפוס (עצור קריאות)';
    kb.push([statusBtn, '📍 אזורי עבודה']);
    kb.push(['💳 חיובים וערעורים', '💎 הפרופיל שלי']);

    return kb;
  };

  const addBotMessage = (text: string, inline_keyboard?: Array<Array<{ text: string; callback_data: string }>>) => {
    const newMsg: TelegramMessage = {
      id: 'm_' + Date.now() + Math.random(),
      sender: 'bot',
      text,
      timestamp: new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }),
      replyMarkup: inline_keyboard ? { inline_keyboard } : undefined,
    };
    setMessages((prev) => [...prev, newMsg]);
  };

  const addUserMessage = (text: string) => {
    const newMsg: TelegramMessage = {
      id: 'u_' + Date.now() + Math.random(),
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, newMsg]);
  };

  // Main input handler executing bot.py logic
  const handleSendMessage = (textToSend?: string) => {
    const text = (textToSend || inputText).trim();
    if (!text) return;
    setInputText('');
    addUserMessage(text);

    // Cancel command
    if (text === '❌ ביטול וחזרה' || text === '/cancel') {
      setFsmState('idle');
      setFsmData({});
      addBotMessage('🎛️ פעולה בוטלה. **תפריט ראשי:**');
      return;
    }

    // /start command
    if (text === '/start') {
      setFsmState('idle');
      setFsmData({});
      if (currentUser.is_blocked) {
        addBotMessage('❌ חשבונך נחסם.');
        return;
      }
      addBotMessage('🎛️ **תפריט ראשי:**');
      return;
    }

    // FSM State Machine Handlers
    if (fsmState === 'waiting_publish_text') {
      const cleaned = cleanOrderText(text);
      const estPrice = extractOrderPrice(cleaned);
      if (estPrice === 0) {
        addBotMessage('⚠️ המערכת לא זיהתה מחיר. נא לכלול מחיר בספרות (למשל: 100).');
        return;
      }
      setFsmData({ order_text: cleaned, est_price: estPrice });
      setFsmState('waiting_publish_dest');
      addBotMessage(
        `✅ טקסט נוקה.\n💵 מחיר שזוהה: ${estPrice} ש"ח.\n\nלאן לשגר את הקריאה?`,
        [
          [
            { text: 'לנהגים בפרטי', callback_data: 'dest_private' },
            { text: 'לקבוצות (חיצוני)', callback_data: 'dest_groups' },
          ],
        ]
      );
      return;
    }

    if (fsmState === 'waiting_new_city') {
      addDriverCity(currentUser.user_id, text);
      setFsmState('idle');
      addBotMessage(`✅ העיר ${text} נוספה בהצלחה לאזורי העבודה שלך.`);
      return;
    }

    if (fsmState === 'waiting_driver_eta') {
      const minutes = parseInt(text, 10);
      if (isNaN(minutes) || minutes <= 0) {
        addBotMessage('⚠️ נא להזין מספר דקות הגיוני.');
        return;
      }
      const orderId = fsmData.take_order_id;
      const res = submitOrderBid(orderId, currentUser.user_id, minutes);
      setFsmState('idle');
      if (!res.success) {
        addBotMessage(res.message);
      } else {
        addBotMessage(`⏳ בקשתך לקריאה #${orderId} עם זמן הגעה של ${minutes} דקות נשלחה לסדרן. המתנה לאישור...`);
      }
      return;
    }

    if (fsmState === 'waiting_dispute_reason') {
      const debtId = fsmData.debt_id;
      submitDebtAppeal(debtId, text);
      setFsmState('idle');
      addBotMessage(`✅ הערעור על חיוב #${debtId} ("${text}") נשלח להנהלה לבדיקה. תקבל עדכון בקרוב.`);
      return;
    }

    if (fsmState === 'waiting_station_name') {
      setFsmData({ new_station_name: text });
      setFsmState('waiting_station_comm');
      addBotMessage('💰 מה יהיה **אחוז העמלה** של התחנה? (למשל: 10.5):');
      return;
    }

    if (fsmState === 'waiting_station_comm') {
      const comm = parseFloat(text);
      if (isNaN(comm) || comm < 0) {
        addBotMessage('⚠️ נא להזין מספר חוקי.');
        return;
      }
      const name = fsmData.new_station_name;
      const newSt = createStation(name, comm);
      setFsmState('idle');
      addBotMessage(`✅ תחנה **${newSt.name}** נוצרה עם עמלה של ${comm}%.`);
      return;
    }

    if (fsmState === 'waiting_user_id_role') {
      const parts = text.split(' ');
      if (parts.length < 2) {
        addBotMessage('⚠️ פורמט שגוי. נסה שוב (ID Role StationID).\nלמשל: 301 dispatcher 1');
        return;
      }
      const targetId = parseInt(parts[0], 10);
      const newRole = parts[1] as Role | 'blocked';
      const stationId = parts.length > 2 ? parseInt(parts[2], 10) : 1;
      updateUserRoleAndStation(targetId, newRole, stationId);
      setFsmState('idle');
      addBotMessage(`✅ המשתמש ${targetId} עודכן בהצלחה לתפקיד ${newRole} בתחנה ${stationId}.`);
      return;
    }

    if (fsmState === 'waiting_broadcast') {
      const count = sendBroadcast(text);
      setFsmState('idle');
      addBotMessage(`✅ ההודעה שודרה בהצלחה ל-${count} משתמשים במערכת.`);
      return;
    }

    // Top Level Menu Commands
    if (text === '💎 הפרופיל שלי') {
      const roleHeb = ROLE_NAMES[currentUser.role] || 'נהג';
      const profileText = `💎 **הפרופיל שלך:**\n👤 ${currentUser.full_name}\n📱 ${currentUser.phone}\n🛡️ ${roleHeb} (תחנה: ${currentUser.station_id})\n\n🚗 רכב: ${currentUser.car_brand} ${currentUser.car_model} (${currentUser.car_year})\n⭐ דירוג: ${currentUser.rating.toFixed(1)}/5.0 (${currentUser.total_trips} נסיעות)\n💰 חוב לתחנה: **${currentUser.debt_balance.toFixed(2)} ש"ח**`;
      addBotMessage(profileText);
      return;
    }

    if (text === '📍 אזורי עבודה') {
      const myCities = driverCities
        .filter((dc) => dc.user_id === currentUser.user_id)
        .map((dc) => dc.city_name);
      const citiesStr = myCities.length > 0 ? myCities.join(', ') : 'לא הוגדרו אזורים (מקבל קריאות מכל הארץ)';
      addBotMessage(
        `📍 **הערים שלך:**\n${citiesStr}\n\n*רק קריאות מהערים האלו יקפצו אליך כשתהיה פנוי.*`,
        [
          [
            { text: '➕ הוסף עיר', callback_data: 'add_city' },
            { text: '🗑️ נקה הכל', callback_data: 'clear_cities' },
          ],
        ]
      );
      return;
    }

    if (text === '🟢 פנוי לעבודה' || text === '🔴 תפוס (עצור קריאות)') {
      const res = toggleDriverStatus();
      addBotMessage(res.message);
      return;
    }

    if (text === '📢 פרסם קריאה') {
      if (!['admin', 'station_manager', 'dispatcher'].includes(currentUser.role)) {
        addBotMessage('❌ אין לך הרשאת סדרן להפעיל פונקציה זו.');
        return;
      }
      setFsmState('waiting_publish_text');
      addBotMessage(
        '📝 **הדבק פרטי קריאה:**\n(המערכת תנקה חצים אוטומטית. חובה לרשום מחיר בספרות).'
      );
      return;
    }

    if (text === '📋 מצב קריאות') {
      if (!['admin', 'station_manager', 'dispatcher'].includes(currentUser.role)) {
        addBotMessage('❌ אין לך הרשאת סדרן להפעיל פונקציה זו.');
        return;
      }
      const openOrders = orders.filter((o) => {
        if (currentUser.role === 'admin') return o.status === 'open';
        return o.status === 'open' && o.station_id === currentUser.station_id;
      });

      if (openOrders.length === 0) {
        addBotMessage('✅ אין קריאות פתוחות לתחנה שלך כרגע.');
        return;
      }

      openOrders.forEach((o) => {
        const bids = o.bids || [];
        let txt = `🎫 קריאה #${o.order_id}\n💵 מחיר: ${o.price} ש"ח\n📝 טקסט: ${o.text}`;
        if (bids.length > 0) {
          txt += `\n\n🔔 **הצעות נהגים (${bids.length}):**\n` +
            bids.map((b) => `• ${b.driver_name} (⭐${b.rating}) - ${b.eta_minutes} דקות`).join('\n');
        }
        const buttons: Array<Array<{ text: string; callback_data: string }>> = [
          [{ text: '❌ מחק קריאה (נלקחה מחוץ לבוט)', callback_data: `delorder_${o.order_id}` }],
        ];
        if (bids.length > 0) {
          bids.forEach((b) => {
            buttons.push([
              { text: `✅ אשר את ${b.driver_name} (${b.eta_minutes} דק')`, callback_data: `approve_${o.order_id}_${b.driver_id}` },
              { text: `❌ דחה את ${b.driver_name}`, callback_data: `deny_${o.order_id}_${b.driver_id}` },
            ]);
          });
        }
        addBotMessage(txt, buttons);
      });
      return;
    }

    if (text === '💳 חיובים וערעורים') {
      const myDebts = debts.filter((d) => d.driver_id === currentUser.user_id && d.status === 'unpaid');
      if (myDebts.length === 0) {
        addBotMessage('✅ אין לך חובות פתוחים במערכת.');
        return;
      }
      myDebts.forEach((d) => {
        const txt = `🧾 **חיוב מתחנה ${d.station_id}**\nעבור קריאה #${d.order_id}\n💰 סכום לתשלום: ${d.amount} ש"ח\nסיבה: ${d.reason}`;
        addBotMessage(txt, [
          [{ text: '⚖️ ערעור / בקשת ביטול', callback_data: `appeal_${d.debt_id}` }],
        ]);
      });
      return;
    }

    if (text === '🛠️ פאנל מנהל מערכת' || text === '🏢 ניהול תחנה ועובדים') {
      if (currentUser.role === 'admin') {
        addBotMessage('👑 **פאנל ניהול מתקדם (God Mode):**\nבחר את הפעולה הרצויה:', [
          [{ text: '➕ פתיחת תחנה חדשה', callback_data: 'god_new_station' }],
          [{ text: '👥 ניהול הרשאות משתמשים', callback_data: 'god_manage_users' }],
          [{ text: '📢 הודעת Broadcast גלובלית', callback_data: 'god_broadcast' }],
        ]);
      } else if (currentUser.role === 'station_manager') {
        addBotMessage('👑 **ניהול תחנה:**', [
          [{ text: '👥 פנה להנהלה להוספת עובדים', callback_data: 'mgr_dummy' }],
        ]);
      }
      return;
    }

    // Default response
    addBotMessage(`קיבלתי: "${text}". שלח /start לתפריט הראשי.`);
  };

  // Inline callback query handler executing bot.py callback logic
  const handleCallback = async (callback_data: string) => {
    addUserMessage(`[לחיצה על כפתור: ${callback_data}]`);

    if (callback_data === 'add_city') {
      setFsmState('waiting_new_city');
      addBotMessage('✍️ הקלד עיר להוספה (למשל: מודיעין עילית):');
      return;
    }

    if (callback_data === 'clear_cities') {
      clearDriverCities(currentUser.user_id);
      addBotMessage('✅ כל הערים נמחקו. לא תקבל קריאות עד שתוסיף ערים חדשות.');
      return;
    }

    if (callback_data === 'dest_private') {
      const data = fsmData;
      const res = await publishOrder(data.order_text, 'private', data.est_price);
      setFsmState('idle');
      addBotMessage(
        `✅ קריאה #${res.order.order_id} שוגרה בהצלחה ל-${res.eligibleDriversCount} נהגים בפרטי (סונן לפי אזורי עבודה וסטטוס פנוי).`
      );
      return;
    }

    if (callback_data === 'dest_groups') {
      const data = fsmData;
      const res = await publishOrder(data.order_text, 'groups', data.est_price);
      setFsmState('idle');
      addBotMessage(`✅ קריאה #${res.order.order_id} שוגרה בהצלחה ל-${botGroups.length} קבוצות מוגדרות במערכת.`);
      return;
    }

    if (callback_data.startsWith('delorder_')) {
      const orderId = parseInt(callback_data.split('_')[1], 10);
      deleteOrder(orderId);
      addBotMessage(`✅ קריאה #${orderId} נסגרה/נמחקה מהמערכת.`);
      return;
    }

    if (callback_data.startsWith('take_')) {
      const orderId = parseInt(callback_data.split('_')[1], 10);
      if (currentUser.status !== 'free') {
        addBotMessage("⚠️ אתה בסטטוס תפוס! העבר ל'פנוי' בתפריט הראשי קודם.");
        return;
      }
      setFsmData({ take_order_id: orderId });
      setFsmState('waiting_driver_eta');
      addBotMessage(`🎫 בקשה לקריאה #${orderId}\n⏱️ **כמה זמן עד להגעה למוצא?** (במספר דקות):`);
      return;
    }

    if (callback_data.startsWith('approve_')) {
      const [, orderIdStr, driverIdStr] = callback_data.split('_');
      const orderId = parseInt(orderIdStr, 10);
      const driverId = parseInt(driverIdStr, 10);
      const res = approveDriverOrder(orderId, driverId);
      if (res.success) {
        addBotMessage(
          `✅ סגרת את קריאה #${orderId} על הנהג (נרשם חוב עמלה של ₪${res.debtAmount}).\nאיך הנהג/הרכב נראה לך? דרג עכשיו:`,
          [
            [
              { text: '⭐ 1', callback_data: `rate_${driverId}_1` },
              { text: '⭐⭐ 2', callback_data: `rate_${driverId}_2` },
              { text: '⭐⭐⭐ 3', callback_data: `rate_${driverId}_3` },
            ],
            [
              { text: '⭐⭐⭐⭐ 4', callback_data: `rate_${driverId}_4` },
              { text: '⭐⭐⭐⭐⭐ 5', callback_data: `rate_${driverId}_5` },
            ],
          ]
        );
      }
      return;
    }

    if (callback_data.startsWith('deny_')) {
      const [, orderIdStr, driverIdStr] = callback_data.split('_');
      denyDriverOrder(parseInt(orderIdStr, 10), parseInt(driverIdStr, 10));
      addBotMessage(`❌ דחית את הנהג לקריאה #${orderIdStr}.`);
      return;
    }

    if (callback_data.startsWith('rate_')) {
      const [, driverIdStr, starsStr] = callback_data.split('_');
      rateDriver(parseInt(driverIdStr, 10), parseInt(starsStr, 10));
      addBotMessage(`✅ דירגת את הנהג ב-${starsStr} כוכבים. המערכת עודכנה בהצלחה.`);
      return;
    }

    if (callback_data.startsWith('appeal_')) {
      const debtId = parseInt(callback_data.split('_')[1], 10);
      setFsmData({ debt_id: debtId });
      setFsmState('waiting_dispute_reason');
      addBotMessage('✍️ **מדוע אתה מבקש לבטל את החיוב הזה?**\nהקש את הסיבה (למשל: "הלקוח ביטל"):');
      return;
    }

    if (callback_data === 'god_new_station') {
      setFsmState('waiting_station_name');
      addBotMessage('🏢 הקלד את **שם התחנה החדשה** (למשל: תחנת השפלה):');
      return;
    }

    if (callback_data === 'god_manage_users') {
      setFsmState('waiting_user_id_role');
      addBotMessage(
        '👥 **ניהול הרשאות:**\nאנא הקלד את פקודת השינוי בפורמט הבא:\n`[מזהה_משתמש] [תפקיד] [מזהה_תחנה]`\n\nתפקידים: admin, station_manager, dispatcher, user, blocked\nלדוגמה: `301 dispatcher 1`'
      );
      return;
    }

    if (callback_data === 'god_broadcast') {
      setFsmState('waiting_broadcast');
      addBotMessage('📢 הקלד את ההודעה שתשודר **לכל המשתמשים במערכת**:');
      return;
    }

    if (callback_data === 'mgr_dummy') {
      addBotMessage('פעולה זו מבוצעת על ידי הנהלת המערכת.');
      return;
    }
  };

  const mainButtons = getMainKeyboardButtons();

  return (
    <div className="max-w-2xl mx-auto bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden flex flex-col h-[780px]">
      {/* Telegram App Bar */}
      <div className="bg-slate-800 px-4 py-3 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-sky-400 to-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-md">
            🤖
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-white text-sm">Kobi ERP Bot</span>
              <span className="text-[10px] bg-blue-500/20 text-blue-300 border border-blue-500/30 px-1.5 py-0.2 rounded font-mono">
                bot
              </span>
            </div>
            <div className="flex items-center gap-1 text-[11px] text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>מקוון • מענה מיידי</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {fsmState !== 'idle' && (
            <button
              onClick={() => handleSendMessage('❌ ביטול וחזרה')}
              className="text-xs bg-red-500/15 hover:bg-red-500/25 text-red-300 border border-red-500/30 px-2.5 py-1 rounded-lg transition flex items-center gap-1"
            >
              <X className="w-3.5 h-3.5" />
              <span>ביטול (FSM: {fsmState})</span>
            </button>
          )}

          <button
            onClick={() => {
              setMessages([
                {
                  id: 'm_new',
                  sender: 'bot',
                  text: '🎛️ **תפריט ראשי:**',
                  timestamp: new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }),
                },
              ]);
              setFsmState('idle');
            }}
            title="נקה צ'אט"
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-700 transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Telegram Message Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-950/80">
        <div className="text-center my-2">
          <span className="text-[11px] bg-slate-800/80 text-slate-400 px-3 py-1 rounded-full border border-slate-700">
            היום • שיחת בוט מאובטחת
          </span>
        </div>

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs sm:text-sm whitespace-pre-wrap leading-relaxed shadow-sm ${
                msg.sender === 'user'
                  ? 'bg-blue-600 text-white rounded-tl-sm'
                  : 'bg-slate-800 text-slate-100 border border-slate-700/80 rounded-tr-sm'
              }`}
            >
              {msg.text}

              <div
                className={`text-[10px] mt-1.5 flex items-center gap-1 ${
                  msg.sender === 'user' ? 'text-blue-200 justify-end' : 'text-slate-400 justify-start'
                }`}
              >
                <span>{msg.timestamp}</span>
                {msg.sender === 'user' && <CheckCheck className="w-3 h-3 text-blue-200" />}
              </div>
            </div>

            {/* Inline Keyboard Buttons */}
            {msg.replyMarkup?.inline_keyboard && (
              <div className="mt-2 space-y-1.5 w-full max-w-[85%]">
                {msg.replyMarkup.inline_keyboard.map((row, rIdx) => (
                  <div key={rIdx} className="grid grid-flow-col gap-1.5">
                    {row.map((btn, bIdx) => (
                      <button
                        key={bIdx}
                        onClick={() => handleCallback(btn.callback_data)}
                        className="bg-slate-800 hover:bg-slate-700 active:bg-blue-600 text-slate-200 hover:text-white text-xs font-semibold py-2 px-3 rounded-xl border border-slate-700 transition shadow-sm text-center truncate"
                      >
                        {btn.text}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Telegram Reply Keyboard (Persistent Buttons at bottom) */}
      <div className="bg-slate-900 border-t border-slate-800 p-2.5 space-y-1.5">
        <div className="grid gap-1.5">
          {mainButtons.map((row, rIdx) => (
            <div key={rIdx} className="grid grid-flow-col gap-1.5">
              {row.map((btnText, bIdx) => (
                <button
                  key={bIdx}
                  onClick={() => handleSendMessage(btnText)}
                  className={`py-2 px-2.5 rounded-xl text-xs font-bold transition text-center truncate shadow-sm ${
                    btnText.startsWith('🟢')
                      ? 'bg-emerald-600/20 hover:bg-emerald-600 text-emerald-300 hover:text-white border border-emerald-500/30'
                      : btnText.startsWith('🔴')
                      ? 'bg-red-600/20 hover:bg-red-600 text-red-300 hover:text-white border border-red-500/30'
                      : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600'
                  }`}
                >
                  {btnText}
                </button>
              ))}
            </div>
          ))}
        </div>

        {/* Text Input Row */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage();
          }}
          className="flex items-center gap-2 pt-1"
        >
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={
              fsmState !== 'idle'
                ? `ממתין להקלטת תשובה (${fsmState})...`
                : 'כתוב הודעה או בחר כפתור למעלה...'
            }
            className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2 text-xs sm:text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={!inputText.trim()}
            className="p-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl transition shadow"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
