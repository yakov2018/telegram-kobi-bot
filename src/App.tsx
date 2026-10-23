import React, { useState, useEffect } from 'react';
import { useApp } from './context/AppContext';
import { Header, MainTab } from './components/Header';
import { DriverPanel } from './components/DriverPanel';
import { DispatcherPanel } from './components/DispatcherPanel';
import { StationManagerDashboard } from './components/StationManagerDashboard';
import { AdminDashboard } from './components/AdminDashboard';
import { RegistrationModal } from './components/RegistrationModal';
import { MiniAppGuideModal } from './components/MiniAppGuideModal';
import { ErrorBoundary } from './components/ErrorBoundary';

export const AppContent: React.FC = () => {
  const { currentUser, isAuthLoading, isAuthenticated, authError } = useApp();
  const [activeTab, setActiveTab] = useState<MainTab>('driver');
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);

  // סנכרון ראשוני של כרטיסיית ברירת המחדל לפי תפקיד המשתמש המאומת
  useEffect(() => {
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

  // 1. מסך טעינה מהשרת - מוסר לחלוטין (unmount) בסיום הבקשה
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center font-sans" dir="rtl">
        <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-3xl mb-4 animate-bounce">
          🚖
        </div>
        <h2 className="text-lg font-extrabold text-white mb-1.5">טוען נתונים מהשרת...</h2>
        <p className="text-xs text-slate-400 max-w-sm mb-5">
          מאמת משתמש מול מסד הנתונים בענן
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
          {/* כרטיסיית נהג - פתוחה לכל המשתמשים */}
          {safeTab === 'driver' && <DriverPanel />}

          {/* כרטיסיית סדרן - אך ורק לסדרן, מנהל תחנה ומנהל מערכת */}
          {safeTab === 'dispatcher' && isDispatcherAllowed && <DispatcherPanel />}

          {/* כרטיסיית מנהל תחנה - אך ורק למנהל תחנה ומנהל מערכת */}
          {safeTab === 'station_manager' && isStationManagerAllowed && <StationManagerDashboard />}

          {/* כרטיסיית ניהול מערכת גלובלי - אך ורק ל-Super Admin (God Mode) */}
          {safeTab === 'admin' && isAdminAllowed && <AdminDashboard />}
        </ErrorBoundary>
      </main>

      <RegistrationModal isOpen={isRegisterOpen} onClose={() => setIsRegisterOpen(false)} />
      <MiniAppGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
    </div>
  );
};

export default AppContent;
