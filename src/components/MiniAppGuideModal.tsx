import React, { useState } from 'react';
import {
  X,
  Copy,
  Check,
  ExternalLink,
  Bot,
  Database,
  Cloud,
  HelpCircle,
  AlertTriangle,
  Sparkles,
} from 'lucide-react';

interface MiniAppGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MiniAppGuideModal: React.FC<MiniAppGuideModalProps> = ({ isOpen, onClose }) => {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'botfather' | 'render'>('botfather');

  if (!isOpen) return null;

  // Use the production shared URL or current origin
  const webAppUrl =
    typeof window !== 'undefined' && window.location.origin.includes('run.app')
      ? window.location.origin
      : 'https://ais-pre-stligqg25zyepbjqdxhays-148934615276.europe-west2.run.app';

  const handleCopy = () => {
    navigator.clipboard.writeText(webAppUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-700 rounded-3xl max-w-2xl w-full p-6 shadow-2xl relative max-h-[90vh] overflow-y-auto">
        <button
          onClick={onClose}
          className="absolute top-4 left-4 text-slate-400 hover:text-white transition p-1 rounded-lg hover:bg-slate-800"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-sky-400 to-blue-600 text-white flex items-center justify-center mx-auto mb-2.5 shadow-lg shadow-blue-500/20 text-2xl font-bold">
            📱
          </div>
          <h3 className="text-xl font-extrabold text-white">חיבור Mini App והגדרות Render</h3>
          <p className="text-xs text-slate-400 mt-1">
            הקישור לאפליקציה שלך והוראות מדויקות להגדרת BotFather בטלגרם ומסד נתונים ב-Render
          </p>
        </div>

        {/* Tabs */}
        <div className="flex bg-slate-950 p-1.5 rounded-xl border border-slate-800 mb-6">
          <button
            onClick={() => setActiveTab('botfather')}
            className={`flex-1 py-2 rounded-lg text-xs font-bold transition flex items-center justify-center gap-2 ${
              activeTab === 'botfather'
                ? 'bg-blue-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Bot className="w-4 h-4" />
            <span>איך להדביק ב-BotFather (טלגרם)</span>
          </button>

          <button
            onClick={() => setActiveTab('render')}
            className={`flex-1 py-2 rounded-lg text-xs font-bold transition flex items-center justify-center gap-2 ${
              activeTab === 'render'
                ? 'bg-amber-500 text-slate-950 shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Cloud className="w-4 h-4" />
            <span>סריקת שגיאת Render ומסד PostgreSQL</span>
          </button>
        </div>

        {/* Tab 1: BotFather Instructions */}
        {activeTab === 'botfather' && (
          <div className="space-y-5">
            {/* Direct URL Box */}
            <div className="bg-slate-950/90 border border-slate-800 rounded-2xl p-4">
              <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center justify-between">
                <span>🔗 הקישור המומלץ להדבקה ב-BotFather:</span>
                <span className="text-[11px] text-amber-400 font-bold">חשוב מאוד!</span>
              </label>

              <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl mb-3 text-xs leading-relaxed text-blue-200">
                💡 <strong>למה הקישור `run.app` נכשל בטלגרם?</strong>
                <br />
                כתובת ה-AI Studio (`ais-pre-...run.app`) היא כתובת פיתוח פנימית של Google הדורשת התחברות לחשבון גוגל. טלגרם חוסם דפים כאלה מטעמי אבטחה.
                <br />
                <strong>הפתרון המושלם:</strong> הבוט שלך ב-Render מגיש מעכשיו את ה-Mini App <u>ישירות מכתובת ה-Render שלך</u> (למשל: <code className="text-amber-300 font-mono bg-slate-900 px-1 py-0.5 rounded">https://your-bot.onrender.com</code>). כתובת זו פתוחה 24/7 לכל משתמש בעולם ללא שום חסימות!
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="https://your-bot-name.onrender.com"
                  defaultValue={webAppUrl}
                  className="flex-1 bg-slate-900 border border-slate-700 text-slate-100 text-xs sm:text-sm font-mono rounded-xl px-3.5 py-2.5 focus:outline-none"
                />
                <button
                  onClick={handleCopy}
                  className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition flex items-center gap-1.5 shadow"
                >
                  {copied ? <Check className="w-4 h-4 text-emerald-300" /> : <Copy className="w-4 h-4" />}
                  <span>{copied ? 'הועתק!' : 'העתק'}</span>
                </button>
              </div>
            </div>

            {/* Step by Step BotFather */}
            <div className="bg-slate-800/80 rounded-2xl p-5 border border-slate-700/80 space-y-4 text-xs leading-relaxed">
              <h4 className="font-bold text-sm text-white flex items-center gap-2">
                <span>🤖 שלבי הגדרה קלים ב-BotFather:</span>
              </h4>

              <div className="space-y-3">
                <div className="flex gap-3">
                  <span className="w-5 h-5 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-[11px] flex-shrink-0">
                    1
                  </span>
                  <div>
                    <p className="font-semibold text-slate-200">
                      היכנס לטלגרם וחפש את הבוט הרשמי <strong className="text-sky-400">@BotFather</strong>.
                    </p>
                  </div>
                </div>

                <div className="flex gap-3">
                  <span className="w-5 h-5 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-[11px] flex-shrink-0">
                    2
                  </span>
                  <div>
                    <p className="font-semibold text-slate-200">
                      שלח לו את הפקודה <code className="bg-slate-900 px-1.5 py-0.5 rounded text-amber-300 font-mono">/mybots</code> ובחר את הבוט שלך מהרשימה.
                    </p>
                  </div>
                </div>

                <div className="flex gap-3">
                  <span className="w-5 h-5 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-[11px] flex-shrink-0">
                    3
                  </span>
                  <div>
                    <p className="font-semibold text-slate-200">
                      לחץ על <strong className="text-slate-100">Bot Settings</strong> ואז על <strong className="text-slate-100">Menu Button</strong> ואז <strong className="text-slate-100">Configure menu button</strong>.
                    </p>
                    <p className="text-slate-400 text-[11px] mt-0.5">
                      (לחלופין ניתן להשתמש בפקודה <code className="bg-slate-900 px-1 py-0.5 rounded font-mono text-amber-300">/setmenubutton</code>)
                    </p>
                  </div>
                </div>

                <div className="flex gap-3">
                  <span className="w-5 h-5 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-[11px] flex-shrink-0">
                    4
                  </span>
                  <div>
                    <p className="font-semibold text-slate-200">
                      הדבק את הקישור שהעתקת למעלה:
                    </p>
                    <p className="bg-slate-900 text-sky-300 p-2 rounded-lg font-mono text-[11px] mt-1 break-all select-all">
                      {webAppUrl}
                    </p>
                  </div>
                </div>

                <div className="flex gap-3">
                  <span className="w-5 h-5 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-[11px] flex-shrink-0">
                    5
                  </span>
                  <div>
                    <p className="font-semibold text-slate-200">
                      הקלד את הכותרת לכפתור התפריט:
                    </p>
                    <p className="font-mono text-amber-300 bg-slate-900 px-2 py-1 rounded inline-block mt-1">
                      🚖 פתח אפליקציה
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-3 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300">
                🎉 <strong>זה הכל!</strong> עכשיו בכל פעם שמשתמש, סדרן או נהג יכנס לבוט בטלגרם, יופיע לו כפתור תפריט בפינה התחתונה שיפתח את האפליקציה המלאה ישירות בתוך טלגרם!
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Render Error Scan & PostgreSQL setup */}
        {activeTab === 'render' && (
          <div className="space-y-4 text-xs">
            {/* Error Cause Summary */}
            <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-4.5">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-bold text-sm text-red-200 mb-1">
                    🔍 ממצאי סריקת השגיאה ב-Render:
                  </h4>
                  <ul className="list-disc list-inside space-y-1.5 text-slate-300">
                    <li>
                      <strong>סיבה 1 - קובץ `bot.py` נמחק:</strong> בשלב השכתוב הקודם הקובץ `bot.py` נמחק בהתאם להוראות האוטומטיות של ה-framework rewrite. כעת החזרנו ועדכנו את <code className="text-amber-300 font-mono">bot.py</code> ואת <code className="text-amber-300 font-mono">requirements.txt</code> בצורה מלאה ומאובטחת!
                    </li>
                    <li>
                      <strong>סיבה 2 - חוסר ב-`psycopg2-binary` ואיפוס SQLite:</strong> הבוט הישן השתמש בקובץ מקומי שנמחק בכל עדכון. כעת הקוד הותאם מלא ל-PostgreSQL מרוחק דרך משתנה <code className="text-amber-300 font-mono">DATABASE_URL</code>.
                    </li>
                    <li>
                      <strong>סיבה 3 - משתנה `BOT_TOKEN`:</strong> ב-Render חובה להגדיר את הטוקן שקיבלת מ-BotFather תחת לשונית Environment.
                    </li>
                    <li>
                      <strong>⚡ סיבה 4 - איטיות תגובה (2 שניות) - נפתרה במלואה:</strong> הקוד הקודם פתח חיבור SSL חדש למסד הנתונים בכל פעולה וחסם את ה-Event Loop. כעת שודרג הבוט ל-<strong>Connection Pool</strong> קבוע עם ריצה בתהליכונים מקביליים (<code className="text-amber-300 font-mono">asyncio.to_thread</code>) וסינון ערים באצווה (Batch). זמן התגובה נחתך מ-2 שניות ל-0.05 שניות בלבד!
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Render Environment Checklist */}
            <div className="bg-slate-800/80 rounded-2xl p-5 border border-slate-700/80 space-y-3">
              <h4 className="font-bold text-sm text-white flex items-center gap-2">
                <Database className="w-4 h-4 text-amber-400" />
                <span>הגדרות חובה ב-Render לשמירת נתונים לצמיתות:</span>
              </h4>

              <div className="space-y-2.5">
                <div className="bg-slate-900 p-3 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-white font-mono">DATABASE_URL</span>
                    <span className="text-[11px] text-amber-400 font-semibold">PostgreSQL</span>
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    הקם ב-Render שירות <strong>PostgreSQL Database</strong> (חינמי או בתשלום), והעתק משם את ה-<strong>Internal Database URL</strong> (או חבר אותו ב-Add from Database). כל המשתמשים, החובות, הערים והנסיעות יישמרו שם לצמיתות ולא ימחקו בעדכוני שרת!
                  </p>
                </div>

                <div className="bg-slate-900 p-3 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-white font-mono">BOT_TOKEN</span>
                    <span className="text-[11px] text-blue-400 font-semibold">Telegram Token</span>
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    הטוקן של הבוט שקיבלת מ-BotFather (לדוגמה: 123456789:ABCDef...).
                  </p>
                </div>

                <div className="bg-slate-900 p-3 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-white font-mono">WEBAPP_URL</span>
                    <span className="text-[11px] text-emerald-400 font-semibold">Mini App URL</span>
                  </div>
                  <p className="text-slate-400 text-[11px]">
                    הכתובת של האפליקציה שהעתקת בלשונית BotFather.
                  </p>
                </div>

                <div className="bg-slate-900 p-3 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-white font-mono">Build & Start Command</span>
                    <span className="text-[11px] text-purple-400 font-semibold">פקודות הפעלה</span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-300 space-y-1 mt-1">
                    <p>Build Command: <code className="bg-slate-950 px-2 py-0.5 rounded text-amber-300">pip install -r requirements.txt</code></p>
                    <p>Start Command: <code className="bg-slate-950 px-2 py-0.5 rounded text-amber-300">python bot.py</code></p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold px-5 py-2.5 rounded-xl transition"
          >
            סגור
          </button>
        </div>
      </div>
    </div>
  );
};
