import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { SupportTicket } from '../types';
import {
  MessageSquare,
  BookOpen,
  ShieldCheck,
  Send,
  CheckCircle2,
  Clock,
  XCircle,
  Car,
  MapPin,
  Scale,
  Smartphone,
  ChevronDown,
  ChevronUp,
  Lock,
} from 'lucide-react';

export const SupportAndGuidePanel: React.FC = () => {
  const { currentUser, tickets, createTicket } = useApp();
  const [subTab, setSubTab] = useState<'tickets' | 'guide' | 'privacy'>('tickets');

  // Ticket creation form state
  const [category, setCategory] = useState<SupportTicket['category']>('general');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitBanner, setSubmitBanner] = useState<string | null>(null);

  // Guide accordion state
  const [openGuideId, setOpenGuideId] = useState<string>('g1');

  const myTickets = (tickets || []).filter((t) => t.user_id === currentUser.user_id);

  const handleSubmitTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;
    setIsSubmitting(true);

    const categorySubjects: Record<SupportTicket['category'], string> = {
      general: 'פנייה אישית להנהלה',
      billing: 'בירור בנושא חיוב / עמלה (🍓)',
      bug: 'דיווח על תקלה טכנית',
      idea: 'הצעת ייעול ושיפור',
      unblock_request: 'בקשה לשחרור חסימה',
    };

    const finalSubject = subject.trim() || categorySubjects[category];
    const res = await createTicket({
      category,
      subject: finalSubject,
      message: message.trim(),
    });
    setIsSubmitting(false);

    if (res.ok) {
      setMessage('');
      setSubject('');
      setSubmitBanner(`✅ פנייתך (#${res.ticket_id || ''}) נשלחה בהצלחה להנהלת המערכת! תשובת המנהל תופיע כאן ותישלח אליך ישירות בבוט.`);
      setTimeout(() => setSubmitBanner(null), 6000);
    }
  };

  const GUIDE_SECTIONS = [
    {
      id: 'g1',
      icon: <Smartphone className="w-5 h-5 text-amber-400" />,
      title: '1. איך עובדים עם הבוט והמיני-אפליקציה?',
      items: [
        'סטטוס עבודה (🟢 פנוי / 🔴 תפוס): לחיצה על כפתור "פנוי לעבודה" מחברת אותך למערכת השיגור. כל עוד אתה במצב פנוי, הבוט ישלח אליך התראות בזמן אמת על כל קריאה חדשה המתפרסמת באזורי העבודה שלך.',
        'הפרופיל שלי (💎): מציג את כרטיס הנהג האישי שלך כולל דירוג משוקלל, מספר נסיעות, יתרת חוב, וכפתורים מהירים לעדכון מספר טלפון, החלפת פרטי רכב וצפייה ב-5 הנסיעות האחרונות.',
        'הפרדת הרשאות חכמה: כניסה למיני-אפליקציה מנתבת אותך אוטומטית לעמדה התואמת לתפקידך (נהג, סדרן, מנהל תחנה או מנהל מערכת).',
      ],
    },
    {
      id: 'g2',
      icon: <Car className="w-5 h-5 text-emerald-400" />,
      title: '2. איך לוקחים קריאה ומציעים זמן הגעה (ETA)?',
      items: [
        'צפייה בקריאות זמינות: לחץ על "🚗 קריאות זמינות" בבוט או בעמדת הנהג כדי לראות את כלל הקריאות הפתוחות התואמות לערי העבודה שלך.',
        'הגשת מועמדות וזמן הגעה (ETA): בלחיצה על "קח נסיעה", אם הקריאה דורשת זמן הגעה תתבקש להזין תוך כמה דקות תגיע ללקוח (למשל: 6 דקות).',
        'אישור הסדרן וקבלת פרטי לקוח: הסדרן רואה את ההצעה שלך יחד עם דירוג הנהג ופרטי הרכב. ברגע שהסדרן מאשר אותך – הנסיעה ננעלת עבורך ומספר הטלפון של הלקוח נשלח אליך בפרטי!',
      ],
    },
    {
      id: 'g3',
      icon: <MapPin className="w-5 h-5 text-sky-400" />,
      title: '3. איך עובדים אזורי העבודה והסינון החכם?',
      items: [
        'סינון ממוקד לפי ערים (📍 אזורי עבודה): כדי למנוע עומס התראות על נסיעות רחוקות, תוכל לבחור בדיוק מאילו ערים ברצונך לקבל קריאות (למשל: ירושלים, בני ברק, פתח תקווה).',
        'הוספה והסרה בלחיצה אחת: ניתן להדליק או לכבות ערים פופולריות בלחיצה, או להקליד כל עיר/קיצור (כמו י-ם, ב"ב, פ"ת) ומילון ה-NLP יתרגם אותה אוטומטית.',
        'מצב כל הארץ 🌍: אם רשימת הערים שלך ריקה (או לחצת על "נקה הכל"), המערכת תשלח אליך קריאות מכל רחבי הארץ ללא סינון גיאוגרפי.',
      ],
    },
    {
      id: 'g4',
      icon: <Scale className="w-5 h-5 text-purple-400" />,
      title: '4. התנהלות מול חיובים (🍓), זיכויים (🍏) וערעורים',
      items: [
        'חיוב עמלה (🍓): בסיום נסיעה או בשריון קריאה, נרשם חיוב עמלה לפי אחוז העמלה של התחנה המשגרת.',
        'זיכוי נהג (🍏): כאשר אתה מסדיר תשלום מול התחנה או מזוכה בגין ביטול, מנהל התחנה מזכה את חשבונך והחוב מתקזז מיידית יחד עם הודעת אישור בטלגרם.',
        'הגשת ערעור על חיוב (⚖️): אם לקוח ביטל נסיעה או שנפלה טעות בסכום החיוב, לחץ על "הגש ערעור" ליד החיוב ופרט את הסיבה. מנהל התחנה או מנהל המערכת יבדקו את הערעור ויוכלו לאשר ולבטל את החוב בלחיצה.',
        'תקרת חוב (Auto-Freeze): צבירת חוב פתוח מעל ₪500 מקפיאה זמנית את האפשרות לעבור למצב "פנוי" עד להסדרת היתרה.',
      ],
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in" dir="rtl">
      {/* Header Banner */}
      <div className="bg-slate-900/95 border border-slate-800 rounded-2xl p-5 shadow-md flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-2xl">
            💬
          </div>
          <div>
            <h2 className="text-lg font-extrabold text-white">מרכז שירות, מדריך למשתמש ותקנון פרטיות</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              פתיחת פנייה ישירה להנהלה, מדריך עבודה אינטראקטיבי ותנאי השימוש במערכת
            </p>
          </div>
        </div>

        {/* Sub-navigation buttons */}
        <div className="flex bg-slate-950 p-1.5 rounded-xl border border-slate-800 gap-1.5">
          <button
            onClick={() => setSubTab('tickets')}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
              subTab === 'tickets'
                ? 'bg-amber-500 text-slate-950 shadow'
                : 'text-slate-300 hover:text-white hover:bg-slate-900'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>💬 פניות ומשוב</span>
          </button>
          <button
            onClick={() => setSubTab('guide')}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
              subTab === 'guide'
                ? 'bg-amber-500 text-slate-950 shadow'
                : 'text-slate-300 hover:text-white hover:bg-slate-900'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>📖 מדריך למשתמש</span>
          </button>
          <button
            onClick={() => setSubTab('privacy')}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold transition cursor-pointer ${
              subTab === 'privacy'
                ? 'bg-amber-500 text-slate-950 shadow'
                : 'text-slate-300 hover:text-white hover:bg-slate-900'
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>🔒 תקנון ופרטיות</span>
          </button>
        </div>
      </div>

      {/* SUB-TAB 1: TICKETS & FEEDBACK */}
      {subTab === 'tickets' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Open New Ticket Form */}
          <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
            <h3 className="font-extrabold text-base text-white flex items-center gap-2">
              <Send className="w-4 h-4 text-amber-400" />
              <span>פתיחת פנייה חדשה להנהלה</span>
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              נתקלת בתקלה? יש לך שאלה לגבי חיוב או הצעת ייעול? שלח פנייה ישירה להנהלת המערכת ותקבל מענה בפרטי בטלגרם וכאן באפליקציה.
            </p>

            {submitBanner && (
              <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-bold leading-relaxed">
                {submitBanner}
              </div>
            )}

            <form onSubmit={handleSubmitTicket} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-slate-300 font-bold mb-1.5">סוג הפנייה</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value as SupportTicket['category'])}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="general">📩 פנייה אישית להנהלה</option>
                  <option value="billing">💳 בירור בנושא חיוב / עמלה (🍓)</option>
                  <option value="bug">🛠️ דיווח על תקלה טכנית</option>
                  <option value="idea">💡 הצעת ייעול ושיפור</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1.5">נושא הפנייה (אופציונלי)</label>
                <input
                  type="text"
                  placeholder="למשל: בירור לגבי קריאה #1024"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-bold mb-1.5">פירוט הפנייה</label>
                <textarea
                  rows={4}
                  placeholder="כתוב כאן את כל הפרטים בצורה ברורה..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-3 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-extrabold text-xs shadow-md transition flex items-center justify-center gap-2 cursor-pointer"
              >
                <Send className="w-4 h-4" />
                <span>{isSubmitting ? 'שולח פנייה...' : 'שלח פנייה להנהלה'}</span>
              </button>
            </form>
          </div>

          {/* My Tickets History */}
          <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-amber-400" />
                <span>היסטוריית הפניות שלי ({myTickets.length})</span>
              </h3>
            </div>

            {myTickets.length === 0 ? (
              <div className="text-center py-12 text-slate-500 text-xs space-y-2">
                <div className="text-3xl">📭</div>
                <p>לא פתחת פניות שירות עד כה.</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1">
                {myTickets.map((t) => (
                  <div
                    key={t.ticket_id}
                    className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="font-extrabold text-white">
                        פנייה #{t.ticket_id} • {t.subject}
                      </span>
                      {t.status === 'resolved' ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[11px] font-bold">
                          <CheckCircle2 className="w-3 h-3" />
                          נענתה / טופלה
                        </span>
                      ) : t.status === 'rejected' ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-red-500/15 text-red-300 border border-red-500/30 text-[11px] font-bold">
                          <XCircle className="w-3 h-3" />
                          נדחתה
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[11px] font-bold">
                          <Clock className="w-3 h-3" />
                          בבדיקת הנהלה
                        </span>
                      )}
                    </div>
                    <p className="text-slate-300 leading-relaxed bg-slate-900/70 p-2.5 rounded-lg border border-slate-800/80">
                      {t.message}
                    </p>
                    {t.admin_reply && (
                      <div className="p-3 rounded-lg bg-emerald-950/30 border border-emerald-700/40 text-emerald-200">
                        <strong className="block text-emerald-400 mb-0.5">💬 תגובת הנהלת המערכת:</strong>
                        {t.admin_reply}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUB-TAB 2: INTERACTIVE USER GUIDE */}
      {subTab === 'guide' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
          <div>
            <h3 className="font-extrabold text-base text-white flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-amber-400" />
              <span>מדריך מלא למשתמש – כל מה שצריך לדעת על המערכת</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              לחץ על כל קטגוריה כדי לפתוח את ההסבר המפורט
            </p>
          </div>

          <div className="space-y-3">
            {GUIDE_SECTIONS.map((sec) => {
              const isOpen = openGuideId === sec.id;
              return (
                <div
                  key={sec.id}
                  className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden transition"
                >
                  <button
                    onClick={() => setOpenGuideId(isOpen ? '' : sec.id)}
                    className="w-full p-4 flex items-center justify-between text-right hover:bg-slate-900/60 transition cursor-pointer"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center">
                        {sec.icon}
                      </div>
                      <span className="font-extrabold text-sm text-white">{sec.title}</span>
                    </div>
                    {isOpen ? (
                      <ChevronUp className="w-4 h-4 text-amber-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    )}
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-4 pt-1 border-t border-slate-800/80 space-y-2.5 text-xs text-slate-300 leading-relaxed">
                      {sec.items.map((item, idx) => (
                        <div key={idx} className="flex items-start gap-2">
                          <span className="text-amber-400 font-bold mt-0.5">•</span>
                          <span>{item}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SUB-TAB 3: PRIVACY POLICY & TERMS OF USE */}
      {subTab === 'privacy' && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5 text-xs leading-relaxed text-slate-300">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
              <Lock className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h3 className="font-extrabold text-base text-white">תקנון שימוש ומדיניות פרטיות</h3>
              <p className="text-[11px] text-slate-400">
                כללי ההתנהגות, אבטחת המידע בענן וזכויות המשתמשים במערכת השיגור
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
              <h4 className="font-extrabold text-sm text-amber-400">1. כללי שימוש והתנהגות מקצועית</h4>
              <p>
                • המערכת נועדה לחבר בזמן אמת בין תחנות מוניות/משלוחים, סדרנים ונהגים רשומים ומאומתים בלבד.
              </p>
              <p>
                • נהג המגיש מועמדות לנסיעה ומציין זמן הגעה (ETA) מתחייב לעמוד בזמן שהוצהר ולספק שירות אדיב ובטיחותי ללקוח.
              </p>
              <p>
                • חל איסור מוחלט להעביר מספרי טלפון של לקוחות או פרטי נסיעות לגורמים חיצוניים שאינם רשומים במערכת.
              </p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
              <h4 className="font-extrabold text-sm text-emerald-400">2. מדיניות פרטיות ושמירת נתונים בענן</h4>
              <p>
                • הנתונים נשמרים במסד נתונים מרוחק ומאובטח (PostgreSQL) לצורך תפעול רציף של מערך הקריאות, החובות והמנויים.
              </p>
              <p>
                • המידע הנשמר כולל: מזהה טלגרם, שם מלא, מספר טלפון, פרטי רכב, אזורי עבודה נבחרים, היסטוריית קריאות ומאזן עמלות.
              </p>
              <p>
                • פרטי הנהג מוצגים לסדרן המשגר את הקריאה לצורך אישור הנסיעה בלבד ואינם מועברים לשום גורם מסחרי חיצוני.
              </p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
              <h4 className="font-extrabold text-sm text-sky-400">3. עמלות, חיובים וזכות ערעור</h4>
              <p>
                • כל תחנה מציגה בשקיפות מלאה את אחוז העמלה שלה. חיובי עמלות (🍓) וזיכויים (🍏) מתועדים במלואם בתיק הנהג.
              </p>
              <p>
                • לכל נהג שמורה הזכות המלאה להגיש ערעור מנומק על כל חיוב ישירות מהבוט או מהמיני-אפליקציה.
              </p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-2">
              <h4 className="font-extrabold text-sm text-purple-400">4. אכיפה, חסימות ובקשות שחרור</h4>
              <p>
                • הנהלת המערכת רשאית להשעות או לחסום חשבון נהג בגין הפרת משמעת, מסירת דיווחים כוזבים או אי-הסדרת חוב.
              </p>
              <p>
                • משתמש שחשבונו נחסם רשאי להגיש בקשה מנומקת לשחרור חסימה באמצעות הכפתור הייעודי בבוט או במיני-אפליקציה.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
