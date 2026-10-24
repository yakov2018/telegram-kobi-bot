import React, { useState, useEffect } from 'react';
import { useApp } from './context/AppContext';
import { Header, MainTab } from './components/Header';
import { DriverPanel } from './components/DriverPanel';
import { DispatcherPanel } from './components/DispatcherPanel';
import { StationManagerDashboard } from './components/StationManagerDashboard';
import { AdminDashboard } from './components/AdminDashboard';
import { SupportAndGuidePanel } from './components/SupportAndGuidePanel';
import { RegistrationModal } from './components/RegistrationModal';
import { MiniAppGuideModal } from './components/MiniAppGuideModal';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Ban, Send, CheckCircle2, Clock } from 'lucide-react';

export const AppContent: React.FC = () => {
  const { currentUser, isAuthLoading, isAuthenticated, authError, tickets, createTicket } = useApp();
  const [activeTab, setActiveTab] = useState<MainTab>('driver');
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);

  // Blocked user appeal state
  const [appealMessage, setAppealMessage] = useState('');
  const [appealSent, setAppealSent] = useState(false);
  const [isSendingAppeal, setIsSendingAppeal] = useState(false);

  // סנכרון ראשוני של כרטיסיית ברירת המחדל לפי תפקיד המשתמש המאומת או פרמטר tab מורשה
  useEffect(() => {
    const requestedTab = new URLSearchParams(window.location.search).get('tab') as MainTab | null;
    if (requestedTab === 'support') {
      setActiveTab('support');
      return;
    }

    if (currentUser?.role === 'admin') {
      setActiveTab('admin');
    } else if (currentUser?.role === 'station_manager') {
      setActiveTab('station_manager');
    } else if (currentUser?.role === 'dispatcher') {
      setActiveTab('dispatcher');
    } else {
      setActiveTab('driver');
    }
  }, [currentUser?.role]);

  // 1. מסך טעינה מהשרת
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
        <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-3xl mb-4 animate-bounce">
          🚖
        </div>
        <h2 className="text-lg font-extrabold text-white mb-1.5">טוען נתונים מהשרת...</h2>
        <p className="text-xs text-slate-400 max-w-sm mb-5">
          מאמת הרשאות משתמש מול מסד הנתונים בענן
        </p>
        <div className="w-48 h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className="w-full h-full bg-gradient-to-r from-amber-500 to-amber-300 animate-pulse" />
        </div>
      </div>
    );
  }

  // 2. אם האימות נכשל מול הבוט בטלגרם
  if (authError || !isAuthenticated || !currentUser || currentUser.user_id === 0) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
        <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/30 flex items-center justify-center text-3xl mb-4">
          ⚠️
        </div>
        <h2 className="text-lg font-extrabold text-red-400 mb-2">שגיאה בטעינת נתונים מהשרת</h2>
        <p className="text-xs text-slate-300 max-w-md mb-6 leading-relaxed">
          {authError || 'אימות ה-Mini App נכשל. נא לפתוח את האפליקציה ישירות מכפתור התפריט בבוט הטלגרם.'}
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition shadow cursor-pointer"
        >
          🔄 נסה שוב
        </button>
      </div>
    );
  }

  // 3. חסימה הרמטית למשתמש חסום + טופס הגשת בקשה לשחרור חסימה (סעיפים 2 ו-3)
  if (Number(currentUser.is_blocked) === 1 && currentUser.role !== 'admin') {
    const myUnblockTickets = (tickets || []).filter(
      (t) => t.user_id === currentUser.user_id && t.category === 'unblock_request'
    );

    const handleAppealSubmit = async (e: React.FormEvent) => {
      e.preventDefault();
      if (!appealMessage.trim()) return;
      setIsSendingAppeal(true);
      await createTicket({
        category: 'unblock_request',
        subject: 'בקשה לשחרור חסימה',
        message: appealMessage.trim(),
      });
      setIsSendingAppeal(false);
      setAppealSent(true);
      setAppealMessage('');
    };

    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans" dir="rtl">
        <Header activeTab="driver" setActiveTab={() => {}} />
        <main className="flex-1 max-w-xl w-full mx-auto px-4 py-10 flex flex-col justify-center">
          <div className="bg-slate-900 border border-red-500/40 rounded-2xl p-6 shadow-2xl space-y-5 text-center">
            <div className="w-16 h-16 rounded-2xl bg-red-500/15 border border-red-500/30 flex items-center justify-center mx-auto text-red-400">
              <Ban className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-red-400">חשבונך נחסם על ידי ההנהלה</h1>
              <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">
                אינך רשאי לצפות בקריאות או לבצע פעולות במערכת במצב חסום.
                {currentUser.block_reason ? ` סיבת החסימה: ${currentUser.block_reason}` : ''}
              </p>
            </div>

            {appealSent ? (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-bold space-y-1">
                <CheckCircle2 className="w-6 h-6 mx-auto text-emerald-400 mb-1" />
                <div>בקשתך לשחרור החסימה נשלחה להנהלת המערכת!</div>
                <div className="font-normal text-slate-300">
                  ברגע שהבקשה תאושר, חשבונך ומקלדת הבוט ישוחררו באופן מיידי.
                </div>
              </div>
            ) : (
              <form onSubmit={handleAppealSubmit} className="space-y-3 text-right text-xs">
                <label className="block font-bold text-slate-200">
                  📝 הגש בקשה לשחרור חסימה / פנייה להנהלה:
                </label>
                <textarea
                  rows={4}
                  placeholder="פרט כאן את הסיבה לבקשת שחרור החסימה..."
                  value={appealMessage}
                  onChange={(e) => setAppealMessage(e.target.value)}
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-white focus:outline-none focus:border-amber-500"
                />
                <button
                  type="submit"
                  disabled={isSendingAppeal}
                  className="w-full py-3 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold shadow transition flex items-center justify-center gap-2 cursor-pointer"
                >
                  <Send className="w-4 h-4" />
                  <span>{isSendingAppeal ? 'שולח בקשה...' : 'שלח בקשה לשחרור חסימה'}</span>
                </button>
              </form>
            )}

            {myUnblockTickets.length > 0 && (
              <div className="pt-4 border-t border-slate-800 text-right space-y-2 text-xs">
                <h4 className="font-bold text-slate-400">בקשות קודמות שהגשת:</h4>
                {myUnblockTickets.map((t) => (
                  <div key={t.ticket_id} className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white">בקשה #{t.ticket_id}</span>
                      <span className="inline-flex items-center gap-1 text-[11px] text-amber-300">
                        <Clock className="w-3 h-3" />
                        {t.status === 'resolved' ? 'טופלה' : t.status === 'rejected' ? 'נדחתה' : 'בבדיקת הנהלה'}
                      </span>
                    </div>
                    <p className="text-slate-400">{t.message}</p>
                    {t.admin_reply && (
                      <p className="text-emerald-300 font-bold mt-1">💬 מענה הנהלה: {t.admin_reply}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    );
  }

  // אבטחת הרשאות קפדנית על ניווט (Strict Role-Based Access Control)
  const isDispatcherAllowed = currentUser?.role === 'dispatcher' || currentUser?.role === 'station_manager' || currentUser?.role === 'admin';
  const isStationManagerAllowed = currentUser?.role === 'station_manager' || currentUser?.role === 'admin';
  const isAdminAllowed = currentUser?.role === 'admin';

  // חישוב כרטיסייה מוגנת: חוסם לחלוטין כל זליגת פאנל למי שאינו מורשה
  const safeTab: MainTab =
    activeTab === 'admin' && !isAdminAllowed
      ? 'driver'
      : activeTab === 'station_manager' && !isStationManagerAllowed
      ? 'driver'
      : activeTab === 'dispatcher' && !isDispatcherAllowed
      ? 'driver'
      : activeTab;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans" dir="rtl">
      {/* תפריט עליון מרכזי יחיד */}
      <Header
        activeTab={safeTab}
        setActiveTab={(tab) => {
          if (tab === 'admin' && !isAdminAllowed) return;
          if (tab === 'station_manager' && !isStationManagerAllowed) return;
          if (tab === 'dispatcher' && !isDispatcherAllowed) return;
          setActiveTab(tab);
        }}
        onOpenRegister={() => setIsRegisterOpen(true)}
        onOpenGuide={() => setIsGuideOpen(true)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-6 py-5">
        <ErrorBoundary>
          {/* כרטיסיית נהג - פתוחה לכל המשתמשים הפעילים */}
          {safeTab === 'driver' && <DriverPanel />}

          {/* כרטיסיית סדרן - אך ורק לסדרן, מנהל תחנה ומנהל מערכת */}
          {safeTab === 'dispatcher' && isDispatcherAllowed && <DispatcherPanel />}

          {/* כרטיסיית מנהל תחנה - אך ורק למנהל תחנה ומנהל מערכת */}
          {safeTab === 'station_manager' && isStationManagerAllowed && <StationManagerDashboard />}

          {/* כרטיסיית ניהול מערכת גלובלי - אך ורק ל-Super Admin (God Mode) */}
          {safeTab === 'admin' && isAdminAllowed && <AdminDashboard />}

          {/* כרטיסיית שירות, מדריך למשתמש ותקנון פרטיות */}
          {safeTab === 'support' && <SupportAndGuidePanel />}
        </ErrorBoundary>
      </main>

      <RegistrationModal isOpen={isRegisterOpen} onClose={() => setIsRegisterOpen(false)} />
      <MiniAppGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
    </div>
  );
};

export default AppContent;
